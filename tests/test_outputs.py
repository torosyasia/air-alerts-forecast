"""Pinned data, next-day forecast and README blocks."""
import pandas as pd
import pytest

from airalerts.config import PROCESSED, RAW, RESULTS, pinned
from airalerts.fetch import sha256


def test_pinned_files_match_manifest():
    for name, pin in pinned().items():
        path = RAW / pin["file"]
        if not path.exists():
            pytest.skip(f"{name} not downloaded yet (run run_all.py)")
        assert sha256(path) == pin["sha256"], name
        assert pin["version"] in pin["url"] or pin.get("committed")


def test_next_day_forecast(built):
    if not (PROCESSED / "features.csv").exists() or not (RESULTS / "metrics_validation_test.csv").exists():
        pytest.skip("run run_all.py first")
    from airalerts.forecast import forecast_next_day
    daily, _, _ = built
    out = forecast_next_day()
    D = (pd.Timestamp(daily.date.max()) + pd.Timedelta(days=1)).date()
    assert set(out.city) == {"kyiv", "kharkiv", "dnipro"}
    assert (pd.to_datetime(out.forecast_for).dt.date == D).all()     # first day after the data
    assert ((0 <= out.q10_h) & (out.q10_h <= out.q50_h) & (out.q50_h <= out.q90_h) & (out.q90_h <= 25)).all()


def test_readme_blocks_present():
    from airalerts.config import ROOT
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for b in ("FORECAST", "DATA", "FACTS"):
        assert text.count(f"<!-- {b}:START -->") == 1 and text.count(f"<!-- {b}:END -->") == 1
