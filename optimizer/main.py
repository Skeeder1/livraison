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
from optimizer.solver import solve_vrp
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

    # Une seule résolution : les rendez-vous en hub sont désormais optionnels
    # (disjonction sur les nœuds de dépôt et de retrait), donc le solveur décide
    # lui-même lesquels valent leur détour. L'ancienne fonction résolvait le
    # problème deux fois, avec puis sans hubs, pour arbitrer entre « un transfert
    # imposé à chaque hub » et « aucun transfert » — un faux dilemme né du fait
    # que la paire était obligatoire.
    manager, routing, solution = solve_vrp(data)

    if solution is None:
        print("No solution found")
    else:
        results = get_results(data, manager, routing, solution)
        for key, value in results.items():
            if isinstance(value, dict):
                print(f"{key}:")
                for subkey, subvalue in value.items():
                    print(f"  {subkey}: {subvalue}")
            else:
                print(f"{key}: {value}")

        create_visualization(data, manager, routing, solution, results)
        print("Visualization created successfully")
    


if __name__ == '__main__':
    main()