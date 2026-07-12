"""Estimator unit tests on a controlled DGP (no OMOP, fast)."""
import numpy as np
import pytest

from shp.estimators import (
    aipw_ate, fit_propensity, iptw_ate, naive_ate, positivity, tmle_ate,
)
from shp.study.diabetes import dgp as dgp_mod


@pytest.fixture(scope="module")
def cohort():
    return dgp_mod.generate(n=8000, seed=7)


def test_naive_is_biased(cohort):
    """Confounding by indication makes the crude contrast miss the truth."""
    res = naive_ate(cohort.y, cohort.a)
    assert abs(res.estimate - cohort.true_ate) > 0.1


def test_iptw_recovers(cohort):
    e = fit_propensity(cohort.X, cohort.a)
    res = iptw_ate(cohort.y, cohort.a, e)
    assert res.covers(cohort.true_ate), f"{res} vs truth {cohort.true_ate:.3f}"


def test_aipw_recovers(cohort):
    res = aipw_ate(cohort.X, cohort.a, cohort.y, seed=7)
    assert res.covers(cohort.true_ate), f"{res} vs truth {cohort.true_ate:.3f}"
    assert abs(res.estimate - cohort.true_ate) < 0.1


def test_tmle_recovers(cohort):
    res = tmle_ate(cohort.X, cohort.a, cohort.y, seed=7)
    assert res.covers(cohort.true_ate), f"{res} vs truth {cohort.true_ate:.3f}"
    assert abs(res.estimate - cohort.true_ate) < 0.1


def test_doubly_robust_beat_naive(cohort):
    naive = naive_ate(cohort.y, cohort.a)
    aipw = aipw_ate(cohort.X, cohort.a, cohort.y, seed=7)
    assert abs(aipw.estimate - cohort.true_ate) < abs(naive.estimate - cohort.true_ate)


def test_randomized_has_no_confounding():
    """confounding=0 ⇒ naive ≈ truth (sanity check on the DGP)."""
    c = dgp_mod.generate(n=8000, seed=3, confounding=0.0)
    res = naive_ate(c.y, c.a)
    assert res.covers(c.true_ate)


def test_positivity_report(cohort):
    e = fit_propensity(cohort.X, cohort.a)
    rep = positivity(e)
    assert 0.0 <= rep.min_e <= rep.max_e <= 1.0
