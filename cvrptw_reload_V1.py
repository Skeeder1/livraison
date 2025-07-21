#!/usr/bin/env python3
# This Python file uses the following encoding: utf-8
# Copyright 2015 Tin Arm Engineering AB
# Copyright 2018 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# ... (rest of the license header)

from functools import partial
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from print_solution import *

###########################
# Problem Data Definition #
###########################
def create_data_model():
    """Crée le modèle de données avec les points de livraison, les hubs,
       et un nœud dummy servant d’horloge globale.
    """
    data = {}
    _capacity = 3
    # Liste des localisations (en unités de block)
    _locations = [
        (4, 4),  # depot
        (4, 4),  # unload depot_first
        (4, 4),  # unload depot_second
        (4, 4),  # unload depot_third
        (4, 4),  # unload depot_fourth
        (4, 4),  # unload depot_fifth
        (2, 0),
        (8, 0),  # locations to visit
        (0, 1),
        (1, 1),
        (5, 2),
        (7, 2),
        (3, 3),
        (6, 3),
        (5, 5),
        (8, 5),
        (1, 6),
        (2, 6),
        (3, 7),
        (6, 7),
        (0, 8),
        (7, 8)
    ]
    # Conversion en mètres (Manhattan block ~ (114m, 80m))
    data['locations'] = [(l[0] * 114, l[1] * 80) for l in _locations]
    data['num_locations'] = len(data['locations'])

    # Demandes pour les clients (1 unité par livraison) et pour le depot/recharges
    data['demands'] = [
        0,              # depot
        -_capacity,     # unload depot_first
        -_capacity,     # unload depot_second
        -_capacity,     # unload depot_third
        -_capacity,     # unload depot_fourth
        -_capacity,     # unload depot_fifth
        1, 1,           # locations 6,7
        1, 1,           # locations 8,9
        1, 1,           # locations 10,11
        1, 1,           # locations 12,13
        1, 1,           # locations 14,15
        1, 1,           # locations 16,17
        1, 1,           # locations 18,19
        1, 1            # locations 20,21
    ]
    data['time_per_demand_unit'] = 5  # 5 minutes par unité
    data['time_windows'] = [
        (0, 0),       # depot
        (0, 1000),    # unload depot_first
        (0, 1000),    # unload depot_second
        (0, 1000),    # unload depot_third
        (0, 1000),    # unload depot_fourth
        (0, 1000),    # unload depot_fifth
        (75, 850), (75, 850),   # locations 6,7
        (60, 700), (45, 550),   # locations 8,9
        (0, 800), (50, 600),    # locations 10,11
        (0, 1000), (10, 200),   # locations 12,13
        (0, 1000), (75, 850),   # locations 14,15
        (85, 950), (5, 150),    # locations 16,17
        (15, 250), (10, 200),   # locations 18,19
        (45, 550), (30, 400)    # locations 20,21
    ]

    # Véhicules réels
    data['num_vehicles'] = 3
    data['vehicle_capacity'] = _capacity
    data['vehicle_max_distance'] = 10_000
    data['vehicle_max_time'] = 200   # Par exemple, 1500 minutes d'horizon
    data['vehicle_speed'] = 4 * 60 / 3.6  # 5 km/h converti en m/min
    data['depot'] = 0

    # [HUB : Ajout de 2 nœuds pour le transfert d'1 unité]
    hub_block_location = (3, 6)  # position du hub
    hub_capacity = 1            # transfert d'une unité
    data['locations'].append((hub_block_location[0] * 114, hub_block_location[1] * 80))
    data['locations'].append((hub_block_location[0] * 114, hub_block_location[1] * 80))
    data['num_locations'] = len(data['locations'])
    data['demands'].append(-hub_capacity)  # hub_deposit
    data['demands'].append(hub_capacity)   # hub_pickup
    data['time_windows'].append((50, 500))   # fenêtre pour le dépôt
    data['time_windows'].append((50, 500))   # fenêtre pour le pickup
    data['hub_deposit'] = data['num_locations'] - 2
    data['hub_pickup']  = data['num_locations'] - 1

    # === Ajout du NOEUD DUMMY pour l'horloge globale ===
    # Ce nœud est fictif, avec demande 0 et une fenêtre temporelle large.
    dummy_coordinate = (0, 0)  # Valeur arbitraire
    data['locations'].append(dummy_coordinate)
    data['demands'].append(0)
    data['time_windows'].append((0, data['vehicle_max_time']))  # On étend jusqu'à l'horizon total
    data['dummy_global_node'] = data['num_locations']
    data['num_locations'] = len(data['locations'])

    return data

###########################
# Problem Constraints    #
###########################
def manhattan_distance(position_1, position_2):
    """Calcule la distance de Manhattan entre deux points."""
    return abs(position_1[0] - position_2[0]) + abs(position_1[1] - position_2[1])

