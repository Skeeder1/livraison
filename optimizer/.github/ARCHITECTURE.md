# VRP Optimizer Architecture

This document details the internal implementation of the VRP solver, including the OR-Tools configuration, constraint system, node extension scheme, and advanced mechanisms for vehicle reloading and hub transfers.

## Solver Architecture Overview

The solver is implemented in 10 distinct phases in `optimizer/solver.py`:

```
1. Data Extension        → Add virtual nodes for reloads and hubs
2. Model Creation        → Initialize routing model and manager
3. Callback Registration → Register distance/time evaluators
4. Add Dimensions        → Add Distance, Capacity, Time tracking
5. Configure Constraints → Set node disjunctions and penalties
6. Time Constraints      → Set time windows and vehicle shifts
7. Vehicle Assignment    → Restrict which nodes each vehicle can visit
8. Hub Constraints       → Add special constraints for hub transfers
9. Objective Function    → Set distance minimization as primary goal
10. Solve               → Run search with PATH_CHEAPEST_ARC + GUIDED_LOCAL_SEARCH
```

## Phase 1: Data Extension

The solver extends the original node set to enable virtual operations:

### Node Extension Mechanism

**Original Nodes:**
```
Index 0:                           Depot
Index 1 to num_customers:          Customers (with cargo to deliver)
Index (num_customers + 1) to end:  Hubs (intermediate transfer points)
```

**Extended Nodes (added during setup_data_extensions):**

1. **Unload Depots** (NUM_UNLOAD_DEPOTS = 10 default)
   - Located at depot physical location
   - Demand: -max_vehicle_capacity (negative = unload operation)
   - Purpose: Allow vehicles to reload mid-route
   - Added as optional disjunctions (penalty = 0, free to skip)

2. **Hub Deposit Nodes** (one per hub)
   - Located at respective hub physical location
   - Demand: -1 (drop 1 unit of cargo)
   - Purpose: Vehicle drops cargo at hub
   - Part of hub transfer triplet

3. **Hub Pickup Nodes** (one per hub)
   - Located at respective hub physical location
   - Demand: +1 (pick up 1 unit of cargo)
   - Purpose: Vehicle picks up cargo from hub
   - Part of hub transfer triplet

4. **Dummy Nodes** (one per hub)
   - Located at depot physical location
   - Demand: 0 (no cargo change)
   - Purpose: Mediate timing between deposit/pickup
   - Assigned to dummy vehicles only

5. **Dummy Vehicles** (one per hub)
   - Zero capacity
   - Only service dummy nodes
   - Purely for constraint enforcement
   - Allow temporal ordering of hub transfers

### Base Node Mapping

A critical array `base_node` maps extended indices back to original location indices:

```python
base_node[extended_index] → original_location_index
```

**Use Case:**
```python
# When accessing distance/time matrix with extended indices:
distance = distance_matrix[base_node[from_extended], base_node[to_extended]]
time = distance * Config.DISTANCE_TO_TIME_FACTOR
```

This allows the solver to use the original distance matrix without recomputing for virtual nodes.

## Phase 2-3: Model Creation & Callbacks

### Routing Model Setup

```python
manager = RoutingIndexManager(
    num_locations = len(extended_locations),
    num_vehicles = num_vehicles + num_dummies,
    starts = [0, 0, 0],  # Each vehicle starts at depot (node 0)
    ends = [0, 0, 0]     # Each vehicle ends at depot (node 0)
)

routing = RoutingModel(manager)
```

### Distance Evaluator Callback

```python
def distance_evaluator(from_index, to_index):
    from_node = manager.IndexToNode(from_index)
    to_node = manager.IndexToNode(to_index)

    # Base distance from matrix
    dist = distance_matrix[base_node[from_node], base_node[to_node]]

    # Add penalties:
    # 1. Reload penalty (depot to depot arcs are expensive)
    if from_node == depot and to_node == depot:
        dist += vehicle_max_distance  # 100,000

    # 2. Hub penalty (discourage hub usage)
    if to_node in hub_deposit_nodes or to_node in hub_pickup_nodes:
        dist += 500

    return dist
```

### Time Evaluator Callback

