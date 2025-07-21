#!/usr/bin/env python3
# This Python file uses the following encoding: utf-8
# Copyright 2015 Tin Arm Engineering AB
# Copyright 2018 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# ... (license text omitted for brevity)

from functools import partial
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from print_solution import *

###########################
# Problem Data Definition #
###########################
def create_data_model():
    """Crée le modèle de données.
       - Les clients, le dépôt et les points de hub sont définis.
       - Deux nœuds pour le hub : deposit (demande = -1) et pickup (demande = +1).
       - Un nœud dummy est ajouté pour servir d'horloge globale.
    """
    data = {}
    _capacity = 3
    # Liste des localisations en "block" (les coordonnées en block)
    _locations = [
        (4, 4),  # depot (index 0)
        (4, 4),  # unload depot_first (index 1)
        (4, 4),  # unload depot_second (index 2)
        (4, 4),  # unload depot_third (index 3)
        (4, 4),  # unload depot_fourth (index 4)
        (4, 4),  # unload depot_fifth (index 5)
        (2, 0),  # client (index 6)
        (8, 0),  # client (index 7)
        (0, 1),  # client (index 8)
        (1, 1),  # client (index 9)
        (5, 2),  # client (index 10)
        (7, 2),  # client (index 11)
        (3, 3),  # client (index 12)
        (6, 3),  # client (index 13)
        (5, 5),  # client (index 14)
        (8, 5),  # client (index 15)
        (1, 6),  # client (index 16)
        (2, 6),  # client (index 17)
        (3, 7),  # client (index 18)
        (6, 7),  # client (index 19)
        (0, 8),  # client (index 20)
        (7, 8)   # client (index 21)
    ]
    # Conversion en mètres (en utilisant 114m x 80m par block)
    data['locations'] = [(l[0] * 114, l[1] * 80) for l in _locations]
    data['num_locations'] = len(data['locations'])

    # Demandes : pour le dépôt, les stations de déchargement et les clients.
    # Ici, pour les clients, la demande est 1 ; pour les stations de déchargement, la demande est -_capacity.
    data['demands'] = [
        0,              # depot (index 0)
        -_capacity,     # unload depot_first (index 1)
        -_capacity,     # unload depot_second (index 2)
        -_capacity,     # unload depot_third (index 3)
        -_capacity,     # unload depot_fourth (index 4)
        -_capacity,     # unload depot_fifth (index 5)
        1, 1,           # clients (indices 6,7)
        1, 1,           # clients (indices 8,9)
        1, 1,           # clients (indices 10,11)
        1, 1,           # clients (indices 12,13)
        1, 1,           # clients (indices 14,15)
        1, 1,           # clients (indices 16,17)
        1, 1,           # clients (indices 18,19)
        1, 1            # clients (indices 20,21)
    ]

    data['time_per_demand_unit'] = 5  # 5 minutes par unité
    data['time_windows'] = [
        (0, 0),       # depot (index 0)
        (0, 1000),    # unload depot_first (index 1)
        (0, 1000),    # unload depot_second (index 2)
        (0, 1000),    # unload depot_third (index 3)
        (0, 1000),    # unload depot_fourth (index 4)
        (0, 1000),    # unload depot_fifth (index 5)
        (0, 850), (75, 850),   # clients (indices 6,7)
        (60, 700), (45, 550),   # clients (indices 8,9)
        (0, 800), (50, 600),    # clients (indices 10,11)
        (0, 1000), (10, 200),   # clients (indices 12,13)
        (0, 1000), (75, 850),   # clients (indices 14,15)
        (85, 950), (5, 150),    # clients (indices 16,17)
        (15, 250), (10, 200),   # clients (indices 18,19)
        (45, 550), (30, 400)    # clients (indices 20,21)
    ]

    # Véhicules réels : 3 véhicules
    data['num_vehicles'] = 3
    data['vehicle_capacity'] = _capacity
    data['vehicle_max_distance'] = 10_000
    data['vehicle_max_time'] = 1_500
    data['vehicle_speed'] = 4 * 60 / 3.6  # 5 km/h converti en m/min
    data['depot'] = 0

    # [HUB] Ajout de deux nœuds pour le hub (pour transférer 1 unité)
    hub_block_location = (4, 6)  # position du hub
    hub_capacity = 1
    data['locations'].append((hub_block_location[0] * 114, hub_block_location[1] * 80))  # hub_deposit
    data['locations'].append((hub_block_location[0] * 114, hub_block_location[1] * 80))  # hub_pickup
    data['num_locations'] = len(data['locations'])
    data['demands'].append(-hub_capacity)  # hub_deposit
    data['demands'].append(hub_capacity)   # hub_pickup
    data['time_windows'].append((0, 500))   # fenêtre pour le dépôt
    data['time_windows'].append((0, 500))   # fenêtre pour le pickup
    data['hub_deposit'] = data['num_locations'] - 2
    data['hub_pickup'] = data['num_locations'] - 1

    # === Ajout du nœud dummy pour l'horloge globale ===
    dummy_coordinate = (0, 0)  # position arbitraire (ne sera pas utilisé pour la distance réelle)
    data['locations'].append(dummy_coordinate)
    data['demands'].append(0)
    data['time_windows'].append((0, 10000))  # fenêtre très large couvrant l'horizon total
    data['dummy_global_node'] = data['num_locations']  # index du nœud dummy
    data['num_locations'] = len(data['locations'])

    return data

