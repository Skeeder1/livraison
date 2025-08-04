# optimizer/postprocessor.py
from ortools.constraint_solver import pywrapcp
from typing import Dict, Any

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

def get_results(data: Dict[str, Any], manager: pywrapcp.RoutingIndexManager, routing: pywrapcp.RoutingModel, solution: pywrapcp.Assignment) -> Dict[str, Any]:
    """
    Extracts results from solution.

    :param data: Data dictionary.
    :param manager: Routing manager.
    :param routing: Routing model.
    :param solution: Solution assignment.
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

    for v in range(data['num_vehicles']):
        # Commencer au point de départ du véhicule
        index = routing.Start(v)
        route = []  # Séquence des nœuds visités
        times = []  # Temps d'arrivée à chaque nœud
        loads = []  # Charge cumulée transportée à chaque nœud
        
        # Parcourir toute la route du véhicule
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)  # Convertir l'index en numéro de nœud
            route.append(node)
            # Temps d'arrivée au nœud (dimension temporelle)
            times.append(solution.Value(time_dimension.CumulVar(index)))
            # Charge cumulée transportée au nœud (dimension capacité)
            # Dans OR-Tools, CumulVar représente la charge totale collectée/transportée
            load_value = solution.Value(capacity_dimension.CumulVar(index))
            loads.append(load_value)
            
            # Debug pour comprendre les transferts de hub
            if node >= data['num_customers'] + 1:  # Nœud hub ou dérivé
                demand = data['demands'][node]
                print(f"DEBUG HUB: Vehicle {v}, node {node}, demand={demand}, load_value={load_value}")
                
            index = solution.Value(routing.NextVar(index))  # Passer au nœud suivant
        
        # Ajouter le nœud final (retour au dépôt)
        route.append(manager.IndexToNode(index))
        times.append(solution.Value(time_dimension.CumulVar(index)))
        loads.append(solution.Value(capacity_dimension.CumulVar(index)))
        
        # Sauvegarder les données du véhicule
        routes.append(route)
        estimated_times.append(times)
        
        # Calculer la capacité restante à chaque étape
        # Capacité restante = Capacité totale du véhicule - Charge cumulée transportée
        cap = data['vehicle_capacities'][v] if v < len(data['vehicle_capacities']) else 0
        remaining_charges.append([cap - l for l in loads])

    # Calcul de la distance totale de la solution
    total_distance = get_total_distance(manager, routing, solution, data)
    
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

    # Détection des hubs activés (utilisés dans la solution)
    activated_hubs = set()
    hub_start = 1 + data['num_customers']  # Premier index des hubs
    
    for h in range(data['num_hubs']):
        activated = False
        
        # Vérifier le nœud hub original
        hub_node = hub_start + h
        hub_index = manager.NodeToIndex(hub_node)
        # Un hub est activé si la variable ActiveVar est à 1 (nœud visité)
        if solution.Value(routing.ActiveVar(hub_index)) == 1:
            activated = True
            
        # Vérifier également les dépôts et pickups si disponibles 
        # (pour les transferts entre véhicules via hubs)
        if 'hub_deposits' in data and 'hub_pickups' in data:
            if h < len(data['hub_deposits']):
                deposit = data['hub_deposits'][h]  # Point de dépôt au hub
                pickup = data['hub_pickups'][h]    # Point de ramassage au hub
                dep_index = manager.NodeToIndex(deposit)
                pick_index = manager.NodeToIndex(pickup)
                # Hub activé si dépôt OU ramassage est utilisé
                if solution.Value(routing.ActiveVar(dep_index)) == 1 or solution.Value(routing.ActiveVar(pick_index)) == 1:
                    activated = True
                    
        if activated:
            activated_hubs.add(h)

    # Calcul de la répartition de charge finale entre véhicules
    # Charge finale = charge totale transportée à la fin de la route
    loads = [solution.Value(capacity_dimension.CumulVar(routing.End(v))) for v in range(data['num_vehicles'])]
    
    # Calcul du déséquilibre de charge (différence entre max et min)
    imbalance = max(loads) - min(loads) if loads else 0

    # Temps de calcul (pour l'instant fixé à 0, pourrait être mesuré)
    calc_time = 0

    # Retourner tous les résultats structurés
    return {
        'per_livreur': {
            'routes': routes,                    # Routes de chaque véhicule
            'estimated_times': estimated_times,  # Temps d'arrivée à chaque nœud
            'remaining_charges': remaining_charges # Capacité restante à chaque étape
        },
        'indicators': {
            'total_distance': total_distance,           # Distance totale parcourue
            'total_tardiness_minutes': total_tardiness, # Retard total en minutes
            'activated_hubs': len(activated_hubs),      # Nombre de hubs utilisés
            'load_repartition': loads,                  # Charge finale de chaque véhicule
            'calc_time': calc_time                      # Temps de calcul
        }
    }