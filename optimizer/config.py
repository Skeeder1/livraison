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

    # ── Zone de livraison ────────────────────────────────────────────────
    # Le dépôt était placé en (0.0, 0.0), c'est-à-dire « Null Island » : un point
    # du golfe de Guinée, en plein océan. Les tournées s'affichaient donc sur la
    # mer. La zone est désormais calée sur Paris.
    DEPOT_POSITION = (48.8566, 2.3522)  # Paris, Île de la Cité

    # Rayon de la zone de livraison, en degrés de latitude autour du dépôt.
    # 0.055° ≈ 6 km : une tournée urbaine crédible.
    POSITION_RANGE_MIN = -0.055
    POSITION_RANGE_MAX = 0.055

    # ── Conversion distance → temps ──────────────────────────────────────
    # Les distances sont euclidiennes, exprimées en degrés (approximation plane,
    # acceptable à l'échelle d'une ville). Ce facteur les convertit en secondes.
    #
    # Calibrage : ~85 km par degré à la latitude de Paris (111 km en latitude,
    # 73 km en longitude), pour une vitesse moyenne de 20 km/h en circulation
    # urbaine → 85 / 20 × 3600 ≈ 15 300 s par degré.
    #
    # L'ancienne valeur (600) était calée sur une zone de ±5° ; la conserver
    # avec la zone urbaine actuelle ramènerait les trajets à ~30 secondes.
    DISTANCE_TO_TIME_FACTOR = 15000.0
    SERVICE_TIME_PER_UNIT = 60  # 60 seconds per demand unit for service time

    # Graine du générateur aléatoire des données jouet.
    # Fixée pour que deux exécutions produisent le même scénario : indispensable
    # pour comparer des configurations, rejouer un cas, ou réutiliser le cache
    # d'itinéraires OSRM. Mettre à None pour un tirage différent à chaque fois.
    RANDOM_SEED = 42

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


