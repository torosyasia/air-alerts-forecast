"""Interval arithmetic: union of overlapping alerts and splitting by Kyiv-local day.

Alerts for one city overlap (oblast + raion + hromada records, duplicated rows, level
changes), so hours are always computed on the union of intervals, never as a sum.
"""
import numpy as np
import pandas as pd

from .config import TZ


def merge(starts, ends, gap_s=0.0):
    """Union of [start, end) intervals. Intervals separated by <= gap_s seconds are joined.

    starts/ends: tz-aware Series or arrays. Returns two numpy datetime64[ns] arrays (UTC).
    """
    s = pd.to_datetime(pd.Series(starts), utc=True).to_numpy("datetime64[ns]")
    e = pd.to_datetime(pd.Series(ends), utc=True).to_numpy("datetime64[ns]")
    if len(s) == 0:
        return s, e
    order = np.argsort(s, kind="stable")
    s, e = s[order], e[order]
    gap = np.timedelta64(int(gap_s * 1e9), "ns")
    out_s, out_e = [s[0]], [e[0]]
    for a, b in zip(s[1:], e[1:]):
        if a <= out_e[-1] + gap:
            if b > out_e[-1]:
                out_e[-1] = b
        else:
            out_s.append(a)
            out_e.append(b)
    return np.array(out_s), np.array(out_e)


def day_bounds(first_day, last_day):
    """Kyiv-local midnights from first_day to last_day + 1 (inclusive), as UTC datetime64.

    Day lengths are 23 h / 25 h on DST transition days.
    """
    days = pd.date_range(first_day, pd.Timestamp(last_day) + pd.Timedelta(days=1), freq="D")
    bounds = days.tz_localize(TZ).tz_convert("UTC")
    return days[:-1].date, bounds.to_numpy("datetime64[ns]")


def hours_per_day(merged_s, merged_e, first_day, last_day):
    """Hours of the (already merged) intervals that fall into each Kyiv-local day."""
    dates, b = day_bounds(first_day, last_day)
    out = np.zeros(len(dates))
    for a, z in zip(merged_s, merged_e):
        i = max(np.searchsorted(b, a, side="right") - 1, 0)
        while i < len(dates) and b[i] < z:
            lo, hi = max(a, b[i]), min(z, b[i + 1])
            if hi > lo:
                out[i] += (hi - lo) / np.timedelta64(1, "s") / 3600.0
            i += 1
    return pd.Series(out, index=pd.Index(dates, name="date"))


def day_lengths(first_day, last_day):
    dates, b = day_bounds(first_day, last_day)
    return pd.Series(np.diff(b) / np.timedelta64(1, "s") / 3600.0, index=pd.Index(dates, name="date"))


def starts_per_day(starts, first_day, last_day):
    """Number of interval starts falling into each Kyiv-local day."""
    dates, b = day_bounds(first_day, last_day)
    s = pd.to_datetime(pd.Series(starts), utc=True).to_numpy("datetime64[ns]")
    idx = np.searchsorted(b, s, side="right") - 1
    ok = (idx >= 0) & (idx < len(dates))
    counts = np.bincount(idx[ok], minlength=len(dates))
    return pd.Series(counts, index=pd.Index(dates, name="date"))


def level_hours_per_day(records, first_day, last_day):
    """Hours per day split by level with precedence red > yellow > none.

    Records of different units of one city can overlap with different levels (e.g. the raion
    on yellow while the city is on red). Overlapping time is counted once, as the most severe
    level, so hours_red + hours_yellow + hours_none == total hours for every day.
    """
    def h(mask):
        r = records[mask]
        return hours_per_day(*merge(r.started_at, r.finished_at), first_day, last_day)
    red = h(records.level == "red")
    red_yellow = h(records.level.isin(["red", "yellow"]))
    total = h(records.level.notna())
    return {"red": red, "yellow": red_yellow - red, "none": total - red_yellow}