def create_distance_evaluator(data):
    """Retourne le callback de distance, avec pénalité si un nœud de hub est impliqué."""
    _distances = {}
    for from_node in range(data['num_locations']):
        _distances[from_node] = {}
        for to_node in range(data['num_locations']):
            if from_node == to_node:
                _distances[from_node][to_node] = 0
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
            extra_penalty = 500  # Ajustez cette valeur si besoin
        return base_distance + extra_penalty
    return distance_evaluator

def add_distance_dimension(routing, manager, data, distance_evaluator_index):
    """Ajoute la dimension distance."""
    distance = 'Distance'
    routing.AddDimension(
        distance_evaluator_index,
        0,
        data['vehicle_max_distance'],
        True,
        distance)
    distance_dimension = routing.GetDimensionOrDie(distance)
    distance_dimension.SetGlobalSpanCostCoefficient(100)

def create_demand_evaluator(data):
    """Retourne le callback de demande."""
    _demands = data['demands']
    def demand_evaluator(manager, from_node):
        return _demands[manager.IndexToNode(from_node)]
    return demand_evaluator

def add_capacity_constraints(routing, manager, data, demand_evaluator_index):
    """Ajoute la dimension capacité.
       Pour le hub, on impose que la quantité déposée soit égale à celle récupérée,
       et qu'un même véhicule ne puisse pas faire les deux.
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

    for node in [1, 2, 3, 4, 5]:
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], 0)

    for node in range(6, len(data['demands'])):
        node_index = manager.NodeToIndex(node)
        capacity_dimension.SlackVar(node_index).SetValue(0)
        if node not in [data.get('hub_deposit'), data.get('hub_pickup')]:
            routing.AddDisjunction([node_index], 100_000)
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
    """Retourne le callback pour le temps total entre nœuds."""
    def service_time(data, node):
        return abs(data['demands'][node]) * data['time_per_demand_unit']
    def travel_time(data, from_node, to_node):
        if from_node == to_node:
            return 0
        else:
            return manhattan_distance(data['locations'][from_node],
                                      data['locations'][to_node]) / data['vehicle_speed']
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
    """Ajoute la dimension Temps et les fenêtres temporelles."""
    time = 'Time'
    max_time = data['vehicle_max_time']
    # Ne pas forcer le cumul à zéro pour permettre une continuité
    routing.AddDimension(
        time_evaluator_index,
        max_time,
        max_time,
        False,
        time)
    
    time_dimension = routing.GetDimensionOrDie(time)

    for location_idx, window in enumerate(data['time_windows']):
        if location_idx == 0:
            continue  # dépôt
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(window[0], window[1])
        routing.AddToAssignment(time_dimension.SlackVar(index))
        
    # Pour les véhicules réels, forcer leur départ à 0
    penalty_slack = 1_000_000_000  # Forte pénalité sur l'attente
    num_real = data['num_vehicles'] - 1
    for vehicle_id in range(num_real):
        index = routing.Start(vehicle_id)
        time_dimension.CumulVar(index).SetRange(0, 0)
        routing.AddToAssignment(time_dimension.SlackVar(index))
        time_dimension.SetSlackCostCoefficientForVehicle(penalty_slack, vehicle_id)
        
    # Pour le véhicule dummy, on lui donne une fenêtre large (de 0 à max_time)
    dummy_vehicle_id = data['num_vehicles'] - 1
    index = routing.Start(dummy_vehicle_id)
    time_dimension.CumulVar(index).SetRange(0, max_time)
    routing.AddToAssignment(time_dimension.SlackVar(index))
    
    # CONTRAINTE HORLOGE GLOBALE :
    # On lie le nœud dummy (global clock) aux événements critiques du hub.
    dummy_index = manager.NodeToIndex(data['dummy_global_node'])
    dummy_time = time_dimension.CumulVar(dummy_index)
    if 'hub_deposit' in data and 'hub_pickup' in data:
        deposit_index = manager.NodeToIndex(data['hub_deposit'])
        pickup_index  = manager.NodeToIndex(data['hub_pickup'])
        routing.solver().Add(time_dimension.CumulVar(deposit_index) <= dummy_time)
        routing.solver().Add(dummy_time >= time_dimension.CumulVar(pickup_index))
    
    # IMPORTANT : Forcer le véhicule dummy à "attendre" jusqu'à la fin de l'horizon.
    # On impose que le temps de fin du véhicule dummy soit égal à max_time.
    dummy_end_index = routing.End(dummy_vehicle_id)
    dummy_end_time = time_dimension.CumulVar(dummy_end_index)
    routing.solver().Add(dummy_end_time == max_time)

def restrict_vehicle_assignments(routing, manager, data):
    """Restreint l'affectation des nœuds : tous les nœuds réels sont servis
       par les véhicules réels, et le nœud dummy est réservé au véhicule dummy.
    """
    num_real = data['num_vehicles'] - 1
    dummy_vehicle = num_real
    for node in range(data['num_locations']):
        if 'dummy_global_node' in data and node == data['dummy_global_node']:
            routing.SetAllowedVehiclesForIndex([dummy_vehicle], manager.NodeToIndex(node))
        else:
            routing.SetAllowedVehiclesForIndex(list(range(num_real)), manager.NodeToIndex(node))

###########
# Printer (inchangé)
###########
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
        node = manager.IndexToNode(order)
        if assignment.Value(routing.NextVar(order)) == order:
            dropped.append(node)
    print(f'dropped orders: {dropped}')
    for reload in range(1, 6):
        node = manager.IndexToNode(reload)
        if assignment.Value(routing.NextVar(reload)) == reload:
            dropped.append(node)
    print(f'dropped reload stations: {dropped}')
    num_real = data['num_vehicles'] - 1
    for vehicle_id in range(num_real):
        index = routing.Start(vehicle_id)
        plan_output = f'Route for vehicle {vehicle_id}:\n'
        distance = 0
        while not routing.IsEnd(index):
            load_var = capacity_dimension.CumulVar(index)
            time_var = time_dimension.CumulVar(index)
            plan_output += (
                f' {manager.IndexToNode(index)} '
                f'Load({assignment.Min(load_var)}) '
                f'Time({assignment.Min(time_var)},{assignment.Max(time_var)}) ->'
            )
            previous_index = index
            index = assignment.Value(routing.NextVar(index))
            distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
        load_var = capacity_dimension.CumulVar(index)
        time_var = time_dimension.CumulVar(index)
        plan_output += (
            f' {manager.IndexToNode(index)} '
            f'Load({assignment.Min(load_var)}) '
            f'Time({assignment.Min(time_var)},{assignment.Max(time_var)})\n'
        )
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

########
# Main #
########
def main():
    """Point d'entrée du programme."""
    data = create_data_model()
    # Nombre de véhicules réels (par exemple 3)
    num_real = data['num_vehicles']
    # On ajoute 1 véhicule dummy ; le véhicule dummy aura l'indice num_real
    data['num_vehicles'] = num_real + 1
    # Création du RoutingIndexManager avec le nombre total de véhicules
    manager = pywrapcp.RoutingIndexManager(data['num_locations'],
                                           data['num_vehicles'],
                                           data['depot'])
    routing = pywrapcp.RoutingModel(manager)
    
    distance_evaluator_index = routing.RegisterTransitCallback(
        partial(create_distance_evaluator(data), manager))
    routing.SetArcCostEvaluatorOfAllVehicles(distance_evaluator_index)
    add_distance_dimension(routing, manager, data, distance_evaluator_index)
    
    demand_evaluator_index = routing.RegisterUnaryTransitCallback(
        partial(create_demand_evaluator(data), manager))
    add_capacity_constraints(routing, manager, data, demand_evaluator_index)
    
    time_evaluator_index = routing.RegisterTransitCallback(
        partial(create_time_evaluator(data), manager))
    add_time_window_constraints(routing, manager, data, time_evaluator_index)
    
    restrict_vehicle_assignments(routing, manager, data)
    
    # [HUB : CONTRAINTES de synchronisation]
    # On impose que le dépôt du hub se fasse avant le pickup,
    # et qu'un même véhicule ne réalise pas les deux.
    time_dimension = routing.GetDimensionOrDie('Time')
    if 'hub_deposit' in data and 'hub_pickup' in data:
        deposit_index = manager.NodeToIndex(data['hub_deposit'])
        pickup_index  = manager.NodeToIndex(data['hub_pickup'])
        routing.solver().Add(time_dimension.CumulVar(deposit_index) <= time_dimension.CumulVar(pickup_index))
        routing.solver().Add(routing.VehicleVar(deposit_index) != routing.VehicleVar(pickup_index))
    
    # [CONTRAINTE HORLOGE GLOBALE]
    # On lie le nœud dummy (global clock) aux temps du hub.
    if 'dummy_global_node' in data and 'hub_deposit' in data and 'hub_pickup' in data:
        dummy_index = manager.NodeToIndex(data['dummy_global_node'])
        dummy_time = time_dimension.CumulVar(dummy_index)
        deposit_index = manager.NodeToIndex(data['hub_deposit'])
        pickup_index  = manager.NodeToIndex(data['hub_pickup'])
        routing.solver().Add(time_dimension.CumulVar(deposit_index) <= dummy_time)
        routing.solver().Add(dummy_time <= time_dimension.CumulVar(pickup_index))
    
    # IMPORTANT : Forcer le véhicule dummy à couvrir tout l'horizon.
    dummy_vehicle_id = data['num_vehicles'] - 1
    dummy_end_index = routing.End(dummy_vehicle_id)
    dummy_end_time = time_dimension.CumulVar(dummy_end_index)
    routing.solver().Add(dummy_end_time == data['vehicle_max_time'])
    
    # Forcer les véhicules réels à démarrer à 0 pour disposer d'une référence commune.
    for vehicle_id in range(num_real):
        start_index = routing.Start(vehicle_id)
        routing.solver().Add(time_dimension.CumulVar(start_index) == 0)
    
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.FromSeconds(5)
    
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
