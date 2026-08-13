# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Vehicle Routing Problem (VRP) optimizer** using Google OR-Tools to solve delivery route optimization with:
- **Capacitated Vehicle Routing with Time Windows (CVRPTW)**
- **Vehicle Reloading**: Vehicles can return to depot mid-route to reload
- **Hub Transfers**: Cargo can be transferred between vehicles at intermediate hubs

The system optimizes for minimum distance while respecting vehicle capacities, time windows, and shift constraints.

## Quick Start

```bash
python -m optimizer.main
```

Runs the complete pipeline: data load → preprocess → solve → visualize → print results

Output: Interactive map (`vrp_visualization.html`) + console metrics

## Essential Commands

| Command | Purpose |
|---------|---------|
| `python -m optimizer.main` | Run complete solver pipeline |
| `python -m pytest optimizer/tests/test_solver.py -v` | Run tests |
| `python -m optimizer.stats` | Performance analysis (parametric testing) |

## Core Architecture

**Pipeline:**
```
Data Load → Preprocess → Solve → Post-process → Visualize
```

**Main Modules:**
- `main.py`: Orchestration
- `solver.py`: OR-Tools solver (10-phase setup)
- `data_loader.py`: JSON + NumPy data loading
- `preprocessor.py`: Baseline VRP computation
- `postprocessor.py`: Results extraction
- `trace.py`: Solution reading (slacks, per-step loads, JSON coercion), no rendering deps
- `scenario.py`: Callable API, one solve, bounded params, returns a tour document
- `tour_format.py`: Tour document contract consumed by the web demo
- `print_solution.py`: Folium visualization
- `config.py`: Centralized configuration
- `create_toy_data.py`: Synthetic data generation
- `stats.py`: Performance analysis

**Server-side entry point:** never import `main.py` from a server (it calls
`colorama.init`, reconfigures `sys.stdout`, sets `GLOG_*`). Use
`scenario.solve_scenario` instead; it is not safe to call concurrently in one
process (class-level `Config`, global NumPy seed).

**Removing hubs:** always through `solver.strip_hubs`. Setting `num_hubs = 0`
leaves the hub nodes in `locations` / `demands` / `time_windows`, where they get
no disjunction and therefore become mandatory stops. See AGENTS.md.

**No thread knob:** `RoutingSearchParameters` has no `num_search_workers` field
(checked on 9.15.6755). `lns_time_limit` defaults to 100 ms, and
`Duration.FromSeconds` rejects floats.

## Configuration (config.py)

**Key Parameters:**
```python
TIME_TO_SOLVE = 10              # Solver time limit (seconds)
NUM_CUSTOMERS = 45              # Deliveries
NUM_VEHICLES = 3                # Drivers
NUM_HUBS = 2                    # Transfer locations
NUM_UNLOAD_DEPOTS = 10          # Reload points at depot
DISTANCE_TO_TIME_FACTOR = 600   # 1 unit distance = 10 minutes
SERVICE_TIME_PER_UNIT = 60      # seconds per cargo unit
```

Modify dynamically via:
```python
Config.update(NUM_CUSTOMERS=100, TIME_TO_SOLVE=30)
```

## Data Format

**Input files** (in `optimizer/tests/toy_data/`):

| File | Content |
|------|---------|
| `colis.json` | Customers: position, volume, time windows |
| `livreurs.json` | Vehicles: capacity, start/end times |
| `hubs.json` | Hubs: position, load_limit |
| `weights.json` | Multi-objective weights (loaded, not used) |
| `distance_matrix.npy` | Pairwise distances |
| `time_matrix.npy` | Pairwise times (not used; calculated dynamically) |

**Node Indexing:**
```
0: Depot
1 to num_customers: Customers
(num_customers + 1) to end: Hubs
```

Extended nodes added by solver:
- Unload depots (reload points at depot)
- Hub deposits/pickups (transfer operations)
- Dummy nodes (constraint mediation)

## Critical Implementation Notes

1. **Time Matrix Unused**: Travel time calculated dynamically as `distance × 600`
2. **Load Calculation**: `actual_load = vehicle_capacity - cumulative_demand`
3. **Baseline VRP**: Computed without hubs for performance comparison
4. **Multi-Objective**: Single distance objective + penalties for time/balance/hubs
5. **Node Extension**: Virtual nodes map to physical locations via `base_node` array
6. **Config is Global**: Changes affect all subsequent calls; restore values after tests

## For Detailed Documentation

See `.github/` directory:

- **[.github/README.md](.github/README.md)**: Technical overview, architecture, data formats
- **[.github/ARCHITECTURE.md](.github/ARCHITECTURE.md)**: 10-phase solver details, constraints, dimensions, hub transfers
- **[.github/USAGE_GUIDE.md](.github/USAGE_GUIDE.md)**: How to use, configure, troubleshoot, interpret results
- **[.github/CLAUDE_INSTRUCTIONS.md](.github/CLAUDE_INSTRUCTIONS.md)**: Development guidelines, temp files in `.github/temp/`

## Development Guidelines

- **Temporary files**: Store in `.github/temp/`
- **Adding constraints**: Modify solver.py phases 5-8
- **Adding metrics**: Extend postprocessor.py `get_results()`
- **Adding visualizations**: Modify print_solution.py `create_visualization()`
- **Testing changes**: Use `python -m optimizer.stats` for parametric analysis

See [.github/CLAUDE_INSTRUCTIONS.md](.github/CLAUDE_INSTRUCTIONS.md) for detailed development practices.

## Git Commit Guidelines

**Important:** When creating commits:
- **DO NOT** include Claude's name or signature in commit messages
- Keep commit messages focused on technical changes only
- Use clear, concise descriptions of what changed and why
- Follow the format: `Short description` followed by bullet points of changes if needed

Example of **CORRECT** commit format:
```
Fix vehicle visualization and load tracking

- Fix max_time calculation to use only real vehicles
- Implement decreasing load display (10/10 → 0/10)
- Invert progress bar colors for better UX
```

Example of **INCORRECT** format (do not use):
```
🤖 Generated with Claude Code

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Performance Characteristics

| Problem | Typical Solve Time |
|---------|-------------------|
| 50 customers, 3 vehicles | < 1 second |
| 100 customers, 5 vehicles | 5-15 seconds |
| 150+ customers, 7 vehicles | 30+ seconds (may need tuning) |

Increase `TIME_TO_SOLVE` and/or reduce problem size for larger instances.
