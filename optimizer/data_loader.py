# optimizer/data_loader.py
import pandas as pd
import numpy as np
from typing import Dict, Any
import os

from optimizer.config import Config

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
        'depot': 0,  # Assuming depot is always node 1
    }

    # Locations: depot + customers + hubs
    # Le dépôt était codé en dur à (0.0, 0.0), ce qui contredisait silencieusement
    # Config.DEPOT_POSITION : déplacer la zone de livraison déplaçait les clients
    # mais laissait le dépôt en plein océan Atlantique.
    locations = [tuple(Config.DEPOT_POSITION)]
    locations.extend(colis['position'].tolist())
    if len(hubs) > 0:
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

    # Time windows: large for depot/hubs, specific for customers (en secondes)
    time_windows = [(0, 86400)] * data['num_nodes']  # 24h en secondes
    for i in range(data['num_customers']):
        time_windows[1 + i] = (colis.iloc[i]['tw_start'], colis.iloc[i]['tw_end'])
    data['time_windows'] = time_windows

    # Vehicle info.
    # Capacités ramenées à l'entier : c'est déjà ce que le solveur applique
    # (`setup_data_extensions` fait `int(cap)`), et la troncature était jusqu'ici
    # invisible. Une capacité de 13.7 était annoncée telle quelle, contrainte à
    # 13 par le modèle, et faisait planter le rapport console sur un format
    # entier (`ValueError: Unknown format code 'd' for object of type 'float'`).
    # Le cas ne se présentait pas avec les données jouet, dont la colonne
    # entièrement à 10.0 est relue en int64 par pandas.
    data['vehicle_capacities'] = [int(capacity) for capacity in livreurs['capacity'].tolist()]
    data['num_vehicles'] = len(livreurs)
    data['start_times'] = livreurs['start_time'].tolist()
    data['end_times'] = livreurs['end_time'].tolist()
    
    # Time-related parameters (centralized in Config)
    # NB : l'import de Config est au niveau module. Le réimporter ici en ferait
    # une variable locale à toute la fonction, y compris avant cette ligne.
    data['time_per_demand_unit'] = Config.SERVICE_TIME_PER_UNIT
    data['distance_to_time_factor'] = Config.DISTANCE_TO_TIME_FACTOR  # Facteur de conversion distance->temps
    data['vehicle_max_time'] = Config.END_TIME_MAX
    data['vehicle_max_distance'] = 100000  # Large value for distance penalties

    return data