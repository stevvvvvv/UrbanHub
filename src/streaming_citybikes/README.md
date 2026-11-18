# partie 2 — streaming CityBikes

à faire :
- collecte automatique toutes les 2-3 min des stations des grandes villes (api : https://api.citybik.es/v2/networks)
- variables : `station_id`, `station_name`, `latitude`, `longitude`, `timestamp`, `bikes_available`, `free_slots`
- stockage dans le data lake : `data/raw/citybikes/dt=YYYY-MM-DD/...`

conventions communes avec la partie 1 :
- chemins via une variable `URBANHUB_DATA_DIR` (voir `src/batch_noaa/config.py`)
- timestamps en UTC
- données nettoyées en parquet dans `data/processed/citybikes/`

attention : l'api ne donne que l'état actuel des stations, pas d'historique. il faut lancer la collecte le plus tôt possible pour avoir assez de données pour l'analyse croisée (partie 4).
