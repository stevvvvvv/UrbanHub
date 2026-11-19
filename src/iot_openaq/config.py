
import os

BASE_URL = "https://api.openaq.org/v3"

API_KEY = os.getenv("OPENAQ_API_KEY")

# Villes que nous souhaitons étudier
CITIES = [
    "Paris",
    "Lyon",
    "Marseille",
]

# Polluants étudiés
POLLUTANTS = [
    "pm25",
    "pm10",
    "no2",
    "o3",
    "co",
]
