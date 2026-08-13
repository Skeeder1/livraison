"""
Résolution d'un scénario à la demande, appelable depuis un service web.

`optimizer.main` est un programme : il colore la sortie, reconfigure les flux
standard, écrit trois variables d'environnement `GLOG_*` et dépose un fichier
HTML. Rien de tout cela n'a sa place dans un processus serveur. Ce module offre
le même calcul sous forme de fonction : des paramètres entrent, un document de
tournée sort.

    from pathlib import Path
    from optimizer.scenario import solve_scenario

    tour = solve_scenario(
        {"customers": 45, "vehicles": 3, "hubs": 2, "budget_seconds": 30},
        workdir=Path("/tmp/scenario-1234"),
    )

Trois différences assumées avec `optimizer.main`, détaillées dans `solve_scenario` :
une seule résolution, aucune distance de référence, aucun rendu.
"""
from __future__ import annotations

import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Dict

from optimizer.config import Config
from optimizer.create_toy_data import create_toy_data
from optimizer.data_loader import load_data
from optimizer.postprocessor import get_results
from optimizer.road_routing import build_road_legs
from optimizer.solver import solve_vrp
from optimizer.tour_format import build_tour
from optimizer.trace import (
    compute_cumulative_loads,
    compute_slacks,
    convert_to_json_serializable,
)


class ScenarioParamsError(ValueError):
    """Paramètres refusés : clé inconnue, type invalide, ou valeur hors bornes."""


class NoSolutionError(RuntimeError):
    """Le solveur n'a rien trouvé dans le budget imparti."""


#: Bornes appliquées **côté serveur**, indépendamment de ce que demande le client.
#: Un scénario est du temps CPU : sans plafond, une requête suffit à saturer la
#: machine. Les valeurs hautes correspondent à quelques dizaines de secondes de
#: calcul sur un cœur.
SCENARIO_LIMITS: Dict[str, tuple] = {
    'customers': (1, 120),
    'vehicles': (1, 8),
    'hubs': (0, 4),
    'capacity': (1, 50),
    'budget_seconds': (1, 60),
}

#: Valeurs par défaut : le scénario de référence de la démonstration.
SCENARIO_DEFAULTS: Dict[str, Any] = {
    'customers': 45,
    'vehicles': 3,
    'hubs': 2,
    'capacity': 10,
    'time_windows_binding': False,
    'budget_seconds': 30,
    'seed': 42,
    'hub_transfers': False,
}

#: Fenêtres horaires contraignantes : fin tirée entre 2 h et 6 h après l'ouverture.
#: Les tournées de référence s'étalent sur ~2 h, si bien qu'une partie des clients
#: devient effectivement difficile à servir dans les temps, ce que le solveur
#: arbitre contre pénalité (`Config.TIME_WINDOW_VIOLATION_PENALTY`).
BINDING_TW_END_MIN = 7200
BINDING_TW_END_MAX = 21600

#: Fenêtres non contraignantes : la journée entière, comme dans la démonstration.
OPEN_TW_END = 86400

#: Budget d'une passe de recherche à grand voisinage. C'est la valeur par défaut
#: d'OR-Tools 9.15 ; on l'épingle pour que le budget total reste le seul levier.
LNS_TIME_LIMIT_MS = 100


def _ortools_version() -> str:
    try:
        return version('ortools')
    except PackageNotFoundError:  # installation sans métadonnées
        return 'inconnue'


