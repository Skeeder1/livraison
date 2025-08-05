# File: print_solution.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import json
import folium
from folium.plugins import HeatMap, MiniMap
import numpy as np
import matplotlib.cm as cm
from optimizer.data_loader import load_data
from optimizer.preprocessor import preprocess
from optimizer.solver import solve_vrp
from optimizer.postprocessor import get_results

def convert_to_json_serializable(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    elif isinstance(obj, dict):
        return {k: convert_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_json_serializable(i) for i in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_to_json_serializable(i) for i in obj)
    else:
        return obj

def create_visualization(data, manager, routing, solution, results, output_file='vrp_visualization.html'):
    if solution is None:
        print("Cannot create visualization: No solution found")
        return

    # Recompute base_node as in solver
    base_node = list(range(data['num_nodes']))
    for u in data['unload_depots']:
        base_node.append(data['depot'])
    hub_start = 1 + data['num_customers']
    for i in range(data['num_hubs']):
        hub = hub_start + i
        base_node.append(hub)  # deposit
        base_node.append(hub)  # pickup
    for d in data['dummy_nodes']:
        base_node.append(data['depot'])

    # Helper functions
    def get_travel_time(from_node, to_node):
        b_from = base_node[from_node]
        b_to = base_node[to_node]
        return int(data['time_matrix'][b_from, b_to])

    def service_time(node):
        return abs(data['demands'][node]) * data['time_per_demand_unit']

    # Compute slacks
    time_dimension = routing.GetDimensionOrDie('Time')
    slacks_list = []
    for v in range(data['num_vehicles']):
        route_slacks = []
        index = routing.Start(v)
        while not routing.IsEnd(index):
            next_index = solution.Value(routing.NextVar(index))
            transit = service_time(manager.IndexToNode(index)) + get_travel_time(manager.IndexToNode(index), manager.IndexToNode(next_index))
            slack = solution.Value(time_dimension.CumulVar(next_index)) - solution.Value(time_dimension.CumulVar(index)) - transit
            route_slacks.append(max(0, slack))  # Ensure non-negative
            index = next_index
        slacks_list.append(route_slacks)
    results['per_livreur']['slacks'] = slacks_list

    # Compute cumulative loads for visualization (use real solver data)
    cumulative_loads = []
    # Utiliser seulement les vrais véhicules, pas les dummy vehicles
    num_real_vehicles = len(data['vehicle_capacities'])
    
    # Calculer pour tous les véhicules (réels + dummy)
    for v in range(data['num_vehicles']):
        if v < num_real_vehicles:
            # Véhicule réel
            route = results['per_livreur']['routes'][v]
            vehicle_capacity = data['vehicle_capacities'][v]
            
    # Use the correctly computed current_loads from postprocessor
    # current_loads now contains the actual load carried, not remaining capacity
    cumulative_loads = []
    
    # Calculer pour tous les véhicules (réels + dummy)
    for v in range(data['num_vehicles']):
        if v < num_real_vehicles:
            # Véhicule réel - utiliser les données du postprocessor
            current_loads = results['per_livreur']['current_loads'][v]  # Maintenant c'est la charge transportée
            vehicle_capacity = data['vehicle_capacities'][v]
            
            # Convertir charge transportée en capacité restante pour la visualisation
            remaining_charges = []
            for load in current_loads:
                remaining_capacity = vehicle_capacity - load
                remaining_charges.append(remaining_capacity)
            cumulative_loads.append(current_loads)  # Utiliser les charges transportées
        else:
            # Véhicule dummy - capacité toujours 0
            route = results['per_livreur']['routes'][v]
            dummy_loads = [0] * len(route)
            cumulative_loads.append(dummy_loads)
    
    results['per_livreur']['cumulative_loads'] = cumulative_loads

    # Compute transfers
    transfers = []
    for i in range(data['num_hubs']):
        deposit = data['hub_deposits'][i]
        pickup = data['hub_pickups'][i]
        deposit_v = deposit_t = pickup_v = pickup_t = None
        for v in range(data['num_vehicles']):
            route = results['per_livreur']['routes'][v]
            if deposit in route:
                pos = route.index(deposit)
                deposit_t = results['per_livreur']['estimated_times'][v][pos]
                deposit_v = v
            if pickup in route:
                pos = route.index(pickup)
                pickup_t = results['per_livreur']['estimated_times'][v][pos]
                pickup_v = v
        if deposit_v is not None and pickup_v is not None:
            transfers.append({'hub': hub_start + i, 'deposit_v': deposit_v, 'deposit_t': deposit_t, 'pickup_v': pickup_v, 'pickup_t': pickup_t})
    results['transfers'] = transfers

    # Max time
    max_time = max(max(times) for times in results['per_livreur']['estimated_times'] if times)

    # Heatmap data
    time_spent = np.zeros(len(data['locations']))
    for v in range(data['num_vehicles']):
        route = results['per_livreur']['routes'][v]
        slacks = results['per_livreur']['slacks'][v]
        for j in range(len(route) - 1):
            node = route[j]
            time_spent[node] += service_time(node) + slacks[j]
    heat_data = [[data['locations'][i][0], data['locations'][i][1], time_spent[i]] for i in range(len(time_spent)) if time_spent[i] > 0]

    # Create map
    depot_loc = data['locations'][data['depot']]
    m = folium.Map(location=depot_loc, zoom_start=12)

    # Colors
    colors = cm.tab10(np.linspace(0, 1, num_real_vehicles))
    colors_hex = ['#%02x%02x%02x' % (int(r*255), int(g*255), int(b*255)) for r, g, b, _ in colors]

    # Route groups
    for v in range(num_real_vehicles):
        group = folium.FeatureGroup(name=f'Route {v+1}')
        route = results['per_livreur']['routes'][v]
        route_locs = [data['locations'][node] for node in route]
        folium.PolyLine(route_locs, color=colors_hex[v], weight=5, opacity=0.7).add_to(group)
        group.add_to(m)

    # Markers
    customers_group = folium.FeatureGroup(name='Customers')
    for i in range(1, 1 + data['num_customers']):
        loc = data['locations'][i]
        demand = data['demands'][i]
        tw = data['time_windows'][i]
        folium.Marker(loc, icon=folium.Icon(icon='home', prefix='fa', color='blue'), popup=f'Customer {i}<br>Demand: {demand}<br>TW: {tw[0]}-{tw[1]}', tooltip=f'Customer {i}').add_to(customers_group)
    customers_group.add_to(m)

    hubs_group = folium.FeatureGroup(name='Hubs')
    for i in range(data['num_hubs']):
        h = hub_start + i
        loc = data['locations'][h]
        folium.CircleMarker(loc, radius=10, color='green', fill=True, fill_color='green', popup=f'Hub {i+1}', tooltip=f'Hub {i+1}').add_to(hubs_group)
    hubs_group.add_to(m)

    depot_group = folium.FeatureGroup(name='Depot')
    folium.Marker(depot_loc, icon=folium.Icon(icon='star', prefix='fa', color='red'), popup='Depot', tooltip='Depot').add_to(depot_group)
    depot_group.add_to(m)

    # Heatmap
    heat_group = folium.FeatureGroup(name='Activity Heatmap')
    HeatMap(heat_data).add_to(heat_group)
    heat_group.add_to(m)

    # MiniMap
    m.add_child(MiniMap())

    # LayerControl
    folium.LayerControl().add_to(m)

    # JS data
    js_data = {
        'results': results,
        'locations': data['locations'],
        'time_windows': data['time_windows'],
        'demands': data['demands'],
        'vehicle_capacities': data['vehicle_capacities'] + [0] * (data['num_vehicles'] - num_real_vehicles),  # Include dummy vehicles
        'max_time': max_time,
        'colors': colors_hex + ['#000000'] * (data['num_vehicles'] - num_real_vehicles),  # Black for dummy vehicles
        'num_vehicles': data['num_vehicles'],  # All vehicles including dummies
        'depot': data['depot'],
        'transfers': results['transfers'],
        'num_customers': data['num_customers'],
        'num_hubs': data['num_hubs'],
        'hub_deposits': data.get('hub_deposits', []),
        'hub_pickups': data.get('hub_pickups', []),
        'time_per_demand_unit': data['time_per_demand_unit'],
        'baseline_distance': data.get('baseline_distance', 0)
    }
    js_data = convert_to_json_serializable(js_data)
    js_data_json = json.dumps(js_data)

    # CSS
    css_path = os.path.join(os.path.dirname(__file__), 'visualization', 'styles.css')
    with open(css_path, 'r') as f:
        style_content = f.read()
    css = '''
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css">
    <style>
    ''' + style_content + '''
    </style>
    '''
    m.get_root().header.add_child(folium.Element(css))

    # HTML
    html_path = os.path.join(os.path.dirname(__file__), 'visualization', 'interface.html')
    with open(html_path, 'r') as f:
        html_template = f.read()
    html = html_template.format(max_time=max_time, baseline_distance=data.get('baseline_distance', 0))
    m.get_root().html.add_child(folium.Element(html))

    # JS
    map_id = m._id
    js_path = os.path.join(os.path.dirname(__file__), 'visualization', 'script.js')
    with open(js_path, 'r') as f:
        script_content = f.read()
    script = '''
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <script>
    ''' + script_content.replace('{map_id}', map_id).replace('{js_data_json}', js_data_json) + '''
    </script>
    '''
    m.get_root().html.add_child(folium.Element(script))

    # Save
    m.save(output_file)

if __name__ == '__main__':
    data_dir = os.path.join(os.path.dirname(__file__), 'tests', 'toy_data')
    data = load_data(data_dir)
    data = preprocess(data)
    manager, routing, solution = solve_vrp(data)
    if solution:
        results = get_results(data, manager, routing, solution)
        create_visualization(data, manager, routing, solution, results)
    else:
        print("No solution found")