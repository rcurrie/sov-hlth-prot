"""Average-treatment-effect estimators: naive → IPTW → AIPW → TMLE.

This is the OHDSI-style causal chain the napkin plan calls for, implemented so the
semi-synthetic answer-key test can confirm recovery of an *injected* ATE:

    naive    — crude difference in means; biased under confounding (the baseline)
    IPTW     — stabilized Hájek inverse-probability weighting
    AIPW     — augmented IPW, doubly robust, cross-fitted (Super-Learner-lite)
    TMLE     — targeted maximum likelihood, doubly robust, cross-fitted nuisance
               + logistic fluctuation targeting step

Doubly robust means: consistent if EITHER the propensity model OR the outcome model
is correct. We cross-fit nuisance functions (sample-splitting) so the estimators
attain root-n inference without Donsker conditions — the modern (Chernozhukov et al.)
recipe. Outcomes here are continuous (Δ HbA1c); estimators scale to [0,1] for the
TMLE fluctuation and rescale back.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold

EPS_CLIP = 0.025          # propensity trimming bound (positivity guard)
Q_CLIP = 1e-4             # outcome-on-[0,1] clip for logit stability


@dataclass
class ATEResult:
    method: str
    estimate: float
    se: float
    ci_low: float
    ci_high: float
    extra: dict | None = None

    def covers(self, truth: float) -> bool:
        return self.ci_low <= truth <= self.ci_high

    def __str__(self) -> str:
        return (f"{self.method:<6} ATE={self.estimate:+.3f}  "
                f"95% CI [{self.ci_low:+.3f}, {self.ci_high:+.3f}]  (SE {self.se:.3f})")


def _ci(estimate: float, se: float) -> tuple[float, float]:
    return estimate - 1.96 * se, estimate + 1.96 * se


# --------------------------------------------------------------------------- #
# Naive
# --------------------------------------------------------------------------- #
def naive_ate(y: np.ndarray, a: np.ndarray) -> ATEResult:
    y1, y0 = y[a == 1], y[a == 0]
    est = y1.mean() - y0.mean()
    se = np.sqrt(y1.var(ddof=1) / len(y1) + y0.var(ddof=1) / len(y0))
    lo, hi = _ci(est, se)
    return ATEResult("naive", est, se, lo, hi)


# --------------------------------------------------------------------------- #
# Propensity
# --------------------------------------------------------------------------- #
def fit_propensity(X: np.ndarray, a: np.ndarray, clip: float = EPS_CLIP) -> np.ndarray:
    """In-sample propensity (used for IPTW + diagnostics). Cross-fit variants live
    in the AIPW/TMLE routines."""
    model = LogisticRegression(max_iter=1000, C=1e6)
    model.fit(X, a)
    e = model.predict_proba(X)[:, 1]
    return np.clip(e, clip, 1 - clip)


def _crossfit_propensity(X, a, folds, clip=EPS_CLIP, seed=0):
    e = np.zeros(len(a))
    kf = KFold(n_splits=folds, shuffle=True, random_state=seed)
    for tr, te in kf.split(X):
        m = LogisticRegression(max_iter=1000, C=1e6).fit(X[tr], a[tr])
        e[te] = m.predict_proba(X[te])[:, 1]
    return np.clip(e, clip, 1 - clip)


def _crossfit_outcome(X, a, y, folds, seed=0, learner=None):
    """Cross-fit mu(X,A); return held-out predictions mu1, mu0 (A forced to 1/0)."""
    n = len(y)
    mu1 = np.zeros(n)
    mu0 = np.zeros(n)
    Xa = np.column_stack([X, a])
    kf = KFold(n_splits=folds, shuffle=True, random_state=seed)
    for tr, te in kf.split(X):
        model = (learner() if learner else
                 GradientBoostingRegressor(n_estimators=200, max_depth=3,
                                           learning_rate=0.05, subsample=0.9,
                                           random_state=seed))
        model.fit(Xa[tr], y[tr])
        X1 = np.column_stack([X[te], np.ones(len(te))])
        X0 = np.column_stack([X[te], np.zeros(len(te))])
        mu1[te] = model.predict(X1)
        mu0[te] = model.predict(X0)
    return mu1, mu0


# --------------------------------------------------------------------------- #
# IPTW (stabilized Hájek)
# --------------------------------------------------------------------------- #
def iptw_ate(y: np.ndarray, a: np.ndarray, e: np.ndarray) -> ATEResult:
    p = a.mean()
    w = np.where(a == 1, p / e, (1 - p) / (1 - e))   # stabilized weights
    # Hájek (self-normalized) means
    sw1 = (w * a).sum()
    sw0 = (w * (1 - a)).sum()
    m1 = (w * a * y).sum() / sw1
    m0 = (w * (1 - a) * y).sum() / sw0
    est = m1 - m0
    # IC-based SE for the Hájek difference
    n = len(y)
    ic = (w * a * (y - m1)) / (sw1 / n) - (w * (1 - a) * (y - m0)) / (sw0 / n)
    se = ic.std(ddof=1) / np.sqrt(n)
    lo, hi = _ci(est, se)
    return ATEResult("IPTW", est, se, lo, hi,
                     extra={"max_weight": float(w.max()), "ess": float(w.sum() ** 2 / (w ** 2).sum())})


# --------------------------------------------------------------------------- #
# AIPW (cross-fitted, doubly robust)
# --------------------------------------------------------------------------- #
def aipw_ate(X, a, y, folds: int = 5, seed: int = 0, learner=None) -> ATEResult:
    X = np.asarray(X, float)
    a = np.asarray(a, float)
    y = np.asarray(y, float)
    e = _crossfit_propensity(X, a, folds, seed=seed)
    mu1, mu0 = _crossfit_outcome(X, a, y, folds, seed=seed, learner=learner)
    psi = (mu1 - mu0) + a * (y - mu1) / e - (1 - a) * (y - mu0) / (1 - e)
    est = psi.mean()
    se = psi.std(ddof=1) / np.sqrt(len(y))
    lo, hi = _ci(est, se)
    return ATEResult("AIPW", est, se, lo, hi)


# --------------------------------------------------------------------------- #
# TMLE (cross-fitted nuisance + logistic-fluctuation targeting)
# --------------------------------------------------------------------------- #
def _logit(p):
    p = np.clip(p, Q_CLIP, 1 - Q_CLIP)
    return np.log(p / (1 - p))


def _expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def _fit_epsilon(ys, off, H, iters: int = 100, tol: float = 1e-8) -> float:
    """1-D Newton for the fluctuation parameter ε in a quasi-binomial model with
    fixed offset: E[Ys] = expit(off + ε·H). Solves the score equation Σ H(Ys−p)=0."""
    eps = 0.0
    for _ in range(iters):
        p = _expit(off + eps * H)
        grad = np.sum(H * (ys - p))
        hess = -np.sum(H * H * p * (1 - p))
        if abs(hess) < 1e-12:
            break
        step = grad / hess
        eps -= step
        if abs(step) < tol:
            break
    return float(eps)


def tmle_ate(X, a, y, folds: int = 5, seed: int = 0, learner=None) -> ATEResult:
    X = np.asarray(X, float)
    a = np.asarray(a, float)
    y = np.asarray(y, float)
    n = len(y)

    e = _crossfit_propensity(X, a, folds, seed=seed)
    mu1, mu0 = _crossfit_outcome(X, a, y, folds, seed=seed, learner=learner)

    # Scale outcome to [0,1] for the logistic fluctuation.
    ymin, ymax = y.min(), y.max()
    span = max(ymax - ymin, 1e-9)
    ys = (y - ymin) / span
    Q1 = np.clip((mu1 - ymin) / span, Q_CLIP, 1 - Q_CLIP)
    Q0 = np.clip((mu0 - ymin) / span, Q_CLIP, 1 - Q_CLIP)
    Qa = np.where(a == 1, Q1, Q0)

    # Clever covariate and targeting step.
    H = a / e - (1 - a) / (1 - e)
    eps = _fit_epsilon(ys, _logit(Qa), H)

    H1 = 1.0 / e
    H0 = -1.0 / (1 - e)
    Q1s = _expit(_logit(Q1) + eps * H1)
    Q0s = _expit(_logit(Q0) + eps * H0)
    Qas = _expit(_logit(Qa) + eps * H)

    psi_scaled = (Q1s - Q0s).mean()
    est = psi_scaled * span

    # Influence-curve SE (rescaled).
    ic = (H * (ys - Qas) + (Q1s - Q0s) - psi_scaled) * span
    se = ic.std(ddof=1) / np.sqrt(n)
    lo, hi = _ci(est, se)
    return ATEResult("TMLE", est, se, lo, hi, extra={"epsilon": eps})


# --------------------------------------------------------------------------- #
# Convenience: run the whole chain.
# --------------------------------------------------------------------------- #
def run_chain(X, a, y, folds: int = 5, seed: int = 0) -> list[ATEResult]:
    X = np.asarray(X, float)
    a = np.asarray(a, int)
    y = np.asarray(y, float)
    e = fit_propensity(X, a)
    return [
        naive_ate(y, a),
        iptw_ate(y, a, e),
        aipw_ate(X, a, y, folds=folds, seed=seed),
        tmle_ate(X, a, y, folds=folds, seed=seed),
    ]
