# Partie 4 — Contribution de Julien Cantau

## Périmètre

La copie locale contient déjà le commit `8276446`, fusion de la PR nº 1 OpenAQ. La contribution ajoutée ici est l'analyse croisée : préparation des données, météo complémentaire, jointures, indicateurs, diagnostics, notebook et documentation. Les pipelines et notebooks des parties 1 à 3 restent inchangés.

Aucune donnée réelle n'était présente dans `data/` lors du développement. Les résultats enregistrés dans `reports/partie4/` indiquent donc des sources absentes ; ils ne démontrent aucune relation entre météo, pollution et vélos. Les calculs sont vérifiés séparément avec des données simulées dans des répertoires temporaires. L'analyse empirique devra être relancée après réception des fichiers du groupe.

## Fichiers ajoutés et rôle

| Fichier | Rôle |
|---|---|
| `src/analysis_cross/config.py` | Chemins du data lake et les 11 villes du projet, repris du référentiel CityBikes |
| `src/analysis_cross/prepare.py` | Normalisation des villes, stocks et mouvements vélo, pollution horaire/journalière, agrégation NOAA, jointures validées |
| `src/analysis_cross/weather.py` | Requêtes Open-Meteo aux dates vélo, reprise depuis cache, unités, archivage brut et export UTC |
| `src/analysis_cross/run.py` | Pipeline hors réseau, audit de couverture, quatre croisements, corrélations et synthèse |
| `src/analysis_cross/plots.py` | Figures de corrélation et comparaison pluie/sec par ville, heure et type de jour |
| `notebooks/04_partie4_analyse_croisee.ipynb` | Questions, exécution des calculs, graphiques et interprétation méthodologique |
| `tests/test_analysis_cross.py` | Vérifications des risques spécifiques aux croisements et exécution de bout en bout |

## Installation et exécution

Depuis la racine du dépôt sous macOS/Linux :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Sous PowerShell, activer avec `.venv\Scripts\Activate.ps1`. Les commandes suivantes sont ensuite identiques.

### 1. Préparer les entrées

Recevoir les fichiers réels du groupe ou rejouer les pipelines existants. `download` et `clean` seuls ne créent pas `noaa_daily.parquet` : il faut également exécuter les cellules du notebook 01 jusqu'à l'export.

```bash
python -m src.batch_noaa.download --cities-only
python -m src.batch_noaa.clean
jupyter notebook notebooks/01_partie1_meteo_batch.ipynb

# Terminal dédié, Ctrl+C après une durée de collecte suffisante :
python -m src.streaming_citybikes.collector
python -m src.streaming_citybikes.process
```

Pour OpenAQ, utiliser la clé et les commandes de la partie 3. Le pipeline croisé consomme `data/processed/openaq/pollution_clean.parquet`. Ne pas placer la clé dans le notebook ni dans Git.

### 2. Ajouter la météo des dates vélo

```bash
python -m src.analysis_cross.weather
# Réinterroger l'API et remplacer le cache :
python -m src.analysis_cross.weather --refresh
```

La collecte déduit villes et bornes depuis les données vélo. Les requêtes couvrent au plus 31 jours chacune, au centre de chaque ville, jusqu'à la veille au plus tard. Une indisponibilité de l'API remonte comme une erreur ; aucune prévision ou donnée simulée n'est substituée silencieusement. Les dates de collecte futures ou non encore disponibles ne sont pas inventées. Relancer plus tard si nécessaire.

Données demandées : température à 2 m (°C), précipitations (mm), vent à 10 m (m/s), humidité relative (%). Les unités de la réponse sont contrôlées. Les réponses sont archivées avec URL, date UTC de téléchargement et origine des données vélo. La météo est une estimation de modèles/réanalyses ; elle n'est pas interchangeable avec une mesure de station NOAA. Source et attribution : [Open-Meteo, Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api).

### 3. Exécuter l'analyse

```bash
python -m src.analysis_cross.run
jupyter notebook notebooks/04_partie4_analyse_croisee.ipynb
python -m pytest tests -v
```

Le notebook n'appelle aucune API. Il fonctionne en l'absence de certaines sources et affiche les diagnostics correspondants. Une source présente mais mal formée entraîne une erreur explicite plutôt qu'un résultat silencieusement vide.

Pour changer de data lake, définir `URBANHUB_DATA_DIR` avant de lancer Python/Jupyter. Le CLI accepte aussi des répertoires explicites pour isoler les exports :

```bash
python -m src.analysis_cross.run --processed /chemin/data/processed --output /chemin/tables --reports /chemin/rapports
```

## Choix de calcul

### Temps, villes et jointures

Les mesures horaires sont en UTC, y compris lors du changement d'heure. Les dates journalières sont des étiquettes civiles Europe/Paris, conformément au notebook NOAA. Les villes sont rapprochées par nom exact normalisé (casse et accents) ; aucune correspondance approximative par sous-chaîne n'est inventée. Une localité périphérique OpenAQ ne sera donc pas arbitrairement attribuée à une métropole.

Les jointures sont internes, sur les clés temporelles exactes. On moyenne les deux stations parisiennes avant de joindre NOAA pour éviter de multiplier les observations de pollution. Les doublons de la table de droite font échouer la jointure validée. Les 12 stations NOAA représentent 11 villes.

### Vélos : éviter les biais de fréquence de collecte

L'export du notebook 02 additionne `bikes_available` à travers les collectes d'une heure : ce nombre augmente mécaniquement avec la fréquence de collecte et n'est pas un stock instantané.

