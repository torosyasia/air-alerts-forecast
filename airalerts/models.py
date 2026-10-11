"""CP4: linear quantile regression, trained on the whole history vs a fresh window.

Quantile regression fits q_tau(y | x) = x' beta_tau by minimising the pinball loss, one
model per tau in {0.1, 0.5, 0.9}. Unlike least squares it predicts the interval directly
and lets the width depend on the features (e.g. an alert running at midnight).

Rolling origin as for the baselines: for every evaluated day D the model is refitted on
rows with date < D (whole history, or only the last W days), then predicts D.
"""
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .evaluate import (ALPHA, FORECAST_CITIES, baseline_forecasts, block_bootstrap_diff,
                       interval_score, periods, score_table)

TAUS = (ALPHA / 2, 0.5, 1 - ALPHA / 2)
BASE = ["h_lag1", "h_mean7", "h_mean28", "ep_mean7", "h_last6h", "weekend"]
MIDNIGHT = ["active_t0", "active_elapsed_h"]
FEATURE_SETS = {
    "with_midnight": BASE + MIDNIGHT,                                   # main model
    "no_midnight": BASE,                                                # ablation asked for
    "no_midnight_no_last6h": [c for c in BASE if c != "h_last6h"],      # stricter ablation
}
FRESH_WINDOWS = (28, 42, 56, 84)  # chosen on validation only
N_CONF = 28                       # past out-of-sample days used by the conformal correction


def fit_predict(train, x_new, cols):
    """Three quantile regressions on `train`, prediction for one row. Constant columns in
    the training window are dropped (decided on the training rows only)."""
    use = [c for c in cols if train[c].nunique() > 1]
    X = sm.add_constant(train[use].to_numpy(float), has_constant="add")
    xn = np.r_[1.0, x_new[use].to_numpy(float)]
    out = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for tau in TAUS:
            beta = sm.QuantReg(train["y"].to_numpy(float), X).fit(q=tau, max_iter=5000).params
            out.append(float(xn @ beta))
    return sorted(out)  # no quantile crossing


def rolling_forecasts(X, daily, days, cols, window=None, name=None):
    """Forecast every day in `days` for every city, refitting on rows with date < D."""
    cap = daily.set_index(["city", "date"]).day_len_h
    rows = []
    for city in FORECAST_CITIES:
        xc = X[X.city == city].set_index("date").sort_index()
        for D in days:
            train = xc[xc.index < D]
            if window:
                train = train[train.index >= (pd.Timestamp(D) - pd.Timedelta(days=window)).date()]
            assert train.index.max() < D, "leakage: training row not before the forecast day"
            q = np.clip(fit_predict(train, xc.loc[D], cols), 0, cap[(city, D)])
            rows.append({"city": city, "date": D, "method": name, "q10": q[0], "q50": q[1], "q90": q[2],
                         "y": xc.loc[D, "y"], "active_t0": xc.loc[D, "active_t0"], "cap": cap[(city, D)]})
    return pd.DataFrame(rows)


def days_between(a, b):
    return list(pd.date_range(a, b, freq="D").date)


def conformalize(f, n=N_CONF, alpha=ALPHA):
    """Conformalized quantile regression (CQR), rolling.

    For day D take the model's own out-of-sample forecasts of the previous n days and their
    conformity scores s = max(q10 - y, y - q90) (how far y fell outside the interval;
    negative if inside). Q = the k-th smallest score, k = ceil((n + 1)(1 - alpha)). The
    corrected interval is [q10 - Q, q90 + Q]: widened if the model under-covered, narrowed
    if it over-covered. Uses only days before D.
    """
    out = []
    k = int(np.ceil((n + 1) * (1 - alpha)))
    for city, g in f.groupby("city"):
        g = g.sort_values("date").reset_index(drop=True)
        s = np.maximum(g.q10 - g.y, g.y - g.q90).to_numpy()
        for i in range(n, len(g)):
            assert g.date[i - 1] < g.date[i]
            Q = np.sort(s[i - n:i])[k - 1]
            r = g.loc[i].copy()
            r["q10"], r["q90"] = max(r.q10 - Q, 0.0), min(r.q90 + Q, r.cap)
            r["q10"] = min(r.q10, r.q90)
            r["method"] = f"{r.method}+cqr"
            out.append(r)
    return pd.DataFrame(out)


def needs_conformal(f_val):
    """Pre-stated rule (DECISIONS D-18): calibrate a variant if the upper end of the 95% Wilson
    CI of its pooled validation coverage is below the nominal 0.80."""
    t = score_table(f_val)
    return t.cov_hi95.iloc[0] < 1 - ALPHA


