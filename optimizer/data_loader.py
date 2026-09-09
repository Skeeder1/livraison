# optimizer/data_loader.py
import json
import os
from typing import Any

import numpy as np

from optimizer.config import Config


def load_data(data_dir: str) -> dict[str, Any]:
    """
    Loads all required data from JSON and NumPy files.

    :param data_dir: Directory containing the data files.
    :return: Dictionary with loaded data.
    """
    # Validate file existence
    for file in ['colis.json', 'livreurs.json', 'hubs.json', 'weights.json', 'distance_matrix.npy']:
        if not os.path.exists(os.path.join(data_dir, file)):
            raise FileNotFoundError(f"Missing file: {file} in {data_dir}")

    # Les quatre tables sont des listes d'enregistrements, la forme meme que
    # `DataFrame.to_json(orient='records')` ecrivait. Elles ne servent qu'ici :
    # rien en aval ne fait autre chose que les compter, si bien que pandas ne
    # gagnait rien et coutait 42 Mo dans la fonction serverless qui resout un
    # scenario a la demande.
    colis = _read_records(data_dir, 'colis.json')
    livreurs = _read_records(data_dir, 'livreurs.json')
    hubs = _read_records(data_dir, 'hubs.json')
    weights = _read_records(data_dir, 'weights.json')

    # Convert weights to dictionary
    if any(not {'criterion', 'weight'}.issubset(entry) for entry in weights):
        raise ValueError("weights.json must contain 'criterion' and 'weight' columns")
    data = {
        'colis': colis,
        'livreurs': livreurs,
        'hubs': hubs,
        'weights': {entry['criterion']: entry['weight'] for entry in weights},
        'distance_matrix': np.load(f"{data_dir}/distance_matrix.npy"),
        # Facultative : seul le mode routier la produit. Son absence fait
        # retomber le solveur sur `distance x DISTANCE_TO_TIME_FACTOR`.
        **({'time_matrix': np.load(f"{data_dir}/time_matrix.npy"),
            'distance_scale': 1.0}
           if os.path.exists(f"{data_dir}/time_matrix.npy") else {}),
        'depot': 0,  # Assuming depot is always node 1
    }

    # Locations: depot + customers + hubs
    # Le dépôt était codé en dur à (0.0, 0.0), ce qui contredisait silencieusement
    # Config.DEPOT_POSITION : déplacer la zone de livraison déplaçait les clients
    # mais laissait le dépôt en plein océan Atlantique.
    locations = [tuple(Config.DEPOT_POSITION)]
    locations.extend(entry['position'] for entry in colis)
    if len(hubs) > 0:
        locations.extend(entry['position'] for entry in hubs)
    data['locations'] = locations

    # Node indices: 0: depot, 1 to num_customers: customers, num_customers+1 to end: hubs
    data['num_customers'] = len(colis)
    data['num_hubs'] = len(hubs)
    data['num_nodes'] = 1 + data['num_customers'] + data['num_hubs']

    # Demands: 0 for depot/hubs, positive volume for customers
    #
    # La conversion en entier etait jusqu'ici faite par pandas, qui relisait une
    # colonne de 1.0 en int64 sans le dire. Elle est desormais explicite, parce
    # que la dimension de capacite d'OR-Tools ne manipule que des entiers : un
    # volume fractionnaire serait tronque par le modele tout en restant affiche
    # tel quel, exactement le genre d'ecart silencieux que `int()` ferme ici.
    demands = [0] * data['num_nodes']
    for i in range(data['num_customers']):
        demands[1 + i] = int(colis[i]['volume'])
    data['demands'] = demands

    # Time windows: large for depot/hubs, specific for customers (en secondes)
    time_windows = [(0, 86400)] * data['num_nodes']  # 24h en secondes
    for i in range(data['num_customers']):
        time_windows[1 + i] = (int(colis[i]['tw_start']), int(colis[i]['tw_end']))
    data['time_windows'] = time_windows

    # Vehicle info.
    # Capacités ramenées à l'entier : c'est déjà ce que le solveur applique
    # (`setup_data_extensions` fait `int(cap)`), et la troncature était jusqu'ici
    # invisible. Une capacité de 13.7 était annoncée telle quelle, contrainte à
    # 13 par le modèle, et faisait planter le rapport console sur un format
    # entier (`ValueError: Unknown format code 'd' for object of type 'float'`).
    # Le cas ne se présente pas avec les données jouet, que `create_toy_data`
    # écrit déjà arrondies à l'entier.
    data['vehicle_capacities'] = [int(entry['capacity']) for entry in livreurs]
    data['num_vehicles'] = len(livreurs)
    data['start_times'] = [int(entry['start_time']) for entry in livreurs]
    data['end_times'] = [int(entry['end_time']) for entry in livreurs]
    
    # Time-related parameters (centralized in Config)
    # NB : l'import de Config est au niveau module. Le réimporter ici en ferait
    # une variable locale à toute la fonction, y compris avant cette ligne.
    data['time_per_demand_unit'] = Config.SERVICE_TIME_PER_UNIT
    data['distance_to_time_factor'] = Config.DISTANCE_TO_TIME_FACTOR  # Facteur de conversion distance->temps
    data['vehicle_max_time'] = Config.TIME_HORIZON_SECONDS
    data['vehicle_max_distance'] = Config.VEHICLE_MAX_DISTANCE_METERS

    return data


def _read_records(data_dir: str, filename: str) -> list[dict]:
    """Relit une table ecrite par `create_toy_data`, en liste d'enregistrements."""
    with open(os.path.join(data_dir, filename), encoding='utf-8') as handle:
        return json.load(handle)
