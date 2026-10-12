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
# Which version of each source is used is recorded in data/raw/MANIFEST.json (url with the
# exact commit, local file, sha256) - the single source of truth for the pinned snapshot.
# `python run_all.py --latest` downloads the newest versions and rewrites the manifest.
MANIFEST = RAW / "MANIFEST.json"
SOURCE_SPECS = {
    # Parsed from the official Telegram channel @air_alert_ua, UTC. Ends 2026-09-07.
    "official": {"repo": "Vadimkin/ukrainian-air-raid-sirens-dataset", "branch": "main",
                 "file": "datasets/official_data_uk.csv", "local": "official_data_uk_{ver}.csv"},
    # Raw alerts.in.ua API records archived daily by a GitHub Action, UTC, with alert_level.
    "alerts_in_ua": {"repo": "JustJimer/ukraine-air-alert-stats", "branch": "main",
                     "file": "archive/alerts_in_ua.csv", "local": "alerts_in_ua_{ver}.csv"},
    # Kyiv City State Administration open data, naive Kyiv local time, with level and cause.
    # data.gov.ua overwrites the file in place, so dated snapshots are committed to this repo.
    "kmda": {"url": "https://data.gov.ua/dataset/83eda433-b4d9-47ac-89a0-5868dd4d5ce6/resource/"
                    "08559e6a-863f-4d9b-86c1-d23e8b8b4630/download/airalerts.json",
             "local": "kmda_airalerts_{ver}.json", "committed": True},
}


def pinned():
    """{source: {url, file, sha256, version, committed}} from data/raw/MANIFEST.json."""
    import json
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def source_path(name):
    return RAW / pinned()[name]["file"]


# The archive is filled from an API whose history reaches one month back; its first sync
# ran 2026-10-06 ~12:00 UTC, so it is complete only from about 2026-09-06 12:00 UTC.
ARCHIVE_COMPLETE_FROM = pd.Timestamp("2026-09-06 12:00", tz="UTC")
# The official Telegram feed's last post is 2026-09-07 06:09 UTC (#338380).
OFFICIAL_COMPLETE_UNTIL = pd.Timestamp("2026-09-07 06:09", tz="UTC")
# Switch from the official CSV to the archive at a Kyiv midnight inside the window where
# both are complete (checked in build.py on the overlap).
OFFICIAL_TO_ARCHIVE_CUT = pd.Timestamp("2026-09-07 00:00", tz=TZ)


def kmda_to_archive_cut():
    """Kyiv: KMDA until local midnight of this day, alerts.in.ua from it (D-05).

    The day is the last day present in the pinned KMDA snapshot (it may be partial, so it
    comes from the archive). It is fixed when the snapshot is pinned (fetch.py) and stored in
    MANIFEST.json, not derived from the data inside the backtest: otherwise which source
    supplies the days before D would depend on KMDA records published after D 00:00 - a leak
    found by the leak-hunter agent (agents/leak_hunter.md).
    """
    return pd.Timestamp(pinned()["kmda"]["kyiv_archive_from"]).tz_localize(TZ)

# Documented outages of the official channel (no posts for the whole country). Posts #334744
# (last normal post) and #334746 (first post after); #334745 on 2026-08-30 12:42 UTC reads
# "З технічних причин тимчасово не працює публікація повідомлень в цьому каналі".
# Days overlapping an outage are missing (NaN) for cities whose source is the official CSV.
OFFICIAL_OUTAGES = [(pd.Timestamp("2026-08-29 04:55:28", tz="UTC"), pd.Timestamp("2026-09-02 13:48:04", tz="UTC"))]

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

# All oblast centres on government-controlled territory, for the all-Ukraine map and the
# shared forecast model (airalerts/national.py). Same covering rule as above: the oblast, the
# raion that contains the city, the city hromada (official CSV) or the city / hromada units
# (alerts.in.ua archive). Names were checked against both sources. The four cities above are
# reused unchanged. Centres under occupation are not modelled (OCCUPIED_CENTRES).
def _centre(key, name, oblast, raion, hromada_adj=None):
    titles = (oblast, raion, f"м. {name}") + ((f"{hromada_adj} територіальна громада",) if hromada_adj else ())
    return City(key, name, oblast, raion, f"м. {name} та", forecast=True, archive_titles=titles)


ALL_CITIES = {
    "kyiv": CITIES["kyiv"],
    "kharkiv": CITIES["kharkiv"],
    "dnipro": CITIES["dnipro"],
    "lviv": CITIES["lviv"],
    "vinnytsia": _centre("vinnytsia", "Вінниця", "Вінницька область", "Вінницький район", "Вінницька"),
    "lutsk": _centre("lutsk", "Луцьк", "Волинська область", "Луцький район", "Луцька"),
    "zhytomyr": _centre("zhytomyr", "Житомир", "Житомирська область", "Житомирський район", "Житомирська"),
    "uzhhorod": _centre("uzhhorod", "Ужгород", "Закарпатська область", "Ужгородський район", "Ужгородська"),
    "zaporizhzhia": _centre("zaporizhzhia", "Запоріжжя", "Запорізька область", "Запорізький район", "Запорізька"),
    "ivano_frankivsk": _centre("ivano_frankivsk", "Івано-Франківськ", "Івано-Франківська область",
                               "Івано-Франківський район", "Івано-Франківська"),
    "kropyvnytskyi": _centre("kropyvnytskyi", "Кропивницький", "Кіровоградська область", "Кропивницький район",
                             "Кропивницька"),
    "mykolaiv": _centre("mykolaiv", "Миколаїв", "Миколаївська область", "Миколаївський район", "Миколаївська"),
    "odesa": _centre("odesa", "Одеса", "Одеська область", "Одеський район", "Одеська"),
    "poltava": _centre("poltava", "Полтава", "Полтавська область", "Полтавський район", "Полтавська"),
    "rivne": _centre("rivne", "Рівне", "Рівненська область", "Рівненський район", "Рівненська"),
    "sumy": _centre("sumy", "Суми", "Сумська область", "Сумський район", "Сумська"),
    "ternopil": _centre("ternopil", "Тернопіль", "Тернопільська область", "Тернопільський район", "Тернопільська"),
    "kherson": _centre("kherson", "Херсон", "Херсонська область", "Херсонський район", "Херсонська"),
    "khmelnytskyi": _centre("khmelnytskyi", "Хмельницький", "Хмельницька область", "Хмельницький район",
                            "Хмельницька"),
    "cherkasy": _centre("cherkasy", "Черкаси", "Черкаська область", "Черкаський район", "Черкаська"),
    "chernivtsi": _centre("chernivtsi", "Чернівці", "Чернівецька область", "Чернівецький район", "Чернівецька"),
    "chernihiv": _centre("chernihiv", "Чернігів", "Чернігівська область", "Чернігівський район", "Чернігівська"),
}
OCCUPIED_CENTRES = {"Донецька область": "Донецьк", "Луганська область": "Луганськ",
                    "Автономна Республіка Крим": "Сімферополь", "м. Севастополь": "Севастополь"}

# Gap (seconds) below which two alert records are treated as one episode when counting
# episodes. A change of threat level is a new record with no "all clear" in between.
EPISODE_GAP_S = 60