def run(X, daily):
    per = periods(daily)
    val, test = days_between(*per["validation"]), days_between(*per["test"])
    allv = val + test
    warm = days_between(pd.Timestamp(per["validation"][0]) - pd.Timedelta(days=N_CONF),
                        pd.Timestamp(per["validation"][0]) - pd.Timedelta(days=1))

    # 1) fresh-window length: validation only, main feature set
    cand = {W: rolling_forecasts(X, daily, val, FEATURE_SETS["with_midnight"], W, f"qr_fresh{W}")
            for W in FRESH_WINDOWS}
    val_scores = pd.DataFrame({W: score_table(f).iloc[0] for W, f in cand.items()}).T
    W_best = int(val_scores.interval_score.idxmin())

    # 2) final variants; the N_CONF warm-up days before validation feed the conformal step only
    fc = []
    for fs, cols in FEATURE_SETS.items():
        for window, name in ((None, f"qr_full__{fs}"), (W_best, f"qr_fresh{W_best}__{fs}")):
            f = rolling_forecasts(X, daily, warm + allv, cols, window, name)
            fc.append(f[f.date.isin(allv)])
            if needs_conformal(f[f.date.isin(val)]):
                c = conformalize(f)
                fc.append(c[c.date.isin(allv)])
    fc = pd.concat(fc, ignore_index=True)

    base = pd.concat([baseline_forecasts(daily[daily.city == c]).assign(city=c) for c in FORECAST_CITIES])
    base = base[base.date.isin(allv)]
    return fc, base, val_scores, W_best, per


def compare(fc, base, days):
    """Score tables and the 'beats the best baseline' verdict on the given days."""
    f = fc[fc.date.isin(days)]
    b = base[base.date.isin(days)]
    res = {}
    for city in FORECAST_CITIES + ("pooled",):
        sel_f = f if city == "pooled" else f[f.city == city]
        sel_b = b if city == "pooled" else b[b.city == city]
        tb, tm = score_table(sel_b), score_table(sel_f)
        tm["beats_MAE"] = tm.MAE < tb.MAE.min()
        tm["beats_IS"] = tm.interval_score < tb.interval_score.min()
        res[city] = (tb, tm)
    return res


LOSSES = {"MAE": lambda g: (g.y - g.q50).abs().to_numpy(),
          "interval_score": lambda g: interval_score(g.y, g.q10, g.q90).to_numpy()}


def paired_diff(fa, fb, days, metric, block=3, n_boot=5000, seed=0):
    """mean(loss_a - loss_b) over cities and days with a 95% block-bootstrap CI.
    Blocks of consecutive days are resampled within each city (stratified)."""
    rng = np.random.default_rng(seed)
    diffs = []
    for city in FORECAST_CITIES:
        a = fa[(fa.city == city) & fa.date.isin(days)].sort_values("date")
        b = fb[(fb.city == city) & fb.date.isin(days)].sort_values("date")
        assert list(a.date) == list(b.date)
        diffs.append(LOSSES[metric](a) - LOSSES[metric](b))
    boots = np.zeros(n_boot)
    for d in diffs:
        n = len(d)
        starts = rng.integers(0, n - block + 1, size=(n_boot, int(np.ceil(n / block))))
        idx = (starts[:, :, None] + np.arange(block)).reshape(n_boot, -1)[:, :n]
        boots += d[idx].sum(axis=1)
    total = sum(len(d) for d in diffs)
    m = float(np.concatenate(diffs).mean())
    return m, float(np.quantile(boots / total, 0.025)), float(np.quantile(boots / total, 0.975))


def bootstrap_vs_best(fc, base, days, method, metric):
    """Block-bootstrap CI of mean(loss_model - loss_best_baseline), best baseline by `metric`
    on these days; stratified by city (blocks resampled within each city)."""
    loss = {"MAE": lambda g: (g.y - g.q50).abs(),
            "interval_score": lambda g: interval_score(g.y, g.q10, g.q90)}[metric]
    b = base[base.date.isin(days)]
    best = score_table(b)[metric if metric != "MAE" else "MAE"].idxmin()
    out = {}
    for city in FORECAST_CITIES:
        m = fc[(fc.method == method) & (fc.city == city) & fc.date.isin(days)].set_index("date").sort_index()
        bb = b[(b.method == best) & (b.city == city)].set_index("date").sort_index()
        out[city] = block_bootstrap_diff(loss(m).to_numpy(), loss(bb).to_numpy())
    return best, out


