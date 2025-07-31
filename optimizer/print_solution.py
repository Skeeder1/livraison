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

    # Assign customers to livreurs
    customer_to_livreur = {}
    customer_arrival = {}
    for v in range(data['num_vehicles']):
        route = results['per_livreur']['routes'][v]
        times = results['per_livreur']['estimated_times'][v]
        for j, node in enumerate(route[:-1]):
            if 1 <= node <= data['num_customers']:
                customer_to_livreur[node] = v
                customer_arrival[node] = times[j]

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

    # Heatmap data (but we'll make it optional and off by default)
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
    colors = cm.tab10(np.linspace(0, 1, data['num_vehicles']))
    colors_hex = ['#%02x%02x%02x' % (int(r*255), int(g*255), int(b*255)) for r, g, b, _ in colors]

    # Route groups
    for v in range(data['num_vehicles']):
        group = folium.FeatureGroup(name=f'Route {v+1}', show=True)
        route = results['per_livreur']['routes'][v]
        route_locs = [data['locations'][node] for node in route]
        # Thickness scaled by average load
        avg_load = np.mean([data['vehicle_capacities'][v] - r for r in results['per_livreur']['remaining_charges'][v]])
        weight = 3 + (avg_load / max(data['vehicle_capacities'])) * 5 if data['vehicle_capacities'] else 5
        folium.PolyLine(route_locs, color=colors_hex[v], weight=weight, opacity=0.7).add_to(group)
        group.add_to(m)

    # Customer markers with color by livreur and size by volume
    customers_group = folium.FeatureGroup(name='Customers', show=True)
    max_demand = max(data['demands'][1:1+data['num_customers']]) if data['num_customers'] > 0 else 1
    for i in range(1, 1 + data['num_customers']):
        loc = data['locations'][i]
        demand = data['demands'][i]
        tw = data['time_windows'][i]
        livreur = customer_to_livreur.get(i, -1)
        color = colors_hex[livreur] if livreur != -1 else '#0000ff'
        size = 20 + (demand / max_demand) * 20
        arrival = customer_arrival.get(i, 'N/A')
        icon_html = f'<i class="fa fa-home" style="color:{color}; font-size:{size}px;"></i>'
        icon = folium.DivIcon(html=icon_html)
        popup = f'Customer {i}<br>Demand: {demand}<br>TW: {tw[0]}-{tw[1]}<br>Arrival: {arrival}'
        folium.Marker(loc, icon=icon, popup=popup, tooltip=f'Customer {i}').add_to(customers_group)
    customers_group.add_to(m)

    # Hub markers with arrows and pulsing
    hubs_group = folium.FeatureGroup(name='Hubs', show=True)
    for i in range(data['num_hubs']):
        h = hub_start + i
        loc = data['locations'][h]
        icon_html = '<div style="position: relative;"><i class="fa fa-circle" style="color:green; font-size:20px;"></i><i class="fa fa-arrows-alt" style="position:absolute; top:0; left:0; color:white; font-size:10px;"></i></div>'
        icon = folium.DivIcon(html=icon_html)
        folium.Marker(loc, icon=icon, popup=f'Hub {i+1}', tooltip=f'Hub {i+1}').add_to(hubs_group)
    hubs_group.add_to(m)

    # Depot
    depot_group = folium.FeatureGroup(name='Depot', show=True)
    folium.Marker(depot_loc, icon=folium.Icon(icon='star', prefix='fa', color='red'), popup='Depot', tooltip='Depot').add_to(depot_group)
    depot_group.add_to(m)

    # Heatmap (off by default)
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
        'vehicle_capacities': data['vehicle_capacities'] + [0] * data['num_hubs'],
        'max_time': max_time,
        'colors': colors_hex,
        'num_vehicles': data['num_vehicles'],
        'depot': data['depot'],
        'transfers': results['transfers'],
        'num_customers': data['num_customers'],
        'time_per_demand_unit': data['time_per_demand_unit'],
        'baseline_distance': data.get('baseline_distance', 0),
        'customer_arrival': customer_arrival
    }
    js_data = convert_to_json_serializable(js_data)
    js_data_json = json.dumps(js_data)

    # CSS with pulse for hubs
    css = '''
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css">
    <style>
    #info-panel { position: absolute; top: 10px; left: 10px; background: rgba(255,255,255,0.8); padding: 10px; border-radius: 5px; z-index: 1000; }
    #controls { position: absolute; top: 10px; right: 10px; background: rgba(255,255,255,0.8); padding: 10px; border-radius: 5px; z-index: 1000; }
    #legend { position: absolute; bottom: 10px; left: 10px; background: rgba(255,255,255,0.8); padding: 10px; border-radius: 5px; z-index: 1000; }
    .spinner { border: 4px solid rgba(0,0,0,0.1); border-left-color: #7983ff; border-radius: 50%; width: 24px; height: 24px; animation: spin 1s linear infinite; position: absolute; top: -30px; left: 0; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .progress { height: 5px; background: green; }
    .pulse { animation: pulse 2s infinite; }
    @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.1); } 100% { transform: scale(1); } }
    </style>
    '''
    m.get_root().header.add_child(folium.Element(css))

    # HTML
    html = '''
    <div id="info-panel">
        <h3>Stats</h3>
        <p>Total Distance: <span id="total-distance"></span> (Baseline: {baseline_distance:.2f})</p>
        <p>Elapsed Time: <span id="elapsed-time"></span></p>
        <p>Colis Delivered: <span id="delivered"></span></p>
        <p>Total Delay: <span id="delay"></span></p>
        <p>Hub Transfers: <span id="transfers"></span></p>
        <p>Avg Capacity: <span id="avg-capacity"></span></p>
    </div>
    <div id="controls">
        <input type="range" min="0" max="{max_time}" value="0" step="1" id="time-slider" aria-label="Time Slider">
        <button id="play" aria-label="Play">Play</button>
        <button id="pause" aria-label="Pause">Pause</button>
        <button id="replay" aria-label="Replay">Replay</button>
        <select id="speed" aria-label="Speed">
            <option value="1">x1</option>
            <option value="2">x2</option>
            <option value="5">x5</option>
        </select>
        <button id="export" aria-label="Export">Export PNG</button>
    </div>
    <div id="legend">
        <h3>Legend</h3>
        <ul>
            <li>Depot: Red Star</li>
            <li>Customers: Blue House</li>
            <li>Hubs: Green Circle</li>
            <li>Livreurs: Colored Bike</li>
        </ul>
    </div>
    '''.format(max_time=max_time, baseline_distance=data.get('baseline_distance', 0))
    m.get_root().html.add_child(folium.Element(html))

    # JS
    map_id = m._id
    script = f'''
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <script>
    var map = map_{map_id};
    var jsData = {js_data_json};
    var vehicleMarkers = [];
    var spinnerMarkers = [];
    var transferMarkers = [];
    var hubMarkers = [];
    jsData.results.transfers.forEach(function(tr, idx) {{
        var icon = L.divIcon({{html: '<div style="background: yellow; padding: 2px;">P</div>', iconSize: [20,20]}});
        var marker = L.marker(jsData.locations[tr.hub], {{icon: icon, opacity: 0}});
        marker.addTo(map);
        transferMarkers.push(marker);
        // Hub pulsing
        var hubIcon = L.divIcon({{html: '<div class="hub-icon"><i class="fa fa-circle" style="color:green; font-size:20px;"></i><i class="fa fa-arrows-alt" style="position:absolute; top:5px; left:5px; color:white; font-size:10px;"></i></div>', iconSize: [20,20]}});
        var hubMarker = L.marker(jsData.locations[tr.hub], {{icon: hubIcon}});
        hubMarker.addTo(map);
        hubMarkers.push(hubMarker);
    }});
    for (var v = 0; v < jsData.num_vehicles; v++) {{
        var cap = jsData.vehicle_capacities[v];
        var iconHtml = '<div style="position: relative;"><div style="position: absolute; top: -40px; left: 0; background: white; padding: 2px; border: 1px solid; width: 100px;">Charge: <span class="charge-text">0/' + cap + '</span><div class="progress" style="width: 100%;"></div></div><i class="fas fa-bicycle" style="color:' + jsData.colors[v] + '; font-size:24px;"></i></div>';
        var icon = L.divIcon({{html: iconHtml, iconSize: [30,30]}});
        var marker = L.marker(jsData.locations[jsData.results.per_livreur.routes[v][0]], {{icon: icon}});
        marker.addTo(map);
        vehicleMarkers.push(marker);
        var spinner = L.divIcon({{html: '<div class="spinner"></div>', iconSize: [24,24]}});
        var spinnerMarker = L.marker([0,0], {{icon: spinner, opacity: 0}});
        spinnerMarker.addTo(map);
        spinnerMarkers.push(spinnerMarker);
    }}
    function updateAtTime(t) {{
        var delivered = 0;
        var total_delay = 0;
        var transfers_done = 0;
        var total_load = 0;
        var total_cap = 0;
        jsData.results.transfers.forEach(function(tr, idx) {{
            if (t >= tr.pickup_t) {{
                transfers_done++;
            }}
            var opacity = (t >= tr.deposit_t && t < tr.pickup_t) ? 1 : 0;
            transferMarkers[idx].setOpacity(opacity);
            if (opacity > 0) {{
                hubMarkers[idx]._icon.classList.add('pulse');
            }} else {{
                hubMarkers[idx]._icon.classList.remove('pulse');
            }}
        }});
        for (var v = 0; v < jsData.num_vehicles; v++) {{
            var route = jsData.results.per_livreur.routes[v];
            var times = jsData.results.per_livreur.estimated_times[v];
            var remainings = jsData.results.per_livreur.remaining_charges[v];
            var slacks = jsData.results.per_livreur.slacks[v];
            var i = 0;
            for (; i < times.length - 1; i++) {{
                if (t < times[i + 1]) break;
            }}
            if (t >= times[times.length - 1]) i = times.length - 2;
            var from = route[i];
            var to = route[i + 1];
            var time_from = times[i];
            var time_to = times[i + 1];
            var slack = slacks[i];
            var service = Math.abs(jsData.demands[from]) * jsData.time_per_demand_unit;
            var depart_time = time_from + service + slack;
            var travel = time_to - depart_time;
            var loc_from = jsData.locations[from];
            var loc_to = jsData.locations[to];
            var is_on_road = t >= depart_time;
            var lat, lng;
            var remaining;
            if (is_on_road) {{
                var fraction = (t - depart_time) / travel;
                fraction = Math.min(1, Math.max(0, fraction));
                lat = loc_from[0] + fraction * (loc_to[0] - loc_from[0]);
                lng = loc_from[1] + fraction * (loc_to[1] - loc_from[1]);
                remaining = remainings[i + 1];
                spinnerMarkers[v].setOpacity(0);
            }} else {{
                lat = loc_from[0];
                lng = loc_from[1];
                remaining = remainings[i];
                var show_spinner = (t > time_from && t < depart_time) ? 1 : 0;
                spinnerMarkers[v].setLatLng([lat, lng]);
                spinnerMarkers[v].setOpacity(show_spinner);
            }}
            vehicleMarkers[v].setLatLng([lat, lng]);
            var html = vehicleMarkers[v].getIcon().options.html;
            html = html.replace(/Charge: \d+\/\d+/, 'Charge: ' + remaining + '/' + jsData.vehicle_capacities[v]);
            var progress_width = (remaining / jsData.vehicle_capacities[v] * 100) || 0;
            var progress_color = progress_width > 50 ? 'green' : 'red';
            html = html.replace(/background: [^;]+; width: [^;]+%/, 'background: ' + progress_color + '; width: ' + progress_width);
            vehicleMarkers[v].setIcon(L.divIcon({{html: html, iconSize: [30,30]}}));
            if (from >= 1 && from <= jsData.num_customers && t >= time_to) {{
                delivered++;
                var tw_end = jsData.time_windows[from][1];
                total_delay += Math.max(0, time_from - tw_end);
            }}
            var load = jsData.vehicle_capacities[v] - remaining;
            total_load += load;
            total_cap += jsData.vehicle_capacities[v];
        }}
        document.getElementById('total-distance').innerText = jsData.results.indicators.total_distance.toFixed(2);
        document.getElementById('elapsed-time').innerText = t;
        document.getElementById('delivered').innerText = delivered;
        document.getElementById('delay').innerText = total_delay.toFixed(2);
        document.getElementById('transfers').innerText = transfers_done;
        document.getElementById('avg-capacity').innerText = (total_load / total_cap * 100).toFixed(2) + '%';
    }}
    var slider = document.getElementById('time-slider');
    slider.addEventListener('input', function() {{ updateAtTime(parseInt(this.value)); }});
    var timer = null;
    var speed = 1;
    document.getElementById('play').addEventListener('click', function() {{
        if (timer) clearInterval(timer);
        timer = setInterval(function() {{
            var val = parseInt(slider.value) + speed;
            if (val > jsData.max_time) {{
                clearInterval(timer);
                return;
            }}
            slider.value = val;
            updateAtTime(val);
        }}, 50);
    }});
    document.getElementById('pause').addEventListener('click', function() {{ clearInterval(timer); }});
    document.getElementById('replay').addEventListener('click', function() {{
        clearInterval(timer);
        slider.value = 0;
        updateAtTime(0);
    }});
    document.getElementById('speed').addEventListener('change', function() {{ speed = parseInt(this.value); }});
    document.getElementById('export').addEventListener('click', function() {{
        html2canvas(document.querySelector('#map_{map_id}')).then(canvas => {{
            var link = document.createElement('a');
            link.download = 'vrp_visualization.png';
            link.href = canvas.toDataURL();
            link.click();
        }});
    }});
    updateAtTime(0);
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