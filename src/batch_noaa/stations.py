"""Récupère la liste des stations NOAA situées en France."""
import pandas as pd
import requests

from . import config


def fetch_isd_history(force: bool = False) -> pd.DataFrame:
    """Télécharge (une seule fois) le référentiel des stations isd-history.csv."""
    path = config.RAW_DIR / "isd-history.csv"
    if force or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(config.ISD_HISTORY_URL, timeout=config.TIMEOUT)
        r.raise_for_status()
        path.write_bytes(r.content)
    return pd.read_csv(path, dtype=str)


def french_stations(years=config.YEARS) -> pd.DataFrame:
    """Stations FR actives sur au moins une partie de la période demandée."""
    df = fetch_isd_history()
    df = df[df["CTRY"] == config.COUNTRY].copy()

    # la station doit avoir émis pendant la période (BEGIN/END au format YYYYMMDD)
    start, end = f"{min(years)}0101", f"{max(years)}1231"
    df = df[(df["END"] >= start) & (df["BEGIN"] <= end)]

    df["station_id"] = df["USAF"] + df["WBAN"]
    df["city"] = df["station_id"].map(config.CITY_STATIONS)
    cols = ["station_id", "STATION NAME", "LAT", "LON", "ELEV(M)", "BEGIN", "END", "city"]
    return df[cols].rename(columns={"STATION NAME": "station_name"}).reset_index(drop=True)


if __name__ == "__main__":
    st = french_stations()
    print(f"{len(st)} stations FR actives sur {config.YEARS[0]}-{config.YEARS[-1]}")
    print(st[st["city"].notna()][["station_id", "station_name", "city"]].to_string(index=False))