Lorsque les parquets par station sont disponibles, la partie 4 recalcule :

- **Offre** : somme des vélos par collecte, puis moyenne des stocks collectés dans l'heure.
- **Remplissage** : moyenne du rapport vélos/capacité, borné entre 0 et 1.
- **Mouvements apparents** : variation absolue de stock par station entre deux observations distantes de dix minutes au maximum.
- **Activité par station et heure** : somme des variations divisée par la somme des durées valides en station-heures. La première observation n'est pas une activité nulle. Les intervalles sont affectés à l'heure de leur fin.
- **Contexte** : nombre moyen de stations par collecte, nombre de collectes, exposition totale.

Si seul `citybikes_hourly.parquet` est disponible, le pipeline conserve le remplissage et écarte les stocks et mouvements agrégés dont l'exposition est inconnue. Il signale ce mode dégradé. Marseille et Nice sont exclues du croisement vélo selon le périmètre convenu.

Le rééquilibrage, les mouvements qui se compensent, la composition du réseau et les observations manquantes limitent ces indicateurs. Les parquets par station sont préférables pour toute conclusion sur l'activité.

### Pollution : capteurs, couverture et unités

On exclut les dates invalides, valeurs négatives/non finies et identifiants/polluants/unités absents. Les répétitions d'une même mesure sont supprimées. Les observations sont moyennées par capteur et heure puis par ville, polluant et unité. Les formes typographiques µ et μ sont harmonisées ; aucune conversion ppb–µg/m³ n'est tentée.

Pour le journalier, chaque capteur doit disposer d'au moins 18 heures distinctes valides sur la date locale. Les capteurs admissibles sont moyennés avec un poids égal. Ce critère est un choix de complétude du projet, pas une validation réglementaire. Aucun indice sanitaire ou seuil réglementaire n'est calculé.

### Analyse statistique

Les corrélations de Spearman sont calculées par ville, polluant et unité sur les couples valides ; elles nécessitent 30 couples et sept dates locales au minimum. Les variables constantes donnent un diagnostic, pas une valeur artificielle. Chaque résultat indique effectif, nombre de jours et statut.

Il s'agit de corrélations bivariées descriptives, y compris dans la table des trois flux. Elles ne sont pas corrigées des saisons ou des rythmes horaires et ne démontrent aucune causalité. La comparaison pluie/sec est séparée par ville, heure locale et semaine/week-end ; ses effectifs permettent de repérer les groupes incomparables. Aucune p-value n'est produite puisque l'autocorrélation n'est pas modélisée.

## Sorties

Les quatre tables dans `data/processed/cross_analysis/` :

| Table | Grain | Sources |
|---|---|---|
| `meteo_velos.parquet` | ville/heure UTC | CityBikes + Open-Meteo |
| `meteo_pollution.parquet` | ville/date locale/polluant/unité | OpenAQ + NOAA |
| `pollution_velos.parquet` | ville/heure UTC/polluant/unité | OpenAQ + CityBikes |
| `trois_flux.parquet` | ville/heure UTC/polluant/unité | OpenAQ + CityBikes + Open-Meteo |

Dans `reports/partie4/` : `couverture.csv`, quatre fichiers `correlations_*.csv`, `diagnostic.json`, `synthese.md`. Le notebook ajoute `audit_villes.csv`, les figures, ainsi que les comparaisons pluie/sec et profils horaires si les données le permettent. L'audit montre les effectifs et bornes de chaque source ; les tables jointes donnent la couverture effectivement commune.

## Limites héritées de la version OpenAQ intégrée

L'inspection du code intégré montre que :

1. `collector.py` demande seulement la première page de 20 localisations françaises ; la liste `CITIES` de son fichier de configuration ne filtre pas la collecte.
2. `history.py` sélectionne un seul capteur NO₂ parisien et demande les sept derniers jours, sans historique 2021–2025.
3. `process.py` élimine les mesures de plus de 30 jours : injecter un historique ancien ne suffit donc pas à le rendre exploitable.
4. Les chemins de cette partie sont relatifs à la racine et ne suivent pas encore `URBANHUB_DATA_DIR`.

Pour obtenir le croisement NOAA–OpenAQ réel, le groupe doit étendre cette collecte (inventaire/pagination et disponibilité des capteurs, plages historiques explicites, conservation des anciennes données). La partie 4 prend déjà en charge l'historique une fois celui-ci fourni au format nettoyé attendu. Ces changements n'ont pas été faits dans la contribution du collègue afin de garder un périmètre de responsabilité clair.

## Trame de présentation orale

« J'ai réalisé la couche d'analyse croisée du data lake. J'ai commencé par vérifier la compatibilité des villes, dates, unités et grains. Les vélos sont récents, donc j'ai ajouté une collecte météo Open-Meteo aux dates observées. J'ai corrigé dans ma préparation le biais lié à la somme des stocks vélo répétés, et normalisé les variations par le temps observé. J'ai construit quatre tables de jointure, un audit de couverture et des analyses descriptives. Le notebook explique les limites : pas de correspondance entre années différentes, pas de conversion implicite d'unités, pas de causalité déduite des corrélations. Sans données communes, le résultat est un diagnostic d'impossibilité plutôt qu'une conclusion inventée. »

Cette trame décrit le travail logiciel effectivement réalisé ; les observations métier chiffrées devront provenir de la réexécution sur les fichiers réels du groupe.
