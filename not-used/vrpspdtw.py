# -*- coding: utf-8 -*-
"""
Exemple complet et cohérent pour un VRP simple
avec OR-Tools, partant de votre base de code.
Ce code devrait se lancer sans erreur de "Wrong number or type of arguments".
"""

from ortools.constraint_solver.pywrapcp import (
    RoutingIndexManager,
    RoutingModel,
    DefaultRoutingSearchParameters
)
from ortools.constraint_solver.routing_enums_pb2 import FirstSolutionStrategy


class CreateDistanceCallback:
    """Callback pour calculer la distance entre deux nœuds."""
    def __init__(self, distance_matrix):
        self.matrix = distance_matrix

    def Distance(self, from_node, to_node):
        return self.matrix[from_node][to_node]


def main():
    """Fonction principale : crée un problème simple et le résout avec OR-Tools."""

    # =========================================================================
    # 1) Données d'entrée
    # =========================================================================
    # Exemple simplifié basé sur votre structure
    input_data = {
        "locations": [
            {"time_windows": [[0, 10800]], "service_time": 20},
            {"time_windows": [[0, 10800]], "service_time": 40},
            {"time_windows": [[0, 10800]], "service_time": 900},
            {"time_windows": [[0, 10800]], "service_time": 900},
            {"time_windows": [[21000, 46800]], "service_time": 900},
            {"time_windows": [[18000, 46800]], "service_time": 900},
        ],
        "distance_matrix": [
            [812,    0,    2229, 672,  3561, 2372],
            [0,    812,    2553, 672,  3561, 2372],
            [0,    0,    2229, 672,  3561, 2372],
            [0,    0,    2553, 672,  3561, 2372],
            [2583, 2583, 0,    2288, 2063, 741 ],
            [812,  812,  2410, 0,    3418, 2229],
            [3585, 3585, 1906, 3290, 0,    1756],
            [2452, 2452, 586,  2157, 1732, 0   ],
        ],
        "start_location_index": [0,1],
        "end_location_index": [1,0]
    }

    # =========================================================================
    # 2) Extraction des données
    # =========================================================================
    locations = input_data["locations"]
    distance_matrix = input_data["distance_matrix"]

    num_locations = len(locations)
    print("Nombre de localisations :", num_locations)

    # Indices de départ et d'arrivée pour le (ou les) véhicule(s)
    start_location = input_data.get("start_location_index", 0)
    end_location = input_data.get("end_location_index", 1)

    num_vehicles = 2  # On gère ici un unique véhicule pour simplifier
    print("Nombre de véhicules :", num_vehicles)
    print("Start location index :", start_location)
    print("End location index   :", end_location)

    # Limite de temps (millisecondes) pour la recherche
    search_time_limit = 20  # 8 secondes
    # NOTE: Si le problème devient plus complexe, augmenter ce temps.

    # =========================================================================
    # 3) Création du RoutingIndexManager
    # =========================================================================
    # On indique : nb de points (num_locations),
    #              nb de véhicules (num_vehicles),
    #              l'indice du départ,
    #              l'indice de l'arrivée.
    manager = RoutingIndexManager(
        num_locations,
        num_vehicles,
        start_location,   # liste de starts
        end_location    # liste de ends  
    )

    # =========================================================================
    # 4) Création du RoutingModel
    # =========================================================================
    routing = RoutingModel(manager)

    # =========================================================================
    # 5) Configuration des paramètres de recherche
    # =========================================================================
    search_parameters = DefaultRoutingSearchParameters()
    search_parameters.time_limit.FromSeconds(search_time_limit)
    # Stratégie de première solution
    search_parameters.first_solution_strategy = FirstSolutionStrategy.PATH_CHEAPEST_ARC

    # =========================================================================
    # 6) Définition du callback de distance
    # =========================================================================
    dist_cb = CreateDistanceCallback(distance_matrix)
    dist_callback_index = routing.RegisterTransitCallback(dist_cb.Distance)

    # 3) Utiliser l'indice retourné pour définir le coût
    routing.SetArcCostEvaluatorOfAllVehicles(dist_callback_index)

    # =========================================================================
    # (Optionnel) 7) Création d'une dimension temps si on veut la gérer
    # =========================================================================
    # Ex : On calcule un "temps" = distance / speed + service_time
    # ICI, on laisse commenté pour un code minimal
    """
    speed = 1.0
    # On peut simuler un service_time identique ou dépendant du 'locations'
    service_times = [loc["service_time"] for loc in locations]

    # On crée un callback simple
    def total_time(from_index, to_index):
        # node
        from_node = manager.IndexToNode(from_index)
        to_node   = manager.IndexToNode(to_index)
        travel_time = distance_matrix[from_node][to_node] / speed
        service_time = service_times[from_node]
        return travel_time + service_time

    total_time_callback_index = routing.RegisterTransitCallback(total_time)
    dimension_name = "Time"
    # On autorise par ex. 24h = 86400 en secondes
    horizon = 86400
    routing.AddDimension(
        total_time_callback_index,  # callback
        horizon,  # slack max
        horizon,  # max cumul
        True,     # start cumul at zero
        dimension_name
    )
    # time_dimension = routing.GetDimensionOrDie(dimension_name)
    """

    # =========================================================================
    # 8) Résolution du problème
    # =========================================================================
    assignment = routing.SolveWithParameters(search_parameters)

    if not assignment:
        print("Aucune solution trouvée.")
        return

    # =========================================================================
    # 9) Affichage de la solution
    # =========================================================================
    total_cost = assignment.ObjectiveValue()
    print(f"Distance totale de la solution : {total_cost}")

    # Comme on a 1 seul véhicule, on affiche sa tournée
    vehicle_id = 0
    index = routing.Start(vehicle_id)
    route_nodes = []
    while not routing.IsEnd(index):
        node_index = manager.IndexToNode(index)
        route_nodes.append(node_index)
        index = assignment.Value(routing.NextVar(index))
    # Dernier nœud
    route_nodes.append(manager.IndexToNode(index))

    print("Itinéraire du véhicule 0 :", " -> ".join(map(str, route_nodes)))


def run():
    """Méthode d'entrée alternative si besoin."""
    try:
        main()
    except Exception as e:
        print(f"Erreur inattendue : {e}")


if __name__ == '__main__':
    run()
