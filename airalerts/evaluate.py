"""Baselines, rolling-origin evaluation and metrics (DECISIONS.md D-11).

Rolling origin: for every evaluated day D the forecast is issued at D 00:00 using only
the target values of days before D; the origin then moves one day forward. Nothing is
shuffled, and nothing from D or later enters the forecast of D.

Every method returns three quantiles of y(D): q10, q50 (the point forecast) and q90.
[q10, q90] is the 80% interval.
"""
import numpy as np
import pandas as pd
from scipy import stats

from .config import REPORTS

N_RESID = 28            # days of past errors used to build baseline intervals (fixed a priori)
TEST_DAYS = 14
VALIDATION_FROM = pd.Timestamp("2026-09-08").date()
BACKTEST = (pd.Timestamp("2025-01-01").date(), pd.Timestamp("2026-08-26").date())
FORECAST_CITIES = ("kyiv", "kharkiv", "dnipro")
ALPHA = 0.2             # 1 - nominal coverage of the interval


def periods(daily):
    last = daily.date.max()
    test_from = (pd.Timestamp(last) - pd.Timedelta(days=TEST_DAYS - 1)).date()
    val_to = (pd.Timestamp(test_from) - pd.Timedelta(days=1)).date()
    return {"validation": (VALIDATION_FROM, val_to), "test": (test_from, last), "backtest_appendix": BACKTEST}


# --- baselines ------------------------------------------------------------------------
def _point_forecasts(y):
    """Point forecast for each day from the values strictly before it (shift >= 1)."""
    past = y.shift(1)
    return {
        "yesterday": past,
        "mean7": past.rolling(7).mean(),
        "median7": past.rolling(7).median(),
        "same_weekday": y.shift(7),
    }


def baseline_forecasts(daily_city):
    """All baselines for every day of one city. Columns: date, method, q10, q50, q90."""
    d = daily_city.sort_values("date").set_index("date")
    assert (np.diff(pd.to_datetime(d.index)) == np.timedelta64(1, "D")).all(), "days must be contiguous"
    y, cap = d.hours, d.day_len_h
    out = []
    for name, p in _point_forecasts(y).items():
        err = (y - p).shift(1)  # errors of days before D only
        lo = p + err.rolling(N_RESID).quantile(ALPHA / 2)
        hi = p + err.rolling(N_RESID).quantile(1 - ALPHA / 2)
        out.append(pd.DataFrame({"method": name, "q10": lo, "q50": p, "q90": hi}))
    past = y.shift(1)
    out.append(pd.DataFrame({"method": "climatology28",
                             "q10": past.rolling(N_RESID).quantile(ALPHA / 2),
                             "q50": past.rolling(N_RESID).quantile(0.5),
                             "q90": past.rolling(N_RESID).quantile(1 - ALPHA / 2)}))
    f = pd.concat(out)
    for q in ("q10", "q50", "q90"):  # hours are bounded by the length of the day
        f[q] = f[q].clip(lower=0, upper=cap.reindex(f.index))
    f["y"] = y.reindex(f.index)
    return f.reset_index().dropna()


# --- metrics --------------------------------------------------------------------------
def interval_score(y, lo, hi, alpha=ALPHA):
    """Winkler / interval score: width + 2/alpha * distance by which y falls outside."""
    return (hi - lo) + 2 / alpha * (lo - y) * (y < lo) + 2 / alpha * (y - hi) * (y > hi)


def pinball(y, q, tau):
    return np.maximum(tau * (y - q), (tau - 1) * (y - q))


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (c - h, c + h)


