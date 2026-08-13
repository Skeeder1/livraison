# optimizer/preprocessor.py
from typing import Dict, Any
from .solver import solve_vrp, strip_hubs
from .postprocessor import get_total_distance
def preprocess(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pre-processes data: filters hubs (keep all for now), computes baseline VRP without hubs.

    :param data: Loaded data dictionary.
    :return: Updated data with baseline distance.
    """
    # Filter hubs: keep all for now, or implement filtering e.g., based on location clustering

    # Compute baseline without hubs.
    # Le retrait des hubs est mutualisé dans `strip_hubs` : la troncature était
    # dupliquée ici, et `solve_vrp_with_optimal_hubs` en avait une version
    # incomplète qui laissait les hubs dans le modèle.
    data_no_hubs = strip_hubs(data)
    manager, routing, solution = solve_vrp(data_no_hubs)
    if solution is None:
        raise ValueError("No baseline solution found")
    baseline_distance = get_total_distance(manager, routing, solution, data_no_hubs)
    data['baseline_distance'] = baseline_distance

    return data