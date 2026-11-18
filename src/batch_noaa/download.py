"""Téléchargement parallèle des fichiers NOAA Global Hourly des stations françaises.

Usage :
    python -m src.batch_noaa.download                 # toutes les stations FR, 5 dernières années
    python -m src.batch_noaa.download --cities-only   # uniquement les stations des grandes villes
    python -m src.batch_noaa.download --years 2024 2025 --workers 32

Les fichiers déjà présents sont ignorés : on peut relancer le script après une coupure.
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config
from .stations import french_stations


def make_session(workers: int) -> requests.Session:
    """Session HTTP partagée entre les threads, avec retry sur les erreurs serveur."""
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=workers, pool_maxsize=workers)
    s = requests.Session()
    s.mount("https://", adapter)
    return s


def is_noaa_csv(head: bytes) -> bool:
    """Vrai si le contenu ressemble à un CSV NOAA (et pas à une page html d'erreur)."""
    return head.lstrip(b"\xef\xbb\xbf").startswith(b'"STATION"')


def download_one(session: requests.Session, station: str, year: int) -> tuple[str, str, int]:
    """Télécharge un fichier station/année. Renvoie (clé, statut, taille)."""
    key = f"{year}/{station}"
    dest = config.RAW_DIR / f"year={year}" / f"{station}.csv"
    if dest.exists() and dest.stat().st_size > 0:
        with open(dest, "rb") as f:
            if is_noaa_csv(f.read(20)):
                return key, "deja_present", dest.stat().st_size
        # sinon : fichier invalide d'un ancien run, on le retélécharge

    url = config.ACCESS_URL.format(year=year, station=station)
    r = session.get(url, timeout=config.TIMEOUT)
    if r.status_code in (403, 404):   # pas de données pour cette station cette année-là
        return key, "absent", 0
    r.raise_for_status()
    if not is_noaa_csv(r.content[:20]):
        raise ValueError("la réponse n'est pas un CSV NOAA (page html ?)")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")   # écriture atomique : pas de fichier à moitié écrit
    tmp.write_bytes(r.content)
    tmp.replace(dest)
    return key, "ok", len(r.content)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=int, nargs="+", default=config.YEARS)
    p.add_argument("--workers", type=int, default=config.MAX_WORKERS)
    p.add_argument("--cities-only", action="store_true")
    args = p.parse_args()

    stations = french_stations(args.years)
    if args.cities_only:
        stations = stations[stations["city"].notna()]
    jobs = [(s, y) for s in stations["station_id"] for y in args.years]
    print(f"{len(stations)} stations x {len(args.years)} années = {len(jobs)} fichiers à traiter "
          f"({args.workers} en parallèle)")

    session = make_session(args.workers)
    results, t0 = [], time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_one, session, s, y): (s, y) for s, y in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            s, y = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:  # on log et on continue, le fichier sera retenté au prochain run
                results.append((f"{y}/{s}", f"erreur: {e}", 0))
            if i % 50 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} ({time.time() - t0:.0f}s)")

    counts = {}
    for _, status, _ in results:
        k = "erreur" if status.startswith("erreur") else status
        counts[k] = counts.get(k, 0) + 1
    total_mb = sum(r[2] for r in results) / 1e6
    print(f"terminé en {time.time() - t0:.0f}s : {counts} — {total_mb:.0f} Mo")

    # journal du run, utile pour la traçabilité du data lake
    log = config.RAW_DIR / "_logs" / f"download_{datetime.now():%Y%m%d_%H%M%S}.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"years": args.years, "counts": counts, "files": results}, indent=1))


if __name__ == "__main__":
    main()
