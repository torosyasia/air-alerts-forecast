# Агент 2: відтворювач («запуск із чистого клону»)

**Роль.** Незалежна перевірка відтворюваності. Агент клонує репозиторій у порожню теку і
виконує лише те, що написано в README в розділі «Як запустити». Потім дивиться, що змінилось у
git. Окремо агент робить пробний запуск `--latest` на найсвіжіших даних. Нічого не виправляє.

**Коли.** 11.10.2026, на коміті [`0048e54`](https://github.com/torosyasia/air-alerts-forecast/commit/0048e54), паралельно з
[рецензентом](reviewer.md). Працював ~17 хв, бо двічі запускав увесь конвеєр.

**Результат.**
- **Закріплений запуск — PASS.** Він бітово відтворює закомічені результати, включно з
  PNG: `git status` після запуску порожній.
  - Час: `run_all.py` 5 хв 34 с, pytest 45/45 за 1.5 хв.
  - Недетермінізму немає, бо генератори випадкових чисел мають фіксовані seed.
- **`--latest` — запуск PASS, але знайшлося п'ять проблем.** Усі виправлено в
  [`bdf54f7`](https://github.com/torosyasia/air-alerts-forecast/commit/bdf54f7).

## Що знайшов і що змінилось

| Знахідка | Що було | Що зробили |
|---|---|---|
| **Тест прив'язаний до знімка** | `test_missing_days_are_left_out` мав `assert days_after == 39`. З новим днем даних виходило 40, і тест падав | Тест рахує очікуване з даних. Тепер тести перевіряють властивості, а не конкретні числа |
| **Дубль знімка KMDA** | `--latest` створював новий файл KMDA, навіть коли той байт-у-байт збігався зі старим | Якщо sha256 збігається, лишається старий запис у MANIFEST, а новий файл видаляється |
| **Модель захардкоджена** | `MAIN_MODEL = "qr_full__with_midnight"`. На новому вікні валідації вона вже не найкраща, а текст і далі казав «обрана на валідації» | Головна модель щоразу обирається на валідації (найменший interval score) |
| **Ручні таблиці застарівають** | Після `--latest` таблиці результатів у README показували старий тест і суперечили автоблоку прогнозу | Таблиці результатів стали автоблоком (`RESULTS`), який перегенеровує `run_all.py` |
| **Транзитивні залежності не закріплені** | У `requirements.txt` було 7 прямих залежностей | Повний `pip freeze`: 25 пакетів |
| **Як закомітити оновлення** | README не казав, що новий знімок KMDA треба закомітити | Додано команду `git add …` і пояснення, чому інакше закріплений запуск зупиниться |

## Що з цього вийшло далі
Агент показав, що з одним днем більше даних (знімок 11.10, тест 27.09–10.10) київські
метрики моделі погіршились: MAE 5.05, покриття 71%. Я окремо перерахував порівняння на цьому
знімку. Модель у Києві вже не краща за найкращий простий прогноз за жодною метрикою:
- MAE 5.05 проти 4.17;
- interval score 19.07 проти 18.43.

Через це в README і [REPORT](../REPORT.md) висновок про прогноз переписано: головне — злам і
чесна оцінка, а не «модель перемагає baseline».

## Точний промпт
Промпт писав Claude Code англійською, тут без змін.

```text
You are an independent reproducibility checker for a small Python data-science repository. You have NOT seen how it was built. Do not push, commit to, or modify the original checkout at /home/user/air-alerts-forecast — work only in fresh clones under /tmp.

Repository: https://github.com/torosyasia/air-alerts-forecast , branch claude/air-alert-forecast-ukraine-zu5n11 (the network allows GitHub, raw.githubusercontent.com, data.gov.ua and PyPI; outbound HTTPS goes through a preconfigured proxy, do not disable TLS verification). Python 3.13 is installed as python3.

Tasks:
A. Pinned run from scratch:
   1. git clone --branch claude/air-alert-forecast-ukraine-zu5n11 https://github.com/torosyasia/air-alerts-forecast /tmp/repro_pinned
   2. Follow ONLY the instructions in its README.md section "Як запустити" (create .venv, pip install -r requirements.txt, run `python run_all.py`, then `python -m pytest`). Record wall time of each step and any errors/warnings.
   3. After the run, `git status` and `git diff --stat` in the clone: which committed files changed? For changed CSV/MD files show a short sample of what differs (e.g. `git diff -U0 results/ | head -80`, and for README.md the diff). Ideally a pinned run reproduces the committed results exactly; note any non-determinism. PNG figures may differ in bytes — just report whether they changed.
B. --latest smoke test (separate clone, so A stays clean):
   1. git clone the same branch to /tmp/repro_latest, create its own venv, install requirements, run `python run_all.py --latest`.
   2. Report: did it succeed; what versions did data/raw/MANIFEST.json change from/to (git diff data/raw/MANIFEST.json); the new last complete day and the forecast in results/forecast_next_day.csv; the README FORECAST/DATA blocks after the run; then run pytest in that clone and report.
C. Read README.md "Як запустити" and "Структура репозиторію": is anything missing or misleading for a newcomer (commands, timings, file descriptions that don't match the tree)?

Report concisely: for each of A, B, C — pass/fail, timings, exact error messages if any, and the list of differences. Be specific (file paths, line excerpts). Do not try to fix the repository yourself.
```
