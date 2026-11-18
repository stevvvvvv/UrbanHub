"""Génère de faux snapshots CityBikes (même format que le collecteur) pour tester sans réseau.

    URBANHUB_DATA_DIR=/tmp/urbanhub_test python -m tests.make_sample_citybikes

À NE PAS utiliser pour les analyses : les valeurs sont simulées.
"""
import gzip
import json
from datetime import datetime, timedelta, timezone

import numpy as np

from src.streaming_citybikes import config

rng = np.random.default_rng(0)
SPEC = {"velib": 200, "velhop": 40}   # réseau -> nombre de stations


def make_stations(network, n):
    lat0, lon0 = config.CITY_CENTERS[config.NETWORKS[network]]
    lat = lat0 + rng.normal(0, 0.03, n)
    lon = lon0 + rng.normal(0, 0.04, n)
    dist = np.hypot(lat - lat0, (lon - lon0) * 0.7)
    cap = rng.integers(10, 40, n)
    return [dict(id=f"{network}-{i:04d}", name=f"Station {i}", latitude=float(lat[i]),
                 longitude=float(lon[i]), cap=int(cap[i]), periph=float(dist[i] / dist.max()),
                 bias=float(rng.normal(0, 0.15))) for i in range(n)]


def main(days=2, step_min=5):
    start = datetime(2026, 11, 16, tzinfo=timezone.utc)
    stations = {n: make_stations(n, k) for n, k in SPEC.items()}
    t = start
    while t < start + timedelta(days=days):
        h = (t.hour + 1) % 24   # heure locale approximative
        # matin : périphérie se vide, centre se remplit ; soir : l'inverse
        flow = np.exp(-((h - 8.5) ** 2) / 3) - np.exp(-((h - 18) ** 2) / 4)
        for network, sts in stations.items():
            out = []
            for s in sts:
                occ = 0.5 + s["bias"] + 0.4 * flow * (2 * s["periph"] - 1) * -1 + rng.normal(0, 0.05)
                bikes = int(np.clip(round(occ * s["cap"]), 0, s["cap"]))
                out.append(dict(id=s["id"], name=s["name"], latitude=s["latitude"],
                                longitude=s["longitude"], timestamp=t.isoformat() + "Z",
                                free_bikes=bikes, empty_slots=s["cap"] - bikes,
                                extra={"slots": s["cap"], "virtual": False}))
            payload = {"network": {"id": network, "stations": out}, "collected_at": t.isoformat()}
            dest = config.RAW_DIR / f"dt={t:%Y-%m-%d}" / network / f"{t:%H%M%S}.json.gz"
            dest.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(dest, "wt", encoding="utf-8") as f:
                json.dump(payload, f)
        t += timedelta(minutes=step_min)
    print("snapshots simulés écrits dans", config.RAW_DIR)


if __name__ == "__main__":
    main()
