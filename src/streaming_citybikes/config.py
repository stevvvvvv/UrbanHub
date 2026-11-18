"""Paramètres de la partie 2 (flux streaming CityBikes)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("URBANHUB_DATA_DIR", ROOT / "data"))

# ── Data lake ──
RAW_DIR = DATA_DIR / "raw" / "citybikes"              # réponses brutes de l'API (json.gz)
PROCESSED_DIR = DATA_DIR / "processed" / "citybikes"  # parquet aplati, partitionné par jour

# ── Source ──
API_URL = "https://api.citybik.es/v2/networks/{network}"
USER_AGENT = "UrbanHub/1.0 (projet etudiant IPSSI)"
TIMEOUT = 30

# ── Collecte ──
INTERVAL_S = 150   # une collecte toutes les 2 min 30

# réseaux de vélos en libre-service des grandes villes (identifiants CityBikes)
# Nice n'a pas de réseau à stations dans CityBikes (Pony est en free-floating : 0 station)
NETWORKS = {
    "velib": "Paris",
    "velov": "Lyon",
    "le-velo": "Marseille",
    "velo": "Toulouse",
    "bicloo": "Nantes",
    "velhop": "Strasbourg",
    "velomagg": "Montpellier",
    "v3-bordeaux": "Bordeaux",
    "vlille": "Lille",
    "le-velo-star": "Rennes",
}

# centre-ville de référence (pour mesurer l'éloignement des stations)
CITY_CENTERS = {
    "Paris": (48.8566, 2.3522), "Lyon": (45.7640, 4.8357), "Marseille": (43.2965, 5.3698),
    "Toulouse": (43.6047, 1.4442), "Nice": (43.7102, 7.2620), "Nantes": (47.2184, -1.5536),
    "Strasbourg": (48.5734, 7.7521), "Montpellier": (43.6108, 3.8767),
    "Bordeaux": (44.8378, -0.5792), "Lille": (50.6292, 3.0573), "Rennes": (48.1173, -1.6778),
}
