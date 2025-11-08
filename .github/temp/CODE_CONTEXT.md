# Code Context: Dummy Vehicles and Time Constraints

## What Are Dummy Vehicles?

Dummy vehicles are a **solver implementation detail**, not real delivery vehicles.

### Why They Exist

In the hub-transfer architecture, packages must be:
1. Delivered to a hub by one vehicle (unload)
2. Picked up from a hub by another vehicle (reload)

The connection between "unload" and "pickup" nodes is managed by dummy vehicles. This is a constraint implementation technique used in OR-Tools routing problems.

### Configuration in solver.py

**Lines 59-72: Create dummy vehicles**
```python
def setup_data_extensions(data):
    # ... line 61 ...
    num_real_vehicles = data['num_vehicles']  # Save real count
    
    # ... lines 63-69 ...
    for _ in range(data['num_hubs']):
        dummy = current_num
        data['locations'].append(data['locations'][data['depot']])
        # Each dummy node is at the depot location
        data['demands'].append(0)  # No cargo handling
        data['time_windows'].append((0, data['vehicle_max_time']))
        data['dummy_nodes'].append(dummy)
        current_num += 1

    # Lines 71-77: Extend data structures for dummies
    data['num_locations'] = len(data['locations'])
    data['num_vehicles'] = num_real_vehicles + data['num_hubs']  # 3 + 2 = 5

    vehicle_capacities += [0] * data['num_hubs']  # [10,10,10,0,0]
    vehicle_max_times = [data['end_times'][v] - data['start_times'][v] 
                         for v in range(num_real_vehicles)]
    vehicle_max_times += [data['vehicle_max_time']] * data['num_hubs']  
    # [86400, 86400, 86400, 1440000, 1440000]
```

### Time Window Configuration

**Lines 347-354: Set dummy vehicle time limits**
```python
def setup_time_constraints(routing, manager, data, time_dimension, num_real_vehicles):
    # ... (real vehicles: lines 338-345) ...
    
    # For dummy vehicles
    for i in range(data['num_hubs']):
        vehicle_id = num_real_vehicles + i  # vehicle_id = 3, 4
        index = routing.Start(vehicle_id)
        # Allow start time 0 to max
        time_dimension.CumulVar(index).SetRange(0, data['vehicle_max_time'])
        routing.AddToAssignment(time_dimension.SlackVar(index))
        
        end_index = routing.End(vehicle_id)
        # SET END TIME TO MAXIMUM (1,440,000 seconds = 400 hours)
        time_dimension.CumulVar(end_index).SetValue(data['vehicle_max_time'])  # Line 354
```

**Why line 354 sets end time to 1,440,000:**
- Dummy vehicles should be able to complete any valid route
- Setting to max time ensures no time violations
- These vehicles are not "real" - the time is meaningless
- It's a constraint artifact, not a target end time

### Vehicle Configuration Summary

```python
# From config.py
data['vehicle_max_time'] = 1440000  # 400 hours (24 * 60 * 60 seconds)

# Result for test case (3 real + 2 hubs):
data['num_vehicles'] = 5

vehicles_info = [
    {'id': 0, 'type': 'real',  'capacity': 10, 'start': 0, 'end': 86400},
    {'id': 1, 'type': 'real',  'capacity': 10, 'start': 0, 'end': 86400},
    {'id': 2, 'type': 'real',  'capacity': 10, 'start': 0, 'end': 86400},
    {'id': 3, 'type': 'dummy', 'capacity':  0, 'start': 0, 'end': 1440000},  # <- BUG: included in sum
    {'id': 4, 'type': 'dummy', 'capacity':  0, 'start': 0, 'end': 1440000},  # <- BUG: included in sum
]
```

---

## How The Bug Manifests

### In postprocessor.py get_results()

