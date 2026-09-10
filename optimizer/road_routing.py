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
import math
import os
import tempfile
import time
import urllib.error
import urllib.request

#: Serveur de routage. Par défaut l'instance **cycliste** de FOSSGIS.
#:
#: `routing.openstreetmap.de` héberge trois instances OSRM derrière trois
#: préfixes, et ce sont bien trois graphes distincts. Mesuré sur un même couple
#: de points parisiens :
#:
#: ===============  ==========  ==========  =====================
#: préfixe          distance    durée       vitesse implicite
#: ===============  ==========  ==========  =====================
#: `routed-bike`     1 744,2 m    786,6 s    8,0 km/h
#: `routed-car`      1 140,0 m    205,9 s   19,9 km/h
#: `routed-foot`     1 256,5 m  1 005,5 s    4,5 km/h
#: ===============  ==========  ==========  =====================
#:
#: C'est le **préfixe d'hôte** qui choisit le graphe, jamais le segment de
#: profil dans le chemin : `/route/v1/driving/` et `/route/v1/bike/` rendent le
#: même résultat sur `routed-bike`. Ne pas confondre les deux, sous peine de
#: croire avoir changé de moteur en changeant l'URL.
#:
#: Conditions d'usage (<https://routing.openstreetmap.de/about.html>) : une
#: requête par seconde au plus, un `User-Agent` identifiant l'application — celui
#: d'une bibliothèque est explicitement jugé insuffisant — et l'attribution des
#: données côté interface. L'hôte n'est délibérément pas figé dans le code, les
#: conditions le recommandent, et cela laisse la porte ouverte à une instance
#: locale ou à un autre fournisseur.
#:
#: Aucune disponibilité n'est garantie : le cache disque et le repli à vol
#: d'oiseau sont ce qui rend une panne supportable.
OSRM_BASE_URL = os.environ.get(
    "OSRM_BASE_URL", "https://routing.openstreetmap.de/routed-bike"
)

#: Identité envoyée au serveur de routage. Les conditions de FOSSGIS refusent
#: explicitement le `User-Agent` d'une bibliothèque — `urllib` annonce
#: `Python-urllib/3.12`, exactement ce qu'elles écartent — et bloquent
#: l'usurpation. C'est la première cause de blocage, et elle est gratuite à
#: éviter.
USER_AGENT = os.environ.get(
    "OSRM_USER_AGENT",
    "livraison-cvrptw/1.0 (+https://github.com/Skeeder1/livraison)",
)

#: Intervalle minimal entre deux requêtes, en secondes. Les conditions imposent
#: une requête par seconde et une seule connexion pour un script. La géométrie
#: est demandée une fois par véhicule, donc jusqu'à six fois d'affilée : sans
#: cette attente, une seule résolution suffirait à dépasser le débit autorisé.
INTERVALLE_MINIMAL_S = float(os.environ.get("OSRM_MIN_INTERVAL", "1.0"))

#: Date de la dernière requête, pour tenir l'intervalle, à l'échelle du
#: processus. Un flottant de module suffit ici : `solve_scenario` n'est de toute
#: façon pas sûre en concurrence dans un même processus et ses appelants la
#: sérialisent déjà.
_derniere_requete = 0.0

#: Fichier de rendez-vous entre **processus**, quand il y en a plusieurs.
#:
#: Le compteur ci-dessus est une variable de module : quatre processus en ont
#: quatre exemplaires, donc quatre requêtes par seconde là où le serveur en
#: autorise une. Le débit n'est pas une propriété de notre programme, c'est une
#: obligation envers un service tiers, et elle ne se divise pas entre les
#: processus qui s'en servent.
#:
#: Le verrou n'existe que si `OSRM_THROTTLE_FILE` est posée. Une exécution
#: unique — le cas courant — ne paie donc ni ouverture de fichier ni `flock`, et
#: le pré-calcul en parallèle la pose pour tous ses ouvriers.
FICHIER_ETRANGLEMENT = os.environ.get("OSRM_THROTTLE_FILE")


