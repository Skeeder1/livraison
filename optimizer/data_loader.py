# optimizer/data_loader.py
import pandas as pd
import numpy as np
from typing import Dict, Any
import os

def load_data(data_dir: str) -> Dict[str, Any]:
    """
    Loads all required data from JSON and NumPy files.

    :param data_dir: Directory containing the data files.
    :return: Dictionary with loaded data.
    """
    # Validate file existence
    for file in ['colis.json', 'livreurs.json', 'hubs.json', 'weights.json', 'distance_matrix.npy', 'time_matrix.npy']:
        if not os.path.exists(os.path.join(data_dir, file)):
            raise FileNotFoundError(f"Missing file: {file} in {data_dir}")

    colis = pd.read_json(f"{data_dir}/colis.json", orient='records')
    livreurs = pd.read_json(f"{data_dir}/livreurs.json", orient='records')
    hubs = pd.read_json(f"{data_dir}/hubs.json", orient='records')
    weights = pd.read_json(f"{data_dir}/weights.json", orient='records')

    # Convert weights to dictionary
    if not {'criterion', 'weight'}.issubset(weights.columns):
        raise ValueError("weights.json must contain 'criterion' and 'weight' columns")
    data = {
        'colis': colis,
        'livreurs': livreurs,
        'hubs': hubs,
        'weights': dict(zip(weights['criterion'], weights['weight'])),
        'distance_matrix': np.load(f"{data_dir}/distance_matrix.npy"),
        'time_matrix': np.load(f"{data_dir}/time_matrix.npy"),
        'depot': 0
    }

    # Locations: depot + customers + hubs
    locations = [(0.0, 0.0)]  # Depot at (0,0) assume
    locations.extend(colis['position'].tolist())
    locations.extend(hubs['position'].tolist())
    data['locations'] = locations

    # Node indices: 0: depot, 1 to num_customers: customers, num_customers+1 to end: hubs
    data['num_customers'] = len(colis)
    data['num_hubs'] = len(hubs)
    data['num_nodes'] = 1 + data['num_customers'] + data['num_hubs']

    # Demands: 0 for depot/hubs, positive volume for customers
    demands = [0] * data['num_nodes']
    for i in range(data['num_customers']):
        demands[1 + i] = colis.iloc[i]['volume']
    data['demands'] = demands

    # Time windows: large for depot/hubs, specific for customers
    time_windows = [(0, 1440)] * data['num_nodes']  # 24h in minutes
    for i in range(data['num_customers']):
        time_windows[1 + i] = (colis.iloc[i]['tw_start'], colis.iloc[i]['tw_end'])
    data['time_windows'] = time_windows

    # Vehicle info
    data['vehicle_capacities'] = livreurs['capacity'].tolist()
    data['num_vehicles'] = len(livreurs)
    data['start_times'] = livreurs['start_time'].tolist()
    data['end_times'] = livreurs['end_time'].tolist()

    return data