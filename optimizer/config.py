# optimizer/config.py

# Configuration variables for data generation
class Config:
    # Solver configuration
    TIME_TO_SOLVE = 30  # seconds (increased for better load balancing)

    # Objective function coefficients for load balancing
    TIME_SPAN_COEFFICIENT = 200        # OPTIMAL: Config 1 - Best performance/balance tradeoff
    CAPACITY_SPAN_COEFFICIENT = 50     # OPTIMAL: Config 1
    DISTANCE_SPAN_COEFFICIENT = 30     # OPTIMAL: Config 1
    MAX_TIME_RATIO = 2.0               # Maximum acceptable time ratio (max_time / min_time)

    # General settings
    DEPOT_POSITION = (0.0, 0.0)  # Fixed depot position
    POSITION_RANGE_MIN = -5.0  # Min value for random positions (lat/long)
    POSITION_RANGE_MAX = 5.0  # Max value for random positions
    
    # Time calculation parameters
    DISTANCE_TO_TIME_FACTOR = 600.0  # 1 unit of distance = 600 seconds (10 minutes) - Plus réaliste pour VRP
    SERVICE_TIME_PER_UNIT = 60  # 60 seconds per demand unit for service time

    # Problem size parameters (these will be modified by stats.py)
    NUM_CUSTOMERS = 45
    NUM_VEHICLES = 3
    NUM_HUBS = 2
    NUM_UNLOAD_DEPOTS = 10  # Number of unload depots for reloads at depot
    
    # Capacity settings
    VEHICLE_CAPACITY_MIN = 10.0
    VEHICLE_CAPACITY_MAX = 10.0
    HUB_LOAD_LIMIT = 5.0

    # Time windows (en secondes)
    TW_START_MIN = 0
    TW_START_MAX = 0
    TW_END_MIN = 86400  # 24 heures en secondes
    TW_END_MAX = 86400

    # Time window behavior
    TIME_WINDOWS_OPTIONAL = True  # If True, time windows are optional with penalties
    TIME_WINDOW_VIOLATION_PENALTY = 50000  # Penalty per second of violation (only if optional)

    # Vehicle shifts (en secondes)
    START_TIME_MIN = 0
    START_TIME_MAX = 0
    END_TIME_MIN = 86400  # 24 heures en secondes
    END_TIME_MAX = 200000

    # Analysis parameters
    TIME_INCREMENT = 10   # Time increment for solution attempts (seconds)

    @classmethod
    def update(cls, **kwargs):
        """Update configuration parameters dynamically"""
        for key, value in kwargs.items():
            if hasattr(cls, key):
                setattr(cls, key, value)
            else:
                raise ValueError(f"Invalid configuration parameter: {key}")

# Make the Config class available at module level
config = Config()


