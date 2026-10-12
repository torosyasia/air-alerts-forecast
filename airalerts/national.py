"""All-Ukraine extension: every oblast centre on government-controlled territory.

1. Target: hours under alert per Kyiv-local day for each centre, with the same covering rule,
   cleaning, stitching and missing days as the four studied cities (build.prepare/stitch).
   The stitch official CSV -> alerts.in.ua is checked on the overlap window for every city,
   and cities with questionable data are flagged, not dropped.
2. Descriptive layers for the map: change after 27.08 (fig9 method, every oblast), hours in
   the last 30 days, and whether alerts grew in October.
3. Forecast: one shared quantile regression for all centres (same features + a city effect)
   against per-city models and the simple baselines - see national_models.py.
"""
import numpy as np
import pandas as pd
from scipy import stats

from . import intervals as iv
from .build import overlap_hours, prepare, stitch
from .config import (ALL_CITIES, ARCHIVE_COMPLETE_FROM, OFFICIAL_COMPLETE_UNTIL, OFFICIAL_OUTAGES, PROCESSED,
                     RESULTS, TZ)

STITCH_WINDOW = (ARCHIVE_COMPLETE_FROM, OFFICIAL_COMPLETE_UNTIL)   # both sources complete
STITCH_TOL_H = 0.5          # |official - archive| hours on the overlap window above this -> flagged
OCT = (pd.Timestamp("2026-10-01").date(), None)                  # October so far
SEPT = (pd.Timestamp("2026-09-07").date(), pd.Timestamp("2026-09-30").date())  # same source (archive)


def build_targets():
    p = prepare(ALL_CITIES)
    records, daily, _ = stitch(p, ALL_CITIES)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    records.to_csv(PROCESSED / "national_records.csv", index=False)
    daily.to_csv(PROCESSED / "national_daily.csv", index=False)
    cols = ["city", "date", "hours", "hours_yellow", "hours_red", "n_episodes", "source", "missing"]
    RESULTS.mkdir(exist_ok=True)
    daily[cols].round(3).to_csv(RESULTS / "national_daily_target.csv", index=False)
    return records, daily, data_checks(p, records, daily)


def load_national():
    records = pd.read_csv(PROCESSED / "national_records.csv", dtype={"cause": "string"})
    for c in ("started_at", "finished_at"):
        records[c] = pd.to_datetime(records[c], utc=True, format="mixed")
    daily = pd.read_csv(PROCESSED / "national_daily.csv")
    daily["date"] = pd.to_datetime(daily.date).dt.date
    return records, daily


def data_checks(p, records, daily):
    """Per-city data quality: stitch agreement on the overlap window, archive coverage after
    the switch, missing days, very long alerts. Problems are flagged in the table."""
    lo, hi = STITCH_WINDOW
    rows = []
    for key, city in ALL_CITIES.items():
        d = daily[daily.city == key]
        r = {"city": key, "name": city.name_uk, "oblast": city.oblast_uk,
             "days": len(d), "missing_days": int(d.missing.sum()),
             "long_alert_days": int(d.long_alert.sum())}
        if city.kyiv_kmda:
            r.update(stitch_official_h=np.nan, stitch_archive_h=np.nan, stitch_diff_h=np.nan)
        else:
            a = overlap_hours(p["official"][p["official"].city == key], lo, hi)
            b = overlap_hours(p["archive"][p["archive"].city == key], lo, hi)
            r.update(stitch_official_h=a, stitch_archive_h=b, stitch_diff_h=b - a)
        arc = p["archive"][(p["archive"].city == key)]
        r["archive_units"] = ", ".join(sorted(arc.unit.unique()))
        after = d[d.source == "alerts_in_ua"]
        r["archive_days_with_alert_share"] = float((after.hours > 0).mean()) if len(after) else np.nan
        issues = []
        if not city.kyiv_kmda and abs(r["stitch_diff_h"]) > STITCH_TOL_H:
            issues.append(f"склейка: {r['stitch_official_h']:.1f} год (офіційний канал) проти "
                          f"{r['stitch_archive_h']:.1f} год (alerts.in.ua) на перекритті")
        if r["long_alert_days"] > 0:
            issues.append(f"тривоги > 24 год у {r['long_alert_days']} днях")
        r["issues"] = "; ".join(issues)
        rows.append(r)
    t = pd.DataFrame(rows)
    t.round(3).to_csv(RESULTS / "national_data_checks.csv", index=False)
    return t


