// Browser mirror of stochastic_views.decide_from_runs (Farnoosh Memari, docs/EMPIRICAL_UNCERTAINTY.md):
// aggregate N committee runs on identical input, measure run-to-run dispersion, and feed it into
// Black-Litterman's view uncertainty:  Omega = c(label)·tau·Sigma + diag(s²).
import { allocate, TAU } from './allocation.js?v=202610300036';

export const ORDER = ['Low', 'Medium', 'High'];          // ties in the modal label go to the lower one
const DOWN = { High: 'Medium', Medium: 'Low', Low: 'Low' };
export const gate = (label, regime) => (regime === 'elevated' ? DOWN[label] : label);

export function modalConfidence(labels) {
  const counts = Object.fromEntries(ORDER.map(c => [c, labels.filter(l => l === c).length]));
  const top = Math.max(...Object.values(counts));
  return { label: ORDER.find(c => counts[c] === top), counts };
}

const stats = a => {
  const n = a.length, mean = a.reduce((x, y) => x + y, 0) / n;
  const v = n >= 2 ? a.reduce((x, y) => x + (y - mean) ** 2, 0) / (n - 1) : null;
  return { mean, var: v, std: v === null ? null : Math.sqrt(v), min: Math.min(...a), max: Math.max(...a) };
};

// runs: [{ valid, spy_q, tlt_q, confidence }]; views in percent (total return)
export function aggregate(runs) {
  const ok = runs.filter(r => r.valid);
  if (!ok.length) return { n_valid: 0, n_runs: runs.length };
  const spy = stats(ok.map(r => r.spy_q)), tlt = stats(ok.map(r => r.tlt_q));
  const { label, counts } = modalConfidence(ok.map(r => r.confidence));
  return { n_valid: ok.length, n_runs: runs.length, spy, tlt, label, counts,
           empirical_var: ok.length >= 2 ? [spy.var / 1e4, tlt.var / 1e4] : null };   // %² -> decimal²
}

export function decide(sigma, runs, rfPct, mode, regime) {
  const agg = aggregate(runs);
  if (!agg.n_valid) return { agg, effective: 'prior_only', decision: allocate(sigma, null, 'Medium', rfPct, null), perRun: [] };
  let effective = mode, label = agg.label, ev = agg.empirical_var;
  if (mode === 'reported' || !ev) { effective = 'reported'; ev = null; }
  else if (mode === 'empirical') label = 'Medium';        // self-report ignored: neutral c = 1
  const used = gate(label, regime);
  const decision = allocate(sigma, [agg.spy.mean, agg.tlt.mean], used, rfPct, null, ev);
  const perRun = runs.filter(r => r.valid).map(r => allocate(sigma, [r.spy_q, r.tlt_q], gate(r.confidence, regime), rfPct, null).target_spy);
  const priorSd = [Math.sqrt(TAU * sigma[0][0]), Math.sqrt(TAU * sigma[1][1])];
  const dispersion = ev ? [agg.spy.std / 100 / priorSd[0], agg.tlt.std / 100 / priorSd[1]] : (agg.spy.std !== null ? [agg.spy.std / 100 / priorSd[0], agg.tlt.std / 100 / priorSd[1]] : null);
  return { agg, effective, label, used, ev, decision, perRun, dispersion, priorSd };
}
