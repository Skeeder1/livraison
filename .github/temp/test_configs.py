"""
Script to test different coefficient configurations and measure performance vs balance tradeoff
"""
import subprocess
import re
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from optimizer.config import Config
from optimizer.main import main as run_solver
import json

def parse_output(output):
    """Extract metrics from solver output"""
    lines = output.split('\n')

    # Find vehicle stops
    vehicles = {}
    for i, line in enumerate(lines):
        if f'🚛 VÉHICULE' in line and 'VÉHICULE' in line:
            vehicle_num = re.search(r'VÉHICULE (\d+)', line)
            if vehicle_num:
                v_num = int(vehicle_num.group(1))
                # Look for "Nombre d'arrêts" in next lines
                for j in range(i, min(i+5, len(lines))):
                    if 'Nombre d\'arrêts' in lines[j]:
                        stops = re.search(r': (\d+)', lines[j])
                        if stops:
                            vehicles[v_num] = int(stops.group(1))
                        break

    # Find distance
    distance = None
    for line in lines:
        if 'Distance totale' in line:
            dist_match = re.search(r': (\d+)', line)
            if dist_match:
                distance = int(dist_match.group(1))
                break

    # Calculate client counts (stops - 2 for depot start/end, minus hubs/reloads)
    # Approximate: real clients ≈ (stops - 2) / 1.3 (accounting for hubs/reloads)
    clients = {}
    for v, stops in vehicles.items():
        if v <= 3:  # Only real vehicles
            # Rough estimate
            clients[v] = max(0, int((stops - 2) * 0.6))  # Empirical factor

    return {
        'vehicles': vehicles,
        'clients': clients,
        'distance': distance
    }

def test_configuration(time_span, capacity_span, distance_span, num_runs=3):
    """Test a specific configuration"""
    print(f"\n=== Testing Config: TIME={time_span}, CAPACITY={capacity_span}, DISTANCE={distance_span} ===")

    # Update config
    Config.TIME_SPAN_COEFFICIENT = time_span
    Config.CAPACITY_SPAN_COEFFICIENT = capacity_span
    Config.DISTANCE_SPAN_COEFFICIENT = distance_span

    results = []

    for run in range(num_runs):
        print(f"  Run {run+1}/{num_runs}...", end='', flush=True)

        # Capture output
        import io
        from contextlib import redirect_stdout, redirect_stderr

        output_buffer = io.StringIO()
        try:
            with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
                run_solver()
            output = output_buffer.getvalue()

            # Parse results
            metrics = parse_output(output)
            results.append(metrics)

            if metrics['distance']:
                print(f" Distance: {metrics['distance']}, Clients: {metrics['clients']}")
            else:
                print(" FAILED")

        except Exception as e:
            print(f" ERROR: {e}")
            results.append({'vehicles': {}, 'clients': {}, 'distance': None})

    # Calculate averages
    avg_distance = sum(r['distance'] for r in results if r['distance']) / len([r for r in results if r['distance']])

    # Get typical balance
    if results[0]['clients']:
        client_counts = [results[0]['clients'].get(i, 0) for i in [1, 2, 3]]
        balance_str = f"{client_counts[0]}-{client_counts[1]}-{client_counts[2]}"
        max_clients = max(client_counts)
        min_clients = min([c for c in client_counts if c > 0] or [0])
        avg_clients = sum(client_counts) / 3 if sum(client_counts) > 0 else 1
        balance_score = (max_clients - min_clients) / avg_clients if avg_clients > 0 else 0
    else:
        balance_str = "?"
        balance_score = 999

    return {
        'config': {'TIME': time_span, 'CAPACITY': capacity_span, 'DISTANCE': distance_span},
        'avg_distance': avg_distance,
        'balance': balance_str,
        'balance_score': balance_score,
        'results': results
    }

if __name__ == '__main__':
    # Test configurations
    configs = [
        (0, 0, 0),           # Config 0: Baseline
        (200, 50, 30),       # Config 1: Light
        (300, 100, 50),      # Config 2: Moderate
        (400, 150, 60),      # Config 3: Strong
        (500, 300, 75),      # Config 4: Very strong (current)
    ]

    all_results = []

    for time_span, capacity_span, distance_span in configs:
        result = test_configuration(time_span, capacity_span, distance_span, num_runs=3)
        all_results.append(result)

    # Print summary table
    print("\n" + "="*80)
    print("SUMMARY TABLE")
    print("="*80)
    print(f"{'Config':<10} {'Coefficients':<25} {'Balance':<15} {'Avg Distance':<15} {'Balance Score':<15}")
    print("-"*80)

    baseline_dist = all_results[0]['avg_distance']

    for i, result in enumerate(all_results):
        config_str = f"{i}"
        coef_str = f"T={result['config']['TIME']}, C={result['config']['CAPACITY']}"
        balance = result['balance']
        dist = result['avg_distance']
        perf_ratio = dist / baseline_dist if baseline_dist > 0 else 0
        bal_score = result['balance_score']

        print(f"{config_str:<10} {coef_str:<25} {balance:<15} {dist:<15.0f} {bal_score:<15.2f}")

    # Save to JSON
    output_file = Path(__file__).parent / 'performance_analysis_results.json'
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\nResults saved to: {output_file}")