**Lines 283-354: Process all vehicles**
```python
for v in range(data['num_vehicles']):  # v = 0, 1, 2, 3, 4
    # ... extract route, times, loads for each vehicle ...
    
    # Dummy vehicles also get their times extracted:
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        times.append(solution.Value(time_dimension.CumulVar(index)))
        # ... update node ... 
        index = solution.Value(routing.NextVar(index))
    
    final_node = manager.IndexToNode(index)
    route.append(final_node)
    times.append(solution.Value(time_dimension.CumulVar(index)))  # LAST TIME = 1,440,000
    
    routes.append(route)
    estimated_times.append(times)  # Includes dummy vehicles' times!
```

**Line 378: The Bug**
```python
# estimated_times = [
#     [0, ..., 59617],          # Vehicle 0 (real): 16h 33m 37s
#     [0, ..., 61063],          # Vehicle 1 (real): 16h 57m 43s
#     [0, ..., 14551],          # Vehicle 2 (real): 4h 2m 31s
#     [13h11m38s, 1440000],     # Vehicle 3 (dummy): 400h ← PROBLEM
#     [13h12m39s, 1440000],     # Vehicle 4 (dummy): 400h ← PROBLEM
# ]

total_time_all_vehicles = sum(times[-1] if times else 0 for times in estimated_times)
# = 59617 + 61063 + 14551 + 1440000 + 1440000
# = 3,015,231 seconds
# = 837 hours 33 minutes 51 seconds ← WRONG!
```

---

## Why This Specific Value?

### Where 1,440,000 Comes From

1. **config.py line 48:**
   ```python
   END_TIME_MAX = 200000  # Config value
   ```

2. **solver.py line 21:**
   ```python
   data['vehicle_max_time'] = 1440000
   ```

3. **This is used for:**
   - Dummy vehicle time limits (line 77)
   - Dummy vehicle end times (line 354)
   - Time window ranges for dummy nodes (line 67)

### Breakdown of 1,440,000 Seconds

```
1,440,000 seconds = ?

1,440,000 ÷ 60 = 24,000 minutes
24,000 ÷ 60 = 400 hours
400 ÷ 24 = 16.67 days

Or more directly:
1,440,000 ÷ 86,400 (seconds in a day) = 16.67 days
```

This is meant to represent "a long time" to avoid constraint violations, but it's completely unrealistic for actual delivery metrics.

---

## The Solution Explained

### Why num_real_vehicles Must Be Tracked

The solver needs to know which vehicles are real vs. dummy:

```python
# Dummy vehicles:
num_real_vehicles = data['num_vehicles'] - data['num_hubs']

# For 3 real + 2 hubs:
num_real_vehicles = 5 - 2 = 3  ✓ Correct

# So when calculating time:
total_time_all_vehicles = sum(
    times[-1] if times else 0 
    for times in estimated_times[:num_real_vehicles]  # Only [0:3]
)
# = 59617 + 61063 + 14551
# = 135,231 seconds
# = 37 hours 33 minutes 51 seconds ✓ CORRECT
```

### Implementation Pattern

**Most appropriate: Store in data dict (no API changes)**
```python
# solver.py line 72
data['num_real_vehicles'] = num_real_vehicles

# postprocessor.py line 378
num_real_vehicles = data.get('num_real_vehicles', data['num_vehicles'])
total_time_all_vehicles = sum(
    times[-1] if times else 0 
    for times in estimated_times[:num_real_vehicles]
)
```

This is backward-compatible and doesn't require signature changes to get_results().

---

## Related Issues To Watch

Once this is fixed, also check:

1. **Display issues in display_detailed_results()** (line 44-154)
   - Currently shows all vehicles including dummies
   - May want to skip display of dummy vehicles or mark them clearly
   - Dummy routes like `0 → 62 → 0` are confusing to users

2. **Comparison logic in solve_vrp_with_optimal_hubs()** (line 481-544)
   - Uses total_time_all_vehicles to compare with/without hubs
   - Will automatically work correctly once metric is fixed
   - Hub solutions should appear ~2-3x slower (reasonable), not 56x

3. **Other metrics that might have similar issues:**
   - Check if final_loads includes dummies (line 370) ← currently OK
   - Check if load_imbalance_percentage calculations include dummies (line 371) ← currently OK

