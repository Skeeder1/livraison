# -*- coding: utf-8 -*-
"""
Exemple de VRPSPDTW (Vehicle Routing Problem with Pickup & Delivery et Time Windows)
utilisant OR-Tools en Python.

Points importants :
  - On définit chaque requête comme (pickup_node, delivery_node).
  - On ajoute les contraintes de capacité, les fenêtres de temps,
    et on impose que pickup précède la delivery avec AddPickupAndDelivery().
"""

from __future__ import print_function
from functools import partial
from six.moves import xrange

# OR-Tools
from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2

def create_data_model():
    """
    Crée la structure de données nécessaire au VRP :
      - depot : index du dépôt (où les véhicules commencent et terminent).
      - locations : liste des coordonnées (x, y) de chaque nœud (y compris le dépôt).
      - demands : demande (positive ou négative) associée à chaque nœud.
      - time_windows : fenêtres de temps [ouverture, fermeture] par nœud.
      - pickups_deliveries : liste de paires (i_pickup, i_delivery).
      - vehicle_capacity : capacité maximum d'un véhicule.
      - num_vehicles : nombre de véhicules.
      - vehicle_speed : vitesse pour convertir distance en temps.
    """
    data = {}

    # ---------------------------
    # 1) Positions (x,y) + Dépôt
    # ---------------------------
    #
    # Index 0 : dépôt
    # Index 1..N : nœuds "pickup" ou "delivery"
    #
    # Exemple : 1 requête = (pickup=1, delivery=2), 2e requête = (pickup=3, delivery=4), etc.
    #
    data['locations'] = [
        (4, 4),  # 0 - Depot
        (2, 0),  # 1 - Pickup 1
        (2, 6),  # 2 - Delivery 1
        (8, 0),  # 3 - Pickup 2
        (8, 5),  # 4 - Delivery 2
        (1, 1),  # 5 - Pickup 3
        (1, 6),  # 6 - Delivery 3
        (5, 2),  # 7 - Pickup 4
        (5, 7),  # 8 - Delivery 4
    ]
    data['num_locations'] = len(data['locations'])

    # Index du dépôt
    data['depot'] = 0

    # -----------------------
    # 2) Paires Pickup/Delivery
    # -----------------------
    # On indique quelles paires vont ensemble.
    # Cela doit correspondre aux indices plus haut (sans le dépôt).
    # Exemple : la requête 1 est (pickup=1, delivery=2).
    #           la requête 2 est (pickup=3, delivery=4), etc.
    #
    data['pickups_deliveries'] = [
        (1, 2),
        (3, 4),
        (5, 6),
        (7, 8),
    ]

    # -----------------------
    # 3) Fenêtres de temps
    # -----------------------
    # On définit pour chaque nœud (y compris le dépôt) un intervalle [start, end].
    # Par exemple : le dépôt est ouvert de 0 à 500, etc.
    # Les pickups et deliveries ont leurs propres contraintes.
    #
    data['time_windows'] = [
        (0, 500),   # 0 - Depot
        (10, 50),   # 1 - Pickup 1
        (30, 80),   # 2 - Delivery 1
        (10, 50),   # 3 - Pickup 2
        (30, 80),   # 4 - Delivery 2
        (10, 50),   # 5 - Pickup 3
        (30, 80),   # 6 - Delivery 3
        (10, 50),   # 7 - Pickup 4
        (30, 80),   # 8 - Delivery 4
    ]

    # --------------------------------
    # 4) Demandes (capacités à gérer)
    # --------------------------------
    # Hypothèse : On récupère +3 unités sur un pickup, on livre -3 unités sur la delivery.
    # On encode cela directement comme un "demand" (positif pour pickup, négatif pour delivery).
    #
    demands = [0] * data['num_locations']  # par défaut
    # On va dire que chacune des 4 requêtes représente 2 unités :
    # Pickup = +2, Delivery = -2
    requests_capacity = 2

    # Requête 1: (1=pickup, 2=delivery)
    demands[1] = +requests_capacity
    demands[2] = -requests_capacity

    # Requête 2: (3=pickup, 4=delivery)
    demands[3] = +requests_capacity
    demands[4] = -requests_capacity

    # Requête 3: (5=pickup, 6=delivery)
    demands[5] = +requests_capacity
    demands[6] = -requests_capacity

    # Requête 4: (7=pickup, 8=delivery)
    demands[7] = +requests_capacity
    demands[8] = -requests_capacity

    data['demands'] = demands

    # -----------------------
    # 5) Autres paramètres
    # -----------------------
    data['vehicle_capacity'] = 5  # ex. chaque véhicule peut transporter 6 unités max.
    data['num_vehicles'] = 2      # par exemple 2 véhicules
    data['vehicle_speed'] = 1     # pour simplifier la conversion distance => temps

    return data


