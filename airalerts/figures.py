"""CP6 figures. Each figure answers one question, written in its title.

Static PNGs for the README (light surface, explicit background so they read on any page).
Palette (validated with the dataviz validator): cities Kyiv/Kharkiv/Dnipro = categorical
slots 1-3; alert levels yellow/red = the two level colors; sequential blue for heatmaps.
Identity is never color-only: every series is direct-labelled or in a legend.
"""
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

from . import intervals as iv  # noqa: E402
from .config import ROOT, TZ  # noqa: E402
from .regimes import HYP_DAY, REFORM_DAY, episodes  # noqa: E402

FIG = ROOT / "figures"
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
CITY = {"kyiv": "#2a78d6", "kharkiv": "#eb6834", "dnipro": "#1baf7a", "lviv": "#52514e"}
NAME = {"kyiv": "Київ", "kharkiv": "Харків", "dnipro": "Дніпро", "lviv": "Львів"}
YELLOW, RED = "#eda100", "#e34948"
SEQ = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
START = pd.Timestamp("2026-06-01")


def style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False,
        "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False,
    })


def mark_dates(ax, top, label=True):
    for d, txt, ha in ((HYP_DAY, "злам 27.08 ", "right"), (REFORM_DAY, " реформа 06.09", "left")):
        ax.axvline(pd.Timestamp(d), color=INK2, lw=1, ls=(0, (4, 3)))
        if label:
            ax.text(pd.Timestamp(d), top, txt, color=INK2, fontsize=8.5, va="top", ha=ha)


def shade_missing(ax, d):
    for day in d[d.missing].date:
        ax.axvspan(pd.Timestamp(day), pd.Timestamp(day) + pd.Timedelta(days=1), color=GRID, lw=0)


def save(fig, name):
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / name, dpi=150, bbox_inches="tight")
    plt.close(fig)


