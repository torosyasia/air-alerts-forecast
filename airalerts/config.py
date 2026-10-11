"""Project-wide constants: time zone, pinned data sources, cities and stitching rules.

Every number the pipeline uses comes from one of the sources below. Sources that
upstream versions in git are pinned to a commit; the KMDA file on data.gov.ua is
overwritten in place upstream, so its snapshot is committed to this repo.
"""
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
RESULTS = ROOT / "results"  # small committed result tables, readable on GitHub

TZ = "Europe/Kyiv"  # the forecast day D is [00:00, 24:00) Kyiv local time

# --- sources -----------------------------------------------------------------
OFFICIAL_SHA = "7ccd4367b7057a4541ce109ca09cf1f0220f6a75"  # Vadimkin/ukrainian-air-raid-sirens-dataset
ARCHIVE_SHA = "3b0e7f1dc7e0e04e85db73f8a24b3e587d3e05ee"   # JustJimer/ukraine-air-alert-stats

SOURCES = {
    # Parsed from the official Telegram channel @air_alert_ua, UTC. Ends 2026-09-07.
    "official": {
        "url": "https://raw.githubusercontent.com/Vadimkin/ukrainian-air-raid-sirens-dataset/"
               f"{OFFICIAL_SHA}/datasets/official_data_uk.csv",
        "path": RAW / f"official_data_uk_{OFFICIAL_SHA[:7]}.csv",
        "sha256": "1f50085481d229f57b624d83b1ce723e884dea409c14afb5b7040c8a2f233e4f",
    },
    # Raw alerts.in.ua API records archived daily by a GitHub Action, UTC, with alert_level.
    "alerts_in_ua": {
        "url": "https://raw.githubusercontent.com/JustJimer/ukraine-air-alert-stats/"
               f"{ARCHIVE_SHA}/archive/alerts_in_ua.csv",
        "path": RAW / f"alerts_in_ua_{ARCHIVE_SHA[:7]}.csv",
        "sha256": "e140f876e2cc3cb4160c9d65c72297747abf53e29d7cc316c05452969d682053",
    },
    # Kyiv City State Administration open data, naive Kyiv local time, with level and cause.
    "kmda": {
        "url": "https://data.gov.ua/dataset/83eda433-b4d9-47ac-89a0-5868dd4d5ce6/resource/"
               "08559e6a-863f-4d9b-86c1-d23e8b8b4630/download/airalerts.json",
        "path": RAW / "kmda_airalerts_2026-10-10.json",
        "committed": True,  # never re-downloaded by fetch; a refresh is a new dated snapshot
        "sha256": "0c9ef4fc776ef695d818127ff5d11f9a9e994acf703c063e97b89f332c07e44b",
    },
}

# The archive is filled from an API whose history reaches one month back; its first sync
# ran 2026-10-06 ~12:00 UTC, so it is complete only from about 2026-09-06 12:00 UTC.
ARCHIVE_COMPLETE_FROM = pd.Timestamp("2026-09-06 12:00", tz="UTC")
# The official Telegram feed's last post is 2026-09-07 06:09 UTC (#338380).
OFFICIAL_COMPLETE_UNTIL = pd.Timestamp("2026-09-07 06:09", tz="UTC")
# Switch from the official CSV to the archive at a Kyiv midnight inside the window where
# both are complete (checked in build.py on the overlap).
OFFICIAL_TO_ARCHIVE_CUT = pd.Timestamp("2026-09-07 00:00", tz=TZ)

# The official channel parser closes an alert it never saw end at start + 1 h. Such rows
# are not observations; DECISIONS.md: drop them and report a sensitivity check.
IMPUTED_DURATION_S = 3600


@dataclass(frozen=True)
class City:
    key: str
    name_uk: str
    oblast_uk: str          # oblast name as in the official CSV / archive
    raion_uk: str | None    # raion that contains the city
    hromada_prefix: str | None  # hromada / city unit name prefix
    forecast: bool          # part of the forecast set (Lviv is descriptive only)
    kyiv_kmda: bool = False  # Kyiv uses KMDA as its primary source
    archive_titles: tuple = field(default_factory=tuple)  # covering unit titles in the archive


CITIES = {
    "kyiv": City("kyiv", "Київ", "м. Київ", None, None, forecast=True, kyiv_kmda=True,
                 archive_titles=("м. Київ",)),
    "kharkiv": City("kharkiv", "Харків", "Харківська область", "Харківський район", "м. Харків та",
                    forecast=True,
                    archive_titles=("Харківська область", "Харківський район",
                                    "Харківська територіальна громада", "м. Харків")),
    "dnipro": City("dnipro", "Дніпро", "Дніпропетровська область", "Дніпровський район", "м. Дніпро та",
                   forecast=True,
                   archive_titles=("Дніпропетровська область", "Дніпровський район",
                                   "Дніпровська територіальна громада", "м. Дніпро")),
    "lviv": City("lviv", "Львів", "Львівська область", "Львівський район", "м. Львів та",
                 forecast=False,
                 archive_titles=("Львівська область", "Львівський район",
                                 "Львівська територіальна громада", "м. Львів")),
}

# Gap (seconds) below which two alert records are treated as one episode when counting
# episodes. A change of threat level is a new record with no "all clear" in between.
EPISODE_GAP_S = 60
