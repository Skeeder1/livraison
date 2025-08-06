# optimizer/solver.py
from functools import partial
from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2
from optimizer.config import Config


def setup_data_extensions(data):
    """
    Étend les données avec les nœuds additionnels pour OR-Tools.
    
    :param data: Dictionnaire de données du problème
    :return: Données étendues avec capacités des véhicules et nœuds
    """
    # Convert vehicle capacities to integers
    vehicle_capacities = [int(cap) for cap in data['vehicle_capacities']]
    
    # Set additional parameters
    data['time_per_demand_unit'] = 5
    data['vehicle_max_distance'] = 100000
    data['vehicle_max_time'] = 1440000

    # Identify reload group for depot and unload depots
    reload_group = [data['depot']]

    # Add unload depots for reloads at depot
    config.num_unload_depots = 10
    data['unload_depots'] = []
    current_num = len(data['locations'])
    max_vehicle_capacity = max(vehicle_capacities) if vehicle_capacities else 0
    
    for _ in range(num_unload_depots):
        data['locations'].append(data['locations'][data['depot']])
        data['demands'].append(-max_vehicle_capacity)
        data['time_windows'].append((0, data['vehicle_max_time']))
        data['unload_depots'].append(current_num)
        reload_group.append(current_num)
        current_num += 1

    # Add deposit and pickup for each hub for transfers
    hub_capacity = 1
    data['hub_deposits'] = []
    data['hub_pickups'] = []
    hub_start = 1 + data['num_customers']
    hub_indices = range(hub_start, hub_start + data['num_hubs'])
    
    for h in hub_indices:
        deposit = current_num
        pickup = current_num + 1
        data['locations'].append(data['locations'][h])
        data['locations'].append(data['locations'][h])
        data['demands'].append(-hub_capacity)
        data['demands'].append(hub_capacity)
        data['time_windows'].append(data['time_windows'][h])
        data['time_windows'].append(data['time_windows'][h])
        data['hub_deposits'].append(deposit)
        data['hub_pickups'].append(pickup)
        current_num += 2

    # Add dummy nodes and dummy vehicles for each hub
    data['dummy_nodes'] = []
    num_real_vehicles = data['num_vehicles']
    
    for _ in range(data['num_hubs']):
        dummy = current_num
        data['locations'].append(data['locations'][data['depot']])
        data['demands'].append(0)
        data['time_windows'].append((0, data['vehicle_max_time']))
        data['dummy_nodes'].append(dummy)
        current_num += 1

    data['num_locations'] = len(data['locations'])
    data['num_vehicles'] = num_real_vehicles + data['num_hubs']

    # Extend vehicle capacities and max times for dummy vehicles
    vehicle_capacities += [0] * data['num_hubs']
    vehicle_max_times = [data['end_times'][v] - data['start_times'][v] for v in range(num_real_vehicles)]
    vehicle_max_times += [data['vehicle_max_time']] * data['num_hubs']

    return vehicle_capacities, vehicle_max_times, reload_group, hub_indices, num_real_vehicles


def create_base_node_mapping(data, hub_indices):
    """
    Crée la correspondance entre nœuds étendus et nœuds de base pour les matrices.
    
    :param data: Dictionnaire de données étendues
    :param hub_indices: Indices des hubs originaux
    :return: Liste de correspondance base_node
    """
    base_node = list(range(data['num_nodes']))
    
    for u in data['unload_depots']:
        base_node.append(data['depot'])
        
    for i, d in enumerate(data['hub_deposits']):
        hub = list(hub_indices)[i]
        base_node.append(hub)
        
    for i, p in enumerate(data['hub_pickups']):
        hub = list(hub_indices)[i]
        base_node.append(hub)
        
    for d in data['dummy_nodes']:
        base_node.append(data['depot'])
        
    return base_node


