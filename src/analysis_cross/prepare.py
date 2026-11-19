"""Préparation des clés de jointure et des indicateurs comparables."""
import unicodedata

import numpy as np
import pandas as pd

from .config import CITIES


def city_name(value):
    """Correspondance exacte après normalisation ; aucune ville devinée par sous-chaîne."""
    def norm(s):
        return ''.join(c for c in unicodedata.normalize('NFKD', str(s))
                       if not unicodedata.combining(c)).strip().casefold()
    return {norm(c): c for c in CITIES}.get(norm(value))


def cities(df):
    df = df.copy()
    df["city"] = df["city"].map(city_name)
    return df.dropna(subset=["city"])


def bike_hourly(df):
    """Moyenne des stocks par collecte, mouvements rapportés au temps observé.

    Une variation sur >10 min est exclue. Les variations sont des mouvements
    apparents (incluant le rééquilibrage), pas un comptage des trajets.
    """
    df = cities(df)
    df = df[~df.city.isin(["Marseille", "Nice"])].copy()
    df["collected_at"] = pd.to_datetime(df.collected_at, utc=True, errors="coerce")
    for col in ["bikes_available", "capacity"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["collected_at", "station_id", "network", "bikes_available", "capacity"])
    df = df[(df.capacity > 0) & (df.bikes_available >= 0)]
    keys = ["network", "station_id"]
    df = df.drop_duplicates(keys + ["collected_at"]).sort_values(keys + ["collected_at"])
    g = df.groupby(keys)
    gap = g.collected_at.diff().dt.total_seconds()
    valid = gap.gt(0) & gap.le(600)
    df["movement"] = g.bikes_available.diff().abs().where(valid)
    df["exposure_h"] = (gap / 3600).where(valid)
    df["occupancy"] = (df.bikes_available / df.capacity).clip(0, 1)
    df["heure_utc"] = df.collected_at.dt.floor("h")
    # Deux niveaux : les stations ne sont pas additionnées plusieurs fois par heure.
    snapshots = df.groupby(["city", "heure_utc", "collected_at"]).agg(
        stock=("bikes_available", "sum"), occupancy=("occupancy", "mean"),
        stations=("station_id", "size")).reset_index()
    stocks = snapshots.groupby(["city", "heure_utc"]).agg(
        velos_disponibles=("stock", "mean"), remplissage_moyen=("occupancy", "mean"),
        stations=("stations", "mean"), collectes=("collected_at", "nunique"))
    moves = df.groupby(["city", "heure_utc"])[["movement", "exposure_h"]].sum(min_count=1)
    moves["activite_par_station_heure"] = moves.movement / moves.exposure_h.replace(0, np.nan)
    return stocks.join(moves).reset_index()


def load_bikes(processed):
    files = sorted((processed / "citybikes").glob("dt=*.parquet"))
    if files:
        return bike_hourly(pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)), "stations recalculées"
    path = processed / "citybikes_hourly.parquet"
    if path.exists():
        df = cities(pd.read_parquet(path))
        df = df[~df.city.isin(["Marseille", "Nice"])].copy()
        df["heure_utc"] = pd.to_datetime(df.heure_utc, utc=True, errors="coerce")
        df = df.dropna(subset=["heure_utc"])
        if df.duplicated(["city", "heure_utc"]).any():
            raise ValueError("Doublons ville/heure dans l'export vélo")
        # L'export 02 somme les stocks : ne pas les employer comme une offre réelle.
        df = df.drop(columns=["velos_disponibles", "mouvements"], errors="ignore")
        return df, "export 02 : remplissage seulement, exposition inconnue"
    return pd.DataFrame(), "absent"


def pollution_tables(df, min_hours=18):
    """Moyenne par capteur/heure, puis par ville, sans mélanger les unités.

    Les jours sont définis en Europe/Paris, comme dans NOAA. Un capteur doit
    avoir >=18 heures distinctes valides pour entrer dans la moyenne journalière.
    """
    df = cities(df)
    df["timestamp"] = pd.to_datetime(df.timestamp, utc=True, errors="coerce")
    df["value"] = pd.to_numeric(df.value, errors="coerce")
    df = df.dropna(subset=["timestamp", "sensor_id", "pollutant", "unit", "value"])
    df = df[np.isfinite(df.value) & df.value.ge(0)].copy()
    df["unit"] = df.unit.astype(str).str.strip().str.replace("μ", "µ", regex=False)
    df["pollutant"] = df.pollutant.astype(str).str.lower().str.strip()
    df = df.drop_duplicates(["city", "sensor_id", "pollutant", "unit", "timestamp"])
    df["heure_utc"] = df.timestamp.dt.floor("h")
    keys = ["city", "pollutant", "unit"]
    sensor = df.groupby(keys + ["sensor_id", "heure_utc"]).value.mean().reset_index()
    hourly = sensor.groupby(keys + ["heure_utc"]).agg(
        pollution=("value", "mean"), sensors=("sensor_id", "nunique")).reset_index()
    sensor["date"] = sensor.heure_utc.dt.tz_convert("Europe/Paris").dt.tz_localize(None).dt.normalize()
    daily = sensor.groupby(keys + ["sensor_id", "date"]).agg(
        pollution=("value", "mean"), hours=("heure_utc", "nunique")).reset_index()
    daily = daily[daily.hours >= min_hours].groupby(keys + ["date"]).agg(
        pollution=("pollution", "mean"), sensors=("sensor_id", "nunique")).reset_index()
    return hourly, daily


def noaa_daily(df):
    df = cities(df)
    dates = pd.to_datetime(df.date, errors="raise")
    if dates.dt.tz is not None:
        dates = dates.dt.tz_convert("Europe/Paris").dt.tz_localize(None)
    df["date"] = dates.dt.normalize()
    if df.duplicated(["station_id", "date"]).any():
        raise ValueError("Doublons NOAA station/jour")
    # Paris possède deux stations : une seule ligne ville/jour avant jointure.
    cols = [c for c in ["t_mean", "wind_mean", "p_mean", "precipitation_day"] if c in df]
    if not {"t_mean", "wind_mean"}.issubset(cols):
        raise ValueError("NOAA : colonnes t_mean et wind_mean requises")
    return df.groupby(["city", "date"])[cols].mean().reset_index()


def join(left, right, on):
    """Jointure exacte, jamais de rapprochement d'années différentes."""
    return left.merge(right, on=on, how="inner", validate="many_to_one")
