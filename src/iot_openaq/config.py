import os
from pathlib import Path
from src.streaming_citybikes.config import CITY_CENTERS
BASE_URL = "https://api.openaq.org/v3"
API_KEY = os.getenv("OPENAQ_API_KEY")
DATA_DIR = Path(os.getenv("URBANHUB_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
CITIES = list(CITY_CENTERS)
POLLUTANTS = ["pm25", "pm10", "no2", "o3", "co"]
