# create_toy_data.py (place this in ortools/ directory)
import pandas as pd
import numpy as np
import os
from typing import List, Tuple

# Configuration variables - Modify these to change the toy data dynamically
# General settings
DEPOT_POSITION: Tuple[float, float] = (0.0, 0.0)  # Fixed depot position
POSITION_RANGE_MIN: float = 0.0  # Min value for random positions (lat/long)
POSITION_RANGE_MAX: float = 10.0  # Max value for random positions
SPEED_FACTOR: float = 10.0  # Factor to convert distance to time (time_matrix = distance_matrix * SPEED_FACTOR)

# Customers (colis)
NUM_CUSTOMERS: int = 8  # Number of customers
CUSTOMER_VOLUME_MIN: float = 1.0  # Min volume per customer
CUSTOMER_VOLUME_MAX: float = 5.0  # Max volume per customer
TW_START_MIN: int = 0  # Min time window start (minutes from midnight)
TW_START_MAX: int = 50  # Max time window start
TW_END_MIN: int = 100  # Min time window end
TW_END_MAX: int = 200  # Max time window end

# Vehicles (livreurs)
NUM_VEHICLES: int = 1  # Number of vehicles
VEHICLE_CAPACITY_MIN: float = 10.0  # Min capacity per vehicle
VEHICLE_CAPACITY_MAX: float = 20.0  # Max capacity per vehicle
START_TIME_MIN: int = 0  # Min start time for shifts
START_TIME_MAX: int = 0  # Max start time (set to same for uniform)
END_TIME_MIN: int = 200  # Min end time for shifts
END_TIME_MAX: int = 300  # Max end time

# Hubs
NUM_HUBS: int = 1  # Number of hubs
HUB_LOAD_LIMIT: float = None  # Load limit per hub (None for no limit)

# Weights
WEIGHTS_DICT = {
    'distance': 1.0,
    'tardiness': 0.8,
    'hubs': 0.6,
    'imbalance': 0.4,
    'waiting': 0.2
}  # Dictionary of weights; add/modify keys as needed

# Function to generate random positions
def generate_random_position() -> Tuple[float, float]:
    lat = np.random.uniform(POSITION_RANGE_MIN, POSITION_RANGE_MAX)
    long = np.random.uniform(POSITION_RANGE_MIN, POSITION_RANGE_MAX)
    return (lat, long)

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

# Main generation logic
data_dir = os.path.join('optimizer', 'tests', 'toy_data')
os.makedirs(data_dir, exist_ok=True)

# Generate positions: depot + customers + hubs
locations = [DEPOT_POSITION]
customer_positions = [generate_random_position() for _ in range(NUM_CUSTOMERS)]
hub_positions = [generate_random_position() for _ in range(NUM_HUBS)]
locations.extend(customer_positions)
locations.extend(hub_positions)

# Compute matrices
distance_matrix = compute_distance_matrix(locations)
time_matrix = distance_matrix * SPEED_FACTOR

# Toy colis
colis_data = {
    'id': list(range(1, NUM_CUSTOMERS + 1)),
    'position': customer_positions,
    'tw_start': [np.random.randint(TW_START_MIN, TW_START_MAX + 1) for _ in range(NUM_CUSTOMERS)],
    'tw_end': [np.random.randint(TW_END_MIN, TW_END_MAX + 1) for _ in range(NUM_CUSTOMERS)],
    'volume': [np.random.uniform(CUSTOMER_VOLUME_MIN, CUSTOMER_VOLUME_MAX) for _ in range(NUM_CUSTOMERS)]
}
colis = pd.DataFrame(colis_data)
colis.to_json(os.path.join(data_dir, 'colis.json'), orient='records')

# Toy livreurs
livreurs_data = {
    'id': list(range(1, NUM_VEHICLES + 1)),
    'capacity': [np.random.uniform(VEHICLE_CAPACITY_MIN, VEHICLE_CAPACITY_MAX) for _ in range(NUM_VEHICLES)],
    'start_time': [np.random.randint(START_TIME_MIN, START_TIME_MAX + 1) for _ in range(NUM_VEHICLES)],
    'end_time': [np.random.randint(END_TIME_MIN, END_TIME_MAX + 1) for _ in range(NUM_VEHICLES)]
}
livreurs = pd.DataFrame(livreurs_data)
livreurs.to_json(os.path.join(data_dir, 'livreurs.json'), orient='records')

# Toy hubs
hubs_data = {
    'id': list(range(1, NUM_HUBS + 1)),
    'position': hub_positions,
    'load_limit': [HUB_LOAD_LIMIT] * NUM_HUBS
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

print(f"Toy data created in {data_dir} with configuration:")
print(f" - Customers: {NUM_CUSTOMERS}")
print(f" - Vehicles: {NUM_VEHICLES}")
print(f" - Hubs: {NUM_HUBS}")