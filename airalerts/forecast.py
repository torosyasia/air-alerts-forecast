"""Forecast for the first day after the data: median and 80% interval for Kyiv, Kharkiv, Dnipro.

The day D is the first Kyiv-local day after the last complete day of the data. The forecast
is issued as of D 00:00 Kyiv (only records before that moment are used, through the same
`history_at` gate as in the evaluation) by the model with the lowest pooled validation
interval score among the quantile-regression variants (DECISIONS D-18). The choice is made
again on every run, so it follows the validation window when the data are refreshed.
Depending on when the data snapshot was taken, D is "today" or "tomorrow" for the reader.
"""
import numpy as np
import pandas as pd

from . import intervals as iv
from .build import load_processed
from .config import PROCESSED, RESULTS, TZ, pinned
from .evaluate import FORECAST_CITIES
from .features import features_at
from .models import FEATURE_SETS, N_CONF, fit_predict

# The forecast block says the median is biased when its mean shift on the test is at least
# this share of the test MAE (a systematic error, not just more days on one side).
BIAS_SHARE_OF_MAE = 0.25
CITY_UK = {"kyiv": "Київ", "kharkiv": "Харків", "dnipro": "Дніпро"}


def human(method):
    """Readable Ukrainian name of a model variant for running text (technical names stay in tables)."""
    window, fs, cqr = parse_method(method)
    s = "квантильна регресія на " + ("всій історії" if window is None else f"останніх {window} днях")
    s += {"with_midnight": "", "no_midnight": " без ознаки «тривога о 00:00»",
          "no_midnight_no_last6h": " без ознак останніх 6 годин"}[fs]
    return s + (" з конформною калібровкою" if cqr else "")


def select_main_model(metrics):
    v = metrics[(metrics.period == "validation") & (metrics.city == "pooled") & (metrics.kind == "model")]
    return v.loc[v.interval_score.idxmin(), "method"]


def parse_method(name):
    """'qr_full__with_midnight' / 'qr_fresh84__no_midnight+cqr' -> (window, feature set, cqr)."""
    base, cqr = name.removesuffix("+cqr"), name.endswith("+cqr")
    kind, fs = base.split("__")
    window = None if kind == "qr_full" else int(kind.removeprefix("qr_fresh"))
    return window, fs, cqr


def forecast_next_day():
    """The published forecast for the three studied cities: rows of the all-Ukraine forecast
    (one main model everywhere - the shared quantile regression chosen on validation,
    airalerts/national_models.py; run it first). The per-city model of CP4 stays in REPORT."""
    a = pd.read_csv(RESULTS / "forecast_next_day_all.csv")
    out = a.set_index("city").loc[list(FORECAST_CITIES)].reset_index()
    cols = ["city", "forecast_for", "issued_as_of_kyiv", "q10_h", "q50_h", "q90_h", "alert_running_at_00",
            "hours_yesterday", "mean_last_7d", "model", "test_MAE_h", "test_coverage80",
            "best_baseline_test_MAE_h", "data_snapshot_utc"]
    out = out[cols].round({"test_MAE_h": 2, "test_coverage80": 2, "best_baseline_test_MAE_h": 2})
    out.to_csv(RESULTS / "forecast_next_day.csv", index=False)
    return out


