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
        d = daily[(daily.city == city) & (daily.date >= start)].sort_values("date")
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
    d = daily[daily.city == city]
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
