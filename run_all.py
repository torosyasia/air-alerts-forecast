"""One command for the whole pipeline.

    python run_all.py            # reproduce the pinned snapshot (data/raw/MANIFEST.json)
    python run_all.py --latest   # download the newest data, re-pin it, rebuild everything

Both modes regenerate results/, reports/, figures/ and the auto-generated blocks of README.md
(forecast for the next day, data dates).
"""
import argparse
import time

from airalerts import evaluate, forecast, readme, stats
from airalerts.build import build, load_processed
from airalerts.config import PROCESSED
from airalerts.events import main as run_events
from airalerts.features import build_features
from airalerts.fetch import fetch_latest
from airalerts.figures import main as run_figures
from airalerts.models import main as run_models
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
    step("facts per city", stats.main)
    fc = step("forecast for the next day", forecast.forecast_next_day)
    step("figures", run_figures)
    step("README auto blocks", lambda: readme.update_blocks({
        "FORECAST": forecast.markdown(fc), "DATA": forecast.data_markdown(),
        "RESULTS": forecast.results_markdown(),
        "FACTS": stats.markdown(stats.main())}))
    print("[run_all] done: results/, reports/, figures/, README blocks")


if __name__ == "__main__":
    main()