def _attendre_son_tour():
    """
    Fait respecter l'intervalle minimal, entre processus s'il le faut.

    Le fichier porte la date de la dernière requête émise par n'importe quel
    processus, en secondes depuis l'époque — et non `time.monotonic()`, dont
    l'origine est propre à chaque processus et n'est donc pas comparable.

    Le verrou est tenu **pendant** l'attente, et pas seulement pendant la
    lecture. C'est ce qui sérialise les ouvriers : le second lit la date du
    premier, dort le temps qu'il faut, écrit la sienne, puis relâche. Sans cela
    quatre ouvriers liraient la même date, dormiraient le même temps et
    partiraient ensemble — exactement la rafale qu'on cherche à éviter.
    """
    if not FICHIER_ETRANGLEMENT:
        global _derniere_requete
        depuis = time.monotonic() - _derniere_requete
        if depuis < INTERVALLE_MINIMAL_S:
            time.sleep(INTERVALLE_MINIMAL_S - depuis)
        _derniere_requete = time.monotonic()
        return

    import fcntl

    chemin = FICHIER_ETRANGLEMENT
    os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
    with open(chemin, "a+", encoding="utf-8") as verrou:
        fcntl.flock(verrou.fileno(), fcntl.LOCK_EX)
        try:
            verrou.seek(0)
            contenu = verrou.read().strip()
            try:
                precedente = float(contenu)
            except ValueError:
                precedente = 0.0
            depuis = time.time() - precedente
            if 0 <= depuis < INTERVALLE_MINIMAL_S:
                time.sleep(INTERVALLE_MINIMAL_S - depuis)
            verrou.seek(0)
            verrou.truncate()
            verrou.write(f"{time.time():.6f}")
            verrou.flush()
        finally:
            fcntl.flock(verrou.fileno(), fcntl.LOCK_UN)

#: Segment de profil dans le chemin de l'API. **Cosmétique** : `osrm-routed` sert
#: le graphe sur lequel il a été démarré et ignore ce segment. C'est
#: `OSRM_BASE_URL` qui décide du mode de déplacement, pas cette valeur.
#:
#: Elle reste dans la clé de cache parce qu'une instance tierce, elle, pourrait
#: le lire, et que deux moteurs ne doivent jamais se relire l'un l'autre.
#:
#: Ce que change vraiment le passage de la voiture au vélo, mesuré sur les 48
#: points réels de l'instance de référence, 2 256 couples, `routed-bike` contre
#: `routed-car` :
#:
#: * distances vélo/voiture : médiane 0,935 — le vélo coupe par où la voiture ne
#:   passe pas (contresens cyclables, voies vertes), et rallonge ailleurs ;
#: * durées vélo/voiture : médiane 1,883. Vitesse implicite 28,0 km/h pour la
#:   voiture contre **13,2 km/h** pour le vélo ;
#: * mesure indépendante sur le moteur Valhalla, 380 couples : 0,945 et 1,523,
#:   16,7 km/h. Deux moteurs, même conclusion sur le sens et l'ordre de grandeur.
#:
#: Le classement des arcs par longueur se déplace d'une médiane de 14 places sur
#: 380 : ce n'est pas une homothétie, le solveur ne choisit pas les mêmes arcs.
#: `VITESSE_DE_REPLI_M_PAR_S` et `Config.DISTANCE_TO_TIME_FACTOR`, tous deux calés
#: sur 20 km/h, sont donc optimistes d'environ moitié par rapport au routage réel.
OSRM_PROFILE = os.environ.get("OSRM_PROFILE", "bike")
DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "osrm")
#: Conservé pour les appelants qui l'importaient. Utiliser `cache_dir()`, qui
#: relit l'environnement à chaque appel.
CACHE_DIR = DEFAULT_CACHE_DIR
#: Patience accordée à une requête de **géométrie**, en secondes.
#:
#: La géométrie est cosmétique : sans elle `tour_format` trace une droite et
#: marque `legs[].road` à faux. Une tournée reste juste. Mesuré sur le serveur
#: de FOSSGIS, six itinéraires successifs à une seconde d'intervalle : 0,22 à
#: 0,45 s chacun, sans pénalité de débit. Une patience courte suffit donc, et
#: c'est elle qui protège le budget d'une requête qui traîne.
REQUEST_TIMEOUT = 30