def write_report(fc, base, val_scores, W_best, per, path):
    val, test = days_between(*per["validation"]), days_between(*per["test"])
    L = ["# CP4: quantile regression vs baselines (generated by `airalerts/models.py`)", "",
         "Linear quantile regression (q10, q50, q90), refitted every day on rows dated before D:",
         "`qr_full` on the whole history (from 2022-04), `qr_freshW` on the last W days.",
         "Feature sets: `with_midnight` = " + ", ".join(FEATURE_SETS["with_midnight"]) + ";",
         "`no_midnight` drops active_t0 and active_elapsed_h; `no_midnight_no_last6h` also drops h_last6h.",
         "`+cqr` = conformalized quantile regression (added only where the pre-stated rule asks for it).", "",
         "## 1. Fresh-window length (validation only, feature set with_midnight)", "",
         val_scores[["MAE", "coverage80", "width", "interval_score"]].round(3).to_markdown(), "",
         f"Chosen W = {W_best} (lowest validation interval score).", ""]
    for nm, days in (("validation", val), ("test", test)):
        r = compare(fc, base, days)
        L += [f"## 2. {nm}: {days[0]} .. {days[-1]}", ""]
        for city, (tb, tm) in r.items():
            L += [f"### {city}", "", "Baselines:", "",
                  tb[["MAE", "coverage80", "cov_lo95", "cov_hi95", "width", "interval_score"]].round(2).to_markdown(), "",
                  "Models (beats_* = better than the best of the 5 baselines on this metric):", "",
                  tm[["MAE", "coverage80", "cov_lo95", "cov_hi95", "width", "interval_score", "beats_MAE", "beats_IS"]]
                  .round(2).to_markdown(), ""]
    L += ["## 3. Does 'alert running at 00:00 and for how long' help?", "",
          "Mean paired difference of daily losses (negative = the first model is better), all 3 cities,",
          "with a 95% block-bootstrap CI (blocks of 3 days within each city, 5000 resamples).", "",
          "| comparison | period | metric | mean diff | 95% CI |", "|---|---|---|---|---|"]
    pairs = [("qr_full__with_midnight", "qr_full__no_midnight"),
             ("qr_full__no_midnight", "qr_full__no_midnight_no_last6h")]
    for a, b in pairs:
        for nm, days in (("validation", val), ("test", test)):
            for metric in ("MAE", "interval_score"):
                m, lo, hi = paired_diff(fc[fc.method == a], fc[fc.method == b], days, metric)
                L.append(f"| {a} − {b} | {nm} | {metric} | {m:+.2f} | [{lo:+.2f}, {hi:+.2f}] |")
    L += ["", "## 4. Main model vs the best baseline on the test (per metric)", "",
          "| model | metric | best baseline | mean diff (model − baseline) | 95% CI |", "|---|---|---|---|---|"]
    tb_test = score_table(base[base.date.isin(test)])
    for mth in sorted(fc.method.unique()):
        for metric in ("MAE", "interval_score"):
            best = tb_test[metric].idxmin()
            m, lo, hi = paired_diff(fc[fc.method == mth], base[base.method == best], test, metric)
            L.append(f"| {mth} | {metric} | {best} | {m:+.2f} | [{lo:+.2f}, {hi:+.2f}] |")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    from .build import load_processed
    from .config import PROCESSED, REPORTS
    _, daily = load_processed()
    X = pd.read_csv(PROCESSED / "features.csv")
    X["date"] = pd.to_datetime(X.date).dt.date
    fc, base, val_scores, W_best, per = run(X, daily)
    fc.to_csv(PROCESSED / "model_forecasts.csv", index=False)
    write_report(fc, base, val_scores, W_best, per, REPORTS / "models.md")
    export_test_metrics(fc, base, per)
    return fc, base, val_scores, W_best, per


def export_test_metrics(fc, base, per):
    """Small committed table: validation and test metrics of every baseline and model."""
    from .config import RESULTS
    rows = []
    for pname in ("validation", "test"):
        days = days_between(*per[pname])
        for city in FORECAST_CITIES + ("pooled",):
            for kind, src in (("baseline", base), ("model", fc)):
                s = src[src.date.isin(days)]
                s = s if city == "pooled" else s[s.city == city]
                t = score_table(s).reset_index()
                t.insert(0, "kind", kind)
                t.insert(0, "city", city)
                t.insert(0, "period", pname)
                rows.append(t)
    out = pd.concat(rows, ignore_index=True).drop(columns=["relMAE"], errors="ignore")
    RESULTS.mkdir(exist_ok=True)
    out.round(4).to_csv(RESULTS / "metrics_validation_test.csv", index=False)


if __name__ == "__main__":
    main()