```python
def time_evaluator(from_index, to_index):
    from_node = manager.IndexToNode(from_index)
    to_node = manager.IndexToNode(to_index)

    # Travel time (distance-based)
    base_dist = distance_matrix[base_node[from_node], base_node[to_node]]
    travel_time = base_dist * Config.DISTANCE_TO_TIME_FACTOR  # 600.0

    # Service time (demand-based)
    to_demand = data['demands'][to_node]
    service_time = abs(to_demand) * Config.SERVICE_TIME_PER_UNIT  # 60

    return travel_time + service_time
```

## Phase 4: Dimensions

Dimensions track cumulative values along routes:

### Distance Dimension
```python
dimension_name = 'Distance'
routing.AddDimension(
    evaluator_index = distance_evaluator_index,
    slack_capacity = 0,              # No slack allowed (exact distances)
    vehicle_capacity = 100000,       # Max distance per vehicle
    fix_start_cumul_to_zero = True,  # Start at 0 distance
    name = dimension_name
)

distance_dimension = routing.GetDimensionOrDie(dimension_name)

# Global span cost (minimize maximum distance traveled by any vehicle)
distance_dimension.SetGlobalSpanCostCoefficient(100)
```

**Purpose:** Track total distance, apply penalty to long spans

---

### Capacity Dimension
```python
dimension_name = 'Capacity'
routing.AddDimensionWithVehicleCapacity(
    evaluator_index = demand_evaluator_index,
    slack_capacity = max(vehicle_capacities),  # Can temporarily exceed then unload
    vehicle_capacities = vehicle_capacities,   # Per-vehicle limit
    fix_start_cumul_to_zero = False,
    name = dimension_name
)

capacity_dimension = routing.GetDimensionOrDie(dimension_name)
```

**How It Works:**
- Tracks `cumulative_demand` along route
- At each node, adds demand (positive for customers, negative for unload/deposit)
- Actual vehicle load = `vehicle_capacity - cumulative_demand`
- Ensures load never exceeds capacity

**Demand Values:**
- Customer node: +volume (1.0 default)
- Unload depot: -max_capacity (reload operation)
- Hub deposit: -1 (drop cargo)
- Hub pickup: +1 (pick cargo)
- Dummy node: 0 (no change)

---

### Time Dimension
```python
dimension_name = 'Time'
routing.AddDimension(
    evaluator_index = time_evaluator_index,
    slack_capacity = data['vehicle_max_time'],     # 1,440,000 seconds
    vehicle_capacity = data['vehicle_max_time'],
    fix_start_cumul_to_zero = False,
    name = dimension_name
)

time_dimension = routing.GetDimensionOrDie(dimension_name)

# Penalize waiting time
time_dimension.SetSpanCostCoefficientForVehicle(100, vehicle_id)
```

**Purpose:** Track cumulative time (travel + service), enforce time windows

## Phase 5: Constraints & Penalties

### Node Disjunctions (Optional Visits)

```python
# Customers: High penalty to skip (they must be serviced)
for customer_node in customer_nodes:
    routing.AddDisjunction([customer_node], penalty=100000)

# Hubs: Moderate penalty (can skip if not beneficial)
for hub_node in hub_nodes:
    routing.AddDisjunction([hub_node], penalty=500)

# Unload depots: Free to skip (optional reloading)
for unload_node in unload_depot_nodes:
    routing.AddDisjunction([unload_node], penalty=0)

# Dummy nodes: Should be visited (mediate hub transfers)
for dummy_node in dummy_nodes:
    routing.AddDisjunction([dummy_node], penalty=100000)
```

**Purpose:** Allow solver flexibility while discouraging skip of critical nodes

### Slack Constraints

```python
# Force zero slack at customer nodes (no waiting time)
for customer_node in customer_nodes:
    time_dimension.SlackVar(customer_node).SetValue(0)

# Force zero slack at hub nodes
for hub_node in hub_deposit_nodes + hub_pickup_nodes:
    time_dimension.SlackVar(hub_node).SetValue(0)

# Real vehicles: Apply slack cost (discourage waiting)
for vehicle_id in real_vehicles:
    time_dimension.SetSpanCostCoefficientForVehicle(100, vehicle_id)
```

