"""Interactive all-Ukraine map (GitHub Pages, docs/) and its preview image.

Oblast outlines: geoBoundaries gbOpen UKR ADM1 (simplified), from OpenStreetMap / Wambacher,
licence ODbL 1.0 - pinned by commit and sha256 below, coordinates rounded to 0.01 degree
(about 1 km) to keep the page light. The page reads docs/data/map_data.json, which
run_all.py rewrites, so the map always shows the same snapshot as the README.
"""
import json
import subprocess

import numpy as np
import pandas as pd

from .config import ALL_CITIES, OCCUPIED_CENTRES, ROOT

DOCS = ROOT / "docs"
GEO_URL = ("https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/9469f09/releaseData/gbOpen/UKR/ADM1/"
           "geoBoundaries-UKR-ADM1_simplified.geojson")
GEO_SHA256 = "4a5947e7497574d51f93255dfa7e03dce0c7acf6ecee52d25773a5205854a399"
GEO_OUT = DOCS / "data" / "oblasts.geojson"
EN_UK = {
    "Kherson Oblast": "Херсонська область", "Volyn Oblast": "Волинська область", "Rivne Oblast": "Рівненська область",
    "Zhytomyr Oblast": "Житомирська область", "Kyiv Oblast": "Київська область",
    "Chernihiv Oblast": "Чернігівська область", "Sumy Oblast": "Сумська область",
    "Kharkiv Oblast": "Харківська область", "Luhansk Oblast": "Луганська область",
    "Donetsk Oblast": "Донецька область", "Zaporizhia Oblast": "Запорізька область",
    "Lviv Oblast": "Львівська область", "Ivano-Frankivsk Oblast": "Івано-Франківська область",
    "Zakarpattia Oblast": "Закарпатська область", "Ternopil Oblast": "Тернопільська область",
    "Chernivtsi Oblast": "Чернівецька область", "Odessa Oblast": "Одеська область",
    "Mykolaiv Oblast": "Миколаївська область", "Autonomous Republic of Crimea": "Автономна Республіка Крим",
    "Vinnytsia Oblast": "Вінницька область", "Khmelnytskyi Oblast": "Хмельницька область",
    "Cherkasy Oblast": "Черкаська область", "Poltava Oblast": "Полтавська область",
    "Dnipropetrovsk Oblast": "Дніпропетровська область", "Kirovohrad Oblast": "Кіровоградська область",
    "Kyiv": "м. Київ", "Sevastopol": "м. Севастополь",
}
# The four cities studied in depth: role on the map and where their analysis is
DEEP = {
    "kyiv": ("головний кейс: злам 27.08", "REPORT.md#4-висновки-з-доказами"),
    "kharkiv": ("прифронтове місто", "REPORT.md#6-прогноз-результати-по-містах"),
    "dnipro": ("активний тил", "REPORT.md#6-прогноз-результати-по-містах"),
    "lviv": ("далекий захід (лише описово)", "REPORT.md#7-цікаві-факти-з-даних"),
}
BASELINE_UK = {"yesterday": "«як учора»", "mean7": "середнє за 7 днів", "median7": "медіана за 7 днів",
               "same_weekday": "«як тиждень тому»", "climatology28": "квантилі за 28 днів"}
REPO = "https://github.com/torosyasia/air-alerts-forecast/blob/main/"


def prepare_geojson():
    """Download the pinned outlines once (if missing), check sha256, round, keep the name."""
    if GEO_OUT.exists():
        return json.loads(GEO_OUT.read_text(encoding="utf-8"))
    import hashlib
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".geojson", delete=False).name
    subprocess.run(["curl", "-sSfL", "--retry", "4", "-m", "300", "-o", tmp, GEO_URL], check=True)
    raw = open(tmp, "rb").read()
    assert hashlib.sha256(raw).hexdigest() == GEO_SHA256, "geojson sha256 mismatch"
    g = json.loads(raw)

    def rnd(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], 2), round(c[1], 2)]
        out = [rnd(x) for x in c]
        if out and isinstance(out[0][0], (int, float)):          # a ring: drop repeated points
            out = [p for i, p in enumerate(out) if i == 0 or p != out[i - 1]]
        return out
    feats = [{"type": "Feature", "properties": {"name": EN_UK[f["properties"]["shapeName"]],
                                                 "iso": f["properties"]["shapeISO"]},
              "geometry": {"type": f["geometry"]["type"], "coordinates": rnd(f["geometry"]["coordinates"])}}
             for f in g["features"]]
    out = {"type": "FeatureCollection", "source": GEO_URL, "source_sha256": GEO_SHA256,
           "licence": "ODbL 1.0 (OpenStreetMap / geoBoundaries)", "features": feats}
    GEO_OUT.parent.mkdir(parents=True, exist_ok=True)
    GEO_OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return out


