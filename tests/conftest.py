"""All tests run on the real pinned data (no synthetic fixtures, see DECISIONS.md D-01)."""
import pytest

from airalerts.build import build


@pytest.fixture(scope="session")
def built():
    daily, records, checks = build()
    return daily, records, checks
