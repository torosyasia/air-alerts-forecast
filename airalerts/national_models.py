"""All-Ukraine forecast: one shared quantile regression for every oblast centre.

Same features as the main model (known at 00:00, features.history_at) plus a city effect
(one-hot intercept per city). The slopes are shared, so the new regime (since 27.08) gives
~22 times more training rows than a model of one city. Compared on validation with
per-city models of the same form and with the five baselines; the test is the last 14
complete days, as for the three studied cities. Rolling origin: the model for day D is fitted
on rows with date < D only (asserted), refitted every REFIT_DAYS days.
"""
import warnings
from multiprocessing import Pool

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .config import ALL_CITIES, PROCESSED, RESULTS
from .evaluate import baseline_forecasts, periods, score_table
from .features import feature_matrix
from .models import FEATURE_SETS, TAUS, days_between
from .national import load_national

COLS = FEATURE_SETS["with_midnight"]
CITY_KEYS = list(ALL_CITIES)
FRESH_W = 84            # the fresh window chosen on validation for the studied cities (D-18)
REFIT_DAYS = 1          # refit every day, as for the studied cities (training rows always < D)


def _features_one(city):
    records, daily = load_national()
    return feature_matrix(records[records.city == city], daily[daily.city == city], [city])


def build_features_all(processes=4):
    with Pool(processes) as pool:
        parts = pool.map(_features_one, CITY_KEYS)
    X = pd.concat(parts, ignore_index=True)
    X.to_csv(PROCESSED / "national_features.csv", index=False)
    return X


def load_features():
    X = pd.read_csv(PROCESSED / "national_features.csv")
    X["date"] = pd.to_datetime(X.date).dt.date
    return X


def design(df, cols, shared):
    """Feature matrix; for the shared model add one-hot city intercepts (first city = base)."""
    M = df[cols].to_numpy(float)
    if shared:
        D = (df.city.to_numpy()[:, None] == np.array(CITY_KEYS[1:])[None, :]).astype(float)
        M = np.hstack([M, D])
    return sm.add_constant(M, has_constant="add")


def fit(train, cols, shared):
    X = design(train, cols, shared)
    keep = X.std(axis=0) > 0
    keep[0] = True                                   # constant
    betas = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for tau in TAUS:
            b = np.zeros(X.shape[1])
            b[keep] = sm.QuantReg(train.y.to_numpy(float), X[:, keep]).fit(q=tau, max_iter=5000).params
            betas.append(b)
    return betas


def predict(betas, rows, cols, shared):
    X = design(rows, cols, shared)
    q = np.sort(np.column_stack([X @ b for b in betas]), axis=1)    # no quantile crossing
    return q


def rolling(X, daily, days, shared, window=None, name=None, cities=None):
    """Rolling-origin forecasts. shared=True: one model on all cities; False: one per city."""
    cap = daily.set_index(["city", "date"]).day_len_h
    groups = [None] if shared else (cities or CITY_KEYS)
    out = []
    for g in groups:
        xg = X if g is None else X[X.city == g]
        betas, fitted_on = None, None
        for D in days:
            if betas is None or (pd.Timestamp(D) - pd.Timestamp(fitted_on)).days >= REFIT_DAYS:
                train = xg[xg.date < D]
                if window:
                    train = train[train.date >= (pd.Timestamp(D) - pd.Timedelta(days=window)).date()]
                assert train.date.max() < D, "leakage: training row not before the forecast day"
                train = train.dropna(subset=COLS + ["y"])
                betas, fitted_on = fit(train, COLS, shared), D
            rows = xg[xg.date == D].dropna(subset=COLS)
            if cities is not None:
                rows = rows[rows.city.isin(cities)]
            if rows.empty:
                continue
            q = predict(betas, rows, COLS, shared)
            c = np.array([cap[(cc, D)] for cc in rows.city])
            q = np.clip(q, 0, c[:, None])
            out.append(pd.DataFrame({"city": rows.city.to_numpy(), "date": D, "method": name,
                                     "q10": q[:, 0], "q50": q[:, 1], "q90": q[:, 2], "y": rows.y.to_numpy()}))
    return pd.concat(out, ignore_index=True)


BASELINES = ("yesterday", "mean7", "median7", "same_weekday", "climatology28")
METHODS = {"qr_city": dict(shared=False), "qr_shared": dict(shared=True),
           f"qr_shared_fresh{FRESH_W}": dict(shared=True, window=FRESH_W)}
NAMES = {"qr_city": "окрема модель для кожного міста", "qr_shared": "спільна модель на всіх містах",
         f"qr_shared_fresh{FRESH_W}": f"спільна модель на останніх {FRESH_W} днях"}


def common(fc):
    """Keep city-days on which every method has a forecast (methods are scored on the same days)."""
    k = fc.groupby(["city", "date"]).method.nunique()
    keep = k[k == fc.method.nunique()].index
    return fc.set_index(["city", "date"]).loc[keep].reset_index()


