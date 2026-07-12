"""Design diagnostics: positivity/overlap and covariate balance.

These gate the *credibility* of any ATE estimate. The napkin plan asks us to
"stress positivity & unmeasured confounding" — these functions provide the
positivity read; the unmeasured-confounding stress test lives in the study harness
(drop a true confounder, watch the estimate move).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PositivityReport:
    min_e: float
    max_e: float
    frac_below: float        # share of propensity scores below the trimming bound
    frac_above: float
    n_extreme: int
    overlap_ok: bool

    def __str__(self) -> str:
        flag = "OK" if self.overlap_ok else "VIOLATION"
        return (f"positivity[{flag}] e∈[{self.min_e:.3f},{self.max_e:.3f}] "
                f"extreme={self.n_extreme} ({self.frac_below + self.frac_above:.1%})")


def positivity(e: np.ndarray, bound: float = 0.05) -> PositivityReport:
    below = e < bound
    above = e > (1 - bound)
    n_ext = int(below.sum() + above.sum())
    return PositivityReport(
        min_e=float(e.min()), max_e=float(e.max()),
        frac_below=float(below.mean()), frac_above=float(above.mean()),
        n_extreme=n_ext, overlap_ok=(n_ext / len(e) < 0.05),
    )


def standardized_mean_differences(X: np.ndarray, a: np.ndarray,
                                  names: list[str] | None = None,
                                  weights: np.ndarray | None = None) -> dict[str, float]:
    """Absolute SMD per covariate, optionally on a weighted (pseudo-)population.
    |SMD| < 0.1 is the conventional balance threshold."""
    X = np.asarray(X, float)
    a = np.asarray(a, int)
    t, c = a == 1, a == 0
    if weights is None:
        w = np.ones(len(a))
    else:
        w = np.asarray(weights, float)

    def wmean(col, mask):
        return np.average(col[mask], weights=w[mask])

    def wvar(col, mask):
        m = wmean(col, mask)
        return np.average((col[mask] - m) ** 2, weights=w[mask])

    out = {}
    p = X.shape[1]
    names = names or [f"x{i}" for i in range(p)]
    for i in range(p):
        col = X[:, i]
        mt, mc = wmean(col, t), wmean(col, c)
        pooled = np.sqrt((wvar(col, t) + wvar(col, c)) / 2)
        out[names[i]] = float(abs(mt - mc) / pooled) if pooled > 0 else 0.0
    return out
