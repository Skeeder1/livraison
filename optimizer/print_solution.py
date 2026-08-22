# File: print_solution.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import json
import folium
from folium.plugins import HeatMap, MiniMap

from optimizer.road_routing import build_road_legs
import numpy as np
import matplotlib.cm as cm
from optimizer.data_loader import load_data
from optimizer.preprocessor import preprocess
from optimizer.solver import service_time, solve_vrp
from optimizer.postprocessor import get_results
# Attentes, charges et sérialisation JSON vivent dans `optimizer.trace` : elles
# servent aussi à l'API `optimizer.scenario`, qui ne doit pas importer folium ni
# matplotlib. Une seule implémentation, deux consommateurs.
from optimizer.trace import (
    compute_cumulative_loads,
    compute_slacks,
    convert_to_json_serializable,
)

def create_visualization(data, manager, routing, solution, results, output_file='vrp_visualization.html'):
    if solution is None:
        print("Cannot create visualization: No solution found")
        return

    hub_start = 1 + data['num_customers']
    num_real_vehicles = len(data['vehicle_capacities'])

    results['per_livreur']['slacks'] = compute_slacks(data, manager, routing, solution)
    results['per_livreur']['cumulative_loads'] = compute_cumulative_loads(data, results)

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

    # Max time (only from real vehicles, not dummy vehicles)
    max_time = max(max(results['per_livreur']['estimated_times'][v]) for v in range(num_real_vehicles) if results['per_livreur']['estimated_times'][v])

    # Heatmap data
    time_spent = np.zeros(len(data['locations']))
    for v in range(data['num_vehicles']):
        route = results['per_livreur']['routes'][v]
        slacks = results['per_livreur']['slacks'][v]
        for j in range(len(route) - 1):
            node = route[j]
            time_spent[node] += service_time(data, node) + slacks[j]
    heat_data = [[data['locations'][i][0], data['locations'][i][1], time_spent[i]] for i in range(len(time_spent)) if time_spent[i] > 0]

    # Create map
    depot_loc = data['locations'][data['depot']]
    m = folium.Map(location=depot_loc, zoom_start=12)

    # Colors
    colors = cm.tab10(np.linspace(0, 1, num_real_vehicles))
    colors_hex = ['#%02x%02x%02x' % (int(r*255), int(g*255), int(b*255)) for r, g, b, _ in colors]

    # Géométrie routière réelle des tournées (OSRM), avec repli en lignes droites
    # si le réseau est indisponible. Voir optimizer/road_routing.py.
    print("🛣️  Calcul du tracé sur le réseau routier réel...")
    road_legs = build_road_legs(
        data['locations'],
        results['per_livreur']['routes'][:num_real_vehicles],
    )

    # Route groups
    for v in range(num_real_vehicles):
        group = folium.FeatureGroup(name=f'Route {v+1}')
        route = results['per_livreur']['routes'][v]
        # On enchaîne la géométrie de chaque segment plutôt que de relier les
        # clients à vol d'oiseau : le tracé suit les rues.
        route_locs = []
        for i in range(len(route) - 1):
            leg = road_legs.get(f"{route[i]}-{route[i + 1]}")
            if not leg:
                leg = [data['locations'][route[i]], data['locations'][route[i + 1]]]
            # Le dernier point d'un segment est le premier du suivant.
            route_locs.extend(leg if not route_locs else leg[1:])
        if not route_locs:
            route_locs = [data['locations'][node] for node in route]
        folium.PolyLine(route_locs, color=colors_hex[v], weight=5, opacity=0.7).add_to(group)
        group.add_to(m)

    # Markers - Assign customer color based on their delivery vehicle
    customers_group = folium.FeatureGroup(name='Customers')
    for i in range(1, 1 + data['num_customers']):
        loc = data['locations'][i]
        demand = data['demands'][i]
        tw = data['time_windows'][i]

        # Find which vehicle delivers to this customer
        customer_vehicle = None
        for v in range(num_real_vehicles):
            if i in results['per_livreur']['routes'][v]:
                customer_vehicle = v
                break

        # Use vehicle color, or gray if not assigned
        if customer_vehicle is not None:
            marker_color = colors_hex[customer_vehicle]
            vehicle_label = f'Vehicle {customer_vehicle + 1}'
        else:
            marker_color = '#808080'  # Gray for unassigned
            vehicle_label = 'Not Assigned'

        # Use CircleMarker to support custom hex colors
        folium.CircleMarker(
            loc,
            radius=7,
            popup=f'Customer {i}<br>{vehicle_label}<br>Demand: {demand}<br>TW: {tw[0]}-{tw[1]}',
            tooltip=f'Customer {i}',
            color=marker_color,
            fill=True,
            fillColor=marker_color,
            fillOpacity=0.8,
            weight=2
        ).add_to(customers_group)
    customers_group.add_to(m)

    hubs_group = folium.FeatureGroup(name='Hubs')
    for i in range(data['num_hubs']):
        h = hub_start + i
        loc = data['locations'][h]

        # Hub main marker
        folium.Marker(
            loc,
            icon=folium.Icon(icon='warehouse', prefix='fa', color='green'),
            popup=f'Hub {i+1}',
            tooltip=f'Hub {i+1}'
        ).add_to(hubs_group)

        # Deposit and Pickup markers at the same location with mini icons
        # Deposit marker (drop-off)
        folium.CircleMarker(
            loc,
            radius=6,
            color='orange',
            fill=True,
            fillColor='orange',
            fillOpacity=0.6,
            weight=2,
            popup=f'Hub {i+1} - Depot (Drop-off)',
            tooltip=f'Hub {i+1} - Depot'
        ).add_to(hubs_group)

        # Pickup marker (pick-up)
        folium.CircleMarker(
            loc,
            radius=5,
            color='blue',
            fill=True,
            fillColor='blue',
            fillOpacity=0.6,
            weight=2,
            popup=f'Hub {i+1} - Pickup (Pick-up)',
            tooltip=f'Hub {i+1} - Pickup'
        ).add_to(hubs_group)

    hubs_group.add_to(m)

    depot_group = folium.FeatureGroup(name='Depot')
    folium.Marker(depot_loc, icon=folium.Icon(icon='star', prefix='fa', color='red'), popup='Depot', tooltip='Depot').add_to(depot_group)
    depot_group.add_to(m)

    # Heatmap
    # `show=False` : la carte de chaleur reste disponible dans le sélecteur de
    # couches, mais n'est plus active au chargement. Elle recouvrait les tracés
    # de tournée, qui sont l'information principale.
    heat_group = folium.FeatureGroup(name='Activity Heatmap', show=False)
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
        'baseline_distance': data.get('baseline_distance', 0),
        # Géométrie routière par segment, clé "noeud_depart-noeud_arrivee".
        # L'animation interpole le long de ces points : les livreurs suivent les
        # rues au lieu de se déplacer à vol d'oiseau.
        'road_legs': road_legs,
    }
    js_data = convert_to_json_serializable(js_data)
    js_data_json = json.dumps(js_data)

    # CSS
    css_path = os.path.join(os.path.dirname(__file__), 'visualization', 'styles.css')
    with open(css_path, 'r', encoding='utf-8') as f:
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
    with open(html_path, 'r', encoding='utf-8') as f:
        html_template = f.read()
    html = html_template.format(max_time=max_time, baseline_distance=data.get('baseline_distance', 0))
    m.get_root().html.add_child(folium.Element(html))

    # JS
    map_id = m._id
    js_path = os.path.join(os.path.dirname(__file__), 'visualization', 'script.js')
    with open(js_path, 'r', encoding='utf-8') as f:
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