##############################
# Callback et Dimensions
##############################
def manhattan_distance(position_1, position_2):
    """Calcule la distance de Manhattan entre deux points."""
    return abs(position_1[0] - position_2[0]) + abs(position_1[1] - position_2[1])

def create_distance_evaluator(data):
    """Retourne un callback donnant la distance entre deux nœuds,
       avec une pénalité sur les arcs impliquant les nœuds du hub."""
    _distances = {}
    for from_node in range(data['num_locations']):
        _distances[from_node] = {}
        for to_node in range(data['num_locations']):
            if from_node == to_node:
                _distances[from_node][to_node] = 0
            # Pour éviter des transitions entre nœuds de même type (par exemple entre clients)
            elif from_node in range(6) and to_node in range(6):
                _distances[from_node][to_node] = data['vehicle_max_distance']
            else:
                _distances[from_node][to_node] = manhattan_distance(
                    data['locations'][from_node],
                    data['locations'][to_node])
    def distance_evaluator(manager, from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node   = manager.IndexToNode(to_index)
        base_distance = _distances[from_node][to_node]
        extra_penalty = 0
        hub_nodes = [data['hub_deposit'], data['hub_pickup']]
        if from_node in hub_nodes or to_node in hub_nodes:
            extra_penalty = 500  # ajustez selon votre contexte
        return base_distance + extra_penalty
    return distance_evaluator

def add_distance_dimension(routing, manager, data, distance_evaluator_index):
    """Ajoute la dimension de distance."""
    distance = 'Distance'
    routing.AddDimension(
        distance_evaluator_index,
        0,  # pas de slack
        data['vehicle_max_distance'],
        True,  # Le cumul démarre à zéro
        distance)
    distance_dimension = routing.GetDimensionOrDie(distance)
    distance_dimension.SetGlobalSpanCostCoefficient(100)

def create_demand_evaluator(data):
    """Retourne le callback pour la demande de chaque nœud."""
    _demands = data['demands']
    def demand_evaluator(manager, from_node):
        return _demands[manager.IndexToNode(from_node)]
    return demand_evaluator

def add_capacity_constraints(routing, manager, data, demand_evaluator_index):
    """Ajoute la contrainte de capacité.
       Pour le hub, impose que le flux de 1 unité soit équilibré et qu'un même véhicule ne fasse pas les deux opérations.
    """
    vehicle_capacity = data['vehicle_capacity']
    capacity = 'Capacity'
    routing.AddDimension(
        demand_evaluator_index,
        vehicle_capacity,
        vehicle_capacity,
        True,
        capacity)
    capacity_dimension = routing.GetDimensionOrDie(capacity)
    # Pour les nœuds de recharge (indices 1 à 5)
    for node in [1, 2, 3, 4, 5]:
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], 0)
    # Pour les autres nœuds (clients)
    for node in range(6, len(data['demands'])):
        node_index = manager.NodeToIndex(node)
        capacity_dimension.SlackVar(node_index).SetValue(0)
        if node not in [data.get('hub_deposit'), data.get('hub_pickup')]:
            routing.AddDisjunction([node_index], 100_000)
    # Contrainte Hub : le dépôt et le pickup doivent être cohérents
    if 'hub_deposit' in data and 'hub_pickup' in data:
        deposit_index = manager.NodeToIndex(data['hub_deposit'])
        pickup_index  = manager.NodeToIndex(data['hub_pickup'])
        routing.solver().Add(
            capacity_dimension.CumulVar(deposit_index) + data['demands'][data['hub_deposit']]
            == capacity_dimension.CumulVar(pickup_index) - data['demands'][data['hub_pickup']]
        )
        routing.solver().Add(
            routing.VehicleVar(deposit_index) != routing.VehicleVar(pickup_index)
        )