def run():
    _, daily = load_national()
    X = load_features()
    per = periods(daily)
    val, test = days_between(*per["validation"]), days_between(*per["test"])
    fc = [rolling(X, daily, val + test, name=m, **kw) for m, kw in METHODS.items()]
    base = pd.concat([baseline_forecasts(daily[daily.city == c]).assign(city=c) for c in CITY_KEYS])
    base = base[base.date.isin(val + test) & base.method.isin(BASELINES)]
    fc = common(pd.concat(fc + [base[["city", "date", "method", "q10", "q50", "q90", "y"]]], ignore_index=True))
    fc.to_csv(PROCESSED / "national_forecasts.csv", index=False)
    rows = []
    for pname, days in (("validation", val), ("test", test)):
        f = fc[fc.date.isin(days)]
        rows.append(score_table(f).reset_index().assign(period=pname, city="pooled"))
        for c, g in f.groupby("city"):
            rows.append(score_table(g).reset_index().assign(period=pname, city=c))
    m = pd.concat(rows, ignore_index=True)
    m["kind"] = np.where(m.method.isin(BASELINES), "baseline", "model")
    main = select_main(m)                                       # validation only

    m["main"] = m.method == main
    m.round(4).to_csv(RESULTS / "national_metrics.csv", index=False)
    return m, main, per


def select_main(m):
    """Validation only: among the model variants whose pooled 80% coverage is plausible (its 95%
    Wilson CI contains 0.80), the lowest interval score; if none is, the lowest interval score.
    Rule written after seeing the first validation run (DECISIONS D-22)."""
    v = m[(m.period == "validation") & (m.city == "pooled") & (m.kind == "model")].set_index("method")
    ok = v[(v.cov_lo95 <= 0.8) & (v.cov_hi95 >= 0.8)]
    return (ok if len(ok) else v).interval_score.idxmin()


def city_table(m, main):
    """Test metrics per city: the main model vs the best simple baseline (best on the test)."""
    t = m[m.period == "test"]
    rows = []
    for c in CITY_KEYS:
        g = t[t.city == c].set_index("method")
        b = g[g.kind == "baseline"]
        r = g.loc[main]
        rows.append({"city": c, "n_days": int(r.n), "model_MAE_h": r.MAE, "model_IS": r.interval_score,
                     "model_coverage80": r.coverage80, "best_baseline_MAE_h": b.MAE.min(),
                     "best_baseline_by_MAE": b.MAE.idxmin(), "best_baseline_IS": b.interval_score.min(),
                     "model_beats_baseline_MAE": r.MAE < b.MAE.min(),
                     "model_beats_baseline_IS": r.interval_score < b.interval_score.min()})
    return pd.DataFrame(rows)


def forecast_next_day_all(main, ct):
    """Forecast for the day after the last complete day, every centre, with the main model."""
    from . import intervals as iv
    from .config import TZ
    from .features import features_at
    records, daily = load_national()
    X = load_features()
    D = (pd.Timestamp(daily.date.max()) + pd.Timedelta(days=1)).date()
    assert records.finished_at.max() >= pd.Timestamp(D).tz_localize(TZ).tz_convert("UTC")
    rows = []
    for c in CITY_KEYS:
        d = daily[daily.city == c]
        f = features_at(records[records.city == c], D, frozenset(d.date[d.hours.isna()]))
        f.update(city=c, date=D)
        rows.append(f)
    xD = pd.DataFrame(rows)
    kw = METHODS[main]
    cap = float(iv.day_lengths(D, D).iloc[0])
    train = X[X.date < D].dropna(subset=COLS + ["y"])
    if kw.get("window"):
        train = train[train.date >= (pd.Timestamp(D) - pd.Timedelta(days=kw["window"])).date()]
    if kw["shared"]:
        q = predict(fit(train, COLS, True), xD, COLS, True)
    else:
        q = np.vstack([predict(fit(train[train.city == c], COLS, False), xD[xD.city == c], COLS, False)
                       for c in CITY_KEYS])
    q = np.clip(q, 0, cap)
    out = xD[["city"]].copy()
    out["name"] = [ALL_CITIES[c].name_uk for c in CITY_KEYS]
    out["oblast"] = [ALL_CITIES[c].oblast_uk for c in CITY_KEYS]
    out["forecast_for"] = D
    out["q10_h"], out["q50_h"], out["q90_h"] = q[:, 0].round(1), q[:, 1].round(1), q[:, 2].round(1)
    out["alert_running_at_00"] = xD.active_t0.astype(bool).to_numpy()
    out["hours_yesterday"] = xD.h_lag1.round(1).to_numpy()
    out["model"] = main
    out = out.merge(ct[["city", "model_MAE_h", "model_coverage80", "best_baseline_MAE_h", "best_baseline_by_MAE"]]
                    .rename(columns={"model_MAE_h": "test_MAE_h", "model_coverage80": "test_coverage80",
                                     "best_baseline_MAE_h": "best_baseline_test_MAE_h",
                                     "best_baseline_by_MAE": "best_baseline"}), on="city")
    out["data_snapshot_utc"] = records.finished_at.max().strftime("%Y-%m-%d %H:%M")
    out.round(2).to_csv(RESULTS / "forecast_next_day_all.csv", index=False)
    return out
