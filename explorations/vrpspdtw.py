# -*- coding: utf-8 -*-
"""
Enlèvement et livraison APPARIÉS, avec fenêtres horaires (PDPTW).

Jalon du projet, antérieur au solveur livré (`optimizer/`). C'est l'étape qui a
rendu exprimable l'idée centrale : un colis pris quelque part et remis ailleurs.

Le nom du fichier dit VRPSPDTW, avec un S pour « simultané ». Le code n'en fait
rien : chaque nœud est un enlèvement OU une livraison, jamais les deux, et les
paires relient un client à un autre. C'est un PDPTW. Le fichier garde son nom
d'origine, la correction est ici.

Trois contraintes suffisent à poser un enlèvement-livraison, et elles y sont :

    routing.AddPickupAndDelivery(pickup, delivery)          apparie les deux nœuds
    VehicleVar(pickup) == VehicleVar(delivery)              même véhicule
    CumulVar(pickup) <= CumulVar(delivery)                  l'un avant l'autre

S'y ajoutent une dimension Capacity et des fenêtres horaires par nœud.

Deux défauts l'empêchaient de calculer quoi que ce soit, et ont été corrigés :

  * `create_time_callback` lisait `data['manager']`, jamais affecté ;
  * il renvoyait un flottant, là où OR-Tools attend un entier 64 bits.

Dans les deux cas l'exception Python remonte dans la recherche C++ sans être
propagée : elle reste attachée au fil d'exécution, et TOUS les rappels suivants
renvoient zéro. Le solveur trouvait alors des tournées valides sur un objectif
nul et affichait « Distance: 0m », sans que rien ne signale la panne. C'est le
même symptôme que la troncature `int()` du solveur livré — un coût d'arc
silencieusement nul — par un tout autre mécanisme.

Sur le lien avec le solveur livré, une précision que l'historique impose : le
hub y reprend la paire de nœuds et la précédence, mais exige deux véhicules
DIFFÉRENTS là où l'on exige ici le même. Cette inversion ne vient pas de ce
fichier : `cvrptw_reload_V2.py` la portait déjà dans le commit initial. Les deux
pistes ont été explorées en parallèle, pas l'une dérivée de l'autre.

Lancer : python explorations/vrpspdtw.py
"""
from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2

def create_data_model():
    """Modèle de données avec pickup/delivery pairs"""
    data = {}
    
    # Format: [pickup_node, delivery_node, demand_pickup, demand_delivery]
    data['pickup_delivery_pairs'] = [
        (1, 2, 3, 2),  # Client 1: pickup à node 1, delivery à node 2
        (3, 4, 5, 1),  # Client 2
        (5, 6, 2, 4)   # Client 3
    ]
    
    # Time windows pour chaque node (0 = depot)
    data['time_windows'] = {
        0: (0, 300),    # Depot
        1: (30, 100),   # Pickup Client 1
        2: (150, 200),  # Delivery Client 1
        3: (60, 120),   # Pickup Client 2
        4: (180, 240),  # Delivery Client 2
        5: (90, 150),   # Pickup Client 3
        6: (210, 270)   # Delivery Client 3
    }
    
    # Coordonnées des nodes (dépot + pickup/delivery nodes)
    data['locations'] = [
        (40, 40),  # 0: Depot
        (22, 22), (36, 26),  # 1-2: Client 1
        (21, 45), (45, 35),  # 3-4: Client 2
        (50, 50), (25, 35)   # 5-6: Client 3
    ]
    
    data['vehicle_capacity'] = 15
    data['num_vehicles'] = 2
    data['depot'] = 0
    data['service_time'] = 10  # Temps de service par node
    data['vehicle_speed'] = 1.0  # unités par minute
    
    return data

def manhattan_distance(pos1, pos2):
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

def create_distance_callback(data, manager):
    """Crée une matrice de distances et retourne un callback utilisant 'manager'."""
    num_nodes = len(data['locations'])
    distance_matrix = [[0]*num_nodes for _ in range(num_nodes)]

    # Pré-calcul des distances
    for i in range(num_nodes):
        for j in range(num_nodes):
            distance_matrix[i][j] = manhattan_distance(
                data['locations'][i],
                data['locations'][j]
            )

    def distance_callback(from_index, to_index):
        # On utilise 'manager' pour convertir from_index / to_index
        real_from = manager.IndexToNode(from_index)
        real_to   = manager.IndexToNode(to_index)
        return distance_matrix[real_from][real_to]

    return distance_callback

