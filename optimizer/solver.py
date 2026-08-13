# optimizer/solver.py
from functools import partial
from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2
from optimizer.config import Config


def setup_data_extensions(data):
    """
    Étend les données avec les nœuds additionnels pour OR-Tools.
    
    :param data: Dictionnaire de données du problème
    :return: Données étendues avec capacités des véhicules et nœuds
    """
    # Convert vehicle capacities to integers
    vehicle_capacities = [int(cap) for cap in data['vehicle_capacities']]
    
    # Set additional parameters
    data['time_per_demand_unit'] = 5
    data['vehicle_max_distance'] = 100000
    data['vehicle_max_time'] = 1440000

    # Identify reload group for depot and unload depots
    reload_group = [data['depot']]

    # Add unload depots for reloads at depot
    data['unload_depots'] = []
    current_num = len(data['locations'])
    max_vehicle_capacity = max(vehicle_capacities) if vehicle_capacities else 0
    
    for _ in range(Config.NUM_UNLOAD_DEPOTS):
        data['locations'].append(data['locations'][data['depot']])
        data['demands'].append(-max_vehicle_capacity)
        data['time_windows'].append((0, data['vehicle_max_time']))
        data['unload_depots'].append(current_num)
        reload_group.append(current_num)
        current_num += 1

    # Add deposit and pickup for each hub for transfers
    hub_capacity = 1
    data['hub_deposits'] = []
    data['hub_pickups'] = []
    hub_start = 1 + data['num_customers']
    hub_indices = range(hub_start, hub_start + data['num_hubs'])
    
    for h in hub_indices:
        deposit = current_num
        pickup = current_num + 1
        data['locations'].append(data['locations'][h])
        data['locations'].append(data['locations'][h])
        data['demands'].append(-hub_capacity)
        data['demands'].append(hub_capacity)
        data['time_windows'].append(data['time_windows'][h])
        data['time_windows'].append(data['time_windows'][h])
        data['hub_deposits'].append(deposit)
        data['hub_pickups'].append(pickup)
        current_num += 2

    # Add dummy nodes and dummy vehicles for each hub
    data['dummy_nodes'] = []
    num_real_vehicles = data['num_vehicles']

    for _ in range(data['num_hubs']):
        dummy = current_num
        data['locations'].append(data['locations'][data['depot']])
        data['demands'].append(0)
        data['time_windows'].append((0, data['vehicle_max_time']))
        data['dummy_nodes'].append(dummy)
        current_num += 1

    data['num_locations'] = len(data['locations'])
    data['num_real_vehicles'] = num_real_vehicles  # Store for later use in metrics
    data['num_vehicles'] = num_real_vehicles + data['num_hubs']

    # Extend vehicle capacities and max times for dummy vehicles
    vehicle_capacities += [0] * data['num_hubs']
    vehicle_max_times = [data['end_times'][v] - data['start_times'][v] for v in range(num_real_vehicles)]
    vehicle_max_times += [data['vehicle_max_time']] * data['num_hubs']

    return vehicle_capacities, vehicle_max_times, reload_group, hub_indices, num_real_vehicles


def create_base_node_mapping(data, hub_indices):
    """
    Crée la correspondance entre nœuds étendus et nœuds de base pour les matrices.
    
    :param data: Dictionnaire de données étendues
    :param hub_indices: Indices des hubs originaux
    :return: Liste de correspondance base_node
    """
    base_node = list(range(data['num_nodes']))

    for u in data['unload_depots']:
        base_node.append(data['depot'])

    # Dépôt et retrait d'un même hub sont **consécutifs** en numérotation :
    # `setup_data_extensions` les crée par paire (deposit = n, pickup = n + 1).
    # Les parcourir hub par hub est donc la seule façon de rester aligné sur les
    # numéros de nœuds. Les traiter en deux passes (tous les dépôts, puis tous
    # les retraits) décalait la correspondance dès le deuxième hub : le retrait
    # du hub 1 pointait vers le hub 2, et le dépôt du hub 2 vers le hub 1. Les
    # distances et les temps de transfert étaient alors calculés depuis la
    # mauvaise position. Sans effet à un seul hub, d'où la discrétion du défaut.
    for deposit, pickup, hub in zip(data['hub_deposits'], data['hub_pickups'], hub_indices):
        base_node.append(hub)  # dépôt
        base_node.append(hub)  # retrait

    for d in data['dummy_nodes']:
        base_node.append(data['depot'])

    return base_node


