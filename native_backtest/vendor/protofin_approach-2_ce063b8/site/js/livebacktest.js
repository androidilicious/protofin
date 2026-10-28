// Backtest replay engine: steps month by month through site/data/backtest_months.json, decides with
// the saved answers (gpt-4o committee or Jev; recorded once, no model is called from the site), and
// scores every decision with the realised next-month returns. Benchmarks computed alongside:
// fixed 60/40 and prior-only (no views). Costs: flat bps per unit one-way turnover.
import { allocate, EQUILIBRIUM_SPY, DELTA, MIN_SPY, MAX_SPY } from './allocation.js?v=202610042259';
import { DOWNGRADE } from './pipeline.js?v=202610042259';

// Jev answers are read defensively: find each question's block wherever the response nests it.
const TILT_OFFSET = { strong_equities: 3, lean_equities: 1.5, neutral: 0, lean_bonds: -1.5, strong_bonds: -3 };   // points added to the stock-minus-bond edge
function findKey(o, key, depth = 0) {
  if (!o || typeof o !== 'object' || depth > 6) return undefined;
  if (key in o) return o[key];
  for (const v of Object.values(o)) { const r = findKey(v, key, depth + 1); if (r !== undefined) return r; }
  return undefined;
}
export function readJev(raw) {
  const q1 = findKey(raw, 'stocks_beat_bonds') ?? {}, q2 = findKey(raw, 'tilt') ?? {};
  const num = v => (typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' && !isNaN(+v) ? +v : null);
  let p = num(q1.noul) ?? num(q1.probability) ?? num(q1.p) ?? num(findKey(q1, 'true')) ?? (typeof q1.answer === 'boolean' ? (q1.answer ? 1 : 0) : null);
  if (p != null && p > 1) p /= 100;
  const probs = findKey(q2, 'probabilities') || {};
  const choice = q2.answer ?? q2.value ?? q2.choice ?? Object.entries(probs).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'neutral';
  let conf = num(q2.confidence) ?? num(q1.confidence) ?? (p != null ? Math.abs(2 * p - 1) : 0);
  if (conf > 1) conf /= 100;
  const offset = Object.keys(probs).length ? Object.entries(probs).reduce((acc, [k, v]) => acc + (TILT_OFFSET[k] ?? 0) * (num(v) ?? 0), 0) : (TILT_OFFSET[choice] ?? 0);
  return { p: p ?? 0.5, choice, probs, confidence: Math.max(0, Math.min(1, conf)), offset };
}

// Months plus every saved answer. Nothing on the site calls a model: the committee replies were
// recorded once locally (research/run_saved_committee.py) and Jev's once (scripts/build_jev_runs.py).
const getJson = async name => { const r = await fetch(new URL('../data/' + name, import.meta.url), { cache: 'no-store' }); return r.ok ? r.json() : null; };
export async function loadMonths() {
  const [base, com, jev, sto] = await Promise.all([getJson('backtest_months.json'), getJson('committee_runs.json'), getJson('jev_runs.json'), getJson('stochastic_runs.json')]);
  if (!base) throw new Error('backtest_months.json not found');
  for (const m of base.months) { m.committee = com?.months?.[m.as_of] || null; m.jev = jev?.months?.[m.as_of] || null; m.runs = sto?.months?.[m.as_of] || null; }
  return base.months;
}

// Net-of-cost path for a given list of monthly SPY weights (same accounting as LiveBacktest.step).
export function simulate(months, weights, costBps = 5) {
  const cost = costBps / 1e4; let nav = 1, w = EQUILIBRIUM_SPY, turnover = 0;
  const navs = [1], rets = [], rf = [];
  months.forEach((m, i) => {
    const t = weights[i], turn = Math.abs(t - w);
    if (turn > 1e-9) { turnover += turn; nav *= 1 - turn * cost; }
    const ret = t * m.r_spy + (1 - t) * m.r_tlt;
    nav *= 1 + ret; navs.push(nav); rets.push(ret); rf.push(Math.pow(1 + m.rf_pct / 100, 1 / 12) - 1);
    w = (t * (1 + m.r_spy)) / (1 + ret);
  });
  return { navs, ...stats(navs, rets, rf), turnover };
}

function stats(navs, rets, rfMonthly) {
  const n = rets.length; if (n < 2) return { cagr: 0, vol: 0, sharpe: 0, maxdd: 0 };
  const years = n / 12;
  const cagr = Math.pow(navs[navs.length - 1] / navs[0], 1 / years) - 1;
  const ex = rets.map((r, i) => r - (rfMonthly[i] || 0));
  const mean = ex.reduce((a, b) => a + b, 0) / n;
  const sd = Math.sqrt(ex.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1));
  const vol = Math.sqrt(rets.reduce((a, b) => a + (b - rets.reduce((x, y) => x + y, 0) / n) ** 2, 0) / (n - 1)) * Math.sqrt(12);
  let peak = navs[0], maxdd = 0;
  for (const v of navs) { peak = Math.max(peak, v); maxdd = Math.min(maxdd, v / peak - 1); }
  return { cagr, vol, sharpe: sd > 0 ? (mean / sd) * Math.sqrt(12) : 0, maxdd };
}

