"""Transforme les snapshots bruts CityBikes en parquet exploitable.

Usage :
    python -m src.streaming_citybikes.process

Colonnes produites :
    network, city, station_id, station_name, latitude, longitude,
    timestamp (UTC, dernière mise à jour de la station selon l'API),
    collected_at (UTC, heure de la collecte),
    bikes_available, free_slots, capacity

Un fichier parquet par jour : relancer le traitement réécrit les jours concernés
(même entrée = même sortie).
"""
import gzip
import json
from pathlib import Path

import pandas as pd

from . import config


def to_utc(s: pd.Series) -> pd.Series:
    """Parse des dates ISO 8601 hétérogènes (avec ou sans microsecondes) en UTC."""
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="ISO8601")
    except (TypeError, ValueError):   # pandas < 2.0
        return pd.to_datetime(s, utc=True, errors="coerce")


def parse_snapshot(path: Path) -> pd.DataFrame:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        payload = json.load(f)
    net = payload["network"]
    rows = []
    for st in net["stations"]:
        extra = st.get("extra") or {}
        rows.append({
            "network": net["id"],
            "station_id": st["id"],
            "station_name": st.get("name"),
            "latitude": st.get("latitude"),
            "longitude": st.get("longitude"),
            "timestamp": st.get("timestamp"),
            "bikes_available": st.get("free_bikes"),
            "free_slots": st.get("empty_slots"),
            "slots_extra": extra.get("slots"),
            "virtual": extra.get("virtual"),
            "renting": extra.get("renting"),
            "returning": extra.get("returning"),
        })
    df = pd.DataFrame(rows)
    df["collected_at"] = payload["collected_at"]
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df["city"] = df["network"].map(config.NETWORKS)
    # l'API renvoie parfois "+00:00Z" : on normalise avant de parser
    ts = df["timestamp"].astype(str).str.replace(r"\+00:00Z$", "+00:00", regex=True)
    df["timestamp"] = to_utc(ts)
    df["collected_at"] = to_utc(df["collected_at"])

    for c in ["latitude", "longitude", "bikes_available", "free_slots", "slots_extra"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # stations virtuelles (zones de dépôt sans bornes) : pas de capacité, on les écarte
    df = df[df["virtual"].fillna(False).astype(bool) == False]  # noqa: E712
    # stations hors service (ni prêt ni retour possible) : sinon elles passeraient pour « vides »
    hors_service = (df["renting"] == False) & (df["returning"] == False)  # noqa: E712
    df = df[~hors_service]
    df = df.dropna(subset=["station_id", "latitude", "longitude", "bikes_available"])
    df = df[(df["bikes_available"] >= 0) & (df["free_slots"].fillna(0) >= 0)]

    # capacité = vélos + places libres (bornes en panne exclues) ; sinon nombre de bornes déclaré
    df["capacity"] = (df["bikes_available"] + df["free_slots"]).fillna(df["slots_extra"])
    df = df.drop_duplicates(["network", "station_id", "collected_at"])
    cols = ["network", "city", "station_id", "station_name", "latitude", "longitude",
            "timestamp", "collected_at", "bikes_available", "free_slots", "capacity"]
    return df[cols]


def main():
    days = sorted(p for p in config.RAW_DIR.glob("dt=*") if p.is_dir())
    if not days:
        print(f"aucune donnée brute dans {config.RAW_DIR} — lancer d'abord le collecteur")
        return
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for day in days:
        files = sorted(day.glob("*/*.json.gz"))
        frames = []
        for f in files:
            try:
                frames.append(parse_snapshot(f))
            except Exception as e:   # fichier tronqué (collecte interrompue) : on l'ignore
                print(f"  ignoré : {f.name} ({type(e).__name__})")
        if not frames:
            continue
        df = clean(pd.concat(frames, ignore_index=True))
        df.to_parquet(config.PROCESSED_DIR / f"{day.name}.parquet", index=False)
        total += len(df)
        print(f"{day.name} : {len(files)} snapshots -> {len(df):,} lignes")
    print(f"total : {total:,} lignes dans {config.PROCESSED_DIR}")


if __name__ == "__main__":
    main()
