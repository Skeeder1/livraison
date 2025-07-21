# optimizer/solver.py
from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2
from typing import Dict, Any, Tuple
import time

def create_routing_model(data: Dict[str, Any]) -> Tuple[pywrapcp.RoutingIndexManager, pywrapcp.RoutingModel, pywrapcp.Assignment]:
    """
    Creates the routing model with dimensions and constraints.

    :param data: Preprocessed data dictionary.
    :return: Manager, routing model.
    """
    manager = pywrapcp.RoutingIndexManager(data['num_nodes'], data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)

    # Distance arc cost
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(data['distance_matrix'][from_node][to_node])

    transit_distance = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_distance)

    # Time dimension
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(data['time_matrix'][from_node][to_node])

    transit_time = routing.RegisterTransitCallback(time_callback)
    horizon = 1440  # 24 hours in minutes
    routing.AddDimension(transit_time, horizon, horizon, False, 'Time')
    time_dimension = routing.GetDimensionOrDie('Time')

    high_coeff = 1000000  # For hard constraints
    alpha = data['weights']['distance']
    beta = data['weights']['tardiness']

    # Time windows and tardiness
    for node in range(1, data['num_nodes']):
        index = manager.NodeToIndex(node)
        tw_start, tw_end = data['time_windows'][node]
        time_dimension.CumulVar(index).SetMin(tw_start)  # Hard early
        time_dimension.SetCumulVarSoftUpperBound(index, tw_end, beta)  # Soft late

    # Driver shift limits
    for v in range(data['num_vehicles']):
        start_index = routing.Start(v)
        end_index = routing.End(v)
        time_dimension.CumulVar(start_index).SetMin(data['start_times'][v])
        time_dimension.CumulVar(end_index).SetMax(data['end_times'][v])

    # Capacity dimension (positive demands for cumulative delivered)
    def demand_callback(from_index, to_index):
        to_node = manager.IndexToNode(to_index)
        return data['demands'][to_node]

    transit_demand = routing.RegisterTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(transit_demand, 0, data['vehicle_capacities'], True, 'Capacity')

    # For multiple reloads, use virtual vehicles for trips
    # Assume max_trips = 3 for simplicity
    max_trips = 3
    num_physical = data['num_vehicles']
    data['num_vehicles'] = num_physical * max_trips
    # Replicate capacities, start/end times
    data['vehicle_capacities'] = data['vehicle_capacities'] * max_trips
    data['start_times'] = data['start_times'] * max_trips
    data['end_times'] = data['end_times'] * max_trips

    # Chain time for trips of same physical
    solver = routing.solver()
    turnaround = 10  # minutes to reload
    for l in range(num_physical):
        for k in range(1, max_trips):
            v_prev = l * max_trips + (k-1)
            v = l * max_trips + k
            solver.Add(time_dimension.CumulVar(routing.Start(v)) >= time_dimension.CumulVar(routing.End(v_prev)) + turnaround)

    # For the first trip of each physical, use the start_time, last end_time already set

    # Mandatory break every 4h driving
    # Add driving dimension for cumulative driving
    routing.AddDimension(transit_time, 0, horizon, True, 'Driving')
    driving_dimension = routing.GetDimensionOrDie('Driving')

    # For breaks, use SetBreakIntervalsOfVehicle
    for v in range(data['num_vehicles']):
        break_intervals = []
        # Single break for simplicity, between 4h and end-30min
        break_start_min = 4 * 60
        break_end_max = horizon - 30
        break_duration = 30
        break_interval = routing.solver().FixedDurationIntervalVar(0, horizon, break_duration, False, 'break')
        break_intervals.append(break_interval)
        routing.SetBreakIntervalsOfVehicle(break_intervals, v, [break_start_min, break_end_max])

    # Hubs: optional, with sync for pairs and transfer
    if data['num_hubs'] > 0:
        n_c = data['num_customers']
        hub_nodes = [1 + n_c + h for h in range(data['num_hubs'])]
        for hub_node in hub_nodes:
            routing.AddDisjunction([manager.NodeToIndex(hub_node)], 0)  # Optional

        # Duplicate hubs per vehicle for sync, but to avoid explosion, duplicate for each vehicle
        # Wait, to duplicate, we would need to add more nodes, but for simplicity, since hubs are optional, but to sync, if visited by multiple vehicles, add constraint
        # But to enforce only two, and sync, it's complex
        # For now, skip detailed hub sync and transfer, add as optional visits without additional constraints
        # To add basic sync, would require tracking which vehicles visit which hub, using ActiveVar, but for pairs, O(v^2) constraints, if v small, ok

        # Assume small v, add for each hub, for each pair v1 < v2, if both visit hub, then |time v1 - time v2| <=5
        # But to do that, since hub is single node, but to get the time at hub for each v, if the route visits hub, the time is the time when the vehicle visits it

        # To get the time at hub for v, we can use time_dimension.CumulVar( manager.NodeToIndex(hub_node) ), but since the node is shared, the cumul is the same for all, but no, the cumul is the time at the visit, but if multiple vehicles visit, the time is different for each visit, but the node is one, the CumulVar is one for the node, but no, the CumulVar is for the node, but since routes are separate, how to get per vehicle time?

        # That's the issue, in routing, the CumulVar is per node, but since the node is visited by one vehicle only (unless allowed multiple, but by default, each node visited at most one)
        # Wait, in VRP, each node is visited exactly one, by one vehicle, except optional or depot.

        # For hubs, if optional, but if multiple vehicles can visit the same hub, we need to allow multiple visits to the same node.

        # But in OR-Tools routing, by default, each node is visited at most once, by one vehicle.

        # To allow multiple vehicles to visit the same hub, we need to duplicate the hub node for each vehicle.

        # Yes, that's the standard way.

        # So, to implement, we need to duplicate hubs per vehicle

        # Let's adjust the model for that.

        # Update the node count

        # Customer nodes 1 to n_c, depot 0, then hub copies for each hub per vehicle: for each h, for each v, hub_h_v

        num_hub_copies = data['num_hubs'] * data['num_vehicles']

        old_num_nodes = data['num_nodes']

        data['num_nodes'] = old_num_nodes + num_hub_copies - data['num_hubs']  # replace single with copies

        # Update matrices, demands, tw

        # To extend matrix, for each hub copy, same as the original hub

        # Assume we remove the original hub nodes, add copies

        # First, the base nodes: depot + customers

        base_n = 1 + data['num_customers']

        # Then add hub copies starting from base_n

        data['hub_indices'] = {}

        for h in range(data['num_hubs']):

            data['hub_indices'][h] = {}

            for v in range(data['num_vehicles']):

                node = base_n + h * data['num_vehicles'] + v

                data['hub_indices'][h][v] = node

        # Extend matrices

        original_size = old_num_nodes

        new_size = data['num_nodes']

        new_distance = np.zeros((new_size, new_size), dtype=float)

        new_time = np.zeros((new_size, new_size), dtype=float)

        new_distance[0:base_n, 0:base_n] = data['distance_matrix'][0:base_n, 0:base_n]

        new_time[0:base_n, 0:base_n] = data['time_matrix'][0:base_n, 0:base_n]

        # For new hub copies, copy from original hub row/column

        for h in range(data['num_hubs']):

            original_h = 1 + data['num_customers'] + h

            for v in range(data['num_vehicles']):

                node = data['hub_indices'][h][v]

                new_distance[0:base_n, node] = data['distance_matrix'][0:base_n, original_h]

                new_distance[node, 0:base_n] = data['distance_matrix'][original_h, 0:base_n]

                new_time[0:base_n, node] = data['time_matrix'][0:base_n, original_h]

                new_time[node, 0:base_n] = data['time_matrix'][original_h, 0:base_n]

                # Between hub copies, assume 0 if same hub, but since different v, but location same, so 0

                for v2 in range(data['num_vehicles']):

                    node2 = data['hub_indices'][h][v2]

                    new_distance[node, node2] = 0

                    new_time[node, node2] = 0

        data['distance_matrix'] = new_distance

        data['time_matrix'] = new_time

        # Demands 0 for hub copies

        data['demands'] = data['demands'][:base_n] + [0] * num_hub_copies

        # TW large for hub copies

        data['time_windows'] = data['time_windows'][:base_n] + [(0, 1440)] * num_hub_copies

        # Now, in the model, add disjunction for each hub copy, penalty 0

        for h in range(data['num_hubs']):

            for v in range(data['num_vehicles']):

                node = data['hub_indices'][h][v]

                routing.AddDisjunction([manager.NodeToIndex(node)], 0)

        # Add sync for pairs at same hub

        for h in range(data['num_hubs']):

            for v1 in range(data['num_vehicles']):

                for v2 in range(v1 + 1, data['num_vehicles']):

                    node1 = data['hub_indices'][h][v1]

                    node2 = data['hub_indices'][h][v2]

                    active1 = routing.ActiveVar(manager.NodeToIndex(node1))

                    active2 = routing.ActiveVar(manager.NodeToIndex(node2))

                    time1 = time_dimension.CumulVar(manager.NodeToIndex(node1))

                    time2 = time_dimension.CumulVar(manager.NodeToIndex(node2))

                    # If both active, |time1 - time2| <=5

                    solver.Add(active1 * (time1 - time2) <= 5)

                    solver.Add(active2 * (time2 - time1) <= 5)

                    # For transfer q, same quantity, so q = 0 net, but to have, perhaps add q

                    # For load, since CVRP, cumul is cumulative delivered, to transfer, it would require adjusting the cumul, but hard

                    # For now, assume the exchange is for balance, but to add the objective for imbalance

    # Load imbalance in objective

    capacity_dimension = routing.GetDimensionOrDie('Capacity')

    max_load = solver.Max([capacity_dimension.CumulVar(routing.End(v)) for v in range(data['num_vehicles'])])

    min_load = solver.Min([capacity_dimension.CumulVar(routing.End(v)) for v in range(data['num_vehicles'])])

    imbalance = max_load - min_load

    delta = data['weights']['imbalance']

    solver.Add(routing.AddToAssignment(imbalance * delta))  # Add to objective

    # For useless hubs, count active hubs, penalize

    gamma = data['weights']['hubs']

    active_hubs = solver.Sum([routing.ActiveVar(manager.NodeToIndex(data['hub_indices'][h][v])) for h in range(data['num_hubs']) for v in range(data['num_vehicles'])])  # Count all copies, but to count unique hubs, need to add BoolVar for hub active if any v active

    for h in range(data['num_hubs']):

        hub_active = solver.Max([routing.ActiveVar(manager.NodeToIndex(data['hub_indices'][h][v])) for v in range(data['num_vehicles'])])  # 1 if any v visits

        solver.Add(routing.AddToAssignment(hub_active * gamma))

    # For waiting, to add, perhaps soft penalty for slack at hubs, but skip

    return manager, routing

def solve_vrp(data: Dict[str, Any]) -> Tuple[pywrapcp.RoutingIndexManager, pywrapcp.RoutingModel, pywrapcp.Assignment]:
    """
    Solves the VRP model.

    :param data: Preprocessed data.
    :return: Manager, routing, solution.
    """
    manager, routing = create_routing_model(data)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()

    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH

    search_parameters.time_limit.seconds = 600

    search_parameters.log_search = True

    solution = routing.SolveWithParameters(search_parameters)

    # Post check for hub benefit, if total distance not < baseline, perhaps discard, but for now, assume

    return manager, routing, solution