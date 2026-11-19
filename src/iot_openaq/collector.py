
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import API_KEY, BASE_URL, POLLUTANTS


def collect_openaq():
    if not API_KEY:
        raise RuntimeError(
            "Clé OpenAQ absente : configure OPENAQ_API_KEY."
        )

    headers = {"X-API-Key": API_KEY}

    # Chercher quelques stations de mesure en France
    response = requests.get(
        f"{BASE_URL}/locations",
        headers=headers,
        params={"iso": "FR", "limit": 20, "page": 1},
        timeout=30,
    )
    response.raise_for_status()

    locations = response.json().get("results", [])
    measurements = []

    for location in locations:
        location_id = location["id"]

        response = requests.get(
            f"{BASE_URL}/locations/{location_id}/latest",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        latest = response.json().get("results", [])

        # Associer chaque mesure à son polluant
        sensors = {
            sensor["id"]: sensor["parameter"]
            for sensor in location.get("sensors", [])
        }

        for measure in latest:
            parameter = sensors.get(measure["sensorsId"], {})
            pollutant = parameter.get("name", "").lower()

            if pollutant not in POLLUTANTS:
                continue

            coordinates = measure.get("coordinates") or {}

            measurements.append({
                "sensor_id": measure["sensorsId"],
                "station_id": location_id,
                "station_name": location.get("name"),
                "city": location.get("locality"),
                "pollutant": pollutant,
                "unit": parameter.get("units"),
                "value": measure["value"],
                "timestamp": measure["datetime"]["utc"],
                "latitude": coordinates.get("latitude"),
                "longitude": coordinates.get("longitude"),
            })

    # Enregistrer les données brutes
    output_dir = Path("data/raw/openaq")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )
    output_file = output_dir / f"pollution_{timestamp}.json"

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(measurements, file, ensure_ascii=False, indent=2)

    print(f"Stations examinées : {len(locations)}")
    print(f"Mesures collectées : {len(measurements)}")
    print(f"Fichier enregistré : {output_file}")


if __name__ == "__main__":
    collect_openaq()