def markdown(out):
    D = out.forecast_for.iloc[0]
    L = [f"**Прогноз на {pd.Timestamp(D):%d.%m.%Y}** (доба 00:00–24:00 за Києвом), зроблений станом на "
         f"{pd.Timestamp(D):%d.%m} 00:00 з даних до {out.data_snapshot_utc.iloc[0]} UTC. "
         f"Модель — спільна квантильна регресія для всіх обласних центрів (обрана на валідації; прогноз для "
         f"кожного центру — [на карті](https://torosyasia.github.io/air-alerts-forecast/) і в "
         f"[`results/forecast_next_day_all.csv`](results/forecast_next_day_all.csv)).", "",
         "| Місто | Медіана, год | 80% інтервал, год | Тривога о 00:00 | Учора, год | Середнє за 7 днів, год | MAE моделі на тесті | Покриття на тесті |",
         "|---|---|---|---|---|---|---|---|"]
    for _, r in out.iterrows():
        L.append(f"| {CITY_UK[r.city]} | **{r.q50_h:.1f}** | {r.q10_h:.1f} – {r.q90_h:.1f} | "
                 f"{'так' if r.alert_running_at_00 else 'ні'} | {r.hours_yesterday:.1f} | {r.mean_last_7d:.1f} | "
                 f"{r.test_MAE_h:.2f} | {r.test_coverage80:.0%} |")
    k = out.set_index("city").loc["kyiv"]
    from .evaluate import periods
    _, daily = load_processed()
    test = periods(daily)["test"]
    mf = pd.read_csv(PROCESSED / "national_forecasts.csv")
    mf = mf[(mf.city == "kyiv") & (mf.method == k.model) & (pd.to_datetime(mf.date).dt.date >= test[0])]
    above = int((mf.y > mf.q50).sum())
    worse = k.test_MAE_h >= k.best_baseline_test_MAE_h
    bias = float((mf.y - mf.q50).mean())          # > 0: the median is too low on average
    shifted = abs(bias) >= BIAS_SHARE_OF_MAE * k.test_MAE_h
    L += ["", f"**Наскільки цьому вірити.** На тесті 80% інтервал накрив факт у {out.test_coverage80.min():.0%}–"
          f"{out.test_coverage80.max():.0%} днів, а медіана помилялась у середньому на {out.test_MAE_h.min():.1f}–"
          f"{out.test_MAE_h.max():.1f} год. "
          + (f"Для Києва модель не краща за найкращий простий прогноз ({k.test_MAE_h:.1f} проти "
             f"{k.best_baseline_test_MAE_h:.1f} год)" if worse else
             f"Для Києва модель трохи краща за найкращий простий прогноз ({k.test_MAE_h:.1f} проти "
             f"{k.best_baseline_test_MAE_h:.1f} год)")
          + ((f", а її медіана {'занижена' if bias > 0 else 'завищена'}: у середньому факт "
              f"{'вищий' if bias > 0 else 'нижчий'} на {abs(bias):.1f} год (вищий у {above} з {len(mf)} днів). ")
             if shifted and (above >= 0.6 * len(mf) if bias > 0 else above <= 0.4 * len(mf)) else
             (f"; факт у середньому вищий за медіану на {bias:.1f} год, хоча вищий лише в {above} з {len(mf)} днів "
              "(кілька дуже важких днів тягнуть середнє вгору). ") if shifted else ". ")
          + "Тож для Києва дивіться на інтервал, а не на точну цифру; це статистика, а не попередження про "
          "загрозу. Файл: [`results/forecast_next_day.csv`](results/forecast_next_day.csv)."]
    return "\n".join(L)


CITY_EN = {"kyiv": "Kyiv", "kharkiv": "Kharkiv", "dnipro": "Dnipro"}


def markdown_en(out):
    """Short English forecast block for README.en.md (same numbers as markdown())."""
    D = out.forecast_for.iloc[0]
    k = out.set_index("city").loc["kyiv"]
    L = [f"**Forecast for {pd.Timestamp(D):%d %b %Y}** (00:00–24:00 Kyiv time), issued as of 00:00 from data up "
         f"to {out.data_snapshot_utc.iloc[0]} UTC.", "",
         "| City | Median, h | 80% interval, h | Alert at 00:00 | Yesterday, h | Test MAE, h | Test coverage |",
         "|---|---|---|---|---|---|---|"]
    for _, r in out.iterrows():
        L.append(f"| {CITY_EN[r.city]} | **{r.q50_h:.1f}** | {r.q10_h:.1f} – {r.q90_h:.1f} | "
                 f"{'yes' if r.alert_running_at_00 else 'no'} | {r.hours_yesterday:.1f} | {r.test_MAE_h:.2f} | "
                 f"{r.test_coverage80:.0%} |")
    worse = k.test_MAE_h >= k.best_baseline_test_MAE_h
    L += ["", "**How far to trust it.** For Kyiv the model is "
          + ("not better than the best simple baseline" if worse else "only slightly better than the best simple baseline")
          + f" ({k.test_MAE_h:.1f} vs {k.best_baseline_test_MAE_h:.1f} h mean error), so read the interval, not the "
          "point. This is a statistical forecast, not a threat warning."]
    return "\n".join(L)


