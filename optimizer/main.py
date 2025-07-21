# optimizer/main.py
from optimizer.data_loader import load_data
from optimizer.preprocessor import preprocess
from optimizer.solver import solve_vrp
from optimizer.postprocessor import get_results

if __name__ == '__main__':
    data_dir = 'tests/toy_data'  # Adjust for actual
    data = load_data(data_dir)
    data = preprocess(data)
    manager, routing, solution = solve_vrp(data)
    results = get_results(data, manager, routing, solution)
    print(results)