# =========================================
# 1) Distances (Manhattan ou Euclidien, ...)
# =========================================
def manhattan_distance(position_1, position_2):
    """Calcule la distance de Manhattan entre deux points (x1,y1) et (x2,y2)."""
    return abs(position_1[0] - position_2[0]) + abs(position_1[1] - position_2[1])


def create_distance_evaluator(data):
    """
    Crée un callback qui retourne la distance entre deux nœuds.
    Pré-calcul pour accélérer.
    """
    _distances = {}
    for from_node in range(data['num_locations']):
        _distances[from_node] = {}
        for to_node in range(data['num_locations']):
            if from_node == to_node:
                _distances[from_node][to_node] = 0
            else:
                _distances[from_node][to_node] = manhattan_distance(
                    data['locations'][from_node],
                    data['locations'][to_node]
                )

    def distance_evaluator(manager, from_index, to_index):
        real_from = manager.IndexToNode(from_index)
        real_to = manager.IndexToNode(to_index)
        return _distances[real_from][real_to]

    return distance_evaluator


# =============================
# 2) Demande (Capacity) 
# =============================
def create_demand_evaluator(data):
    """
    Crée un callback pour la demande (positive ou négative) de chaque nœud.
    """
    demands = data['demands']

    def demand_evaluator(manager, index):
        node = manager.IndexToNode(index)
        return demands[node]

    return demand_evaluator


def add_capacity_constraints(routing, data, demand_callback_index):
    """
    Ajoute la dimension 'Capacity' pour respecter la limite de chargement max.
    """
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        [data['vehicle_capacity']] * data['num_vehicles'],  # capacity de chaque véhicule
        True,  # start cumul at 0
        'Capacity'
    )


# ===============================
# 3) Temps & Fenêtres de temps
# ===============================
def create_time_evaluator(data):
    """
    Crée un callback temps : temps(de from_node à to_node) = distance / speed
    + éventuel temps de service, etc. (ici on ne met que la distance/speed).
    """
    # Pré-calcul
    _travel_times = {}
    for from_node in range(data['num_locations']):
        _travel_times[from_node] = {}
        for to_node in range(data['num_locations']):
            dist = manhattan_distance(
                data['locations'][from_node],
                data['locations'][to_node]
            )
            # Ici : temps = dist / speed
            _travel_times[from_node][to_node] = int(dist / data['vehicle_speed'])

    def time_evaluator(manager, from_index, to_index):
        real_from = manager.IndexToNode(from_index)
        real_to = manager.IndexToNode(to_index)
        return _travel_times[real_from][real_to]

    return time_evaluator


def add_time_window_constraints(routing, manager, data, time_callback_index):
    """
    Ajoute la dimension 'Time' et applique les fenêtres de temps à chaque nœud.
    """
    routing.AddDimension(
        time_callback_index,
        500,  # autorise un "waiting time" max (large)
        500,  # horizon max pour la tournée
        False,  # la valeur cumul ne démarre pas forcément à 0
        'Time'
    )
    time_dimension = routing.GetDimensionOrDie('Time')

    # Contraintes de fenêtres de temps pour chaque nœud
    for location_idx, time_window in enumerate(data['time_windows']):
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1])


