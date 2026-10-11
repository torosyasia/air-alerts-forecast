# air-alerts-forecast

Чи змінився режим повітряних тривог у Києві восени 2026 року, і як чесно прогнозувати
добові години тривоги, коли режим змінюється? Прогноз робимо для Києва, Харкова і Дніпра;
Львів — лише описове порівняння.

> Робота триває: повний README (результати, метод, обмеження) з'явиться на CP7.
> Рішення і їх обґрунтування — у [DECISIONS.md](DECISIONS.md), якість даних — у
> [reports/data_quality.md](reports/data_quality.md).

## Запуск
Python 3.13 (перевірено на 3.13.16), залежності з зафіксованими версіями — у `requirements.txt`.
Перший запуск завантажує ~45 МБ сирих даних із зафіксованих комітів і звіряє sha256
(`data/raw/MANIFEST.json`); у репозиторії лежить лише знімок KMDA.
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run_all.py           # усе: дані -> ціль -> ознаки -> baselines -> звіти (~2 хв)
.venv/bin/python -m pytest            # тести на реальних даних, зокрема leakage-тести (~1.5 хв)
```
Окремі кроки: `python -m airalerts.build` (дані і ціль), `python -m airalerts.features`
(ознаки), `python -m airalerts.evaluate` (baselines).

## Поточний стан (CP3): baselines на тесті 26.09–09.10.2026
| Місто | Середнє y, год/добу | Найменший MAE | Найменший interval score | Покриття 80% (найкращий за interval score) |
|---|---|---|---|---|
| Київ | 9.51 | 4.30 (вчора) | 20.3 (медіана 7 днів) | 0.43 |
| Харків | 16.57 | 2.20 (climatology28) | 13.2 (climatology28) | 0.79 |
| Дніпро | 5.65 | 2.56 (медіана 7 днів) | 15.5 (climatology28) | 0.86 |

Повні таблиці — у [reports/baselines.md](reports/baselines.md). Моделі (квантильна регресія,
вся історія vs свіже вікно) додаються на CP4.

## Дані (стан на 10.10.2026)
| Джерело | Останній запис у даних |
|---|---|
| KMDA, data.gov.ua (м. Київ, рівні і причини загроз) | 2026-10-04 23:32 за Києвом |
| Офіційний Telegram-канал @air_alert_ua (через Vadimkin/ukrainian-air-raid-sirens-dataset) | 2026-09-07 05:28 UTC |
| alerts.in.ua (через JustJimer/ukraine-air-alert-stats) | 2026-10-10 09:50 UTC |
