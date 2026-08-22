"""
Tracé des tournées sur le réseau routier réel, via OSRM.

Sans ce module, les tournées sont dessinées en segments droits d'un client à
l'autre : les livreurs traversent les immeubles et la Seine. Ici, chaque segment
est remplacé par l'itinéraire routier effectif.

Choix techniques
----------------
* **OSRM** (serveur public de démonstration) plutôt qu'OpenRouteService ou
  GraphHopper : il ne demande **aucune clé d'API**, donc aucun secret à stocker
  ni à faire fuir — ce qui compte pour un dépôt public.
* **Une requête par tournée**, pas une par segment : `steps=true` renvoie la
  géométrie découpée par étape, ce qui permet de reconstituer chaque segment
  client→client tout en divisant le nombre d'appels par ~18.
* **Cache disque** : le serveur public est limité en débit et les données jouet
  sont régénérées à chaque exécution. Le cache rend les relances instantanées.
  Il est facultatif : ni sa lecture ni son écriture ne peuvent faire échouer un
  calcul. Son emplacement se règle par `OSRM_CACHE_DIR`, ce qui compte sur un
  hébergement où seul `/tmp` est accessible en écriture.
* **Repli silencieux en ligne droite** : sans réseau, le projet doit continuer à
  tourner. On perd le réalisme du tracé, jamais l'exécution.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request

OSRM_BASE_URL = os.environ.get(
    "OSRM_BASE_URL", "https://router.project-osrm.org"
)
DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "osrm")
#: Conservé pour les appelants qui l'importaient. Utiliser `cache_dir()`, qui
#: relit l'environnement à chaque appel.
CACHE_DIR = DEFAULT_CACHE_DIR
REQUEST_TIMEOUT = 30


def cache_dir():
    """
    Répertoire du cache d'itinéraires.

    Lu à chaque appel plutôt que figé à l'import : sur un hébergement sans
    système de fichiers inscriptible ailleurs que dans `/tmp`, la variable
    `OSRM_CACHE_DIR` doit pouvoir être posée après le chargement du module.
    """
    return os.environ.get("OSRM_CACHE_DIR", DEFAULT_CACHE_DIR)


def _cache_path(waypoints):
    """Chemin de cache déterministe pour une suite de points de passage."""
    key = json.dumps([[round(lat, 6), round(lon, 6)] for lat, lon in waypoints])
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return os.path.join(cache_dir(), f"{digest}.json")


def _read_cache(cache_file):
    """
    Lit une entrée de cache, ou renvoie None si elle est absente ou illisible.

    Un fichier tronqué par une exécution interrompue ne doit pas faire échouer
    la requête : le calcul repart vers OSRM, et l'entrée sera réécrite.
    """
    try:
        with open(cache_file, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"   ⚠️  Cache OSRM illisible ({exc}), recalcul.")
        return None


def _write_cache(cache_file, legs):
    """
    Enregistre une entrée de cache, sans jamais faire échouer l'appelant.

    Deux précautions :

    * **l'écriture est facultative.** Sur un système de fichiers en lecture
      seule, `makedirs` lève `OSError: Read-only file system`. Cette écriture se
      trouvait hors du `try` : un appel OSRM **réussi** faisait alors échouer la
      requête entière, alors que le chemin d'échec, lui, était protégé. Le cas
      typique est l'exécution sans serveur, où seul `/tmp` est inscriptible.
    * **l'écriture est atomique.** Un fichier temporaire puis `os.replace`,
      opération atomique sur un même système de fichiers. Deux résolutions
      simultanées portant sur la même tournée ne peuvent plus entrelacer leurs
      écritures et laisser un JSON tronqué derrière elles.
    """
    directory = os.path.dirname(cache_file)
    handle = temporary = None
    try:
        os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(legs, handle)
        os.replace(temporary, cache_file)
    except OSError as exc:
        print(f"   ⚠️  Cache OSRM non écrit ({exc}), le tracé reste valide.")
        if temporary is not None and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _straight_legs(waypoints):
    """Repli : un segment droit entre chaque paire de points consécutifs."""
    return [
        [list(waypoints[i]), list(waypoints[i + 1])]
        for i in range(len(waypoints) - 1)
    ]


def fetch_route_legs(waypoints):
    """
    Renvoie la géométrie routière de chaque segment d'une tournée.

    :param waypoints: Liste de (latitude, longitude), dans l'ordre de visite
    :return: Liste de segments ; chaque segment est une liste de [lat, lon]
             suivant les rues. En cas d'échec réseau, segments droits.
    """
    if len(waypoints) < 2:
        return []

    cache_file = _cache_path(waypoints)
    cached = _read_cache(cache_file)
    if cached is not None:
        return cached

    # OSRM attend des couples lon,lat — l'inverse de la convention usuelle.
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    url = (
        f"{OSRM_BASE_URL}/route/v1/driving/{coords}"
        "?overview=full&geometries=geojson&steps=true"
    )

    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"   ⚠️  OSRM injoignable ({exc}) — tracé en lignes droites.")
        return _straight_legs(waypoints)

    if payload.get("code") != "Ok" or not payload.get("routes"):
        print(f"   ⚠️  OSRM a répondu '{payload.get('code')}' — tracé en lignes droites.")
        return _straight_legs(waypoints)

    legs = []
    for leg in payload["routes"][0]["legs"]:
        points = []
        for step in leg["steps"]:
            # Les étapes se chevauchent d'un point : on retire le doublon.
            coordinates = step["geometry"]["coordinates"]
            for lon, lat in coordinates:
                point = [lat, lon]
                if not points or points[-1] != point:
                    points.append(point)
        legs.append(points if len(points) >= 2 else None)

    # Un segment vide (point non raccordé au réseau) retombe en ligne droite.
    straight = _straight_legs(waypoints)
    legs = [leg if leg else straight[i] for i, leg in enumerate(legs)]

    _write_cache(cache_file, legs)

    return legs


def build_road_legs(locations, routes):
    """
    Construit la géométrie routière de toutes les tournées.

    :param locations: Coordonnées (lat, lon) indexées par numéro de nœud
    :param routes: Une liste de nœuds par véhicule
    :return: Dictionnaire "noeud_depart-noeud_arrivee" → liste de [lat, lon].
             Les clés sont des chaînes pour survivre à la sérialisation JSON
             vers le navigateur.
    """
    road_legs = {}
    for route in routes:
        if len(route) < 2:
            continue
        waypoints = [tuple(locations[node]) for node in route]
        legs = fetch_route_legs(waypoints)
        for i, leg in enumerate(legs):
            road_legs[f"{route[i]}-{route[i + 1]}"] = leg
    return road_legs
