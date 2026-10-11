# Агент 3: адвокат диявола

**Роль.** Для кожного головного висновку агент придумує 3–5 альтернативних пояснень і кожне
перевіряє кодом на реальних даних. Вердикт для кожного: відкинуто, частково підтверджено чи
підтверджено. Процесу агент не бачив і сам нічого не виправляв.

**Коли.** 12.10.2026 (за UTC ще 11.10), на `main` після merge PR #3 (коміт `886f069`).
Працював ~9 хв.

**Як.**
- Агент склонував репозиторій, запустив `run_all.py` і переконався, що знімок відтворюється.
- Написав скрипт на ~300 рядків: [`devils_advocate_checks.py`](devils_advocate_checks.py),
  вивід — у [`devils_advocate_output.txt`](devils_advocate_output.txt).
- Скрипт закомічено без змін логіки. Перед цим я перезапустив його у своїй копії: вивід
  збігся до символу. Окремо я перевірив головну знахідку (сусідні області) простим
  підрахунком записів з офіційного CSV, без функцій агента.

**Підсумок.** Один висновок дані спростували, два виявились здебільшого наслідком простішого
ефекту, чотири тримаються з уточненнями.

## Вердикти
Тут C1–C7 — сім головних висновків у тому вигляді, як вони стояли в README до перевірки.

### C1. Злам у Києві 27.08, до реформи 06.09 — **тримається**
| Альтернатива | Перевірка | Вердикт |
|---|---|---|
| Артефакт KMDA чи склейки джерел | Київ із незалежного офіційного каналу: теж 27.08, кількість тривог 2.07 → 7.33, кореляція з KMDA 0.997. Лише KMDA до 03.10: теж 27.08 | відкинуто |
| Кілька екстремальних днів | Без 27–30.08: злам 31.08 (перший день, що лишився). Без 10 найгірших днів — 28.08 | відкинуто |
| Вибір шкали (корінь) | log і ранги — 27.08. **Сирі години — 18.08**: окремі важкі дні 18.08 (10 тривог) і 20.08 (14 год) | частково: були «передвісники» з 18.08 |
| Вікно; реформа, а не атаки | Усі вікна дають 27.08. Вікно лише до 05.09 (до реформи) — 27.08, P = 0.96. Другого зламу після 27.08 немає | відкинуто |
| Поступове зростання, а не сходинка | Сходинка краща за лінійний перехід за BIC; найкращий «перехід» триває одну добу 26→27.08 | відкинуто |
| Змінився спосіб оголошувати (дроблення тривог) | 1.00 запису на тривогу до і після; частка < 5 хв 3.2% → 5.0% | відкинуто |

### C2. Зросла насамперед кількість тривог (~80%) — **тримається, з діапазоном**
- Без екстремальних днів — 78%; без тривог < 5 хв — 79%; за медіанами — 80%.
- **Частково:**
  - Якщо тривоги з паузою < 1 год рахувати однією хвилею, частка кількості — 56%: пауз
    ≤ 30 хв стало більше (8% → 17%).
  - Хвіст тривалості виріс помітно. 75-й процентиль тривалості 0.73 → 1.32 год (×1.8), а
    медіана лише ×1.4.

### C3. Тривоги стали частими в усі години доби — **підтверджено, що це наслідок кількості**
Агент змоделював «нульову» ситуацію: кожна доба після зламу має свою справжню кількість
тривог, але години їхнього старту взято зі **старого** добового профілю. За такої моделі
частка днів із тривогами у ≥ 3 з 4 блоків доби — 81% (73–89%). Спостерігали 84%. Тобто
«усі години доби» — це арифметичний наслідок того, що тривог утричі більше. Окремого
висновку тут немає, а добовий профіль стартів значуще не змінився (p = 0.13).

