// Runs the NATIVE AP2 replay engine (site/js/livebacktest.js) unchanged, from the vendored copies.
// Two jobs:
//   decisions:  call LiveBacktest.decide() for every saved month with outcome fields REMOVED from the
//               month objects (proves the decision never reads realised returns). Writes weights only.
//   native-dev: run LiveBacktest.step() (native execution assumptions: same-close trade, native
//               5 bp per unit of SPY turnover, native returns and cash) over months whose decision
//               date is on or before --last-as-of, and write the per-month log and native summary.
// The only shim is a fetch() for file: URLs so the engine's own loadMonths() can read the vendored
// JSON files; no engine code is modified.
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, ...v] = a.replace(/^--/, '').split('='); return [k, v.join('=')]; }));
const engineDir = path.resolve(args.engine);           // .../site/js
const job = args.job;                                   // decisions | native-dev
const mode = args.mode;                                 // committee | jev
const out = args.out;

globalThis.fetch = async (url) => {
  const u = url instanceof URL ? url : new URL(String(url));
  if (u.protocol !== 'file:') throw new Error(`network fetch blocked in harness: ${u}`);
  try {
    const text = await readFile(fileURLToPath(u), 'utf8');
    return { ok: true, status: 200, json: async () => JSON.parse(text) };
  } catch (e) {
    return { ok: false, status: 404, json: async () => null };
  }
};

const lb = await import(pathToFileURL(path.join(engineDir, 'livebacktest.js')).href);
const months = await lb.loadMonths();
const engineMode = mode === 'jev' ? 'jev' : 'saved';    // in the engine, any non-'jev' mode decides with the saved committee

if (job === 'decisions') {
  const OUTCOME_KEYS = ['r_spy', 'r_tlt', 'next'];
  const bt = new lb.LiveBacktest(months, { mode: engineMode, delayMs: 0 });
  const rows = [];
  for (const m0 of months) {
    const m = { ...m0 };
    for (const k of OUTCOME_KEYS) delete m[k];
    const d = await bt.decide(m);
    rows.push({ as_of: m.as_of, w_spy: d.w, conf_applied: d.conf, conf_reported: d.confRep, views: d.views,
                regime: m.regime, source: d.detail?.source ?? null, problems: d.detail?.problems ?? [] });
  }
  await writeFile(out, JSON.stringify({ engine: engineDir, mode, n: rows.length, rows }, null, 1));
  console.log(`decisions: ${rows.length} months -> ${out}`);
} else if (job === 'native-dev') {
  const last = args['last-as-of'];
  const sel = months.filter(m => m.as_of <= last);
  const bt = new lb.LiveBacktest(sel, { mode: engineMode, delayMs: 0 });
  while (bt.i < sel.length) await bt.step();
  const log = bt.log.map((r, i) => ({ as_of: r.as_of, w: r.w, ret_live: bt.hist.rlive[i], nav_live: bt.hist.live[i], rf_month: bt.hist.rf[i] }));
  await writeFile(out, JSON.stringify({ engine: engineDir, mode, last_as_of: last, n: sel.length, summary: bt.summary(), log }, null, 1));
  console.log(`native-dev: ${sel.length} months through ${last} -> ${out}`);
} else {
  throw new Error(`unknown job ${job}`);
}
