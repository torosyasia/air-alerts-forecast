"""Forecast for the first day after the data: median and 80% interval for Kyiv, Kharkiv, Dnipro.

The day D is the first Kyiv-local day after the last complete day of the data. The forecast
is issued as of D 00:00 Kyiv (only records before that moment are used, through the same
`history_at` gate as in the evaluation) by the main model chosen on validation:
quantile regression on the whole history with the midnight features (DECISIONS D-18).
Depending on when the data snapshot was taken, D is "today" or "tomorrow" for the reader.
"""
import numpy as np
import pandas as pd

from . import intervals as iv
from .build import load_processed
from .config import PROCESSED, RESULTS, TZ, pinned
from .evaluate import FORECAST_CITIES
from .features import features_at
from .models import FEATURE_SETS, fit_predict

MAIN_MODEL = "qr_full__with_midnight"
CITY_UK = {"kyiv": "Київ", "kharkiv": "Харків", "dnipro": "Дніпро"}


def forecast_next_day():
    records, daily = load_processed()
    X = pd.read_csv(PROCESSED / "features.csv")
    X["date"] = pd.to_datetime(X.date).dt.date
    D = (pd.Timestamp(daily.date.max()) + pd.Timedelta(days=1)).date()
    t0 = pd.Timestamp(D).tz_localize(TZ)
    snapshot = records.finished_at.max()
    assert snapshot >= t0.tz_convert("UTC"), "data must reach the forecast origin"
    cols = FEATURE_SETS["with_midnight"]
    cap = float(iv.day_lengths(D, D).iloc[0])
    metrics = pd.read_csv(RESULTS / "metrics_validation_test.csv")
    rows = []
    for city in FORECAST_CITIES:
        d = daily[daily.city == city]
        missing = frozenset(d.date[d.hours.isna()])
        f = pd.Series(features_at(records[records.city == city], D, missing))
        train = X[(X.city == city) & (X.date < D)].dropna(subset=cols + ["y"])
        q = np.clip(fit_predict(train, f, cols), 0, cap)
        m = metrics[(metrics.period == "test") & (metrics.city == city) & (metrics.method == MAIN_MODEL)].iloc[0]
        rows.append({"city": city, "forecast_for": D, "issued_as_of_kyiv": f"{D} 00:00",
                     "q10_h": round(q[0], 1), "q50_h": round(q[1], 1), "q90_h": round(q[2], 1),
                     "alert_running_at_00": bool(f.active_t0), "hours_yesterday": round(f.h_lag1, 1),
                     "mean_last_7d": round(f.h_mean7, 1), "model": MAIN_MODEL,
                     "test_MAE_h": round(m.MAE, 2), "test_coverage80": round(m.coverage80, 2),
                     "data_snapshot_utc": snapshot.strftime("%Y-%m-%d %H:%M")})
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "forecast_next_day.csv", index=False)
    return out


def markdown(out):
    D = out.forecast_for.iloc[0]
    L = [f"**Прогноз на {pd.Timestamp(D):%d.%m.%Y}** (доба 00:00–24:00 за Києвом), зроблений станом на "
         f"{pd.Timestamp(D):%d.%m} 00:00 з даних до {out.data_snapshot_utc.iloc[0]} UTC. "
         "Модель — квантильна регресія на всій історії (обрана на валідації).", "",
         "| Місто | Медіана, год | 80% інтервал, год | Тривога о 00:00 | Учора, год | Середнє за 7 днів, год | MAE моделі на тесті | Покриття на тесті |",
         "|---|---|---|---|---|---|---|---|"]
    for _, r in out.iterrows():
        L.append(f"| {CITY_UK[r.city]} | **{r.q50_h:.1f}** | {r.q10_h:.1f} – {r.q90_h:.1f} | "
                 f"{'так' if r.alert_running_at_00 else 'ні'} | {r.hours_yesterday:.1f} | {r.mean_last_7d:.1f} | "
                 f"{r.test_MAE_h:.2f} | {r.test_coverage80:.0%} |")
    L += ["", "Інтервал широкий, бо київські дні мінливі й кластеризуються (розширення 1). "
          "Це статистичний прогноз, а не попередження про загрозу. Файл: "
          "[`results/forecast_next_day.csv`](results/forecast_next_day.csv)."]
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
