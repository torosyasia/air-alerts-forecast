"""Devil's advocate checks of the main conclusions C1-C7 (README "Головні висновки", D-19..D-21).

Written by the devil's-advocate agent (agents/devils_advocate.md); committed unchanged except for
the import path and the raw file paths (taken from the pinned MANIFEST instead of hardcoded names).
Run from the repo root after run_all.py (needs data/processed/*):
    .venv/bin/python agents/devils_advocate_checks.py
Every block prints the numbers quoted in the review. Seeds are fixed.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from airalerts import intervals as iv
from airalerts.build import load_processed
from airalerts.config import ROOT, TZ, source_path
from airalerts.regimes import changepoint_posterior, summarize, episodes
from airalerts.sources import load_archive, load_official
from airalerts import events as EV

rng = np.random.default_rng(0)
R, D = load_processed()
CUT, REFORM = date(2026, 8, 27), date(2026, 9, 6)
B0 = CUT - timedelta(days=60)
EXTREME = [date(2026, 8, d) for d in (27, 28, 29, 30)]          # 13, 12, 10, 11 alerts
OUTAGE = [date(2026, 8, 29) + timedelta(days=i) for i in range(5)]
K = D[(D.city == "kyiv") & ~D.missing].set_index("date").sort_index()
LAST = K.index.max()
P = lambda *a: print(*a)


def cp(x, dates):
    s = summarize(changepoint_posterior(np.asarray(x, float), list(dates)))
    return f"MAP {s['map']} p={s['p_map']:.2f} HPD {s['hpd95_from']}..{s['hpd95_to']} BF10 {s['log10_BF_change_vs_none']:.1f}"


def daily_from(ep, days):
    """episodes per day (by start date) over a list of days."""
    n = ep.groupby("date").size().reindex(days, fill_value=0)
    return n


def ep_kyiv(gap_s=60, rec=None):
    rec = R if rec is None else rec
    return episodes(rec, "kyiv", gap_s=gap_s)


def decompose(ep, db, da):
    """share of ln(hours ratio) explained by count: ln(count ratio)/(ln count + ln mean-duration)."""
    eb, ea = ep[ep.date.isin(db)], ep[ep.date.isin(da)]
    rc = (len(ea) / len(da)) / (len(eb) / len(db))
    rd = ea.dur_h.mean() / eb.dur_h.mean()
    return rc, rd, np.log(rc) / (np.log(rc) + np.log(rd))


pre = [d for d in K.index if B0 <= d < CUT]
post = [d for d in K.index if d >= CUT]

# ================================= C1 =====================================================
P("\n=== C1: break on 27.08 ===")
w = K.loc[date(2026, 6, 1):]
P("baseline sqrt hours   ", cp(np.sqrt(w.hours), w.index))
P("segments in window:", w.source.value_counts().to_dict() if "source" in w else "")
# C1a source: re-derive Kyiv from the official Telegram CSV (independent of KMDA)
off, _ = load_official()
off = off[(off.city == "kyiv") & ~off.imputed_end]
eo = episodes(off.assign(city="kyiv"), "kyiv")
odays = [d for d in pd.date_range("2026-06-01", "2026-09-06").date if d not in OUTAGE]
no = daily_from(eo, odays)
ho = pd.Series(iv.hours_per_day(*iv.merge(off.started_at, off.finished_at), odays[0], odays[-1]),
               index=pd.date_range(odays[0], odays[-1]).date).reindex(odays)
import airalerts.regimes as RG
RG.MIN_SEG = 3   # only 6 observed days after 27.08 in the official feed (outage 29.08-02.09)
P("official CSV (01.06-06.09, outage out, MIN_SEG 3): sqrt h", cp(np.sqrt(ho), odays), "| sqrt n", cp(np.sqrt(no), odays))
kd = K.reindex(odays)
P("KMDA on the same days       (MIN_SEG 3): sqrt h", cp(np.sqrt(kd.hours), odays), "| sqrt n", cp(np.sqrt(kd.n_episodes), odays))
RG.MIN_SEG = 7
ob = [d for d in odays if B0 <= d < CUT]; oa = [d for d in odays if d >= CUT]
P(f"official: episodes/day {no[ob].mean():.2f} -> {no[oa].mean():.2f}; hours {ho[ob].mean():.2f} -> {ho[oa].mean():.2f}"
  f"; corr with KMDA n_episodes {np.corrcoef(no.values, K.n_episodes.reindex(odays).values)[0, 1]:.3f}")
P("KMDA only (window ends 03.10, before alerts.in.ua):", cp(np.sqrt(w.loc[:date(2026, 10, 3)].hours), w.loc[:date(2026, 10, 3)].index))
# C1b few extreme days / transforms
wx = w.drop(EXTREME)
P("without 27-30.08:     ", cp(np.sqrt(wx.hours), wx.index))
top = w.hours.nlargest(10).index
P("without top-10 h days:", cp(np.sqrt(w.drop(top).hours), w.drop(top).index))
for name, f in (("raw hours", lambda x: x), ("log1p hours", np.log1p), ("ranks", lambda x: stats.rankdata(x))):
    P(f"{name:21s}", cp(f(w.hours.values), w.index))
P(f"medians h/day 60d before -> after: {K.hours[pre].median():.2f} -> {K.hours[post].median():.2f}; "
  f"n/day {K.n_episodes[pre].median():.1f} -> {K.n_episodes[post].median():.1f}")
# C1c window
for a, b in (("2026-04-01", None), ("2026-08-01", None), ("2026-06-01", "2026-09-05"), ("2026-07-15", "2026-09-05")):
    ww = K.loc[pd.Timestamp(a).date():(pd.Timestamp(b).date() if b else LAST)]
    P(f"window {a}..{b or LAST}:", cp(np.sqrt(ww.hours), ww.index), "| n:", cp(np.sqrt(ww.n_episodes), ww.index))
ww = K.loc[CUT:]
P("second break inside 27.08..end (sqrt h):", cp(np.sqrt(ww.hours), ww.index))
# C1d step vs ramp (BIC on sqrt hours, Gaussian errors, separate variances not modelled)
y = np.sqrt(w.hours.values); t = np.arange(len(y)); n = len(y)
def bic(res, k): return n * np.log((res ** 2).mean()) + k * np.log(n)
it = list(w.index).index(CUT)
step = np.where(t >= it, y[t >= it].mean(), y[t < it].mean())
best = min(((bic(y - np.interp(t, [a, b], [y[:a].mean(), y[b:].mean()]), 4), a, b)
            for a in range(10, it + 1) for b in range(a + 1, min(a + 30, n - 10))), key=lambda z: z[0])
P(f"BIC step@27.08 {bic(y - step, 3):.1f} vs best ramp {best[0]:.1f} from {w.index[best[1]]} to {w.index[best[2]]}")
P("7-day means of hours, 6.08-2.09:", K.hours.loc[date(2026, 8, 6):date(2026, 9, 2)].rolling(7).mean().iloc[6::7].round(2).to_dict())
# C1e declaration practice: fragmentation / very short alerts
rk = R[(R.city == "kyiv")].copy(); rk["date"] = rk.started_at.dt.tz_convert(TZ).dt.date
e60 = ep_kyiv()
for lab, ds in (("before", pre), ("after", post)):
    e = e60[e60.date.isin(ds)].sort_values("start")
    g = (e.start.values[1:] - e.end.values[:-1]) / np.timedelta64(1, "m")
    P(f"{lab}: records/episode {rk.date.isin(ds).sum() / len(e):.2f}; episodes <5 min {(e.dur_h < 5 / 60).mean():.1%}, "
      f"<10 min {(e.dur_h < 10 / 60).mean():.1%}; gaps 1-10 min {((g > 1) & (g <= 10)).mean():.1%}, <=30 min {(g <= 30).mean():.1%}")
for gap in (60, 300, 900, 1800, 3600):
    e = ep_kyiv(gap)
    nb, na = e.date.isin(pre).sum() / len(pre), e.date.isin(post).sum() / len(post)
    rc, rd, sh = decompose(e, pre, post)
    P(f"merge gap {gap:4d}s: episodes/day {nb:.2f} -> {na:.2f} (x{na / nb:.2f}); share of log-increase from count {sh:.0%}")
# C1f day of week
dw = lambda ds: K.loc[ds].assign(w=[d.weekday() for d in ds]).groupby("w").hours.mean().mean()
P(f"DOW-balanced mean hours {dw(pre):.2f} -> {dw(post):.2f}")

# ================================= C2 =====================================================
P("\n=== C2: more alerts, not longer ===")
P("baseline (60 s): count x{:.2f}, mean dur x{:.2f}, share {:.0%}".format(*decompose(e60, pre, post)))
P("without 27-30.08:      count x{:.2f}, dur x{:.2f}, share {:.0%}".format(*decompose(e60, pre, [d for d in post if d not in EXTREME])))
P("drop episodes < 5 min: count x{:.2f}, dur x{:.2f}, share {:.0%}".format(*decompose(e60[e60.dur_h >= 5 / 60], pre, post)))
mid = [d for d in post if d < REFORM]; late = [d for d in post if d >= REFORM]
P("27.08-05.09 only:      count x{:.2f}, dur x{:.2f}, share {:.0%}".format(*decompose(e60, pre, mid)))
P("06.09-end only:        count x{:.2f}, dur x{:.2f}, share {:.0%}".format(*decompose(e60, pre, late)))
eb, ea = e60[e60.date.isin(pre)], e60[e60.date.isin(post)]
rcm = K.n_episodes[post].median() / K.n_episodes[pre].median()
rdm = ea.dur_h.median() / eb.dur_h.median()
P(f"medians: count x{rcm:.2f}, dur x{rdm:.2f}, share {np.log(rcm) / (np.log(rcm) + np.log(rdm)):.0%}; "
  f"trimmed(10%) dur x{stats.trim_mean(ea.dur_h, .1) / stats.trim_mean(eb.dur_h, .1):.2f}")
P("duration quantiles before:", eb.dur_h.quantile([.25, .5, .75, .9]).round(2).tolist(), "after:", ea.dur_h.quantile([.25, .5, .75, .9]).round(2).tolist())

# ================================= C3 =====================================================
P("\n=== C3: alerts at all hours ===")
bl = lambda h: np.asarray(h) // 6
def share3(e, ds):
    k = e.groupby("date").hour.apply(lambda h: len(set(bl(h)))).reindex(ds, fill_value=0)
    return (k >= 3).mean()
P(f"observed share of days with starts in >=3 blocks: {share3(e60, pre):.0%} -> {share3(e60, post):.0%}")
hb, ha = eb.hour.values, ea.hour.values
cnt = K.n_episodes[post].values.astype(int)
sims = {"old hour profile": [], "uniform hours": []}
for _ in range(2000):
    sims["old hour profile"].append(np.mean([len(set(bl(rng.choice(hb, c)))) >= 3 for c in cnt]))
    sims["uniform hours"].append(np.mean([len(set(bl(rng.integers(0, 24, c)))) >= 3 for c in cnt]))
for k_, v in sims.items():
    P(f"null ({k_}) with the post-break daily counts: {np.mean(v):.0%} (95% {np.quantile(v, .025):.0%}-{np.quantile(v, .975):.0%})")
for lo_, hi_ in ((3, 4), (5, 6)):
    f = lambda ds: [d for d in ds if lo_ <= K.n_episodes[d] <= hi_]
    P(f"days with {lo_}-{hi_} alerts: share >=3 blocks {share3(e60, f(pre)):.0%} (n={len(f(pre))}) -> {share3(e60, f(post)):.0%} (n={len(f(post))})")
P("start-block shares before:", np.bincount(bl(hb), minlength=4) / len(hb), "after:", np.round(np.bincount(bl(ha), minlength=4) / len(ha), 2))

# ================================= C4 =====================================================
P("\n=== C4: drones (yellow) dominate after the reform ===")
arc, _ = load_archive()
ak = arc[(arc.city == "kyiv")]
lo4, hi4 = pd.Timestamp("2026-09-06 03:00", tz="UTC"), pd.Timestamp("2026-10-03 21:00", tz="UTC")
for lab, src in (("KMDA", R[(R.city == "kyiv") & (R.segment == "kmda")]), ("alerts.in.ua", ak)):
    s = src[(src.started_at >= lo4) & (src.started_at < hi4)]
    h = (s.finished_at - s.started_at).dt.total_seconds() / 3600
    P(f"{lab} 06.09-03.10: records {len(s)}, yellow share of records {(s.level == 'yellow').mean():.1%}, of hours {h[s.level == 'yellow'].sum() / h.sum():.1%}")
kk = R[(R.city == "kyiv") & R.cause.notna()]
P("level x cause:\n", pd.crosstab(kk.cause, kk.level))
kp = K.loc[REFORM:]
wk = kp.groupby(pd.to_datetime(kp.index).to_period("W")).agg(y=("hours_yellow", "sum"), h=("hours", "sum"))
P("weekly yellow share:", (wk.y / wk.h).round(2).tolist())
P(f"yellow share without 3 biggest days: {kp.drop(kp.hours.nlargest(3).index).hours_yellow.sum() / kp.drop(kp.hours.nlargest(3).index).hours.sum():.1%}; "
  f"share of days with any red hour {(kp.hours_red > 0).mean():.0%}")

# ================================= C5 =====================================================
P("\n=== C5: local to Kyiv ===")
offall = pd.read_csv(source_path("official"))
arcall = pd.read_csv(source_path("alerts_in_ua")); arcall = arcall[arcall.alert_type == "air_raid"]
for c in ("started_at", "finished_at"):
    offall[c] = pd.to_datetime(offall[c], utc=True, format="mixed"); arcall[c] = pd.to_datetime(arcall[c], utc=True, format="mixed")
offall = offall[(offall.finished_at - offall.started_at).dt.total_seconds() != 3600]
cut_src = pd.Timestamp("2026-09-07", tz=TZ)
days5 = [d for d in pd.date_range("2026-06-01", str(LAST)).date if d not in OUTAGE]
def oblast_series(ob):
    """union of ANY alert in the oblast (oblast/raion/hromada); official CSV before 07.09, archive after.
    Returns episodes/day and hours/day. NB: frontline oblasts saturate (one raion is almost always on)."""
    a = offall[(offall.oblast == ob) & (offall.started_at < cut_src)][["started_at", "finished_at"]]
    b = arcall[(arcall.location_oblast == ob) & (arcall.started_at >= cut_src)][["started_at", "finished_at"]]
    r = pd.concat([a, b]).dropna()
    h = pd.Series(iv.hours_per_day(*iv.merge(r.started_at, r.finished_at), days5[0], days5[-1]),
                  index=pd.date_range(days5[0], days5[-1]).date).reindex(days5)
    return daily_from(episodes(r.assign(city="x"), "x"), days5), h
b_ = [d for d in days5 if B0 <= d < CUT]; a_ = [d for d in days5 if d >= CUT]
a_off = [d for d in a_ if d < date(2026, 9, 7)]          # 27-28.08 and 03-06.09: official feed only, no stitch
for ob in ("м. Київ", "Київська область", "Житомирська область", "Черкаська область", "Вінницька область",
           "Чернігівська область", "Сумська область", "Полтавська область"):
    n5, h5 = oblast_series(ob)
    P(f"{ob:21s} cover {h5[b_].mean() / 24:4.0%} | n/day {n5[b_].mean():4.2f} -> official-only {n5[a_off].mean():4.2f} "
      f"(x{n5[a_off].mean() / n5[b_].mean():.2f}), all after {n5[a_].mean():4.2f} (x{n5[a_].mean() / n5[b_].mean():.2f}) "
      f"| h/day x{h5[a_].mean() / h5[b_].mean():.2f} | stitched {cp(np.sqrt(n5.values), days5)}")
# power: inject a step at 27.08 into Dnipro / Kharkiv hours (gap kept) and re-run the detector
for city in ("dnipro", "kharkiv"):
    c = D[(D.city == city) & ~D.missing & (D.date >= date(2026, 6, 1))].set_index("date")
    for r_ in (1.25, 1.5, 2.0):
        h = c.hours.where(c.index < CUT, np.minimum(c.hours * r_, c.day_len_h))
        s = summarize(changepoint_posterior(np.sqrt(h.values), list(h.index)))
        P(f"power {city} hours x{r_}: MAP {s['map']} BF10 {s['log10_BF_change_vs_none']:.1f}")
    P(f"{city}: mean share of the day under alert 60d before 27.08 = {(c.hours / c.day_len_h)[[d for d in c.index if B0 <= d < CUT]].mean():.0%}")

# ================================= C6 =====================================================
P("\n=== C6: clustering ===")
def disp(x):
    x = np.asarray(x, float); d_ = x.var(ddof=1) / x.mean(); return d_, stats.chi2.sf((len(x) - 1) * d_, len(x) - 1)
n6 = K.n_episodes[post]
P("D all post days: %.2f p=%.3f" % disp(n6))
P("D without 27-30.08: %.2f p=%.3f" % disp(n6.drop(EXTREME)))
P("D without 01-06.10: %.2f p=%.3f" % disp(n6.drop([date(2026, 10, i) for i in range(1, 7)])))
wkid = np.arange(len(n6)) // 7
num = sum(((g - g.mean()) ** 2).sum() for _, g in n6.groupby(wkid)); df = len(n6) - len(set(wkid))
Dw = num / df / n6.mean()
P(f"D within 7-day blocks (pooled): {Dw:.2f}, p={stats.chi2.sf(Dw * df, df):.3f}")
m7 = n6.rolling(7, center=True, min_periods=4).mean()
P(f"detrended chi2/df vs centred 7-day mean: {(((n6 - m7) ** 2) / m7).sum() / (len(n6) * 6 / 7):.2f}")
P("lag-1 autocorr of detrended counts: %.2f" % pd.Series((n6 - m7).values).autocorr(1))
def gap_cv(e):
    e = e.sort_values("start"); g = (e.start.values[1:] - e.end.values[:-1]) / np.timedelta64(1, "s") / 3600
    return g.std(ddof=1) / g.mean(), (g < 1).mean()
P("observed quiet-gap CV %.2f, share<1h %.2f" % gap_cv(ea))
P("gap CV with 10-min merge %.2f, 30-min merge %.2f" % (gap_cv(ep_kyiv(600)[lambda e: e.date.isin(post)])[0], gap_cv(ep_kyiv(1800)[lambda e: e.date.isin(post)])[0]))
# null: no within-day clustering. Each day keeps its own count; starts drawn from the post hour profile,
# durations from post durations, overlaps merged. Second null: constant rate (= mean) + hour profile.
ha_frac = (ea.start.dt.tz_convert(TZ).dt.hour + ea.start.dt.tz_convert(TZ).dt.minute / 60).values
def sim_cv(counts):
    s_, e_ = [], []
    for i, c in enumerate(counts):
        st = i * 24 + rng.choice(ha_frac, c) + rng.uniform(-.5, .5, c)
        s_ += list(st); e_ += list(st + rng.choice(ea.dur_h.values, c))
    o = np.argsort(s_); s_, e_ = np.array(s_)[o], np.array(e_)[o]
    ms, me = [s_[0]], [e_[0]]
    for a, b in zip(s_[1:], e_[1:]):
        if a <= me[-1]: me[-1] = max(me[-1], b)
        else: ms.append(a); me.append(b)
    g = np.array(ms[1:]) - np.array(me[:-1]); return g.std(ddof=1) / g.mean(), (g < 1).mean()
for lab, cnts in (("own daily counts + hour profile", lambda: n6.values.astype(int)), ("Poisson(mean) + hour profile", lambda: rng.poisson(n6.mean(), len(n6)))):
    v = np.array([sim_cv(cnts()) for _ in range(300)])
    P(f"null [{lab}]: CV {v[:, 0].mean():.2f} (95% {np.quantile(v[:, 0], .025):.2f}-{np.quantile(v[:, 0], .975):.2f}), share<1h {v[:, 1].mean():.2f}")

# ================================= C7 =====================================================
P("\n=== C7: no excess around events ===")
ee = pd.read_csv(ROOT / "results/events_effects.csv")
from statsmodels.stats.multitest import multipletests
P(f"min p_more {ee.p_more.min():.3f}; Holm-adjusted min {multipletests(ee.p_more, method='holm')[1].min():.2f}; "
  f"min p_less {ee.p_less.min():.3f}")
evs = pd.read_csv(ROOT / "data/events/events.csv")
dk = D[D.city == "kyiv"].copy()
# (a) placebo windows contaminated by other events: blank all event windows for the placebo table
ewin = {(pd.Timestamp(x) + pd.Timedelta(days=k)).date() for x in evs.date for k in range(-1, 4)}
masked = dk.copy(); masked.loc[masked.date.isin(ewin), "hours"] = np.nan
y = dk.set_index(pd.to_datetime(dk.date)).hours; ym = masked.set_index(pd.to_datetime(masked.date)).hours
offs = np.array([o for o in range(-30, 31) if abs(o) >= 5])
days7 = [pd.Timestamp(x) for x in evs.date if pd.Timestamp(x) >= y.index.min() + pd.Timedelta(days=31)]
obs = np.nanmean([EV.window_mean(y, d) for d in days7])
tab = np.array([[EV.window_mean(ym, d + pd.Timedelta(days=int(o))) for o in offs] for d in days7])
perm = np.nanmean(tab[np.arange(len(days7)), rng.integers(0, len(offs), (10000, len(days7)))], axis=1)
P(f"Kyiv all events, placebo windows without other events: excess {obs - perm.mean():+.2f} h, p_more {(perm >= obs).mean():.3f}; "
  f"placebo windows lying fully inside other events' windows: {np.isnan(tab).mean():.0%}")
# (b) events whose +-33 days straddle the 27.08 break
near = [d for d in days7 if abs((d.date() - CUT).days) <= 33]
P("events within 33 days of the break:", [str(d.date()) for d in near])
# (c) other windows (anticipation / same day): p for Kyiv, all events, using the project's function
for wnd in ((0, 0), (0, 1), (-3, -1)):
    EV.WINDOW = wnd
    r = EV.analyse(D, evs, "kyiv").set_index("category")
    P(f"window {wnd}: Kyiv all excess {r.loc['all', 'excess_h']:+.2f} p_more {r.loc['all', 'p_more']:.3f}; min p over groups {r.p_more.min():.3f}")
EV.WINDOW = (-1, 3)
r = EV.analyse(D, evs[~evs.date.isin(["2026-08-24", "2026-09-17"])], "kyiv").set_index("category")
P(f"without the 2 events whose placebo range straddles 27.08: Kyiv all excess {r.loc['all', 'excess_h']:+.2f}, p_more {r.loc['all', 'p_more']:.3f}")
