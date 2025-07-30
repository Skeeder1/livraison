# optimizer/main.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
# optimizer/solver.py
import logging

# Configure Python logging to console
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s', handlers=[logging.StreamHandler()])

from optimizer.data_loader import load_data
from optimizer.preprocessor import preprocess
from optimizer.solver import solve_vrp
from optimizer.postprocessor import get_results
os.environ['GLOG_logtostderr'] = '1'
os.environ['GLOG_minloglevel'] = '0'
os.environ['GLOG_v'] = '3'  # Verbose level; increase if needed

if __name__ == '__main__':
    print(f"begining VRP solving")
    data_dir = os.path.join(os.path.dirname(__file__), 'tests', 'toy_data')
    data = load_data(data_dir)
    
    print("preprocessing data")
    data = preprocess(data)
    
    print(f"begining VRP solving with {data['num_nodes']} nodes and {data['num_vehicles']} vehicles")
  
    manager, routing, solution = solve_vrp(data)
    print(f"Baseline distance: {data['baseline_distance']:.2f}")
    if solution is None:
        print("No solution found")
    results = get_results(data, manager, routing, solution)
    print(results)