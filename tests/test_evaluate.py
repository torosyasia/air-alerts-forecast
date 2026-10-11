"""Rolling-origin evaluation: periods, no look-ahead in baselines, metric identities.
All checks use the real daily target table and real baseline forecasts."""
import numpy as np
import pandas as pd
import pytest

from airalerts.evaluate import (FORECAST_CITIES, TEST_DAYS, baseline_forecasts, block_bootstrap_diff,
                                interval_score, periods, pinball)


def test_periods_are_ordered_and_disjoint(built):
    daily, _, _ = built
    p = periods(daily)
    v0, v1 = p["validation"]
    t0, t1 = p["test"]
    assert t1 == daily.date.max()                                   # ends at the last complete day
    assert (pd.Timestamp(t1) - pd.Timestamp(t0)).days + 1 == TEST_DAYS
    assert v0 <= v1 < t0                                            # validation strictly before test
    assert p["backtest_appendix"][1] < v0


@pytest.mark.parametrize("city", FORECAST_CITIES)
def test_baselines_use_only_the_past(built, city):
    """Changing the target on D and after (permuting the real values) must not change any
    baseline forecast for D."""
    daily, _, _ = built
    d = daily[daily.city == city].sort_values("date").reset_index(drop=True)
    base = baseline_forecasts(d).set_index(["date", "method"])
    rng = np.random.default_rng(3)
    p = periods(daily)
    days = [p["test"][0], p["test"][1], p["validation"][0], pd.Timestamp("2026-09-06").date()]
    for day in days:
        alt = d.copy()
        fut = alt.date >= day
        alt.loc[fut, "hours"] = rng.permutation(alt.loc[fut, "hours"].to_numpy())
        f = baseline_forecasts(alt).set_index(["date", "method"])
        a, b = base.xs(day, level="date"), f.xs(day, level="date")
        assert np.allclose(a[["q10", "q50", "q90"]], b[["q10", "q50", "q90"]], atol=0, rtol=0), (city, day)


def test_interval_bounds(built):
    daily, _, _ = built
    for city in FORECAST_CITIES:
        d = daily[daily.city == city]
        f = baseline_forecasts(d).merge(d[["date", "day_len_h"]], on="date")
        assert (f.q10 <= f.q90).all()
        assert (f.q10 >= 0).all() and (f.q90 <= f.day_len_h + 1e-9).all()


def test_metric_identities_on_real_forecasts(built):
    daily, _, _ = built
    f = baseline_forecasts(daily[daily.city == "kyiv"])
    # pinball loss at tau = 0.5 is half the absolute error
    assert np.allclose(pinball(f.y, f.q50, 0.5), 0.5 * (f.y - f.q50).abs())
    s = interval_score(f.y, f.q10, f.q90)
    covered = (f.y >= f.q10) & (f.y <= f.q90)
    assert np.allclose(s[covered], (f.q90 - f.q10)[covered])        # inside: score = width
    assert (s[~covered] > (f.q90 - f.q10)[~covered]).all()          # outside: penalised


def test_block_bootstrap_on_real_losses(built):
    daily, _, _ = built
    f = baseline_forecasts(daily[daily.city == "kyiv"])
    a = f[f.method == "yesterday"].set_index("date")
    b = f[f.method == "median7"].set_index("date")
    a, b = a.loc[a.index.intersection(b.index)].tail(60), b.loc[a.index.intersection(b.index)].tail(60)
    la, lb = (a.y - a.q50).abs(), (b.y - b.q50).abs()
    m, lo, hi = block_bootstrap_diff(la, lb)
    assert m == pytest.approx((la - lb).mean()) and lo <= m <= hi
    assert block_bootstrap_diff(la, lb) == (m, lo, hi)              # deterministic with a seed
