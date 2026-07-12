"""Semi-synthetic diabetes comparative-effectiveness data-generating process.

A made-up but clinically-shaped study to exercise the causal machinery end to end.

Question (target-trial emulation):
    In adults with poorly-controlled type-2 diabetes initiating a *second-line*
    antihyperglycemic, does starting an **SGLT2 inhibitor** (A=1) vs a
    **sulfonylurea** (A=0) lead to greater HbA1c reduction at 12 months?
    Outcome Y = ΔHbA1c (month-12 minus baseline); more-negative is better.

Why semi-synthetic: we author the structural causal model, so the *true* ATE is
known by construction. We store both potential outcomes Y(0), Y(1) — used ONLY as
the answer key — and confirm the estimator stack recovers E[Y(1)-Y(0)] from the
confounded observational data. This validates the estimators, never a clinical claim.

Confounding by indication is deliberate: prescribers favour SGLT2 for patients with
higher BMI and renal/cardio risk and avoid it at very low eGFR, while sulfonylureas
go to older / longer-duration patients. Those same covariates drive the outcome, so
the naive contrast is biased and the adjustment must earn its keep.

The covariate distributions carry light El Salvador flavor (a CKDu-hotspot residence
indicator) so the same machinery slots onto the phase-1 SV-calibrated population.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Covariate (confounder) names, in the order the estimator matrix expects.
COVARIATES = [
    "age_z",          # standardized age
    "female",
    "baseline_hba1c", # %
    "egfr",           # mL/min/1.73m2
    "bmi",            # kg/m2
    "dm_duration",    # years
    "ckd",            # comorbid CKD flag
    "ckdu_region",    # resides in CKDu hotspot (SV flavor)
]


@dataclass
class DiabetesCohort:
    df: pd.DataFrame          # observed: covariates + a + y (+ raw covariate cols)
    true_ate: float           # E[Y(1)-Y(0)] over the sampled population (answer key)
    true_att: float           # E[Y(1)-Y(0) | A=1]
    tau_homogeneous: float    # the constant part of the effect
    seed: int

    @property
    def X(self) -> np.ndarray:
        return self.df[COVARIATES].to_numpy(float)

    @property
    def a(self) -> np.ndarray:
        return self.df["a"].to_numpy(int)

    @property
    def y(self) -> np.ndarray:
        return self.df["y"].to_numpy(float)


def generate(n: int = 6000, seed: int = 42,
             tau: float = -0.5, heterogeneous: bool = True,
             confounding: float = 1.0) -> DiabetesCohort:
    """Draw a confounded cohort with a known treatment effect.

    tau            base SGLT2-vs-SU effect on ΔHbA1c (negative = better control).
    heterogeneous  if True the effect is modified by baseline HbA1c and eGFR, so
                   the marginal ATE = mean over the sample of the CATE.
    confounding    multiplier on the treatment-assignment dependence on covariates
                   (0 = randomized trial; 1 = realistic confounding by indication).
    """
    rng = np.random.default_rng(seed)

    # --- Covariates L -------------------------------------------------------
    age = np.clip(rng.normal(58, 11, n), 30, 88)
    age_z = (age - 58) / 11
    female = rng.binomial(1, 0.52, n)
    baseline_hba1c = np.clip(rng.normal(8.6, 1.2, n), 6.5, 14.0)   # poorly controlled
    bmi = np.clip(rng.normal(30, 5, n), 18, 50)
    dm_duration = np.clip(rng.normal(8, 4, n), 0, 30)
    ckdu_region = rng.binomial(1, 0.25, n)
    # eGFR declines with age, duration, and CKDu-region exposure (Mesoamerican nephropathy flavor).
    egfr = np.clip(
        rng.normal(95, 18, n) - 6 * age_z - 1.1 * dm_duration - 8 * ckdu_region, 18, 140
    )
    ckd = (egfr < 60).astype(int)

    # --- Treatment assignment A (confounding by indication) -----------------
    # SGLT2 favoured for higher BMI and better-but-not-too-low renal function;
    # avoided at very low eGFR; sulfonylureas drift to older/longer-duration.
    logit_a = (
        0.10
        + confounding * (
            + 0.55 * (bmi - 30) / 5
            + 0.50 * (egfr - 90) / 18
            - 0.90 * (egfr < 45)
            - 0.35 * age_z
            - 0.25 * (dm_duration - 8) / 4
            + 0.30 * (baseline_hba1c - 8.6)
            - 0.20 * ckdu_region
        )
    )
    e_true = 1 / (1 + np.exp(-logit_a))
    a = rng.binomial(1, e_true)

    # --- Potential outcomes Y(0), Y(1): ΔHbA1c at 12 months ------------------
    # Prognostic (confounder) effect on ΔHbA1c, shared by both arms:
    #   higher baseline regresses down more; longer duration & low eGFR respond less.
    prognostic = (
        -0.85 * (baseline_hba1c - 8.6)     # regression to the mean / more room to fall
        + 0.10 * age_z
        + 0.06 * (dm_duration - 8) / 4
        - 0.04 * (egfr - 90) / 18
        + 0.15 * ckd
    )
    # Treatment effect (CATE): base tau, optionally modified.
    if heterogeneous:
        cate = tau - 0.20 * (baseline_hba1c - 8.6) + 0.012 * (egfr - 90)
    else:
        cate = np.full(n, tau)

    noise = rng.normal(0, 0.6, n)
    base_level = -0.4                       # both arms improve somewhat on intensification
    y0 = base_level + prognostic + 0.0 * 1 + noise
    y1 = base_level + prognostic + cate + noise
    y = np.where(a == 1, y1, y0)

    df = pd.DataFrame({
        "age": age, "age_z": age_z, "female": female,
        "baseline_hba1c": baseline_hba1c, "egfr": egfr, "bmi": bmi,
        "dm_duration": dm_duration, "ckd": ckd, "ckdu_region": ckdu_region,
        "e_true": e_true, "a": a, "y": y,
        # answer key — never fed to the estimators:
        "_y0": y0, "_y1": y1, "_cate": cate,
    })

    return DiabetesCohort(
        df=df,
        true_ate=float((y1 - y0).mean()),
        true_att=float((y1 - y0)[a == 1].mean()),
        tau_homogeneous=float(tau),
        seed=seed,
    )
