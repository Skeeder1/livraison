# optimizer/postprocessor.py
from ortools.constraint_solver import pywrapcp
from typing import Dict, Any

def get_total_distance(manager, routing, solution, data):
    """    
    Computes total distance from solution.

    :param manager: Routing manager.
    :param routing: Routing model.
    :param solution: Solution assignment.
    :param data: Data dictionary.
    :return: Total distance.
    """
    total_distance = 0
    for vehicle_id in range(data['num_vehicles']):
        index = routing.Start(vehicle_id)
        while not routing.IsEnd(index):
            # from_node = manager.IndexToNode(index)  # Optional: can comment out if not needed elsewhere
            next_index = solution.Value(routing.NextVar(index))
            # to_node = manager.IndexToNode(next_index)  # Optional: can comment out if not needed elsewhere
            total_distance += routing.GetArcCostForVehicle(index, next_index, vehicle_id)  # Modified line to use arc cost
            index = next_index
    return total_distance

def get_results(data: Dict[str, Any], manager: pywrapcp.RoutingIndexManager, routing: pywrapcp.RoutingModel, solution: pywrapcp.Assignment) -> Dict[str, Any]:
    """
    Extracts results from solution.

    :param data: Data dictionary.
    :param manager: Routing manager.
    :param routing: Routing model.
    :param solution: Solution assignment.
    :return: Dictionary with results.
    """
    if solution is None:
        return {'error': 'No solution found'}

    time_dimension = routing.GetDimensionOrDie('Time')
    capacity_dimension = routing.GetDimensionOrDie('Capacity')

    routes = []
    estimated_times = []
    remaining_charges = []  # Load remaining, but since CVRP, remaining = capacity - total delivered? But capacity is on cumulative

    for v in range(data['num_vehicles']):
        index = routing.Start(v)
        route = []
        times = []
        loads = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            route.append(node)
            times.append(solution.Value(time_dimension.CumulVar(index)))
            loads.append(solution.Value(capacity_dimension.CumulVar(index)))
            index = solution.Value(routing.NextVar(index))
        route.append(manager.IndexToNode(index))
        times.append(solution.Value(time_dimension.CumulVar(index)))
        loads.append(solution.Value(capacity_dimension.CumulVar(index)))
        routes.append(route)
        estimated_times.append(times)
        remaining_charges.append([data['vehicle_capacities'][v] - l for l in loads])  # Assume remaining = cap - cumul delivered

    total_distance = get_total_distance(manager, routing, solution, data)
    total_tardiness = 0
    for v in range(data['num_vehicles']):
        index = routing.Start(v)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if 1 <= node <= data['num_customers']:
                time = solution.Value(time_dimension.CumulVar(index))
                _, tw_end = data['time_windows'][node]
                total_tardiness += max(0, time - tw_end)
            index = solution.Value(routing.NextVar(index))

    activated_hubs = set()
    for h in range(data['num_hubs']):
        for v in range(data['num_vehicles']):
            node = data['hub_indices'][h][v]
            if solution.Value(routing.ActiveVar(manager.NodeToIndex(node))) == 1:
                activated_hubs.add(h)

    loads = [solution.Value(capacity_dimension.CumulVar(routing.End(v))) for v in range(data['num_vehicles'])]
    imbalance = max(loads) - min(loads) if loads else 0

    calc_time = 0  # Assume from log

    return {
        'per_livreur': {
            'routes': routes,
            'estimated_times': estimated_times,
            'remaining_charges': remaining_charges
        },
        'indicators': {
            'total_distance': total_distance,
            'total_tardiness_minutes': total_tardiness,
            'activated_hubs': len(activated_hubs),
            'load_repartition': loads,
            'calc_time': calc_time
        }
    }