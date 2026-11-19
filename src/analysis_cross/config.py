"""Chemins communs et périmètre de l'analyse croisée."""
import os
from pathlib import Path
from src.streaming_citybikes.config import CITY_CENTERS

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("URBANHUB_DATA_DIR", ROOT / "data"))
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = PROCESSED_DIR / "cross_analysis"
REPORT_DIR = ROOT / "reports" / "partie4"
CITIES = tuple(CITY_CENTERS)
