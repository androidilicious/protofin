"""Offline diagnostic of server.py's allocation equations; no market/API calls.

Synthetic annual volatilities: SPY 18%, TLT 15%; correlation -0.2.
This constructs a boundary case, not an estimate of its real-world frequency.
Run: python research/allocation_sensitivity.py
Only the Python standard library is required.
"""

import json
import math


def scale(matrix, factor):
    return [[value * factor for value in row] for row in matrix]


def add(left, right):
    return [[left[i][j] + right[i][j] for j in range(2)] for i in range(2)]


def inverse(matrix):
    a, b = matrix[0]
    c, d = matrix[1]
    determinant = a * d - b * c
    if determinant == 0:
        raise ValueError("Singular matrix")
    return [[d / determinant, -b / determinant],
            [-c / determinant, a / determinant]]


def multiply_vector(matrix, vector):
    return [sum(a * b for a, b in zip(row, vector)) for row in matrix]


SIGMA = [[0.18 ** 2, -0.2 * 0.18 * 0.15],
         [-0.2 * 0.18 * 0.15, 0.15 ** 2]]
DELTA = 2.5
PRIOR = multiply_vector(scale(SIGMA, DELTA), [0.6, 0.4])


def evaluate(views, confidence_scale=1.0, tau=0.05):
    # server.py uses P = identity, so P multiplications disappear here.
    prior_precision = inverse(scale(SIGMA, tau))
    view_precision = inverse(scale(SIGMA, tau * confidence_scale))
    first = multiply_vector(prior_precision, PRIOR)
    second = multiply_vector(view_precision, views)
    posterior = multiply_vector(
        inverse(add(prior_precision, view_precision)),
        [a + b for a, b in zip(first, second)],
    )
    simplified = [(confidence_scale * p + q) / (confidence_scale + 1)
                  for p, q in zip(PRIOR, views)]
    assert all(math.isclose(a, b, abs_tol=1e-12)
               for a, b in zip(posterior, simplified))

    raw = multiply_vector(inverse(scale(SIGMA, DELTA)), posterior)
    clipped = [min(1.0, max(0.0, value)) for value in raw]
    total = sum(clipped)
    current_weights = [value / total for value in clipped] if total else None

    # Exact two-asset, fully invested, long-only mean-variance optimum:
    # maximize mu'w - DELTA/2 * w'SIGMA*w, subject to w=(x, 1-x).
    denominator = SIGMA[0][0] + SIGMA[1][1] - 2 * SIGMA[0][1]
    spy_weight = ((posterior[0] - posterior[1]) / DELTA
                  + SIGMA[1][1] - SIGMA[0][1]) / denominator
    spy_weight = min(1.0, max(0.0, spy_weight))

    return {
        "views_percent": [round(value * 100, 6) for value in views],
        "tau": tau,
        "raw_weights": raw,
        "current_weights_percent": ([round(value * 100, 6)
                                     for value in current_weights]
                                    if current_weights else None),
        "constrained_weights_percent": [round(spy_weight * 100, 6),
                                        round((1 - spy_weight) * 100, 6)],
        "zero_normalization_denominator": total == 0,
    }


def main():
    tau_cases = [evaluate([0.06, 0.04], tau=tau)
                 for tau in [0.0001, 0.05, 10.0]]
    assert all(case["current_weights_percent"] ==
               tau_cases[0]["current_weights_percent"] for case in tau_cases)

    # With Medium confidence, Q near -PRIOR leaves tiny posterior returns.
    boundary_cases = [
        evaluate([-PRIOR[0] + 0.0001, -PRIOR[1] - 0.0001]),
        evaluate([-PRIOR[0] - 0.0001, -PRIOR[1] + 0.0001]),
    ]
    assert boundary_cases[0]["current_weights_percent"] == [100.0, 0.0]
    assert boundary_cases[1]["current_weights_percent"] == [0.0, 100.0]
    invalid_case = evaluate([-0.10, -0.10])
    assert invalid_case["zero_normalization_denominator"]
    print(json.dumps({
        "scope": "Synthetic diagnostic, not a live pipeline run or backtest",
        "covariance": SIGMA,
        "prior_percent": [round(value * 100, 6) for value in PRIOR],
        "tau_invariance": tau_cases,
        "boundary_sensitivity": boundary_cases,
        "zero_denominator": invalid_case,
    }, indent=2))


if __name__ == "__main__":
    main()
