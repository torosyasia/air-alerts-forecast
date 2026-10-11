# Агент 1: рецензент («скептичний аудит чисел»)

**Роль.** Незалежний скептичний рецензент. Процесу не бачив, судить лише з файлів. Нічого не
редагує. Завдання: звірити кожне число в README з файлом-джерелом, знайти висновки, сильніші
за докази, і перевірити посилання.

**Коли.** 11.10.2026, перед фінальним PR CP7, на коміті [`0048e54`](https://github.com/torosyasia/air-alerts-forecast/commit/0048e54).
Працював ~7 хв паралельно з [агентом-відтворювачем](reproducer.md).

**Результат.** Перевірив ~170 чисел. Знайшов 1 справжню помилку в коді, 1 неправильну дату, 6
неузгодженостей і 10 висновків, сильніших за докази. Битих посилань немає. Усе виправлено в
[`c80c79f`](https://github.com/torosyasia/air-alerts-forecast/commit/c80c79f).

## Що знайшов і що змінилось

| Знахідка | Що було | Що зробили |
|---|---|---|
| **Подвійне округлення в таблиці фактів** (баг у коді) | Частку спершу округлювали до 3 знаків, потім ще раз до %. Харків 2022 показував 18% замість 19%, Дніпро 2022 — 12% замість 13%, Дніпро 2025 — 24% замість 25% | `stats.py` зберігає неокруглену частку; `<1%` замість `0%` |
| **Дата переходу на районні тривоги** | «до грудня 2025 — на всю область» | За офіційним CSV: Харківська — із серпня 2025, Дніпропетровська — поступово з травня, Львівська — з вересня–листопада; додано джерело |
| **Львів має формальний злам** (log10 BF 5.0) | У висновку «злам лише в Києві» Львова не було | Додано: «формальний злам 18.09, але це падіння 0.10 → 0 год/добу» |
| **HPD Києва як суцільний інтервал** | «95% інтервал 18–27.08» | «95% HPD-набір: 18.08 і 25–27.08» (4 окремі дні) |
| **«Тривоги розтяглися на всю добу»** | Звучало як зміна добового ритму | Розподіл стартів по блоках доби значуще не змінився (χ², p = 0.13). Показник «≥ 3 з 4 блоків» росте майже автоматично, коли тривог більше. Формулювання пом'якшено |
| **«Навколо подій тривог не більше»** | Звучало як доведена відсутність ефекту | «Надлишку не виявлено; смуги широкі» |
| **«Злам цільовий»** | Висновок про намір із двох контрольних міст із 5 пропущеними днями | «Локальний (київський)»; додано помірні зміни в Харкові (тривог +21%, годин менше) |
| **Абляція «тривога о 00:00» лише з тесту** | Наводили тільки тест: −0.76 [−1.42, −0.34] | Додано валідацію: −0.44 [−1.27, +0.10], там CI містить 0 |
| **Чистота вибору моделі** | «Обрано тільки на валідації» | Додано три застереження: 84 дні — край сітки; поріг CQR встановлено після перегляду валідації; спосіб інтервалів baselines змінено після того, як тестову таблицю вже було видно |
| **«Разом на 3 містах» як критерій** | Подавалось як заздалегідь оголошене | Чесно написано, що «разом» уточнено після; по містах критерій виконується лише для Дніпра |
| **Надмірна дисперсія = кластеризація** | Одне пояснення | Додано альтернативу: зміна інтенсивності в межах періоду. Її потім перевіряв [адвокат диявола](devils_advocate.md) |
| **Застарілі числа в DECISIONS** (D-02, D-10, D-18) | Цифри до виправлення пропуску 29.08–02.09 | Оновлено |
| **Посилання на KMDA** | Інший id датасету, ніж у завантажувачі | Узгоджено з `config.py` |
| Дрібне | 1.50 проти 1.51, вікна «до» 1.5 і 1.7, автокореляція 0.30 і 0.41 без пояснення | Названо вікно або показник |

## Точний промпт
Промпт писав Claude Code англійською (агенти працюють з кодом), тут без змін.

```text
You are an independent, skeptical reviewer of a small data-science repository. You have NOT seen how it was built; judge only what is in the files. Do not edit, commit or push anything — this is a read-only review.

Repository (already checked out, branch claude/air-alert-forecast-ukraine-zu5n11): /home/user/air-alerts-forecast
Project: analysis of Ukrainian air-raid alerts (Kyiv, Kharkiv, Dnipro; Lviv descriptive), a regime change in Kyiv in autumn 2026, and a probabilistic next-day forecast. Texts are in Ukrainian.

Your tasks:
1. Read README.md and figures/README.md completely. For EVERY number or factual claim in them, find the file it should come from (results/*.csv, reports/*.md, DECISIONS.md, data/events/events.csv) and check that it matches (allow rounding). You may run small read-only Python/pandas snippets with /home/user/air-alerts-forecast/.venv/bin/python to recompute things from results/*.csv (e.g. results/daily_target.csv, results/metrics_validation_test.csv, results/changepoints.csv, results/process_poisson_vs_clustering.csv, results/events_effects.csv, results/city_facts.csv, results/day_night_hours.csv, results/forecast_next_day.csv). Do not run run_all.py and do not write files inside the repo (use /tmp for anything you need).
2. Check that conclusions are not stronger than the evidence: e.g. statistical significance claimed where CIs include 0, causal language without support, "no change" where data are missing, coverage claims vs sample size, numbers described as 'test' that come from validation, etc.
3. Check internal consistency: the same quantity reported differently in README vs figures/README vs reports vs DECISIONS; dates/periods (test period, validation period, 'before/after 27.08' windows) used consistently; figure captions matching what the figure titles/files claim (you can open PNGs in figures/ with your file-reading tool).
4. Check that links in README.md and figures/README.md point to files/anchors that exist.

Report back a concise list of findings, most important first. For each: file and line (or section), the exact text, what the source file says (with the number), and a suggested fix. Separate "wrong number / inconsistency", "claim stronger than evidence", "broken link", "minor wording". If something checks out, you don't need to list it, but at the end state roughly how many numbers you verified.
```
