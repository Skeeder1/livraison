"""
Lecture d'une solution OR-Tools : attentes, charges, sérialisation.

Ces trois fonctions vivaient dans `print_solution.py`, derrière des imports de
folium, matplotlib et seaborn. Elles ne font pourtant que relire une solution :
les isoler ici permet à un appelant sans interface graphique, le serveur de
`optimizer.scenario`, de les utiliser sans tirer la pile de rendu, et garantit
qu'il n'existe **qu'une seule** implémentation de chaque calcul.

`print_solution.create_visualization` les importe désormais au lieu de les
redéfinir.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from optimizer.solver import create_base_node_mapping, create_evaluator_functions


def convert_to_json_serializable(obj: Any) -> Any:
    """
    Remplace récursivement les scalaires NumPy par leurs équivalents Python.

    Les demandes et les distances proviennent de pandas et de NumPy : elles
    arrivent en `np.int64` / `np.float64`, que `json.dumps` refuse avec
    « Object of type int64 is not JSON serializable ».

    :param obj: Structure quelconque (dict, list, tuple, scalaire)
    :return: La même structure, sérialisable en JSON
    """
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {k: convert_to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_to_json_serializable(i) for i in obj]
    if isinstance(obj, tuple):
        return tuple(convert_to_json_serializable(i) for i in obj)
    return obj


def compute_slacks(data: dict[str, Any], manager, routing, solution) -> list[list[int]]:
    """
    Reconstitue le temps d'attente à chaque étape de chaque tournée.

    Le solveur ne restitue pas l'attente : la dimension « Time » ne donne que
    l'heure d'arrivée à chaque nœud. L'attente se déduit par différence :

        attente = arrivée(suivant) - arrivée(courant) - (service + trajet)

    Le terme `(service + trajet)` est obtenu auprès de l'évaluateur temporel du
    solveur lui-même (`create_evaluator_functions`), et non recalculé : une
    seconde formule finirait par diverger de celle qui a réellement contraint la
    résolution, et les attentes affichées ne correspondraient plus à la solution.

    Les valeurs négatives sont ramenées à 0 : elles n'apparaissent que sur les
    arcs des véhicules fictifs, dont la dimension temporelle est libre.

    :param data: Données **étendues** par `solve_vrp` (nœuds de rechargement,
                 dépôts/retraits de hub et nœuds fictifs déjà ajoutés)
    :param manager: Gestionnaire d'indices OR-Tools
    :param routing: Modèle de routage OR-Tools
    :param solution: Solution retournée par le solveur
    :return: Une liste d'attentes par véhicule, dans l'ordre des étapes.
             Elle compte un élément de moins que la route : la dernière étape
             n'a pas d'arc sortant.
    """
    time_dimension = routing.GetDimensionOrDie('Time')

    hub_start = 1 + data['num_customers']
    hub_indices = range(hub_start, hub_start + data['num_hubs'])
    base_node = create_base_node_mapping(data, hub_indices)
    reload_group = [data['depot']] + data['unload_depots']
    _, _, create_time_evaluator = create_evaluator_functions(data, base_node, reload_group)
    transit = create_time_evaluator(data)

    slacks = []
    for vehicle in range(data['num_vehicles']):
        route_slacks = []
        index = routing.Start(vehicle)
        while not routing.IsEnd(index):
            next_index = solution.Value(routing.NextVar(index))
            waited = (
                solution.Value(time_dimension.CumulVar(next_index))
                - solution.Value(time_dimension.CumulVar(index))
                - transit(manager, index, next_index)
            )
            route_slacks.append(max(0, waited))
            index = next_index
        slacks.append(route_slacks)

    return slacks


def compute_cumulative_loads(data: dict[str, Any], results: dict[str, Any]) -> list[list[int]]:
    """
    Charge transportée à chaque étape, véhicules fictifs compris.

    Les véhicules réels reprennent telles quelles les charges calculées par le
    post-traitement. Les véhicules fictifs, ceux qui matérialisent un transfert
    en hub, ne transportent rien : leur ligne est explicitement mise à zéro,
    pour que l'affichage ne présente pas une capacité qui n'existe pas.

    :param data: Données étendues par `solve_vrp`
    :param results: Sortie de `get_results`
    :return: Une liste de charges par véhicule, alignée sur les routes
    """
    per_livreur = results['per_livreur']
    num_real_vehicles = len(data['vehicle_capacities'])

    cumulative_loads = []
    for vehicle in range(data['num_vehicles']):
        if vehicle < num_real_vehicles:
            cumulative_loads.append(per_livreur['current_loads'][vehicle])
        else:
            cumulative_loads.append([0] * len(per_livreur['routes'][vehicle]))

    return cumulative_loads
