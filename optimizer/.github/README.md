# VRP Optimizer - Technical Documentation

## Project Overview

**VRP Optimizer** is a Vehicle Routing Problem (VRP) solver with advanced extensions for multi-hub delivery networks and in-route vehicle reloading. The system uses **Google OR-Tools** constraint solver to optimize delivery routes while minimizing distance, tardiness, load imbalances, and hub utilization.

This is a specialized solver for delivery optimization that handles:
- **Capacitated Vehicle Routing with Time Windows (CVRPTW)**: Delivery routes respecting vehicle capacities and customer time windows
- **Vehicle Reloading**: Vehicles can return to depot mid-route to reload cargo
- **Hub Transfers**: Cargo can be transferred between vehicles at intermediate hubs for network resilience

## Quick Start

### Installation

```bash
# Install dependencies (if not already installed)
pip install ortools pandas numpy matplotlib seaborn folium colorama

# Run the complete solver pipeline
python -m optimizer.main
```

This will:
1. Generate synthetic test data (45 customers, 3 vehicles, 2 hubs)
2. Solve the VRP optimization problem
3. Create an interactive HTML visualization
4. Display detailed metrics

### Output

- **Console Output:**
  - Problem parameters (node count, vehicle count, hub count)
  - Baseline distance (VRP without hubs for comparison)
  - Solution metrics (total distance, tardiness, hub usage, load balance)
  - Vehicle routes and stops

- **Visualization:**
  - Interactive map (`vrp_visualization.html`)
  - Route polylines colored by vehicle
  - Markers for customers, hubs, depot
  - Heatmap of time spent at locations
  - Vehicle load tracking along routes

## Architecture Overview

### Data Pipeline

```
Input Data (JSON + NumPy)
    ↓
[Data Loader] - Load colis, livreurs, hubs, distance/time matrices
    ↓
[Preprocessor] - Compute baseline VRP (without hubs) for comparison
    ↓
[Solver] - OR-Tools CVRPTW with hub transfers and vehicle reloading
    ↓
[Post-processor] - Extract routes, times, loads, and metrics
    ↓
[Visualization] - Create interactive HTML map with route details
    ↓
Output: Routes, metrics, visualization
```

### Core Components

| Component | Purpose |
|-----------|---------|
| **config.py** | Centralized configuration (solver time, capacities, time windows, etc.) |
| **data_loader.py** | Load problem data from JSON and NumPy files |
| **preprocessor.py** | Compute baseline VRP without hubs for performance comparison |
| **solver.py** | OR-Tools routing solver with 10-phase setup |
| **postprocessor.py** | Extract results and calculate metrics |
| **print_solution.py** | Generate interactive Folium visualization |
| **create_toy_data.py** | Generate synthetic test data |
| **stats.py** | Performance analysis tool for parametric testing |

## Input Data Format

### Required Files (in `optimizer/tests/toy_data/`)

**1. colis.json** - Customer/package data
```json
[
  {
    "id": "C1",
    "position": [0.5, 0.3],
    "tw_start": 0,
    "tw_end": 86400,
    "volume": 1.0
  },
  ...
]
```
- **position**: [latitude, longitude] coordinates
- **tw_start, tw_end**: Time window in seconds (0-86400 for 24 hours)
- **volume**: Demand/package volume

**2. livreurs.json** - Vehicles/drivers
```json
[
  {
    "id": "V1",
    "capacity": 10.0,
    "start_time": 0,
    "end_time": 86400
  },
  ...
]
```
- **capacity**: Vehicle cargo capacity
- **start_time, end_time**: Shift start/end in seconds

**3. hubs.json** - Distribution hubs
```json
[
  {
    "id": "H1",
    "position": [0.2, 0.1],
    "load_limit": 5.0
  },
  ...
]
```
- **position**: Hub location [lat, long]
- **load_limit**: Max cargo at hub (currently not enforced)

**4. weights.json** - Multi-objective weights (loaded but not used in current objective)
```json
[
  {"criterion": "distance", "weight": 1.0},
  {"criterion": "tardiness", "weight": 0.8},
  {"criterion": "hubs", "weight": 0.6},
  {"criterion": "imbalance", "weight": 0.4},
  {"criterion": "waiting", "weight": 0.2}
]
```

**5. distance_matrix.npy** - Pairwise distances (NumPy array)
- Shape: (num_locations, num_locations)
- Euclidean distances between all points
- Generated automatically by create_toy_data.py

**6. time_matrix.npy** - Pairwise travel times (loaded but NOT USED)
- Shape: (num_locations, num_locations)
- **Note:** Actual travel time is dynamically calculated: `distance * 600.0`

### Node Indexing

```
Index 0:                           Depot (physical location (0,0))
Index 1 to NUM_CUSTOMERS:          Customers
Index NUM_CUSTOMERS+1 to end:      Hubs
```

Extended indices (created by solver):
- Unload depot nodes (at depot location)
- Hub deposit/pickup nodes (at hub locations)
- Dummy nodes (for constraint mediation)

See ARCHITECTURE.md for detailed extension scheme.

## Configuration

All parameters in `optimizer/config.py`:

### Solver Configuration
- **TIME_TO_SOLVE**: 10 seconds (maximum time to find solution)

### Problem Size
- **NUM_CUSTOMERS**: 45 (default, customize via create_toy_data or Config.update)
- **NUM_VEHICLES**: 3 (vehicles/drivers)
- **NUM_HUBS**: 2 (distribution hubs)
- **NUM_UNLOAD_DEPOTS**: 10 (reload points at main depot)

### Spatial & Capacity
- **DEPOT_POSITION**: (0.0, 0.0) - fixed origin
- **POSITION_RANGE_MIN/MAX**: -5.0 to 5.0 (random position bounds)
- **VEHICLE_CAPACITY_MIN/MAX**: 10.0 each (all vehicles have same capacity in default)
- **HUB_LOAD_LIMIT**: 5.0 (not enforced in solver)

