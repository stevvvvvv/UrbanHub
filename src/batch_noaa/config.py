"""Paramètres de la partie 1 (flux batch NOAA)."""
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("URBANHUB_DATA_DIR", ROOT / "data"))

# ── Data lake ──
RAW_DIR = DATA_DIR / "raw" / "noaa"              # CSV bruts tels que téléchargés
PROCESSED_DIR = DATA_DIR / "processed" / "noaa"  # parquet nettoyé, partitionné par année

# ── Sources ──
ISD_HISTORY_URL = "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"
# l'ancienne adresse ncei.noaa.gov/data/global-hourly/access renvoie désormais une page html :
# les fichiers sont servis depuis le bucket public NOAA sur AWS (mêmes fichiers, même format)
ACCESS_URL = "https://noaa-global-hourly-pds.s3.amazonaws.com/{year}/{station}.csv"

# ── Périmètre ──
COUNTRY = "FR"                     # code FIPS : France métropolitaine + Corse
N_YEARS = 5
END_YEAR = min(date.today().year - 1, 2025)   # le jeu ISD n'est plus alimenté après 2025 (remplacé par GHCNh)
YEARS = list(range(END_YEAR - N_YEARS + 1, END_YEAR + 1))

MAX_WORKERS = 16                   # téléchargements simultanés
TIMEOUT = 60

# station de référence (aéroport) pour chaque grande ville — id = USAF + WBAN
CITY_STATIONS = {
    "07149099999": "Paris",        # Orly
    "07157099999": "Paris",        # Roissy-CDG
    "07650099999": "Marseille",    # Marignane
    "07481099999": "Lyon",         # Saint-Exupéry
    "07630099999": "Toulouse",     # Blagnac
    "07690099999": "Nice",         # Côte d'Azur
    "07222099999": "Nantes",       # Atlantique
    "07190099999": "Strasbourg",   # Entzheim
    "07643099999": "Montpellier",  # Méditerranée
    "07510099999": "Bordeaux",     # Mérignac
    "07015099999": "Lille",        # Lesquin
    "07130099999": "Rennes",       # Saint-Jacques
}
