"""Leak hunt: can information from after the forecast origin t0 = D 00:00 Kyiv reach a
forecast or its evaluation?  (Independent review; DECISIONS.md D-14.)

The existing tests in test_leakage.py perturb the *processed* records. They cannot see a
leak that happens earlier, inside build.py (source stitching, snapshot truncation, outage
cut, imputed-row drop, 'missing' flags). The main check here therefore rebuilds the whole
pipeline from raw sources truncated to what existed at t0 ("as-of" rebuild):

  - every raw record that starts at or after t0 is removed (all three sources);
  - a record running at t0 gets an arbitrary end (t0 + 1 s, or t0 + 60 days) - its true
    end is unknown at t0; in the alerts.in.ua archive it is left open (NaT), as the
    archive itself stores ongoing alerts, and the archive snapshot is t0 + 1 min;
  - the imputed-end flag is recomputed on the truncated data.

Features of D from the as-of rebuild must equal the features of D in the real pipeline.

Tests that document a REAL leak fail on the current code; tests that document a checked,
clean path pass. Only real records are used (DECISIONS.md D-01).
"""
import shutil
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import airalerts.build as B
from airalerts import sources as S
from airalerts.config import IMPUTED_DURATION_S, PROCESSED, RESULTS, TZ
from airalerts.features import FEATURES, features_at, origin
from airalerts.models import FEATURE_SETS

MODEL_FEATURES = FEATURE_SETS["with_midnight"]   # what the main model actually uses


# --- as-of rebuild -------------------------------------------------------------------
def _truncate(df, t0, running_end, keep_open=False):
    d = df[df.started_at < t0].copy()
    d["finished_at"] = d.finished_at.astype("datetime64[ns, UTC]")
    run = d.finished_at > t0
    d.loc[run, "finished_at"] = pd.NaT if keep_open else running_end
    return d


def build_as_of(t0, running_end, truncate_kmda=True):
    """Run build.build() on raw data as it existed at t0. Writes only to a temp dir."""
    orig = (B.load_official, B.load_archive, B.load_kmda, B.fetch_pinned, B.PROCESSED, B.REPORTS, B.RESULTS)

    def official(*_):
        d, st = S.load_official()
        d = _truncate(d, t0, running_end)
        d["imputed_end"] = (d.finished_at - d.started_at).dt.total_seconds() == IMPUTED_DURATION_S
        return d, st

    def archive(*_):
        d, st = S.load_archive()
        st["snapshot_utc"] = t0 + pd.Timedelta(minutes=1)
        return _truncate(d, t0, running_end, keep_open=True), st

    def kmda():
        d, st = S.load_kmda()
        return (_truncate(d, t0, running_end) if truncate_kmda else d), st

    tmp = Path(tempfile.mkdtemp(prefix="asof_"))
    B.load_official, B.load_archive, B.load_kmda, B.fetch_pinned = official, archive, kmda, (lambda: None)
    B.PROCESSED = B.REPORTS = B.RESULTS = tmp
    try:
        daily, records, _ = B.build()
    finally:
        (B.load_official, B.load_archive, B.load_kmda, B.fetch_pinned, B.PROCESSED, B.REPORTS, B.RESULTS) = orig
        shutil.rmtree(tmp, ignore_errors=True)
    return daily, records


def _features(daily, records, city, day):
    missing = frozenset(daily[(daily.city == city) & daily.hours.isna()].date)
    return features_at(records[records.city == city], day, missing)


def _diff(a, b, keys):
    out = {}
    for k in keys:
        x, y = a[k], b[k]
        if not (x == y or (np.isnan(x) and np.isnan(y))):
            out[k] = (x, y)
    return out


_cache = {}


def _asof(t0, end_kind, truncate_kmda=True):
    key = (t0, end_kind, truncate_kmda)
    if key not in _cache:
        end = t0 + (pd.Timedelta(seconds=1) if end_kind == "end+1s" else pd.Timedelta(days=60))
        _cache[key] = build_as_of(t0, end, truncate_kmda)
    return _cache[key]