#: Patience accordée à la requête de **matrice**, en secondes.
#:
#: Séparée de la précédente parce que les deux ne pèsent pas la même chose : la
#: matrice décide de la tournée, la géométrie ne fait que la dessiner. Perdre la
#: matrice fait retomber tout le problème sur des distances à vol d'oiseau, donc
#: sur une ville sans rues ; perdre un tracé ne coûte qu'une ligne droite.
#:
#: Le chiffre vient de la mesure, et il est nettement plus élevé qu'on ne
#: l'attendrait. Une matrice de 65 points est facturée par le limiteur du serveur
#: comme les 4 225 itinéraires qu'elle représente : la première rend en 0,38 à
#: 0,49 s, les suivantes à une seconde d'intervalle en **8,9 à 10,0 s**, puis le
#: serveur répond 429. Une patience de deux secondes — ce que le budget de six
#: secondes donnait à trois véhicules — jetait donc une réponse correcte qui
#: était simplement en train d'arriver.
TABLE_TIMEOUT = 20

#: Vitesse retenue pour combler un couple qu'OSRM ne sait pas relier, en m/s.
#: 20 km/h, l'ordre de grandeur d'un vélo cargo en ville.
VITESSE_DE_REPLI_M_PAR_S = 20_000 / 3600


def _ouvrir(url, *, timeout_matrice=False):
    """
    Effectue une requête vers le serveur de routage, en respectant ses règles.

    Deux choses qu'aucun des deux appelants ne doit avoir à se rappeler : le
    `User-Agent` exigé, et l'intervalle d'une seconde entre deux requêtes. Les
    centraliser ici est ce qui garantit qu'elles s'appliquent aux itinéraires
    comme à la matrice — et, si `OSRM_THROTTLE_FILE` est posée, à tous les
    processus à la fois.

    L'attente est faite avant l'appel et non après : deux requêtes séparées
    naturellement par un long calcul ne paient rien.

    :param timeout_matrice: Applique `TABLE_TIMEOUT` plutôt que
        `REQUEST_TIMEOUT`. Une matrice et un tracé ne méritent pas la même
        patience, cf. les deux constantes.
    """
    _attendre_son_tour()
    requete = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(
        requete, timeout=TABLE_TIMEOUT if timeout_matrice else REQUEST_TIMEOUT
    )


def cache_dir():
    """
    Répertoire du cache d'itinéraires.

    Lu à chaque appel plutôt que figé à l'import : sur un hébergement sans
    système de fichiers inscriptible ailleurs que dans `/tmp`, la variable
    `OSRM_CACHE_DIR` doit pouvoir être posée après le chargement du module.
    """
    return os.environ.get("OSRM_CACHE_DIR", DEFAULT_CACHE_DIR)


def _cache_path(waypoints, prefix=""):
    """Chemin de cache déterministe pour une suite de points de passage.

    :param prefix: Distingue deux usages des mêmes points — la géométrie d'un
        itinéraire et la matrice complète n'ont pas le même contenu, et sans lui
        la seconde écraserait la première.
    """
    # Le serveur et le profil font partie de la clé. Sans eux, basculer vers une
    # instance cycliste relirait les itinéraires voiture déjà en cache : le
    # changement de moteur n'aurait aucun effet visible, et le cache mentirait
    # d'autant plus longtemps qu'il est persistant.
    key = json.dumps(
        [prefix, OSRM_BASE_URL, OSRM_PROFILE]
        + [[round(lat, 6), round(lon, 6)] for lat, lon in waypoints]
    )
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return os.path.join(cache_dir(), f"{digest}.json")


def _read_cache(cache_file):
    """
    Lit une entrée de cache, ou renvoie None si elle est absente ou illisible.

    Un fichier tronqué par une exécution interrompue ne doit pas faire échouer
    la requête : le calcul repart vers OSRM, et l'entrée sera réécrite.
    """
    try:
        with open(cache_file, encoding="utf-8") as handle:
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


