# Агент 4: мисливець за витоками

**Роль.** Агент шукає будь-який шлях, яким інформація з моменту після прогнозу (D 00:00
за Києвом) може потрапити в прогноз або в його оцінку. Якщо знаходить, пише тест, що падає,
і виправлення пропонує, але не робить. Процесу не бачив.

**Коли.** 12.10.2026 (за UTC ще 11.10), на `main` після merge PR #3 (коміт `886f069`),
паралельно з [адвокатом диявола](devils_advocate.md). Працював ~14 хв.

**Головна ідея агента.** Наші тести на leakage збурювали вже **оброблені** записи. Тому
вони не могли побачити витік усередині `build.py`: у склейці джерел, обрізанні знімка,
обробці збою каналу чи прапорцях пропусків. Агент зробив «as-of rebuild»:
- увесь конвеєр перебудовується з **сирих** даних, обрізаних на момент t0;
- усе, що почалось після t0, викидається;
- тривога, що йде о t0, отримує довільний кінець: t0 + 1 с або t0 + 60 днів;
- ознаки дня D з такої перебудови мають бітово збігтися з ознаками з реального конвеєра.

Тести — у [`tests/test_leak_hunt.py`](../tests/test_leak_hunt.py), без змін від агента.

## Знайдено
### L1. Точка склейки KMDA → alerts.in.ua залежала від майбутнього — **витік, виправлено**
- **Що було.** `build.py` брав момент перемикання Києва з KMDA на alerts.in.ua як північ
  останнього дня, що є в KMDA (04.10). Тобто яке джерело дає дні до D, залежало від
  записів, опублікованих після D 00:00.
- **Що показала as-of перебудова.** Склейка лягає на D−1, і день D−1 береться з архіву
  alerts.in.ua. Для днів 08.09–04.10 ознаки Києва відрізнялись:
  - години вчора — до 0.09 год;
  - середня кількість тривог за 7 днів — до 0.29;
  - «тривога о 00:00» перемикалась у 2 днях.