def create_evaluator_functions(data, base_node, reload_group):
    """
    Crée les fonctions d'évaluation pour les dimensions du routage.
    
    :param data: Dictionnaire de données
    :param base_node: Correspondance des nœuds
    :param reload_group: Groupe de rechargement
    :return: Fonctions d'évaluation distance, demande et temps
    """
    def get_distance(from_node, to_node):
        b_from = base_node[from_node]
        b_to = base_node[to_node]
        return int(data['distance_matrix'][b_from, b_to])

    def get_travel_time(from_node, to_node):
        # Calcul dynamique : distance * facteur de conversion
        b_from = base_node[from_node]
        b_to = base_node[to_node]
        distance = data['distance_matrix'][b_from, b_to]
        return int(distance * Config.DISTANCE_TO_TIME_FACTOR)

    def create_distance_evaluator(data):
        def distance_evaluator(manager, from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            base_dist = get_distance(from_node, to_node)
            if from_node in reload_group and to_node in reload_group:
                base_dist = data['vehicle_max_distance']
            extra_penalty = 0
            hub_nodes = data['hub_deposits'] + data['hub_pickups']
            if from_node in hub_nodes or to_node in hub_nodes:
                extra_penalty = 100  # Reduced from 500 to encourage rebalancing via hubs
            return base_dist + extra_penalty
        return distance_evaluator

    def create_demand_evaluator(data):
        def demand_evaluator(manager, from_index):
            from_node = manager.IndexToNode(from_index)
            return int(data['demands'][from_node])
        return demand_evaluator

    def service_time(data, node):
        # Utiliser la configuration centralisée pour le temps de service
        return abs(data['demands'][node]) * Config.SERVICE_TIME_PER_UNIT

    def create_time_evaluator(data):
        def time_evaluator(manager, from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(service_time(data, from_node) + get_travel_time(from_node, to_node))
        return time_evaluator

    return create_distance_evaluator, create_demand_evaluator, create_time_evaluator


def setup_routing_model(data, vehicle_capacities, vehicle_max_times):
    """
    Crée et configure le modèle de routage OR-Tools.
    
    :param data: Dictionnaire de données
    :param vehicle_capacities: Capacités des véhicules
    :param vehicle_max_times: Temps max des véhicules
    :return: Manager, routing model et fonctions d'évaluation
    """
    manager = pywrapcp.RoutingIndexManager(data['num_locations'], data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)
    
    # Créer les fonctions d'évaluation
    reload_group = [data['depot']] + data['unload_depots']
    hub_indices = range(1 + data['num_customers'], 1 + data['num_customers'] + data['num_hubs'])
    base_node = create_base_node_mapping(data, hub_indices)
    
    create_distance_evaluator, create_demand_evaluator, create_time_evaluator = create_evaluator_functions(
        data, base_node, reload_group
    )
    
    return manager, routing, create_distance_evaluator, create_demand_evaluator, create_time_evaluator


def add_routing_dimensions(routing, manager, data, vehicle_capacities, vehicle_max_times, 
                         create_distance_evaluator, create_demand_evaluator, create_time_evaluator):
    """
    Ajoute les dimensions de distance, capacité et temps au modèle de routage.
    
    :param routing: Modèle de routage
    :param manager: Gestionnaire d'indices
    :param data: Dictionnaire de données
    :param vehicle_capacities: Capacités des véhicules
    :param vehicle_max_times: Temps max des véhicules
    :param create_distance_evaluator: Fonction d'évaluation distance
    :param create_demand_evaluator: Fonction d'évaluation demande
    :param create_time_evaluator: Fonction d'évaluation temps
    :return: Dimensions de distance, capacité et temps
    """
    # Distance dimension
    distance_evaluator_index = routing.RegisterTransitCallback(partial(create_distance_evaluator(data), manager))
    distance = 'Distance'
    routing.AddDimension(distance_evaluator_index, 0, data['vehicle_max_distance'], True, distance)
    distance_dimension = routing.GetDimensionOrDie(distance)
    distance_dimension.SetGlobalSpanCostCoefficient(Config.DISTANCE_SPAN_COEFFICIENT)

    # Capacity dimension
    demand_evaluator_index = routing.RegisterUnaryTransitCallback(partial(create_demand_evaluator(data), manager))
    capacity = 'Capacity'
    max_slack_capacity = max(vehicle_capacities + [0])
    routing.AddDimensionWithVehicleCapacity(demand_evaluator_index, max_slack_capacity, vehicle_capacities, True, capacity)
    capacity_dimension = routing.GetDimensionOrDie(capacity)
    # REMOVED: SetGlobalSpanCostCoefficient on capacity (measures cumulative, not actual load)
    # capacity_dimension.SetGlobalSpanCostCoefficient(Config.CAPACITY_SPAN_COEFFICIENT)

    # Customer Count dimension - tracks ACTUAL number of customers delivered per vehicle
    def customer_counter_evaluator(manager, from_index):
        """Count only real customers (nodes 1 to num_customers), not hubs/depots/reloads"""
        node = manager.IndexToNode(from_index)
        # Return 1 if this is a real customer delivery
        return 1 if 1 <= node <= data['num_customers'] else 0

    customer_count_index = routing.RegisterUnaryTransitCallback(partial(customer_counter_evaluator, manager))
    customer_count = 'CustomerCount'
    routing.AddDimension(customer_count_index, 0, data['num_customers'], True, customer_count)
    customer_count_dimension = routing.GetDimensionOrDie(customer_count)
    # Apply SPAN penalty to ACTUAL customer count - this is the proper way to balance load
    customer_count_dimension.SetGlobalSpanCostCoefficient(Config.CAPACITY_SPAN_COEFFICIENT)

    # Time dimension
    time_evaluator_index = routing.RegisterTransitCallback(partial(create_time_evaluator(data), manager))
    time = 'Time'
    routing.AddDimensionWithVehicleCapacity(time_evaluator_index, data['vehicle_max_time'], vehicle_max_times, False, time)
    time_dimension = routing.GetDimensionOrDie(time)
    # Minimize makespan and balance route times to prevent extreme time differences
    time_dimension.SetGlobalSpanCostCoefficient(Config.TIME_SPAN_COEFFICIENT)

    return distance_dimension, capacity_dimension, time_dimension, distance_evaluator_index, time_evaluator_index


def configure_constraints_and_penalties(routing, manager, data, capacity_dimension, hub_indices):
    """
    Configure les contraintes et pénalités pour les différents types de nœuds.
    
    :param routing: Modèle de routage
    :param manager: Gestionnaire d'indices
    :param data: Dictionnaire de données
    :param capacity_dimension: Dimension de capacité
    :param hub_indices: Indices des hubs
    """
    # Set slacks and disjunctions for customers
    customer_start = 1
    customer_end = 1 + data['num_customers']
    for node in range(customer_start, customer_end):
        node_index = manager.NodeToIndex(node)
        capacity_dimension.SlackVar(node_index).SetValue(0)
        routing.AddDisjunction([node_index], 100000)

    # Unload depots
    for node in data['unload_depots']:
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], 0)

    # Hub nodes
    for node in hub_indices:
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], 500)

    # Hub deposits and pickups
    for node in data['hub_deposits'] + data['hub_pickups']:
        node_index = manager.NodeToIndex(node)
        capacity_dimension.SlackVar(node_index).SetValue(0)

    # Dummy nodes
    for node in data['dummy_nodes']:
        node_index = manager.NodeToIndex(node)
        routing.AddDisjunction([node_index], 100000)


