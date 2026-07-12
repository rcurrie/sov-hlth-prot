"""The headline answer-key test: inject an ATE, recover it *through OMOP*."""
import pytest

from shp.study.diabetes import cohort as cohort_mod
from shp.study.diabetes import dgp as dgp_mod
from shp.study.diabetes import run as study
from shp.study.diabetes import to_omop


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    db = tmp_path_factory.mktemp("omop") / "diabetes.duckdb"
    return study.run(n=6000, seed=42, db_path=db, do_omop=True)


def test_omop_roundtrip_preserves_rows(tmp_path):
    """The frame rebuilt from OMOP SQL matches the generated cohort size & outcome."""
    cohort = dgp_mod.generate(n=2000, seed=11)
    db = to_omop.load(cohort, db_path=tmp_path / "rt.duckdb")
    frame = cohort_mod.build_analytic_frame(db)
    assert len(frame) == 2000
    # Outcome reconstructed from (followup − baseline) HbA1c matches the DGP's y.
    merged = frame.sort_values("person_id").reset_index(drop=True)
    orig = cohort.df.reset_index(drop=True)
    assert (merged["y"] - orig["y"]).abs().max() < 1e-6
    assert (merged["a"].to_numpy() == orig["a"].to_numpy()).mean() == 1.0


def test_doubly_robust_estimators_cover_truth(report):
    for method in ("AIPW", "TMLE"):
        r = report.by_method(method)
        assert r.covers(report.true_ate), f"{r} misses truth {report.true_ate:.3f}"


def test_naive_is_biased_through_omop(report):
    naive = report.by_method("naive")
    assert abs(naive.estimate - report.true_ate) > 0.1


def test_iptw_improves_balance(report):
    assert max(report.smd_weighted.values()) < max(report.smd_unadjusted.values())


def test_unmeasured_confounding_shifts_estimate(report):
    """Dropping the strongest confounder (eGFR) should move AIPW off the truth."""
    full = report.by_method("AIPW").estimate
    dropped = report.unmeasured["aipw_estimate"]
    assert abs(dropped - report.true_ate) > abs(full - report.true_ate) - 0.05
