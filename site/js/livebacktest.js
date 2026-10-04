// Live backtest engine: steps month by month through site/data/backtest_months.json, decides with
// either the saved gpt-4o masked views (instant replay) or the in-browser committee (WebLLM), and
// scores every decision with the realised next-month returns. Benchmarks computed alongside:
// fixed 60/40 and prior-only (no views). Costs: flat bps per unit one-way turnover.
import { allocate, EQUILIBRIUM_SPY, DELTA, MIN_SPY, MAX_SPY } from './allocation.js?v=202610040144';
import { ensureEngine, browserRoleCall, parseView, parseCio, DOWNGRADE } from './pipeline.js?v=202610040144';

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

export async function loadMonths() {
  const r = await fetch(new URL('../data/backtest_months.json', import.meta.url), { cache: 'no-store' });
  if (!r.ok) throw new Error('backtest_months.json not found');
  return (await r.json()).months;
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
    this.months = months; this.opts = { costBps: 5, mode: 'saved', apiBase: '.', browserModel: 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC', gate: true, ...opts };
    this.reset();
  }
  reset() {
    this.runId = (globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : 'r' + Date.now() + Math.random().toString(36).slice(2)).replace(/[^A-Za-z0-9_-]/g, '');
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
    if (this.opts.mode === 'saved') {
      if (m.saved) { views = [m.saved.spy_q, m.saved.tlt_q]; confRep = m.saved.confidence; detail = { source: 'saved gpt-4o masked view', econ: null, risk: null, cio: `SPY ${m.saved.spy_q}% · TLT ${m.saved.tlt_q}% · ${confRep}` }; }
      else { detail = { source: 'no saved view', cio: 'prior only' }; }
      await new Promise(r => setTimeout(r, this.opts.delayMs ?? 120));
    } else if (this.opts.mode === 'jev') {
      // Jev (typesafe/jev) via the Workers AI binding: typed answers with probabilities, no API key anywhere
      onEvent && onEvent('stage1-start', { parallel: true });
      const r = await fetch(this.opts.apiBase + '/api/jev', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ i: m.i, run: this.runId }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { const err = new Error(j.error || `jev endpoint ${r.status}`); err.status = r.status; throw err; }
      const jv = readJev(j.raw);
      const pi = allocate(m.sigma, null, 'Medium', m.rf_pct, null).pi;
      const baseEdge = (pi[0] - pi[1]) * 100;
      const edge = baseEdge + jv.confidence * jv.offset;            // blend: confidence is the weight on Jev's tilt
      const S = m.sigma, x = ((edge / 100) / DELTA + S[1][1] - S[0][1]) / (S[0][0] + S[1][1] - 2 * S[0][1]);
      const w = Math.min(MAX_SPY, Math.max(MIN_SPY, x));
      onEvent && onEvent('economist', { raw: JSON.stringify(j.raw), view: { text: `P(stocks beat bonds, 12m) = ${(jv.p * 100).toFixed(0)}%` }, ms: j.ms, ok: jv.p != null });
      onEvent && onEvent('risk', { raw: JSON.stringify(j.raw), view: { text: `tilt: ${jv.choice} · ` + Object.entries(jv.probs).map(([k, v]) => `${k.replace('_', ' ')} ${(v * 100).toFixed(0)}%`).join(' · ') }, ms: j.ms, ok: true });
      onEvent && onEvent('cio-start', {});
      onEvent && onEvent('cio', { raw: '', fields: { cio: `Jev tilt ${jv.offset >= 0 ? '+' : ''}${jv.offset.toFixed(2)} pts × confidence ${(jv.confidence * 100).toFixed(0)}% → edge ${baseEdge.toFixed(2)} → ${edge.toFixed(2)} → SPY ${(w * 100).toFixed(1)}%` }, problems: [], ms: 0 });
      return { w, conf: `${(jv.confidence * 100).toFixed(0)}%`, confRep: `${(jv.confidence * 100).toFixed(0)}%`, views: [+(jv.p * 100).toFixed(0), +jv.offset.toFixed(2)],
               detail: { source: 'typesafe/jev', econ: { text: `P(stocks beat bonds) ${(jv.p * 100).toFixed(0)}%` }, risk: { text: `tilt ${jv.choice}` }, cio: `edge ${baseEdge.toFixed(2)} → ${edge.toFixed(2)}`, jev: jv,
                 calc: { S, delta: DELTA, pi: [pi[0] * 100, pi[1] * 100], baseEdge, weightedOffset: jv.confidence * jv.offset, edge, xRaw: x * 100, w: w * 100, lo: MIN_SPY * 100, hi: MAX_SPY * 100, offsets: TILT_OFFSET } } };
    } else if (this.opts.mode === 'site') {
      // gpt-4o via the site's rate-limited endpoint; prompts are built server-side from the month index
      onEvent && onEvent('stage1-start', { parallel: true });
      const r = await fetch('./api/committee', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ i: m.i, run: this.runId }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { const err = new Error(j.error || `committee endpoint ${r.status}`); err.status = r.status; err.remaining = j.remaining; throw err; }
      const ev = parseView(j.economist_raw, 'economist'), rv = parseView(j.risk_raw, 'risk');
      onEvent && onEvent('economist', { raw: j.economist_raw, view: ev, ms: j.timings.economist_ms, ok: true });
      onEvent && onEvent('risk', { raw: j.risk_raw, view: rv, ms: j.timings.risk_ms, ok: true });
      onEvent && onEvent('cio-start', {});
      const { fields, problems } = parseCio(j.cio_raw);
      onEvent && onEvent('cio', { raw: j.cio_raw, fields, problems, ms: j.timings.cio_ms });
      if (problems.length === 0) { views = [fields.spy_q, fields.tlt_q]; confRep = fields.confidence; } else this.rejected++;
      detail = { source: `${j.model} via site endpoint (economist ∥ risk concurrent, then CIO)`, econ: ev, risk: rv, cio: fields.cio, problems, remaining: j.remaining, timings: j.timings };
    } else {
      await ensureEngine(this.opts.browserModel, this.opts.onProgress);
      onEvent && onEvent('stage1-start', {});
      const call = async role => { const t = performance.now(); const rr = await browserRoleCall(role, m.prompts[role], this.opts); const out = rr.raw; const v = parseView(out, role); onEvent && onEvent(role, { raw: out, view: v, ms: Math.round(performance.now() - t), retried: rr.retried, ok: rr.ok }); return { out, v }; };
      const [e, r] = await Promise.all([call('economist'), call('risk')]);
      const cioPrompt = m.prompts.cio.replace('{ECONOMIST_VIEW}', e.out.trim()).replace('{RISK_VIEW}', r.out.trim());
      onEvent && onEvent('cio-start', {});
      const t = performance.now(); const rc = await browserRoleCall('cio', cioPrompt, this.opts); const cioRaw = rc.raw;
      const { fields, problems } = parseCio(cioRaw);
      onEvent && onEvent('cio', { raw: cioRaw, fields, problems, ms: Math.round(performance.now() - t), retried: rc.retried });
      if (problems.length === 0) { views = [fields.spy_q, fields.tlt_q]; confRep = fields.confidence; } else this.rejected++;
      detail = { source: this.opts.browserModel, econ: e.v, risk: r.v, cio: fields.cio, problems, cioNums: problems.length ? null : [fields.spy_q, fields.tlt_q, fields.confidence] };
    }
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