def setup_time_constraints(routing, manager, data, time_dimension, num_real_vehicles):
    """
    Configure les contraintes temporelles et fenêtres de temps.

    - Clients: time windows optionnels avec pénalités (si TIME_WINDOWS_OPTIONAL=True)
    - Hubs: time windows absolus (contraintes dures)

    :param routing: Modèle de routage
    :param manager: Gestionnaire d'indices
    :param data: Dictionnaire de données
    :param time_dimension: Dimension temporelle
    :param num_real_vehicles: Nombre de véhicules réels
    """
    # Identify hub indices for special treatment
    hub_start = 1 + data['num_customers']
    hub_end = hub_start + data['num_hubs']
    hub_indices = set(range(hub_start, hub_end))
    hub_deposits = set(data['hub_deposits'])
    hub_pickups = set(data['hub_pickups'])
    hub_related = hub_indices | hub_deposits | hub_pickups

    # Add time windows
    for location_idx, window in enumerate(data['time_windows']):
        if location_idx == data['depot']:
            continue

        index = manager.NodeToIndex(location_idx)

        # Check if this is a hub-related node
        is_hub_node = location_idx in hub_related

        if is_hub_node:
            # Hubs: hard time window constraints (absolute)
            time_dimension.CumulVar(index).SetRange(int(window[0]), int(window[1]))
            routing.AddToAssignment(time_dimension.SlackVar(index))
        else:
            # Customers: optional time windows with penalties
            if Config.TIME_WINDOWS_OPTIONAL:
                # Allow wide range instead of hard constraints
                time_dimension.CumulVar(index).SetRange(0, int(data['vehicle_max_time']))
                slack_var = time_dimension.SlackVar(index)
                routing.AddToAssignment(slack_var)
                # Apply penalty coefficient for time window violations (slack penalty)
                # Using vehicle-based penalty since node-based isn't available
                for vehicle_id in range(data['num_vehicles']):
                    time_dimension.SetSlackCostCoefficientForVehicle(
                        int(Config.TIME_WINDOW_VIOLATION_PENALTY), vehicle_id
                    )
            else:
                # Original behavior: hard constraints for all
                time_dimension.CumulVar(index).SetRange(int(window[0]), int(window[1]))
                routing.AddToAssignment(time_dimension.SlackVar(index))

    # Set vehicle start and end times
    penalty_slack = 100
    for vehicle_id in range(num_real_vehicles):
        index = routing.Start(vehicle_id)
        time_dimension.CumulVar(index).SetValue(int(data['start_times'][vehicle_id]))
        routing.AddToAssignment(time_dimension.SlackVar(index))
        time_dimension.SetSlackCostCoefficientForVehicle(penalty_slack, vehicle_id)

        end_index = routing.End(vehicle_id)
        time_dimension.CumulVar(end_index).SetMax(int(data['end_times'][vehicle_id]))

    # For dummy vehicles
    for i in range(data['num_hubs']):
        vehicle_id = num_real_vehicles + i
        index = routing.Start(vehicle_id)
        time_dimension.CumulVar(index).SetRange(0, data['vehicle_max_time'])
        routing.AddToAssignment(time_dimension.SlackVar(index))
        end_index = routing.End(vehicle_id)
        time_dimension.CumulVar(end_index).SetValue(data['vehicle_max_time'])