def recent_layers(daily, n_days=30):
    """Per city: hours/day in the last n days, and October vs 07.09-30.09 (same source)."""
    last = daily.date.max()
    rows = []
    for key, d in daily.groupby("city"):
        d = d.set_index("date").sort_index()
        last30 = d.loc[(pd.Timestamp(last) - pd.Timedelta(days=n_days - 1)).date():last]
        sep = d.loc[SEPT[0]:SEPT[1]].dropna(subset=["hours"])
        octo = d.loc[OCT[0]:last].dropna(subset=["hours"])
        p_h = stats.mannwhitneyu(octo.hours, sep.hours, alternative="greater").pvalue
        p_n = stats.mannwhitneyu(octo.n_episodes, sep.n_episodes, alternative="greater").pvalue
        rows.append({
            "city": key, "hours_per_day_30d": last30.hours.mean(), "days_30d": int(last30.hours.notna().sum()),
            "hours_sep": sep.hours.mean(), "hours_oct": octo.hours.mean(),
            "alerts_sep": sep.n_episodes.mean(), "alerts_oct": octo.n_episodes.mean(),
            "hours_ratio_oct_sep": octo.hours.mean() / sep.hours.mean() if sep.hours.mean() > 0 else np.nan,
            "alerts_ratio_oct_sep": (octo.n_episodes.mean() / sep.n_episodes.mean()
                                     if sep.n_episodes.mean() > 0 else np.nan),
            "p_hours_oct_more": p_h, "p_alerts_oct_more": p_n,
            "oct_days": len(octo), "sep_days": len(sep),
        })
    t = pd.DataFrame(rows)
    # "grew in October": more alert hours or more alerts, one-sided Mann-Whitney p < 0.05 and >= +25%
    t["october_growth"] = (((t.p_hours_oct_more < 0.05) & (t.hours_ratio_oct_sep >= 1.25))
                           | ((t.p_alerts_oct_more < 0.05) & (t.alerts_ratio_oct_sep >= 1.25)))
    return t


BREAK = pd.Timestamp("2026-08-27").date()


def change_after_break(daily, before_days=60):
    """Per city, the same comparison as for Kyiv in the README / reports/regimes.md: mean hours
    and alerts per day in the 60 days before 27.08 vs 27.08 - last day (missing days left out)."""
    lo = (pd.Timestamp(BREAK) - pd.Timedelta(days=before_days)).date()
    rows = []
    for key, d in daily.groupby("city"):
        b = d[(d.date >= lo) & (d.date < BREAK)].dropna(subset=["hours"])
        a = d[d.date >= BREAK].dropna(subset=["hours"])
        hb, ha = b.hours.mean(), a.hours.mean()
        reform = pd.Timestamp("2026-09-06").date()
        a1, a2 = a[a.date < reform], a[a.date >= reform]       # before / after the 06.09 reform
        rows.append({"city": key, "hours_before": hb, "hours_after": ha, "hours_delta": ha - hb,
                     "hours_ratio": ha / hb if hb > 0 else np.nan,
                     "alerts_before": b.n_episodes.mean(), "alerts_after": a.n_episodes.mean(),
                     "days_before": len(b), "days_after": len(a),
                     # 27.08-05.09: one source (official CSV, outage days missing) and before the reform;
                     # 06.09-: after the reform and, for all but Kyiv, from alerts.in.ua
                     "hours_27_08_05_09": a1.hours.mean(), "days_27_08_05_09": len(a1),
                     "hours_from_06_09": a2.hours.mean(),
                     "window": f"{lo:%d.%m}–{(BREAK - pd.Timedelta(days=1)):%d.%m} проти "
                               f"{BREAK:%d.%m}–{d.date.max():%d.%m}"})
    return pd.DataFrame(rows)


def thirty_day_series(daily, n_days=30):
    last = daily.date.max()
    first = (pd.Timestamp(last) - pd.Timedelta(days=n_days - 1)).date()
    d = daily[(daily.date >= first) & (daily.date <= last)]
    return {k: [None if pd.isna(h) else round(float(h), 2) for h in g.sort_values("date").hours]
            for k, g in d.groupby("city")}, first, last
