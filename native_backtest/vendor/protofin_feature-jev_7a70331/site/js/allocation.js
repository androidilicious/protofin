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

export function blPosterior(pi, sigma, qExcess, confidence = 'Medium', tau = TAU) {
  const omegaInv = inv2(scale(sigma, OMEGA_SCALE[confidence] * tau));
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
export function allocate(sigma, viewsTotalPct, confidence, rfPct, previousSpy = null) {
  const pi = equilibriumPrior(sigma);
  let er;
  if (viewsTotalPct) {
    const q = viewsTotalPct.map(v => (v - rfPct) / 100);
    er = blPosterior(pi, sigma, q, confidence);
  } else er = [...pi];
  const target = constrainedSpyWeight(er, sigma);
  const [final, status] = applyTradePolicy(target, previousSpy);
  return { pi, er, unconstrained: unconstrainedWeights(er, sigma), target_spy: target, final_spy: final, status };
}
