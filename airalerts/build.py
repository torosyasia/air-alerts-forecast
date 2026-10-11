"""Build city-level alert records and the daily target table, plus a data-quality report.

Target (DECISIONS.md, D-04): hours of Kyiv-local day D (00:00-24:00) during which the city
is covered by at least one air_raid alert of any level, computed on the union of intervals.

Outputs:
  data/processed/city_records.csv  cleaned, stitched records per city (UTC)
  data/processed/daily.csv         one row per city and day
  reports/data_quality.md          what was dropped, flagged, stitched and cross-checked
"""
import json

import numpy as np
import pandas as pd

from . import intervals as iv
from .config import (ARCHIVE_COMPLETE_FROM, CITIES, EPISODE_GAP_S, OFFICIAL_COMPLETE_UNTIL, OFFICIAL_OUTAGES,
                     OFFICIAL_TO_ARCHIVE_CUT, PROCESSED, REPORTS, RESULTS, TZ, kmda_to_archive_cut)
from .fetch import fetch_pinned
from .sources import load_archive, load_kmda, load_official

FIRST_DAY = pd.Timestamp("2022-03-16").date()  # first full day of the official CSV
LONG_ALERT_H = 24


def local_midnight(ts_utc):
    return ts_utc.tz_convert(TZ).normalize()


def clip(df, lo=None, hi=None):
    """Keep the part of each record inside [lo, hi)."""
    d = df.copy()
    if lo is not None:
        d = d[d.finished_at > lo]
        d["started_at"] = d.started_at.where(d.started_at >= lo, lo)
    if hi is not None:
        d = d[d.started_at < hi]
        d["finished_at"] = d.finished_at.where(d.finished_at <= hi, hi)
    return d


def segments(official, archive, kmda, archive_snapshot):
    """Which source covers which time range, per city. Returns {city: [(source_df, lo, hi)]}."""
    kmda_cut = kmda_to_archive_cut()          # pinned with the snapshot, not derived from the data
    archive_cut = OFFICIAL_TO_ARCHIVE_CUT.tz_convert("UTC")
    assert ARCHIVE_COMPLETE_FROM < archive_cut < OFFICIAL_COMPLETE_UNTIL
    assert kmda_cut > ARCHIVE_COMPLETE_FROM
    seg = {}
    for key, city in CITIES.items():
        arc = archive[archive.city == key]
        if city.kyiv_kmda:
            seg[key] = [("kmda", kmda, None, kmda_cut.tz_convert("UTC")),
                        ("alerts_in_ua", arc, kmda_cut.tz_convert("UTC"), archive_snapshot)]
        else:
            seg[key] = [("official", official[official.city == key], None, archive_cut),
                        ("alerts_in_ua", arc, archive_cut, archive_snapshot)]
    return seg


