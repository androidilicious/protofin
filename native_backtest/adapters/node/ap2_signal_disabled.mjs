// Runs the NATIVE JEV engine (site/js/livebacktest.js, unchanged) twice over the development months:
//   on:  Jev's saved answers exactly as recorded;
//   off: the same answers with the tilt switched off (offset 0), so the engine's own JEV branch decides with
//        no signal: edge = equilibrium edge + confidence x 0.
// It also records the engine's own two no-view benchmarks, "fixed" (60/40) and "prior" (Black-Litterman with no
// views). Native execution throughout: trade at the decision close, 5 bp per unit of one-way SPY turnover, weights
// drift between monthly rebalances, native returns and cash. Months after --last-as-of (the protected window) are
// never stepped. The only shim is a fetch() for file: URLs; no engine code is modified.
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, ...v] = a.replace(/^--/, '').split('='); return [k, v.join('=')]; }));
const engineDir = path.resolve(args.engine);
const last = args['last-as-of'];
if (!last) throw new Error('--last-as-of is required (the last development decision date)');

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

async function run(disableSignal) {
  const months = (await lb.loadMonths()).filter(m => m.as_of <= last);
  if (disableSignal) for (const m of months) { if (m.jev) m.jev = { ...m.jev, offset: 0 }; }
  const bt = new lb.LiveBacktest(months, { mode: 'jev', delayMs: 0 });
  while (bt.i < months.length) await bt.step();
  return bt;
}

const on = await run(false);
const off = await run(true);
const rows = on.log.map((r, i) => {
  if (off.log[i].as_of !== r.as_of) throw new Error(`month mismatch at ${i}`);
  return {
    as_of: r.as_of, next: r.next,
    w_on: r.w, w_off: off.log[i].w, w_prior_pct: on.hist.wprior[i],
    nav_on: on.hist.live[i], nav_off: off.hist.live[i], nav_fixed: on.hist.fixed[i], nav_prior: on.hist.prior[i],
    gross_on: on.hist.rlive[i], gross_off: off.hist.rlive[i], gross_fixed: on.hist.rfixed[i], rf_month: on.hist.rf[i],
  };
});
await writeFile(args.out, JSON.stringify({ engine: path.relative(process.cwd(), engineDir), last_as_of: last, n: rows.length,
  cost_bps_per_unit_one_way_spy_turnover: on.opts.costBps, summary: { on: on.summary().live, off: off.summary().live, fixed: on.summary().fixed }, rows }, null, 1) + '\n');
console.log(`signal on/off: ${rows.length} months through ${last} -> ${args.out}`);
