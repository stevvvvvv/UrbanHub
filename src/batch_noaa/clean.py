"""Nettoyage des CSV NOAA bruts -> parquet exploitable.

Usage :
    python -m src.batch_noaa.clean

Format NOAA (ISD) : chaque mesure est une chaîne "valeur,code_qualite,...", avec des
valeurs sentinelles (9999, 99999...) pour les données manquantes et des facteurs
d'échelle (x10). Doc : https://www.ncei.noaa.gov/data/global-hourly/doc/isd-format-document.pdf

Colonnes produites :
    station_id, station_name, city, latitude, longitude, elevation, timestamp (UTC),
    temperature (°C), dew_point (°C), wind_speed (m/s), wind_direction (°),
    pressure (hPa, ramenée au niveau de la mer), visibility (km),
    precipitation (mm), precipitation_period_h (h)
"""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

RAW_COLS = ["STATION", "DATE", "LATITUDE", "LONGITUDE", "ELEVATION", "NAME",
            "REPORT_TYPE", "WND", "VIS", "TMP", "DEW", "SLP", "MA1", "AA1"]

# codes qualité NOAA signalant une valeur suspecte ou erronée
BAD_QC = {"2", "3", "6", "7"}

# bornes physiques plausibles en France métropolitaine
VALID_RANGES = {
    "temperature": (-40, 50),
    "dew_point": (-50, 35),
    "wind_speed": (0, 75),
    "pressure": (920, 1070),
    "visibility": (0, 100),
    "precipitation": (0, 300),
}

# en cas de doublon station/heure : METAR (FM-15) puis SYNOP (FM-12) puis le reste
REPORT_PRIORITY = {"FM-15": 0, "FM-12": 1, "SAO": 2, "FM-16": 3}

VARS = ["temperature", "dew_point", "wind_speed", "wind_direction",
        "pressure", "visibility", "precipitation"]


def _split(s: pd.Series, n: int) -> pd.DataFrame:
    """Découpe "a,b,c" en colonnes (NaN si la mesure est absente)."""
    out = s.fillna("").str.split(",", expand=True)
    for i in range(n):
        if i not in out.columns:
            out[i] = None
    return out[list(range(n))]


def _num(s: pd.Series, missing: int, scale: float = 1.0) -> pd.Series:
    """Convertit en nombre, remplace la sentinelle par NaN et applique l'échelle."""
    v = pd.to_numeric(s, errors="coerce")
    return v.where(v != missing) / scale


def _qc(value: pd.Series, qc: pd.Series) -> pd.Series:
    """Invalide les valeurs dont le code qualité est mauvais."""
    return value.where(~qc.isin(BAD_QC))


