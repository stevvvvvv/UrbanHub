"""Collecte récente des onze villes : heures agrégées des deux derniers jours.

Relancer régulièrement ; la collecte historique partage inventaire et cache.
OPENAQ_API_KEY doit être défini dans l'environnement.
"""
from datetime import datetime, timedelta, timezone
from .history import collect_history


def collect_openaq():
    today = datetime.now(timezone.utc).date()
    collect_history(str(today - timedelta(days=2)), str(today), refresh=True)


if __name__ == "__main__":
    collect_openaq()
