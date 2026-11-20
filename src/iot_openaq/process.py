
from importlib.resources import files
from pathlib import Path

import pandas as pd


from .config import DATA_DIR
RAW_DIR = DATA_DIR / "raw/openaq"
PROCESSED_DIR = DATA_DIR / "processed/openaq"


def process_openaq():
    files = sorted(RAW_DIR.glob("pollution_*.json"))
    files += sorted(RAW_DIR.glob("history_*.json"))

    if not files:
        print("Aucun fichier OpenAQ trouvé.")
        return

    # Charger les fichiers JSON
    frames = [pd.read_json(file) for file in files]
    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        print("Aucune mesure dans les réponses OpenAQ : vérifier la couverture et les dates.")
        return

    print(f"Mesures brutes : {len(df)}")

    # Convertir les dates et les valeurs
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True, errors="coerce"
    )
    df["value"] = pd.to_numeric(
        df["value"], errors="coerce"
    )

    # Conserver l'historique : seules les dates futures sont exclues.
    df = df[df["timestamp"] <= pd.Timestamp.now(tz="UTC")]

    # Supprimer les données incorrectes
    df = df.dropna(
        subset=["sensor_id", "pollutant", "value", "timestamp"]
    )
    df = df[df["value"] >= 0]

    # Supprimer les doublons
    df = df.drop_duplicates(
        subset=["sensor_id", "timestamp", "pollutant"]
    )

    # Enregistrer en Parquet
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output = PROCESSED_DIR / "pollution_clean.parquet"

    df.to_parquet(output, index=False)

    print(f"Mesures nettoyées : {len(df)}")
    print(f"Fichier enregistré : {output}")


if __name__ == "__main__":
    process_openaq()