**Purpose:** Minimize idle time and enforce no-waiting at customer locations

## Phase 6: Time Constraints

### Time Windows

```python
for location_id in range(num_locations):
    tw_start, tw_end = data['time_windows'][location_id]

    # Get the solver index for this location
    index = manager.NodeToIndex(location_id)

    # Exception: Depot has no time window (can visit anytime)
    if location_id != depot:
        time_dimension.CumulVar(index).SetRange(tw_start, tw_end)
```

**Time Windows Format:**
- Each location has `[start_seconds, end_seconds]`
- Default customers: [0, 86400] (entire 24 hours)
- Can be customized per customer in input data

### Vehicle Shift Times

```python
for vehicle_id in real_vehicles:
    start_time = data['start_times'][vehicle_id]
    end_time = data['end_times'][vehicle_id]

    # Set start node time
    start_index = routing.Start(vehicle_id)
    time_dimension.CumulVar(start_index).SetValue(start_time)

    # Constraint end node time
    end_index = routing.End(vehicle_id)
    time_dimension.CumulVar(end_index).SetMax(end_time)
```

**Default Values:**
- start_time: 0 (midnight)
- end_time: 200,000 seconds (very long, essentially unconstrained)

## Phase 7: Vehicle Assignment

### Vehicle Restrictions

```python
# Dummy vehicles can ONLY visit dummy nodes and depot
for vehicle_id in dummy_vehicles:
    for node_id in all_nodes:
        if node_id not in allowed_nodes_for_dummy[vehicle_id]:
            index = manager.NodeToIndex(node_id)
            routing.SetAllowedVehiclesForIndex([vehicle_id], index)

# Real vehicles CANNOT visit dummy nodes
for node_id in dummy_nodes:
    index = manager.NodeToIndex(node_id)
    routing.SetAllowedVehiclesForIndex(real_vehicles, index)
```

**Purpose:**
- Prevent real vehicles from servicing dummy nodes
- Ensure dummy vehicles only enforce constraints
- Maintain vehicle-node assignment logic

## Phase 8: Hub Transfer Constraints

Hub transfers require 4 synchronized constraints per hub:

### 1. Temporal Ordering

```python
# Deposit must happen before pickup
deposit_time = time_dimension.CumulVar(hub_deposit_index)
pickup_time = time_dimension.CumulVar(hub_pickup_index)
routing.AddPickupDeliveryIndex(deposit_index, pickup_index)
# This ensures: deposit_time <= pickup_time
```

**Purpose:** Cargo can't be picked up before it's deposited

---

### 2. Vehicle Separation

```python
def vehicle_pair_callback(from_index, to_index):
    from_node = manager.IndexToNode(from_index)
    to_node = manager.IndexToNode(to_index)

    # Different vehicles must service deposit/pickup
    from_vehicle = routing.GetVehicleOfNode(from_node)
    to_vehicle = routing.GetVehicleOfNode(to_node)

    if (from_node == hub_deposit and to_node == hub_pickup):
        if from_vehicle == to_vehicle:
            return 100000  # Penalize same vehicle

    return 0

vehicle_separation_index = routing.RegisterTransitCallback(vehicle_pair_callback)
routing.AddDimensionWithVehicleCapacity(vehicle_separation_index, ...)
```

**Purpose:** Ensure transfer (not direct handoff by same vehicle)

---

### 3. Capacity Balance

```python
# Deposit reduces load by 1
capacity_dimension.CumulVar(hub_deposit_index) -= 1

# Pickup increases load by 1
capacity_dimension.CumulVar(hub_pickup_index) += 1

# Balance: what's dropped = what's picked up
# (Implicit: OR-Tools capacity constraint)
```

**Purpose:** Ensure cargo inventory is consistent

---

### 4. Dummy Vehicle Mediation