def create_time_evaluator(data):
    """Retourne le callback pour le temps total entre deux nœuds."""
    def service_time(data, node):
        return abs(data['demands'][node]) * data['time_per_demand_unit']
    def travel_time(data, from_node, to_node):
        if from_node == to_node:
            return 0
        else:
            return manhattan_distance(
                data['locations'][from_node],
                data['locations'][to_node]
            ) / data['vehicle_speed']
    _total_time = {}
    for from_node in range(data['num_locations']):
        _total_time[from_node] = {}
        for to_node in range(data['num_locations']):
            if from_node == to_node:
                _total_time[from_node][to_node] = 0
            else:
                _total_time[from_node][to_node] = int(
                    service_time(data, from_node) +
                    travel_time(data, from_node, to_node))
    def time_evaluator(manager, from_index, to_index):
        return _total_time[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]
    return time_evaluator

def add_time_window_constraints(routing, manager, data, time_evaluator_index):
    """Ajoute la dimension Temps et les contraintes de fenêtres temporelles.
       On ne force pas la réinitialisation du temps (fix_start_cumul_to_zero=False)
       afin de permettre d'avoir une référence globale.
    """
    time = 'Time'
    max_time = data['vehicle_max_time']
    routing.AddDimension(
        time_evaluator_index,
        max_time,
        max_time,
        False,   # Ne force pas la remise à zéro, pour conserver une échelle globale
        time)
    time_dimension = routing.GetDimensionOrDie(time)
    for location_idx, time_window in enumerate(data['time_windows']):
        if location_idx == 0:
            continue  # Pour le dépôt, on laisse tel quel
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1])
        routing.AddToAssignment(time_dimension.SlackVar(index))
        
    # Pour les véhicules réels, on fixe leur départ à 0 (pour avoir une référence commune)
    penalty_slack = 1_000_000_000  # Forte pénalité sur l'attente
    num_real = data['num_vehicles'] - 1  # les indices 0 à num_real-1 sont réels
    for vehicle_id in range(num_real):
        index = routing.Start(vehicle_id)
        time_dimension.CumulVar(index).SetRange(0, 0)
        routing.AddToAssignment(time_dimension.SlackVar(index))
        time_dimension.SetSlackCostCoefficientForVehicle(penalty_slack, vehicle_id)    
    # Pour le véhicule dummy, on autorise une plage large
    dummy_vehicle_id = data['num_vehicles'] - 1
    index = routing.Start(dummy_vehicle_id)
    time_dimension.CumulVar(index).SetRange(0, max_time)
    routing.AddToAssignment(time_dimension.SlackVar(index))
    
    # === CONTRAINTE D'HORLOGE GLOBALE basée sur le dummy ===
    # On impose que le temps du nœud dummy (global clock) se situe entre le dépôt et le pickup du hub.
    dummy_index = manager.NodeToIndex(data['dummy_global_node'])
    dummy_time = time_dimension.CumulVar(dummy_index)
    if 'hub_deposit' in data and 'hub_pickup' in data:
        deposit_index = manager.NodeToIndex(data['hub_deposit'])
        pickup_index = manager.NodeToIndex(data['hub_pickup'])
        routing.solver().Add(time_dimension.CumulVar(deposit_index) <= dummy_time)
        routing.solver().Add(dummy_time <= time_dimension.CumulVar(pickup_index))
    
