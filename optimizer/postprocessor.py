# optimizer/postprocessor.py
from typing import Any

from ortools.constraint_solver import pywrapcp

from optimizer.config import Config


# Codes couleurs ANSI
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
    # Couleurs de texte
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    
    # Couleurs de fond
    BG_RED = '\033[101m'
    BG_GREEN = '\033[102m'
    BG_YELLOW = '\033[103m'
    BG_BLUE = '\033[104m'
    BG_MAGENTA = '\033[105m'
    BG_CYAN = '\033[106m'


def format_time(seconds):
    """Convertit les secondes en format lisible (HH:MM:SS)"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:.0f}m{secs:.0f}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:.0f}h{minutes:.0f}m{secs:.0f}s"


def compute_load_imbalance(final_loads):
    """
    Mesure le déséquilibre de charge entre véhicules : l'étendue relative
    (max - min) rapportée à la charge moyenne, exprimée en pourcentage.

    - 0 %   : tous les véhicules terminent avec la même charge (équilibre parfait)
    - 100 % : l'écart entre le plus et le moins chargé vaut la charge moyenne

    L'implémentation précédente calculait `max / min * 100`. Elle souffrait de
    trois défauts :
      1. un équilibre parfait sortait à 100 % au lieu de 0 % ;
      2. c'était un ratio, pas la « différence relative » annoncée en commentaire ;
      3. surtout, son garde-fou anti-division-par-zéro renvoyait 0 dès qu'un
         véhicule finissait à vide — soit le score « parfaitement équilibré »
         attribué au cas le plus déséquilibré qui soit, et affiché en vert.

    :param final_loads: Charge finale de chaque véhicule
    :return: Déséquilibre en pourcentage, arrondi à 2 décimales
    """
    if not final_loads:
        return 0.0
    mean_load = sum(final_loads) / len(final_loads)
    if mean_load <= 0:
        # Aucune charge transportée : il n'y a rien à déséquilibrer.
        return 0.0
    return round((max(final_loads) - min(final_loads)) / mean_load * 100, 2)


def display_detailed_results(data, routes, estimated_times, current_loads, remaining_charges,
                           total_distance, total_tardiness, activated_hubs, load_imbalance_percentage, 
                           final_loads, calc_time):
    """
    Affiche les résultats détaillés de la solution VRP avec des couleurs.
    
    :param data: Dictionnaire de données du problème
    :param routes: Routes de chaque véhicule
    :param estimated_times: Temps d'arrivée à chaque nœud
    :param current_loads: Charges actuelles des véhicules
    :param remaining_charges: Capacités restantes des véhicules
    :param total_distance: Distance totale parcourue
    :param total_tardiness: Retard total en secondes
    :param activated_hubs: Set des hubs activés
    :param load_imbalance_percentage: Pourcentage de déséquilibre de charge
    :param final_loads: Charges finales de chaque véhicule
    :param calc_time: Temps de calcul
    """
    
    # Affichage détaillé des résultats par véhicule
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}")
    print("                    RÉSULTATS DÉTAILLÉS PAR VÉHICULE")
    print(f"{'='*80}{Colors.RESET}")
    
    for v in range(data['num_vehicles']):
        # Couleur différente pour chaque véhicule
        vehicle_color = [Colors.GREEN, Colors.YELLOW, Colors.MAGENTA, Colors.BLUE, Colors.RED][v % 5]
        
        print(f"\n{vehicle_color}{Colors.BOLD}🚛 VÉHICULE {v + 1}{Colors.RESET}")
        print(f"{vehicle_color}{'-' * 50}{Colors.RESET}")
        
        # Informations générales du véhicule
        vehicle_capacity = data['vehicle_capacities'][v] if v < len(data['vehicle_capacities']) else 0
        route = routes[v]
        times = estimated_times[v]
        loads = current_loads[v]
        remaining = remaining_charges[v]
        
        print(f"   {Colors.CYAN}Capacité maximale     :{Colors.RESET} {vehicle_capacity}")
        print(f"   {Colors.CYAN}Nombre d'arrêts       :{Colors.RESET} {len(route)}")
        print(f"   {Colors.CYAN}Route                 :{Colors.RESET} {' → '.join(map(str, route))}")
        
        # Détail étape par étape
        print(f"\n   {Colors.BOLD}{Colors.BLUE}📍 DÉTAIL DE LA TOURNÉE:{Colors.RESET}")
        for i, (node, time, load, _remain) in enumerate(zip(route, times, loads, remaining, strict=False)):
            if node == 0:
                node_type = f"{Colors.RED}🏠 DÉPÔT{Colors.RESET}"
            elif 1 <= node <= data['num_customers']:
                node_type = f"{Colors.GREEN}👤 Client {node}{Colors.RESET}"
                data['demands'][node]
                tw_start, tw_end = data['time_windows'][node]
                print(f"      {Colors.WHITE}Étape {i+1:2d}:{Colors.RESET} {node_type:<25} | {Colors.YELLOW}Arrivée: {format_time(time):<8}{Colors.RESET} | {Colors.CYAN}Charge: {load:>2}/{vehicle_capacity}{Colors.RESET} | {Colors.MAGENTA}Node: {node}{Colors.RESET}")
                continue
            elif data['num_customers'] + Config.NUM_UNLOAD_DEPOTS > node > data['num_customers']:
                node_type = f"{Colors.MAGENTA}🔄 DÉPÔT {node - data['num_customers']}{Colors.RESET}"

            elif node >= data['num_customers'] + Config.NUM_UNLOAD_DEPOTS:
                node_type = f"{Colors.MAGENTA}🌐 HUB   {node - data['num_customers']}{Colors.RESET}"
            else:
                node_type = f"{Colors.WHITE}? Nœud {node}{Colors.RESET}"
            
            print(f"      {Colors.WHITE}Étape {i+1:2d}:{Colors.RESET} {node_type:<25} | {Colors.YELLOW}Arrivée: {format_time(time):<8}{Colors.RESET} | {Colors.CYAN}Charge: {load:>2}/{vehicle_capacity}{Colors.RESET} | {Colors.MAGENTA}Node: {node}{Colors.RESET}")
        
        # Statistiques du véhicule
        total_delivery = loads[0] - loads[-1] if loads else 0
        duration = times[-1] - times[0] if len(times) >= 2 else 0
        print(f"\n   {Colors.BOLD}{Colors.GREEN}📊 STATISTIQUES:{Colors.RESET}")
        print(f"      {Colors.CYAN}Total livré           :{Colors.RESET} {Colors.GREEN}{total_delivery}{Colors.RESET} unités")
        print(f"      {Colors.CYAN}Durée totale          :{Colors.RESET} {Colors.YELLOW}{format_time(duration)}{Colors.RESET}")
        print(f"      {Colors.CYAN}Charge finale         :{Colors.RESET} {Colors.BLUE}{loads[-1] if loads else 0}{Colors.RESET}")
        
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}")
    print("                       INFORMATIONS GÉNÉRALES")
    print(f"{'='*80}{Colors.RESET}")

    # Affichage des informations générales
    print(f"\n{Colors.BOLD}{Colors.RED}📈 INDICATEURS GLOBAUX:{Colors.RESET}")
    print(f"   {Colors.CYAN}Distance totale           :{Colors.RESET} {Colors.YELLOW}{total_distance}{Colors.RESET} unités")
    print(f"   {Colors.CYAN}Retard total              :{Colors.RESET} {Colors.RED if total_tardiness > 0 else Colors.GREEN}{format_time(total_tardiness)}{Colors.RESET}")
    print(f"   {Colors.CYAN}Hubs activés              :{Colors.RESET} {Colors.MAGENTA}{len(activated_hubs)}{Colors.RESET}")
    # Seuils calés sur l'étendue relative : 0 % = équilibre parfait.
    imbalance_color = (Colors.RED if load_imbalance_percentage > 60
                       else Colors.YELLOW if load_imbalance_percentage > 30
                       else Colors.GREEN)
    print(f"   {Colors.CYAN}Déséquilibre de charge    :{Colors.RESET} {imbalance_color}{load_imbalance_percentage}%{Colors.RESET}")
    print(f"   {Colors.CYAN}Temps de calcul           :{Colors.RESET} {Colors.BLUE}{calc_time}s{Colors.RESET}")
    
    print(f"\n{Colors.BOLD}{Colors.BLUE}📊 RÉPARTITION DES CHARGES FINALES:{Colors.RESET}")
    for v in range(data['num_vehicles']):
        final_load = final_loads[v] if v < len(final_loads) else 0
        vehicle_capacity = data['vehicle_capacities'][v] if v < len(data['vehicle_capacities']) else 0
        percentage = final_load/vehicle_capacity*100 if vehicle_capacity > 0 else 0
        
        # Couleur basée sur le pourcentage d'utilisation
        if percentage > 80:
            color = Colors.RED
        elif percentage > 60:
            color = Colors.YELLOW
        elif percentage > 30:
            color = Colors.GREEN
        else:
            color = Colors.BLUE
            
        vehicle_color = [Colors.GREEN, Colors.YELLOW, Colors.MAGENTA, Colors.BLUE, Colors.RED][v % 5]
        print(f"   {vehicle_color}Véhicule {v+1:2d}{Colors.RESET}            : {color}{final_load:>2}/{vehicle_capacity} ({percentage:.1f}%){Colors.RESET}")
    
    if data['num_hubs'] > 0:
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}🔄 HUBS UTILISÉS:{Colors.RESET}")
        if activated_hubs:
            for hub_id in sorted(activated_hubs):
                print(f"   {Colors.GREEN}Hub {hub_id + 1}{Colors.RESET}")
        else:
            print(f"   {Colors.YELLOW}Aucun hub utilisé{Colors.RESET}")
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")


def get_activated_hubs(data: dict[str, Any], manager: pywrapcp.RoutingIndexManager, routing: pywrapcp.RoutingModel, solution: pywrapcp.Assignment) -> set:
    """
    Détecte les hubs où un transfert entre coursiers a réellement eu lieu.

    Un hub compte comme activé lorsque **son dépôt et son retrait sont tous
    deux desservis** : c'est la définition d'un échange de colis.

    Le simple passage par le nœud de hub d'origine ne compte pas. Ce nœud porte
    une demande nulle et une disjonction bon marché : le solveur le traverse
    parfois comme un point de passage ordinaire, sans rien y déposer. L'ancienne
    règle — « activé si le nœud du hub est visité OU si l'un des deux nœuds de
    la paire l'est » — comptait donc des survols comme des transferts, et
    faisait passer pour un rendez-vous ce qui n'était qu'un détour. Les survols
    restent rapportés séparément, sous `hubFlybys`.

    La disjonction « l'un OU l'autre » était de surcroît impossible depuis que
    les deux activations sont liées : c'est les deux nœuds ou aucun.
    
    :param data: Dictionnaire de données du problème
    :param manager: Gestionnaire de routage OR-Tools
    :param routing: Modèle de routage OR-Tools
    :param solution: Solution d'affectation OR-Tools
    :return: Set contenant les indices des hubs activés
    """
    activated_hubs = set()
    deposits = data.get('hub_deposits') or []
    pickups = data.get('hub_pickups') or []

    for h in range(data['num_hubs']):
        if h >= len(deposits) or h >= len(pickups):
            continue
        depose = solution.Value(routing.ActiveVar(manager.NodeToIndex(deposits[h])))
        collecte = solution.Value(routing.ActiveVar(manager.NodeToIndex(pickups[h])))
        if depose == 1 and collecte == 1:
            activated_hubs.add(h)

    return activated_hubs


def get_total_tardiness(manager, routing, solution, data, time_dimension):
    # Calcul du retard total (tardiness) - temps de livraison après la fenêtre de temps
    total_tardiness = 0
    for v in range(data['num_vehicles']):
        index = routing.Start(v)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            # Vérifier seulement les clients (pas le dépôt ni les hubs)
            if 1 <= node <= data['num_customers']:
                time = solution.Value(time_dimension.CumulVar(index))  # Temps d'arrivée
                _, tw_end = data['time_windows'][node]  # Fin de la fenêtre de temps
                # Ajouter le retard si arrivée après la fenêtre
                total_tardiness += max(0, time - tw_end)
            index = solution.Value(routing.NextVar(index))
    return total_tardiness


def get_total_distance(manager, routing, solution, data):
    """    
    Calcule la distance totale parcourue par tous les véhicules dans la solution.
    
    Cette fonction parcourt chaque véhicule et additionne les coûts des arcs
    (distances) entre chaque paire de nœuds consécutifs dans leur route.

    :param manager: Gestionnaire de routage OR-Tools
    :param routing: Modèle de routage OR-Tools
    :param solution: Solution d'affectation OR-Tools
    :param data: Dictionnaire de données du problème
    :return: Distance totale parcourue par tous les véhicules
    """
    total_distance = 0
    
    # Parcourir chaque véhicule
    for vehicle_id in range(data['num_vehicles']):
        index = routing.Start(vehicle_id)  # Commencer au point de départ
        
        # Parcourir toute la route du véhicule
        while not routing.IsEnd(index):
            next_index = solution.Value(routing.NextVar(index))  # Nœud suivant
            # Ajouter le coût de l'arc (distance) entre le nœud actuel et le suivant
            total_distance += routing.GetArcCostForVehicle(index, next_index, vehicle_id)
            index = next_index
            
    return total_distance

def get_results(data: dict[str, Any], manager: pywrapcp.RoutingIndexManager, routing: pywrapcp.RoutingModel, solution: pywrapcp.Assignment, verbose: bool = True) -> dict[str, Any]:
    """
    Extracts results from solution.

    :param data: Data dictionary.
    :param manager: Routing manager.
    :param routing: Routing model.
    :param solution: Solution assignment.
    :param verbose: Affiche le rapport détaillé sur la sortie standard. Vrai par
        défaut, pour l'exécution en ligne de commande. Un appelant serveur
        (`optimizer.scenario`) le met à faux : le rapport fait une centaine de
        lignes par résolution, et polluerait ses journaux.
    :return: Dictionary with results.
    """
    if solution is None:
        return {'error': 'No solution found'}

    time_dimension = routing.GetDimensionOrDie('Time')
    capacity_dimension = routing.GetDimensionOrDie('Capacity')

    # Extraction des routes, temps et charges pour chaque véhicule
    routes = []
    estimated_times = []
    remaining_charges = []  # Capacité restante = capacité totale - charge cumulée transportée
    current_loads = []  # Initialize current_loads list

    # Dictionnaire structuré des indices pour une organisation claire
    {
        'vehicles': {
            'real': list(range(Config.NUM_VEHICLES)),
            'dummy': list(range(Config.NUM_VEHICLES, Config.NUM_VEHICLES + Config.NUM_HUBS))
        },
        'nodes': {
            'depot': 0,
            'customers': list(range(1, Config.NUM_CUSTOMERS + 1)),
            'unload_depots': list(range(Config.NUM_CUSTOMERS + 1, Config.NUM_CUSTOMERS + Config.NUM_UNLOAD_DEPOTS + 1)),
            'hubs': list(range(Config.NUM_CUSTOMERS + Config.NUM_UNLOAD_DEPOTS + 1, Config.NUM_CUSTOMERS + Config.NUM_UNLOAD_DEPOTS + Config.NUM_HUBS + 1))
        }
    }

    for v in range(data['num_vehicles']):
        # Commencer au point de départ du véhicule
        index = routing.Start(v)
        route = []  # Séquence des nœuds visités
        times = []  # Temps d'arrivée à chaque nœud
        loads = []  # Charge cumulée transportée à chaque nœud

        # Vérifier si l'index du véhicule existe dans vehicle_capacities
        if v < len(data['vehicle_capacities']):
            vehicle_capacity = data['vehicle_capacities'][v]
        else:
            vehicle_capacity = 0  # Véhicule dummy, capacité = 0

        # Parcourir toute la route du véhicule
        # Calculer la charge en ordre décroissant: commence à capacity et diminue quand on livre
        current_charge = vehicle_capacity  # Commence plein

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)  # Convertir l'index en numéro de nœud
            route.append(node)
            # Temps d'arrivée au nœud (dimension temporelle)
            times.append(solution.Value(time_dimension.CumulVar(index)))

            # Mettre à jour la charge basée sur la demande du nœud:
            # - Les clients réduisent la charge (demand > 0)
            # - Les hub pickups augmentent la charge (demand > 0)
            # - Les hub deposits réduisent la charge (demand < 0)
            # - Les unload depots font recharger complètement (demand < 0)
            node_demand = data['demands'][node]

            # Identify node type using the hub_deposits and hub_pickups lists
            is_hub_deposit = node in data.get('hub_deposits', [])
            is_hub_pickup = node in data.get('hub_pickups', [])
            is_unload_depot = node in data.get('unload_depots', [])

            if is_hub_pickup and node_demand > 0:
                # At hub pickup: LOAD a package from transfer (increase charge)
                current_charge += node_demand
            elif node_demand > 0:
                # At customer: DELIVER a package (decrease charge)
                current_charge -= node_demand
            elif is_hub_deposit and node_demand < 0:
                # At hub deposit: UNLOAD a package for transfer (decrease charge)
                current_charge -= abs(node_demand)
            elif is_unload_depot and node_demand < 0:
                # At unload depot: full recharge
                current_charge = vehicle_capacity
            elif node == 0:
                # At main depot: no charge change
                pass

            # Enregistrer la charge APRÈS avoir traité le nœud
            load_value = max(0, min(current_charge, vehicle_capacity))
            loads.append(load_value)

            index = solution.Value(routing.NextVar(index))  # Passer au nœud suivant

        # Ajouter le nœud final (retour au dépôt)
        final_node = manager.IndexToNode(index)
        route.append(final_node)
        times.append(solution.Value(time_dimension.CumulVar(index)))
        loads.append(max(0, min(current_charge, vehicle_capacity)))  # Charge au retour
        
        # Calculer la capacité restante à chaque étape
        # Capacité restante = Capacité totale du véhicule - Charge cumulée transportée
        cap = data['vehicle_capacities'][v] if v < len(data['vehicle_capacities']) else 0  # Véhicule factice
        remaining_charges.append([cap - charge for charge in loads])
        current_loads.append(loads)  # Store current loads for each vehicle

        # Sauvegarder les données du véhicule
        routes.append(route)
        estimated_times.append(times)

    # Calcul de la distance totale de la solution
    total_distance = get_total_distance(manager, routing, solution, data)
    
    # Calcul du retard total (tardiness) 
    total_tardiness = get_total_tardiness(manager, routing, solution, data, time_dimension)

    # Détection des hubs activés (utilisés dans la solution)
    activated_hubs = get_activated_hubs(data, manager, routing, solution)
    
    # Calcul de la répartition de charge finale entre véhicules
    load_repartition = [solution.Value(capacity_dimension.CumulVar(routing.End(v))) for v in range(data['num_vehicles'])]
    
    final_loads = [vehicle_loads[-1] if vehicle_loads else 0 for vehicle_loads in current_loads]
    load_imbalance_percentage = compute_load_imbalance(final_loads)

    # Temps de calcul (pour l'instant fixé à 0, pourrait être mesuré)
    calc_time = 0

    # Calcul du temps total de livraison (somme des temps de tous les véhicules)
    # Pour chaque véhicule, le temps de livraison est le dernier temps enregistré (retour au dépôt)
    # IMPORTANT: Ne compter que les véhicules réels, pas les véhicules dummy créés pour les hubs
    num_real_vehicles = data.get('num_real_vehicles', Config.NUM_VEHICLES)
    total_time_all_vehicles = sum(
        times[-1] if times else 0
        for times in estimated_times[:num_real_vehicles]
    )

    # Affichage des résultats détaillés
    if verbose:
        display_detailed_results(data, routes, estimated_times, current_loads, remaining_charges,
                               total_distance, total_tardiness, activated_hubs, load_imbalance_percentage,
                               final_loads, calc_time)

    # Retourner tous les résultats structurés
    return {
        'per_livreur': {
            'routes': routes,                    # Routes de chaque véhicule
            'estimated_times': estimated_times,  # Temps d'arrivée à chaque nœud
            'current_loads': current_loads,                  # Charge finale de chaque véhicule
            'remaining_charges': remaining_charges # Capacité restante à chaque étape
        },
        'indicators': {
            'total_distance': total_distance,           # Distance totale parcourue
            'total_tardiness_minutes': total_tardiness, # Retard total en secondes
            'activated_hubs': len(activated_hubs),      # Nombre de hubs utilisés
            'load_repartition': load_repartition,          # charge cumulée en fin de tournée, par véhicule
            'load_imbalance_percentage': load_imbalance_percentage,
            'calc_time': calc_time,        # Temps de calcul
            'total_time_all_vehicles': total_time_all_vehicles  # Somme des temps de tous les véhicules (en secondes)
        }
    }