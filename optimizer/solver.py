# optimizer/solver.py
from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2
from typing import Dict, Any, Tuple
import time
import logging
import numpy as np

logging.basicConfig(level=logging.INFO)

def create_routing_model(data: Dict[str, Any]) -> Tuple[pywrapcp.RoutingIndexManager, pywrapcp.RoutingModel]:
    """
    Creates the routing model with dimensions and constraints.

    :param data: Preprocessed data dictionary.
    :return: Manager, routing model.
    """
    logging.info("Creating routing model")

    cost_scale: int = 10  # Scale factor for costs to handle float weights as ints

    # Round demands and capacities to ints (for toy data; use higher scale for fractions)
    data['demands'] = [int(round(d)) for d in data['demands']]
    data['vehicle_capacities'] = [int(round(c)) for c in data['vehicle_capacities']]
    print("Demands and capacities rounded")
    # Weights
    alpha: float = data['weights']['distance']
    beta: float = data['weights']['tardiness']
    gamma: float = data['weights']['hubs']
    delta: float = data['weights']['imbalance']
    omega: float = data['weights']['waiting']

    # Modification for virtual vehicles (multi-trips) BEFORE manager
    max_trips: int = 3  # Configurable max trips per vehicle
    num_physical: int = data['num_vehicles']
    data['num_vehicles'] = num_physical * max_trips
    data['vehicle_capacities'] = data['vehicle_capacities'] * max_trips
    data['start_times'] = [int(t) for t in data['start_times'] * max_trips]  # Ensure int
    data['end_times'] = [int(t) for t in data['end_times'] * max_trips]  # Ensure int

    # Modification for hub duplication BEFORE manager
    if data['num_hubs'] > 0:
        num_hub_copies: int = data['num_hubs'] * data['num_vehicles']
        old_num_nodes: int = data['num_nodes']
        data['num_nodes'] = old_num_nodes + num_hub_copies - data['num_hubs']

        base_n: int = 1 + data['num_customers']

        data['hub_indices'] = {}
        for h in range(data['num_hubs']):
            data['hub_indices'][h] = {}
            for v in range(data['num_vehicles']):
                node: int = base_n + h * data['num_vehicles'] + v
                data['hub_indices'][h][v] = node

        original_size: int = old_num_nodes
        new_size: int = data['num_nodes']
        new_distance: np.ndarray = np.zeros((new_size, new_size), dtype=float)
        new_time: np.ndarray = np.zeros((new_size, new_size), dtype=float)
        new_distance[0:base_n, 0:base_n] = data['distance_matrix'][0:base_n, 0:base_n]
        new_time[0:base_n, 0:base_n] = data['time_matrix'][0:base_n, 0:base_n]

        for h in range(data['num_hubs']):
            original_h: int = 1 + data['num_customers'] + h
            for v in range(data['num_vehicles']):
                node: int = data['hub_indices'][h][v]
                new_distance[0:base_n, node] = data['distance_matrix'][0:base_n, original_h]
                new_distance[node, 0:base_n] = data['distance_matrix'][original_h, 0:base_n]
                new_time[0:base_n, node] = data['time_matrix'][0:base_n, original_h]
                new_time[node, 0:base_n] = data['time_matrix'][original_h, 0:base_n]
                for v2 in range(data['num_vehicles']):
                    node2: int = data['hub_indices'][h][v2]
                    new_distance[node, node2] = 0
                    new_time[node, node2] = 0

        data['distance_matrix'] = new_distance
        data['time_matrix'] = new_time

        data['demands'] = data['demands'][:base_n] + [0] * num_hub_copies
        data['time_windows'] = data['time_windows'][:base_n] + [(0, 1440) for _ in range(num_hub_copies)]

    print("Creating RoutingIndexManager")
    manager: pywrapcp.RoutingIndexManager = pywrapcp.RoutingIndexManager(data['num_nodes'], data['num_vehicles'], data['depot'])
    print("RoutingIndexManager created")

    print("Creating RoutingModel")
    routing: pywrapcp.RoutingModel = pywrapcp.RoutingModel(manager)
    print("RoutingModel created")

    # Distance arc cost (weighted and scaled)
    def distance_callback(from_index: int, to_index: int) -> int:
        from_node: int = manager.IndexToNode(from_index)
        to_node: int = manager.IndexToNode(to_index)
        return int(cost_scale * alpha * data['distance_matrix'][from_node][to_node])

    transit_distance: int = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_distance)

    # Time dimension
    def time_callback(from_index: int, to_index: int) -> int:
        from_node: int = manager.IndexToNode(from_index)
        to_node: int = manager.IndexToNode(to_index)
        return int(data['time_matrix'][from_node][to_node])

    transit_time: int = routing.RegisterTransitCallback(time_callback)
    horizon: int = 1440  # 24 hours in minutes
    routing.AddDimension(transit_time, horizon, horizon, False, 'Time')  # slack_max=horizon allows waiting
    time_dimension: pywrapcp.RoutingDimension = routing.GetDimensionOrDie('Time')

    M: int = 1000000  # Big-M for constraints

    # Time windows, tardiness, and waiting penalties
    solver: pywrapcp.Solver = routing.solver()
    for node in range(1, data['num_nodes']):
        index: int = manager.NodeToIndex(node)
        tw_start, tw_end = data['time_windows'][node]
        time_dimension.CumulVar(index).SetMin(int(tw_start))  # Hard: no service before tw_start
        time_dimension.SetCumulVarSoftUpperBound(index, int(tw_end), int(cost_scale * beta))  # Soft: penalize late

    # Waiting penalties via slack (only for customers)
    for node in range(1, data['num_customers'] + 1):
        index: int = manager.NodeToIndex(node)
        slack_penalty: pywrapcp.IntExpr = time_dimension.SlackVar(index) * int(cost_scale * omega)
        solver.Add(routing.AddToAssignment(slack_penalty))

    # Driver shift limits (hard)
    for v in range(data['num_vehicles']):
        start_index: int = routing.Start(v)
        end_index: int = routing.End(v)
        time_dimension.CumulVar(start_index).SetMin(int(data['start_times'][v]))
        time_dimension.CumulVar(end_index).SetMax(int(data['end_times'][v]))

    # Capacity dimension
    def demand_callback(from_index: int, to_index: int) -> int:
        to_node: int = manager.IndexToNode(to_index)
        return data['demands'][to_node]

    transit_demand: int = routing.RegisterTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(transit_demand, 0, data['vehicle_capacities'], True, 'Capacity')

    # Chain for multi-trips
    turnaround: int = 10  # minutes to reload
    for l in range(num_physical):
        for k in range(1, max_trips):
            v_prev: int = l * max_trips + (k - 1)
            v: int = l * max_trips + k
            solver.Add(time_dimension.CumulVar(routing.Start(v)) >= time_dimension.CumulVar(routing.End(v_prev)) + turnaround)

    # Mandatory breaks
    print("Adding Driving dimension for breaks")
    max_breaks: int = 1  # Simplified to 1 mandatory for toy; extend for longer shifts
    routing.AddDimension(transit_time, 0, horizon, False, 'Driving')  # slack_max=0 excludes waiting from driving
    driving_dimension: pywrapcp.RoutingDimension = routing.GetDimensionOrDie('Driving')
    print("Driving dimension added")

    for v in range(data['num_vehicles']):
        print(f"Setting breaks for vehicle {v}")
        break_intervals = []
        for b in range(max_breaks):
            break_start_min: int = 4 * 60 * (b + 1)
            break_end_max: int = horizon - 30 * (max_breaks - b)
            break_duration: int = 30
            optional: bool = b > 0  # First mandatory, others optional
            break_interval: pywrapcp.IntervalVar = solver.FixedDurationIntervalVar(
                break_start_min, break_end_max, break_duration, optional, f'break_{v}_{b}'
            )
            break_intervals.append(break_interval)
        driving_dimension.SetBreakIntervalsOfVehicle(break_intervals, v, [transit_time] * data['num_nodes'])
        print(f"Breaks set for vehicle {v}")
        
                
    # Hub constraints
    if data['num_hubs'] > 0:
        for h in range(data['num_hubs']):
            for v in range(data['num_vehicles']):
                node: int = data['hub_indices'][h][v]
                routing.AddDisjunction([manager.NodeToIndex(node)], 0)  # Optional

            # Prevent same vehicle visiting multiple hubs
            for v in range(data['num_vehicles']):
                hub_nodes_for_v: List[int] = [data['hub_indices'][h][v] for h in range(data['num_hubs'])]
                solver.Add(solver.Sum(routing.ActiveVar(manager.NodeToIndex(n)) for n in hub_nodes_for_v) <= 1)

            # Sync times for vehicles at same hub
            for v1 in range(data['num_vehicles']):
                for v2 in range(v1 + 1, data['num_vehicles']):
                    node1: int = data['hub_indices'][h][v1]
                    node2: int = data['hub_indices'][h][v2]
                    active1: pywrapcp.IntVar = routing.ActiveVar(manager.NodeToIndex(node1))
                    active2: pywrapcp.IntVar = routing.ActiveVar(manager.NodeToIndex(node2))
                    time1: pywrapcp.IntVar = time_dimension.CumulVar(manager.NodeToIndex(node1))
                    time2: pywrapcp.IntVar = time_dimension.CumulVar(manager.NodeToIndex(node2))
                    solver.Add(time1 - time2 <= 5 + M * (2 - active1 - active2))
                    solver.Add(time2 - time1 <= 5 + M * (2 - active1 - active2))

                    # Quantity exchange (dummy net zero; extend with PD for real transfers)
                    max_volume: int = 1000  # Upper bound
                    q: pywrapcp.IntVar = solver.IntVar(-max_volume, max_volume, f'q_h{h}_v{v1}v{v2}')
                    solver.Add(q == -q)  # Net zero

        # Hub activation penalty
        hub_actives = []
        for h in range(data['num_hubs']):
            hub_active: pywrapcp.IntVar = solver.Max(
                [routing.ActiveVar(manager.NodeToIndex(data['hub_indices'][h][v])) for v in range(data['num_vehicles'])]
            )
            hub_penalty: pywrapcp.IntExpr = hub_active * int(cost_scale * gamma)
            solver.Add(routing.AddToAssignment(hub_penalty))
            hub_actives.append(hub_active)

        # Any hub used
        any_hub_used: pywrapcp.IntVar = solver.Max(hub_actives)

        # Hard: hubs only if distance strictly reduced
        scaled_baseline: int = int(cost_scale * alpha * data['baseline_distance'])
        solver.Add(routing.CostVar() <= scaled_baseline - 1 + M * (1 - any_hub_used))

    # Load imbalance penalty
    capacity_dimension: pywrapcp.RoutingDimension = routing.GetDimensionOrDie('Capacity')
    max_load: pywrapcp.IntVar = solver.Max([capacity_dimension.CumulVar(routing.End(v)) for v in range(data['num_vehicles'])])
    min_load: pywrapcp.IntVar = solver.Min([capacity_dimension.CumulVar(routing.End(v)) for v in range(data['num_vehicles'])])
    imbalance: pywrapcp.IntVar = max_load - min_load
    imbalance_penalty: pywrapcp.IntExpr = imbalance * int(cost_scale * delta)
    solver.Add(routing.AddToAssignment(imbalance_penalty))

    # Stock conservation
    total_demand = sum(data['demands'])
    solver.Add(solver.IntConst(total_demand) == solver.Sum([capacity_dimension.CumulVar(routing.End(v)) for v in range(data['num_vehicles'])]))
    return manager, routing

def solve_vrp(data: Dict[str, Any]) -> Tuple[pywrapcp.RoutingIndexManager, pywrapcp.RoutingModel, pywrapcp.Assignment]:
    """
    Solves the VRP model.

    :param data: Preprocessed data.
    :return: Manager, routing, solution.
    """
    logging.info("Solving VRP")
    start_time: float = time.time()
    manager, routing = create_routing_model(data)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = 600
    search_parameters.log_search = True

    solution: pywrapcp.Assignment = routing.SolveWithParameters(search_parameters)
    data['calc_time'] = time.time() - start_time

    if solution:
        logging.info("Solution found")
    else:
        logging.warning("No solution found")

    return manager, routing, solution