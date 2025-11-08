# Claude Code Instructions

This file contains guidelines for Claude Code when working on this VRP optimizer project.

## Temporary Files

Claude Code should store temporary files, debugging output, and analysis files in:
```
.github/temp/
```

This directory should be gitignored if it contains sensitive data or large temporary artifacts.

## Key Development Commands

### Running the Complete Pipeline
```bash
python -m optimizer.main
```
- Generates toy data if needed
- Runs the VRP solver
- Creates interactive HTML visualization
- Prints detailed results and metrics

### Running Tests
```bash
python -m pytest optimizer/tests/test_solver.py -v
```

### Running Performance Analysis
```bash
python -m optimizer.stats
```
- Tests combinations of parameters
- Generates performance metrics CSV
- Creates visualization plots
- Saves results to `optimizer/analysis_results/`

### Data Generation Only
```python
from optimizer.create_toy_data import create_toy_data
create_toy_data()
```

## Code Structure Conventions

### Configuration Changes
Configuration should be modified via `Config.update()`:
```python
from optimizer.config import Config
Config.update(NUM_CUSTOMERS=50, NUM_VEHICLES=5)
```

**Important:** Changes are global. Reset values after parametric testing:
```python
Config.update(NUM_CUSTOMERS=45, NUM_VEHICLES=3)
```

### Adding New Features

**New dimensions:** Add to `add_routing_dimensions()` in solver.py
**New constraints:** Add to `configure_constraints_and_penalties()` or separate function
**New metrics:** Add extraction to `get_results()` in postprocessor.py
**New visualization elements:** Modify `create_visualization()` in print_solution.py

### Data Pipeline Steps

When modifying data pipeline:
1. **Data Input:** Modify data_loader.py
2. **Preprocessing:** Modify preprocessor.py
3. **Solving:** Modify solver.py (10 phases clearly marked)
4. **Results:** Modify postprocessor.py
5. **Display:** Modify print_solution.py or stats.py

## Critical Implementation Notes

### Node Extension System
The solver uses extended node indices that map to physical locations via `base_node` array:
- Use `base_node[extended_index]` to get actual location/matrix index
- Distance/time lookups MUST use: `matrix[base_node[from], base_node[to]]`

### Time Calculation
- Travel time is **NOT** from time_matrix.npy
- **Always use:** `distance * Config.DISTANCE_TO_TIME_FACTOR` (600.0)
- Service time: `abs(demand) * Config.SERVICE_TIME_PER_UNIT` (60)

### Load Tracking
- OR-Tools tracks cumulative pickups (positive = added to vehicle)
- **Actual load** = `vehicle_capacity - cumulative_capacity`
- Negative demands (unload depots, hub deposits) reduce cumulative value

### Baseline Computation
- Preprocessor.py solves VRP without hubs first
- **Can fail** if problem is over-constrained
- Consider error handling if extending constraints

## Commit Guidelines

When committing changes:
1. **Feature additions:** Describe the solver aspect being improved (nodes, constraints, objective, etc.)
2. **Bug fixes:** Reference specific behavior and root cause
3. **Analysis/tests:** Include what parameters were tested
4. **Documentation:** Updated docs should mention code sections changed

Example:
```
Add hub transfer rebalancing constraint

- Limits consecutive transfers to same vehicle (prevents oscillation)
- Adds new constraint in setup_hub_constraints()
- Updates postprocessor get_results() to track rebalancing count
```

## Debugging Tips

### Solver Returns No Solution
1. Check time limit is sufficient (increase `Config.TIME_TO_SOLVE`)
2. Verify baseline VRP is solvable (preprocessor.py)
3. Check constraint feasibility (disable hub transfers, reload, time windows)
4. Reduce problem size (fewer customers, more vehicles)

### Unexpected Vehicle Loads
- Check base_node mapping is correct
- Verify negative demands (unload depots, hub deposits) are set correctly
- Check capacity dimension slack settings
- Print cumulative_capacity and expected load value

### Visualization Issues
- Verify all three external files exist: interface.html, script.js, styles.css
- Check that solution is not None before visualization
- Inspect vrp_visualization.html to see embedded data correctness

### Performance Degradation
- Use stats.py to identify which parameter combination causes slowdown
- Check constraint count (may be polynomial growth)
- Profile solver.py phases with timing instrumentation

## Testing Approach

Since test_solver.py is minimal:
1. **Manual testing:** Run main.py with different parameters
2. **Regression testing:** Use same toy data, ensure results are consistent
3. **Parametric testing:** Use stats.py to identify breaking points
4. **Edge cases:**
   - Single customer
   - Single vehicle with multiple reloads
   - Customer far from others
   - Very tight time windows

## Documentation Updates

When making significant changes:
1. Update relevant .md file in .github/
2. If adding solver phase: update ARCHITECTURE.md solver phases
3. If changing data format: update USAGE_GUIDE.md input section
4. If new configuration: update Config explanation
5. If changing algorithm: update ARCHITECTURE.md algorithm section

## Performance Considerations

- **Solver time:** Default 10 seconds - increase for large problems
- **Node extension:** Each hub adds 4 nodes + 1 dummy vehicle (linear growth)
- **Unload depots:** 10 default - trades accuracy for speed
- **Search strategy:** PATH_CHEAPEST_ARC is greedy, may need GLS time
- **Matrix size:** O(n²) distance matrix for n locations

Typical performance:
- 50 customers, 3 vehicles: Solves in < 1 second
- 100 customers, 5 vehicles: ~5-10 seconds
- 150+ customers: May need 30+ seconds or problem simplification
