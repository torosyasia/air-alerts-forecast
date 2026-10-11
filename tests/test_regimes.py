"""Change-point posterior and event-window helpers on the real daily table."""
import numpy as np
import pandas as pd

from airalerts.events import PLACEBO_MIN_GAP, PLACEBO_RANGE, window_mean
from airalerts.regimes import changepoint_posterior, compare_periods, detect, summarize


def test_posterior_is_a_distribution_and_hpd_holds_95(built):
    daily, _, _ = built
    d = daily[(daily.city == "kyiv") & (daily.date >= pd.Timestamp("2026-06-01").date())]
    post = changepoint_posterior(np.sqrt(d.hours.to_numpy()), list(d.date))
    assert np.isclose(post.sum(), 1) and (post >= 0).all()
    s = summarize(post)
    hpd = post.sort_values(ascending=False)
    hpd = hpd[hpd.cumsum().shift(fill_value=0) < 0.95]
    assert hpd.sum() >= 0.95 and s["map"] in hpd.index
    assert s["hpd95_from"] <= s["map"] <= s["hpd95_to"]


def test_missing_days_are_left_out(built):
    daily, records, _ = built
    cp, _ = detect(daily, cities=("kharkiv",))
    assert np.isfinite(cp.log10_BF_change_vs_none).all()
    r = compare_periods(daily, records, "kharkiv", pd.Timestamp("2026-08-27").date())
    # 44 calendar days after the cut, 5 of them missing (29.08-02.09)
    assert r["days_after"] == 39


def test_event_window_skips_missing_days(built):
    daily, _, _ = built
    k = daily[daily.city == "kharkiv"]
    y = k.set_index(pd.to_datetime(k.date)).hours
    m = window_mean(y, pd.Timestamp("2026-08-30"))                  # window 29.08-02.09: all missing
    assert np.isnan(m)
    m2 = window_mean(y, pd.Timestamp("2026-09-02"))                 # 01.09-05.09: 03-05.09 observed
    assert np.isclose(m2, y.loc["2026-09-03":"2026-09-05"].mean())
    assert PLACEBO_MIN_GAP >= 5 and PLACEBO_RANGE > PLACEBO_MIN_GAP  # placebo windows never overlap


def test_process_stats_on_real_data(built):
    """Index of dispersion is var/mean of the daily counts; quiet gaps that touch a missing
    day (29.08-02.09 for Kharkiv) are not used."""
    from airalerts.process import analyse
    daily, records, _ = built
    res, gaps = analyse(daily, records, cities=("kharkiv",))
    r = res[res.period == "after"].iloc[0]
    d = daily[(daily.city == "kharkiv") & ~daily.missing & (daily.date >= pd.Timestamp("2026-08-27").date())]
    assert np.isclose(r.dispersion_D, d.n_episodes.var(ddof=1) / d.n_episodes.mean())
    g = gaps[("kharkiv", "after")]
    assert (g > 0).all() and g.max() < 24 * 5      # no gap bridges the 5-day outage
