# create_toy_data.py
import json
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

#: Décimales conservées à l'écriture. C'est le `double_precision` par défaut de
#: `DataFrame.to_json`, qui écrivait ces quatre fichiers jusqu'ici.
JSON_DOUBLE_PRECISION = 10


def _rounded(value):
    """Arrondit les flottants d'une structure, en convertissant les scalaires NumPy."""
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return round(float(value), JSON_DOUBLE_PRECISION)
    return value


def _write_records(data_dir: str, filename: str, records: List[dict]) -> None:
    """
    Ecrit une table sous la forme d'une liste d'enregistrements.

    C'est exactement ce que produisait `DataFrame.to_json(orient='records')`,
    dont ces quatre fichiers sortaient jusqu'ici. Pandas ne servait qu'a ce
    passage par le disque, et pesait 42 Mo dans une fonction serverless plafonnee
    a 225 Mo, d'ou son retrait du chemin de resolution. Il reste une dependance
    de `optimizer.stats`, qui agrege des campagnes de mesure et n'a pas cette
    contrainte.

    L'arrondi n'est pas cosmetique. Sans lui les coordonnees repartent avec
    quelques decimales de plus que ce que pandas ecrivait, et le scenario de
    reference, graine comprise, ne rend plus la meme tournee : les tests lents
    et les chiffres publies dans la demonstration cessent d'etre reproductibles.
    """
    with open(os.path.join(data_dir, filename), 'w', encoding='utf-8') as handle:
        json.dump(_rounded(records), handle)


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
    # Les deux bornes sont tirees colonne par colonne, et non client par client.
    # L'ordre des tirages fait partie du scenario : `RANDOM_SEED` ne reproduit la
    # tournee de reference que si la suite d'appels reste identique.
    tw_start = [int(np.random.randint(Config.TW_START_MIN, Config.TW_START_MAX + 1))
                for _ in range(Config.NUM_CUSTOMERS)]
    tw_end = [int(np.random.randint(Config.TW_END_MIN, Config.TW_END_MAX + 1))
              for _ in range(Config.NUM_CUSTOMERS)]
    colis = [
        {
            'id': i + 1,
            'position': list(customer_positions[i]),
            'tw_start': tw_start[i],
            'tw_end': tw_end[i],
            'volume': 1.0,  # Volume fixe de 1.0
        }
        for i in range(Config.NUM_CUSTOMERS)
    ]
    _write_records(data_dir, 'colis.json', colis)

    # Toy livreurs
    livreurs = [
        {
            'id': i + 1,
            # Capacités entières : un véhicule transporte un nombre entier de colis,
            # et le solveur tronque de toute façon (`setup_data_extensions`).
            'capacity': int(round(np.random.uniform(Config.VEHICLE_CAPACITY_MIN, Config.VEHICLE_CAPACITY_MAX))),
            'start_time': Config.START_TIME_MIN,
            'end_time': Config.END_TIME_MAX,
        }
        for i in range(Config.NUM_VEHICLES)
    ]
    _write_records(data_dir, 'livreurs.json', livreurs)

    # Toy hubs
    hubs = [
        {
            'id': i + 1,
            'position': list(hub_positions[i]),
            'load_limit': Config.HUB_LOAD_LIMIT,
        }
        for i in range(Config.NUM_HUBS)
    ]
    _write_records(data_dir, 'hubs.json', hubs)

    # Toy weights
    weights = [
        {'criterion': criterion, 'weight': weight}
        for criterion, weight in WEIGHTS_DICT.items()
    ]
    _write_records(data_dir, 'weights.json', weights)

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