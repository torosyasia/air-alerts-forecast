"""CP5: regime change in Kyiv and controls (DECISIONS.md D-19).

Bayesian single change point. The daily series x_1..x_n (window W) has one unknown
change day tau: x_t ~ N(mu_1, s_1^2) for t < tau and N(mu_2, s_2^2) for t >= tau. Each
segment gets a conjugate Normal-Inverse-Gamma prior, so the marginal likelihood of a
segment is closed-form and the posterior over tau is exact on the grid of days:
  P(tau | x) ∝ p(x_1..x_{tau-1}) * p(x_tau..x_n)   (uniform prior over tau).
Series: sqrt(hours) and sqrt(episodes) per day (square root stabilises the variance of
counts/durations).
"""
import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import gammaln

from . import intervals as iv
from .config import EPISODE_GAP_S, TZ

WINDOW = (pd.Timestamp("2026-06-01").date(), None)      # None -> last complete day
SENSITIVITY_STARTS = ("2026-05-01", "2026-07-01")
MIN_SEG = 7
REFORM_DAY = pd.Timestamp("2026-09-06").date()
HYP_DAY = pd.Timestamp("2026-08-27").date()              # Toros's refined hypothesis (D-15)


def log_marginal(x, m0, k0, a0, b0):
    n = len(x)
    xb = x.mean()
    kn, an = k0 + n, a0 + n / 2
    bn = b0 + 0.5 * ((x - xb) ** 2).sum() + k0 * n * (xb - m0) ** 2 / (2 * kn)
    return (gammaln(an) - gammaln(a0) + a0 * np.log(b0) - an * np.log(bn)
            + 0.5 * (np.log(k0) - np.log(kn)) - n / 2 * np.log(2 * np.pi))


def changepoint_posterior(x, dates):
    """Posterior over the first day of the new regime. Weak, data-scaled prior that does not
    favour any tau: m0 = mean(x), k0 = 0.01, a0 = 1, b0 = var(x)."""
    x = np.asarray(x, float)
    m0, k0, a0, b0 = x.mean(), 0.01, 1.0, max(x.var(), 1e-6)
    taus = range(MIN_SEG, len(x) - MIN_SEG + 1)
    lp = np.array([log_marginal(x[:t], m0, k0, a0, b0) + log_marginal(x[t:], m0, k0, a0, b0) for t in taus])
    p = np.exp(lp - lp.max())
    p /= p.sum()
    post = pd.Series(p, index=[dates[t] for t in taus], name="posterior")
    # Bayes factor "one change" vs "no change": p(x | M1) = mean over tau of p(x | tau)
    lm1 = lp.max() + np.log(np.exp(lp - lp.max()).mean())
    post.attrs["log10_bf"] = float((lm1 - log_marginal(x, m0, k0, a0, b0)) / np.log(10))
    return post


def summarize(post):
    order = post.sort_values(ascending=False)
    hpd = order[order.cumsum().shift(fill_value=0) < 0.95]       # smallest set with >= 95% mass
    return {"map": order.index[0], "p_map": float(order.iloc[0]),
            "hpd95_from": min(hpd.index), "hpd95_to": max(hpd.index), "hpd95_days": len(hpd),
            "p_before_reform": float(post[[d < REFORM_DAY for d in post.index]].sum()),
            "log10_BF_change_vs_none": post.attrs["log10_bf"]}


def detect(daily, cities=("kyiv", "kharkiv", "dnipro", "lviv"), start=WINDOW[0]):
    rows, posts = [], {}
    for city in cities:
        d = daily[(daily.city == city) & (daily.date >= start) & ~daily.missing].sort_values("date")
        for series, x in (("sqrt_hours", np.sqrt(d.hours)), ("sqrt_episodes", np.sqrt(d.n_episodes))):
            post = changepoint_posterior(x.to_numpy(), list(d.date))
            posts[(city, series)] = post
            s = summarize(post)
            tau = s["map"]
            before, after = d[d.date < tau], d[d.date >= tau]
            rows.append({"city": city, "series": series, "window_from": start, **s,
                         "hours_before": before.hours.mean(), "hours_after": after.hours.mean(),
                         "episodes_before": before.n_episodes.mean(), "episodes_after": after.n_episodes.mean()})
    return pd.DataFrame(rows), posts