def create_evaluator_functions(data, base_node, reload_group):
    """
    Crée les fonctions d'évaluation pour les dimensions du routage.
    
    :param data: Dictionnaire de données
    :param base_node: Correspondance des nœuds
    :param reload_group: Groupe de rechargement
    :return: Fonctions d'évaluation distance, demande et temps
    """
    def get_distance(from_node, to_node):
        b_from = base_node[from_node]
        b_to = base_node[to_node]
        return int(data['distance_matrix'][b_from, b_to])

    def get_travel_time(from_node, to_node):
        # Calcul dynamique : distance * facteur de conversion
        b_from = base_node[from_node]
        b_to = base_node[to_node]
        distance = data['distance_matrix'][b_from, b_to]
        return int(distance * Config.DISTANCE_TO_TIME_FACTOR)

    def create_distance_evaluator(data):
        def distance_evaluator(manager, from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            base_dist = get_distance(from_node, to_node)
            if from_node in reload_group and to_node in reload_group:
                base_dist = data['vehicle_max_distance']
            extra_penalty = 0
            hub_nodes = data['hub_deposits'] + data['hub_pickups']
            if from_node in hub_nodes or to_node in hub_nodes:
                extra_penalty = 500
            return base_dist + extra_penalty
        return distance_evaluator

    def create_demand_evaluator(data):
        def demand_evaluator(manager, from_index):
            from_node = manager.IndexToNode(from_index)
            return int(data['demands'][from_node])
        return demand_evaluator

    def service_time(data, node):
        # Utiliser la configuration centralisée pour le temps de service
        return abs(data['demands'][node]) * Config.SERVICE_TIME_PER_UNIT

    def create_time_evaluator(data):
        def time_evaluator(manager, from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(service_time(data, from_node) + get_travel_time(from_node, to_node))
        return time_evaluator

    return create_distance_evaluator, create_demand_evaluator, create_time_evaluator


def setup_routing_model(data, vehicle_capacities, vehicle_max_times):
    """
    Crée et configure le modèle de routage OR-Tools.
    
    :param data: Dictionnaire de données
    :param vehicle_capacities: Capacités des véhicules
    :param vehicle_max_times: Temps max des véhicules
    :return: Manager, routing model et fonctions d'évaluation
    """
    manager = pywrapcp.RoutingIndexManager(data['num_locations'], data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)
    
    # Créer les fonctions d'évaluation
    reload_group = [data['depot']] + data['unload_depots']
    hub_indices = range(1 + data['num_customers'], 1 + data['num_customers'] + data['num_hubs'])
    base_node = create_base_node_mapping(data, hub_indices)
    
    create_distance_evaluator, create_demand_evaluator, create_time_evaluator = create_evaluator_functions(
        data, base_node, reload_group
    )
    
    return manager, routing, create_distance_evaluator, create_demand_evaluator, create_time_evaluator


def add_routing_dimensions(routing, manager, data, vehicle_capacities, vehicle_max_times, 
                         create_distance_evaluator, create_demand_evaluator, create_time_evaluator):
    """
    Ajoute les dimensions de distance, capacité et temps au modèle de routage.
    
    :param routing: Modèle de routage
    :param manager: Gestionnaire d'indices
    :param data: Dictionnaire de données
    :param vehicle_capacities: Capacités des véhicules
    :param vehicle_max_times: Temps max des véhicules
    :param create_distance_evaluator: Fonction d'évaluation distance
    :param create_demand_evaluator: Fonction d'évaluation demande
    :param create_time_evaluator: Fonction d'évaluation temps
    :return: Dimensions de distance, capacité et temps
    """
    # Distance dimension
    distance_evaluator_index = routing.RegisterTransitCallback(partial(create_distance_evaluator(data), manager))
    distance = 'Distance'
    routing.AddDimension(distance_evaluator_index, 0, data['vehicle_max_distance'], True, distance)
    distance_dimension = routing.GetDimensionOrDie(distance)
    distance_dimension.SetGlobalSpanCostCoefficient(100)

    # Capacity dimension
    demand_evaluator_index = routing.RegisterUnaryTransitCallback(partial(create_demand_evaluator(data), manager))
    capacity = 'Capacity'
    max_slack_capacity = max(vehicle_capacities + [0])
    routing.AddDimensionWithVehicleCapacity(demand_evaluator_index, max_slack_capacity, vehicle_capacities, True, capacity)
    capacity_dimension = routing.GetDimensionOrDie(capacity)

    # Time dimension
    time_evaluator_index = routing.RegisterTransitCallback(partial(create_time_evaluator(data), manager))
    time = 'Time'
    routing.AddDimensionWithVehicleCapacity(time_evaluator_index, data['vehicle_max_time'], vehicle_max_times, False, time)
    time_dimension = routing.GetDimensionOrDie(time)

    return distance_dimension, capacity_dimension, time_dimension, distance_evaluator_index


def configure_constraints_and_penalties(routing, manager, data, capacity_dimension, hub_indices):
    """
    Configure les contraintes et pénalités pour les différents types de nœuds.
    
    :param routing: Modèle de routage
    :param manager: Gestionnaire d'indices
    :param data: Dictionnaire de données
    :param capacity_dimension: Dimension de capacité
    :param hub_indices: Indices des hubs
    """
    # Set slacks and disjunctions for customers
    customer_start = 1
    customer_end = 1 + data['num_customers']
    for node in range(customer_start, customer_end):
        node_index = manager.NodeToIndex(node)
        capacity_dimension.SlackVar(node_index).SetValue(0)
        routing.AddDisjunction([node_index], 100000)

    # Unload depots
    for node in data['unload_depots']:
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], 0)

    # Hub nodes
    for node in hub_indices:
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], 500)

    # Hub deposits and pickups
    for node in data['hub_deposits'] + data['hub_pickups']:
        node_index = manager.NodeToIndex(node)
        capacity_dimension.SlackVar(node_index).SetValue(0)

    # Dummy nodes
    for node in data['dummy_nodes']:
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], 100000)