def parse_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Transforme un DataFrame brut NOAA en DataFrame propre (une ligne = station x heure)."""
    for c in RAW_COLS:
        if c not in df.columns:
            df[c] = None

    out = pd.DataFrame({
        "station_id": df["STATION"].astype(str).str.zfill(11),
        "station_name": df["NAME"],
        "latitude": pd.to_numeric(df["LATITUDE"], errors="coerce"),
        "longitude": pd.to_numeric(df["LONGITUDE"], errors="coerce"),
        "elevation": pd.to_numeric(df["ELEVATION"], errors="coerce"),
        "timestamp": pd.to_datetime(df["DATE"], errors="coerce", utc=True),
        "report_type": df["REPORT_TYPE"].astype(str).str.strip(),
    })

    # vent : "direction,qc,type,vitesse,qc" — direction en °, vitesse en m/s x10
    w = _split(df["WND"], 5)
    direction = _qc(_num(w[0], 999), w[1])
    speed = _qc(_num(w[3], 9999, 10), w[4])
    wtype = w[2].str.upper()
    out["wind_direction"] = direction.where(~wtype.isin(["C", "V"]))  # calme / variable : pas de direction
    out["wind_speed"] = speed.mask(wtype.eq("C"), 0.0)                 # calme = 0 m/s

    # visibilité : "distance_m,qc,variabilite,qc" -> km
    v = _split(df["VIS"], 4)
    out["visibility"] = _qc(_num(v[0], 999999, 1000), v[1])

    # température / point de rosée : "+0123,qc" en °C x10
    t = _split(df["TMP"], 2)
    out["temperature"] = _qc(_num(t[0], 9999, 10), t[1])
    d = _split(df["DEW"], 2)
    out["dew_point"] = _qc(_num(d[0], 9999, 10), d[1])

    # pression au niveau de la mer : "10132,qc" en hPa x10
    p = _split(df["SLP"], 2)
    out["pressure"] = _qc(_num(p[0], 99999, 10), p[1])
    # les METAR horaires ne donnent pas la SLP mais le QNH (calage altimétrique, champ MA1),
    # quasi identique à la pression au niveau de la mer : on s'en sert pour combler les trous
    ma = _split(df["MA1"], 4)
    out["pressure"] = out["pressure"].fillna(_qc(_num(ma[0], 99999, 10), ma[1]))

    # précipitations : "periode_h,hauteur_mm x10,condition,qc"
    a = _split(df["AA1"], 4)
    out["precipitation_period_h"] = _num(a[0], 99)
    out["precipitation"] = _qc(_num(a[1], 9999, 10), a[3])
    out.loc[out["precipitation_period_h"].isna() | (out["precipitation_period_h"] == 0),
            "precipitation"] = np.nan

    # valeurs physiquement impossibles -> NaN
    for col, (lo, hi) in VALID_RANGES.items():
        out[col] = out[col].where(out[col].between(lo, hi))

    # point de rosée > température : incohérent
    out.loc[out["dew_point"] > out["temperature"] + 0.5, "dew_point"] = np.nan

    out = out.dropna(subset=["timestamp"])

    # doublons station/heure (METAR + SYNOP + SPECI au même instant) :
    # on fusionne en gardant, colonne par colonne, la 1re valeur non nulle selon la priorité
    out["_prio"] = out["report_type"].map(REPORT_PRIORITY).fillna(9)
    out = (out.sort_values(["timestamp", "_prio"])
              .groupby(["station_id", "timestamp"], as_index=False).first()
              .drop(columns=["_prio", "report_type"]))

    # on ne garde que les lignes qui contiennent au moins une mesure
    out = out.dropna(subset=VARS, how="all")
    out["city"] = out["station_id"].map(config.CITY_STATIONS)
    return out


def clean_file(path: Path) -> dict:
    """Nettoie un fichier station/année et l'écrit en parquet. Renvoie des stats qualité."""
    with open(path, "rb") as f:
        if not f.read(20).lstrip(b"\xef\xbb\xbf").startswith(b'"STATION"'):
            print(f"  ignoré (pas un CSV NOAA) : {path}")
            return {"file": f"{path.parent.name}/{path.stem}", "raw_rows": 0, "clean_rows": 0}
    raw = pd.read_csv(path, dtype=str, usecols=lambda c: c in RAW_COLS, low_memory=False)
    clean = parse_raw(raw)

    year = path.parent.name.split("=")[-1]
    dest = config.PROCESSED_DIR / f"year={year}" / f"{path.stem}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(dest, index=False)   # écrase : relancer le nettoyage donne le même résultat

    stats = {"file": f"{year}/{path.stem}", "raw_rows": len(raw), "clean_rows": len(clean)}
    for v in VARS:
        stats[f"missing_{v}_%"] = round(100 * clean[v].isna().mean(), 1) if len(clean) else 100.0
    return stats


def local_date(ts: pd.Series) -> pd.Series:
    """Jour calendaire en heure de Paris (timestamp UTC -> date locale à minuit)."""
    return ts.dt.tz_convert("Europe/Paris").dt.tz_localize(None).dt.normalize()


def daily_precipitation(df: pd.DataFrame) -> pd.DataFrame:
    """Cumul journalier de pluie par station.

    Les stations ne déclarent pas toutes la pluie sur la même durée (1h, 3h, 6h, 12h, 24h).
    Pour chaque station/jour on prend la durée qui couvre le mieux les 24h, et on somme.
    """
    p = df.dropna(subset=["precipitation", "precipitation_period_h"]).copy()
    p["date"] = local_date(p["timestamp"])
    g = (p.groupby(["station_id", "date", "precipitation_period_h"])
           .agg(total=("precipitation", "sum"), n=("precipitation", "size"))
           .reset_index())
    g["coverage"] = (g["n"] * g["precipitation_period_h"] / 24).clip(upper=1)
    g = g[g["coverage"] >= 0.75]   # on exige au moins 18h couvertes
    best = g.sort_values(["coverage", "precipitation_period_h"], ascending=[False, True])
    best = best.drop_duplicates(["station_id", "date"])
    return best[["station_id", "date", "total"]].rename(columns={"total": "precipitation_day"})


def main():
    files = sorted(config.RAW_DIR.glob("year=*/*.csv"))
    print(f"{len(files)} fichiers bruts à nettoyer")
    with ProcessPoolExecutor() as pool:
        stats = list(pool.map(clean_file, files, chunksize=4))

    report = pd.DataFrame(stats)
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    report.to_csv(config.PROCESSED_DIR / "_quality_report.csv", index=False)
    print(f"lignes brutes : {report['raw_rows'].sum():,} -> lignes propres : {report['clean_rows'].sum():,}")
    print("taux moyen de valeurs manquantes après nettoyage (%) :")
    print(report.filter(like="missing_").mean().round(1).to_string())


if __name__ == "__main__":
    main()