# --- LEAK: the KMDA -> archive switch point is derived from the last KMDA record ---------
@pytest.mark.parametrize("day", [date(2026, 9, 10), date(2026, 10, 1)])   # validation, test
def test_kyiv_features_equal_as_of_rebuild(built, day):
    """FAILS (real leak, build.py:44). kmda_cut = local midnight of the *last* KMDA start
    (2026-10-04). Which source supplies Kyiv's days before D therefore depends on records
    that appear after t0: rebuilt from data as of t0 the cut is D-1 00:00, day D-1 comes from
    the alerts.in.ua archive, and the features of D change (levels, episode counts, even
    whether an alert is running at 00:00). For D = 2026-10-04 the cut position encodes
    whether y(D) > 0 (it is 10-04 only because KMDA has a record that starts on 10-04)."""
    daily, records, _ = built
    t0 = origin(day)
    a = _features(daily, records, "kyiv", day)
    d2, r2 = _asof(t0, "end+1s")
    b = _features(d2, r2, "kyiv", day)
    diff = _diff(a, b, MODEL_FEATURES)
    assert not diff, f"kyiv {day}: features used by the main model differ from the as-of rebuild: {diff}"


# --- clean: Kharkiv / Dnipro (fixed official->archive cut), Kyiv after the KMDA cut -------
@pytest.mark.parametrize("day,cities", [
    (date(2026, 9, 12), ("kharkiv", "dnipro")),          # validation, alert running at 00:00 in Kharkiv
    (date(2026, 10, 5), ("kyiv", "kharkiv", "dnipro")),  # test, after the KMDA cut
    (date(2026, 10, 9), ("kyiv", "kharkiv", "dnipro")),  # last test day
])
def test_features_equal_as_of_rebuild_clean_paths(built, day, cities):
    daily, records, _ = built
    t0 = origin(day)
    for end_kind in ("end+1s", "end+60d"):
        d2, r2 = _asof(t0, end_kind)
        for city in cities:
            diff = _diff(_features(daily, records, city, day), _features(d2, r2, city, day), FEATURES)
            assert not diff, (city, day, end_kind, diff)


@pytest.mark.parametrize("day", [date(2026, 8, 31), date(2026, 9, 3), date(2026, 9, 6)])
def test_outage_cut_and_missing_flags_use_nothing_after_t0(built, day):
    """Official-CSV era around the 29.08-02.09 channel outage: the cut 'at the outage start'
    and the 'missing' days must not depend on how the running alert (Kharkiv, 109.7 h) ended
    or on records after t0. KMDA is left untruncated here (only Kharkiv/Dnipro are checked;
    a KMDA cut before 2026-09-06 would trip build.py's own assertion)."""
    daily, records, _ = built
    t0 = origin(day)
    for end_kind in ("end+1s", "end+60d"):
        d2, r2 = _asof(t0, end_kind, truncate_kmda=False)
        for city in ("kharkiv", "dnipro"):
            diff = _diff(_features(daily, records, city, day), _features(d2, r2, city, day), FEATURES)
            assert not diff, (city, day, end_kind, diff)


def test_no_dropped_imputed_record_runs_at_a_kyiv_midnight():
    """Imputed-end rows (start + 1 h) are dropped using after-the-fact knowledge that no end
    was ever posted. That could hide an alert running at 00:00. Checked: none of them spans a
    Kyiv-local midnight, so active_t0 / active_elapsed_h are never affected."""
    off, _ = S.load_official()
    imp = off[off.imputed_end]
    s = imp.started_at.dt.tz_convert(TZ).dt.normalize()
    e = imp.finished_at.dt.tz_convert(TZ).dt.normalize()
    assert len(imp) > 0 and (s == e).all()


# --- clean: every lag in the committed feature table is a past target ----------------
def test_all_lags_are_past_targets_on_every_row(built):
    """test_leakage.py checks h_lag1 on ~30 sampled days; here all rows, all 7 lags, all
    cities (DST days and the source-switch days included), plus h_mean7."""
    daily, records, _ = built
    path = PROCESSED / "features.csv"
    if not path.exists():
        pytest.skip("run `python run_all.py` first (needs data/processed/features.csv)")
    X = pd.read_csv(path)
    X["date"] = pd.to_datetime(X.date).dt.date
    for city, g in X.groupby("city"):
        y = daily[daily.city == city].set_index("date").hours
        g = g.set_index("date")
        for k in range(1, 8):
            prev = y.reindex([(pd.Timestamp(d) - pd.Timedelta(days=k)).date() for d in g.index]).to_numpy()
            lag = g[f"h_lag{k}"].to_numpy()
            assert (np.isfinite(prev) == np.isfinite(lag)).all()
            ok = np.isfinite(prev)
            assert np.abs(prev[ok] - lag[ok]).max() < 1e-9, (city, k)
        m7 = y.shift(1).rolling(7, min_periods=1).mean().reindex(g.index)
        assert np.nanmax(np.abs(m7 - g.h_mean7)) < 1e-9, city
        for f in FEATURES:                                # no feature is the target itself
            assert not np.allclose(g[f].fillna(-1), g.y.fillna(-1)), (city, f)