def setup_time_constraints(routing, manager, data, time_dimension, num_real_vehicles):
    """
    Configure les contraintes temporelles et fenêtres de temps.
    
    :param routing: Modèle de routage
    :param manager: Gestionnaire d'indices
    :param data: Dictionnaire de données
    :param time_dimension: Dimension temporelle
    :param num_real_vehicles: Nombre de véhicules réels
    """
    # Add time windows
    for location_idx, window in enumerate(data['time_windows']):
        if location_idx == data['depot']:
            continue
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(int(window[0]), int(window[1]))
        routing.AddToAssignment(time_dimension.SlackVar(index))

    # Set vehicle start and end times
    penalty_slack = 100
    for vehicle_id in range(num_real_vehicles):
        index = routing.Start(vehicle_id)
        time_dimension.CumulVar(index).SetValue(int(data['start_times'][vehicle_id]))
        routing.AddToAssignment(time_dimension.SlackVar(index))
        time_dimension.SetSlackCostCoefficientForVehicle(penalty_slack, vehicle_id)

        end_index = routing.End(vehicle_id)
        time_dimension.CumulVar(end_index).SetMax(int(data['end_times'][vehicle_id]))

    # For dummy vehicles
    for i in range(data['num_hubs']):
        vehicle_id = num_real_vehicles + i
        index = routing.Start(vehicle_id)
        time_dimension.CumulVar(index).SetRange(0, data['vehicle_max_time'])
        routing.AddToAssignment(time_dimension.SlackVar(index))
        end_index = routing.End(vehicle_id)
        time_dimension.CumulVar(end_index).SetValue(data['vehicle_max_time'])


def setup_vehicle_restrictions(routing, manager, data, num_real_vehicles):
    """
    Configure les restrictions d'affectation des véhicules aux nœuds.
    
    :param routing: Modèle de routage
    :param manager: Gestionnaire d'indices
    :param data: Dictionnaire de données
    :param num_real_vehicles: Nombre de véhicules réels
    """
    real_vehicles = list(range(num_real_vehicles))
    for node in range(data['num_locations']):
        node_index = manager.NodeToIndex(node)
        if node in data['dummy_nodes']:
            dummy_i = data['dummy_nodes'].index(node)
            dummy_v = num_real_vehicles + dummy_i
            routing.SetAllowedVehiclesForIndex([dummy_v], node_index)
        else:
            routing.SetAllowedVehiclesForIndex(real_vehicles, node_index)


