"""Checks of the daily target on the real data.

The main oracle recomputes coverage of a day by brute force on a 1-second grid from the
cleaned records and compares it with the interval-union implementation.
"""
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from airalerts import intervals as iv
from airalerts.config import CITIES, SOURCES, TZ
from airalerts.sources import load_official


def _day_window(d):
    lo = pd.Timestamp(d).tz_localize(TZ)
    hi = (pd.Timestamp(d) + pd.Timedelta(days=1)).tz_localize(TZ)
    return lo.tz_convert("UTC"), hi.tz_convert("UTC")


def grid_hours(records, d):
    lo, hi = _day_window(d)
    n = int((hi - lo).total_seconds())
    covered = np.zeros(n, dtype=bool)
    r = records[(records.finished_at > lo) & (records.started_at < hi)]
    for s, e in zip(r.started_at, r.finished_at):
        a = max(0, int(np.floor((s - lo).total_seconds())))
        b = min(n, int(np.ceil((e - lo).total_seconds())))
        covered[a:b] = True
    return covered.sum() / 3600, len(r)


def test_hours_within_day_length(built):
    daily, _, _ = built
    d = daily[~daily.missing]
    for col in ("hours", "hours_none", "hours_yellow", "hours_red"):
        assert (d[col] >= 0).all()
        assert (d[col] <= d.day_len_h + 1e-9).all(), col
    assert daily.hours.isna().equals(daily.missing)  # NaN only on documented missing days


def test_dst_day_lengths(built):
    daily, _, _ = built
    k = daily[daily.city == "kyiv"].set_index("date").day_len_h
    assert k[date(2026, 3, 29)] == 23 and k[date(2025, 10, 26)] == 25 and k[date(2026, 3, 30)] == 24


@pytest.mark.parametrize("city", list(CITIES))
def test_union_matches_second_grid(built, city):
    daily, records, _ = built
    d = daily[daily.city == city].set_index("date")
    rec = records[records.city == city]
    rng = np.random.default_rng(0)
    days = list(rng.choice(d.index[d.hours > 0], size=40, replace=False))
    days += [date(2026, 3, 29), date(2025, 10, 26), date(2026, 9, 6), date(2026, 9, 7), date(2026, 9, 8)]
    for day in days:
        h, n_rec = grid_hours(rec, day)
        # ceil/floor of sub-second timestamps: at most 1 s per record boundary
        assert abs(h - d.hours[day]) <= 2 * n_rec / 3600 + 1e-9, (city, day, h, d.hours[day])


def test_alert_across_midnight_is_split(built):
    """KMDA uid 2402 (red, 'Ракетна загроза') runs 2026-09-07 19:39:27 -> 09-08 05:40:43 local."""
    daily, _, _ = built
    raw = pd.DataFrame(json.loads(SOURCES["kmda"]["path"].read_text(encoding="utf-8"))).set_index("uid")
    def h(uid, lo=None, hi=None):
        s, e = pd.Timestamp(raw.dateTimeStart[uid]), pd.Timestamp(raw.dateTimeEnd[uid])
        s, e = max(s, lo) if lo else s, min(e, hi) if hi else e
        return (e - s).total_seconds() / 3600
    midnight = pd.Timestamp("2026-09-08 00:00")
    k = daily[daily.city == "kyiv"].set_index("date").hours
    # 09-07: uid 2401 (whole) + uid 2402 up to midnight
    assert k[date(2026, 9, 7)] == pytest.approx(h("2401") + h("2402", hi=midnight), abs=1e-6)
    # 09-08: uid 2402 after midnight + 2403..2405 + 2406 up to midnight
    expected = h("2402", lo=midnight) + h("2403") + h("2404") + h("2405") + h("2406", hi=pd.Timestamp("2026-09-09"))
    assert k[date(2026, 9, 8)] == pytest.approx(expected, abs=1e-6)


def test_covering_rule(built):
    """Only the oblast, the city's raion and the city's hromada count."""
    _, records, _ = built
    for key, c in CITIES.items():
        r = records[(records.city == key) & (records.segment == "official")]
        allowed = r.unit.eq(c.oblast_uk)
        if c.raion_uk:
            allowed |= r.unit.eq(c.raion_uk)
        if c.hromada_prefix:
            allowed |= r.unit.str.startswith(c.hromada_prefix)
        assert allowed.all(), r.unit[~allowed].unique()
        a = records[(records.city == key) & (records.segment == "alerts_in_ua")]
        assert a.unit.isin(c.archive_titles).all()
    # a real alert in another raion of Kharkiv oblast exists in the raw data but not in the city
    raw = pd.read_csv(SOURCES["official"]["path"], usecols=["oblast", "raion", "level", "started_at"])
    other = raw[(raw.oblast == "Харківська область") & (raw.level == "raion") & (raw.raion == "Чугуївський район")]
    assert len(other) > 0
    assert not records[records.city == "kharkiv"].unit.eq("Чугуївський район").any()


