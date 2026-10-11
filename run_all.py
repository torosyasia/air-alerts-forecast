"""One command for the whole pipeline: python run_all.py"""
from airalerts.build import build, load_processed
from airalerts.config import PROCESSED
from airalerts.evaluate import evaluate_baselines, write_report
from airalerts.features import build_features
from airalerts.events import main as run_events
from airalerts.models import main as run_models
from airalerts.regimes import run_report as run_regimes

if __name__ == "__main__":
    build()                                   # fetch pinned sources, daily target, data-quality report
    build_features()                          # features known at 00:00 of the forecast day
    _, daily = load_processed()
    fc, tables, per = evaluate_baselines(daily)
    fc.to_csv(PROCESSED / "baseline_forecasts.csv", index=False)
    write_report(tables, per, daily)          # reports/baselines.md
    run_models()                              # reports/models.md, results/metrics_validation_test.csv
    run_regimes()                             # reports/regimes.md, results/changepoint*.csv
    run_events()                              # reports/events.md, results/events_effects.csv
    print("done: reports/*.md, results/*.csv")
