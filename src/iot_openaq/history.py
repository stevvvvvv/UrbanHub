"""Inventaire géographique et historique paginé, avec cache mensuel.

python -m src.iot_openaq.history --start 2021-01-01 --end 2025-08-31
La disponibilité réelle des capteurs est enregistrée dans coverage_locations.json.
"""
import argparse
import json
import os
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .config import BASE_URL, DATA_DIR, POLLUTANTS
from src.streaming_citybikes.config import CITY_CENTERS


def pages(session, endpoint, params):
    page = 1
    while True:
        r = session.get(BASE_URL + endpoint, params=params | {"page": page, "limit": 1000}, timeout=60)
        r.raise_for_status()
        payload = r.json()
        rows = payload.get("results", [])
        yield from rows
        if len(rows) < 1000:
            break
        page += 1


def collect_history(start="2021-01-01", end="2025-08-31", refresh=False):
    key = os.getenv("OPENAQ_API_KEY")
    if not key:
        raise RuntimeError("Configurer OPENAQ_API_KEY dans l'environnement")
    lo, hi = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    if lo > hi:
        raise ValueError("La date de début doit précéder la fin")
    raw = DATA_DIR / "raw/openaq"
    raw.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["X-API-Key"] = key
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504], respect_retry_after_header=True)))
    inventory = []
    for city, (lat, lon) in CITY_CENTERS.items():
        locations = list(pages(session, "/locations", {"coordinates": f"{lat},{lon}", "radius": 15000}))
        inventory.append({"city": city, "radius_m": 15000, "locations": locations})
        (raw / "coverage_locations.json").write_text(json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
        for location in locations:
            for sensor in location.get("sensors", []):
                parameter = sensor["parameter"]
                if parameter["name"].lower() not in POLLUTANTS:
                    continue
                for month in pd.date_range(lo.normalize().replace(day=1), hi, freq="MS"):
                    begin = max(lo, month)
                    finish = min(hi + pd.Timedelta(days=1), month + pd.offsets.MonthBegin(1))
                    out = raw / f"history_{city}_{sensor['id']}_{begin.date()}_{finish.date()}.json"
                    if out.exists() and not refresh:
                        continue
                    records = []
                    for item in pages(session, f"/sensors/{sensor['id']}/hours", {
                        "datetime_from": begin.isoformat(), "datetime_to": finish.isoformat()}):
                        timestamp = item.get("period", {}).get("datetimeFrom", {}).get("utc")
                        if timestamp is None or not begin <= pd.Timestamp(timestamp) < finish:
                            continue
                        coords = location.get("coordinates") or {}
                        records.append(dict(sensor_id=sensor["id"], station_id=location["id"],
                            station_name=location.get("name"), city=city, locality=location.get("locality"),
                            pollutant=parameter["name"].lower(), unit=parameter["units"],
                            value=item.get("value"), timestamp=timestamp,
                            latitude=coords.get("latitude"), longitude=coords.get("longitude")))
                    temp = out.with_suffix(".tmp")
                    temp.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
                    temp.replace(out)
                    print(city, sensor["id"], begin.date(), len(records))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2025-08-31")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    collect_history(args.start, args.end, args.refresh)
