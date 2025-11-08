# optimizer/main.py
import os
import sys
import logging

from pathlib import Path
from colorama import init
init(autoreset=True)
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
# Configure Python logging to console
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s', handlers=[logging.StreamHandler()])

# Configure OR-Tools logging
os.environ['GLOG_logtostderr'] = '1'
os.environ['GLOG_minloglevel'] = '0'
os.environ['GLOG_v'] = '3'  # Verbose level; increase if needed

# Import project modules
from optimizer.data_loader import load_data
from optimizer.preprocessor import preprocess
from optimizer.solver import solve_vrp, solve_vrp_with_optimal_hubs
from optimizer.postprocessor import get_results
from optimizer.print_solution import create_visualization
from optimizer.create_toy_data import create_toy_data
from optimizer.config import Config

# Main function to run the VRP solution process
def main():
    create_toy_data()
    print(f"begining VRP solving")
    data_dir = os.path.join(os.path.dirname(__file__), 'tests', 'toy_data')
    data = load_data(data_dir)
    
    print("preprocessing data")
    data = preprocess(data)

    print(f"begining VRP solving with {data['num_nodes']} nodes and {data['num_vehicles']} vehicles and {data['num_hubs']} hubs")
    print(f"Baseline distance: {data['baseline_distance']:.2f}")

    # Utiliser la nouvelle fonction qui compare avec/sans hubs
    manager, routing, solution, results, hubs_used = solve_vrp_with_optimal_hubs(data)

    if solution is None:
        print("No solution found")
    else:
        # Les résultats sont déjà calculés par solve_vrp_with_optimal_hubs
        for key, value in results.items():
            if isinstance(value, dict):
                print(f"{key}:")
                for subkey, subvalue in value.items():
                    print(f"  {subkey}: {subvalue}")
            else:
                print(f"{key}: {value}")

        # Utiliser les données appropriées pour la visualisation
        if not hubs_used:
            # Si on a choisi la solution sans hubs, recréer data_no_hubs pour la visualisation
            import copy
            data_viz = copy.deepcopy(data)
            data_viz['num_hubs'] = 0
            data_viz['hubs'] = []
        else:
            data_viz = data

        create_visualization(data_viz, manager, routing, solution, results)
        print("Visualization created successfully")
    


if __name__ == '__main__':
    main()