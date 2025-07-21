def extract_solution_steps(data, manager, routing, assignment):
    """
    Extracts the information (coordinates, time, load, demands) from the solution
    to be used in the HTML/JS visualization.

    Returns a dictionary structured as follows:
    {
        'vehicles': [
            {
                'vehicle_id': 0,
                'steps': [
                    {
                       'index': routingIndex,
                       'node': managerIndexToNode,
                       'x': x_coordinate_in_meters,
                       'y': y_coordinate_in_meters,
                       'time': timeCumul,
                       'load': loadCumul
                    },
                    ...
                ],
                'color': '#FF0000',  # color for vehicle
            },
            ...
        ],
        'depots': [...],
        'hubs': [...],
        'delivery_points': [...],
        'max_time': ...
    }
    """
    # Colors for the vehicles (cycle if more vehicles than colors)
    vehicle_colors = ["#FF0000", "#0000FF", "#008000", "#800080", "#FFA500"]
    
    capacity_dim = routing.GetDimensionOrDie('Capacity')
    time_dim = routing.GetDimensionOrDie('Time')

    # 1) Collect "steps" for each vehicle
    vehicles_data = []
    max_time = 0
    
    for vehicle_id in range(data['num_vehicles']):
        color = vehicle_colors[vehicle_id % len(vehicle_colors)]
        index = routing.Start(vehicle_id)
        vehicle_steps = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            x_coord, y_coord = data['locations'][node]
            
            load = assignment.Value(capacity_dim.CumulVar(index))
            time_cumul = assignment.Value(time_dim.CumulVar(index))
            max_time = max(max_time, time_cumul)
            
            vehicle_steps.append({
                'index': index,
                'node': node,
                'x': x_coord,
                'y': y_coord,
                'time': time_cumul,
                'load': load
            })
            index = assignment.Value(routing.NextVar(index))
        # Add the end index
        node = manager.IndexToNode(index)
        x_coord, y_coord = data['locations'][node]

        load = assignment.Value(capacity_dim.CumulVar(index))
        time_cumul = assignment.Value(time_dim.CumulVar(index))
        max_time = max(max_time, time_cumul)
        
        vehicle_steps.append({
            'index': index,
            'node': node,
            'x': x_coord,
            'y': y_coord,
            'time': time_cumul,
            'load': load
        })
        
        vehicles_data.append({
            'vehicle_id': vehicle_id,
            'steps': vehicle_steps,
            'color': color
        })

    # 2) Separate out depots, hubs, and delivery points
    depots_info = []
    hubs_info = []
    delivery_points_info = []

    # Repérer les indices de hub
    hub_indices = []
    if 'hub_deposit' in data and 'hub_pickup' in data:
        hub_indices = [data['hub_deposit'], data['hub_pickup']]

    for node_id in range(data['num_locations']):
        x_coord, y_coord = data['locations'][node_id]
        demand = data['demands'][node_id]

        # On considère 0..5 comme des "depots" (dépôt principal + reloads)
        if node_id < 6:
            depots_info.append({
                'node': node_id,
                'x': x_coord,
                'y': y_coord,
                'demand': demand
            })
        # S'il fait partie des hubs
        elif node_id in hub_indices:
            hubs_info.append({
                'node': node_id,
                'x': x_coord,
                'y': y_coord,
                'demand': demand
            })
        # Sinon, c'est un point de livraison "classique"
        else:
            delivery_points_info.append({
                'node': node_id,
                'x': x_coord,
                'y': y_coord,
                'demand': demand
            })

    return {
        'vehicles': vehicles_data,
        'depots': depots_info,
        'hubs': hubs_info,
        'delivery_points': delivery_points_info,
        'max_time': max_time
    }


