"""One command for the whole pipeline.

    python run_all.py            # reproduce the pinned snapshot (data/raw/MANIFEST.json)
    python run_all.py --latest   # download the newest data, re-pin it, rebuild everything

Both modes regenerate results/, reports/, figures/ and the auto-generated blocks of README.md
(forecast for the next day, data dates), README.en.md (forecast) and REPORT.md (data dates, facts, test results).
"""
import argparse
import time

from airalerts import evaluate, forecast, readme, stats
from airalerts.build import build, load_processed
from airalerts.config import PROCESSED, ROOT
from airalerts.events import main as run_events
from airalerts.features import build_features
from airalerts.fetch import fetch_latest
from airalerts.figures import main as run_figures
from airalerts.models import main as run_models
from airalerts.neighbours import main as run_neighbours
from airalerts.national_map import main as run_national
from airalerts.process import main as run_process
from airalerts.regimes import run_report as run_regimes


def step(name, fn):
    t = time.time()
    out = fn()
    print(f"[run_all] {name:<34} {time.time() - t:6.1f} s")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--latest", action="store_true", help="download the newest data and re-pin the manifest")
    args = ap.parse_args()
    if args.latest:
        step("fetch newest data (re-pin)", fetch_latest)
    step("data -> daily target + QA report", build)                    # verifies pins, builds target
    step("features known at 00:00", build_features)
    _, daily = load_processed()

    def baselines():
        fc, tables, per = evaluate.evaluate_baselines(daily)
        fc.to_csv(PROCESSED / "baseline_forecasts.csv", index=False)
        evaluate.write_report(tables, per, daily)
    step("baselines (rolling origin)", baselines)
    step("quantile regression models", run_models)
    step("regimes: change point, H1-H3", run_regimes)
    step("events: placebo permutation", run_events)
    step("Poisson vs clustering", run_process)
    step("neighbour oblasts on 27.08", run_neighbours)
    step("facts per city", stats.main)
    step("all Ukraine: target, shared model, map", run_national)   # the main forecast model
    fc = step("forecast for the next day", forecast.forecast_next_day)
    step("figures", run_figures)
    def blocks():
        data = forecast.data_markdown()
        readme.update_blocks({"FORECAST": forecast.markdown(fc), "DATA": data}, ROOT / "README.md")
        readme.update_blocks({"FORECAST_EN": forecast.markdown_en(fc)}, ROOT / "README.en.md")
        readme.update_blocks({"DATA": data, "RESULTS": forecast.results_markdown(),
                              "FACTS": stats.markdown(stats.main())}, ROOT / "REPORT.md")
    step("README + REPORT auto blocks", blocks)
    summary()


def summary():
    """Short console summary: data dates, the forecast for the four main cities, where files are."""
    import pandas as pd
    from airalerts.config import RESULTS, pinned
    f = pd.read_csv(RESULTS / "forecast_next_day_all.csv").set_index("city")
    d = pd.read_csv(RESULTS / "daily_target.csv")
    print("\n[run_all] done.")
    print("  data:     " + ", ".join(f"{k} {v['version']}" for k, v in pinned().items())
          + f"; last full day {d.date.max()}; data up to {f.data_snapshot_utc.iloc[0]} UTC")
    print(f"  forecast for {f.forecast_for.iloc[0]} (median, 80% interval, hours under alert):")
    for c in ("kyiv", "kharkiv", "dnipro", "lviv"):
        r = f.loc[c]
        print(f"    {r['name']:<8} {r.q50_h:5.1f}  [{r.q10_h:.1f} - {r.q90_h:.1f}]   test MAE {r.test_MAE_h:.2f} h "
              f"vs best simple {r.best_baseline_test_MAE_h:.2f} h")
    print("  files:    results/ (see results/README.md), reports/, figures/, docs/ (map), "
          "README.md, README.en.md, REPORT.md")


if __name__ == "__main__":
    main()
