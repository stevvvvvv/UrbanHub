"""Exécution hors réseau et exports de la partie 4.

python -m src.analysis_cross.run
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .prepare import cities, join, load_bikes, noaa_daily, pollution_tables


def correlations(df, groups, xs, ys, time, min_n=30, min_days=7):
    """Spearman descriptif par ville, effectifs et durée visibles, sans p-value.

    Les observations horaires ne sont pas indépendantes. Ces seuils évitent les
    petits échantillons mais ne constituent pas une garantie de significativité.
    """
    rows = []
    if df.empty:
        return pd.DataFrame(columns=groups + ["x", "y", "n", "jours", "rho", "statut"])
    for key, group in df.groupby(groups):
        key = key if isinstance(key, tuple) else (key,)
        for x in xs:
            for y in ys:
                if x not in group or y not in group:
                    continue
                pair = group[[x, y, time]].replace([np.inf, -np.inf], np.nan).dropna()
                n = len(pair)
                days = pd.to_datetime(pair[time], utc=True).dt.tz_convert("Europe/Paris").dt.date.nunique()
                status = "descriptif"
                rho = np.nan
                if n < min_n or days < min_days:
                    status = "échantillon insuffisant"
                elif pair[x].nunique() < 2 or pair[y].nunique() < 2:
                    status = "variable constante"
                else:
                    rho = pair[x].rank().corr(pair[y].rank())
                rows.append(dict(zip(groups, key)) | dict(x=x, y=y, n=n, jours=days, rho=rho, statut=status))
    return pd.DataFrame(rows)


def coverage(sources):
    rows = []
    for name, (df, time) in sources.items():
        if df.empty:
            continue
        for city, g in df.groupby("city"):
            rows.append(dict(source=name, city=city, lignes=len(g), debut=str(g[time].min()),
                             fin=str(g[time].max()), instants=g[time].nunique()))
    return pd.DataFrame(rows, columns=["source", "city", "lignes", "debut", "fin", "instants"])


def run(processed=None, output=None, reports=None):
    processed = Path(processed or config.PROCESSED_DIR)
    output = Path(output or config.OUTPUT_DIR)
    reports = Path(reports or config.REPORT_DIR)
    output.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    notes = []
    bikes, bike_source = load_bikes(processed)
    notes.append(f"Vélos : {bike_source}.")
    def read(relative):
        path = processed / relative
        if not path.exists():
            notes.append(f"Source absente : {relative}.")
            return pd.DataFrame()
        return pd.read_parquet(path)
    weather = read("openmeteo/weather_hourly.parquet")
    if not weather.empty:
        weather = cities(weather)
        weather["heure_utc"] = pd.to_datetime(weather.heure_utc, utc=True, errors="raise")
    pollution = read("openaq/pollution_clean.parquet")
    ph, pdaily = pollution_tables(pollution) if not pollution.empty else (pd.DataFrame(), pd.DataFrame())
    noaa = read("noaa_daily.parquet")
    noaa = noaa_daily(noaa) if not noaa.empty else noaa
    tables = {}
    tables["meteo_velos"] = join(bikes, weather, ["city", "heure_utc"]) if not bikes.empty and not weather.empty else pd.DataFrame()
    tables["meteo_pollution"] = join(pdaily, noaa, ["city", "date"]) if not pdaily.empty and not noaa.empty else pd.DataFrame()
    tables["pollution_velos"] = join(ph, bikes, ["city", "heure_utc"]) if not ph.empty and not bikes.empty else pd.DataFrame()
    tables["trois_flux"] = join(tables["pollution_velos"], weather, ["city", "heure_utc"]) if not tables["pollution_velos"].empty and not weather.empty else pd.DataFrame()
    specs = {
        "meteo_velos": (["city"], ["temperature", "precipitation", "wind_speed"], ["activite_par_station_heure", "remplissage_moyen"], "heure_utc"),
        "meteo_pollution": (["city", "pollutant", "unit"], ["t_mean", "wind_mean", "p_mean", "precipitation_day"], ["pollution"], "date"),
        "pollution_velos": (["city", "pollutant", "unit"], ["pollution"], ["activite_par_station_heure", "remplissage_moyen"], "heure_utc"),
        "trois_flux": (["city", "pollutant", "unit"], ["temperature", "precipitation", "wind_speed", "pollution"], ["activite_par_station_heure", "remplissage_moyen"], "heure_utc"),
    }
    stats = {}
    for name, table in tables.items():
        # CSV vide avec en-tête explicite et parquet même en l'absence de chevauchement.
        if table.empty:
            table = pd.DataFrame(columns=["city", specs[name][3]])
            tables[name] = table
            notes.append(f"{name} : aucun couple d'observations simultanées exploitable.")
        table.to_parquet(output / f"{name}.parquet", index=False)
        groups, xs, ys, time = specs[name]
        stats[name] = correlations(table, groups, xs, ys, time)
        stats[name].to_csv(reports / f"correlations_{name}.csv", index=False)
    cov = coverage({"velos": (bikes, "heure_utc"), "openmeteo": (weather, "heure_utc"),
                    "openaq_horaire": (ph, "heure_utc"), "openaq_journalier": (pdaily, "date"), "noaa": (noaa, "date")})
    cov.to_csv(reports / "couverture.csv", index=False)
    manifest = {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "processed_dir": str(processed),
                "bike_source": bike_source, "lignes_jointes": {k: len(v) for k, v in tables.items()},
                "notes": notes, "minimum_correlation": {"observations": 30, "jours": 7}}
    (reports / "diagnostic.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Résultats de la partie 4", "", f"Exécution UTC : {manifest['generated_at']}", ""] + [f"- {n}" for n in notes]
    for name, result in stats.items():
        usable = result[result.statut == "descriptif"]
        lines += ["", f"## {name}", "", f"{len(tables[name])} lignes jointes ; {len(usable)} corrélations descriptives calculables."]
        for row in usable.itertuples():
            lines.append(f"- {row.city}, {getattr(row, 'pollutant', '')} {getattr(row, 'unit', '')} : {row.x} / {row.y}, ρ={row.rho:.3f}, n={row.n}, {row.jours} jours.")
    lines += ["", "Les corrélations décrivent des associations, sans démontrer de causalité. Les cycles horaires, la saison, le nombre de stations et le rééquilibrage peuvent expliquer une association. Aucune conclusion chiffrée ne doit être tirée d'un croisement vide."]
    (reports / "synthese.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tables, stats, cov, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reports", type=Path)
    args = parser.parse_args()
    _, _, _, manifest = run(args.processed, args.output, args.reports)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