def set_allowed_vehicles(routing, vehicles, index):
    """
    Restreint les véhicules autorisés à desservir un nœud.

    Remplace `RoutingModel.SetAllowedVehiclesForIndex`, cassé côté Python depuis
    OR-Tools 9.15 : la signature C++ est passée de `const std::vector<int>&` à
    `absl::Span<const int>` sans typemap SWIG correspondant, si bien que tout
    appel lève `TypeError: ... argument 2 of type 'absl::Span< int const >'`,
    quel que soit le type passé (liste, tuple, ndarray).
    Suivi amont : https://github.com/google/or-tools/issues/4982 (jalon 9.16).

    On contraint donc directement la variable de véhicule du nœud, ce que
    l'API native fait en interne.

    La valeur -1 — sentinelle « nœud non desservi » — est réinjectée lorsqu'elle
    appartient déjà au domaine. Sans cela, les `AddDisjunction` posées sur chaque
    nœud deviendraient inopérantes : le solveur perdrait le droit d'abandonner un
    client contre pénalité, ce qui peut rendre le modèle infaisable.

    :param routing: Modèle de routage
    :param vehicles: Indices des véhicules autorisés
    :param index: Index solveur du nœud (issu de manager.NodeToIndex)
    """
    vehicle_var = routing.VehicleVar(index)
    allowed = [int(v) for v in vehicles]
    if vehicle_var.Contains(-1):
        allowed.append(-1)
    vehicle_var.SetValues(allowed)


def setup_vehicle_restrictions(routing, manager, data, num_real_vehicles):
    """
    Configure les restrictions d'affectation des véhicules aux nœuds.

    :param routing: Modèle de routage
    :param manager: Gestionnaire d'indices
    :param data: Dictionnaire de données
    :param num_real_vehicles: Nombre de véhicules réels
    """
    real_vehicles = list(range(num_real_vehicles))
    for node in range(data['num_locations']):
        node_index = manager.NodeToIndex(node)
        if node in data['dummy_nodes']:
            dummy_i = data['dummy_nodes'].index(node)
            dummy_v = num_real_vehicles + dummy_i
            set_allowed_vehicles(routing, [dummy_v], node_index)
        else:
            set_allowed_vehicles(routing, real_vehicles, node_index)


