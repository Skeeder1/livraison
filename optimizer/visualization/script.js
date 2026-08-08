// File: script.js
window.addEventListener('load', function() {
    var map = map_{map_id};
    var jsData = {js_data_json};

    // ── Déplacement le long du réseau routier ────────────────────────────
    // `jsData.road_legs` contient, pour chaque segment client→client, la
    // polyligne de l'itinéraire réel (OSRM). Interpoler le long de cette
    // polyligne — et non entre les deux extrémités — fait suivre les rues aux
    // livreurs. Les longueurs cumulées sont mises en cache : elles sont
    // recalculées à chaque image sinon, pour chaque véhicule.
    var legLengthCache = {};

    function legMetrics(leg) {
        var lengths = [0];
        var total = 0;
        for (var k = 1; k < leg.length; k++) {
            var dLat = leg[k][0] - leg[k - 1][0];
            var dLng = leg[k][1] - leg[k - 1][1];
            total += Math.sqrt(dLat * dLat + dLng * dLng);
            lengths.push(total);
        }
        return { lengths: lengths, total: total };
    }

    function pointAlongLeg(key, leg, fraction) {
        if (!leg || leg.length < 2) { return null; }
        var metrics = legLengthCache[key];
        if (!metrics) {
            metrics = legMetrics(leg);
            legLengthCache[key] = metrics;
        }
        if (metrics.total === 0) { return leg[0]; }

        // Recherche dichotomique du tronçon contenant la distance visée.
        var target = fraction * metrics.total;
        var lo = 0;
        var hi = metrics.lengths.length - 1;
        while (lo < hi - 1) {
            var mid = (lo + hi) >> 1;
            if (metrics.lengths[mid] <= target) { lo = mid; } else { hi = mid; }
        }
        var span = metrics.lengths[hi] - metrics.lengths[lo];
        var f = span > 0 ? (target - metrics.lengths[lo]) / span : 0;
        return [
            leg[lo][0] + f * (leg[hi][0] - leg[lo][0]),
            leg[lo][1] + f * (leg[hi][1] - leg[lo][1])
        ];
    }

    // Count real vehicles (exclude dummy vehicles)
    var num_real_vehicles = jsData.vehicle_capacities.length;
    for (var i = 0; i < jsData.vehicle_capacities.length; i++) {
        if (jsData.vehicle_capacities[i] === 0) {
            num_real_vehicles = i;
            break;
        }
    }
    var vehicleMarkers = [];
    var spinnerMarkers = [];
    var transferMarkers = [];
    jsData.results.transfers.forEach(function(tr) {
        var icon = L.divIcon({html: '<div style="background: yellow; padding: 2px;">P</div>', iconSize: [20,20]});
        var marker = L.marker(jsData.locations[tr.hub], {icon: icon, opacity: 0});
        marker.addTo(map);
        transferMarkers.push(marker);
    });
    // Only create markers for real vehicles, not dummy vehicles
    for (var v = 0; v < num_real_vehicles; v++) {
        var cap = jsData.vehicle_capacities[v];
        // Display initial full charge
        var iconHtml = '<div style="position: relative;"><div style="position: absolute; top: -40px; left: 0; background: white; padding: 2px; border: 1px solid; width: 100px;">Charge: <span class="charge-text">' + cap + '/' + cap + '</span><div class="progress" style="background: green; width: 100%; height: 8px; border-radius: 4px;"></div></div><i class="fas fa-bicycle" style="color:' + jsData.colors[v] + '; font-size:24px;"></i></div>';
        var icon = L.divIcon({html: iconHtml, iconSize: [30,30]});
        var marker = L.marker(jsData.locations[jsData.results.per_livreur.routes[v][0]], {icon: icon});
        marker.addTo(map);
        vehicleMarkers.push(marker);
        var spinner = L.divIcon({html: '<div class="spinner"></div>', iconSize: [24,24]});
        var spinnerMarker = L.marker([0,0], {icon: spinner, opacity: 0});
        spinnerMarker.addTo(map);
        spinnerMarkers.push(spinnerMarker);
    }
    function updateAtTime(t) {
        var delivered = 0;
        var total_delay = 0;
        var transfers_done = 0;
        var total_load = 0;
        var total_cap = 0;
        jsData.results.transfers.forEach(function(tr, idx) {
            if (t >= tr.pickup_t) {
                transfers_done++;
            }
            var opacity = (t >= tr.deposit_t && t < tr.pickup_t) ? 1 : 0;
            transferMarkers[idx].setOpacity(opacity);
        });
        // Only process real vehicles, not dummy vehicles
        for (var v = 0; v < num_real_vehicles; v++) {
            var route = jsData.results.per_livreur.routes[v];
            var times = jsData.results.per_livreur.estimated_times[v];
            var cumulative_loads = jsData.results.per_livreur.cumulative_loads[v];
            var slacks = jsData.results.per_livreur.slacks[v];

            // Vérifications de sécurité
            if (!route || !times || !cumulative_loads || !slacks) {
                console.warn("Missing data for vehicle", v, {route: !!route, times: !!times, cumulative_loads: !!cumulative_loads, slacks: !!slacks});
                continue;
            }
            var i = 0;
            for (; i < times.length - 1; i++) {
                if (t < times[i + 1]) break;
            }
            if (t >= times[times.length - 1]) i = times.length - 2;
            i = Math.max(0, Math.min(i, times.length - 2)); // Ensure i is in valid range


            // Safety check: ensure we have valid indices
            if (i < 0 || i >= route.length - 1 || i >= times.length - 1) {
                console.warn("Invalid index for vehicle", v, "i:", i, "route.length:", route.length, "times.length:", times.length);
                continue;
            }

            var from = route[i];
            var to = route[i + 1];
            var time_from = times[i];
            var time_to = times[i + 1];
            var slack = slacks[i];
            var service = Math.abs(jsData.demands[from]) * jsData.time_per_demand_unit;
            var service_end = time_from + service;
            var depart_time = time_from + service + slack;
            var travel = time_to - depart_time;
            var loc_from = jsData.locations[from];
            var loc_to = jsData.locations[to];
            var lat, lng;
            var current_load;

            // Determine current phase
            var phase = "idle"; // default
            if (t < time_from) {
                phase = "idle"; // hasn't reached this node yet
            } else if (t < service_end) {
                phase = "service"; // actively loading/unloading
            } else if (t < depart_time) {
                phase = "waiting"; // waiting for time window
            } else if (t < time_to) {
                phase = "travel"; // in transit
            } else {
                phase = "idle"; // already left this segment
            }


            // Calculate position and load based on phase
            if (phase === "service" || phase === "waiting") {
                // Vehicle is at current node (stationary)
                lat = loc_from[0];
                lng = loc_from[1];
                current_load = cumulative_loads[i];
                spinnerMarkers[v].setLatLng([lat, lng]);
                spinnerMarkers[v].setOpacity(phase === "service" ? 1 : 0);
            } else if (phase === "travel") {
                // Vehicle is in transit
                var fraction = (t - depart_time) / travel;
                fraction = Math.min(1, Math.max(0, fraction));
                // Suivre l'itinéraire routier quand il est disponible ; sinon,
                // repli sur le segment droit (cas hors ligne).
                var legKey = from + '-' + to;
                var roadLeg = jsData.road_legs ? jsData.road_legs[legKey] : null;
                var roadPoint = pointAlongLeg(legKey, roadLeg, fraction);
                if (roadPoint) {
                    lat = roadPoint[0];
                    lng = roadPoint[1];
                } else {
                    lat = loc_from[0] + fraction * (loc_to[0] - loc_from[0]);
                    lng = loc_from[1] + fraction * (loc_to[1] - loc_from[1]);
                }
                current_load = cumulative_loads[i];
                spinnerMarkers[v].setOpacity(0);
            } else if (phase === "idle" && t >= time_to) {
                // Already reached the destination of this segment
                lat = loc_to[0];
                lng = loc_to[1];
                // Use current segment's load
                current_load = cumulative_loads[i];
                spinnerMarkers[v].setOpacity(0);
            } else {
                // Idle (hasn't reached segment yet)
                lat = loc_from[0];
                lng = loc_from[1];
                current_load = cumulative_loads[i];
                spinnerMarkers[v].setOpacity(0);
            }
            
            // Les transferts sont déjà pris en compte dans les données du solver (cumulative_loads)
            // Pas besoin de recalculer ici
            
            vehicleMarkers[v].setLatLng([lat, lng]);
            var capacity = jsData.vehicle_capacities[v];

            // current_load est maintenant directement la charge actuelle (colis transportés)
            // S'assurer que current_load est valide
            current_load = Math.max(0, Math.min(capacity, current_load));


            // Reconstruire l'HTML pour s'assurer que la charge et la barre de progression sont correctement mises à jour
            var progress_width = (current_load / capacity * 100);
            // Inverser les couleurs: vert = charge élevée, rouge = charge faible
            var progress_color = progress_width > 80 ? 'green' : (progress_width > 30 ? 'orange' : 'red');
            var cap = capacity;
            var vehicle_color = jsData.colors[v];

            // Change vehicle color based on phase
            var phase_color = vehicle_color;
            var phase_label = '';
            if (phase === "service") {
                phase_color = 'orange';
                phase_label = '🔄 En service';
            } else if (phase === "waiting") {
                phase_color = '#FFD700'; // Gold/yellow
                phase_label = '⏳ En attente';
            } else if (phase === "travel") {
                phase_color = vehicle_color;
                phase_label = '🚚 En route';
            } else {
                phase_color = '#CCCCCC'; // Gray for idle
                phase_label = '';
            }

            // Récréer le HTML complètement pour éviter les problèmes de regex
            var newIconHtml = '<div style="position: relative;"><div style="position: absolute; top: -50px; left: -20px; background: white; padding: 3px 5px; border: 1px solid #999; border-radius: 3px; width: 110px; font-size: 11px; text-align: center;"><div style="color: #333; font-weight: bold; margin-bottom: 2px;">' + phase_label + '</div><div>Charge: <span class="charge-text">' + Math.round(current_load) + '/' + cap + '</span></div><div class="progress" style="background: ' + progress_color + '; width: 100%; height: 6px; border-radius: 3px; margin-top: 2px;"></div></div><i class="fas fa-bicycle" style="color:' + phase_color + '; font-size:24px; text-shadow: 1px 1px 2px rgba(0,0,0,0.3);"></i></div>';
            vehicleMarkers[v].setIcon(L.divIcon({html: newIconHtml, iconSize: [30,30]}));

            // Count all customers delivered so far on this vehicle's route
            for (var j = 1; j < route.length; j++) {
                var customer_node = route[j];
                var customer_arrival_time = times[j];

                // Check if it's a customer node and we've reached it
                if (customer_node >= 1 && customer_node <= jsData.num_customers && t >= customer_arrival_time) {
                    delivered++;
                    var tw_end = jsData.time_windows[customer_node][1];
                    total_delay += Math.max(0, customer_arrival_time - tw_end);
                }
            }

            total_load += current_load;
            total_cap += capacity;
        }
        document.getElementById('total-distance').innerText = jsData.results.indicators.total_distance.toFixed(2);
        document.getElementById('elapsed-time').innerText = t;
        document.getElementById('delivered').innerText = delivered;
        document.getElementById('delay').innerText = total_delay.toFixed(2);
        document.getElementById('transfers').innerText = transfers_done;
        document.getElementById('avg-capacity').innerText = (total_load / total_cap * 100).toFixed(2) + '%';

        // Display vehicle phases for debugging/transparency
        var phaseInfo = '';
        for (var v = 0; v < num_real_vehicles; v++) {
            var route = jsData.results.per_livreur.routes[v];
            var times = jsData.results.per_livreur.estimated_times[v];
            if (!times || times.length === 0) continue;

            var i = 0;
            for (; i < times.length - 1; i++) {
                if (t < times[i + 1]) break;
            }
            if (t >= times[times.length - 1]) i = times.length - 2;
            i = Math.max(0, i);

            var time_from = times[i];
            var time_to = times[i + 1];
            var slacks = jsData.results.per_livreur.slacks[v];
            var slack = slacks[i] || 0;
            var service = Math.abs(jsData.demands[route[i]]) * jsData.time_per_demand_unit;
            var service_end = time_from + service;
            var depart_time = time_from + service + slack;

            var vPhase = 'Idle';
            if (t >= time_from && t < service_end) vPhase = 'Service';
            else if (t >= service_end && t < depart_time) vPhase = 'Waiting';
            else if (t >= depart_time && t < time_to) vPhase = 'Travel';

            var phaseEmoji = vPhase === 'Service' ? '🔄' : (vPhase === 'Waiting' ? '⏳' : (vPhase === 'Travel' ? '🚚' : ''));
            phaseInfo += 'V' + (v+1) + ': ' + phaseEmoji + ' ' + vPhase + ' | ';
        }
        if (document.getElementById('phase-info')) {
            document.getElementById('phase-info').innerText = phaseInfo;
        }
    }
    var slider = document.getElementById('time-slider');
    slider.addEventListener('input', function() { updateAtTime(parseInt(this.value)); });
    var timer = null;
    var speed = 1;
    document.getElementById('play').addEventListener('click', function() {
        clearInterval(timer);
        timer = setInterval(function() {
            var val = parseInt(slider.value) + speed;
            if (val > jsData.max_time) {
                clearInterval(timer);
                return;
            }
            slider.value = val;
            updateAtTime(val);
        }, 50);
    });
    document.getElementById('pause').addEventListener('click', function() { clearInterval(timer); });
    document.getElementById('replay').addEventListener('click', function() {
        clearInterval(timer);
        slider.value = 0;
        updateAtTime(0);
    });
    document.getElementById('speed').addEventListener('change', function() { speed = parseInt(this.value); });
    document.getElementById('export').addEventListener('click', function() {
        html2canvas(document.querySelector('#map_{map_id}')).then(canvas => {
            var link = document.createElement('a');
            link.download = 'vrp_visualization.png';
            link.href = canvas.toDataURL();
            link.click();
        });
    });
    updateAtTime(0);
    
    // Test debug : forcer un affichage à t=50 pour voir l'évolution
    setTimeout(function() {
        updateAtTime(50);
    }, 1000);
    
});