### C4. Після реформи переважають дронові (жовті) тривоги — **тримається, з діапазоном**
- За KMDA жовтих 92% годин, за alerts.in.ua — 87%. Тож правильно давати діапазон 87–92%.
- «Жовтий = дрони» — не припущення: у KMDA жовтий рівень має рівно одну причину —
  «Дронова небезпека» (168 з 168).
- Червоні години бувають у 35% днів.

### C5. Злам локальний (київський) — **СПРОСТОВАНО**
| Альтернатива | Перевірка | Вердикт |
|---|---|---|
| **Зміна регіональна, а контрольні міста — слабкий контроль** | «Будь-яка тривога в області» з офіційного каналу, 60 днів до 27.08 проти 27.08–06.09. **Київська область:** тривог ×1.8, годин ×3.5. **Черкаська:** ×1.8 / ×3.4. **Вінницька:** ×3.9 / ×3.6. Житомирська: ×2.1 / ×1.7. Найімовірніша дата зламу для Вінницької, Київської й Черкаської — теж 27.08. Для Вінницької HPD-набір вузький (25–28.08), для Київської й Черкаської — широкий. Чернігівська й Полтавська — ×1.0 | **підтверджено** |
| Харків «на стелі» | Місто Харків під тривогою 77% часу, тож київське ×4.7 там неможливе фізично | підтверджено |
| Дніпро надто шумний | Штучна сходинка ×1.25 від 27.08 методом не ловиться (BF 0.1), ×1.5 — ловиться (3.2) | підтверджено: зміни < ×1.5 у Дніпрі не видно |

### C6. Київські тривоги кластеризуються (D = 1.51, CV пауз = 1.50) — **частково спростовано**
- **Розкид між днями (D)** — це хвилі на тиждень-два, а не «густо-пусто» щодня. У межах
  тижня D = 1.03 (p = 0.43). Без тихого тижня 01–06.10 D = 1.36 (p = 0.07).
- **Пачки в межах доби — справжні.** Модель без пачок, з тією самою кількістю тривог на
  добу й тим самим добовим ритмом, дає CV пауз 1.13 (95%: 0.99–1.27) і 27% пауз < 1 год.
  Спостерігали CV 1.50 і 41%.

### C7. Надлишку тривог навколо подій не виявлено — **тримається**
- Висновок не змінюється з поправкою Голма на 15 тестів (мінімальне скориговане p = 1.00).
- Не змінюється й із «чистими» плацебо, без вікон інших подій (Київ +0.09 год, p = 0.34), і
  без подій біля 27.08.
- Інші вікна — [0, 0], [0, 1], [−3, −1] — теж нічого не дають.
- Ефекти < ~0.5 год/добу виключити не можна; це вже було сказано.