def add_hub_constraints(routing, manager, data, time_dimension, capacity_dimension):
    """
    Ajoute les contraintes spécifiques aux hubs pour les transferts.
    
    :param routing: Modèle de routage
    :param manager: Gestionnaire d'indices
    :param data: Dictionnaire de données
    :param time_dimension: Dimension temporelle
    :param capacity_dimension: Dimension de capacité
    """
    for i in range(data['num_hubs']):
        deposit = data['hub_deposits'][i]
        pickup = data['hub_pickups'][i]
        dummy = data['dummy_nodes'][i]
        deposit_index = manager.NodeToIndex(deposit)
        pickup_index = manager.NodeToIndex(pickup)
        dummy_index = manager.NodeToIndex(dummy)

        # Time constraint
        routing.solver().Add(time_dimension.CumulVar(deposit_index) <= time_dimension.CumulVar(pickup_index))

        # Different vehicles
        routing.solver().Add(routing.VehicleVar(deposit_index) != routing.VehicleVar(pickup_index))

        # Capacity constraint
        routing.solver().Add(
            capacity_dimension.CumulVar(deposit_index) + data['demands'][deposit] ==
            capacity_dimension.CumulVar(pickup_index) - data['demands'][pickup]
        )

        # Dummy constraints
        dummy_time = time_dimension.CumulVar(dummy_index)
        routing.solver().Add(time_dimension.CumulVar(deposit_index) <= dummy_time)
        routing.solver().Add(dummy_time <= time_dimension.CumulVar(pickup_index))


def configure_search_parameters(data):
    """
    Configure les paramètres de recherche pour le solver.
    
    :param data: Dictionnaire de données
    :return: Paramètres de recherche configurés
    """
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    # Use PARALLEL_CHEAPEST_INSERTION for better initial vehicle balance
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    
    time_limit = data.get('time_limit', Config.TIME_TO_SOLVE)
    search_parameters.time_limit.FromSeconds(time_limit)
    
    return search_parameters


def solve_vrp(data):
    """
    Fonction principale pour résoudre le VRP.
    
    :param data: Dictionnaire de données du problème
    :return: Manager, routing model et solution
    """
    # 1. Étendre les données
    vehicle_capacities, vehicle_max_times, reload_group, hub_indices, num_real_vehicles = setup_data_extensions(data)
    
    # 2. Créer le modèle de routage
    manager, routing, create_distance_evaluator, create_demand_evaluator, create_time_evaluator = setup_routing_model(
        data, vehicle_capacities, vehicle_max_times
    )
    
    # 3. Ajouter les dimensions
    distance_dimension, capacity_dimension, time_dimension, distance_evaluator_index, time_evaluator_index = add_routing_dimensions(
        routing, manager, data, vehicle_capacities, vehicle_max_times,
        create_distance_evaluator, create_demand_evaluator, create_time_evaluator
    )
    
    # 4. Configurer les contraintes et pénalités
    configure_constraints_and_penalties(routing, manager, data, capacity_dimension, hub_indices)
    
    # 5. Configurer les contraintes temporelles
    setup_time_constraints(routing, manager, data, time_dimension, num_real_vehicles)
    
    # 6. Configurer les restrictions de véhicules
    setup_vehicle_restrictions(routing, manager, data, num_real_vehicles)
    
    # 7. Ajouter les contraintes de hubs
    add_hub_constraints(routing, manager, data, time_dimension, capacity_dimension)
    
    # 8. Définir la fonction objective
    # Optimiser la DISTANCE avec pénalités pour équilibrer temps et charges
    # Les coefficients SPAN forcent l'équilibrage sans changer l'objectif principal
    routing.SetArcCostEvaluatorOfAllVehicles(distance_evaluator_index)

    # Add fixed cost per vehicle to incentivize balanced usage
    routing.SetFixedCostOfAllVehicles(50)  # OPTIMAL: Light incentive for vehicle balance

    # 9. Configurer les paramètres de recherche
    search_parameters = configure_search_parameters(data)
    
    # 10. Résoudre
    solution = routing.SolveWithParameters(search_parameters)

    return manager, routing, solution