def _normalize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valide les paramètres reçus et complète les manquants.

    Les clés inconnues sont refusées plutôt qu'ignorées : une faute de frappe
    côté client se traduirait sinon par un scénario silencieusement différent de
    celui demandé.

    :param params: Paramètres bruts
    :return: Paramètres complets et bornés
    :raises ScenarioParamsError: clé inconnue, type invalide ou valeur hors bornes
    """
    unknown = set(params) - set(SCENARIO_DEFAULTS)
    if unknown:
        raise ScenarioParamsError(
            f"Paramètres inconnus : {sorted(unknown)}. "
            f"Attendus : {sorted(SCENARIO_DEFAULTS)}"
        )

    resolved = dict(SCENARIO_DEFAULTS)
    resolved.update(params)

    for key in ('time_windows_binding', 'hub_transfers'):
        if not isinstance(resolved[key], bool):
            raise ScenarioParamsError(f"{key} doit être un booléen")

    if resolved['seed'] is not None:
        try:
            resolved['seed'] = int(resolved['seed'])
        except (TypeError, ValueError):
            raise ScenarioParamsError("seed doit être un entier ou None") from None

    for key, (low, high) in SCENARIO_LIMITS.items():
        value = resolved[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ScenarioParamsError(f"{key} doit être un nombre, reçu {value!r}")
        if not low <= value <= high:
            raise ScenarioParamsError(f"{key} doit être compris entre {low} et {high}, reçu {value}")
        resolved[key] = int(value)

    if resolved['hub_transfers'] and resolved['hubs'] == 0:
        raise ScenarioParamsError("hub_transfers exige au moins un hub")

    return resolved


def solve_scenario(
    params: Dict[str, Any],
    *,
    workdir: Path,
    fetch_roads: bool = True,
) -> Dict[str, Any]:
    """
    Génère un scénario, le résout **une fois**, et retourne la tournée mise en forme.

    Paramètres acceptés dans `params`, avec leurs valeurs par défaut (celles du
    scénario de référence de la démonstration) :

    ==========================  =========  ===================================
    Clé                         Défaut     Effet
    ==========================  =========  ===================================
    `customers`                 45         Nombre de clients à desservir
    `vehicles`                  3          Nombre de livreurs
    `hubs`                      2          Nombre de points de rechargement
    `capacity`                  10         Capacité d'un véhicule, en colis
    `time_windows_binding`      False      Fenêtres horaires réellement serrées
    `budget_seconds`            30         Budget de recherche, en secondes
    `seed`                      42         Graine du tirage ; None pour varier
    `hub_transfers`             False      Active le transfert de colis en hub
    ==========================  =========  ===================================

    Chaque valeur est bornée par `SCENARIO_LIMITS` avant d'atteindre le solveur.

    **Une seule résolution.** `optimizer.main` en enchaîne trois : une pour la
    distance de référence (`preprocess`), puis une sans hubs et une avec, dont il
    garde la meilleure. Ici on appelle `solve_vrp` directement, ce qui divise le
    temps de réponse par trois. Le prix de ce choix :

    * la distance de référence n'est pas calculée. Elle n'apparaît dans aucun
      champ du document retourné, sa seule perte est donc théorique ;
    * **la stratégie de hub n'est pas arbitrée** : le document décrit la
      configuration demandée, et non la meilleure des deux. Un appelant qui veut
      la comparaison doit lancer deux scénarios, `hub_transfers` à faux puis à
      vrai, et comparer `stats.cumulativeDriveTime`.

    **Sans transfert (`hub_transfers=False`, le défaut)**, la mécanique d'échange
    entre véhicules est désactivée : ni nœuds de dépôt et de retrait, ni
    véhicules fictifs. Les positions des hubs restent dans le jeu de données, et
    comme aucune disjonction n'est posée sur elles, elles deviennent des
    passages **obligatoires** : les tournées les traversent alors que
    `stats.hubsActivated` vaut 0. C'est exactement l'état de données qui a
    produit la démonstration figée, d'où ce défaut.

    **Cette fonction n'est pas sûre en concurrence dans un même processus.** Elle
    écrit dans `Config`, dont les attributs sont des attributs de **classe**,
    donc partagés par tout le processus ; et `create_toy_data` initialise le
    générateur aléatoire **global** de NumPy. Deux appels simultanés se
    corrompraient mutuellement. Les valeurs de `Config` sont restaurées en
    sortie, y compris en cas d'erreur, mais cela ne protège que du séquentiel.
    Un appelant qui sert plusieurs requêtes doit **sérialiser** les appels (un
    verrou) ou les isoler dans des **sous-processus**.

    :param params: Paramètres du scénario (voir le tableau ci-dessus)
    :param workdir: Répertoire de travail où sont écrits les six fichiers du jeu
        de données, puis relus. Fourni par l'appelant, et non déduit du
        répertoire courant : un serveur n'a aucune raison d'écrire à côté du code.
        Il est créé s'il n'existe pas, et n'est pas nettoyé.
    :param fetch_roads: Interroge OSRM pour tracer les tournées sur le réseau
        routier. Une requête HTTP par véhicule vers un serveur public, avec cache
        disque. À faux, les segments sont des droites : le document reste valide,
        `legs[].road` passe à faux, et `stats.roadKm` mesure alors des distances
        à vol d'oiseau, sensiblement plus courtes.
    :return: Document de tournée, tel que décrit dans `optimizer.tour_format`
    :raises ScenarioParamsError: paramètres invalides
    :raises NoSolutionError: aucune solution trouvée dans le budget
    """
    settings = _normalize_params(params)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    if settings['time_windows_binding']:
        tw_end_min, tw_end_max = BINDING_TW_END_MIN, BINDING_TW_END_MAX
    else:
        tw_end_min, tw_end_max = OPEN_TW_END, OPEN_TW_END

    saved = {key: getattr(Config, key) for key in (
        'NUM_CUSTOMERS', 'NUM_VEHICLES', 'NUM_HUBS',
        'VEHICLE_CAPACITY_MIN', 'VEHICLE_CAPACITY_MAX',
        'TW_END_MIN', 'TW_END_MAX', 'RANDOM_SEED',
    )}

    try:
        Config.update(
            NUM_CUSTOMERS=settings['customers'],
            NUM_VEHICLES=settings['vehicles'],
            NUM_HUBS=settings['hubs'],
            VEHICLE_CAPACITY_MIN=float(settings['capacity']),
            VEHICLE_CAPACITY_MAX=float(settings['capacity']),
            TW_END_MIN=tw_end_min,
            TW_END_MAX=tw_end_max,
            RANDOM_SEED=settings['seed'],
        )

        create_toy_data(str(workdir), verbose=False)
        data = load_data(str(workdir))

        if not settings['hub_transfers']:
            # Les hubs restent des positions du jeu de données, mais le solveur
            # n'en fait plus des points de transfert : aucun nœud de dépôt ni de
            # retrait n'est créé, et aucun véhicule fictif n'est ajouté.
            data['num_hubs'] = 0
            data['hubs'] = []

        # Bornes imposées au solveur, transportées par `data` : elles ne touchent
        # pas la configuration globale du processus.
        data['time_limit'] = int(settings['budget_seconds'])
        data['lns_time_limit_ms'] = LNS_TIME_LIMIT_MS
        data['num_search_workers'] = 1

        started = time.monotonic()
        manager, routing, solution = solve_vrp(data)
        elapsed = time.monotonic() - started

        if solution is None:
            raise NoSolutionError(
                f"Aucune solution trouvée en {settings['budget_seconds']} s "
                f"pour {settings['customers']} clients et {settings['vehicles']} véhicules"
            )

        results = get_results(data, manager, routing, solution, verbose=False)
        results['per_livreur']['slacks'] = compute_slacks(data, manager, routing, solution)
        results['per_livreur']['cumulative_loads'] = compute_cumulative_loads(data, results)

        num_real = data['num_real_vehicles']
        road_legs = {}
        if fetch_roads:
            road_legs = build_road_legs(
                data['locations'],
                results['per_livreur']['routes'][:num_real],
            )

        source = {
            'results': results,
            'locations': data['locations'],
            'time_windows': data['time_windows'],
            'demands': data['demands'],
            # Capacité nulle pour les véhicules fictifs : c'est la convention de
            # la charge utile historique, conservée pour qu'un même document soit
            # lisible par les deux producteurs.
            'vehicle_capacities': list(data['vehicle_capacities']) + [0] * (data['num_vehicles'] - num_real),
            'num_vehicles': data['num_vehicles'],
            'num_real_vehicles': num_real,
            'depot': data['depot'],
            'num_customers': data['num_customers'],
            'num_hubs': data['num_hubs'],
            'hub_deposits': data.get('hub_deposits', []),
            'hub_pickups': data.get('hub_pickups', []),
            'unload_depots': data.get('unload_depots', []),
            'time_per_demand_unit': data['time_per_demand_unit'],
            'road_legs': road_legs,
        }
        source = convert_to_json_serializable(source)

        # Texte de provenance en anglais : il part tel quel dans la charge utile
        # affichée par le site, dont l'interface est anglophone.
        meta = {
            'source': 'https://github.com/Skeeder1/livraison',
            'solver': f'Google OR-Tools {_ortools_version()}, RoutingModel (CVRPTW)',
            'generatedFrom': 'optimizer.scenario.solve_scenario',
            'seed': settings['seed'],
            'note': (
                'Solved on demand: one OR-Tools run under a fixed time budget. '
                'The hub strategy is not arbitrated and no baseline is computed.'
            ),
            'budgetSeconds': settings['budget_seconds'],
            'solveSeconds': round(elapsed, 2),
        }

        return build_tour(source, meta)
    finally:
        Config.update(**saved)
