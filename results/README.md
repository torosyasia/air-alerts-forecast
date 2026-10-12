# Файли результатів

Усі файли перегенеровує `run_all.py` для поточного знімка даних (`data/raw/MANIFEST.json`).

**Загальні позначення:**
- **Час:** дати — доба за Києвом (00:00–24:00); години — години тривоги за добу.
- **Міста:** `city` — ключ міста: `kyiv`, `kharkiv`, `dnipro`, `lviv`, а для всієї України
  також обласні центри і `bila_tserkva` (місто-представник Київської області).
- **Методи:** `q10`, `q50`, `q90` — нижня межа 80% інтервалу, медіана і верхня межа.
  `MAE` — середня абсолютна помилка медіани в годинах. `coverage80` — частка днів, коли
  факт потрапив у 80% інтервал. `interval_score` (IS) — ширина інтервалу плюс штраф ×10 за
  промах, менше — краще. Терміни пояснено в [глосарії](../docs/GLOSSARY.md).

## Ціль
| Файл | Що в ньому | Колонки |
|---|---|---|
| `daily_target.csv` | Години тривоги за добу для 4 досліджених міст, з 16.03.2022 | `hours` — години під тривогою (об'єднання інтервалів); `hours_yellow`, `hours_red`, `hours_none` — розбивка за рівнем (червоний > жовтий > без рівня); `n_episodes` — кількість окремих тривог (стартів); `day_len_h` — довжина доби (23/24/25 год); `source` — джерело (`kmda`, `official`, `alerts_in_ua`); `long_alert` — є тривога > 24 год; `missing` — пропуск даних (тоді цифри NaN) |
| `national_daily_target.csv` | Те саме для 23 міст (усі обласні центри + Біла Церква) | ті самі, крім `hours_none`, `day_len_h`, `long_alert` |
| `national_data_checks.csv` | Перевірка даних по кожному з 23 міст | `missing_days`; `long_alert_days`; `stitch_official_h`, `stitch_archive_h`, `stitch_diff_h` — години на перекритті двох джерел (06.09 12:00 – 07.09 06:09 UTC) і різниця; `archive_units` — які одиниці alerts.in.ua покривають місто; `archive_days_with_alert_share`; `issues` — позначені проблеми |

## Прогноз
| Файл | Що в ньому | Колонки |
|---|---|---|
| `forecast_next_day_all.csv` | **Прогноз на наступну добу для всіх 23 міст**, головна (спільна) модель | `forecast_for` — доба прогнозу; `issued_as_of_kyiv` — момент прогнозу (00:00); `q10_h`, `q50_h`, `q90_h`; `alert_running_at_00` — чи йде тривога о 00:00; `hours_yesterday`; `mean_last_7d`; `model`; `test_MAE_h`, `test_coverage80` — точність моделі на тесті в цьому місті; `best_baseline_test_MAE_h`, `best_baseline` — найкращий простий прогноз на тесті; `data_snapshot_utc` — до якого моменту є дані |
| `forecast_next_day.csv` | Ті самі рядки для Києва, Харкова і Дніпра (для README) | ті самі, без `name`, `oblast`, `best_baseline` |
| `national_metrics.csv` | Метрики всіх методів для 23 міст: валідація і тест, по кожному місту й разом (`city = pooled`) | `method` (`qr_shared` — головна, `qr_city` — окремі моделі, `qr_shared_fresh84` — спільна на 84 днях, далі прості прогнози); `n`; `MAE`; `relMAE` — MAE відносно «як учора»; `coverage80` і 95% інтервал Вілсона `cov_lo95`–`cov_hi95`; `width`; `interval_score`; `pinball`; `period`; `kind` (`model` / `baseline`); `main` — головна модель |
| `national_city_test.csv` | Тест по містах: головна модель проти найкращого простого прогнозу | `model_MAE_h`, `model_IS`, `model_coverage80`; `best_baseline_MAE_h`, `best_baseline_by_MAE`, `best_baseline_IS`; `model_beats_baseline_MAE`, `model_beats_baseline_IS` |
| `metrics_validation_test.csv` | Модель v1 (окремо для 3 міст, CP4): метрики всіх варіантів і простих прогнозів | як у `national_metrics.csv`, без `relMAE` і `main` |

## Злам і механізм
| Файл | Що в ньому | Колонки |
|---|---|---|
| `changepoints.csv` | Байєсівська точка зламу для 4 міст (з 01.06) | `series` — шкала (`sqrt_hours`, `sqrt_episodes`); `map` — найімовірніша дата; `p_map`; `hpd95_from`, `hpd95_to`, `hpd95_days` — 95% HPD-набір; `p_before_reform`; `log10_BF_change_vs_none`; `hours_before/after`, `episodes_before/after` — середні по обидва боки `map` |
| `changepoint_posteriors.csv` | Ймовірність кожної дати зламу | `tau` — дата; далі по стовпчику на місто і шкалу |
| `day_night_hours.csv` | Нічні (00–06) і денні (06–24) години тривоги на добу до і після 27.08 | `period`, `night`, `day` |
| `process_poisson_vs_clustering.csv` | Пуассон чи пачки, до і після 27.08 | `dispersion_D` і `p_overdispersion`; `dispersion_D_within_week` — те саме в межах 7-денних блоків; `lag1_autocorr_daily`; `quiet_gap_mean_h`, `quiet_gap_cv` — пауза між тривогами; `ks_p_exponential`; `share_gaps_lt_1h` проти `expected_share_lt_1h_if_poisson` |
| `national_centre_change.csv` | Зміна після 27.08 для кожного з 23 міст — шар карти | `hours_before`, `hours_after` — 60 днів до 27.08 проти 27.08 – остання доба; `hours_delta` — приріст; `hours_ratio`; `alerts_before`, `alerts_after`; `days_before`, `days_after`; `window`; `hours_27_08_05_09` (і `days_27_08_05_09`) — перші дні після зламу, до реформи, одне джерело; `hours_from_06_09` — після реформи |
| `neighbour_oblasts.csv`, `national_oblast_change.csv` | Уся область, будь-яка тривога (метод fig9, офіційний канал): 60 днів до 27.08 проти 27.08–06.09. Перший файл — вибрані області для fig9, другий — усі | `share_of_day_under_alert_before` (≥ 0.6 — насичено); `alerts_per_day_before/after`, `alerts_ratio`; `hours_per_day_before/after`, `hours_ratio`; `p_alerts_more_mw`; `corr_daily_alerts_with_kyiv_before` |
| `national_recent.csv` | Останні 30 днів і жовтень проти 07.09–30.09 | `hours_per_day_30d`; `hours_sep`, `hours_oct`, `alerts_sep`, `alerts_oct` та їхні відношення; `p_hours_oct_more`, `p_alerts_oct_more` (Манн–Вітні, одностороннє); `october_growth` — p < 0.05 і ≥ +25% |
| `events_effects.csv` | Тривоги навколо подій (вікно [−1, +3] дні) проти локальних плацебо | `category`; `n_events`; `hours_event_window`; `hours_local_placebo`; `excess_h` і 95% смуга плацебо `excess_ci95_lo`–`excess_ci95_hi`; `share_events_above_local`; `p_more`, `p_less` |

## Факти
| Файл | Що в ньому | Колонки |
|---|---|---|
| `city_facts.csv` | Цікаві факти по 4 містах після чистки | `episodes_total`, `hours_total`; `share_time_under_alert` і `share_<рік>`; `share_days_without_alert`; `median_episode_min`; найдовша тривога, тиша, рекордні доби (`longest_*`, `record_*`); `busiest_month` |