def _f(x, nd=2):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), nd)


def map_data(fc, ct, change, recent, checks, series, s_first, s_last, main):
    """docs/data/map_data.json: everything the page shows, keyed by oblast name."""
    by_oblast = {c.oblast_uk: k for k, c in ALL_CITIES.items()}
    ch = change.set_index("oblast")
    obl = {}
    names = list(EN_UK.values())
    for ob in names:
        r = {"oblast": ob}
        key = by_oblast.get(ob) or ("kyiv" if ob == "Київська область" else None)
        if ob in OCCUPIED_CENTRES:
            r.update(status="occupied", centre=OCCUPIED_CENTRES[ob],
                     note=f"Обласний центр ({OCCUPIED_CENTRES[ob]}) під окупацією: не рахуємо.")
        if ob in ch.index and ob not in ("Автономна Республіка Крим", "м. Севастополь"):
            c = ch.loc[ob]
            r["change"] = {"alerts_before": _f(c.alerts_per_day_before), "alerts_after": _f(c.alerts_per_day_after),
                           "hours_before": _f(c.hours_per_day_before), "hours_after": _f(c.hours_per_day_after),
                           "alerts_ratio": _f(c.alerts_ratio), "hours_ratio": _f(c.hours_ratio),
                           "share_before": _f(c.share_of_day_under_alert_before),
                           "saturated": bool(c.share_of_day_under_alert_before >= 0.6),
                           "p_alerts_more": _f(c.p_alerts_more_mw, 3)}
        if key and ob not in OCCUPIED_CENTRES:
            f = fc.set_index("city").loc[key]
            t = ct.set_index("city").loc[key]
            rc = recent.set_index("city").loc[key]
            chk = checks.set_index("city").loc[key]
            r.update(status="ok", city=key, centre=ALL_CITIES[key].name_uk,
                     forecast={"q10": _f(f.q10_h, 1), "q50": _f(f.q50_h, 1), "q90": _f(f.q90_h, 1),
                               "alert_at_00": bool(f.alert_running_at_00), "yesterday": _f(f.hours_yesterday, 1)},
                     accuracy={"model_mae": _f(t.model_MAE_h), "base_mae": _f(t.best_baseline_MAE_h),
                               "base_name": BASELINE_UK[t.best_baseline_by_MAE],
                               "model_is": _f(t.model_IS), "base_is": _f(t.best_baseline_IS),
                               "coverage": _f(t.model_coverage80), "days": int(t.n_days),
                               "beats_mae": bool(t.model_beats_baseline_MAE),
                               "beats_is": bool(t.model_beats_baseline_IS)},
                     h30=_f(rc.hours_per_day_30d), series30=series[key],
                     october={"hours_sep": _f(rc.hours_sep), "hours_oct": _f(rc.hours_oct),
                              "alerts_sep": _f(rc.alerts_sep), "alerts_oct": _f(rc.alerts_oct),
                              "growth": bool(rc.october_growth)},
                     issues=chk.issues or "")
            if ob == "Київська область":
                r["note"] = "Обласний центр — м. Київ (окрема одиниця на карті): прогноз і 30 днів — за Києвом."
            if key in DEEP and ob != "Київська область":
                r["deep"] = {"role": DEEP[key][0], "link": REPO + DEEP[key][1]}
        if ob in ("Автономна Республіка Крим", "м. Севастополь"):
            r.setdefault("note", "Тимчасово окупована територія: даних про тривоги немає.")
        obl[ob] = r
    snap = fc.data_snapshot_utc.iloc[0]
    data = {"generated": {"data_snapshot_utc": snap, "last_full_day": str(s_last), "forecast_for": str(fc.forecast_for.iloc[0]),
                          "series_from": str(s_first), "series_to": str(s_last), "model": main,
                          "change_window": "60 днів до 27.08 проти 27.08–06.09 (без 29.08–02.09)",
                          "october_window": "01.10 – останній день проти 07.09–30.09"},
            "oblasts": obl}
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    (DOCS / "data" / "map_data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def preview(data, geo):
    """Static preview of the forecast layer for the README (same colours as the page)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    bg, edge, grey = "#111418", "#3a3f47", "#2a2e35"
    reds = matplotlib.colors.LinearSegmentedColormap.from_list("r", ["#2b1a1c", "#7a2328", "#c8333b", "#ff5a5f"])
    fig, ax = plt.subplots(figsize=(9, 6.2), facecolor=bg)
    ax.set_facecolor(bg)
    k = np.cos(np.radians(48.5))
    for f in geo["features"]:
        o = data["oblasts"].get(f["properties"]["name"], {})
        v = (o.get("forecast") or {}).get("q50")
        col = grey if v is None else reds(min(v, 24) / 24)
        polys = f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]]
        for poly in polys:
            ring = np.array(poly[0])
            ax.add_patch(Polygon(np.c_[ring[:, 0] * k, ring[:, 1]], closed=True, fc=col, ec=edge, lw=0.6))
        if v is not None and f["properties"]["name"] != "Київська область":
            ring = np.array(polys[0][0])
            cx, cy = ring[:, 0].mean() * k, ring[:, 1].mean()
            ax.text(cx, cy, f"{v:.0f}", color="white", ha="center", va="center", fontsize=8, fontweight="bold")
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.axis("off")
    g = data["generated"]
    ax.set_title(f"Прогноз годин тривоги на {pd.Timestamp(g['forecast_for']):%d.%m.%Y} (медіана) — статистика, не поточні тривоги",
                 color="#e8e8e8", fontsize=11, loc="left")
    fig.savefig(ROOT / "figures" / "map_preview.png", dpi=110, bbox_inches="tight", facecolor=bg)
    plt.close(fig)


def report(m, main, per, ct, change, recent, checks):
    from .national_models import NAMES
    nm = {k: c.name_uk for k, c in ALL_CITIES.items()}
    pool = m[m.city == "pooled"].copy()
    pool["method"] = pool.method.map(lambda x: NAMES.get(x, x))
    cols = ["method", "n", "MAE", "coverage80", "cov_lo95", "cov_hi95", "width", "interval_score"]
    ctt = ct.copy()
    ctt.insert(1, "місто", ctt.city.map(nm))
    rc = recent.copy()
    rc.insert(1, "місто", rc.city.map(nm))
    L = ["# Уся Україна: ціль, спільна модель, карта (генерує `airalerts/national_map.py`)", "",
         f"Валідація {per['validation'][0]}..{per['validation'][1]}, тест {per['test'][0]}..{per['test'][1]}. "
         f"Головна модель обрана на валідації: **{NAMES.get(main, main)}** (`{main}`).", "",
         "## 1. Дані по містах: склейка і проблеми", "",
         "Склейка офіційний канал → alerts.in.ua перевірена на вікні, де обидва джерела повні "
         "(06.09 12:00 – 07.09 06:09 UTC). Розбіжність > 0.5 год позначена в `issues`.", "",
         checks.drop(columns=["archive_units"]).round(2).to_markdown(index=False), "",
         "## 2. Валідація і тест, усі міста разом (ті самі міста-дні для всіх методів)", "",
         pool[pool.period == "validation"][cols].round(3).to_markdown(index=False), "",
         pool[pool.period == "test"][cols].round(3).to_markdown(index=False), "",
         "## 3. Тест по містах: головна модель проти найкращого простого прогнозу на тесті", "",
         ctt.round(2).to_markdown(index=False), "",
         f"Модель краща за MAE у {int(ct.model_beats_baseline_MAE.sum())} з {len(ct)} міст, "
         f"за interval score — у {int(ct.model_beats_baseline_IS.sum())} з {len(ct)}.", "",
         "## 4. Зміна після 27.08 по областях (метод fig9: будь-яка тривога в області, офіційний канал)", "",
         change.round(3).to_markdown(index=False), "",
         "## 5. Жовтень проти 07.09–30.09 (одне джерело — alerts.in.ua; Київ — KMDA)", "",
         rc.round(3).to_markdown(index=False), "",
         f"Зростання в жовтні (p < 0.05 і ≥ +25% за годинами або кількістю): "
         f"{', '.join(recent[recent.october_growth].city.map(nm)) or 'немає'}.", ""]
    (ROOT / "reports" / "national.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    from .config import RESULTS
    from .national import build_targets, load_national, recent_layers, thirty_day_series
    from .national_models import build_features_all, city_table, forecast_next_day_all, run
    from .neighbours import analyse, load
    _, _, checks = build_targets()
    build_features_all()
    m, main_model, per = run()
    ct = city_table(m, main_model)
    ct.round(4).to_csv(RESULTS / "national_city_test.csv", index=False)
    fc = forecast_next_day_all(main_model, ct)
    raw = load()
    change, _, _ = analyse(raw, {o: "усі" for o in sorted(raw.oblast.unique())})
    change.round(4).to_csv(RESULTS / "national_oblast_change.csv", index=False)
    _, daily = load_national()
    recent = recent_layers(daily)
    recent.round(4).to_csv(RESULTS / "national_recent.csv", index=False)
    series, s_first, s_last = thirty_day_series(daily)
    geo = prepare_geojson()
    data = map_data(fc, ct, change, recent, checks, series, s_first, s_last, main_model)
    preview(data, geo)
    report(m, main_model, per, ct, change, recent, checks)
    return fc


if __name__ == "__main__":
    print(main())
