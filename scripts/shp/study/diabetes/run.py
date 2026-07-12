"""End-to-end semi-synthetic study: inject a known ATE, recover it from OMOP.

    DGP (known truth) → write OMOP CDM → rebuild analytic frame from OMOP SQL
        → estimator chain (naive → IPTW → AIPW → TMLE) → confirm recovery
        → stress tests (positivity, unmeasured confounding).

The pass/fail criterion is the "answer-key unit test": the doubly-robust estimators'
95% CIs must cover the true ATE, and they must beat the naive contrast's bias.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ... import config
from ...estimators import (
    ATEResult, aipw_ate, fit_propensity, iptw_ate, naive_ate, positivity,
    standardized_mean_differences, tmle_ate,
)
from . import cohort as cohort_mod
from . import dgp as dgp_mod
from . import to_omop


@dataclass
class StudyReport:
    true_ate: float
    true_att: float
    results: list[ATEResult]
    positivity: object
    smd_unadjusted: dict
    smd_weighted: dict
    unmeasured: dict = field(default_factory=dict)
    db_path: str = ""

    def by_method(self, name: str) -> ATEResult:
        return next(r for r in self.results if r.method == name)


def run(n: int = 6000, seed: int = 42, db_path=None, do_omop: bool = True,
        stress_unmeasured: bool = True) -> StudyReport:
    cohort = dgp_mod.generate(n=n, seed=seed)

    if do_omop:
        db_path = to_omop.load(cohort, db_path=db_path)
        frame = cohort_mod.build_analytic_frame(db_path)
    else:
        frame = cohort.df
        db_path = ""

    X = frame[dgp_mod.COVARIATES].to_numpy(float)
    a = frame["a"].to_numpy(int)
    y = frame["y"].to_numpy(float)

    e = fit_propensity(X, a)
    p = a.mean()
    w = (a * p / e) + ((1 - a) * (1 - p) / (1 - e))

    results = [
        naive_ate(y, a),
        iptw_ate(y, a, e),
        aipw_ate(X, a, y, seed=seed),
        tmle_ate(X, a, y, seed=seed),
    ]

    report = StudyReport(
        true_ate=cohort.true_ate,
        true_att=cohort.true_att,
        results=results,
        positivity=positivity(e),
        smd_unadjusted=standardized_mean_differences(X, a, dgp_mod.COVARIATES),
        smd_weighted=standardized_mean_differences(X, a, dgp_mod.COVARIATES, weights=w),
        db_path=db_path,
    )

    if stress_unmeasured:
        report.unmeasured = _unmeasured_confounding_stress(frame, seed)

    return report


def _unmeasured_confounding_stress(frame, seed: int) -> dict:
    """Drop the strongest confounder (eGFR) from the adjustment set and re-estimate.
    A faithful estimator should now be biased — demonstrating it is the *measured*
    covariates doing the work, not magic. This is the 'unmeasured confounding' probe."""
    reduced = [c for c in dgp_mod.COVARIATES if c != "egfr"]
    X = frame[reduced].to_numpy(float)
    a = frame["a"].to_numpy(int)
    y = frame["y"].to_numpy(float)
    res = aipw_ate(X, a, y, seed=seed)
    return {"dropped": "egfr", "aipw_estimate": res.estimate,
            "ci_low": res.ci_low, "ci_high": res.ci_high}


def format_report(report: StudyReport) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("Semi-synthetic diabetes CER — SGLT2 vs sulfonylurea, ΔHbA1c @12m")
    lines.append("=" * 70)
    lines.append(f"TRUE ATE (answer key) : {report.true_ate:+.3f} %HbA1c   "
                 f"(ATT {report.true_att:+.3f})")
    if report.db_path:
        lines.append(f"OMOP round-trip       : {report.db_path}")
    lines.append("-" * 70)
    for r in report.results:
        cover = "✓" if r.covers(report.true_ate) else "✗"
        bias = r.estimate - report.true_ate
        lines.append(f"  {cover} {r}  bias={bias:+.3f}")
    lines.append("-" * 70)
    lines.append(f"  {report.positivity}")
    worst_un = max(report.smd_unadjusted.values())
    worst_w = max(report.smd_weighted.values())
    lines.append(f"  balance: worst |SMD| unadjusted={worst_un:.2f} → IPTW-weighted={worst_w:.2f}")
    if report.unmeasured:
        u = report.unmeasured
        lines.append(f"  unmeasured-confounding probe (drop {u['dropped']}): "
                     f"AIPW={u['aipw_estimate']:+.3f} "
                     f"[{u['ci_low']:+.3f},{u['ci_high']:+.3f}]  ← expected to drift off truth")
    lines.append("=" * 70)
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    config.ensure_dirs()
    print(format_report(run()))