# 1 ---------------------------------------------------------------------------------
def fig_kyiv_break(daily, posts):
    d = daily[(daily.city == "kyiv") & (pd.to_datetime(daily.date) >= START)].copy()
    d["t"] = pd.to_datetime(d.date)
    fig, (a, b) = plt.subplots(2, 1, figsize=(10, 6.2), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    a.bar(d.t, d.hours, width=0.8, color="#9ec5f4", label="години тривоги за добу")
    a.plot(d.t, d.hours.rolling(7, min_periods=4).mean(), color=CITY["kyiv"], lw=2, label="середнє за 7 днів")
    a.set_ylim(0, 24)
    a.set_ylabel("год / добу")
    mark_dates(a, 23.5)
    a.legend(loc="upper left", bbox_to_anchor=(0, 0.88))
    mp = posts[("kyiv", "sqrt_hours")].idxmax()
    lead = (pd.Timestamp(REFORM_DAY) - pd.Timestamp(mp)).days
    a.set_title(f"Коли змінився режим у Києві?  Різко {mp:%d.%m} — за {lead} днів до зміни правил оголошення 06.09")
    for (city, series), lab, col in ((("kyiv", "sqrt_hours"), "за годинами", CITY["kyiv"]),
                                     (("kyiv", "sqrt_episodes"), "за кількістю тривог", INK2)):
        p = posts[(city, series)]
        b.plot(pd.to_datetime(p.index), p.values, color=col, lw=2, label=lab)
    b.set_ylabel("P(злам у цей день)")
    b.legend(loc="upper left")
    mark_dates(b, 0, label=False)
    b.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    b.set_title("Апостеріорний розподіл дати зламу (байєсівська модель з однією точкою)", fontsize=10)
    save(fig, "fig1_kyiv_break.png")


# 2 ---------------------------------------------------------------------------------
def fig_cities(daily):
    fig, axes = plt.subplots(4, 1, figsize=(10, 8.4), sharex=True, sharey=True)
    for ax, city in zip(axes, ("kyiv", "kharkiv", "dnipro", "lviv")):
        d = daily[(daily.city == city) & (pd.to_datetime(daily.date) >= START)].copy()
        d["t"] = pd.to_datetime(d.date)
        shade_missing(ax, d)
        ax.bar(d.t, d.hours, width=0.8, color=CITY[city], alpha=0.35)
        ax.plot(d.t, d.hours.rolling(7, min_periods=4).mean().where(~d.missing), color=CITY[city], lw=2)
        mark_dates(ax, 23.5, label=(city == "kyiv"))
        ax.set_ylim(0, 24)
        ax.text(0.005, 0.92, NAME[city], transform=ax.transAxes, fontweight="bold", va="top")
        ax.set_ylabel("год / добу", fontsize=8.5)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    axes[0].set_title("Чи змінились контрольні міста разом із Києвом? У Харкові й Дніпрі різкого стрибка немає\n"
                      "(стовпчики — доба, лінія — 7 днів; сірі смуги — пропуск даних 29.08–02.09)")
    save(fig, "fig2_cities_daily_hours.png")


# 3 ---------------------------------------------------------------------------------
def fig_count_vs_duration(daily, records):
    k = daily[(daily.city == "kyiv")]
    lo = (pd.Timestamp(HYP_DAY) - pd.Timedelta(days=60)).date()
    before, after = k[(k.date >= lo) & (k.date < HYP_DAY)], k[k.date >= HYP_DAY]
    ep = episodes(records, "kyiv")
    eb, ea = ep[(ep.date >= lo) & (ep.date < HYP_DAY)], ep[ep.date >= HYP_DAY]
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4))
    rng = np.random.default_rng(0)
    for i, (g, lab, col) in enumerate(((before, "60 днів до 27.08", MUTED), (after, "з 27.08", CITY["kyiv"]))):
        x = i + rng.uniform(-0.18, 0.18, len(g))
        a.scatter(x, g.n_episodes, s=14, color=col, alpha=0.7)
        a.hlines(g.n_episodes.mean(), i - 0.3, i + 0.3, color=INK, lw=2)
        a.text(i + 0.33, g.n_episodes.mean(), f"{g.n_episodes.mean():.1f}", va="center", color=INK)
    a.set_xticks([0, 1], ["60 днів до 27.08", "з 27.08"])
    a.set_ylabel("окремих тривог за добу")
    a.set_title(f"Більше тривог?  Так: {before.n_episodes.mean():.1f} → {after.n_episodes.mean():.1f} на добу")
    for g, lab, col in ((eb, "до 27.08", MUTED), (ea, "з 27.08", CITY["kyiv"])):
        x = np.sort(g.dur_h.to_numpy() * 60)
        b.step(x, np.arange(1, len(x) + 1) / len(x), where="post", color=col, lw=2,
               label=f"{lab}: медіана {np.median(x):.0f} хв")
    b.set_xscale("log")
    b.set_xlabel("тривалість однієї тривоги, хв (лог. шкала)")
    b.set_ylabel("частка тривог ≤ x")
    b.legend(loc="lower right")
    b.set_title(f"Довші тривоги?  Трохи: медіана {eb.dur_h.median() * 60:.0f} → {ea.dur_h.median() * 60:.0f} хв")
    save(fig, "fig3_kyiv_count_vs_duration.png")


# 4 ---------------------------------------------------------------------------------
def hour_weekday_share(records, city, lo, hi):
    r = records[records.city == city]
    ms, me = iv.merge(r.started_at, r.finished_at)
    hours = pd.date_range(pd.Timestamp(lo), pd.Timestamp(hi) + pd.Timedelta(days=1), freq="h", tz=TZ)
    b = hours.tz_convert("UTC").to_numpy("datetime64[ns]")
    cov = np.zeros(len(b) - 1)
    for s, e in zip(ms, me):
        i = max(np.searchsorted(b, s, side="right") - 1, 0)
        while i < len(cov) and b[i] < e:
            cov[i] += (min(e, b[i + 1]) - max(s, b[i])) / np.timedelta64(1, "s") / 3600
            i += 1
    h = pd.DataFrame({"t": hours[:-1], "cov": np.clip(cov, 0, 1)})
    h["hour"], h["wd"] = h.t.dt.hour, h.t.dt.dayofweek
    return h.pivot_table(index="wd", columns="hour", values="cov", aggfunc="mean")