def solve_vrp_with_optimal_hubs(data):
    """
    Résout le VRP deux fois (avec et sans hubs) et retourne la meilleure solution
    basée sur le temps total de livraison (somme des temps de tous les véhicules).

    :param data: Dictionnaire de données du problème
    :return: Tuple (manager, routing, solution, results, hubs_used, data_used)
             - hubs_used: True si la solution avec hubs a été choisie, False sinon
             - data_used: le dictionnaire de données correspondant EXACTEMENT à la
               solution retenue.

    Pourquoi `data_used` est renvoyé : `solve_vrp` mute son entrée
    (`setup_data_extensions` ajoute les nœuds de dépôt/retrait des hubs, les
    nœuds fictifs, et porte `num_vehicles` à `num_réels + num_hubs`). Les deux
    résolutions travaillent donc sur deux états de données différents. Sans ce
    retour, l'appelant devait reconstruire l'état à la main — reconstruction
    incomplète qui laissait `num_vehicles` gonflé et faisait planter la
    visualisation avec un IndexError sur les routes.
    """
    from optimizer.postprocessor import get_results
    import copy

    print("\n🔍 Comparaison avec/sans hubs pour optimiser le temps total de livraison...")

    # ===== SOLUTION SANS HUBS =====
    print("\n📊 Résolution SANS hubs...")
    data_no_hubs = copy.deepcopy(data)
    data_no_hubs['num_hubs'] = 0
    data_no_hubs['hubs'] = []

    manager_no_hubs, routing_no_hubs, solution_no_hubs = solve_vrp(data_no_hubs)

    if solution_no_hubs is None:
        print("❌ Aucune solution trouvée sans hubs")
        total_time_no_hubs = float('inf')
        results_no_hubs = None
    else:
        results_no_hubs = get_results(data_no_hubs, manager_no_hubs, routing_no_hubs, solution_no_hubs)
        total_time_no_hubs = results_no_hubs['indicators']['total_time_all_vehicles']
        print(f"✅ Solution sans hubs trouvée - Temps total: {format_time_display(total_time_no_hubs)}")

    # ===== SOLUTION AVEC HUBS =====
    print("\n📊 Résolution AVEC hubs...")
    manager_with_hubs, routing_with_hubs, solution_with_hubs = solve_vrp(data)

    if solution_with_hubs is None:
        print("❌ Aucune solution trouvée avec hubs")
        total_time_with_hubs = float('inf')
        results_with_hubs = None
    else:
        results_with_hubs = get_results(data, manager_with_hubs, routing_with_hubs, solution_with_hubs)
        total_time_with_hubs = results_with_hubs['indicators']['total_time_all_vehicles']
        print(f"✅ Solution avec hubs trouvée - Temps total: {format_time_display(total_time_with_hubs)}")

    # ===== COMPARAISON ET CHOIX =====
    print("\n" + "="*80)
    print("🎯 COMPARAISON DES SOLUTIONS")
    print("="*80)
    print(f"   Sans hubs : {format_time_display(total_time_no_hubs)}")
    print(f"   Avec hubs : {format_time_display(total_time_with_hubs)}")

    if total_time_with_hubs < total_time_no_hubs:
        time_saved = total_time_no_hubs - total_time_with_hubs
        print(f"\n   ✅ Solution AVEC hubs retenue (gain : {format_time_display(time_saved)})")
        print("="*80 + "\n")
        return manager_with_hubs, routing_with_hubs, solution_with_hubs, results_with_hubs, True, data
    else:
        time_lost = total_time_with_hubs - total_time_no_hubs
        if time_lost > 0:
            print(f"\n   ✅ Solution SANS hubs retenue (les hubs ajoutent {format_time_display(time_lost)})")
        else:
            print(f"\n   ✅ Solution SANS hubs retenue (temps équivalent)")
        print("="*80 + "\n")
        return manager_no_hubs, routing_no_hubs, solution_no_hubs, results_no_hubs, False, data_no_hubs


def format_time_display(seconds):
    """Formate le temps en secondes pour un affichage lisible"""
    if seconds == float('inf'):
        return "N/A"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"