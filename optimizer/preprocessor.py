# optimizer/preprocessor.py
from typing import Dict, Any
from .solver import solve_vrp, get_total_distance

def preprocess(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pre-processes data: filters hubs (keep all for now), computes baseline VRP without hubs.

    :param data: Loaded data dictionary.
    :return: Updated data with baseline distance.
    """
    # Filter hubs: keep all for now, or implement filtering e.g., based on location clustering

    # Compute baseline without hubs
    data_no_hubs = data.copy()
    n = 1 + data_no_hubs['num_customers']
    data_no_hubs['num_hubs'] = 0
    data_no_hubs['num_nodes'] = n
    data_no_hubs['demands'] = data_no_hubs['demands'][:n]
    data_no_hubs['time_windows'] = data_no_hubs['time_windows'][:n]
    data_no_hubs['distance_matrix'] = data_no_hubs['distance_matrix'][:n, :n]
    data_no_hubs['time_matrix'] = data_no_hubs['time_matrix'][:n, :n]
    data_no_hubs['locations'] = data_no_hubs['locations'][:n]

    manager, routing, solution = solve_vrp(data_no_hubs)
    if solution is None:
        raise ValueError("No baseline solution found")
    baseline_distance = get_total_distance(manager, routing, solution, data_no_hubs)
    data['baseline_distance'] = baseline_distance

    return data