def _haversine_m(a, b):
    """Distance géodésique en mètres entre deux couples (latitude, longitude)."""
    rayon = 6371000.0
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat = lat2 - lat1
    dlon = math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * rayon * math.asin(math.sqrt(h))


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
        f"{OSRM_BASE_URL}/route/v1/{OSRM_PROFILE}/{coords}"
        "?overview=full&geometries=geojson&steps=true"
    )

    try:
        with _ouvrir(url) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"   ⚠️  OSRM injoignable ({exc}) — aucune géométrie routière.")
        return [None] * (len(waypoints) - 1)

    if payload.get("code") != "Ok" or not payload.get("routes"):
        print(f"   ⚠️  OSRM a répondu '{payload.get('code')}' — aucune géométrie routière.")
        return [None] * (len(waypoints) - 1)

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

    # Un segment non raccordé au réseau reste None : c'est `tour_format` qui
    # tracera la ligne droite, et il marquera alors `road: false`. Y substituer
    # ici une géométrie droite la rendait indiscernable d'un vrai tracé routier,
    # et `legs[].road` valait `true` même hors ligne.

    _write_cache(cache_file, legs)

    return legs


class TableIndisponible(RuntimeError):
    """OSRM n'a pas rendu de matrice — l'appelant décide quoi faire."""


def fetch_table(locations):
    """Matrice des distances et des durées ROUTIÈRES entre tous les points.

    Renvoie ``(distances_m, durations_s)``, deux tableaux N×N.

    Le solveur optimisait jusqu'ici des distances euclidiennes, pendant que la
    carte affichait le vrai réseau : les tournées étaient donc optimales pour une
    ville sans rues. Sur Paris, l'écart n'est pas cosmétique — un trajet mesuré
    ici fait 7 228 m par la route contre 5 723 m à vol d'oiseau, soit un détour
    de 26 %. La Seine, les sens uniques et les vitesses changent les décisions,
    pas seulement le dessin.

    Le service ``/table`` rend la matrice complète en **une seule requête**, et
    non une par couple : 48 points, 2 304 valeurs, mesuré à 0,2 s. C'est ce qui
    rend l'approche praticable sans serveur local.

    :param locations: Coordonnées (latitude, longitude) indexées par nœud
    :return: Deux tableaux N×N, mètres et secondes
    :raises TableIndisponible: OSRM injoignable ou réponse inexploitable
    """
    import numpy as np

    if len(locations) < 2:
        raise TableIndisponible("il faut au moins deux points")

    cache_file = _cache_path(locations, prefix="table")
    cached = _read_cache(cache_file)
    if cached is not None:
        return np.array(cached["distances"]), np.array(cached["durations"])

    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in locations)
    url = f"{OSRM_BASE_URL}/table/v1/{OSRM_PROFILE}/{coords}?annotations=duration,distance"

    try:
        with _ouvrir(url, timeout_matrice=True) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise TableIndisponible(f"OSRM injoignable : {exc}") from exc

    if payload.get("code") != "Ok":
        raise TableIndisponible(f"OSRM a répondu « {payload.get('code')} »")

    distances = payload.get("distances")
    durations = payload.get("durations")
    if not distances or not durations:
        raise TableIndisponible("réponse sans matrice")

    # Un couple non raccordé au réseau vaut None. Le remplacer par le vol
    # d'oiseau, et par une durée cohérente, plutôt que de rejeter toute la
    # matrice pour un point mal placé — mais le signaler.
    manquants = 0
    for i in range(len(locations)):
        for j in range(len(locations)):
            if distances[i][j] is None or durations[i][j] is None:
                manquants += 1
                d = _haversine_m(locations[i], locations[j])
                distances[i][j] = d
                durations[i][j] = d / VITESSE_DE_REPLI_M_PAR_S
    if manquants:
        print(f"   ⚠️  {manquants} couple(s) non raccordé(s) au réseau, comblés à vol d'oiseau.")

    _write_cache(cache_file, {"distances": distances, "durations": durations})
    return np.array(distances), np.array(durations)


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
            # Une absence de géométrie n'est pas inscrite : le consommateur
            # distingue ainsi un tracé routier réel d'un repli en ligne droite.
            if leg:
                road_legs[f"{route[i]}-{route[i + 1]}"] = leg
    return road_legs
