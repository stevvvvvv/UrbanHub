"""Téléchargement Open-Meteo explicite, borné aux heures vélo disponibles.

python -m src.analysis_cross.weather
Les données sont issues de modèles/réanalyses, et non de stations NOAA.
"""
import argparse
import json
from datetime import date, timedelta

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

URL = "https://archive-api.open-meteo.com/v1/archive"
VARIABLES = ["temperature_2m", "precipitation", "wind_speed_10m", "relative_humidity_2m"]


def parse_response(payload, city):
    """Valide les unités demandées avant de produire une table UTC."""
    units = payload["hourly_units"]
    expected = dict(zip(VARIABLES, ["°C", "mm", "m/s", "%"]))
    for key, unit in expected.items():
        if units.get(key) != unit:
            raise ValueError(f"Unité Open-Meteo inattendue : {key}={units.get(key)}")
    df = pd.DataFrame(payload["hourly"])
    df = df.rename(columns={"time": "heure_utc", "temperature_2m": "temperature",
                            "wind_speed_10m": "wind_speed", "relative_humidity_2m": "humidity"})
    df["heure_utc"] = pd.to_datetime(df["heure_utc"], utc=True, errors="raise")
    df["city"] = city
    return df[["city", "heure_utc", "temperature", "precipitation", "wind_speed", "humidity"]]


def collect(refresh=False):
    from .prepare import load_bikes
    bikes, source = load_bikes(config.PROCESSED_DIR)
    if bikes.empty:
        raise SystemExit("Aucune donnée vélo : lancer le collecteur puis le traitement de la partie 2.")
    raw = config.DATA_DIR / "raw" / "openmeteo"
    raw.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))
    frames = []
    for city, group in bikes.groupby("city"):
        start = group.heure_utc.min().date()
        end = min(group.heure_utc.max().date(), date.today() - timedelta(days=1))
        if start > end:
            print(f"{city} : attendre la disponibilité des journées terminées.")
            continue
        # Requêtes mensuelles au maximum pour borner les réponses et faciliter la reprise.
        for lo in pd.date_range(start, end, freq="31D"):
            hi = min(lo.date() + timedelta(days=30), end)
            cache = raw / f"{city}_{lo.date()}_{hi}.json"
            if refresh or not cache.exists():
                lat, lon = config.CITY_CENTERS[city]
                params = {"latitude": lat, "longitude": lon, "start_date": str(lo.date()),
                          "end_date": str(hi), "hourly": ",".join(VARIABLES),
                          "timezone": "UTC", "wind_speed_unit": "ms"}
                response = session.get(URL, params=params, timeout=60)
                response.raise_for_status()
                payload = response.json()
                parse_response(payload, city)  # ne pas conserver une réponse invalide
                cache.write_text(json.dumps({"url": response.url, "bike_source": source,
                    "downloaded_at": pd.Timestamp.now(tz="UTC").isoformat(), "response": payload}),
                    encoding="utf-8")
            frames.append(parse_response(json.loads(cache.read_text(encoding="utf-8"))["response"], city))
    if not frames:
        raise SystemExit("Aucune journée météo disponible.")
    df = pd.concat(frames, ignore_index=True).drop_duplicates(["city", "heure_utc"])
    out = config.PROCESSED_DIR / "openmeteo" / "weather_hourly.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"{len(df)} heures météo → {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Remplacer le cache brut")
    collect(parser.parse_args().refresh)
