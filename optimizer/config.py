# optimizer/config.py

# Configuration variables for data generation
class Config:
    # Solver configuration
    TIME_TO_SOLVE = 30  # seconds (increased for better load balancing)

    # Objective function coefficients for load balancing
    # Mesuré, pas supposé : 30 graines appariées, deux scénarios, deux budgets
    # (cf. `experiments/`, campagne du 2026-09-09). À 200 la valeur livrée perdait
    # 30/30 graines sans hub et 29/30 avec, contre 5.
    #
    # L'écart est surtout un écart de CONVERGENCE. À 10 s de budget, passer à 5
    # fait gagner 3 186 s de makespan et 30,9 km ; à 30 s, il ne reste que 76 s
    # et 2,3 km, parce que la configuration livrée finit par rattraper son
    # retard. Un coefficient élevé ne dégrade pas l'optimum, il ralentit la
    # recherche qui y mène. La valeur retenue est celle qui gagne ou égalise
    # partout, jamais celle qui brille au budget le plus court.
    TIME_SPAN_COEFFICIENT = 5
    CAPACITY_SPAN_COEFFICIENT = 50     # OPTIMAL: Config 1
    DISTANCE_SPAN_COEFFICIENT = 30     # OPTIMAL: Config 1

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
    # Calibrage : la matrice étant désormais isotrope et exprimée en degrés de
    # latitude, un degré vaut 111 km. À 20 km/h en circulation urbaine :
    # 111 / 20 × 3600 ≈ 20 000 s par degré. L'ancienne valeur reposait sur une
    # moyenne de 85 km/degré, qui n'a plus lieu d'être une fois la longitude
    # ramenée à l'échelle de la latitude.
    #
    # L'ancienne valeur (600) était calée sur une zone de ±5° ; la conserver
    # avec la zone urbaine actuelle ramènerait les trajets à ~30 secondes.
    # ── Conversion distance → mètres ─────────────────────────────────────
    # Même approximation, exprimée en distance plutôt qu'en temps : ~85 km par
    # degré, soit 85 000 m. Ce facteur existe parce que le coût d'arc est un
    # entier : sans lui, `int()` reçoit des degrés, et une zone urbaine de
    # ±0,055° tient tout entière sous 1, donc chaque distance tombe à 0 et la
    # dimension Distance ne pèse plus rien dans l'objectif.
    DISTANCE_TO_METERS_FACTOR = 111000.0

    # Ce que coûte l'abandon d'un client, dans la même unité que le coût d'arc,
    # c'est-à-dire en mètres. 1 000 km : environ dix fois la tournée complète de
    # référence, donc abandonner reste toujours plus cher que le plus long des
    # détours, sans être interdit. Ce n'est pas un détail de réglage : tant que
    # les distances valaient 0, la pénalité pouvait valoir n'importe quoi ; dès
    # qu'elles pèsent, une pénalité laissée à 100 000 ne vaut plus que sept arcs
    # et le solveur se met à préférer laisser deux clients de côté.
    DROP_CUSTOMER_PENALTY_METERS = 1_000_000

    # Coût d'abandon d'un transfert entre coursiers, en mètres (même unité que
    # le coût d'arc). À 0, un rendez-vous doit se justifier uniquement par la
    # distance qu'il économise : le solveur ne le retient que s'il est rentable.
    # Valeur à calibrer expérimentalement, cf. `experiments/`.
    TRANSFER_PENALTY_METERS = 0

    # Coût fixe d'utilisation d'un véhicule, en mètres (même unité que le coût
    # d'arc). Il incite à ne pas ouvrir une tournée pour trois clients : sans
    # lui, répartir sur tous les véhicules est toujours gratuit. Valeur héritée
    # d'un réglage manuel, à calibrer, cf. `experiments/`.
    VEHICLE_FIXED_COST_METERS = 50

    DISTANCE_TO_TIME_FACTOR = 20000.0
    SERVICE_TIME_PER_UNIT = 60  # 60 seconds per demand unit for service time

    # Distance maximale d'un véhicule, en mètres. Sert aussi de coût sentinelle
    # sur les arcs entre deux points de rechargement, pour les rendre prohibitifs.
    VEHICLE_MAX_DISTANCE_METERS = 100_000

    # Horizon de la dimension temporelle, en secondes : borne haute des cumuls et
    # attente maximale autorisée à un nœud. Très large devant une journée de
    # livraison (86 400 s), donc non contraignante en pratique.
    TIME_HORIZON_SECONDS = 1_440_000

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