def restrict_vehicle_assignments(routing, manager, data):
    """Restreint l'affectation des nœuds :
       - Les nœuds clients, hub et autres ne sont affectés qu'aux véhicules réels (indices 0 à num_real-1)
       - Le nœud dummy global est réservé au véhicule dummy (indice num_real)
    """
    num_real = data['num_vehicles'] - 1
    dummy_vehicle = num_real
    for node in range(data['num_locations']):
        if 'dummy_global_node' in data and node == data['dummy_global_node']:
            routing.SetAllowedVehiclesForIndex([dummy_vehicle], manager.NodeToIndex(node))
        else:
            routing.SetAllowedVehiclesForIndex(list(range(num_real)), manager.NodeToIndex(node))

##############################
# Printer (inchangé)
##############################
def print_solution(data, manager, routing, assignment):
    """Affiche la solution sur la console."""
    print(f'Objective: {assignment.ObjectiveValue()}')
    total_distance = 0
    total_load = 0
    total_time = 0
    capacity_dimension = routing.GetDimensionOrDie('Capacity')
    time_dimension = routing.GetDimensionOrDie('Time')
    dropped = []
    for order in range(6, routing.nodes()):
        index = manager.IndexToNode(order)
        if assignment.Value(routing.NextVar(index)) == index:
            dropped.append(order)
    print(f'dropped orders: {dropped}')
    for reload in range(1, 6):
        index = manager.IndexToNode(reload)
        if assignment.Value(routing.NextVar(index)) == index:
            dropped.append(reload)
    print(f'dropped reload stations: {dropped}')
    # Affichage pour les véhicules réels
    num_real = data['num_vehicles'] - 1
    for vehicle_id in range(num_real):
        index = routing.Start(vehicle_id)
        plan_output = f'Route for vehicle {vehicle_id}:\n'
        distance = 0
        while not routing.IsEnd(index):
            load_var = capacity_dimension.CumulVar(index)
            time_var = time_dimension.CumulVar(index)
            plan_output += f' {manager.IndexToNode(index)} ' \
                           f'Load({assignment.Min(load_var)}) ' \
                           f'Time({assignment.Min(time_var)},{assignment.Max(time_var)}) ->'
            previous_index = index
            index = assignment.Value(routing.NextVar(index))
            distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
        load_var = capacity_dimension.CumulVar(index)
        time_var = time_dimension.CumulVar(index)
        plan_output += f' {manager.IndexToNode(index)} ' \
                       f'Load({assignment.Min(load_var)}) ' \
                       f'Time({assignment.Min(time_var)},{assignment.Max(time_var)})\n'
        plan_output += f'Distance of the route: {distance}m\n'
        plan_output += f'Load of the route: {assignment.Min(load_var)}\n'
        plan_output += f'Time of the route: {assignment.Min(time_var)}min\n'
        print(plan_output)
        total_distance += distance
        total_load += assignment.Min(load_var)
        total_time += assignment.Min(time_var)
    print(f'Total Distance of all routes: {total_distance}m')
    print(f'Total Load of all routes: {total_load}')
    print(f'Total Time of all routes: {total_time}min')

