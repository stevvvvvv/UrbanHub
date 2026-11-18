"""Génère de faux fichiers bruts au format NOAA pour tester le pipeline sans réseau.

    URBANHUB_DATA_DIR=/tmp/urbanhub_test python -m tests.make_sample_data

À NE PAS utiliser pour les analyses : les valeurs sont simulées.
"""
import numpy as np
import pandas as pd

from src.batch_noaa import config

rng = np.random.default_rng(42)
STATIONS = {  # id: (nom, lat, lon, temp moyenne annuelle)
    "07149099999": ("PARIS-ORLY, FR", 48.72, 2.38, 12.0),
    "07650099999": ("MARSEILLE, FR", 43.44, 5.22, 15.5),
    "07481099999": ("LYON-ST EXUPERY, FR", 45.73, 5.08, 12.5),
    "07222099999": ("NANTES ATLANTIQUE, FR", 47.15, -1.61, 12.8),
}


def fmt(v, width, scale=10, sign=False, missing=None):
    if missing is not None and np.isnan(v):
        return missing
    n = int(round(v * scale))
    return f"{n:+0{width + 1}d}" if sign else f"{n:0{width}d}"


def make(station, name, lat, lon, tmean, year):
    ts = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h", tz="UTC")
    doy = ts.dayofyear.values
    hour = ts.hour.values
    temp = (tmean - 8 * np.cos(2 * np.pi * (doy - 15) / 365)
            - 4 * np.cos(2 * np.pi * (hour - 3) / 24) + rng.normal(0, 2, len(ts)))
    # une vague de chaleur artificielle en juillet
    temp[(ts.month == 7) & (ts.day >= 10) & (ts.day <= 16)] += 9
    dew = temp - np.abs(rng.normal(4, 3, len(ts)))
    wind = np.abs(rng.gamma(2, 2.2, len(ts)))
    wdir = rng.integers(0, 36, len(ts)) * 10
    slp = 1015 + rng.normal(0, 8, len(ts))
    vis = np.clip(30 - 4 * np.maximum(0, 3 - (temp - dew)) ** 2 + rng.normal(0, 3, len(ts)), 0.1, 50)
    rows = []
    for i, t in enumerate(ts):
        wqc = "1"
        tmp = fmt(temp[i], 4, sign=True)
        if rng.random() < 0.02:
            tmp = "+9999"            # manquant
        if rng.random() < 0.002:
            tmp, wqc = "+0999", "7"  # aberrant + mauvais code qualité
        base = dict(STATION=station, DATE=t.strftime("%Y-%m-%dT%H:%M:%S"), SOURCE="4",
                    LATITUDE=lat, LONGITUDE=lon, ELEVATION=100, NAME=name,
                    REPORT_TYPE="FM-15", CALL_SIGN="99999", QUALITY_CONTROL="V020",
                    WND=f"{wdir[i]:03d},1,N,{fmt(wind[i], 4)},{wqc}",
                    CIG="22000,1,9,N", VIS=f"{int(vis[i] * 1000):06d},1,N,1",
                    TMP=f"{tmp},1", DEW=f"{fmt(dew[i], 4, sign=True)},1",
                    SLP=f"{fmt(slp[i], 5)},1", AA1="")
        rows.append(base)
        if t.hour % 6 == 0:  # SYNOP toutes les 6h avec cumul de pluie
            rain = rng.gamma(0.4, 3) if rng.random() < 0.3 else 0.0
            syn = dict(base, REPORT_TYPE="FM-12", AA1=f"06,{fmt(rain, 4)},9,1")
            rows.append(syn)
    return pd.DataFrame(rows)


def main(years=(2024, 2025)):
    for st, (name, lat, lon, tm) in STATIONS.items():
        for y in years:
            dest = config.RAW_DIR / f"year={y}" / f"{st}.csv"
            dest.parent.mkdir(parents=True, exist_ok=True)
            make(st, name, lat, lon, tm, y).to_csv(dest, index=False)
            print("écrit", dest)


if __name__ == "__main__":
    main()
