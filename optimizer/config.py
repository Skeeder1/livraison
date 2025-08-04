# optimizer/config.py

# Configuration variables for data generation
class Config:
    # Solver configuration
    TIME_TO_SOLVE = 30  # seconds
    
    # General settings
    DEPOT_POSITION = (0.0, 0.0)  # Fixed depot position
    POSITION_RANGE_MIN = 0.0  # Min value for random positions (lat/long)
    POSITION_RANGE_MAX = 10.0  # Max value for random positions
    SPEED_FACTOR = 10.0  # Factor to convert distance to time

    # Problem size parameters (these will be modified by stats.py)
    NUM_CUSTOMERS = 10
    NUM_VEHICLES = 3
    NUM_HUBS = 2

    # Capacity settings
    VEHICLE_CAPACITY_MIN = 10.0
    VEHICLE_CAPACITY_MAX = 10.0
    HUB_LOAD_LIMIT = 5.0

    # Time windows
    TW_START_MIN = 0
    TW_START_MAX = 0
    TW_END_MIN = 200000
    TW_END_MAX = 200000

    # Vehicle shifts
    START_TIME_MIN = 0
    START_TIME_MAX = 0
    END_TIME_MIN = 200000
    END_TIME_MAX = 200000

    # Analysis parameters
    MAX_TIME_LIMIT = 10  # Maximum time to try finding a solution (seconds)
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


