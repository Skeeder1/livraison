import os
import json
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import seaborn as sns
from datetime import datetime
from itertools import product
from typing import Dict, List, Tuple, Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from optimizer.data_loader import load_data
from optimizer.preprocessor import preprocess
from optimizer.solver import solve_vrp
from optimizer.create_toy_data import generate_random_position, compute_distance_matrix
from optimizer.config import Config

class PerformanceAnalyzer:
    def __init__(self, results_dir: str = "optimizer/analysis_results"):
        self.results_dir = results_dir
        self.results_file = os.path.join(results_dir, "performance_results.csv")
        os.makedirs(results_dir, exist_ok=True)
        
        # Charger les résultats existants ou créer un nouveau DataFrame
        if os.path.exists(self.results_file):
            self.results_df = pd.read_csv(self.results_file)
        else:
            self.results_df = pd.DataFrame(columns=[
                'timestamp', 'num_customers', 'num_vehicles', 'num_hubs',
                'vehicle_capacity_min', 'vehicle_capacity_max',
                'solve_time', 'solution_found', 'total_distance', 'total_tardiness',
                'num_activated_hubs'
            ])

    def _run_single_test(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Exécute un test unique avec les paramètres donnés."""
        # Sauvegarder les paramètres originaux
        original_params = {
            'NUM_CUSTOMERS': Config.NUM_CUSTOMERS,
            'NUM_VEHICLES': Config.NUM_VEHICLES,
            'NUM_HUBS': Config.NUM_HUBS,
            'VEHICLE_CAPACITY_MIN': Config.VEHICLE_CAPACITY_MIN,
            'VEHICLE_CAPACITY_MAX': Config.VEHICLE_CAPACITY_MAX,
        }
        
        # Mettre à jour la configuration
        Config.update(
            NUM_CUSTOMERS=params['num_customers'],
            NUM_VEHICLES=params['num_vehicles'],
            NUM_HUBS=params['num_hubs'],
            VEHICLE_CAPACITY_MIN=params['vehicle_capacity_min'],
            VEHICLE_CAPACITY_MAX=params['vehicle_capacity_max']
        )
        
        try:
            # Créer les données de test
            data_dir = os.path.join(os.path.dirname(__file__), 'tests', 'toy_data')
            os.makedirs(data_dir, exist_ok=True)
            
            # Générer les nouvelles données
            # Utiliser les fonctions de create_toy_data.py pour générer les fichiers
            locations = [(0.0, 0.0)]  # Depot
            customer_positions = [generate_random_position() for _ in range(params['num_customers'])]
            hub_positions = [generate_random_position() for _ in range(params['num_hubs'])]
            locations.extend(customer_positions)
            locations.extend(hub_positions)
            
            # Exécuter le solveur avec limite de temps croissante
            current_time_limit = Config.TIME_TO_SOLVE  # Commencer avec le temps initial
            
            while current_time_limit <= Config.MAX_TIME_LIMIT:
                start_time = time.time()
                
                # Charger et préprocesser les données
                data = load_data(data_dir)
                data = preprocess(data)
                
                # Mettre à jour le temps limite dans les données
                data['time_limit'] = current_time_limit
                
                # Résoudre le VRP
                manager, routing, solution = solve_vrp(data)
                
                solve_time = time.time() - start_time
                
                # Si une solution est trouvée, retourner les résultats
                if solution:
                    from optimizer.postprocessor import get_results
                    results = get_results(data, manager, routing, solution)
                    
                    return {
                        'timestamp': datetime.now().isoformat(),
                        'num_customers': params['num_customers'],
                        'num_vehicles': params['num_vehicles'],
                        'num_hubs': params['num_hubs'],
                        'vehicle_capacity_min': params['vehicle_capacity_min'],
                        'vehicle_capacity_max': params['vehicle_capacity_max'],
                        'solve_time': solve_time,
                        'solution_found': True,
                        'total_distance': results['indicators']['total_distance'],
                        'total_tardiness': results['indicators']['total_tardiness_minutes'],
                        'num_activated_hubs': results['indicators']['activated_hubs']
                    }
                print(f"Pas de solution trouvée, temps écoulé: {solve_time:.2f} secondes, essayant avec un temps limite plus long")
                # Si pas de solution, augmenter le temps limite
                current_time_limit += Config.TIME_INCREMENT
                # Mettre à jour Config.TIME_TO_SOLVE pour refléter le nouveau temps limite
                Config.update(TIME_TO_SOLVE=current_time_limit)
            
            # Si aucune solution n'est trouvée après le temps maximum
            result = {
                'timestamp': datetime.now().isoformat(),
                'num_customers': params['num_customers'],
                'num_vehicles': params['num_vehicles'],
                'num_hubs': params['num_hubs'],
                'vehicle_capacity_min': params['vehicle_capacity_min'],
                'vehicle_capacity_max': params['vehicle_capacity_max'],
                'solve_time': Config.MAX_TIME_LIMIT,
                'solution_found': False,
                'total_distance': None,
                'total_tardiness': None,
                'num_activated_hubs': None
            }
            
        finally:
            # Restaurer les paramètres originaux
            Config.update(**original_params)
            
        return result

    def run_analysis(self, parameter_ranges: Dict[str, List[Any]]):
        """
        Exécute l'analyse de performance avec les plages de paramètres données.
        
        parameter_ranges: {
            'num_customers': [50, 100, 150],
            'num_vehicles': [3, 5, 7],
            'num_hubs': [1, 2, 3],
            'vehicle_capacity_min': [10, 15],
            'vehicle_capacity_max': [15, 20]
        }
        """
        # Générer toutes les combinaisons de paramètres
        param_names = list(parameter_ranges.keys())
        param_values = list(parameter_ranges.values())
        combinations = list(product(*param_values))
        
        total_combinations = len(combinations)
        print(f"Starting analysis with {total_combinations} parameter combinations")
        
        for i, values in enumerate(combinations, 1):
            params = dict(zip(param_names, values))
            print(f"\nTesting combination {i}/{total_combinations}:")
            print(params)
            
            # Vérifier si cette combinaison a déjà été testée
            existing = self.results_df[
                (self.results_df['num_customers'] == params['num_customers']) &
                (self.results_df['num_vehicles'] == params['num_vehicles']) &
                (self.results_df['num_hubs'] == params['num_hubs']) &
                (self.results_df['vehicle_capacity_min'] == params['vehicle_capacity_min']) &
                (self.results_df['vehicle_capacity_max'] == params['vehicle_capacity_max'])
            ]
            
            if len(existing) > 0:
                print("Configuration already tested, skipping...")
                continue
            
            # Exécuter le test
            result = self._run_single_test(params)
            
            # Ajouter les résultats au DataFrame
            self.results_df = pd.concat([self.results_df, pd.DataFrame([result])], ignore_index=True)
            
            # Sauvegarder les résultats après chaque test
            self.results_df.to_csv(self.results_file, index=False)
            
            print(f"Results saved. Solution found: {result['solution_found']}, Time: {result['solve_time']:.2f}s")

    def plot_results(self, x_param: str, group_by: str | None = None, output_dir: str | None = None):
        """
        Génère des graphiques d'analyse des résultats.
        
        x_param: Paramètre à mettre en axe X
        group_by: Paramètre pour grouper les résultats (optionnel)
        output_dir: Répertoire où sauvegarder les graphiques (optionnel)
        """
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # Filtre pour ne garder que les cas où une solution a été trouvée
        solved_df = self.results_df[self.results_df['solution_found']]
        
        # Créer plusieurs graphiques
        metrics = ['solve_time', 'total_distance', 'total_tardiness', 'num_activated_hubs']
        for metric in metrics:
            plt.figure(figsize=(12, 6))
            
            if group_by:
                for name, group in solved_df.groupby(group_by):
                    plt.scatter(group[x_param], group[metric], label=f'{group_by}={name}')
                    
                    # Ajouter une ligne de tendance
                    z = np.polyfit(group[x_param], group[metric], 1)
                    p = np.poly1d(z)
                    plt.plot(group[x_param], p(group[x_param]), '--', alpha=0.5)
            else:
                plt.scatter(solved_df[x_param], solved_df[metric])
                
                # Ajouter une ligne de tendance
                z = np.polyfit(solved_df[x_param], solved_df[metric], 1)
                p = np.poly1d(z)
                plt.plot(solved_df[x_param], p(solved_df[x_param]), '--', alpha=0.5)
            
            plt.xlabel(x_param)
            plt.ylabel(metric)
            plt.title(f'{metric} vs {x_param}')
            if group_by:
                plt.legend()
            
            if output_dir:
                plt.savefig(os.path.join(output_dir, f'{metric}_vs_{x_param}.png'))
            plt.close()
        
        # Créer une heatmap pour les cas non résolus
        if 'num_customers' in self.results_df.columns and 'num_vehicles' in self.results_df.columns:
            plt.figure(figsize=(10, 8))
            pivot = self.results_df.pivot_table(
                values='solution_found',
                index='num_customers',
                columns='num_vehicles',
                aggfunc=lambda x: sum(x) / len(x)  # Pourcentage de solutions trouvées
            )
            sns.heatmap(pivot, annot=True, cmap='RdYlGn', vmin=0, vmax=1)
            plt.title('Solution Success Rate')
            if output_dir:
                plt.savefig(os.path.join(output_dir, 'solution_success_rate.png'))
            plt.close()

def run_performance_analysis():
    """Fonction principale pour lancer l'analyse des performances."""
    analyzer = PerformanceAnalyzer()
    
    # Définir les plages de paramètres à tester
    parameter_ranges = {
        'num_customers': [50, 75, 100, 125, 150],
        'num_vehicles': [3, 4, 5, 6, 7],
        'num_hubs': [1, 2, 3],
        'vehicle_capacity_min': [10, 15],
        'vehicle_capacity_max': [15, 20]
    }
    
    # Lancer l'analyse
    analyzer.run_analysis(parameter_ranges)
    
    # Générer les graphiques
    output_dir = os.path.join(analyzer.results_dir, 'plots')
    analyzer.plot_results('num_customers', 'num_hubs', output_dir)
    analyzer.plot_results('num_vehicles', 'num_hubs', output_dir)
    analyzer.plot_results('num_customers', 'num_vehicles', output_dir)

if __name__ == '__main__':
    run_performance_analysis()
