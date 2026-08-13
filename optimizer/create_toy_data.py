# create_toy_data.py
import pandas as pd
import numpy as np
import os
from typing import List, Tuple
from optimizer.config import Config

# Weights - Could be moved to Config if needed
WEIGHTS_DICT = {
    'distance': 1.0,
    'tardiness': 0.8,
    'hubs': 0.6,
    'imbalance': 0.4,
    'waiting': 0.2
}

def generate_random_position() -> Tuple[float, float]:
    """
    Tire une position au hasard dans la zone de livraison, autour du dépôt.

    `POSITION_RANGE_MIN/MAX` sont des décalages **relatifs au dépôt**, et non des
    coordonnées absolues : sans cela, les points se retrouvaient autour de
    (0, 0), c'est-à-dire en plein océan Atlantique.

    Le décalage en longitude est divisé par cos(latitude) pour que la zone soit
    approximativement circulaire au sol : à la latitude de Paris, un degré de
    longitude ne vaut que ~73 km contre ~111 km pour un degré de latitude.
    """
    center_lat, center_lon = Config.DEPOT_POSITION
    lat = center_lat + np.random.uniform(Config.POSITION_RANGE_MIN, Config.POSITION_RANGE_MAX)
    lon_spread = 1.0 / np.cos(np.radians(center_lat))
    lon = center_lon + np.random.uniform(Config.POSITION_RANGE_MIN, Config.POSITION_RANGE_MAX) * lon_spread
    return (float(lat), float(lon))

# Function to compute Euclidean distance matrix from positions
def compute_distance_matrix(locations: List[Tuple[float, float]]) -> np.ndarray:
    num_points = len(locations)
    dist_matrix = np.zeros((num_points, num_points))
    for i in range(num_points):
        for j in range(num_points):
            if i != j:
                dist_matrix[i, j] = np.sqrt(
                    (locations[i][0] - locations[j][0]) ** 2 + (locations[i][1] - locations[j][1]) ** 2
                )
    return dist_matrix

def create_toy_data(data_dir: str | None = None, verbose: bool = True) -> None:
    """
    Crée les données de test en utilisant la configuration actuelle.

    :param data_dir: Répertoire de destination. Par défaut `optimizer/tests/toy_data`,
        **relatif au répertoire courant** : un appelant qui ne maîtrise pas son
        répertoire de travail doit fournir un chemin absolu.
    :param verbose: Affiche le récapitulatif du scénario généré. Faux pour un
        appelant serveur, qui régénère les données à chaque requête.
    """
    if data_dir is None:
        data_dir = os.path.join('optimizer', 'tests', 'toy_data')
    os.makedirs(data_dir, exist_ok=True)

    # Scénario reproductible d'une exécution à l'autre (cf. Config.RANDOM_SEED).
    if Config.RANDOM_SEED is not None:
        np.random.seed(Config.RANDOM_SEED)

    # Generate positions: depot + customers + hubs
    locations = [Config.DEPOT_POSITION]
    customer_positions = [generate_random_position() for _ in range(Config.NUM_CUSTOMERS)]
    hub_positions = [generate_random_position() for _ in range(Config.NUM_HUBS)]
    locations.extend(customer_positions)
    locations.extend(hub_positions)

    # Compute matrices
    distance_matrix = compute_distance_matrix(locations)
    # Nouveau calcul du temps : distance * DISTANCE_TO_TIME_FACTOR
    time_matrix = distance_matrix * Config.DISTANCE_TO_TIME_FACTOR

    # Toy colis
    colis_data = {
        'id': list(range(1, Config.NUM_CUSTOMERS + 1)),
        'position': customer_positions,
        'tw_start': [np.random.randint(Config.TW_START_MIN, Config.TW_START_MAX + 1) 
                     for _ in range(Config.NUM_CUSTOMERS)],
        'tw_end': [np.random.randint(Config.TW_END_MIN, Config.TW_END_MAX + 1) 
                   for _ in range(Config.NUM_CUSTOMERS)],
        'volume': [1.0 for _ in range(Config.NUM_CUSTOMERS)]  # Volume fixe de 1.0
    }
    colis = pd.DataFrame(colis_data)
    colis.to_json(os.path.join(data_dir, 'colis.json'), orient='records')

    # Toy livreurs
    livreurs_data = {
        'id': list(range(1, Config.NUM_VEHICLES + 1)),
        # Capacités entières : un véhicule transporte un nombre entier de colis,
        # et le solveur tronque de toute façon (`setup_data_extensions`).
        'capacity': [int(round(np.random.uniform(Config.VEHICLE_CAPACITY_MIN, Config.VEHICLE_CAPACITY_MAX)))
                    for _ in range(Config.NUM_VEHICLES)],
        'start_time': [Config.START_TIME_MIN for _ in range(Config.NUM_VEHICLES)],
        'end_time': [Config.END_TIME_MAX for _ in range(Config.NUM_VEHICLES)]
    }
    livreurs = pd.DataFrame(livreurs_data)
    livreurs.to_json(os.path.join(data_dir, 'livreurs.json'), orient='records')

    # Toy hubs
    hubs_data = {
        'id': list(range(1, Config.NUM_HUBS + 1)),
        'position': hub_positions,
        'load_limit': [Config.HUB_LOAD_LIMIT] * Config.NUM_HUBS
    }
    hubs = pd.DataFrame(hubs_data)
    hubs.to_json(os.path.join(data_dir, 'hubs.json'), orient='records')

    # Toy weights
    weights = pd.DataFrame({
        'criterion': list(WEIGHTS_DICT.keys()),
        'weight': list(WEIGHTS_DICT.values())
    })
    weights.to_json(os.path.join(data_dir, 'weights.json'), orient='records')

    # Save matrices
    np.save(os.path.join(data_dir, 'distance_matrix.npy'), distance_matrix)
    np.save(os.path.join(data_dir, 'time_matrix.npy'), time_matrix)

    if verbose:
        print(f"Toy data created in {data_dir} with configuration:")
        print(f" - Customers: {Config.NUM_CUSTOMERS}")
        print(f" - Vehicles: {Config.NUM_VEHICLES}")
        print(f" - Hubs: {Config.NUM_HUBS}")

if __name__ == '__main__':
    create_toy_data()