def generate_html_visualization(solution_data, data):
    """
    Generates a single string containing the complete HTML, CSS, and JavaScript
    needed to visualize the solution (depots, hubs, deliveries, vehicles).
    """
    # 1) Calcul de l'échelle d'affichage
    all_x = [pt['x'] for pt in solution_data['depots']] + \
            [pt['x'] for pt in solution_data['hubs']] + \
            [pt['x'] for pt in solution_data['delivery_points']]
    all_y = [pt['y'] for pt in solution_data['depots']] + \
            [pt['y'] for pt in solution_data['hubs']] + \
            [pt['y'] for pt in solution_data['delivery_points']]
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)

    width_px = 1200
    height_px = 800
    range_x = max_x - min_x if (max_x - min_x) != 0 else 1
    range_y = max_y - min_y if (max_y - min_y) != 0 else 1
    scale_x = width_px / range_x
    scale_y = height_px / range_y
    scale = min(scale_x, scale_y)

    def scale_point(x, y):
        """Scale the coordinates for visualization."""
        scaled_x = (x - min_x) * scale
        scaled_y = (y - min_y) * scale
        return scaled_x, scaled_y

    # 2) Préparation des données JSON pour le JS
    vehicles_js = []
    for v in solution_data['vehicles']:
        steps_js = []
        for step in v['steps']:
            sx, sy = scale_point(step['x'], step['y'])
            steps_js.append({
                'node': step['node'],
                'time': step['time'],
                'x': sx,
                'y': sy,
                'load': step['load']
            })
        vehicles_js.append({
            'vehicle_id': v['vehicle_id'],
            'color': v['color'],
            'steps': steps_js
        })

    depots_js = []
    for d in solution_data['depots']:
        sx, sy = scale_point(d['x'], d['y'])
        depots_js.append({
            'node': d['node'],
            'x': sx,
            'y': sy,
            'demand': d['demand']
        })

    hubs_js = []
    for h in solution_data['hubs']:
        sx, sy = scale_point(h['x'], h['y'])
        hubs_js.append({
            'node': h['node'],
            'x': sx,
            'y': sy,
            'demand': h['demand']
        })

    deliveries_js = []
    for d in solution_data['delivery_points']:
        sx, sy = scale_point(d['x'], d['y'])
        deliveries_js.append({
            'node': d['node'],
            'x': sx,
            'y': sy,
            'demand': d['demand']
        })

    max_time = solution_data['max_time']

    # 3) Construction de la page HTML
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8" />
    <title>CVRP Visualization</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
        }}
        #mapContainer {{
            position: relative;
            width: {width_px}px;
            height: {height_px}px;
            margin: 20px auto;
            background: #f0f0f0; /* Simple background color */
            border: 2px solid #444;
        }}
        .depotIcon {{
            width: 24px;
            height: 24px;
            background: url('https://cdn-icons-png.flaticon.com/512/190/190488.png') no-repeat center center;
            background-size: contain;
            position: absolute;
            transform: translate(-12px, -12px);
        }}
        .hubIcon {{
            width: 24px;
            height: 24px;
            background: url('https://cdn-icons-png.flaticon.com/512/252/252025.png') no-repeat center center;
            background-size: contain;
            position: absolute;
            transform: translate(-12px, -12px);
        }}
        .deliveryIcon {{
            width: 20px;
            height: 20px;
            background: url('https://cdn-icons-png.flaticon.com/512/190/190411.png') no-repeat center center;
            background-size: contain;
            position: absolute;
            transform: translate(-10px, -10px);
        }}
        .vehicleIcon {{
            width: 26px;
            height: 26px;
            background: url('https://cdn-icons-png.flaticon.com/512/477/477579.png') no-repeat center center;
            background-size: contain;
            position: absolute;
            transform: translate(-13px, -13px);
        }}
        .label {{
            position: absolute;
            background: white;
            color: black;
            padding: 2px 4px;
            border-radius: 3px;
            font-size: 12px;
            border: 1px solid #666;
        }}
        #timeSlider {{
            width: 50%;
            margin: 20px auto;
            display: block;
        }}
        #infoPanel {{
            width: 50%;
            margin: 10px auto;
            text-align: center;
            font-family: sans-serif;
        }}
        #infoPanel span {{
            margin: 0 10px;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <h2 style="text-align:center;">CVRP Solution Visualization</h2>
    <input id="timeSlider" type="range" min="0" max="{max_time}" value="0" />
    <div id="infoPanel">
        Time: <span id="currentTime">0</span> / {max_time}
    </div>
    <div id="mapContainer">
    </div>
    <script>
        let depotsData = {depots_js};
        let hubsData = {hubs_js};
        let deliveriesData = {deliveries_js};
        let vehiclesData = {vehicles_js};

        let mapContainer = document.getElementById("mapContainer");

        // --- Add depots ---
        depotsData.forEach(d => {{
            let icon = document.createElement("div");
            icon.className = "depotIcon";
            icon.style.left = d.x + "px";
            icon.style.top = d.y + "px";
            mapContainer.appendChild(icon);

            let label = document.createElement("div");
            label.className = "label";
            label.style.left = (d.x + 12) + "px";
            label.style.top = (d.y + 12) + "px";
            label.textContent = "Depot " + d.node + " (dem:"+ d.demand +")";
            mapContainer.appendChild(label);
        }});

        // --- Add hubs ---
        hubsData.forEach(h => {{
            let icon = document.createElement("div");
            icon.className = "hubIcon";
            icon.style.left = h.x + "px";
            icon.style.top = h.y + "px";
            mapContainer.appendChild(icon);

            let label = document.createElement("div");
            label.className = "label";
            label.style.left = (h.x + 12) + "px";
            label.style.top = (h.y + 12) + "px";
            label.textContent = "Hub " + h.node + " (dem:"+ h.demand +")";
            mapContainer.appendChild(label);
        }});

        // --- Add deliveries ---
        deliveriesData.forEach(dp => {{
            let icon = document.createElement("div");
            icon.className = "deliveryIcon";
            icon.style.left = dp.x + "px";
            icon.style.top = dp.y + "px";
            mapContainer.appendChild(icon);

            let label = document.createElement("div");
            label.className = "label";
            label.style.left = (dp.x + 10) + "px";
            label.style.top = (dp.y + 10) + "px";
            label.textContent = "Loc " + dp.node + " (dem:"+ dp.demand +")";
            mapContainer.appendChild(label);
        }});

        // --- Add vehicles ---
        let vehicleElements = vehiclesData.map(v => {{
            let vehicleEl = document.createElement("div");
            vehicleEl.className = "vehicleIcon";
            vehicleEl.style.border = "2px solid " + v.color;
            mapContainer.appendChild(vehicleEl);

            let vehicleLabel = document.createElement("div");
            vehicleLabel.className = "label";
            vehicleLabel.style.borderColor = v.color;
            vehicleLabel.style.borderWidth = "2px";
            vehicleLabel.style.borderStyle = "solid";
            vehicleLabel.textContent = "V" + v.vehicle_id + " load:?";
            mapContainer.appendChild(vehicleLabel);

            return {{
                vehicle_id: v.vehicle_id,
                color: v.color,
                steps: v.steps,
                iconEl: vehicleEl,
                labelEl: vehicleLabel
            }};
        }});

        function updateVehiclePositions(currentT) {{
            vehicleElements.forEach(ve => {{
                let steps = ve.steps;
                if (steps.length == 1 || currentT <= steps[0].time) {{
                    placeVehicle(ve, steps[0]);
                    return;
                }}
                if (currentT >= steps[steps.length - 1].time) {{
                    placeVehicle(ve, steps[steps.length - 1]);
                    return;
                }}
                for (let i = 0; i < steps.length - 1; i++) {{
                    let s1 = steps[i];
                    let s2 = steps[i+1];
                    if (s1.time <= currentT && currentT < s2.time) {{
                        let ratio = (currentT - s1.time) / (s2.time - s1.time);
                        let x = s1.x + ratio * (s2.x - s1.x);
                        let y = s1.y + ratio * (s2.y - s1.y);
                        // On suppose load instantané => on garde s1.load
                        placeVehicle(ve, {{ x: x, y: y, load: s1.load }});
                        return;
                    }}
                }}
            }});
        }}

        function placeVehicle(ve, step) {{
            ve.iconEl.style.left = step.x + "px";
            ve.iconEl.style.top = step.y + "px";
            ve.labelEl.style.left = (step.x + 15) + "px";
            ve.labelEl.style.top = (step.y + 15) + "px";
            ve.labelEl.textContent = "V" + ve.vehicle_id + " load:" + step.load;
        }}

        let slider = document.getElementById("timeSlider");
        let currentTimeSpan = document.getElementById("currentTime");
        
        slider.addEventListener("input", () => {{
            let val = parseInt(slider.value, 10);
            currentTimeSpan.textContent = val;
            updateVehiclePositions(val);
        }});

        // Initial placement at time=0
        updateVehiclePositions(0);
    </script>
</body>
</html>
    """

    return html_content