```python
# Dummy node must occur between deposit and pickup in time
deposit_time = time_dimension.CumulVar(hub_deposit_index)
dummy_time = time_dimension.CumulVar(hub_dummy_index)
pickup_time = time_dimension.CumulVar(hub_pickup_index)

routing.AddDimensionWithVehicleCapacity(
    time_evaluator_index,
    slack = vehicle_max_time,
    capacity = vehicle_max_time,
    fix_start_to_zero = False,
    name = f'hub_time_{hub_id}'
)

# Constraint: deposit ≤ dummy ≤ pickup
hub_time_dimension = routing.GetDimensionOrDie(f'hub_time_{hub_id}')
hub_time_dimension.CumulVar(hub_dummy_index).SetRange(
    deposit_time,
    pickup_time
)
```

**Purpose:** Dummy vehicle ensures temporal consistency of transfer

---

## Phase 9: Objective Function

### Single Objective: Distance Minimization

```python
routing.SetArcCostEvaluatorOfAllVehicles(distance_evaluator_index)
```

**Primary Goal:** Minimize total distance traveled across all vehicles

### Multi-Objective via Penalties

While the solver has a single objective (distance), multiple criteria are implicitly optimized:

| Criterion | Implementation |
|-----------|-----------------|
| **Distance** | Arc costs (primary objective) |
| **Tardiness** | Time window penalties (hard constraint) |
| **Load Balance** | Global span coefficient (100) in distance dimension |
| **Hub Usage** | +500 arc penalty for hub nodes |
| **Waiting Time** | Slack penalties (100 per vehicle) in time dimension |

**Weighted Objective (Conceptual):**
```
Minimize: distance + 100×total_span + 100×waiting_time + hub_penalties
Subject to: time_windows, capacity, vehicle_shifts
```

## Phase 10: Search & Solve

### Search Strategy

```python
search_parameters = pywrapcp.RoutingSearchParameters()
search_parameters.first_solution_strategy = (
    routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
)
search_parameters.local_search_metaheuristic = (
    routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
)
search_parameters.time_limit.seconds = Config.TIME_TO_SOLVE  # 10 seconds

solution = routing.SolveFromAssignmentWithParameters(
    initial_solution,
    search_parameters
)
```

### Algorithm Details

**PATH_CHEAPEST_ARC (Initial Solution):**
- Greedy construction heuristic
- Sequentially add cheapest arc that doesn't violate constraints
- Fast (seconds), provides decent starting point
- Often suboptimal for complex problems

**GUIDED_LOCAL SEARCH (Improvement):**
- Metaheuristic for local search
- Guides search away from local optima via penalty adjustments
- Gradually increases penalties on previously-visited edges
- Can find high-quality solutions given sufficient time
- Default 10 seconds typically finds 80-90% optimal solutions

## Critical Implementation Details

### 1. Time Matrix Unused

```python
# Loaded from file:
time_matrix = np.load(f"{data_dir}/time_matrix.npy")

# But NEVER used:
# travel_time = time_matrix[from, to]  ← WRONG

# Always use dynamic calculation:
travel_time = distance * Config.DISTANCE_TO_TIME_FACTOR  # ← CORRECT
```

**Why?** Allows adjusting speed assumptions without regenerating data files

---

### 2. Load Calculation Quirk

```python
# From postprocessor.py
if node == depot and count == 0:
    load_value = vehicle_capacity - reverse_load
else:
    load_value = vehicle_capacity - (reverse_load + 1)  # +1 adjustment
```

The +1 adjustment appears to be a workaround for OR-Tools capacity cumulative calculation. The exact reason isn't clear from code alone.

---

### 3. Baseline Computation Can Fail

```python
# preprocessor.py
try:
    manager, routing, solution = solve_vrp(data_no_hubs)
    if solution is None:
        raise ValueError("No baseline solution found")
except Exception as e:
    print(f"Baseline VRP solving failed: {e}")
    # Current code: Crashes pipeline
    # Better: Handle gracefully or raise informative error
```

---

### 4. Config Is Global Mutable State

```python
Config.update(NUM_CUSTOMERS=100, NUM_VEHICLES=5)
# All subsequent calls use new values
# Not thread-safe

# stats.py saves/restores:
original_params = {
    'NUM_CUSTOMERS': Config.NUM_CUSTOMERS,
    ...
}
Config.update(**original_params)  # Restore
```

---

### 5. Dummy Vehicle Count

