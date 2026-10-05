// Port of allocation.py: the same Black-Litterman blend, constrained optimizer and trade policy.
// Two assets only, so every matrix step is a closed-form 2x2 operation.
export const EQUILIBRIUM_SPY = 0.60;
export const MIN_SPY = 0.40, MAX_SPY = 0.80;
export const NO_TRADE_BAND = 0.02, MAX_MOVE = 0.10;
export const DELTA = 2.5, TAU = 0.05;
export const OMEGA_SCALE = { High: 0.5, Medium: 1.0, Low: 2.0 };

const inv2 = m => {
  const [[a, b], [c, d]] = m, det = a * d - b * c;
  if (det === 0) throw new Error('singular matrix');
  return [[d / det, -b / det], [-c / det, a / det]];
};
const mulv = (m, v) => [m[0][0] * v[0] + m[0][1] * v[1], m[1][0] * v[0] + m[1][1] * v[1]];
const scale = (m, k) => m.map(r => r.map(x => x * k));
const add = (m, n) => m.map((r, i) => r.map((x, j) => x + n[i][j]));

export function equilibriumPrior(sigma, wEq = [EQUILIBRIUM_SPY, 1 - EQUILIBRIUM_SPY]) {
  return mulv(scale(sigma, DELTA), wEq);
}

// View uncertainty: Omega = c(confidence)·tau·Sigma (+ diag(s²) when run-to-run variances are given).
// Mirrors allocation.view_omega; empiricalVar is [s²_spy, s²_tlt] in decimal² of annual return.
export function viewOmega(sigma, confidence = 'Medium', tau = TAU, empiricalVar = null) {
  const om = scale(sigma, OMEGA_SCALE[confidence] * tau);
  if (empiricalVar) {
    if (empiricalVar.length !== 2 || empiricalVar.some(v => !Number.isFinite(v) || v < 0)) throw new Error('empiricalVar must be 2 finite non-negative variances');
    om[0][0] += empiricalVar[0]; om[1][1] += empiricalVar[1];
  }
  return om;
}

export function blPosterior(pi, sigma, qExcess, confidence = 'Medium', tau = TAU, empiricalVar = null) {
  const omegaInv = inv2(viewOmega(sigma, confidence, tau, empiricalVar));
  const tauSigmaInv = inv2(scale(sigma, tau));
  const lhs = inv2(add(tauSigmaInv, omegaInv));
  const rhs = [mulv(tauSigmaInv, pi)[0] + mulv(omegaInv, qExcess)[0], mulv(tauSigmaInv, pi)[1] + mulv(omegaInv, qExcess)[1]];
  return mulv(lhs, rhs);
}

export function unconstrainedWeights(mu, sigma) {
  return mulv(inv2(scale(sigma, DELTA)), mu);
}

export function constrainedSpyWeight(mu, sigma, lo = MIN_SPY, hi = MAX_SPY) {
  const s00 = sigma[0][0], s01 = sigma[0][1], s11 = sigma[1][1];
  const x = ((mu[0] - mu[1]) / DELTA + s11 - s01) / (s00 + s11 - 2 * s01);
  return Math.min(hi, Math.max(lo, x));
}

export function applyTradePolicy(targetSpy, previousSpy, band = NO_TRADE_BAND, maxMove = MAX_MOVE) {
  if (previousSpy === null || previousSpy === undefined) return [targetSpy, 'initial allocation'];
  const diff = targetSpy - previousSpy;
  if (Math.abs(diff) <= band) return [previousSpy, `held: target within ${(band * 100).toFixed(0)}pp no-trade band`];
  const move = Math.sign(diff) * Math.min(Math.abs(diff), maxMove);
  const capped = Math.abs(diff) > maxMove;
  const status = `moved ${(move * 100 >= 0 ? '+' : '')}${(move * 100).toFixed(1)}pp` + (capped ? ` (capped at ${(maxMove * 100).toFixed(0)}pp)` : '');
  return [previousSpy + move, status];
}

// views: [spyTotalPct, tltTotalPct] or null; returns every intermediate quantity like allocation.allocate
export function allocate(sigma, viewsTotalPct, confidence, rfPct, previousSpy = null, empiricalVar = null) {
  const pi = equilibriumPrior(sigma);
  let er, omega = null;
  if (viewsTotalPct) {
    const q = viewsTotalPct.map(v => (v - rfPct) / 100);
    omega = viewOmega(sigma, confidence, TAU, empiricalVar);
    er = blPosterior(pi, sigma, q, confidence, TAU, empiricalVar);
  } else er = [...pi];
  const target = constrainedSpyWeight(er, sigma);
  const [final, status] = applyTradePolicy(target, previousSpy);
  return { pi, er, unconstrained: unconstrainedWeights(er, sigma), target_spy: target, final_spy: final, status, omega };
}
