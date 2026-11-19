
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from .config import API_KEY, BASE_URL


def collect_history():
    if not API_KEY:
        raise RuntimeError("OPENAQ_API_KEY manquante")

    df = pd.read_parquet(
        "data/processed/openaq/pollution_clean.parquet"
    )

    # Choisir un capteur NO2 à Paris
    paris = df[
        df["city"].fillna("").str.contains(
            "PARIS", case=False, regex=False
        )
        & (df["pollutant"] == "no2")
    ]

    if paris.empty:
        print("Aucun capteur NO2 parisien trouvé.")
        return

    sensor = paris.iloc[0]
    sensor_id = int(sensor["sensor_id"])

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)

    response = requests.get(
        f"{BASE_URL}/sensors/{sensor_id}/hours",
        headers={"X-API-Key": API_KEY},
        params={
            "datetime_from": start.isoformat(),
            "datetime_to": end.isoformat(),
            "limit": 1000,
            "page": 1,
        },
        timeout=60,
    )
    response.raise_for_status()

    results = response.json().get("results", [])

    records = []
    for item in results:
        records.append({
            "sensor_id": sensor_id,
            "station_id": int(sensor["station_id"]),
            "station_name": sensor["station_name"],
            "city": sensor["city"],
            "pollutant": sensor["pollutant"],
            "unit": sensor["unit"],
            "value": item.get("value"),
            "timestamp": (item.get("period") or {})
                         .get("datetimeFrom", {})
                         .get("utc"),
            "latitude": sensor["latitude"],
            "longitude": sensor["longitude"],
        })

    output_dir = Path("data/raw/openaq")
    output_dir.mkdir(parents=True, exist_ok=True)

    output = output_dir / "history_paris_no2.json"
    output.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Capteur : {sensor_id}")
    print(f"Mesures historiques : {len(records)}")
    print(f"Fichier : {output}")


if __name__ == "__main__":
    collect_history()