# --- H1: count vs duration, spread over the day ---------------------------------------
def episodes(records, city, gap_s=EPISODE_GAP_S):
    r = records[records.city == city]
    s, e = iv.merge(r.started_at, r.finished_at, gap_s=gap_s)
    ep = pd.DataFrame({"start": pd.to_datetime(s, utc=True), "end": pd.to_datetime(e, utc=True)})
    ep["dur_h"] = (ep.end - ep.start).dt.total_seconds() / 3600
    loc = ep.start.dt.tz_convert(TZ)
    ep["date"], ep["hour"] = loc.dt.date, loc.dt.hour
    ep["block"] = pd.cut(ep.hour, [0, 6, 12, 18, 24], right=False, labels=["00-06", "06-12", "12-18", "18-24"])
    return ep


def compare_periods(daily, records, city, cut, before_days=60, last=None):
    """Before = [cut - before_days, cut), after = [cut, last]. Tests:
    Mann-Whitney U for daily counts/hours and episode durations, chi-square for start blocks."""
    d = daily[(daily.city == city) & ~daily.missing]   # missing days are left out, not zeroed
    last = last or d.date.max()
    b0 = (pd.Timestamp(cut) - pd.Timedelta(days=before_days)).date()
    db, da = d[(d.date >= b0) & (d.date < cut)], d[(d.date >= cut) & (d.date <= last)]
    ep = episodes(records, city)
    eb, ea = ep[(ep.date >= b0) & (ep.date < cut)], ep[(ep.date >= cut) & (ep.date <= last)]
    blocks = pd.crosstab(pd.concat([eb.assign(p="before"), ea.assign(p="after")]).p,
                         pd.concat([eb, ea]).block).reindex(["before", "after"])
    chi2, p_blocks, _, _ = stats.chi2_contingency(blocks)

    def spread(e, days):
        k = e.groupby("date").block.nunique().reindex(days, fill_value=0)
        return k.mean(), (k >= 3).mean()
    sb, sa = spread(eb, db.date), spread(ea, da.date)
    mw = lambda a, b: stats.mannwhitneyu(a, b, alternative="two-sided").pvalue
    return {
        "city": city, "cut": cut, "before": f"{b0}..{(pd.Timestamp(cut) - pd.Timedelta(days=1)).date()}",
        "after": f"{cut}..{last}", "days_before": len(db), "days_after": len(da),
        "hours_day_before": db.hours.mean(), "hours_day_after": da.hours.mean(), "p_hours": mw(db.hours, da.hours),
        "episodes_day_before": db.n_episodes.mean(), "episodes_day_after": da.n_episodes.mean(),
        "p_episodes": mw(db.n_episodes, da.n_episodes),
        "episode_median_h_before": eb.dur_h.median(), "episode_median_h_after": ea.dur_h.median(),
        "episode_mean_h_before": eb.dur_h.mean(), "episode_mean_h_after": ea.dur_h.mean(),
        "p_duration": mw(eb.dur_h, ea.dur_h),
        "blocks_before": (blocks.loc["before"] / blocks.loc["before"].sum()).round(3).to_dict(),
        "blocks_after": (blocks.loc["after"] / blocks.loc["after"].sum()).round(3).to_dict(),
        "p_blocks_chi2": p_blocks,
        "blocks_per_day_before": sb[0], "blocks_per_day_after": sa[0],
        "share_days_3plus_blocks_before": sb[1], "share_days_3plus_blocks_after": sa[1],
    }


# --- H2: levels and causes after the reform -------------------------------------------
def levels_after_reform(daily, records):
    rows = []
    for city in ("kyiv", "kharkiv", "dnipro", "lviv"):
        d = daily[(daily.city == city) & (daily.date >= REFORM_DAY)]
        tot = d.hours.sum()
        rows.append({"city": city, "days": len(d), "hours": tot,
                     "share_yellow": d.hours_yellow.sum() / tot if tot else np.nan,
                     "share_red": d.hours_red.sum() / tot if tot else np.nan,
                     "yellow_red_ratio": d.hours_yellow.sum() / d.hours_red.sum() if d.hours_red.sum() else np.nan})
    lv = pd.DataFrame(rows)
    k = records[(records.city == "kyiv") & (records.segment == "kmda") & records.cause.notna()].copy()
    k["h"] = (k.finished_at - k.started_at).dt.total_seconds() / 3600
    causes = k.groupby(["level", "cause"]).agg(records=("h", "size"), hours=("h", "sum")).reset_index()
    causes["share_records"] = causes.records / causes.records.sum()
    causes["share_hours"] = causes.hours / causes.hours.sum()
    pre = records[(records.city == "kyiv") & (records.segment == "kmda") & (records.started_at < pd.Timestamp("2026-09-06 03:00", tz="UTC"))]
    cause_pre = {"records_before_reform": len(pre), "with_cause": int(pre.cause.notna().sum()),
                 "kmda_cause_period": f"{k.started_at.min()} .. {k.started_at.max()}"}
    return lv, causes, cause_pre