def fig_rhythm(daily, records):
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", SEQ)
    lo = (pd.Timestamp(HYP_DAY) - pd.Timedelta(days=60)).date()
    last = daily[daily.city == "kyiv"].date.max()
    hb = hour_weekday_share(records, "kyiv", lo, (pd.Timestamp(HYP_DAY) - pd.Timedelta(days=1)).date())
    ha = hour_weekday_share(records, "kyiv", HYP_DAY, last)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
    for ax, h, ttl in ((axes[0], hb, "60 днів до 27.08"), (axes[1], ha, "з 27.08")):
        im = ax.imshow(h.values, aspect="auto", cmap=cmap, vmin=0, vmax=1)
        ax.set_xticks(range(0, 24, 3), [f"{x:02d}" for x in range(0, 24, 3)])
        ax.set_yticks(range(7), ["пн", "вт", "ср", "чт", "пт", "сб", "нд"])
        ax.set_xlabel("година доби (Київ)")
        ax.grid(False)
        ax.set_title(f"{ttl}: {h.values.mean() * 24:.1f} год/добу під тривогою", fontsize=10)
    cb = fig.colorbar(im, ax=axes, shrink=0.9, pad=0.01)
    cb.set_label("частка часу під тривогою")
    fig.suptitle("Як змінився добовий ритм Києва?  Раніше тривоги рідкі й частіше вночі, тепер — у будь-яку годину",
                 x=0.06, y=1.06, ha="left", fontweight="bold", fontsize=11)
    save(fig, "fig4_kyiv_hour_weekday.png")