##############################
# Main
##############################
def main():
    """Point d'entrée du programme."""
    data = create_data_model()
    # Nombre de véhicules réels initialement
    num_real = data['num_vehicles']
    # Ajout du véhicule dummy en augmentant le nombre total de véhicules de 1.
    data['num_vehicles'] = num_real + 1  # Indices 0..num_real-1 : véhicules réels, index num_real : dummy

    # Création du RoutingIndexManager avec le nouveau nombre de véhicules.
    manager = pywrapcp.RoutingIndexManager(data['num_locations'],
                                           data['num_vehicles'],
                                           data['depot'])
    routing = pywrapcp.RoutingModel(manager)

    # Enregistrement du callback de distance.
    distance_evaluator_index = routing.RegisterTransitCallback(
        partial(create_distance_evaluator(data), manager))
    routing.SetArcCostEvaluatorOfAllVehicles(distance_evaluator_index)
    add_distance_dimension(routing, manager, data, distance_evaluator_index)

    # Enregistrement du callback de demande.
    demand_evaluator_index = routing.RegisterUnaryTransitCallback(
        partial(create_demand_evaluator(data), manager))
    add_capacity_constraints(routing, manager, data, demand_evaluator_index)

    # Enregistrement du callback de temps.
    time_evaluator_index = routing.RegisterTransitCallback(
        partial(create_time_evaluator(data), manager))
    add_time_window_constraints(routing, manager, data, time_evaluator_index)

    # Restreindre l'affectation : seuls les véhicules réels (0..num_real-1) desservent les clients,
    # et le nœud dummy global est réservé au véhicule dummy (indice num_real).
    restrict_vehicle_assignments(routing, manager, data)

    # [HUB] Contraintes de synchronisation pour le hub (dépôt et pickup)
    time_dimension = routing.GetDimensionOrDie('Time')
    if 'hub_deposit' in data and 'hub_pickup' in data:
        deposit_index = manager.NodeToIndex(data['hub_deposit'])
        pickup_index = manager.NodeToIndex(data['hub_pickup'])
        # On impose que le dépôt se fasse avant le pickup.
        routing.solver().Add(time_dimension.CumulVar(deposit_index) <= time_dimension.CumulVar(pickup_index))
        routing.solver().Add(routing.VehicleVar(deposit_index) != routing.VehicleVar(pickup_index))

    # [HORLOGE GLOBALE] Lier le nœud dummy global (servi par le véhicule dummy) à la synchronisation du hub.
    if 'dummy_global_node' in data and 'hub_deposit' in data and 'hub_pickup' in data:
        dummy_index = manager.NodeToIndex(data['dummy_global_node'])
        dummy_time = time_dimension.CumulVar(dummy_index)
        deposit_index = manager.NodeToIndex(data['hub_deposit'])
        pickup_index = manager.NodeToIndex(data['hub_pickup'])
        # Contraintes : le temps du dépôt <= temps global (dummy) <= temps du pickup.
        routing.solver().Add(time_dimension.CumulVar(deposit_index) <= dummy_time)
        routing.solver().Add(dummy_time <= time_dimension.CumulVar(pickup_index))

    # Optionnel : Forcer les véhicules réels à démarrer à 0
    for vehicle_id in range(num_real):
        start_index = routing.Start(vehicle_id)
        routing.solver().Add(time_dimension.CumulVar(start_index) == 0)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.FromSeconds(50)

    solution = routing.SolveWithParameters(search_parameters)
    if solution:
        print_solution(data, manager, routing, solution)
        solution_data = extract_solution_steps(data, manager, routing, solution)
        html_content = generate_html_visualization(solution_data, data)
        with open("solution_visualization.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("Visualization HTML saved to solution_visualization.html")
    else:
        print("No solution found !")

if __name__ == '__main__':
    main()