# --- clean: model choice depends on validation only ----------------------------------
def test_main_model_choice_ignores_test_period():
    """forecast.select_main_model and the reported validation metrics must not change when
    every test-period outcome is replaced. (The full models.run() rerun with replaced test
    targets was also done by hand: W, the CQR rule, validation forecasts and metrics were
    identical.)"""
    from airalerts.evaluate import periods, score_table
    from airalerts.forecast import select_main_model
    from airalerts.models import days_between
    path = PROCESSED / "model_forecasts.csv"
    if not path.exists():
        pytest.skip("run `python run_all.py` first (needs data/processed/model_forecasts.csv)")
    fc = pd.read_csv(path)
    fc["date"] = pd.to_datetime(fc.date).dt.date
    _, daily = B.load_processed()
    per = periods(daily)
    val, test = set(days_between(*per["validation"])), set(days_between(*per["test"]))

    def metrics(f):
        rows = []
        for pname, days in (("validation", val), ("test", test)):
            s = f[f.date.isin(days)]
            t = score_table(s).reset_index().assign(period=pname, city="pooled", kind="model")
            rows.append(t)
        return pd.concat(rows, ignore_index=True)

    alt = fc.copy()
    rng = np.random.default_rng(11)
    t = alt.date.isin(test)
    alt.loc[t, "y"] = rng.uniform(0, 23, t.sum())
    m0, m1 = metrics(fc), metrics(alt)
    assert select_main_model(m0) == select_main_model(m1)
    v0, v1 = m0[m0.period == "validation"], m1[m1.period == "validation"]
    assert np.allclose(v0.select_dtypes("number"), v1.select_dtypes("number"), equal_nan=True)


# --- clean: the published next-day forecast ------------------------------------------
def test_next_day_forecast_ignores_records_after_t0(monkeypatch, tmp_path):
    """The published next-day forecast (since 12.10: the shared all-Ukraine model,
    national_models.forecast_next_day_all) for D = last day + 1 must not change when everything
    after t0 = D 00:00 is altered (future records re-timed, alerts running at t0 given another
    end). Adapted by Claude Code from the agent's original test of forecast.forecast_next_day,
    which now only reads the all-Ukraine output."""
    import airalerts.national_models as NM
    for f in ("national_features.csv", "national_records.csv"):
        if not (PROCESSED / f).exists():
            pytest.skip("run `python run_all.py` first")
    if not (RESULTS / "national_city_test.csv").exists():
        pytest.skip("run `python run_all.py` first")
    ct = pd.read_csv(RESULTS / "national_city_test.csv")
    main = NM.select_main(pd.read_csv(RESULTS / "national_metrics.csv"))
    monkeypatch.setattr(NM, "RESULTS", tmp_path)
    records, daily = NM.load_national()
    D = (pd.Timestamp(daily.date.max()) + pd.Timedelta(days=1)).date()
    t0 = origin(D)
    future = records.started_at >= t0
    running = (records.started_at < t0) & (records.finished_at > t0)
    cols = ["city", "q10_h", "q50_h", "q90_h", "alert_running_at_00", "hours_yesterday", "mean_last_7d", "model"]

    def run_with(rec):
        monkeypatch.setattr(NM, "load_national", lambda: (rec, daily))
        return NM.forecast_next_day_all(main, ct)[cols]

    base = run_with(records)
    p1 = records.copy()
    p1.loc[running, "finished_at"] = t0 + pd.Timedelta(seconds=1)
    p2 = records.copy()
    p2.loc[running, "finished_at"] = t0 + pd.Timedelta(days=30)
    p3 = records.copy()
    p3.loc[future, "started_at"] = records.started_at[future] + pd.Timedelta(hours=5)
    p3.loc[future, "finished_at"] = records.finished_at[future] + pd.Timedelta(hours=7)
    for name, p in (("running_end_+1s", p1), ("running_never_end", p2), ("future_retimed", p3)):
        pd.testing.assert_frame_equal(base, run_with(p), obj=name)


# --- bug, not a leak: an alert running across a source switch loses 'active at 00:00' ---
@pytest.mark.xfail(strict=True, reason="BUG (not leakage): clip() at a source switch splits an alert "
                                       "running at the switch midnight; history_at then sees no "
                                       "running alert. Kharkiv 2026-09-07: active_t0 = 0, should be 1.")
def test_alert_running_across_source_switch_is_active_at_t0(built):
    _, records, _ = built
    f = features_at(records[records.city == "kharkiv"], date(2026, 9, 7))
    assert f["active_t0"] == 1.0
