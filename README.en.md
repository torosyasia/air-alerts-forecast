# Air raid alerts: a regime change in Kyiv and an honest forecast

*Short English version. The full project is in Ukrainian: [README.md](README.md),
details in [REPORT.md](REPORT.md).*

Test task, stage 2, KSE Agentic AI School 2026 (October 2026). Author: Toros-Manuk
Petrychenko, 2nd-year Applied Mathematics, KSE. The project analyses air-raid alert time
series and makes a next-day forecast without leakage, in Python. It was built together with
AI agents.

> **Question.** Did the air-raid alert regime in Kyiv change in autumn 2026, and how do you
> honestly forecast daily alert hours when the regime changes?
>
> **Short answer.**
> - **Yes.** It changed abruptly on **27 Aug 2026**, 10 days before the alert rules changed
>   on 6 Sep.
> - **Not only Kyiv.** Neighbouring oblasts jumped the same day; the farther oblasts we
>   checked did not.
> - **Drones.** It looks like frequent attacks by small groups of drones.
> - **Hard to forecast.** The honest forecast is a wide interval. For Kyiv the model is not
>   better than "same as yesterday".
>
> **Why this question.** The exact moment of the next alert cannot be predicted. So we look
> at the regime and at alert hours per day, with an uncertainty interval.

| Key numbers (data snapshot 10 Oct 2026) | |
|---|---|
| Kyiv alert hours per day, before → after 27 Aug | **1.7 → 8.0** |
| Separate alerts per day | 2.1 → 7.2 (about 80% of the rise in hours) |
| Kyiv, Cherkasy and Vinnytsia oblasts on 27 Aug | alert hours ≈ ×3.5 |
| Kyiv since 6 Sep: yellow (drone) level | 7.0 of 7.6 alert hours per day (~92%) |
| Kyiv forecast error: model vs "same as yesterday" | 4.8 vs 4.3 h |

**Why it matters.**
- **For the city.** Under resolution No 1092, at the yellow level businesses may keep working
  if they have a shelter, and the Kyiv metro runs fully. So in Kyiv these rules now cover
  ~92% of alert time.
- **For forecasting.** Models trained on history break exactly at a regime change: our Kyiv
  median was too low on 10 of 14 test days. Detecting the change fast matters.
- **For data.** The open dataset of the official channel silently stopped after 7 Sep, and
  the channel had an outage on 29 Aug – 2 Sep. Volunteer data missed long alerts. We built a
  checked series from three cross-validated sources.

**Next-day forecast** (updated by `run_all.py`):

<!-- FORECAST_EN:START -->
**Forecast for 12 Oct 2026** (00:00–24:00 Kyiv time), issued as of 00:00 from data up to 2026-10-12 10:46 UTC.

| City | Median, h | 80% interval, h | Alert at 00:00 | Yesterday, h | Test MAE, h | Test coverage |
|---|---|---|---|---|---|---|
| Kyiv | **4.9** | 0.0 – 11.4 | no | 5.4 | 4.30 | 79% |
| Kharkiv | **15.5** | 9.6 – 20.1 | yes | 14.7 | 2.38 | 86% |
| Dnipro | **6.4** | 3.5 – 9.9 | yes | 8.4 | 2.36 | 79% |

**How far to trust it.** For Kyiv the model is not better than the best simple baseline (4.3 vs 4.3 h mean error), so read the interval, not the point. This is a statistical forecast, not a threat warning.
<!-- FORECAST_EN:END -->

**How it was done: a human + AI agents.**
- **Who did what.** Toros set the question and the rules, approved every checkpoint and
  merged every PR. Claude Code wrote the code and the analysis.
- **Rules set in advance:** no synthetic data, a strict leakage definition, a decision log,
  one commit per step.
- **Four independent checker agents** reviewed the repository without seeing the process:
  - a **reviewer** checked ~170 numbers;
  - a **reproducer** ran everything from a clean clone; results are bit-identical;
  - a **devil's advocate** refuted the claim "the break is Kyiv-only";
  - a **leak hunter** found a real, small leak, which was fixed test-first.

  Details: [agents/](agents/README.md).

**[Interactive map of Ukraine →](https://torosyasia.github.io/air-alerts-forecast/)** — next-day forecast for every oblast centre, change after
27 Aug and alert hours over 30 days (statistics and a forecast, not live alerts).

[![Map preview](figures/map_preview.png)](https://torosyasia.github.io/air-alerts-forecast/)

**Run it** (Python 3.13):
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run_all.py            # reproduce the pinned snapshot (~6 min); --latest for fresh data
.venv/bin/python -m pytest             # tests on real data
```
Step by step: [REPORT §10](REPORT.md#10-як-відтворити).