# 5 ---------------------------------------------------------------------------------
def fig_day_night(daily, records):
    lo = (pd.Timestamp(HYP_DAY) - pd.Timedelta(days=60)).date()
    rows = []
    for city in ("kyiv", "kharkiv", "dnipro", "lviv"):
        last = daily[daily.city == city].date.max()
        miss = set(daily[(daily.city == city) & daily.missing].date)
        for per, (a, b) in (("до 27.08", (lo, (pd.Timestamp(HYP_DAY) - pd.Timedelta(days=1)).date())),
                            ("з 27.08", (HYP_DAY, last))):
            h = hour_weekday_share(records, city, a, b)  # weekday x hour
            # recompute on observed days only
            r = records[records.city == city]
            ms, me = iv.merge(r.started_at, r.finished_at)
            hours = pd.date_range(pd.Timestamp(a), pd.Timestamp(b) + pd.Timedelta(days=1), freq="h", tz=TZ)
            bb = hours.tz_convert("UTC").to_numpy("datetime64[ns]")
            cov = np.zeros(len(bb) - 1)
            for s, e in zip(ms, me):
                i = max(np.searchsorted(bb, s, side="right") - 1, 0)
                while i < len(cov) and bb[i] < e:
                    cov[i] += (min(e, bb[i + 1]) - max(s, bb[i])) / np.timedelta64(1, "s") / 3600
                    i += 1
            df = pd.DataFrame({"t": hours[:-1], "cov": np.clip(cov, 0, 1)})
            df = df[~df.t.dt.date.isin(miss)]
            df["night"] = df.t.dt.hour < 6
            per_day = df.groupby(df.t.dt.date).apply(lambda g: pd.Series({
                "night": g.loc[g.night, "cov"].sum(), "day": g.loc[~g.night, "cov"].sum()}), include_groups=False)
            rows.append({"city": city, "period": per, "night": per_day.night.mean(), "day": per_day.day.mean()})
    t = pd.DataFrame(rows)
    fig, axes = plt.subplots(1, 4, figsize=(11, 3.8))
    for ax, city in zip(axes, ("kyiv", "kharkiv", "dnipro", "lviv")):
        g = t[t.city == city].set_index("period").loc[["до 27.08", "з 27.08"]]
        x = np.arange(2)
        ax.bar(x - 0.18, g.night, width=0.34, color="#184f95", label="ніч 00–06")
        ax.bar(x + 0.18, g.day, width=0.34, color="#86b6ef", label="день 06–24")
        for i, (n, dd) in enumerate(zip(g.night, g.day)):
            share = n / (n + dd) if n + dd else np.nan
            ax.text(i, max(n, dd) + 0.25, f"ніч {share:.0%}", ha="center", fontsize=8.5, color=INK2)
        ax.set_xticks(x, g.index)
        ax.set_ylim(0, 16)
        ax.set_title(NAME[city], fontsize=10)
        if city == "kyiv":
            ax.set_ylabel("год тривоги за добу")
            ax.legend(loc="upper left", fontsize=8.5)
    k = t[t.city == "kyiv"].set_index("period")
    sh = lambda p: k.loc[p, "night"] / (k.loc[p, "night"] + k.loc[p, "day"])
    fig.suptitle(f"Нічні чи денні тривоги?  У Києві денні виросли {k.loc['до 27.08', 'day']:.1f} → "
                 f"{k.loc['з 27.08', 'day']:.1f} год, нічні {k.loc['до 27.08', 'night']:.1f} → {k.loc['з 27.08', 'night']:.1f};"
                 f" частка ночі {sh('до 27.08'):.0%} → {sh('з 27.08'):.0%}",
                 x=0.06, ha="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    save(fig, "fig5_day_night_by_city.png")
    return t


# 6 ---------------------------------------------------------------------------------
def fig_test_forecasts(fc, base, test_days):
    m = fc[(fc.method == "qr_full__with_midnight") & fc.date.isin(test_days)]
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.8), sharey=True)
    for ax, city in zip(axes, ("kyiv", "kharkiv", "dnipro")):
        g = m[m.city == city].sort_values("date")
        t = pd.to_datetime(g.date)
        ax.fill_between(t, g.q10, g.q90, color=CITY[city], alpha=0.18, lw=0, label="80% інтервал моделі")
        ax.plot(t, g.q50, color=CITY[city], lw=2, label="медіана прогнозу")
        inside = (g.y >= g.q10) & (g.y <= g.q90)
        ax.scatter(t[inside], g.y[inside], s=26, color=INK, zorder=3, label="факт (в інтервалі)")
        ax.scatter(t[~inside], g.y[~inside], s=34, facecolor=SURFACE, edgecolor=RED, lw=2, zorder=3,
                   label="факт (поза інтервалом)")
        ax.set_ylim(0, 24)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        ax.tick_params(axis="x", labelsize=8)
        ax.set_title(f"{NAME[city]}: покриття {inside.mean():.0%} ({inside.sum()}/{len(g)})", fontsize=10)
    axes[0].set_ylabel("год тривоги за добу")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=4, fontsize=8.5, bbox_to_anchor=(0.5, -0.06))
    fig.suptitle("Чи потрапляє факт у прогнозний інтервал?  Тест 26.09–09.10: квантильна регресія, прогноз о 00:00 на добу",
                 x=0.06, ha="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    save(fig, "fig6_test_forecasts.png")


# 7 ---------------------------------------------------------------------------------
def fig_process(daily, records, res, gaps_fn):
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 3.9))
    rows = res.copy()
    labels = [f"{NAME[c]}\n{'до' if p == 'before' else 'після'}" for c, p in zip(rows.city, rows.period)]
    cols = [CITY[c] for c in rows.city]
    x = np.arange(len(rows))
    a.bar(x, rows.dispersion_D, color=cols, width=0.6)
    a.axhline(1, color=INK2, lw=1, ls=(0, (4, 3)))
    a.text(len(rows) - 0.5, 1.02, "Пуассон = 1", ha="right", va="bottom", color=INK2, fontsize=8.5)
    for i, v in enumerate(rows.dispersion_D):
        a.text(i, v + 0.03, f"{v:.2f}", ha="center", fontsize=8.5, color=INK)
    a.set_xticks(x, labels, fontsize=8.5)
    a.set_ylabel("дисперсія / середнє (тривог за добу)")
    k = rows[(rows.city == "kyiv") & (rows.period == "after")].iloc[0]
    a.set_title(f"Розкид між днями: у Києві D > 1, але в межах тижня D = {k.dispersion_D_within_week:.2f}"
                "\n(тобто це хвилі на тиждень-два, а не «густо-пусто» щодня)", fontsize=10)
    g = gaps_fn("kyiv", "after")
    bins = np.logspace(np.log10(1 / 60), np.log10(max(g.max(), 24)), 30)
    a2 = b
    a2.hist(g, bins=bins, color=CITY["kyiv"], alpha=0.5, label="Київ з 27.08: паузи між тривогами")
    lam = 1 / g.mean()
    edges = bins
    expected = len(g) * (np.exp(-lam * edges[:-1]) - np.exp(-lam * edges[1:]))
    a2.step(edges[:-1], expected, where="post", color=INK, lw=2, label="очікувано для Пуассона")
    a2.set_xscale("log")
    a2.set_xlabel("пауза від кінця тривоги до наступної, год (лог. шкала)")
    a2.set_ylabel("кількість пауз")
    a2.set_ylim(0, a2.get_ylim()[1] * 1.3)
    a2.legend(loc="upper left", fontsize=8.5)
    r = rows[(rows.city == "kyiv") & (rows.period == "after")].iloc[0]
    a2.set_title(f"Пачки з довгими перервами?  Так: CV пауз {r.quiet_gap_cv:.2f} (Пуассон = 1)", fontsize=10)
    fig.suptitle("Чому прогноз для Києва важкий: рівень змінюється хвилями, а в межах доби тривоги йдуть пачками",
                 x=0.06, ha="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    save(fig, "fig7_poisson_vs_clustering.png")


# 8 ---------------------------------------------------------------------------------
def fig_events(ev):
    cats = [("ru_holiday", "свята РФ"), ("ua_holiday", "свята України"), ("negotiations", "переговори"),
            ("ua_strike", "удари України по РФ"), ("all", "усі події")]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for j, city in enumerate(("kyiv", "kharkiv", "dnipro")):
        g = ev[ev.city == city].set_index("category")
        for i, (c, lab) in enumerate(cats):
            y = i + (j - 1) * 0.22
            r = g.loc[c]
            ax.errorbar(r.excess_h, y, xerr=[[r.excess_h - r.excess_ci95_lo], [r.excess_ci95_hi - r.excess_h]],
                        fmt="o", color=CITY[city], ms=6, lw=2, capsize=0,
                        label=NAME[city] if i == 0 else None)
    ax.axvline(0, color=INK2, lw=1)
    ax.set_yticks(range(len(cats)), [f"{lab} (n={int(ev[(ev.city == 'kyiv') & (ev.category == c)].n_events.iloc[0])})"
                                     for c, lab in cats])
    ax.invert_yaxis()
    ax.set_xlabel("надлишок годин тривоги на добу у вікні [−1; +3] дні (95% смуга плацебо)")
    ax.legend(loc="lower right")
    crosses = ((ev.excess_ci95_lo <= 0) & (ev.excess_ci95_hi >= 0)).all()
    ax.set_title("Чи більше тривог навколо подій?  " + ("Надлишку не виявлено: усі смуги перетинають нуль" if crosses
                 else "Є інтервали, що не перетинають нуль — див. reports/events.md"))
    save(fig, "fig8_events.png")


# 9 ---------------------------------------------------------------------------------
def fig_neighbours(nb):
    """Alerts per day after/before 27.08 by oblast (official CSV only, see neighbours.py)."""
    nb = nb.iloc[::-1].reset_index(drop=True)
    sat = nb.share_of_day_under_alert_before >= 0.6
    color = {"Київ": CITY["kyiv"], "довкола Києва": "#6da7ec", "інші": AXIS}
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for i, r in nb.iterrows():
        ax.barh(i, r.alerts_ratio, color=color[r.group], height=0.65)
        note = (f"  насичено: під тривогою {r.share_of_day_under_alert_before:.0%} часу" if sat[i]
                else f"  ×{r.alerts_ratio:.1f} тривог, ×{r.hours_ratio:.1f} годин")
        ax.text(max(r.alerts_ratio, 0), i, note, va="center", fontsize=8.5, color=MUTED if sat[i] else INK2)
    ax.axvline(1, color=INK2, lw=1, ls=(0, (4, 3)))
    ax.set_yticks(range(len(nb)), nb.oblast.str.replace(" область", " обл."))
    ax.set_xlim(0, nb.alerts_ratio.max() * 1.9)
    ax.set_xlabel("тривог на добу: 27.08–06.09 (без 29.08–02.09) / 60 днів до 27.08; 1 = без змін")
    ax.grid(axis="y", visible=False)
    ax.set_title("Чи змінився 27.08 лише Київ?  Ні: області довкола Києва теж різко зросли\n"
                 "(офіційний канал; «тривога в області» = будь-яка тривога в області, районі чи громаді)")
    save(fig, "fig9_neighbour_oblasts.png")


def main():
    import pandas as pd
    from .build import load_processed
    from .config import PROCESSED, RESULTS
    from .evaluate import periods
    from .models import days_between
    from .process import analyse
    from .regimes import detect
    style()
    records, daily = load_processed()
    _, posts = detect(daily, cities=("kyiv",))
    fig_kyiv_break(daily, posts)
    fig_cities(daily)
    fig_count_vs_duration(daily, records)
    fig_rhythm(daily, records)
    dn = fig_day_night(daily, records)
    dn.round(3).to_csv(RESULTS / "day_night_hours.csv", index=False)
    fc = pd.read_csv(PROCESSED / "model_forecasts.csv")
    fc["date"] = pd.to_datetime(fc.date).dt.date
    fig_test_forecasts(fc, None, days_between(*periods(daily)["test"]))
    res, gaps = analyse(daily, records)
    fig_process(daily, records, res, lambda c, p: gaps[(c, p)])
    fig_events(pd.read_csv(RESULTS / "events_effects.csv"))
    fig_neighbours(pd.read_csv(RESULTS / "neighbour_oblasts.csv"))
    return dn


if __name__ == "__main__":
    print(main())
