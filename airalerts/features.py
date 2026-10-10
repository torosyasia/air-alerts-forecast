"""Features for the forecast of day D, issued at t0 = D 00:00 Kyiv time.

Leakage rule (DECISIONS.md D-14): a feature may use only what was known at t0.
`history_at` is the single gate: it drops every record that starts at or after t0 and
cuts every alert still running at t0 at t0 (its end is unknown then; only the part before
midnight and the fact that it is active are known). All features are computed from that
history alone, and `history_at` asserts the cut.
"""
import numpy as np
import pandas as pd

from . import intervals as iv
from .config import EPISODE_GAP_S, TZ

LOOKBACK_DAYS = 28
REFORM_DAY = pd.Timestamp("2026-09-06").date()  # Kyiv: yellow/red levels from 06.09 06:00

FEATURES = (
    [f"h_lag{k}" for k in range(1, 8)]
    + ["h_mean7", "h_med7", "h_mean28", "ep_lag1", "ep_mean7",
       "yellow_lag1", "red_lag1", "active_t0", "active_yellow_t0", "active_red_t0",
       "active_elapsed_h", "h_last6h", "days_since_alert", "dow", "weekend", "post_reform"]
)


def origin(day):
    """Forecast time t0 for Kyiv-local day `day`, in UTC."""
    return pd.Timestamp(day).tz_localize(TZ).tz_convert("UTC")


def history_at(records, t0, lookback_days=LOOKBACK_DAYS + 1):
    """Records as they were known at t0, limited to the lookback window."""
    lo = t0 - pd.Timedelta(days=lookback_days + 1)
    h = records[(records.started_at < t0) & (records.finished_at > lo)].copy()
    h["ongoing_at_t0"] = h.finished_at > t0
    h["finished_at"] = h.finished_at.where(~h.ongoing_at_t0, t0)
    assert (h.started_at < t0).all() and (h.finished_at <= t0).all(), "leakage: record beyond t0"
    return h


def features_at(records, day):
    """Feature vector for day D from the records of one city."""
    t0 = origin(day)
    h = history_at(records, t0)
    first = (pd.Timestamp(day) - pd.Timedelta(days=LOOKBACK_DAYS)).date()
    last = (pd.Timestamp(day) - pd.Timedelta(days=1)).date()

    ms, me = iv.merge(h.started_at, h.finished_at)
    hours = iv.hours_per_day(ms, me, first, last).to_numpy()[::-1]   # hours[0] = day D-1
    es, _ = iv.merge(h.started_at, h.finished_at, gap_s=EPISODE_GAP_S)
    eps = iv.starts_per_day(es, first, last).to_numpy()[::-1]
    lvl = {}
    for name in ("yellow", "red"):
        r = h[h.level == name]
        lvl[name] = iv.hours_per_day(*iv.merge(r.started_at, r.finished_at), last, last).iloc[0]

    f = {f"h_lag{k}": hours[k - 1] for k in range(1, 8)}
    f["h_mean7"] = hours[:7].mean()
    f["h_med7"] = float(np.median(hours[:7]))
    f["h_mean28"] = hours[:28].mean()
    f["ep_lag1"] = eps[0]
    f["ep_mean7"] = eps[:7].mean()
    f["yellow_lag1"] = lvl["yellow"]
    f["red_lag1"] = lvl["red"]

    t0_64 = t0.to_datetime64()
    running = h[h.ongoing_at_t0]
    f["active_t0"] = float(len(running) > 0)
    f["active_yellow_t0"] = float((running.level == "yellow").any())
    f["active_red_t0"] = float((running.level == "red").any())
    # start of the merged episode that is still running at t0 (merge cannot move a start
    # earlier using records that begin after t0, because those are not in the history)
    run = (ms < t0_64) & (me >= t0_64)  # the merged episode covering t0
    f["active_elapsed_h"] = (float((t0_64 - ms[run][-1]) / np.timedelta64(1, "s") / 3600)
                             if f["active_t0"] and run.any() else 0.0)
    lo6 = t0_64 - np.timedelta64(6, "h")
    f["h_last6h"] = float(sum(max(np.timedelta64(0, "s"), min(e, t0_64) - max(s, lo6))
                              / np.timedelta64(1, "s") for s, e in zip(ms, me)) / 3600)
    nz = np.nonzero(hours[:LOOKBACK_DAYS] > 0)[0]
    f["days_since_alert"] = float(nz[0] + 1) if len(nz) else float(LOOKBACK_DAYS + 1)
    if f["active_t0"]:
        f["days_since_alert"] = 0.0

    dow = pd.Timestamp(day).dayofweek
    f["dow"] = float(dow)
    f["weekend"] = float(dow >= 5)
    f["post_reform"] = float(pd.Timestamp(day).date() >= REFORM_DAY)
    return f


def feature_matrix(records, daily, cities=None):
    """One row per (city, day): features known at t0 plus the target y = hours of day D."""
    rows = []
    for city, d in daily.groupby("city"):
        if cities and city not in cities:
            continue
        rec = records[records.city == city]
        start = (pd.Timestamp(d.date.min()) + pd.Timedelta(days=LOOKBACK_DAYS)).date()
        for day, y in zip(pd.to_datetime(d.date).dt.date, d.hours):
            if day < start:
                continue
            f = features_at(rec, day)
            f.update(city=city, date=day, y=y)
            rows.append(f)
    cols = ["city", "date", "y"] + FEATURES
    return pd.DataFrame(rows)[cols]


def build_features(cities=("kyiv", "kharkiv", "dnipro")):
    from .build import load_processed
    from .config import PROCESSED
    records, daily = load_processed()
    X = feature_matrix(records, daily, cities)
    X.to_csv(PROCESSED / "features.csv", index=False)
    return X


if __name__ == "__main__":
    X = build_features()
    print(X.groupby("city").size(), X.tail(3).T)
