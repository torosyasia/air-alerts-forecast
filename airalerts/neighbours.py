"""Did the oblasts around Kyiv change on 27.08 too? (check added after the devil's-advocate review)

"Any alert in the oblast" = union of every official record in that oblast (oblast, raion or
hromada level), so it is broader than "the city is covered" and saturates for frontline
oblasts (one raion is almost always under alert) - the share of the day under alert before
27.08 is reported so that saturation is visible.

Only the official channel CSV is used, before 07.09: no source stitching. Days 29.08-02.09
(channel outage, D-06a) are left out, and records running at the outage start are cut there.
Before = 60 days before 27.08; after = 27.08-06.09 without the outage days (6 days). The
official CSV does not change any more after 07.09, so these numbers do not depend on the
snapshot.
"""
from datetime import timedelta

import numpy as np
import pandas as pd
from scipy import stats

from . import intervals as iv
from .config import IMPUTED_DURATION_S, OFFICIAL_OUTAGES, RESULTS, TZ, source_path
from .regimes import HYP_DAY, episodes

LAST_DAY = pd.Timestamp("2026-09-06").date()
GROUPS = {
    "м. Київ": "Київ",
    "Київська область": "довкола Києва",
    "Житомирська область": "довкола Києва",
    "Черкаська область": "довкола Києва",
    "Вінницька область": "довкола Києва",
    "Чернігівська область": "інші",
    "Полтавська область": "інші",
    "Сумська область": "інші",
    "Харківська область": "інші",
    "Дніпропетровська область": "інші",
}


def load():
    raw = pd.read_csv(source_path("official")).drop_duplicates()
    for c in ("started_at", "finished_at"):
        raw[c] = pd.to_datetime(raw[c], utc=True, format="mixed")
    raw = raw[(raw.finished_at - raw.started_at).dt.total_seconds() != IMPUTED_DURATION_S]
    for lo, _ in OFFICIAL_OUTAGES:                 # records running at the outage start: cut there
        running = (raw.started_at < lo) & (raw.finished_at > lo)
        raw.loc[running, "finished_at"] = lo
    return raw


def outage_days():
    out = set()
    for lo, hi in OFFICIAL_OUTAGES:
        d = lo.tz_convert(TZ).date()
        while d <= hi.tz_convert(TZ).date():
            out.add(d)
            d += timedelta(days=1)
    return out


def analyse(raw=None, groups=None):
    """groups: {oblast: group label}; default GROUPS (fig9). national.py passes every oblast."""
    raw = load() if raw is None else raw
    groups = groups or GROUPS
    first = HYP_DAY - timedelta(days=60)
    gap = outage_days()
    days = [d for d in pd.date_range(first, LAST_DAY).date if d not in gap]
    before = [d for d in days if d < HYP_DAY]
    after = [d for d in days if d >= HYP_DAY]
    series = {}
    for ob in groups:
        r = raw[raw.oblast == ob]
        n = episodes(r.assign(city="x"), "x").groupby("date").size().reindex(days, fill_value=0)
        h = pd.Series(iv.hours_per_day(*iv.merge(r.started_at, r.finished_at), first, LAST_DAY),
                      index=pd.date_range(first, LAST_DAY).date).reindex(days)
        series[ob] = (n, h)
    kyiv_n = series["м. Київ"][0]
    rows = []
    for ob, (n, h) in series.items():
        rows.append({
            "oblast": ob, "group": groups[ob],
            "share_of_day_under_alert_before": h[before].mean() / 24,
            "alerts_per_day_before": n[before].mean(), "alerts_per_day_after": n[after].mean(),
            "alerts_ratio": n[after].mean() / n[before].mean(),
            "hours_per_day_before": h[before].mean(), "hours_per_day_after": h[after].mean(),
            "hours_ratio": h[after].mean() / h[before].mean(),
            "p_alerts_more_mw": stats.mannwhitneyu(n[after], n[before], alternative="greater").pvalue,
            "corr_daily_alerts_with_kyiv_before": np.corrcoef(n[before], kyiv_n[before])[0, 1],
            "days_before": len(before), "days_after": len(after),
        })
    return pd.DataFrame(rows), series, (before, after)


def main():
    t, _, _ = analyse()
    RESULTS.mkdir(exist_ok=True)
    t.round(4).to_csv(RESULTS / "neighbour_oblasts.csv", index=False)
    return t


if __name__ == "__main__":
    print(main().round(2).to_string())
