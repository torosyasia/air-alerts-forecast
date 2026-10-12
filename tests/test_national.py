"""All-Ukraine extension: same target as the studied cities, and no leakage in the shared model.
Real data only (DECISIONS D-01). The model tests need data/processed/national_*.csv from run_all.py."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from airalerts.build import prepare, stitch
from airalerts.config import ALL_CITIES, CITIES, PROCESSED


@pytest.fixture(scope="module")
def national():
    records, daily, _ = stitch(prepare(ALL_CITIES), ALL_CITIES)
    return records, daily


def test_studied_cities_have_the_same_target(built, national):
    deep, _, _ = built
    _, daily = national
    m = deep.merge(daily, on=["city", "date"], suffixes=("_d", "_n"))
    assert set(m.city) == set(CITIES)
    assert len(m) == len(deep)
    assert np.allclose(m.hours_d.fillna(-1), m.hours_n.fillna(-1))


def test_outage_days_are_missing_for_every_official_city(national):
    _, daily = national
    gap = [date(2026, 8, 29) + pd.Timedelta(days=i) for i in range(5)]
    for key, c in ALL_CITIES.items():
        d = daily[(daily.city == key) & daily.date.isin(gap)]
        if c.kyiv_kmda:
            assert d.hours.notna().all()
        else:
            assert d.missing.all() and d.hours.isna().all(), key


def _features():
    path = PROCESSED / "national_features.csv"
    if not path.exists():
        pytest.skip("run `python run_all.py` first (needs data/processed/national_features.csv)")
    X = pd.read_csv(path)
    X["date"] = pd.to_datetime(X.date).dt.date
    return X


def test_studied_cities_have_the_same_features():
    X = _features()
    F = pd.read_csv(PROCESSED / "features.csv")
    F["date"] = pd.to_datetime(F.date).dt.date
    m = F.merge(X, on=["city", "date"], suffixes=("_a", "_b"))
    assert len(m) == len(F)
    for c in [c for c in F.columns if c not in ("city", "date")]:
        assert np.allclose(m[c + "_a"].fillna(-1), m[c + "_b"].fillna(-1)), c


@pytest.mark.parametrize("shared", [True, False])
def test_shared_model_forecast_ignores_the_future(shared):
    """Forecasts for day D (all cities) do not change when every target from D on and every
    feature after D is replaced - for the shared model and the per-city models."""
    from airalerts.national import load_national
    from airalerts.national_models import COLS, rolling
    X = _features()
    _, daily = load_national()
    D = sorted(X.date.unique())[-5]
    cities = None if shared else ["kyiv", "odesa"]
    base = rolling(X, daily, [D], shared=shared, name="m", cities=cities)
    rng = np.random.default_rng(1)
    X2 = X.copy()
    fut = X2.date >= D
    X2.loc[fut, "y"] = rng.uniform(0, 24, fut.sum())
    later = X2.date > D
    X2.loc[later, COLS] = rng.uniform(0, 5, (later.sum(), len(COLS)))
    alt = rolling(X2, daily, [D], shared=shared, name="m", cities=cities)
    cols = ["city", "q10", "q50", "q90"]
    pd.testing.assert_frame_equal(base[cols].reset_index(drop=True), alt[cols].reset_index(drop=True))


def test_main_model_is_chosen_on_validation_only():
    from airalerts.national_models import select_main
    path = PROCESSED.parent.parent / "results" / "national_metrics.csv"
    if not path.exists():
        pytest.skip("run `python run_all.py` first")
    m = pd.read_csv(path)
    m2 = m.copy()
    t = m2.period == "test"
    m2.loc[t, ["interval_score", "MAE", "coverage80", "cov_lo95", "cov_hi95"]] = np.random.default_rng(2).uniform(
        0, 50, (t.sum(), 5))
    assert select_main(m) == select_main(m2)
