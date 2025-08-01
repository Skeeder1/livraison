// File: script.js
window.addEventListener('load', function() {
    console.log("Custom script starting");
    console.log("Map ID: {map_id}");
    var map = map_{map_id};
    console.log("Map object:", map);
    var jsData = {js_data_json};
    console.log("jsData loaded:", jsData);
    var vehicleMarkers = [];
    var spinnerMarkers = [];
    var transferMarkers = [];
    jsData.results.transfers.forEach(function(tr) {
        console.log("Adding transfer marker for hub:", tr.hub);
        var icon = L.divIcon({html: '<div style="background: yellow; padding: 2px;">P</div>', iconSize: [20,20]});
        var marker = L.marker(jsData.locations[tr.hub], {icon: icon, opacity: 0});
        marker.addTo(map);
        transferMarkers.push(marker);
    });
    for (var v = 0; v < jsData.num_vehicles; v++) {
        console.log("Adding vehicle marker for vehicle:", v);
        var cap = jsData.vehicle_capacities[v];
        var iconHtml = '<div style="position: relative;"><div style="position: absolute; top: -40px; left: 0; background: white; padding: 2px; border: 1px solid; width: 100px;">Charge: <span class="charge-text">0/' + cap + '</span><div class="progress" style="width: 100%;"></div></div><i class="fas fa-bicycle" style="color:' + jsData.colors[v] + '; font-size:24px;"></i></div>';
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
        console.log("Updating at time:", t);
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
        for (var v = 0; v < jsData.num_vehicles; v++) {
            var route = jsData.results.per_livreur.routes[v];
            var times = jsData.results.per_livreur.estimated_times[v];
            var remainings = jsData.results.per_livreur.remaining_charges[v];
            var slacks = jsData.results.per_livreur.slacks[v];
            var i = 0;
            for (; i < times.length - 1; i++) {
                if (t < times[i + 1]) break;
            }
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
            if (is_on_road) {
                var fraction = (t - depart_time) / travel;
                fraction = Math.min(1, Math.max(0, fraction));
                lat = loc_from[0] + fraction * (loc_to[0] - loc_from[0]);
                lng = loc_from[1] + fraction * (loc_to[1] - loc_from[1]);
                remaining = remainings[i + 1];
                spinnerMarkers[v].setOpacity(0);
            } else {
                lat = loc_from[0];
                lng = loc_from[1];
                remaining = remainings[i];
                var show_spinner = t > time_from && t < depart_time;
                spinnerMarkers[v].setLatLng([lat, lng]);
                spinnerMarkers[v].setOpacity(show_spinner ? 1 : 0);
            }
            vehicleMarkers[v].setLatLng([lat, lng]);
            var icon = vehicleMarkers[v].getIcon();
            var html = icon.options.html.replace(/Charge: [^<]+/, 'Charge: ' + remaining + '/' + jsData.vehicle_capacities[v]);
            var progress_width = (remaining / jsData.vehicle_capacities[v] * 100);
            var progress_color = progress_width > 50 ? 'green' : 'red';
            html = html.replace(/background: [^;]+; width: [^;]+;/, 'background: ' + progress_color + '; width: ' + progress_width + '%;');
            vehicleMarkers[v].setIcon(L.divIcon({html: html, iconSize: [30,30]}));
            if (from >= 1 && from <= jsData.num_customers && t >= time_to) {
                delivered++;
                var tw_end = jsData.time_windows[from][1];
                total_delay += Math.max(0, time_from - tw_end);
            }
            var load = jsData.vehicle_capacities[v] - remaining;
            total_load += load;
            total_cap += jsData.vehicle_capacities[v];
        }
        document.getElementById('total-distance').innerText = jsData.results.indicators.total_distance.toFixed(2);
        document.getElementById('elapsed-time').innerText = t;
        document.getElementById('delivered').innerText = delivered;
        document.getElementById('delay').innerText = total_delay.toFixed(2);
        document.getElementById('transfers').innerText = transfers_done;
        document.getElementById('avg-capacity').innerText = (total_load / total_cap * 100).toFixed(2) + '%';
        console.log("Update complete for time:", t);
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
    console.log("Custom script ended");
});