# --- report ---------------------------------------------------------------------------
def fmt(v):
    if isinstance(v, float):
        return f"{v:.3g}" if abs(v) < 0.01 and v != 0 else f"{v:.2f}"
    return str(v)


def run_report():
    from .build import load_processed
    from .config import REPORTS, RESULTS
    records, daily = load_processed()
    cp, posts = detect(daily)
    sens = pd.concat([detect(daily, cities=("kyiv",), start=pd.Timestamp(s).date())[0] for s in SENSITIVITY_STARTS])
    RESULTS.mkdir(exist_ok=True)
    cp.round(4).to_csv(RESULTS / "changepoints.csv", index=False)
    post = pd.concat({f"{c}|{s}": p for (c, s), p in posts.items()}, axis=1)
    post.index.name = "tau"
    post.round(6).to_csv(RESULTS / "changepoint_posteriors.csv")
    comp = [compare_periods(daily, records, c, HYP_DAY) for c in ("kyiv", "kharkiv", "dnipro", "lviv")]
    lv, causes, cause_pre = levels_after_reform(daily, records)

    L = ["# CP5: regime change (generated by `airalerts/regimes.py`)", "",
         "## 1. Bayesian single change point (window 2026-06-01 .. last complete day)", "",
         "Series per day: sqrt(hours) and sqrt(episodes). Posterior over the first day of the new regime",
         "(uniform prior over days, Normal-Inverse-Gamma segments). HPD95 = smallest set of days holding",
         "95% of the posterior (range shown). log10 BF > 2: decisive evidence for one change vs none;",
         "around 0: the data cannot tell. Missing days (D-06a) are left out.", "",
         "| city | series | MAP day | P(MAP) | HPD95 from | HPD95 to | days in HPD95 | P(change before 06.09) | log10 BF | mean h/day before → after | episodes/day before → after |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in cp.iterrows():
        L.append(f"| {r.city} | {r.series} | {r['map']} | {r.p_map:.2f} | {r.hpd95_from} | {r.hpd95_to} | {r.hpd95_days} | "
                 f"{r.p_before_reform:.3f} | {r.log10_BF_change_vs_none:.1f} | {r.hours_before:.2f} → {r.hours_after:.2f} | "
                 f"{r.episodes_before:.2f} → {r.episodes_after:.2f} |")
    L += ["", "Sensitivity of the Kyiv break to the window start:", "",
          "| window from | series | MAP | HPD95 | P(before 06.09) |", "|---|---|---|---|---|"]
    for _, r in sens.iterrows():
        L.append(f"| {r.window_from} | {r.series} | {r['map']} | {r.hpd95_from} .. {r.hpd95_to} | {r.p_before_reform:.3f} |")
    L += ["", f"## 2. Before / after {HYP_DAY} (60 days before vs all days after; Mann-Whitney U, chi-square)", ""]
    keys = [k for k in comp[0] if k != "city"]
    L += ["| | " + " | ".join(c["city"] for c in comp) + " |", "|---|" + "---|" * len(comp)]
    for k in keys:
        L.append(f"| {k} | " + " | ".join(fmt(c[k]) for c in comp) + " |")
    L += ["", "## 3. Levels after the reform (06.09 .. last complete day; overlaps counted as red)", "",
          lv.round(3).to_markdown(index=False), "",
          "Kyiv KMDA `cause` (KMDA segment of the data):", "", causes.round(3).to_markdown(index=False), "",
          f"Before the reform: {cause_pre['records_before_reform']} KMDA records, with a cause: {cause_pre['with_cause']}.",
          f"KMDA records with a cause: {cause_pre['kmda_cause_period']}.", ""]
    (REPORTS / "regimes.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return cp, comp, lv, causes


if __name__ == "__main__":
    run_report()