def add_hub_constraints(routing, manager, data, time_dimension, capacity_dimension):
    """
    Ajoute les contraintes spécifiques aux hubs pour les transferts.
    
    :param routing: Modèle de routage
    :param manager: Gestionnaire d'indices
    :param data: Dictionnaire de données
    :param time_dimension: Dimension temporelle
    :param capacity_dimension: Dimension de capacité
    """
    for i in range(data['num_hubs']):
        deposit = data['hub_deposits'][i]
        pickup = data['hub_pickups'][i]
        dummy = data['dummy_nodes'][i]
        deposit_index = manager.NodeToIndex(deposit)
        pickup_index = manager.NodeToIndex(pickup)
        dummy_index = manager.NodeToIndex(dummy)

        # Time constraint
        routing.solver().Add(time_dimension.CumulVar(deposit_index) <= time_dimension.CumulVar(pickup_index))

        # Different vehicles
        routing.solver().Add(routing.VehicleVar(deposit_index) != routing.VehicleVar(pickup_index))

        # Capacity constraint
        routing.solver().Add(
            capacity_dimension.CumulVar(deposit_index) + data['demands'][deposit] ==
            capacity_dimension.CumulVar(pickup_index) - data['demands'][pickup]
        )

        # Dummy constraints
        dummy_time = time_dimension.CumulVar(dummy_index)
        routing.solver().Add(time_dimension.CumulVar(deposit_index) <= dummy_time)
        routing.solver().Add(dummy_time <= time_dimension.CumulVar(pickup_index))


def configure_search_parameters(data):
    """
    Configure les paramètres de recherche pour le solver.
    
    :param data: Dictionnaire de données
    :return: Paramètres de recherche configurés
    """
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    
    time_limit = data.get('time_limit', Config.MAX_TIME_LIMIT)
    search_parameters.time_limit.FromSeconds(time_limit)
    
    return search_parameters


def solve_vrp(data):
    """
    Fonction principale pour résoudre le VRP.
    
    :param data: Dictionnaire de données du problème
    :return: Manager, routing model et solution
    """
    # 1. Étendre les données
    vehicle_capacities, vehicle_max_times, reload_group, hub_indices, num_real_vehicles = setup_data_extensions(data)
    
    # 2. Créer le modèle de routage
    manager, routing, create_distance_evaluator, create_demand_evaluator, create_time_evaluator = setup_routing_model(
        data, vehicle_capacities, vehicle_max_times
    )
    
    # 3. Ajouter les dimensions
    distance_dimension, capacity_dimension, time_dimension, distance_evaluator_index = add_routing_dimensions(
        routing, manager, data, vehicle_capacities, vehicle_max_times,
        create_distance_evaluator, create_demand_evaluator, create_time_evaluator
    )
    
    # 4. Configurer les contraintes et pénalités
    configure_constraints_and_penalties(routing, manager, data, capacity_dimension, hub_indices)
    
    # 5. Configurer les contraintes temporelles
    setup_time_constraints(routing, manager, data, time_dimension, num_real_vehicles)
    
    # 6. Configurer les restrictions de véhicules
    setup_vehicle_restrictions(routing, manager, data, num_real_vehicles)
    
    # 7. Ajouter les contraintes de hubs
    add_hub_constraints(routing, manager, data, time_dimension, capacity_dimension)
    
    # 8. Définir la fonction objective
    routing.SetArcCostEvaluatorOfAllVehicles(distance_evaluator_index)
    
    # 9. Configurer les paramètres de recherche
    search_parameters = configure_search_parameters(data)
    
    # 10. Résoudre
    solution = routing.SolveWithParameters(search_parameters)
    
    return manager, routing, solution