export class LiveBacktest {
  constructor(months, opts) {
    this.months = months; this.opts = { costBps: 5, mode: 'saved', gate: true, ...opts };
    this.reset();
  }
  reset() {
    this.i = this.opts.start || 0; this.running = false;
    this.nav = { live: 1, fixed: 1, prior: 1 }; this.w = { live: EQUILIBRIUM_SPY, fixed: EQUILIBRIUM_SPY, prior: EQUILIBRIUM_SPY };
    this.hist = { dates: [], live: [], fixed: [], prior: [], wlive: [], wprior: [], rlive: [], rfixed: [], rprior: [], rf: [] };
    this.trades = { live: 0, fixed: 0, prior: 0 }; this.turnover = { live: 0, fixed: 0, prior: 0 }; this.rejected = 0;
    this.log = [];
  }
  // decide the SPY weight for one month with the chosen committee; returns {w, detail}
  async decide(m, onEvent) {
    const cost = this.opts.costBps / 1e4;
    let views = null, conf = 'Medium', confRep = 'Medium', detail = {};
    await new Promise(r => setTimeout(r, this.opts.delayMs ?? 120));
    if (this.opts.mode === 'jev') {
      // Jev (typesafe/jev) answers recorded once; replayed here. Typed probabilities, no text.
      const jv = m.jev;
      if (!jv) { const d0 = allocate(m.sigma, null, 'Medium', m.rf_pct, null); return { w: d0.target_spy, conf: 'n/a', confRep: 'n/a', views: null, detail: { source: 'no saved Jev answer', cio: 'prior only' } }; }
      const pi = allocate(m.sigma, null, 'Medium', m.rf_pct, null).pi;
      const baseEdge = (pi[0] - pi[1]) * 100;
      const edge = baseEdge + jv.confidence * jv.offset;            // blend: confidence is the weight on Jev's tilt
      const S = m.sigma, x = ((edge / 100) / DELTA + S[1][1] - S[0][1]) / (S[0][0] + S[1][1] - 2 * S[0][1]);
      const w = Math.min(MAX_SPY, Math.max(MIN_SPY, x));
      return { w, conf: `${(jv.confidence * 100).toFixed(0)}%`, confRep: `${(jv.confidence * 100).toFixed(0)}%`, views: [+(jv.p * 100).toFixed(0), +jv.offset.toFixed(2)],
               detail: { source: 'saved typesafe/jev answer', econ: { text: `P(stocks beat bonds, 12m) = ${(jv.p * 100).toFixed(0)}%` },
                 risk: { text: `tilt: ${jv.choice} · ` + Object.entries(jv.probs).map(([k, v]) => `${k.replace('_', ' ')} ${(v * 100).toFixed(0)}%`).join(' · ') },
                 cio: `Jev tilt ${jv.offset >= 0 ? '+' : ''}${jv.offset.toFixed(2)} pts × confidence ${(jv.confidence * 100).toFixed(0)}% → edge ${baseEdge.toFixed(2)} → ${edge.toFixed(2)} → SPY ${(w * 100).toFixed(1)}%`, jev: jv,
                 calc: { S, delta: DELTA, pi: [pi[0] * 100, pi[1] * 100], baseEdge, weightedOffset: jv.confidence * jv.offset, edge, xRaw: x * 100, w: w * 100, lo: MIN_SPY * 100, hi: MAX_SPY * 100, offsets: TILT_OFFSET } } };
    }
    // saved three-persona committee (economist ∥ risk -> CIO, temperature 0), one run per month
    const c = m.committee;
    if (c && !c.problems.length) { views = [c.cio.spy_q, c.cio.tlt_q]; confRep = c.cio.confidence; detail = { source: 'saved gpt-4o committee', econ: c.economist, risk: c.risk, cio: c.cio.cio }; }
    else if (c) { this.rejected++; detail = { source: 'saved gpt-4o committee', econ: c.economist, risk: c.risk, cio: `CIO reply unusable (${c.problems.join('; ')}) → prior only`, problems: c.problems }; }
    else if (m.saved) { views = [m.saved.spy_q, m.saved.tlt_q]; confRep = m.saved.confidence; detail = { source: 'saved gpt-4o masked view (single call)', econ: null, risk: null, cio: `SPY ${m.saved.spy_q}% · TLT ${m.saved.tlt_q}% · ${confRep}` }; }
    else detail = { source: 'no saved view', cio: 'prior only' };
    conf = (this.opts.gate && m.regime === 'elevated') ? DOWNGRADE[confRep] : confRep;
    const d = allocate(m.sigma, views, conf, m.rf_pct, null);
    return { w: d.target_spy, conf, confRep, views, detail };
  }
  async step(onEvent) {
    const m = this.months[this.i]; if (!m) return null;
    const cost = this.opts.costBps / 1e4;
    const dec = await this.decide(m, onEvent);
    const priorW = allocate(m.sigma, null, 'Medium', m.rf_pct, null).target_spy;
    const targets = { live: dec.w, fixed: EQUILIBRIUM_SPY, prior: priorW };
    const rfm = Math.pow(1 + m.rf_pct / 100, 1 / 12) - 1;
    for (const k of ['live', 'fixed', 'prior']) {
      const turn = Math.abs(targets[k] - this.w[k]);
      if (turn > 1e-9) { this.trades[k]++; this.turnover[k] += turn; this.nav[k] *= 1 - turn * cost; }
      const wk = targets[k];
      const ret = wk * m.r_spy + (1 - wk) * m.r_tlt;
      this.nav[k] *= 1 + ret;
      this.hist['r' + k].push(ret);
      // drift to next month
      this.w[k] = (wk * (1 + m.r_spy)) / (1 + ret);
    }
    this.hist.dates.push(m.next); this.hist.live.push(this.nav.live); this.hist.fixed.push(this.nav.fixed); this.hist.prior.push(this.nav.prior);
    this.hist.wlive.push(dec.w * 100); this.hist.wprior.push(priorW * 100); this.hist.rf.push(rfm);
    const rec = { as_of: m.as_of, next: m.next, w: dec.w, conf: dec.conf, confRep: dec.confRep, views: dec.views, regime: m.regime, r_spy: m.r_spy, r_tlt: m.r_tlt, ...dec.detail };
    this.log.push(rec);
    this.i++;
    return rec;
  }
  summary() {
    const s = k => stats([1, ...this.hist[k]], this.hist['r' + k], this.hist.rf);
    return { live: { ...s('live'), trades: this.trades.live, turnover: this.turnover.live, rejected: this.rejected },
             fixed: { ...s('fixed'), trades: this.trades.fixed, turnover: this.turnover.fixed },
             prior: { ...s('prior'), trades: this.trades.prior, turnover: this.turnover.prior },
             months: this.hist.dates.length };
  }
}
