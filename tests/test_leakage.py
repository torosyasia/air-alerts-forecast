"""Leakage checks for the features of day D (forecast issued at D 00:00 Kyiv).

Perturbation test: everything that happens at or after t0 is altered (future records
removed, re-timed, or alerts running at t0 given a different end) and the features of D
must not change by a single bit. Only real records are used; perturbations change their
timing, they never add invented alerts to the analysis data.
"""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from airalerts.features import FEATURES, features_at, history_at, origin

FORECAST_CITIES = ("kyiv", "kharkiv", "dnipro")


def _origins(daily, records, city, n_random=15):
    d = daily[(daily.city == city) & (daily.date >= date(2022, 5, 1))]
    rng = np.random.default_rng(1)
    days = list(rng.choice(d.date.to_numpy(), size=n_random, replace=False))
    # days whose midnight falls inside an alert: the hard case (alert running at t0)
    rec = records[records.city == city]
    active = [day for day in d.date.to_numpy()[-120:]
              if ((rec.started_at < origin(day)) & (rec.finished_at > origin(day))).any()]
    days += active[:10]
    days += [date(2026, 3, 29), date(2025, 10, 26), date(2026, 9, 6), date(2026, 9, 7), date(2026, 9, 8)]
    assert len(active) >= 5, "need real origins with an alert running at midnight"
    return days


def _perturbations(rec, t0):
    future = rec.started_at >= t0
    running = (rec.started_at < t0) & (rec.finished_at > t0)
    rng = np.random.default_rng(2)

    p1 = rec[~future]                                          # the future never happens

    p2 = rec.copy()                                            # running alerts end 1 s after t0
    p2.loc[running, "finished_at"] = t0 + pd.Timedelta(seconds=1)

    p3 = rec.copy()                                            # running alerts never end
    p3.loc[running, "finished_at"] = rec.finished_at.max() + pd.Timedelta(days=30)

    p4 = rec.copy()                                            # future re-timed: shifted and
    dur = (rec.finished_at - rec.started_at)[future].to_numpy()  # durations permuted
    p4.loc[future, "started_at"] = rec.started_at[future] + pd.Timedelta(hours=5)
    p4.loc[future, "finished_at"] = p4.started_at[future] + rng.permutation(dur)
    return {"drop_future": p1, "running_end_+1s": p2, "running_never_end": p3, "future_retimed": p4}


@pytest.mark.parametrize("city", FORECAST_CITIES)
def test_features_invariant_to_future(built, city):
    daily, records, _ = built
    rec = records[records.city == city]
    for day in _origins(daily, records, city):
        t0 = origin(day)
        base = features_at(rec, day)
        for name, pert in _perturbations(rec, t0).items():
            alt = features_at(pert, day)
            diff = {k: (base[k], alt[k]) for k in FEATURES if base[k] != alt[k]}
            assert not diff, (city, day, name, diff)


@pytest.mark.parametrize("city", FORECAST_CITIES)
def test_history_is_cut_at_t0(built, city):
    daily, records, _ = built
    rec = records[records.city == city]
    for day in _origins(daily, records, city):
        t0 = origin(day)
        h = history_at(rec, t0)
        assert (h.started_at < t0).all() and (h.finished_at <= t0).all()
        # alerts running at t0 are kept (their pre-midnight part and the fact they are active)
        running = (rec.started_at < t0) & (rec.finished_at > t0)
        assert h.ongoing_at_t0.sum() == running.sum()


@pytest.mark.parametrize("city", FORECAST_CITIES)
def test_lag1_equals_previous_day_target(built, city):
    """h_lag1 for D is exactly the target of D-1 (day D-1 ends at t0), never the target of D."""
    daily, records, _ = built
    d = daily[daily.city == city].set_index("date")
    rec = records[records.city == city]
    for day in _origins(daily, records, city):
        f = features_at(rec, day)
        prev = (pd.Timestamp(day) - pd.Timedelta(days=1)).date()
        assert f["h_lag1"] == pytest.approx(d.hours[prev], abs=1e-9)


def test_running_alert_features_use_only_pre_midnight_part(built):
    """Real case: KMDA uid 2402 ran 2026-09-07 19:39:27 -> 09-08 05:40:43 local (red).
    At t0 = 09-08 00:00 only 4 h 20 min 33 s of it are known."""
    _, records, _ = built
    f = features_at(records[records.city == "kyiv"], date(2026, 9, 8))
    assert f["active_t0"] == 1 and f["active_red_t0"] == 1 and f["active_yellow_t0"] == 0
    assert f["active_elapsed_h"] == pytest.approx((4 * 3600 + 20 * 60 + 33) / 3600, abs=1e-6)


def test_perturbation_test_catches_a_leak(built, monkeypatch):
    """The perturbation test must have power. A realistic bug - the cut placed at 03:00
    instead of 00:00 (UTC midnight read as Kyiv midnight) - must be caught."""
    import airalerts.features as F
    gate = F.history_at

    def leaky_history_at(records, t0, lookback_days=F.LOOKBACK_DAYS + 1):
        return gate(records, t0 + pd.Timedelta(hours=3), lookback_days)

    monkeypatch.setattr(F, "history_at", leaky_history_at)
    daily, records, _ = built
    rec = records[records.city == "kyiv"]
    caught = 0
    for day in _origins(daily, records, "kyiv"):
        base = F.features_at(rec, day)
        for pert in _perturbations(rec, origin(day)).values():
            caught += any(base[k] != F.features_at(pert, day)[k] for k in FEATURES)
    assert caught > 0
