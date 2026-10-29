// Forecast-to-allocation sensitivity for the two Agentic Workflow engines, run on the NATIVE engines unchanged.
//
// For each pre-registered signal strength lambda, the saved monthly answer is rescaled at the one point where the
// signal enters the native allocator, and the engine's own decide() produces the weight:
//
//   jev        edge = baseEdge + confidence x offset        ->  offset(lambda) = lambda x offset
//   committee  q    = (viewsTotalPct - rf) / 100            ->  q(lambda) = pi + lambda x (q - pi),
//                                                               passed back as viewsTotalPct(lambda) = 100 q(lambda) + rf
//
// Nothing else is touched: confidence, the regime confidence gate, sigma, rf, the equilibrium prior, the clip at
// MIN_SPY/MAX_SPY and the engine's own code all stay as they are. Outcome fields are deleted from every month
// object before decide() is called, so a decision cannot read a realised return. Months after --last-as-of (the
// protected window) are never stepped. The only shim is a fetch() for file: URLs.
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, ...v] = a.replace(/^--/, '').split('='); return [k, v.join('=')]; }));
const engineDir = path.resolve(args.engine);
const mode = args.mode;                                     // jev | committee
const last = args['last-as-of'];
const lambdas = (args.lambdas || '0,0.5,1,2').split(',').map(Number);
if (!last) throw new Error('--last-as-of is required');
if (!['jev', 'committee'].includes(mode)) throw new Error(`--mode must be jev or committee, got ${mode}`);

globalThis.fetch = async (url) => {
  const u = url instanceof URL ? url : new URL(String(url));
  if (u.protocol !== 'file:') throw new Error(`network fetch blocked in harness: ${u}`);
  try {
    return { ok: true, status: 200, json: async () => JSON.parse(await readFile(fileURLToPath(u), 'utf8')) };
  } catch {
    return { ok: false, status: 404, json: async () => null };
  }
};

const lb = await import(pathToFileURL(path.join(engineDir, 'livebacktest.js')).href);
const al = await import(pathToFileURL(path.join(engineDir, 'allocation.js')).href);
const OUTCOME_KEYS = ['r_spy', 'r_tlt', 'next'];
const all = await lb.loadMonths();
const months = all.filter(m => m.as_of <= last);
const engineMode = mode === 'jev' ? 'jev' : 'saved';
const bt = new lb.LiveBacktest(months, { mode: engineMode, delayMs: 0 });

// the native committee view for a month, in total-return percent, or null when the engine would decide prior-only
function committeeViews(m) {
  const c = m.committee;
  if (c && !c.problems.length) return [c.cio.spy_q, c.cio.tlt_q];
  if (!c && m.saved) return [m.saved.spy_q, m.saved.tlt_q];
  return null;
}

const out = {};
for (const lam of lambdas) {
  const rows = [];
  for (const m0 of months) {
    const m = { ...m0 };
    for (const k of OUTCOME_KEYS) delete m[k];
    const pi = al.allocate(m.sigma, null, 'Medium', m.rf_pct, null).pi;      // native equilibrium prior, decimal excess
    let trace = {};
    if (mode === 'jev') {
      const jv = m.jev;
      if (jv) {
        m.jev = { ...jv, offset: lam * jv.offset };
        trace = { view_present: true, offset_original: jv.offset, offset_scaled: m.jev.offset, confidence: jv.confidence, p: jv.p, choice: jv.choice };
      } else {
        trace = { view_present: false };
      }
    } else {
      const v = committeeViews(m);
      if (v) {
        const q = v.map((x, i) => (x - m.rf_pct) / 100);
        const qs = q.map((x, i) => pi[i] + lam * (x - pi[i]));
        const vs = qs.map(x => 100 * x + m.rf_pct);
        if (m.committee && !m.committee.problems.length) m.committee = { ...m.committee, cio: { ...m.committee.cio, spy_q: vs[0], tlt_q: vs[1] } };
        else m.saved = { ...m.saved, spy_q: vs[0], tlt_q: vs[1] };
        trace = { view_present: true, views_total_pct_original: v, views_total_pct_scaled: vs, q_original: q, q_scaled: qs };
      } else {
        trace = { view_present: false };
      }
    }
    const d = await bt.decide(m);
    // the native allocator's own intermediate quantities for this month, from the engine's exported functions
    if (mode === 'committee') {
      const v = trace.view_present ? (m.committee && !m.committee.problems.length ? [m.committee.cio.spy_q, m.committee.cio.tlt_q] : [m.saved.spy_q, m.saved.tlt_q]) : null;
      const a = al.allocate(m.sigma, v, d.conf, m.rf_pct, null);
      // the native fully-invested SPY weight before the clip, from the engine's own function with the bounds widened
      const xRaw = al.constrainedSpyWeight(a.er, m.sigma, -1e9, 1e9);
      trace = { ...trace, pi, er: a.er, unconstrained: a.unconstrained, x_raw: xRaw, target_spy: a.target_spy,
                lo: al.MIN_SPY, hi: al.MAX_SPY, conf_applied: d.conf, conf_reported: d.confRep, regime: m.regime };
      if (Math.abs(Math.min(al.MAX_SPY, Math.max(al.MIN_SPY, xRaw)) - a.target_spy) > 1e-12) throw new Error(`clip mismatch at ${m.as_of}`);
      if (Math.abs(a.target_spy - d.w) > 1e-12) throw new Error(`committee weight mismatch at ${m.as_of}: ${a.target_spy} vs ${d.w}`);
    } else {
      const c = d.detail?.calc ?? {};
      trace = { ...trace, pi, base_edge: c.baseEdge, weighted_offset: c.weightedOffset, edge: c.edge,
                x_raw: c.xRaw === undefined ? null : c.xRaw / 100, w: c.w === undefined ? null : c.w / 100,
                lo: c.lo / 100, hi: c.hi / 100, regime: m.regime };
    }
    rows.push({ as_of: m.as_of, w_spy: d.w, source: d.detail?.source ?? null, problems: d.detail?.problems ?? [], ...trace });
  }
  out[String(lam)] = rows;
}

await writeFile(args.out, JSON.stringify({
  engine: path.relative(process.cwd(), engineDir), mode, last_as_of: last, lambdas, n_months: months.length,
  bounds: { min_spy: al.MIN_SPY, max_spy: al.MAX_SPY }, equilibrium_spy: al.EQUILIBRIUM_SPY, delta: al.DELTA,
  outcome_fields_removed_before_decide: OUTCOME_KEYS, scenarios: out }, null, 1) + '\n');
console.log(`${mode}: ${months.length} months x ${lambdas.length} scenarios through ${last} -> ${args.out}`);