def results_markdown():
    """Test results of the baselines and the models (auto block; follows the data)."""
    from .evaluate import baseline_forecasts, periods
    from .models import common_days, days_between, paired_diff
    records, daily = load_processed()
    per = periods(daily)
    m = pd.read_csv(RESULTS / "metrics_validation_test.csv")
    main = select_main_model(m)
    t = m[m.period == "test"]
    pool = t[t.city == "pooled"].set_index("method")
    b = pool[pool.kind == "baseline"]
    best_mae, best_is = b.MAE.idxmin(), b.interval_score.idxmin()
    fresh = [x for x in pool.index if x.startswith("qr_fresh") and x.endswith("+cqr") and "with_midnight" in x]
    rows = [(f"найкращий baseline за MAE (`{best_mae}`)", best_mae), (f"найкращий baseline за IS (`{best_is}`)", best_is),
            (f"**модель, обрана на валідації** (`{main}`)", main)] + [(f"свіже вікно + CQR (`{x}`)", x) for x in fresh if x != main]
    L = [f"Тест **{per['test'][0]:%d.%m}–{per['test'][1]:%d.%m.%Y}** (останні 14 повних діб), прогноз о 00:00 на добу, "
         "3 міста разом:", "", "| Метод | MAE, год | Покриття 80% (95% CI) | Ширина, год | Interval score |", "|---|---|---|---|---|"]
    for label, k in rows:
        r = pool.loc[k]
        L.append(f"| {label} | {r.MAE:.2f} | {r.coverage80:.2f} ({r.cov_lo95:.2f}–{r.cov_hi95:.2f}) | {r.width:.2f} | {r.interval_score:.2f} |")
    L += ["", "| Місто | Модель: MAE / IS / покриття | Найкращий baseline: MAE / IS | Модель краща за |", "|---|---|---|---|"]
    for city in FORECAST_CITIES:
        c = t[t.city == city].set_index("method")
        cb = c[c.kind == "baseline"]
        r = c.loc[main]
        wins = [n for n, ok in (("MAE", r.MAE < cb.MAE.min()), ("interval score", r.interval_score < cb.interval_score.min())) if ok]
        L.append(f"| {CITY_UK[city]} | {r.MAE:.2f} / {r.interval_score:.2f} / {r.coverage80:.2f} | "
                 f"{cb.MAE.min():.2f} (`{cb.MAE.idxmin()}`) / {cb.interval_score.min():.2f} (`{cb.interval_score.idxmin()}`) | "
                 f"{', '.join(wins) if wins else 'жодною метрикою'} |")
    fc = pd.read_csv(PROCESSED / "model_forecasts.csv")
    fc["date"] = pd.to_datetime(fc.date).dt.date
    base = pd.concat([baseline_forecasts(daily[daily.city == c]).assign(city=c) for c in FORECAST_CITIES])
    fc, base = common_days(fc[fc.method == main], base[base.date.isin(set(fc.date))])
    days = days_between(*per["test"])
    d_mae = paired_diff(fc, base[base.method == best_mae], days, "MAE")
    d_is = paired_diff(fc, base[base.method == best_is], days, "interval_score")
    sig = lambda d: "CI не містить 0" if d[1] > 0 or d[2] < 0 else "CI містить 0"
    L += ["", f"Різниця «модель − найкращий baseline» (блоковий bootstrap, 95% CI): MAE {d_mae[0]:+.2f} "
          f"[{d_mae[1]:+.2f}, {d_mae[2]:+.2f}] ({sig(d_mae)}), interval score {d_is[0]:+.2f} [{d_is[1]:+.2f}, {d_is[2]:+.2f}] ({sig(d_is)})."]
    return "\n".join(L)


def data_markdown():
    records, daily = load_processed()
    pins = pinned()
    last_day = daily.date.max()
    from .sources import load_archive, load_kmda
    kmda_last = load_kmda()[1]["last_start_local"].replace("T", " ")[:16]
    import pandas as _pd
    from .config import source_path
    off_all = _pd.to_datetime(_pd.read_csv(source_path("official"), usecols=["started_at"]).started_at,
                              utc=True, format="mixed").max()
    arc_last = load_archive()[1]["snapshot_utc"]
    L = ["| Джерело | Версія у `data/raw/MANIFEST.json` | Останній запис у даних |", "|---|---|---|",
         f"| KMDA, data.gov.ua (Київ) | знімок {pins['kmda']['version']} | {kmda_last} (за Києвом) |",
         f"| Офіційний канал @air_alert_ua (датасет Vadimkin) | коміт `{pins['official']['version']}` | "
         f"{off_all:%Y-%m-%d %H:%M} UTC (канал далі не публікує) |",
         f"| alerts.in.ua (архів JustJimer) | коміт `{pins['alerts_in_ua']['version']}` | "
         f"{arc_last:%Y-%m-%d %H:%M} UTC |",
         "", f"Остання повна доба в аналізі: **{last_day:%d.%m.%Y}**."]
    return "\n".join(L)


if __name__ == "__main__":
    print(forecast_next_day().T)