## Що змінилось після перевірки
- **C5 переписано всюди** (README, REPORT, figures/README, DECISIONS D-19):
  - замість «злам локальний (київський)» тепер «злам охопив Київ і області довкола нього, але
    не всю країну»;
  - перевірку вбудовано в конвеєр: модуль [`airalerts/neighbours.py`](../airalerts/neighbours.py),
    таблиця [`results/neighbour_oblasts.csv`](../results/neighbour_oblasts.csv), графік
    [fig9](../figures/README.md#9-чи-змінився-2708-лише-київ);
  - Харків і Дніпро тепер описано як слабкий контроль: стеля і низька чутливість.
- **C3:** «усі години доби» подано як наслідок кількості, а не окремий висновок.
- **C6:** розкид між днями і пачки в межах доби розділено. У
  [`process.py`](../airalerts/process.py) додано D у межах тижня; заголовки fig7 оновлено.
- **C1, C2, C4:**
  - додано «передвісники» 18.08 і 20.08;
  - діапазон 73–88% (56%, якщо хвилі з паузою < 1 год рахувати однією);
  - 87–92% жовтих годин;
  - незалежне підтвердження з офіційного каналу.
- Коміт: [`6818d15`](https://github.com/torosyasia/air-alerts-forecast/commit/6818d15).

## Точний промпт
Промпт писав Claude Code англійською, тут без змін.

```text
Role: "Devil's advocate" for a small data-science project. You have NOT seen how the project was built. Your job is to attack its main conclusions with alternative explanations and test each alternative on the real data with code. Time budget: about 30–40 minutes. Do not push, commit to, or modify /home/user/air-alerts-forecast; work in your own clone.

Setup:
- git clone https://github.com/torosyasia/air-alerts-forecast /tmp/devil && cd /tmp/devil && git checkout 886f06953ff617f9eda14c84c3d4c0af9f235b8e
- python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python run_all.py   (~6 min; reproduces the committed snapshot; creates data/processed/*). Network to GitHub, raw.githubusercontent.com, data.gov.ua and PyPI works through a preconfigured proxy; never disable TLS verification.
- Useful data: results/daily_target.csv (city, date, hours, hours_yellow, hours_red, hours_none, n_episodes, day_len_h, source, missing...), data/processed/city_records.csv (cleaned alert intervals per city, UTC, with source segment, level, cause), results/*.csv, reports/*.md. Code is in airalerts/ (e.g. airalerts/regimes.py episodes(), changepoint_posterior()). The project is in Ukrainian; DECISIONS.md documents every choice.

Main conclusions to attack (from README.md "Головні висновки" and DECISIONS D-19..D-21):
C1. Kyiv had an abrupt regime change on 2026-08-27, before the alert-rules reform of 2026-09-06 (Bayesian single change point; daily alert hours ~1.7 -> ~8).
C2. The increase is mainly MORE alerts per day (2.1 -> 7.2), not longer ones (~80% of the log-increase from count).
C3. After the break, alerts happen at all hours of the day (days with alerts in >=3 of 4 six-hour blocks 17% -> 84%).
C4. After the reform, drone (yellow) alerts dominate in Kyiv (91.6% of hours yellow; 168 of 170 drone records are ordinary "Дронова небезпека").
C5. The change is local to Kyiv: no sharp break in Kharkiv or Dnipro (with a data gap 29.08–02.09 for those cities).
C6. Kyiv alerts cluster (index of dispersion of daily counts 1.51, CV of quiet gaps 1.50 > 1), which explains why forecasting Kyiv is hard.
C7. No excess of alerts around holidays/negotiations/Ukrainian strikes (local placebo permutation test).

For EACH conclusion, invent 3–5 alternative explanations that would produce the same picture, and test each one with code on the data. Examples to include (add your own): stitching of data sources (Kyiv uses KMDA until 2026-10-04, then alerts.in.ua; does any jump coincide with a source switch?), a single anomalous night or a few extreme days driving the result (re-run without them / with medians / trimmed), day-of-week composition of the windows, rules change instead of attacks (e.g. did alert declaration practice change on 27.08 — are episodes shorter/split, many very short alerts < 5 min, level changes counted as new episodes?), the episode-merging tolerance (60 s) creating more 'episodes', the quiet week 01–06.10 or within-period trend causing the over-dispersion in C6 instead of clustering (e.g. dispersion within sub-windows, detrended counts), the sensitivity of C3 to the mere increase in count (compare with a null where the same number of starts is placed uniformly or according to the old hour-of-day profile), the choice of the change-point window or of sqrt transform, the data gap for C5, multiple testing for C7.

For each alternative give: what it would predict, the code/check you ran (short), the numbers, and a verdict: REJECTED / PARTIALLY SUPPORTED / SUPPORTED. If an alternative is supported or partially supported, say exactly how the conclusion's wording should change.

Final report (concise, numbers first): a table per conclusion (alternative | check | result | verdict), then a short list of recommended wording changes. Also save your analysis script(s) as a single Python file and include its full content at the end of the report (it may be committed to the project as evidence), so keep it reasonably short and runnable from the repo root with .venv/bin/python.
```
