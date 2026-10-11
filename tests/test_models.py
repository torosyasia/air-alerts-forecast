"""Quantile regression and CQR: no look-ahead, valid quantiles. Real data only."""
import numpy as np
import pandas as pd
import pytest

from airalerts.evaluate import periods
from airalerts.features import feature_matrix
from airalerts.models import FEATURE_SETS, conformalize, days_between, rolling_forecasts


@pytest.fixture(scope="module")
def kyiv_X(built):
    daily, records, _ = built
    return feature_matrix(records, daily, cities=["kyiv"]), daily


def _forecast(X, daily, day, window):
    import airalerts.models as M
    old = M.FORECAST_CITIES
    M.FORECAST_CITIES = ("kyiv",)
    try:
        return rolling_forecasts(X, daily, [day], FEATURE_SETS["with_midnight"], window, "m").iloc[0]
    finally:
        M.FORECAST_CITIES = old


@pytest.mark.parametrize("window", [None, 84])
def test_model_forecast_ignores_the_future(kyiv_X, window):
    """Permute the targets of D and later, and the feature rows after D: the forecast for D
    must not change (only rows dated before D are used for fitting)."""
    X, daily = kyiv_X
    rng = np.random.default_rng(4)
    p = periods(daily)
    for day in (p["test"][0], p["validation"][0]):
        base = _forecast(X, daily, day, window)
        alt = X.copy()
        fut = alt.date >= day
        alt.loc[fut, "y"] = rng.permutation(alt.loc[fut, "y"].to_numpy())
        later = alt.date > day
        feats = [c for c in alt.columns if c not in ("city", "date", "y")]
        alt.loc[later, feats] = alt.loc[later, feats].sample(frac=1, random_state=5).to_numpy()
        new = _forecast(alt, daily, day, window)
        assert np.allclose(base[["q10", "q50", "q90"]].astype(float), new[["q10", "q50", "q90"]].astype(float),
                           atol=0, rtol=0)


def test_quantiles_ordered_and_bounded(kyiv_X):
    X, daily = kyiv_X
    p = periods(daily)
    for day in days_between(*p["test"])[:5]:
        f = _forecast(X, daily, day, None)
        assert 0 <= f.q10 <= f.q50 <= f.q90 <= f.cap


def test_cqr_uses_only_past_days(kyiv_X):
    """The conformal correction for D uses the scores of the 28 days before D: changing the
    observed y on D and later leaves the corrected interval for D unchanged."""
    X, daily = kyiv_X
    import airalerts.models as M
    old = M.FORECAST_CITIES
    M.FORECAST_CITIES = ("kyiv",)
    try:
        days = days_between(pd.Timestamp("2026-08-20").date(), pd.Timestamp("2026-09-30").date())
        f = rolling_forecasts(X, daily, days, FEATURE_SETS["no_midnight"], 84, "m")
    finally:
        M.FORECAST_CITIES = old
    D = pd.Timestamp("2026-09-25").date()
    c0 = conformalize(f).set_index("date")
    alt = f.copy()
    alt.loc[alt.date >= D, "y"] = alt.loc[alt.date >= D, "y"].to_numpy()[::-1]
    c1 = conformalize(alt).set_index("date")
    assert c0.loc[D, "q10"] == c1.loc[D, "q10"] and c0.loc[D, "q90"] == c1.loc[D, "q90"]
    assert (c0.q10 <= c0.q90).all() and (c0.q10 >= 0).all() and (c0.q90 <= c0.cap + 1e-9).all()