def create_time_callback(data):
    def time_callback(from_index, to_index):
        from_node = data['manager'].IndexToNode(from_index)
        to_node = data['manager'].IndexToNode(to_index)
        
        travel_time = manhattan_distance(
            data['locations'][from_node],
            data['locations'][to_node]
        ) / data['vehicle_speed']
        
        # Ajouter le temps de service du node de départ
        service_time = data['service_time'] if from_node != data['depot'] else 0
        # OR-Tools attend un entier 64 bits. Renvoyer un flottant lève une
        # TypeError que la couche SWIG ne propage pas : l'exception reste
        # attachée au thread, et TOUS les rappels suivants renvoient zéro. Le
        # solveur trouvait alors des tournées valides sur un objectif nul,
        # affichait « Distance: 0m », et rien ne signalait la panne.
        return int(travel_time + service_time)
    return time_callback

def add_capacity_constraints(routing, data, manager):
    def demand_callback(from_index):
        node = manager.IndexToNode(from_index)
        for pair in data['pickup_delivery_pairs']:
            if node == pair[0]:  # Pickup node
                return pair[2]
            if node == pair[1]:  # Delivery node
                return -pair[3]
        return 0
    
    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimension(
        demand_callback_index,
        0,  # null slack
        data['vehicle_capacity'],
        True,  # start cumul to zero
        'Capacity'
    )



def print_solution(data, routing, manager, solution):
    time_dimension = routing.GetDimensionOrDie('Time')
    capacity_dimension = routing.GetDimensionOrDie('Capacity')
    
    for vehicle_id in range(data['num_vehicles']):
        index = routing.Start(vehicle_id)
        plan_output = f'Route pour véhicule {vehicle_id}:\n'
        route_distance = 0
        route_load = 0
        
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            time_var = time_dimension.CumulVar(index)
            load_var = capacity_dimension.CumulVar(index)
            
            plan_output += (
                f'Node {node} '
                f'Time({solution.Min(time_var)},{solution.Max(time_var)}) '
                f'Load({solution.Value(load_var)}) -> '
            )
            
            previous_index = index
            index = solution.Value(routing.NextVar(index))
            route_distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
        node = manager.IndexToNode(index)
        time_var = time_dimension.CumulVar(index)
        load_var = capacity_dimension.CumulVar(index)
        plan_output += (
            f'Node {node} '
            f'Time({solution.Min(time_var)},{solution.Max(time_var)}) '
            f'Load({solution.Value(load_var)})\n'
        )
        plan_output += f'Distance: {route_distance}m\n'
        print(plan_output)

def main():
    data = create_data_model()
    manager = pywrapcp.RoutingIndexManager(
        len(data['locations']),
        data['num_vehicles'],
        data['depot']
    )
    
    routing = pywrapcp.RoutingModel(manager)

    # `create_time_callback` lit `data['manager']`, qui n'était jamais posé :
    # l'appel levait un KeyError à l'intérieur de la recherche C++, d'où le
    # zéro généralisé décrit dans l'en-tête.
    data['manager'] = manager

    # Injection du manager dans la création du callback
    dist_cb = create_distance_callback(data, manager)
    transit_callback_index = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Add Capacity constraints
    add_capacity_constraints(routing, data, manager)

    # Add Time Window constraints
    time_callback = create_time_callback(data)
    time_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.AddDimension(
        time_callback_index,
        300,  # slack max
        500,  # horizon temporel
        False,  # start cumul to zero
        'Time'
    )
    time_dimension = routing.GetDimensionOrDie('Time')
    
    # Add time windows for all nodes
    for node, window in data['time_windows'].items():
        index = manager.NodeToIndex(node)
        time_dimension.CumulVar(index).SetRange(window[0], window[1])

    # Add Pickup-Delivery constraints
    for pair in data['pickup_delivery_pairs']:
        pickup_index = manager.NodeToIndex(pair[0])
        delivery_index = manager.NodeToIndex(pair[1])
        
        routing.AddPickupAndDelivery(pickup_index, delivery_index)
        routing.solver().Add(
            routing.VehicleVar(pickup_index) == routing.VehicleVar(delivery_index)
        )
        routing.solver().Add(
            time_dimension.CumulVar(pickup_index) <= time_dimension.CumulVar(delivery_index)
        )

    # Paramètres de recherche
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 30

    # Résolution
    solution = routing.SolveWithParameters(search_parameters)

    # Affichage solution
    if solution:
        print_solution(data, routing, manager, solution)
    else:
        print("Aucune solution trouvée!")



if __name__ == '__main__':
    main()