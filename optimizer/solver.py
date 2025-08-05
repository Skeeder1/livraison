# optimizer/solver.py
from functools import partial
from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2
from optimizer.config import Config

# Get solver time limit from config passed in data or from config
def solve_vrp(data):
    """Solves the VRP using the provided data."""
    # Convert vehicle capacities to integers
    vehicle_capacities = [int(cap) for cap in data['vehicle_capacities']]
    
    # Set additional parameters
    data['time_per_demand_unit'] = 5  # Time per unit demand
    data['vehicle_max_distance'] = 100000  # Large value for max distance
    data['vehicle_max_time'] = 1440000  # Full day in minutes

    # Identify reload group for depot and unload depots
    reload_group = [data['depot']]

    # Add unload depots for reloads at depot
    num_unload_depots = 10  # From cvrptw_reload_V1.py
    data['unload_depots'] = []
    current_num = len(data['locations'])
    max_vehicle_capacity = max(vehicle_capacities) if vehicle_capacities else 0
    for _ in range(num_unload_depots):
        data['locations'].append(data['locations'][data['depot']])
        data['demands'].append(-max_vehicle_capacity)  # Use max capacity for unload
        data['time_windows'].append((0, data['vehicle_max_time']))
        data['unload_depots'].append(current_num)
        reload_group.append(current_num)
        current_num += 1

    # Add deposit and pickup for each hub for transfers
    hub_capacity = 1  # From cvrptw_reload_V1.py
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
        data['locations'].append(data['locations'][data['depot']])  # Same as depot
        data['demands'].append(0)
        data['time_windows'].append((0, data['vehicle_max_time']))
        data['dummy_nodes'].append(dummy)
        current_num += 1

    data['num_locations'] = len(data['locations'])
    data['num_vehicles'] = num_real_vehicles + data['num_hubs']

    # Extend vehicle capacities and max times for dummy vehicles
    vehicle_capacities += [0] * data['num_hubs']  # Dummy vehicles have 0 capacity
    vehicle_max_times = [data['end_times'][v] - data['start_times'][v] for v in range(num_real_vehicles)]
    vehicle_max_times += [data['vehicle_max_time']] * data['num_hubs']

    # Base node for distance and time lookups (extra nodes map to original locations)
    base_node = list(range(data['num_nodes']))
    for u in data['unload_depots']:
        base_node.append(data['depot'])
    for i, d in enumerate(data['hub_deposits']):
        hub = hub_start + i
        base_node.append(hub)
    for i, p in enumerate(data['hub_pickups']):
        hub = hub_start + i
        base_node.append(hub)
    for d in data['dummy_nodes']:
        base_node.append(data['depot'])

    # Helper functions for evaluators
    def get_distance(from_node, to_node):
        b_from = base_node[from_node]
        b_to = base_node[to_node]
        return int(data['distance_matrix'][b_from, b_to])

    def get_travel_time(from_node, to_node):
        b_from = base_node[from_node]
        b_to = base_node[to_node]
        return int(data['time_matrix'][b_from, b_to])

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
                extra_penalty = 500  # Penalty for hub nodes
            return base_dist + extra_penalty
        return distance_evaluator

    def create_demand_evaluator(data):
        def demand_evaluator(manager, from_index):
            from_node = manager.IndexToNode(from_index)
            return int(data['demands'][from_node])  # Convert demands to integer
        return demand_evaluator

    def service_time(data, node):
        return abs(data['demands'][node]) * data['time_per_demand_unit']

    def create_time_evaluator(data):
        def time_evaluator(manager, from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(service_time(data, from_node) + get_travel_time(from_node, to_node))
        return time_evaluator

    # Create routing model
    manager = pywrapcp.RoutingIndexManager(data['num_locations'], data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)

    # Distance dimension
    distance_evaluator_index = routing.RegisterTransitCallback(partial(create_distance_evaluator(data), manager))
    distance = 'Distance'
    routing.AddDimension(
        distance_evaluator_index,
        0,
        data['vehicle_max_distance'],
        True,
        distance
    )
    distance_dimension = routing.GetDimensionOrDie(distance)
    distance_dimension.SetGlobalSpanCostCoefficient(100)

    # Capacity dimension
    demand_evaluator_index = routing.RegisterUnaryTransitCallback(partial(create_demand_evaluator(data), manager))
    capacity = 'Capacity'
    max_slack_capacity = max(vehicle_capacities + [0])
    routing.AddDimensionWithVehicleCapacity(
        demand_evaluator_index,
        max_slack_capacity,
        vehicle_capacities,  # Includes dummy vehicles
        True,
        capacity
    )
    capacity_dimension = routing.GetDimensionOrDie(capacity)

    # Set slacks and disjunctions
    customer_start = 1
    customer_end = 1 + data['num_customers']
    for node in range(customer_start, customer_end):
        node_index = manager.NodeToIndex(node)
        capacity_dimension.SlackVar(node_index).SetValue(0)
        routing.AddDisjunction([node_index], 100000)

    for node in data['unload_depots']:
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], 0)

    for node in hub_indices:
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], 0)

    for node in data['hub_deposits'] + data['hub_pickups']:
        node_index = manager.NodeToIndex(node)
        capacity_dimension.SlackVar(node_index).SetValue(0)

    for node in data['dummy_nodes']:
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], 100000)  # Force visit for dummy

    # Time dimension
    time_evaluator_index = routing.RegisterTransitCallback(partial(create_time_evaluator(data), manager))
    time = 'Time'
    routing.AddDimensionWithVehicleCapacity(
        time_evaluator_index,
        data['vehicle_max_time'],  # slack max (waiting allowed)
        vehicle_max_times,
        False,  # Do not force start cumul to zero
        time
    )
    time_dimension = routing.GetDimensionOrDie(time)

    # Add time windows
    for location_idx, window in enumerate(data['time_windows']):
        if location_idx == data['depot']:
            continue
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(int(window[0]), int(window[1]))  # Ensure integer time windows
        routing.AddToAssignment(time_dimension.SlackVar(index))

    # Set vehicle start and end times
    penalty_slack = 100
    for vehicle_id in range(num_real_vehicles):
        index = routing.Start(vehicle_id)
        time_dimension.CumulVar(index).SetValue(int(data['start_times'][vehicle_id]))  # Ensure integer
        routing.AddToAssignment(time_dimension.SlackVar(index))
        time_dimension.SetSlackCostCoefficientForVehicle(penalty_slack, vehicle_id)

        end_index = routing.End(vehicle_id)
        time_dimension.CumulVar(end_index).SetMax(int(data['end_times'][vehicle_id]))  # Ensure integer

    # For dummy vehicles
    for i in range(data['num_hubs']):
        vehicle_id = num_real_vehicles + i
        index = routing.Start(vehicle_id)
        time_dimension.CumulVar(index).SetRange(0, data['vehicle_max_time'])
        routing.AddToAssignment(time_dimension.SlackVar(index))
        end_index = routing.End(vehicle_id)
        time_dimension.CumulVar(end_index).SetValue(data['vehicle_max_time'])

    # Restrict assignments
    real_vehicles = list(range(num_real_vehicles))
    for node in range(data['num_locations']):
        node_index = manager.NodeToIndex(node)
        if node in data['dummy_nodes']:
            dummy_i = data['dummy_nodes'].index(node)
            dummy_v = num_real_vehicles + dummy_i
            routing.SetAllowedVehiclesForIndex([dummy_v], node_index)
        else:
            routing.SetAllowedVehiclesForIndex(real_vehicles, node_index)

    # Add hub constraints
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

    # Objective function
    #print("time_dimension", time_evaluator_index , " distance_evaluator_index", distance_evaluator_index)
    objectif = time_evaluator_index  + distance_evaluator_index
    routing.SetArcCostEvaluatorOfAllVehicles(distance_evaluator_index)


    # Search parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    
    # Use time limit from data if provided, otherwise from config
    time_limit = data.get('time_limit', Config.MAX_TIME_LIMIT)
    search_parameters.time_limit.FromSeconds(time_limit)

    # Solve
    solution = routing.SolveWithParameters(search_parameters)
    return manager, routing, solution