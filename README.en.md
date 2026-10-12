# Air-raid alerts in autumn 2026: what changed, where, and can it be forecast

*Short English version. The full project is in Ukrainian: [README.md](README.md),
details in [REPORT.md](REPORT.md).*

Test task, stage 2, KSE Agentic AI School 2026 (October 2026), by Toros-Manuk Petrychenko,
2nd-year Applied Mathematics, KSE, built together with AI agents. Python, time-series
analysis, a next-day forecast without leakage.

We started by asking whether Kyiv's alert regime changed. The break turned out to be
regional, so we extended the analysis to all oblast centres, built a shared forecast model
and a map.

> **Question.** What changed in the air-raid alert regime in autumn 2026, where, and can
> daily alert hours be forecast honestly when the regime changes?
>
> **Short answer.**
> - **Regime.**
>   - Kyiv had an abrupt break on 27 Aug 2026, 10 days before the alert rules changed.
>     Alert hours per day went from **1.7 to 8.1**, mostly because there were many more
>     separate alerts.
>   - The break is regional: strongest and lasting in Kyiv, Kyiv oblast (Bila Tserkva) and
>     Cherkasy oblast (Cherkasy). There is no rise in the east.
>   - Since 6 Sep, ~92% of Kyiv's alert hours are yellow level, i.e. drones.
> - **Forecast.** One shared model for 23 oblast centres.
>   - Its intervals are honest: coverage 0.82 against a nominal 0.80.
>   - Mean error is 2.14 h against 2.31 h for the best simple baseline.
>   - On the front (Chernihiv, Sumy, Kharkiv oblasts) it is worse than "same as yesterday".
> - **Trust.**
>   - Three official alert sources, cross-checked against each other.
>   - 64 tests on real data, including leakage tests.
>   - 4 independent AI agents checked the numbers, reproducibility, conclusions and leaks.
>
> **Why this question.** The exact moment of the next alert cannot be predicted, so we look
> at the regime and at alert hours per day, with an uncertainty interval.

**Next-day forecast and map** — [interactive map of Ukraine →](https://torosyasia.github.io/air-alerts-forecast/). It shows a forecast
for every oblast centre, the change after 27 Aug and alert hours over 30 days. These are
statistics and a forecast, not live alerts.

[![Map preview](figures/map_preview.png)](https://torosyasia.github.io/air-alerts-forecast/)

<!-- FORECAST_EN:START -->
**Forecast for 12 Oct 2026** (00:00–24:00 Kyiv time), issued as of 00:00 from data up to 2026-10-12 10:46 UTC.

| City | Median, h | 80% interval, h | Alert at 00:00 | Yesterday, h | Test MAE, h | Test coverage |
|---|---|---|---|---|---|---|
| Kyiv | **6.2** | 2.2 – 11.0 | no | 5.4 | 4.22 | 71% |
| Kharkiv | **15.3** | 6.8 – 21.6 | yes | 14.7 | 2.44 | 100% |
| Dnipro | **6.0** | 2.0 – 11.6 | yes | 8.4 | 2.29 | 79% |

**How far to trust it.** For Kyiv the model is only slightly better than the best simple baseline (4.2 vs 4.3 h mean error), so read the interval, not the point. This is a statistical forecast, not a threat warning.
<!-- FORECAST_EN:END -->

| Key numbers (data snapshot 12 Oct 2026, last full day 11 Oct) | |
|---|---|
| Alert hours per day right after the break (27 Aug – 5 Sep, before the reform), by oblast centre | Kyiv 1.7 → 9.4, Kyiv oblast (Bila Tserkva) 1.1 → 6.7, Cherkasy oblast (Cherkasy) 2.4 → 10.0, and the jump holds; western oblasts grew from a tiny base, mostly after 6 Sep; Kharkiv oblast (Kharkiv) 18.5 → 17.6 |
| October vs September (11 days) | significantly more alerts only in Dnipropetrovsk oblast (Dnipro) and Rivne oblast (Rivne), out of 23; no wider wave detected |

**The model: v1 → v2.**
- **v1:** separate models for 3 cities, no better than "same as yesterday" for Kyiv.
- **v2:** one shared model for 23 cities with 626 new-regime city-days. Its main gain is
  honest intervals (coverage 0.82 vs 0.71) at almost the same accuracy
  ([REPORT §6](REPORT.md#6-прогноз-від-v1-до-v2-результати-по-містах)).

**Limitations.**
- A 14-day test: for Kyiv the gap to "same as yesterday" (4.22 vs 4.29 h) is within noise.
- Outside Kyiv the source changes on 7 Sep, right after the 6 Sep reform.
- We observe alerts, not attacks.
- The Bayes factor is inflated, since days are not independent; the break date is robust.

**Why it matters.**
- **City.** Since 6 Sep, ~92% of Kyiv's alert time is yellow level, when under resolution
  No 1092 businesses with a shelter may keep working and the metro runs fully.
- **Forecasting.** Models trained on one city's history break at a regime change.
- **Data.** The official channel's open dataset silently stopped on 7 Sep. We built a
  checked series from three cross-validated sources.

**How it was done: a human + AI agents.**
- **Who did what.** Toros set the question and the rules, approved every checkpoint and
  merged every PR. Claude Code wrote the code and the analysis.
- **Rules set in advance:** no synthetic data, a strict leakage definition, a decision log,
  one commit per step.
- **Four independent checker agents** reviewed the repository without seeing the process.
  The reviewer checked the numbers, and the reproducer re-ran everything bit-identically
  from a clean clone. The devil's advocate refuted "the break is Kyiv-only", and the leak
  hunter found a small real leak, fixed test-first. See [agents/](agents/README.md); the
  human–AI chat log is in [ai_log/](ai_log/).

**Run it** (Python 3.13):
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run_all.py            # reproduce the pinned snapshot (~12 min); --latest for fresh data
.venv/bin/python -m pytest             # tests on real data
```
Step by step: [REPORT §10](REPORT.md#10-як-відтворити). Every result file: [results/README.md](results/README.md).