def build():
    fetch_pinned()
    official, st_off = load_official()
    archive, st_arc = load_archive()
    kmda, st_kmda = load_kmda()
    snap = st_arc["snapshot_utc"]
    last_full_day = (local_midnight(snap) - pd.Timedelta(days=1)).date()

    # --- cleaning --------------------------------------------------------------------
    imputed = official[official.imputed_end]
    official = official[~official.imputed_end]
    # only imputed rows inside the period where a city actually uses the official CSV matter
    uses_official = [k for k, c in CITIES.items() if not c.kyiv_kmda]
    imputed = imputed[imputed.city.isin(uses_official)
                      & (imputed.started_at < OFFICIAL_TO_ARCHIVE_CUT.tz_convert("UTC"))]
    # channel outages: an alert open when the channel went silent has an unknown end -> cut it
    # at the outage start; nothing was published during the outage
    n_cut = 0
    for lo, hi in OFFICIAL_OUTAGES:
        running = (official.started_at < lo) & (official.finished_at > lo)
        n_cut += int(running.sum())
        official.loc[running, "finished_at"] = lo
        official = official[~((official.started_at >= lo) & (official.started_at < hi))]
    ongoing = archive.finished_at.isna()
    archive.loc[ongoing, "finished_at"] = snap  # truncated at the snapshot; that day is excluded

    seg = segments(official, archive, kmda, snap)
    records, daily = [], []
    for key, parts in seg.items():
        recs = []
        for name, df, lo, hi in parts:
            r = clip(df.drop(columns="imputed_end"), lo, hi)
            r["segment"] = name
            recs.append(r)
        recs = pd.concat(recs, ignore_index=True).sort_values("started_at")
        records.append(recs)
        daily.append(daily_table(key, recs, imputed[imputed.city == key], parts, last_full_day))
    records = pd.concat(records, ignore_index=True)
    daily = pd.concat(daily, ignore_index=True)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    records.to_csv(PROCESSED / "city_records.csv", index=False)
    daily.to_csv(PROCESSED / "daily.csv", index=False)
    export_daily(daily)

    checks = cross_checks(official, archive, kmda)
    checks["imputed_sensitivity"] = imputed_sensitivity(records, imputed, daily)
    checks["official_outages"] = {"windows_utc": [f"{a} .. {b}" for a, b in OFFICIAL_OUTAGES],
                                  "records_cut_at_outage_start": n_cut,
                                  "missing_city_days": daily[daily.missing].groupby("city").size().to_dict()}
    write_report(daily, records, imputed, ongoing.sum(), st_off, st_arc, st_kmda, checks, seg, last_full_day)
    return daily, records, checks