# ============================================
# 4) Ajout contrainte Pickup & Delivery
# ============================================
def add_pickup_and_delivery(routing, manager, data):
    # Récupération de la dimension Time
    time_dimension = routing.GetDimensionOrDie('Time')

    for (pickup_idx, delivery_idx) in data['pickups_deliveries']:
        pickup_index = manager.NodeToIndex(pickup_idx)
        delivery_index = manager.NodeToIndex(delivery_idx)

        routing.AddPickupAndDelivery(pickup_index, delivery_index)

        # Même véhicule
        routing.solver().Add(
            routing.VehicleVar(pickup_index) == routing.VehicleVar(delivery_index)
        )

        # pickup avant delivery
        routing.solver().Add(
            time_dimension.CumulVar(pickup_index) <= time_dimension.CumulVar(delivery_index)
        )


# ===============================
# 5) Impression de la solution
# ===============================
def print_solution(data, manager, routing, solution):
    """Affiche la solution sur la console."""
    total_distance = 0
    time_dimension = routing.GetDimensionOrDie('Time')
    capacity_dimension = routing.GetDimensionOrDie('Capacity')

    for vehicle_id in range(data['num_vehicles']):
        index = routing.Start(vehicle_id)
        route_load = 0
        route_distance = 0

        plan_output = 'Route du véhicule {}:\n'.format(vehicle_id)
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            load_var = capacity_dimension.CumulVar(index)
            time_var = time_dimension.CumulVar(index)

            # Infos sur le cumul
            route_load = solution.Value(load_var)
            tmin = solution.Min(time_var)
            tmax = solution.Max(time_var)

            plan_output += '  -> Node {0} Load({1}) Time({2},{3})\n'.format(
                node_index, route_load, tmin, tmax
            )

            # Distance vers le prochain
            previous_index = index
            index = solution.Value(routing.NextVar(index))
            route_distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)

        # Arrivée au dépôt final
        node_index = manager.IndexToNode(index)
        load_var = capacity_dimension.CumulVar(index)
        time_var = time_dimension.CumulVar(index)
        route_load = solution.Value(load_var)
        tmin = solution.Min(time_var)
        tmax = solution.Max(time_var)

        plan_output += '  -> Node {0} Load({1}) Time({2},{3})\n'.format(
            node_index, route_load, tmin, tmax
        )

        plan_output += 'Distance de la route: {} \n'.format(route_distance)
        plan_output += 'Charge finale sur la route: {} \n'.format(route_load)
        plan_output += '----------------------------------------------\n'
        print(plan_output)

        total_distance += route_distance

    print('Distance totale de toutes les routes = {}'.format(total_distance))


# ===============================
# 6) Main
# ===============================
def main():
    data = create_data_model()

    # 1) Créer le manager et le modèle de routage
    manager = pywrapcp.RoutingIndexManager(
        data['num_locations'],
        data['num_vehicles'],
        data['depot']  # même index de départ et d'arrivée
    )
    routing = pywrapcp.RoutingModel(manager)

    # 2) Distance (coût principal = distance)
    distance_evaluator = partial(create_distance_evaluator(data), manager)
    distance_callback_index = routing.RegisterTransitCallback(distance_evaluator)
    routing.SetArcCostEvaluatorOfAllVehicles(distance_callback_index)

    # 3) Contrainte de capacité
    demand_evaluator = partial(create_demand_evaluator(data), manager)
    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_evaluator)
    add_capacity_constraints(routing, data, demand_callback_index)

    # 4) Dimension de temps + fenêtres
    time_evaluator = partial(create_time_evaluator(data), manager)
    time_callback_index = routing.RegisterTransitCallback(time_evaluator)
    add_time_window_constraints(routing, manager, data, time_callback_index)

    # 5) Contrainte Pickup & Delivery
    add_pickup_and_delivery(routing, manager, data)

    # 6) Paramètres de recherche
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    # Optionnel: définir une stratégie d'optimisation plus poussée
    # search_parameters.local_search_metaheuristic = (
    #     routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    # )
    # search_parameters.time_limit.seconds = 30

    # 7) Résolution
    solution = routing.SolveWithParameters(search_parameters)

    # 8) Affichage des résultats
    if solution:
        print_solution(data, manager, routing, solution)
    else:
        print("Aucune solution trouvée.")


if __name__ == '__main__':
    main()