- **Тест, що падав.** `test_kyiv_features_equal_as_of_rebuild` на 10.09 (валідація) і
  01.10 (тест) — закомічено окремо, червоним: [`6381f59`](https://github.com/torosyasia/air-alerts-forecast/commit/6381f59).
- **Масштаб — малий і без систематичного напрямку.** Агент перерахував київську модель з
  ознаками as-of:
  - валідація: MAE 3.88 → 3.99;
  - тест: MAE 4.82 → 4.78, interval score 18.38 → 18.47;
  - покриття те саме.

  Це скоріше чутливість до того, яке з двох джерел дає вчорашній день, ніж оптимізм
  оцінки. Жоден висновок не змінюється.
- **Виправлення.** День склейки тепер закріплюється разом зі знімком у
  [`data/raw/MANIFEST.json`](../data/raw/MANIFEST.json) (`kyiv_archive_from`). Його
  рахує `fetch.py --latest` один раз на знімок, а бектест читає його як константу
  (`config.kmda_to_archive_cut`).
  - Для закріпленого знімка значення те саме (04.10), тож усі опубліковані числа
    бітово не змінились.
  - Обидва тести тепер проходять. Рішення — [DECISIONS D-14a](../DECISIONS.md).

### Баг (не витік): тривога через північ перемикання джерел губить «активна о 00:00» — **задокументовано, не виправлено**
- **Що відбувається.** `clip()` розрізає таку тривогу на два записи: один закінчується
  рівно о 00:00, інший починається рівно о 00:00. Тоді ознаки не бачать, що о півночі
  тривога йшла.
- **Де це трапилось.** Харків і Дніпро 07.09 — 2 тренувальні рядки.
- **Ефект.** ≤ 0.02 год MAE.
- **Чому не виправлено.** Виправлення змінило б саму ціль у день склейки. Тому це
  задокументовано тестом `xfail(strict=True)`: якщо баг колись виправлять, тест про це
  скаже.

## Перевірено, витоку немає
| Шлях | Як перевіряв агент |
|---|---|
| Склейка Харкова й Дніпра (фіксована 07.09), обрізання знімка архіву | as-of rebuild на 12.09 (тривога о 00:00), 05.10, 09.10, з обома варіантами кінця — бітово рівні |
| Збій каналу 29.08–02.09: обрізання на початку збою і прапорці пропусків | as-of rebuild на 31.08 (усередині збою, з «тривогою» Харкова на 109.7 год), 03.09, 06.09 — бітово рівні |
| Викидання записів із домальованим кінцем (знання «відбою так і не було») | жоден із 18 таких записів не перетинає північ, тож «тривога о 00:00» не зачеплена |
| `history_at` / `features_at`, включно з NaN для пропущених днів | усі рядки `features.csv`, усі 7 лагів, усі міста, дні переходу годинника: лаг k точно дорівнює y(D−k), жодна ознака не дорівнює y |
| Часові пояси джерел | KMDA і архів збігаються з точністю до секунд, зсуву на годину немає |
| Вибір моделі (вікно W, правило CQR, спільні дні, головна модель) | весь `models.run()` перезапущено з випадковими y на тесті: W = 84, ті самі варіанти з CQR, валідаційні прогнози й метрики бітово ті самі |
| Rolling QR, CQR, baselines | навчання лише на `date < D`, конформні помилки лише з минулих днів, baselines із `shift(≥ 1)` |
| Опублікований прогноз на завтра (`forecast.py`) | майбутні записи зсунуто, тривогу о 00:00 закінчено через 1 с або ніколи — прогноз і обрана модель ті самі |
| `regimes.py` / `events.py` | у ознаки, моделі й оцінку нічого з них не імпортується; дата реформи — константа, і її немає в ознаках моделі |

**Вже розкрите в DECISIONS (не витік коду, а свобода дослідника).**
- Спосіб інтервалів baselines змінено після того, як було видно київське покриття 0.43 на
  тесті, хоч рішення ухвалено за валідацією.
- Поріг CQR записано після перегляду валідації.
- W = 84 — край сітки.

## Слабкості наших тестів, які агент назвав
1. **Тести збурювали оброблені записи**, тож витоків у `build.py` не бачили. Виправлено:
   додано as-of rebuild.
2. **Шлях із пропущеними днями (NaN) не тестувався.** Виправлено: додано тест на всіх
   рядках.
3. **Вибір моделі й `forecast.py` не тестувались на незалежність від тесту.** Виправлено:
   додано два тести.

## Що змінилось
- **Коміти.** [`6381f59`](https://github.com/torosyasia/air-alerts-forecast/commit/6381f59) — тести
  агента (2 падають) → [`48d7f80`](https://github.com/torosyasia/air-alerts-forecast/commit/48d7f80) — виправлення L1.
- **Тести.** До 45 наших тестів додано 12 + 1 xfail.

## Точний промпт
Промпт писав Claude Code англійською, тут без змін.

```text
Role: "Leakage hunter". You have NOT seen how this project was built. Single task: find ANY path by which information from the future can leak into a forecast or into its evaluation. Time budget: about 30–40 minutes. Do not push, commit to, or modify /home/user/air-alerts-forecast; work in your own clone.

Setup:
- git clone https://github.com/torosyasia/air-alerts-forecast /tmp/leak && cd /tmp/leak && git checkout 886f06953ff617f9eda14c84c3d4c0af9f235b8e
- python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python run_all.py (~6 min; reproduces the committed snapshot) and .venv/bin/python -m pytest (~1.5 min). Network to GitHub/PyPI/data.gov.ua works through a preconfigured proxy; never disable TLS verification.

The project's leakage rule (from its DECISIONS.md D-14): the forecast for Kyiv-local day D is issued at D 00:00 Europe/Kyiv. Inputs may use only what was known before that moment: no features from day D or later; no scaling/normalisation or hyperparameter choice using the test period; no shuffled validation; for an alert that started before midnight and is still running, its end time is unknown at 00:00 (only the part before midnight and the fact it is active may be used). The target y(D) = hours of day D the city was under alert.

Where to look (code is in airalerts/): sources.py and build.py (how records are cleaned, clipped, stitched across sources, how the daily table and 'missing' days are built — can post-hoc knowledge, e.g. an outage window or a snapshot time, or the KMDA cut derived from the last record, influence features of earlier days?), features.py (history_at gate, features_at, NaN handling of missing days), evaluate.py (baselines, rolling windows, conformal bands, periods, metric computation), models.py (rolling_forecasts, training windows, dropna, CQR conformalize, choice of the fresh-window W and of the CQR rule, common_days), forecast.py (next-day forecast, model selection, CQR on past forecasts), regimes.py/events.py are analysis, not forecasting, but check whether anything from them feeds the forecast. Also think about subtle ones: time-zone/DST bugs at the midnight boundary, records whose started_at is before t0 but were only published/known later (e.g. imputed ends, records cut at an outage start using knowledge of when the outage ended), selection of model/window/threshold using test data, the 'missing' flag being decided with future knowledge, daily rolling stats with shift errors, quantile clipping by day length, features that equal the target, anything in tests/test_leakage.py that is weaker than it looks.

If you find a leak: write a pytest test (in a new file tests/test_leak_hunt.py in YOUR clone) that FAILS on the current code and demonstrates the leak on the real data, run it to show it fails, and explain the minimal fix. If you find nothing for a path: describe exactly what you checked and how (experiments you ran, e.g. perturbing data after t0 and comparing forecasts), so the absence of a leak is documented.

Final report (concise): (1) leaks found — each with file:line, mechanism, severity (does it change any reported number? estimate by how much), the failing test code, and the proposed fix; (2) paths checked with no leak found — one line each with the method of checking; (3) weaknesses of the existing leakage tests. Include the full content of tests/test_leak_hunt.py at the end (it will be committed to the project), written so that tests which document a REAL leak fail now, and tests that document checked-and-clean paths pass.
```