def test_duplicates_do_not_change_hours():
    """Union is idempotent: the official CSV with its exact duplicate rows gives the same hours."""
    official, _ = load_official()
    k = official[official.city == "kharkiv"]
    doubled = pd.concat([k, k])
    a = iv.hours_per_day(*iv.merge(k.started_at, k.finished_at), date(2025, 1, 1), date(2026, 9, 5))
    b = iv.hours_per_day(*iv.merge(doubled.started_at, doubled.finished_at), date(2025, 1, 1), date(2026, 9, 5))
    assert np.allclose(a, b)


def test_imputed_rows_dropped(built):
    _, records, _ = built
    r = records[records.segment == "official"]
    assert not ((r.finished_at - r.started_at).dt.total_seconds() == 3600).any()


def test_snapshot_truncation(built):
    daily, records, _ = built
    snap = records.finished_at.max()
    assert records.started_at.max() <= snap
    snap_day = snap.tz_convert(TZ).date()
    assert daily.date.max() < snap_day  # the snapshot day is incomplete and excluded


def test_one_source_per_day_and_segments_respected(built):
    daily, records, _ = built
    assert daily.source.notna().all()
    assert not daily.duplicated(["city", "date"]).any()
    for key in CITIES:
        r = records[records.city == key]
        for seg, g in r.groupby("segment"):
            other = r[r.segment != seg]
            if len(other) and len(g):
                # segments are disjoint in time
                assert g.started_at.min() >= other.finished_at.max() or g.finished_at.max() <= other.started_at.min()


def test_cross_source_agreement(built):
    _, _, c = built
    assert c["kyiv_kmda_vs_archive"]["days_absdiff_gt_0.1h"] == 0
    assert c["kyiv_kmda_vs_archive"]["mae_h"] < 0.05
    assert c["kyiv_kmda_vs_official"]["corr"] > 0.97
    k = c["kharkiv_official_vs_archive_overlap"]
    assert abs(k["official_h"] - k["archive_h"]) < 0.05


def test_level_hours_add_up_to_total(built):
    """red + yellow + none == total for every city and day (overlaps counted once, as red)."""
    daily, _, _ = built
    d = daily[~daily.missing]
    s = d.hours_red + d.hours_yellow + d.hours_none
    assert np.allclose(s, d.hours, atol=1e-9)
    assert (d[["hours_red", "hours_yellow", "hours_none"]] >= -1e-9).all().all()


def test_red_wins_where_levels_overlap(built):
    """Real case: Kharkiv has yellow and red records of different units overlapping in time
    (raion vs city/hromada). Summing per-level unions would exceed the total on those days."""
    daily, records, _ = built
    k = records[records.city == "kharkiv"]
    d = daily[daily.city == "kharkiv"].set_index("date")
    first, last = d.index.min(), d.index.max()
    naive = sum(iv.hours_per_day(*iv.merge(k[k.level == l].started_at, k[k.level == l].finished_at), first, last)
                for l in ("red", "yellow", "none"))
    excess = naive - d.hours
    assert (excess > 0.01).sum() > 0               # the overlap is real
    assert np.allclose(d.hours_red + d.hours_yellow + d.hours_none, d.hours, atol=1e-9, equal_nan=True)


def test_channel_outage_days_are_missing_not_filled(built):
    """The official channel published nothing 2026-08-29 04:55 -> 09-02 13:48 UTC (post #334745:
    'З технічних причин тимчасово не працює публікація'). Kharkiv, Dnipro, Lviv use that source
    then: their days 29.08-02.09 are NaN. Kyiv uses KMDA and is complete."""
    daily, records, _ = built
    out = [date(2026, 8, d) for d in (29, 30, 31)] + [date(2026, 9, 1), date(2026, 9, 2)]
    for city in ("kharkiv", "dnipro", "lviv"):
        d = daily[daily.city == city].set_index("date")
        assert d.loc[out, "missing"].all() and d.loc[out, "hours"].isna().all()
        assert not d.loc[[date(2026, 8, 28), date(2026, 9, 3)], "missing"].any()
        r = records[(records.city == city) & (records.segment == "official")]
        lo = pd.Timestamp("2026-08-29 04:55:28", tz="UTC")
        assert not ((r.finished_at > lo) & (r.started_at < pd.Timestamp("2026-09-02 13:48:04", tz="UTC"))).any()
    k = daily[daily.city == "kyiv"].set_index("date")
    assert not k.loc[out, "missing"].any() and k.loc[out, "hours"].notna().all()