def score_table(f):
    """Per-method metrics on the forecasts in f (one row per day and method)."""
    rows = []
    for m, g in f.groupby("method", sort=False):
        covered = (g.y >= g.q10) & (g.y <= g.q90)
        lo, hi = wilson(int(covered.sum()), len(g))
        rows.append({
            "method": m, "n": len(g),
            "MAE": (g.y - g.q50).abs().mean(),
            "coverage80": covered.mean(), "cov_lo95": lo, "cov_hi95": hi,
            "width": (g.q90 - g.q10).mean(),
            "interval_score": interval_score(g.y, g.q10, g.q90).mean(),
            "pinball": np.mean([pinball(g.y, g[f"q{int(t * 100)}"], t).mean() for t in (0.1, 0.5, 0.9)]),
        })
    t = pd.DataFrame(rows).set_index("method")
    if "yesterday" in t.index:
        t.insert(2, "relMAE", t.MAE / t.loc["yesterday", "MAE"])
    return t


def block_bootstrap_diff(loss_a, loss_b, block=3, n_boot=5000, seed=0):
    """Paired moving-block bootstrap of mean(loss_a - loss_b) over consecutive days.

    Blocks of `block` consecutive days are resampled to keep day-to-day dependence.
    Returns (mean difference, 2.5% and 97.5% bootstrap quantiles).
    """
    d = np.asarray(loss_a) - np.asarray(loss_b)
    n = len(d)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(n_boot, int(np.ceil(n / block))))
    idx = (starts[:, :, None] + np.arange(block)).reshape(n_boot, -1)[:, :n]
    means = d[idx].mean(axis=1)
    return d.mean(), np.quantile(means, 0.025), np.quantile(means, 0.975)


# --- driver ---------------------------------------------------------------------------
def evaluate_baselines(daily):
    per = periods(daily)
    fc = pd.concat([baseline_forecasts(daily[daily.city == c]).assign(city=c) for c in FORECAST_CITIES])
    tables = {}
    for pname, (a, b) in per.items():
        sel = fc[(fc.date >= a) & (fc.date <= b)]
        for c in FORECAST_CITIES:
            tables[(pname, c)] = score_table(sel[sel.city == c])
        tables[(pname, "pooled")] = score_table(sel)
    return fc, tables, per


def write_report(tables, per, daily):
    L = ["# Baselines: rolling-origin evaluation (generated by `airalerts/evaluate.py`)", "",
         "Forecast for day D is issued at D 00:00 Kyiv from the target values of days before D.",
         "q50 is the point forecast, [q10, q90] the 80% interval. Point baselines get their interval",
         f"from the empirical 10%/90% quantiles of their own errors over the previous {N_RESID} days;",
         f"`climatology28` is the 10/50/90% quantiles of the previous {N_RESID} days.", "",
         "Metrics: MAE of q50; relMAE = MAE / MAE(yesterday) on the same days; coverage80 = share",
         "of days with q10 <= y <= q90 (95% Wilson CI); width = mean q90 - q10; interval_score =",
         "width + 10 x the distance by which y misses the interval (alpha = 0.2), lower is better;",
         "pinball = mean quantile loss over q10, q50, q90.", ""]
    for pname, (a, b) in per.items():
        L += [f"## {pname}: {a} .. {b}", ""]
        if pname == "backtest_appendix":
            L += ["Different regime (Kyiv ~1-2 h/day): calibration here does not transfer to the",
                  "autumn-2026 regime. Appendix only.", ""]
        for c in FORECAST_CITIES + ("pooled",):
            t = tables[(pname, c)]
            mean_y = daily[(daily.city == c) & (daily.date >= a) & (daily.date <= b)].hours.mean() if c != "pooled" else np.nan
            L += [f"### {c}" + (f" (mean y = {mean_y:.2f} h/day)" if c != "pooled" else " (3 cities together)"), "",
                  t.round(3).to_markdown(), ""]
    (REPORTS / "baselines.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    from .build import load_processed
    from .config import PROCESSED
    _, daily = load_processed()
    fc, tables, per = evaluate_baselines(daily)
    fc.to_csv(PROCESSED / "baseline_forecasts.csv", index=False)
    write_report(tables, per, daily)
    for k in [("validation", c) for c in FORECAST_CITIES] + [("test", c) for c in FORECAST_CITIES + ("pooled",)]:
        print(k, per[k[0]]); print(tables[k].round(3))