### Time Calculation
- **DISTANCE_TO_TIME_FACTOR**: 600.0 (1 distance unit = 600 seconds = 10 minutes)
- **SERVICE_TIME_PER_UNIT**: 60 seconds per demand unit
- **TW_START/END**: 0 to 86400 seconds (24-hour time windows)

### Analysis
- **TIME_INCREMENT**: 10 seconds (for stats.py iterative solving)

## Output Format

### Vehicle Routes
```
Vehicle 0:
  Route: [0, 5, 12, 3, 0]                  (depot + customers + depot)
  Stops:
    0 (depot):       arrival=0s,   load=10.0, service=0s
    5 (customer):    arrival=125s, load=9.0,  service=60s
    12 (customer):   arrival=200s, load=8.0,  service=60s
    3 (customer):    arrival=350s, load=7.0,  service=60s
  Total distance: 45.2 units
  Total time: 500 seconds (includes service and driving)
```

### Metrics
- **Total Distance**: Sum of distances across all vehicle routes
- **Total Tardiness**: Sum of lateness (max(0, arrival_time - deadline)) for all customers
- **Activated Hubs**: Number of hubs used for transfers
- **Load Imbalance %**: (max_load / min_load) × 100
- **Load Balance**: Max load on any vehicle

### Visualization Data
- Interactive map with vehicle routes as colored polylines
- Customer markers with time window display
- Hub markers showing transfer operations
- Heatmap overlay for time spent at locations
- Timeline showing cumulative progress

## Key Algorithms

1. **Euclidean Distance Calculation**: `sqrt((x1-x2)² + (y1-y2)²)`
2. **Travel Time Calculation**: `distance × 600.0` seconds
3. **Service Time Calculation**: `cargo_volume × 60` seconds
4. **Initial Solution**: PATH_CHEAPEST_ARC (greedy construction)
5. **Improvement**: GUIDED_LOCAL_SEARCH (metaheuristic)
6. **Time Window Feasibility**: Temporal constraint checking during route construction
7. **Capacity Feasibility**: Cumulative load tracking per vehicle

## Advanced Features

### Vehicle Reloading
Vehicles can return to the depot mid-route via virtual "unload depot" nodes:
- Allows vehicles to service more customers than capacity would permit
- Automatically selected by solver if beneficial
- Trade-off: Extra time and distance vs. serving more customers per vehicle

### Hub Transfers
Cargo can be transferred between vehicles at hubs:
- Vehicle A drops cargo at hub deposit
- Vehicle B picks up cargo at hub pickup
- Useful for network rebalancing and resilience
- Mediated by dummy vehicle constraints to ensure temporal feasibility

### Multi-Objective Optimization
While the primary objective is distance minimization, the solver implicitly optimizes multiple criteria through penalty functions:
- Distance: Primary arc cost
- Time: Via slack penalties (100 per vehicle-second of waiting)
- Load balance: Via global span coefficient (100)
- Hub usage: Via arc penalty (+500 for hub nodes)

## Performance Characteristics

| Problem Size | Typical Solve Time | Notes |
|--------------|-------------------|-------|
| 50 customers, 3 vehicles | < 1 second | Very quick |
| 75 customers, 4 vehicles | 2-5 seconds | Good performance |
| 100 customers, 5 vehicles | 5-15 seconds | May approach limit |
| 150 customers, 7 vehicles | 30+ seconds | Increase TIME_TO_SOLVE |

## Troubleshooting

### No Solution Found
1. Increase `Config.TIME_TO_SOLVE` (default 10 seconds)
2. Verify problem is feasible (use fewer time windows or more vehicles)
3. Check baseline VRP solves (preprocessor.py doesn't fail)

### Unexpected Routes
1. Verify distance matrix is correct
2. Check time windows don't conflict
3. Inspect vehicle capacities are sufficient
4. Verify hub constraints in ARCHITECTURE.md are as intended

### Slow Performance
1. Reduce problem size (fewer customers, more vehicles)
2. Relax time windows (wider TW_END)
3. Check for constraint conflicts that force inefficient solutions
4. Use stats.py to profile different parameter combinations

## Dependencies

- **ortools**: Google OR-Tools constraint solver
- **pandas**: Data manipulation
- **numpy**: Numerical arrays
- **matplotlib, seaborn**: Performance analysis plots
- **folium**: Interactive map visualization
- **colorama**: Terminal colors
- **pytest**: Testing framework (if running tests)

## File Structure

```
optimizer/
├── main.py                  # Pipeline orchestration
├── config.py               # Configuration class
├── data_loader.py          # Load JSON + NumPy data
├── preprocessor.py         # Baseline VRP computation
├── solver.py               # OR-Tools solver (10 phases)
├── postprocessor.py        # Results extraction
├── print_solution.py       # Folium visualization
├── stats.py                # Performance analysis tool
├── create_toy_data.py      # Synthetic data generation
├── CLAUDE.md              # Claude Code guidance
├── tests/
│   └── test_solver.py     # Unit tests (minimal)
│   └── toy_data/          # Synthetic data files
├── visualization/         # External viz files
│   ├── interface.html
│   ├── script.js
│   └── styles.css
└── analysis_results/      # Performance analysis outputs
```

## Next Steps

For detailed information on:
- **Solver implementation details**: See [ARCHITECTURE.md](ARCHITECTURE.md)
- **Usage examples and configuration**: See [USAGE_GUIDE.md](USAGE_GUIDE.md)
- **Claude Code development guidelines**: See [CLAUDE_INSTRUCTIONS.md](CLAUDE_INSTRUCTIONS.md)
