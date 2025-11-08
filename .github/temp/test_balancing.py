"""
Script de test pour vérifier l'équilibrage des charges après les modifications.
Analyse la répartition des clients entre véhicules et les temps de route.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import os
from optimizer.data_loader import load_data
from optimizer.preprocessor import preprocess
from optimizer.solver import solve_vrp
from optimizer.postprocessor import get_results
from optimizer.config import Config

def analyze_load_balance(results, data):
    """Analyse l'équilibre de charge entre véhicules"""
    print("\n" + "="*80)
    print("ANALYSE DE L'ÉQUILIBRAGE DES CHARGES")
    print("="*80)

    # Analyser la répartition des clients
    clients_per_vehicle = []
    times_per_vehicle = []
    loads_per_vehicle = []

    num_real_vehicles = len([cap for cap in data['vehicle_capacities'] if cap > 0])

    for v in range(num_real_vehicles):
        route = results['per_livreur']['routes'][v]
        times = results['per_livreur']['estimated_times'][v]
        loads = results['per_livreur']['current_loads'][v]

        # Compter les clients (nœuds entre 1 et num_customers)
        num_clients = sum(1 for node in route if 1 <= node <= data['num_customers'])
        clients_per_vehicle.append(num_clients)

        # Temps total de la route
        route_time = times[-1] - times[0] if len(times) >= 2 else 0
        times_per_vehicle.append(route_time)

        # Charge maximale transportée
        max_load = max(loads) if loads else 0
        loads_per_vehicle.append(max_load)

        print(f"\n📦 Véhicule {v+1}:")
        print(f"   Clients livrés    : {num_clients}")
        print(f"   Temps total       : {route_time:.0f} secondes ({route_time/60:.1f} minutes)")
        print(f"   Charge maximale   : {max_load:.0f}/{data['vehicle_capacities'][v]:.0f}")
        print(f"   Route complète    : {' → '.join(map(str, route[:10]))}{' ...' if len(route) > 10 else ''}")

    # Statistiques globales
    print("\n" + "="*80)
    print("STATISTIQUES GLOBALES")
    print("="*80)

    total_clients = sum(clients_per_vehicle)
    avg_clients = total_clients / num_real_vehicles
    min_clients = min(clients_per_vehicle)
    max_clients = max(clients_per_vehicle)

    avg_time = sum(times_per_vehicle) / num_real_vehicles
    min_time = min(times_per_vehicle)
    max_time = max(times_per_vehicle)
    time_ratio = max_time / min_time if min_time > 0 else float('inf')

    print(f"\n📊 Répartition des clients:")
    print(f"   Total              : {total_clients}")
    print(f"   Moyenne par véhicule: {avg_clients:.1f}")
    print(f"   Min                 : {min_clients}")
    print(f"   Max                 : {max_clients}")
    print(f"   Écart              : {max_clients - min_clients}")
    print(f"   Balance %          : {(max_clients / avg_clients - 1) * 100:.1f}%")

    print(f"\n⏱️  Temps de route:")
    print(f"   Temps total (somme): {sum(times_per_vehicle):.0f} secondes ({sum(times_per_vehicle)/60:.1f} minutes)")
    print(f"   Makespan (max)     : {max_time:.0f} secondes ({max_time/60:.1f} minutes)")
    print(f"   Temps moyen        : {avg_time:.0f} secondes ({avg_time/60:.1f} minutes)")
    print(f"   Temps min          : {min_time:.0f} secondes ({min_time/60:.1f} minutes)")
    print(f"   Ratio max/min      : {time_ratio:.2f}")

    # Évaluation de la qualité
    print(f"\n🎯 Évaluation:")
    if time_ratio <= Config.MAX_TIME_RATIO:
        print(f"   ✅ Ratio temps respecté : {time_ratio:.2f} ≤ {Config.MAX_TIME_RATIO}")
    else:
        print(f"   ❌ Ratio temps dépassé  : {time_ratio:.2f} > {Config.MAX_TIME_RATIO}")

    balance_quality = (max_clients - min_clients) / avg_clients * 100
    if balance_quality < 30:
        print(f"   ✅ Équilibre EXCELLENT  : écart de {balance_quality:.1f}%")
    elif balance_quality < 50:
        print(f"   ⚠️  Équilibre MOYEN     : écart de {balance_quality:.1f}%")
    else:
        print(f"   ❌ Équilibre MAUVAIS   : écart de {balance_quality:.1f}%")

    print(f"\n📏 Distance totale: {results['indicators']['total_distance']:.2f} unités")

    print("\n" + "="*80)

    return {
        'total_clients': total_clients,
        'clients_per_vehicle': clients_per_vehicle,
        'times_per_vehicle': times_per_vehicle,
        'time_ratio': time_ratio,
        'balance_quality': balance_quality,
        'total_time': sum(times_per_vehicle),
        'makespan': max_time
    }

def main():
    print("\n🚀 TEST D'ÉQUILIBRAGE DES CHARGES")
    print(f"\nCoefficients actuels:")
    print(f"  TIME_SPAN_COEFFICIENT     = {Config.TIME_SPAN_COEFFICIENT}")
    print(f"  CAPACITY_SPAN_COEFFICIENT = {Config.CAPACITY_SPAN_COEFFICIENT}")
    print(f"  DISTANCE_SPAN_COEFFICIENT = {Config.DISTANCE_SPAN_COEFFICIENT}")
    print(f"  MAX_TIME_RATIO            = {Config.MAX_TIME_RATIO}")

    # Charger les données
    data_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'optimizer', 'tests', 'toy_data')
    print(f"\n📂 Chargement des données depuis: {data_dir}")
    data = load_data(data_dir)
    data = preprocess(data)

    print(f"\n📋 Problème:")
    print(f"  Clients     : {data['num_customers']}")
    print(f"  Véhicules   : {Config.NUM_VEHICLES}")
    print(f"  Hubs        : {Config.NUM_HUBS}")

    # Résoudre le VRP
    print(f"\n🔍 Résolution du VRP (temps limite: {Config.TIME_TO_SOLVE}s)...")
    manager, routing, solution = solve_vrp(data)

    if solution:
        print("✅ Solution trouvée !")
        results = get_results(data, manager, routing, solution)

        # Analyser l'équilibrage
        metrics = analyze_load_balance(results, data)

        # Sauvegarder les résultats
        import json
        results_file = os.path.join(os.path.dirname(__file__), 'balancing_results.json')
        with open(results_file, 'w') as f:
            json.dump({
                'config': {
                    'TIME_SPAN_COEFFICIENT': Config.TIME_SPAN_COEFFICIENT,
                    'CAPACITY_SPAN_COEFFICIENT': Config.CAPACITY_SPAN_COEFFICIENT,
                    'DISTANCE_SPAN_COEFFICIENT': Config.DISTANCE_SPAN_COEFFICIENT,
                    'MAX_TIME_RATIO': Config.MAX_TIME_RATIO,
                    'NUM_CUSTOMERS': Config.NUM_CUSTOMERS,
                    'NUM_VEHICLES': Config.NUM_VEHICLES,
                    'NUM_HUBS': Config.NUM_HUBS
                },
                'metrics': metrics
            }, f, indent=2)
        print(f"\n💾 Résultats sauvegardés dans: {results_file}")

    else:
        print("❌ Aucune solution trouvée !")

if __name__ == '__main__':
    main()