def export_daily(daily):
    """Committed copy of the daily target table (rounded to 0.001 h = 3.6 s)."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    cols = ["city", "date", "hours", "hours_yellow", "hours_red", "hours_none", "n_episodes",
            "day_len_h", "source", "long_alert", "missing"]
    daily[cols].round(3).to_csv(RESULTS / "daily_target.csv", index=False)


def load_processed():
    """Typed city_records and daily tables from data/processed (run build() first)."""
    records = pd.read_csv(PROCESSED / "city_records.csv")
    for c in ("started_at", "finished_at"):
        records[c] = pd.to_datetime(records[c], utc=True, format="mixed")
    daily = pd.read_csv(PROCESSED / "daily.csv")
    daily["date"] = pd.to_datetime(daily.date).dt.date
    return records, daily


def daily_table(key, recs, imputed, parts, last_full_day):
    first, last = FIRST_DAY, last_full_day
    ms, me = iv.merge(recs.started_at, recs.finished_at)
    out = pd.DataFrame({"hours": iv.hours_per_day(ms, me, first, last)})
    out["day_len_h"] = iv.day_lengths(first, last)
    for lvl, hrs in iv.level_hours_per_day(recs, first, last).items():  # red > yellow > none
        out[f"hours_{lvl}"] = hrs
    es, _ = iv.merge(recs.started_at, recs.finished_at, gap_s=EPISODE_GAP_S)
    out["n_episodes"] = iv.starts_per_day(es, first, last)
    # source used for each day (by the day's midnight)
    _, bounds = iv.day_bounds(first, last)
    out["source"] = None
    for name, _, lo, hi in parts:
        lo64 = np.datetime64("1970-01-01") if lo is None else lo.to_datetime64()
        hi64 = np.datetime64("2100-01-01") if hi is None else hi.to_datetime64()
        sel = (bounds[:-1] >= lo64) & (bounds[:-1] < hi64)
        out.loc[sel, "source"] = name
    # flags: no value is changed by a flag, flags are for the report and for later filtering
    long_rec = recs[(recs.finished_at - recs.started_at) > pd.Timedelta(hours=LONG_ALERT_H)]
    out["long_alert"] = iv.hours_per_day(*iv.merge(long_rec.started_at, long_rec.finished_at), first, last) > 0
    out["n_imputed_dropped"] = 0
    for s, e in zip(imputed.started_at, imputed.finished_at):
        d0, d1 = local_midnight(s).date(), local_midnight(e).date()
        out.loc[(out.index >= d0) & (out.index <= d1), "n_imputed_dropped"] += 1
    # days overlapping a documented outage of a source in use that day are missing
    out["missing"] = False
    for lo, hi in OFFICIAL_OUTAGES:
        used = out.source == "official"
        miss = used & (bounds[1:] > lo.to_datetime64()) & (bounds[:-1] < hi.to_datetime64())
        out.loc[miss, "missing"] = True
    nan_cols = ["hours", "hours_none", "hours_yellow", "hours_red", "n_episodes"]
    out[nan_cols] = out[nan_cols].astype(float)
    out.loc[out.missing, nan_cols] = np.nan
    out.insert(0, "city", key)
    return out.reset_index()


def imputed_sensitivity(records, imputed, daily):
    """How much the daily target would change if the imputed (start + 1 h) rows were kept."""
    out = {}
    for key, imp in imputed.groupby("city"):
        r = pd.concat([records[records.city == key], imp])
        d = daily[daily.city == key].set_index("date")
        alt = iv.hours_per_day(*iv.merge(r.started_at, r.finished_at), d.index.min(), d.index.max())
        diff = (alt - d.hours).abs()
        out[key] = {"days_changed": int((diff > 1e-9).sum()), "max_abs_diff_h": float(diff.max()),
                    "sum_abs_diff_h": float(diff.sum())}
    return out


def overlap_hours(df, lo, hi):
    d = clip(df, lo, hi)
    s, e = iv.merge(d.started_at, d.finished_at)
    return float(((e - s) / np.timedelta64(1, "s")).sum() / 3600)


def cross_checks(official, archive, kmda):
    """Agreement of sources where they overlap (numbers go to the report and the tests)."""
    res = {}
    k_off = official[official.city == "kyiv"]
    last_off_day = (local_midnight(OFFICIAL_COMPLETE_UNTIL) - pd.Timedelta(days=2)).date()
    a = iv.hours_per_day(*iv.merge(kmda.started_at, kmda.finished_at), FIRST_DAY, last_off_day)
    b = iv.hours_per_day(*iv.merge(k_off.started_at, k_off.finished_at), FIRST_DAY, last_off_day)
    for lo, hi in OFFICIAL_OUTAGES:  # days without official data are not a disagreement
        keep = [not (local_midnight(lo).date() <= d <= local_midnight(hi).date()) for d in a.index]
        a, b = a[keep], b[keep]
    res["kyiv_kmda_vs_official"] = {"days": len(a), "corr": a.corr(b), "mae_h": (a - b).abs().mean(),
                                    "days_absdiff_gt_0.1h": int(((a - b).abs() > 0.1).sum()),
                                    "period": f"{FIRST_DAY}..{last_off_day}"}
    lo_day = (local_midnight(ARCHIVE_COMPLETE_FROM) + pd.Timedelta(days=1)).date()
    hi_day = (local_midnight(kmda.started_at.max()) - pd.Timedelta(days=1)).date()
    k_arc = archive[archive.city == "kyiv"]
    a = iv.hours_per_day(*iv.merge(kmda.started_at, kmda.finished_at), lo_day, hi_day)
    b = iv.hours_per_day(*iv.merge(k_arc.started_at, k_arc.finished_at), lo_day, hi_day)
    res["kyiv_kmda_vs_archive"] = {"days": len(a), "corr": a.corr(b), "mae_h": (a - b).abs().mean(),
                                   "days_absdiff_gt_0.1h": int(((a - b).abs() > 0.1).sum()),
                                   "period": f"{lo_day}..{hi_day}"}
    lo, hi = ARCHIVE_COMPLETE_FROM, OFFICIAL_COMPLETE_UNTIL - pd.Timedelta(hours=1)
    for key in ("kharkiv", "dnipro", "lviv"):
        res[f"{key}_official_vs_archive_overlap"] = {
            "window_utc": f"{lo} .. {hi}",
            "official_h": overlap_hours(official[official.city == key], lo, hi),
            "archive_h": overlap_hours(archive[archive.city == key], lo, hi)}
    return res


def zero_runs(s):
    """Longest run of consecutive zero-hour days: (length, first_day)."""
    best, cur, start, best_start = 0, 0, None, None
    for d, v in s.items():
        if v == 0:
            cur += 1
            start = d if cur == 1 else start
            if cur > best:
                best, best_start = cur, start
        else:
            cur = 0
    return best, best_start


def write_report(daily, records, imputed, n_ongoing, st_off, st_arc, st_kmda, checks, seg, last_full_day):
    REPORTS.mkdir(parents=True, exist_ok=True)
    L = ["# Data quality report (generated by `airalerts/build.py`)", ""]
    L += ["## Sources", "",
          f"- official CSV: {st_off['rows_raw']} rows, {st_off['rows_exact_duplicates']} exact duplicate rows dropped",
          f"- alerts.in.ua archive: {st_arc['rows_raw']} rows ({st_arc['rows_not_air_raid']} not `air_raid`, dropped); "
          f"snapshot (latest timestamp) {st_arc['snapshot_utc']}; {n_ongoing} covering records still ongoing → truncated at snapshot",
          f"- KMDA: {st_kmda['rows_raw']} rows, uid contiguous: {st_kmda['uid_contiguous']}, "
          f"last start (local) {st_kmda['last_start_local']}, DST-ambiguous local times resolved: {st_kmda['dst_ambiguous_resolved']}",
          f"- last complete Kyiv-local day in the daily table: **{last_full_day}**", ""]
    L += ["## Stitching (source per city and period)", "", "| city | source | from (UTC) | until (UTC) |", "|---|---|---|---|"]
    for key, parts in seg.items():
        for name, _, lo, hi in parts:
            L.append(f"| {key} | {name} | {lo if lo is not None else 'start'} | {hi} |")
    L += ["", "## Cross-source agreement on overlaps", ""]
    for k, v in checks.items():
        L.append(f"- **{k}**: " + ", ".join(f"{a}={round(b, 4) if isinstance(b, float) else b}" for a, b in v.items()))
    L += ["", "## Per city", "", "| city | days | first | last | mean h/day | zero days | longest zero run | "
          "days with alert >24h | days with dropped imputed record | records |", "|---|---|---|---|---|---|---|---|---|---|"]
    for key, d in daily.groupby("city"):
        zr, zs = zero_runs(d.set_index("date").hours)
        L.append(f"| {key} | {len(d)} | {d.date.min()} | {d.date.max()} | {d.hours.mean():.2f} | {(d.hours == 0).sum()} | "
                 f"{zr} (from {zs}) | {int(d.long_alert.sum())} | {int((d.n_imputed_dropped > 0).sum())} | "
                 f"{(records.city == key).sum()} |")
    L += ["", "## Records with imputed end (start + 1 h) dropped", "",
          "| city | count | first | last |", "|---|---|---|---|"]
    for key, d in imputed.groupby("city"):
        L.append(f"| {key} | {len(d)} | {d.started_at.min()} | {d.started_at.max()} |")
    L += ["", "## Single records longer than 24 h (kept, flagged as `long_alert`)", "",
          "| city | unit | started (UTC) | finished (UTC) | hours |", "|---|---|---|---|---|"]
    r = records[(records.finished_at - records.started_at) > pd.Timedelta(hours=LONG_ALERT_H)]
    for _, x in r.sort_values("started_at").iterrows():
        L.append(f"| {x.city} | {x.unit} | {x.started_at} | {x.finished_at} | {(x.finished_at - x.started_at).total_seconds() / 3600:.1f} |")
    (REPORTS / "data_quality.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    daily, records, checks = build()
    print(json.dumps(checks, indent=1, default=str))
    print(daily.groupby("city").hours.describe())
