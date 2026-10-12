"""Parse each raw source into one record schema, restricted to units that cover a city.

Schema: source, city, unit_type, unit, level ('none' | 'yellow' | 'red'), cause,
        started_at (UTC), finished_at (UTC, NaT while ongoing), record_id.

A city counts as "under alert" when an alert is declared for a unit that contains it:
the oblast, the raion containing the city, or the city's hromada / city unit.
Alerts declared for other raions of the same oblast do not count.
"""
import json

import numpy as np
import pandas as pd

from .config import CITIES, IMPUTED_DURATION_S, TZ, source_path

COLUMNS = ["source", "city", "unit_type", "unit", "level", "cause",
           "started_at", "finished_at", "record_id"]


def _covers(df, city, oblast_col, level_col, raion_col, hromada_col):
    in_oblast = df[oblast_col] == city.oblast_uk
    m = in_oblast & (df[level_col] == "oblast")
    if city.raion_uk:
        m |= in_oblast & (df[level_col] == "raion") & (df[raion_col] == city.raion_uk)
    if city.hromada_prefix:
        m |= in_oblast & (df[level_col] == "hromada") & df[hromada_col].fillna("").str.startswith(city.hromada_prefix)
    return m


def load_official(cities=None):
    """Official channel CSV (UTC). Exact duplicate rows are dropped; rows whose end was
    imputed by the upstream parser (duration exactly 1 h) are flagged, not yet dropped."""
    raw = pd.read_csv(source_path("official"))
    n_raw = len(raw)
    raw = raw.drop_duplicates()
    stats = {"rows_raw": n_raw, "rows_exact_duplicates": n_raw - len(raw)}
    for c in ("started_at", "finished_at"):
        raw[c] = pd.to_datetime(raw[c], utc=True, format="mixed")
    parts = []
    for city in (cities or CITIES).values():
        m = _covers(raw, city, "oblast", "level", "raion", "hromada")
        d = raw[m]
        parts.append(pd.DataFrame({
            "source": "official", "city": city.key, "unit_type": d["level"],
            "unit": d["hromada"].fillna(d["raion"]).fillna(d["oblast"]),
            "level": "none", "cause": None,
            "started_at": d["started_at"], "finished_at": d["finished_at"],
            "record_id": d.index.astype(str),
        }))
    out = pd.concat(parts, ignore_index=True)
    dur = (out.finished_at - out.started_at).dt.total_seconds()
    out["imputed_end"] = dur == IMPUTED_DURATION_S
    return out, stats


def load_archive(cities=None):
    """alerts.in.ua archive (UTC), air_raid alerts only, with yellow/red level."""
    raw = pd.read_csv(source_path("alerts_in_ua"))
    stats = {"rows_raw": len(raw), "rows_not_air_raid": int((raw.alert_type != "air_raid").sum())}
    raw = raw[raw.alert_type == "air_raid"]
    for c in ("started_at", "finished_at"):
        raw[c] = pd.to_datetime(raw[c], utc=True, format="mixed")
    snapshot = max(raw.started_at.max(), raw.finished_at.max())
    parts = []
    for city in (cities or CITIES).values():
        d = raw[(raw.location_oblast == city.oblast_uk) & raw.location_title.isin(city.archive_titles)]
        parts.append(pd.DataFrame({
            "source": "alerts_in_ua", "city": city.key, "unit_type": d["location_type"],
            "unit": d["location_title"], "level": d["alert_level"].fillna("none"), "cause": None,
            "started_at": d["started_at"], "finished_at": d["finished_at"],
            "record_id": d["id"].astype(str),
        }))
    out = pd.concat(parts, ignore_index=True)
    out["imputed_end"] = False
    stats["snapshot_utc"] = snapshot
    return out, stats


def localize_kyiv(start_naive, end_naive):
    """Naive Kyiv local times -> UTC.

    Nonexistent times (spring-forward hour) are shifted forward. An ambiguous time
    (autumn fall-back hour, 03:00-04:00 occurs twice) is resolved as: start -> the first
    occurrence; end -> the earliest occurrence that is not before the start.
    Returns (start_utc, end_utc, n_ambiguous_resolved).
    """
    s = pd.to_datetime(start_naive)
    e = pd.to_datetime(end_naive)
    s_first = s.dt.tz_localize(TZ, ambiguous=np.ones(len(s), bool), nonexistent="shift_forward")
    e_first = e.dt.tz_localize(TZ, ambiguous=np.ones(len(e), bool), nonexistent="shift_forward")
    e_second = e.dt.tz_localize(TZ, ambiguous=np.zeros(len(e), bool), nonexistent="shift_forward")
    e_utc = e_first.where(e_first >= s_first, e_second)
    n_amb = int(s.dt.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward").isna().sum()
                + e.dt.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward").isna().sum())
    return s_first.dt.tz_convert("UTC"), e_utc.dt.tz_convert("UTC"), n_amb


def load_kmda():
    """KMDA open data for Kyiv City (naive local time, level and cause)."""
    raw = pd.DataFrame(json.loads(source_path("kmda").read_text(encoding="utf-8")))
    assert (raw.addressAdminUnitL2 == "місто Київ").all()
    assert (raw.type == "Повітряна тривога").all()
    s, e, n_amb = localize_kyiv(raw.dateTimeStart, raw.dateTimeEnd)
    level = raw.level.map({"null": "none", "Жовтий рівень": "yellow", "Червоний рівень": "red"})
    assert level.notna().all(), raw.level[level.isna()].unique()
    out = pd.DataFrame({
        "source": "kmda", "city": "kyiv", "unit_type": "city", "unit": "м. Київ",
        "level": level, "cause": raw.cause.where(raw.cause != "null"),
        "started_at": s, "finished_at": e, "record_id": raw.uid.astype(str),
    })
    out["imputed_end"] = False
    stats = {"rows_raw": len(raw), "dst_ambiguous_resolved": n_amb,
             "uid_contiguous": bool((raw.uid.astype(int).diff().dropna() == 1).all()),
             "last_start_local": raw.dateTimeStart.max()}
    return out, stats
