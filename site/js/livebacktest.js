// Live backtest engine: steps month by month through site/data/backtest_months.json, decides with
// either the saved gpt-4o masked views (instant replay) or the in-browser committee (WebLLM), and
// scores every decision with the realised next-month returns. Benchmarks computed alongside:
// fixed 60/40 and prior-only (no views). Costs: flat bps per unit one-way turnover.
import { allocate, EQUILIBRIUM_SPY } from './allocation.js?v=202609222113';
import { ensureEngine, browserRoleCall, parseView, parseCio, DOWNGRADE } from './pipeline.js?v=202609222113';

export async function loadMonths() {
  const r = await fetch('./data/backtest_months.json', { cache: 'no-store' });
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
    this.months = months; this.opts = { costBps: 5, mode: 'saved', browserModel: 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC', gate: true, ...opts };
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
    if (this.opts.mode === 'saved') {
      if (m.saved) { views = [m.saved.spy_q, m.saved.tlt_q]; confRep = m.saved.confidence; detail = { source: 'saved gpt-4o masked view', econ: null, risk: null, cio: `SPY ${m.saved.spy_q}% · TLT ${m.saved.tlt_q}% · ${confRep}` }; }
      else { detail = { source: 'no saved view', cio: 'prior only' }; }
      await new Promise(r => setTimeout(r, this.opts.delayMs ?? 120));
    } else if (this.opts.mode === 'site') {
      // gpt-4o via the site's rate-limited endpoint; prompts are built server-side from the month index
      onEvent && onEvent('stage1-start', { parallel: true });
      const r = await fetch('./api/committee', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ i: m.i }) });
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