```python
# solver.py
num_vehicles = data['num_vehicles']
num_dummies = data['num_hubs']
total_vehicles = num_vehicles + num_dummies

# postprocessor.py
num_real_vehicles = data['num_vehicles']  # Must distinguish!

# When printing/analyzing, filter out dummy vehicles:
for vehicle_id in range(num_real_vehicles):  # Skip dummies
    ...
```

---

## Data Flow Example

### Small Example: 3 customers, 1 vehicle, 1 hub

**Input:**
```
Customers: C1 (volume=1), C2 (volume=1), C3 (volume=1)
Vehicle: V1 (capacity=2)
Hub: H1
```

**Extended Nodes Created:**
```
0: Depot
1: C1
2: C2
3: C3
4: H1 (original hub)
5: Unload_1 (at depot)
6: Unload_2 (at depot)
...
15: Hub_deposit (at H1 location)
16: Hub_pickup (at H1 location)
17: Dummy (at depot location)
```

**One Possible Solution:**
```
V1 route: 0 → 1 (deliver 1) → 2 (deliver 1) → 5 (unload) → 3 (deliver 1) → 0
Dummy route: 0 → 17 (dummy node) → 0

V1 details:
  0: Depot (load=2, time=0)
  1: C1 (load=1, time=125)
  2: C2 (load=0, time=250)
  5: Unload (load=2, time=400)    ← Reload to full capacity
  3: C3 (load=1, time=650)
  0: Depot (load=0, time=900)
```

Hub transfer (if triggered):
```
V1 drops at 15 (Hub_deposit): load goes 1 → 0
Dummy mediates timing
V1 picks up at 16 (Hub_pickup): load goes 0 → 1
```

---

## Performance Notes

### Computational Complexity
- **Nodes:** O(n + m×k) where n=customers, m=hubs, k=unload_depots
- **Arcs:** O((n + m×k)²) complete graph
- **Constraints:** O(n + m) time windows + O(m) hub constraints
- **Overall:** NP-hard; no polynomial solution

### Typical Times (10-second limit)
| Problem | Solve Time | Solution Quality |
|---------|-----------|-----------------|
| 50 customers, 3 vehicles | 0.5s | Good (90%+ optimal) |
| 100 customers, 5 vehicles | 5-8s | Good (80%+ optimal) |
| 150 customers, 7 vehicles | 10s+ | May be partial/incomplete |

### Optimization Techniques
1. **Early termination:** Stop at first feasible solution (faster, lower quality)
2. **Time increase:** stats.py iteratively increases time limit
3. **Problem reduction:** Fewer hubs, more vehicles, relaxed time windows
4. **Parameter tuning:** Adjust penalties (hub +500, etc.)

---

## Extending the Solver

### Adding a New Constraint

1. **Define the constraint logic**
   ```python
   def new_constraint_callback(from_index, to_index):
       from_node = manager.IndexToNode(from_index)
       to_node = manager.IndexToNode(to_index)

       if should_apply_constraint(from_node, to_node):
           return PENALTY_VALUE
       return 0
   ```

2. **Register the callback**
   ```python
   new_constraint_index = routing.RegisterTransitCallback(new_constraint_callback)
   ```

3. **Add as dimension or raw constraint**
   ```python
   routing.AddDimension(
       new_constraint_index,
       slack=...,
       capacity=...,
       name='NewConstraint'
   )
   # OR
   routing.AddDisjunction([node_list], penalty=...)
   ```

### Adding a New Dimension

1. **Create evaluator callback**
2. **Register and add dimension**
3. **Set dimension variables' ranges**
4. **Apply costs if needed**

See phases 4-6 for examples.

---

## Validation & Testing

### Manual Testing
```bash
python -m optimizer.main
```

### Parametric Testing
```bash
python -m optimizer.stats
```

### Regression Testing
Use same toy data, verify routes are consistent across runs

---

## References

- **OR-Tools Docs:** https://developers.google.com/optimization/routing
- **VRP Variants:** https://en.wikipedia.org/wiki/Vehicle_routing_problem
- **Guided Local Search:** https://en.wikipedia.org/wiki/Guided_local_search
