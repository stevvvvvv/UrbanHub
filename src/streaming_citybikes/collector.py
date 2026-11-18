"""Collecte automatique de l'état des stations de vélos (API CityBikes).

Usage :
    python -m src.streaming_citybikes.collector              # tourne en continu (Ctrl+C pour arrêter)
    python -m src.streaming_citybikes.collector --once       # une seule collecte (test)
    python -m src.streaming_citybikes.collector --hours 24   # s'arrête au bout de 24h

Chaque collecte interroge tous les réseaux en parallèle et dépose la réponse brute dans le
data lake : data/raw/citybikes/dt=YYYY-MM-DD/<reseau>/<HHMMSS>.json.gz
Garder le brut permet de rejouer le traitement sans rappeler l'API.

L'API ne fournit que l'état actuel des stations, pas d'historique : les données n'existent
que pour la période où ce script a tourné.
"""
import argparse
import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config


def make_session() -> requests.Session:
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=len(config.NETWORKS)))
    s.headers["User-Agent"] = config.USER_AGENT
    return s


def fetch_network(session: requests.Session, network: str, collected_at: datetime) -> tuple[str, int]:
    """Récupère un réseau et l'écrit dans le data lake. Renvoie (réseau, nb de stations)."""
    r = session.get(config.API_URL.format(network=network), timeout=config.TIMEOUT)
    r.raise_for_status()
    payload = r.json()

    stations = payload["network"]["stations"]
    for st in stations:
        # la liste des identifiants de vélos est volumineuse et inutile pour nos analyses
        (st.get("extra") or {}).pop("bike_uids", None)
    payload["collected_at"] = collected_at.isoformat()

    dest = (config.RAW_DIR / f"dt={collected_at:%Y-%m-%d}" / network / f"{collected_at:%H%M%S}.json.gz")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(dest, "wt", encoding="utf-8") as f:
        json.dump(payload, f)
    return network, len(stations)


def collect_once(session: requests.Session, networks: list[str]) -> None:
    collected_at = datetime.now(timezone.utc).replace(microsecond=0)
    ok, errors = 0, []
    with ThreadPoolExecutor(max_workers=len(networks)) as pool:
        futures = {pool.submit(fetch_network, session, n, collected_at): n for n in networks}
        for fut, n in futures.items():
            try:
                _, count = fut.result()
                ok += count
            except Exception as e:   # un réseau en panne ne doit pas arrêter la collecte
                errors.append(f"{n} ({type(e).__name__})")
    local = collected_at.astimezone().strftime("%H:%M:%S")
    msg = f"[{local}] {ok} stations collectées"
    if errors:
        msg += f" — échecs : {', '.join(errors)}"
    print(msg, flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=int, default=config.INTERVAL_S, help="secondes entre deux collectes")
    p.add_argument("--networks", nargs="+", default=list(config.NETWORKS))
    p.add_argument("--hours", type=float, help="durée de collecte (par défaut : infinie)")
    p.add_argument("--once", action="store_true")
    args = p.parse_args()

    session = make_session()
    if args.once:
        collect_once(session, args.networks)
        return

    print(f"collecte de {len(args.networks)} réseaux toutes les {args.interval}s — Ctrl+C pour arrêter")
    start = time.monotonic()
    n = 0
    try:
        while args.hours is None or time.monotonic() - start < args.hours * 3600:
            collect_once(session, args.networks)
            n += 1
            # on cale les collectes sur une grille fixe : pas de dérive dans le temps
            time.sleep(max(0, start + n * args.interval - time.monotonic()))
    except KeyboardInterrupt:
        print("arrêt demandé")
    print(f"{n} collectes effectuées")


if __name__ == "__main__":
    main()
