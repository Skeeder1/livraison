# Delivery Route Optimizer — CVRPTW with hub reloading

> Urban delivery route planning under capacity and time-window constraints, with mid-route reloading. Solved with Google OR-Tools, rendered as an animated map on real road geometry.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![OR-Tools](https://img.shields.io/badge/OR--Tools-9.15-4285F4?logo=google&logoColor=white)
![Leaflet](https://img.shields.io/badge/Leaflet-OpenStreetMap-199900?logo=leaflet&logoColor=white)
![Tests](https://img.shields.io/badge/tests-14%20passing-success)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## The demo in one animation

Three couriers serve 45 customers across Paris. The vehicles follow **the actual road network**, each one's load updates live, and the delivered-parcel counter climbs until the routes complete.

![Route animation](docs/images/demo-tournees.gif)

*Higher-quality video: [`docs/images/demo-tournees.mp4`](docs/images/demo-tournees.mp4)*

---

## The problem

A courier cannot simply "visit every customer in the shortest order". Four interacting constraints get in the way:

| Constraint | What it imposes |
|---|---|
| **Capacity** | A vehicle carries at most 10 parcels. Beyond that, it must reload. |
| **Time windows** | Each customer accepts delivery within a given slot. Too early means waiting; too late is penalised tardiness. |
| **Reloading** | A vehicle can return to the depot or pass through a **hub** to leave full again — at the cost of a detour. |
| **Balancing** | Three 2-hour routes beat one 5-hour route and two 30-minute ones. |

This is a **CVRPTW** (*Capacitated Vehicle Routing Problem with Time Windows*), an NP-hard problem: at 45 customers, exhaustive enumeration is out of reach. The goal is a good solution within a bounded time budget, not a proven optimum.

## The approach

### Modelling

The solver is built on **Google OR-Tools** (`RoutingModel`) with four dimensions:

- **Distance** — the primary objective to minimise;
- **Capacity** — bounded per vehicle, reset at reload points;
- **Customer count** — used to spread customers across vehicles;
- **Time** — carries the time windows, service times, and waiting.

Search strategy: `PARALLEL_CHEAPEST_INSERTION` for the first solution, then **Guided Local Search** as the metaheuristic, under a 30-second budget. Load balancing is driven by `SetGlobalSpanCostCoefficient` on the distance, customer-count, and time dimensions.

Two mechanisms are worth calling out:

**Reloading, modelled with dummy nodes.** OR-Tools cannot natively "empty" a vehicle mid-route. Each hub is therefore split into two nodes — a drop-off (negative demand) and a pick-up (positive demand) — linked by a dummy vehicle. The transfer becomes an ordinary routing constraint.

**Customers are droppable.** Every node is placed in a disjunction with a penalty (`AddDisjunction`). Rather than declaring the problem infeasible when a constraint cannot be met, the solver may sacrifice a customer at an explicit cost — and the final report says so.

### The question the solver actually answers

Hubs cost detours. Are they worth it? The program **solves the problem twice**, with and without hubs, then keeps whichever gives the better total delivery time:

```
🎯 SOLUTION COMPARISON
   Without hubs : 5h 58m 36s
   With hubs    : 29h 15m 25s
   ✅ Solution WITHOUT hubs selected (hubs add 23h 16m 49s)
```

On this dataset the hubs do not pay off — the detour costs more than the reload saves. That is a result, not a failure: the tool exists precisely to settle that question on real data.

> Figures are from one run. Because the search is bounded by wall-clock time (`TIME_TO_SOLVE = 30`), the exact seconds vary slightly between runs even with `RANDOM_SEED` fixed; the conclusion does not.

## Screenshots

| Leaving the depot | Routes in progress | Routes completed |
|---|---|---|
| ![Departure](docs/images/01-depart-depot.jpg) | ![In progress](docs/images/02-tournees-en-cours.jpg) | ![Completed](docs/images/03-tournees-terminees.jpg) |

The map is not a static render: a time slider replays the day, showing each vehicle's state (`En route`, `Servicing`, `Waiting`), its instantaneous load, and the cumulative indicators.

## Installation

```bash
git clone https://github.com/Skeeder1/livraison.git
cd livraison

python -m venv .venv && source .venv/bin/activate
pip install -e ".[cli,dev]"
```

No API key is required: routing uses the public OSRM server and basemaps come from OpenStreetMap.

The `cli` extra brings the interactive map, the charts and the coloured console
output. Without it the install is the solver and its data, which is what a
service calling `optimizer.scenario` wants: 139 MB instead of 320, and nothing
installed that it never runs.

```bash
pip install .              # solver only (ortools, numpy)
pip install ".[analysis]"  # + aggregation of measurement campaigns
```

## Usage

```bash
# Solve the problem and generate the animated map
python -m optimizer.main

# Open the result
xdg-open vrp_visualization.html
```

The scenario is configured in [`optimizer/config.py`](optimizer/config.py):

```python
NUM_CUSTOMERS = 45          # customers to serve
NUM_VEHICLES  = 3           # couriers
NUM_HUBS      = 2           # candidate reload points
TIME_TO_SOLVE = 30          # search budget, in seconds
DEPOT_POSITION = (48.8566, 2.3522)   # Paris, Île de la Cité
RANDOM_SEED   = 42          # None for a different scenario each run
```

### Solving a scenario from code

`python -m optimizer.main` is a program: it regenerates the data, solves, writes
`vrp_visualization.html`, colours its output and reconfigures the standard
streams. None of that belongs in a web service. To call the solver from code,
`optimizer/scenario.py` exposes the same computation as a function:

```python
from pathlib import Path
from optimizer.scenario import solve_scenario

tour = solve_scenario(
    {
        "customers": 45,                # customers to serve
        "vehicles": 3,                  # couriers
        "hubs": 0,                      # transfer points between vehicles
        "capacity": 10,                 # parcels per vehicle
        "time_windows_binding": False,  # genuinely tight time windows
        "budget_seconds": 30,           # search budget
    },
    workdir=Path("/tmp/scenario-1234"),
)

print(tour["stats"]["customersServed"], "customers served")
print(tour["stats"]["roadKm"], "km driven, horizon", tour["horizon"], "s")
```

The returned document stands on its own: geolocated stops, legs drawn on the
road network, loads, waits and indicators. Its full contract is described at the
top of [`optimizer/tour_format.py`](optimizer/tour_format.py), and it is **the
same function** that shapes an offline freeze and a solve served live, so the
two have the same form by construction.

Five things to know before putting this behind an HTTP route:

- **`hubs` commands transfers, and nothing else.** At 0 no hub exists. Above it,
  each hub becomes an exchange point between vehicles. There is no intermediate
  state: a hub carries no demand, so driving through one without transferring
  anything only lengthens the route. On the toy data, transfers clearly degrade
  the tours; that is a result of the solver, and it is exactly the question
  `optimizer.main` exists to settle.
- **One solve.** `main` chains three (baseline distance, then with and without
  hubs). `solve_scenario` calls `solve_vrp` once, which divides the response
  time by three. In exchange the hub strategy is no longer arbitrated: the
  document describes the configuration asked for, not the better of the two.
- **No concurrent calls in one process.** `Config` holds class attributes, and
  generating the data seeds NumPy's global random generator. Two simultaneous
  calls would corrupt each other. Serialise the calls, or isolate them in
  subprocesses.
- **Parameters are bounded server side** by `SCENARIO_LIMITS`, before any
  computation: a scenario is CPU time.
- **`workdir` is supplied by the caller.** The six data files are written there
  and read back; nothing depends on the process working directory.

### Regenerating the demo video

```bash
pip install playwright && playwright install chromium
python tools/capture_demo.py --frames 180 --fps 24
```

The script drives the time slider frame by frame in a headless browser, then assembles the result with ffmpeg. Capture is therefore **deterministic**, instead of depending on animation cadence and machine load.

## Tests

```bash
pytest                  # everything, about 55 s
pytest -m "not slow"    # fast loop, about 20 s
```

```
77 passed in 53.27s
```

The tests cover the load-imbalance indicator, the OR-Tools compatibility layer, the tour document contract and the scenario API end to end.

Two of them are worth pointing out:

- an **upstream regression sentinel**: it asserts that `SetAllowedVehiclesForIndex` is still broken on the OR-Tools side, and will fail the day the fix ships, signalling that our workaround can be removed;
- a **non-regression test on the showcase scenario** (marked `slow`): it replays the reference scenario, 45 customers and 3 vehicles on seed 42, and checks that it lands on the same indicators. It spends its full 30 second budget. The search being time-bounded, those values depend on machine speed: a deviation is not necessarily a regression, and the failure message says so.

## Architecture

```
optimizer/
├── config.py           # Scenario and solver parameters
├── create_toy_data.py  # Dataset generation (seed-reproducible)
├── data_loader.py      # Loading and shaping
├── preprocessor.py     # Baseline distance computation
├── solver.py           # OR-Tools model: dimensions, constraints, hubs
├── postprocessor.py    # Route extraction and indicator computation
├── trace.py            # Reading a solution: waits, loads, JSON
├── scenario.py         # API: a scenario in, a tour document out
├── tour_format.py      # Contract of the document served to a web consumer
├── print_solution.py   # Animated map rendering (folium / Leaflet)
├── road_routing.py     # Real road-network itineraries (OSRM)
├── stats.py            # Comparative analysis
└── visualization/      # HTML, CSS and JavaScript template for the animation

tools/capture_demo.py   # Demo capture to frames and video
tests/unit/             # Unit tests
tests/integration/      # End-to-end tests of the scenario API
features-inventory.md   # Inventory of the features and their tests
```

`trace.py` and `tour_format.py` exist for a precise reason: without them the
animated map and the API would each carry a copy of the same computation, and
the two would eventually drift. The Leaflet rendering now imports the same
functions the server does, and the only dependency on folium or matplotlib is
left in `print_solution.py`.

## Notable technical choices

**Routes follow streets, not straight lines.** Connecting customers as the crow flies produces paths through buildings and across the Seine. Each segment is therefore replaced by its real road itinerary, obtained from OSRM. OSRM was chosen over OpenRouteService or GraphHopper for one specific reason: **no API key**, therefore no secret to store in a public repository. One request per route rather than per segment (thanks to `steps=true`), a disk cache, and a silent fallback to straight lines when the network is unavailable — the project stays runnable offline.

**The distance→time factor is physically calibrated.** Distances are Euclidean, expressed in degrees. Converting them to seconds assumes ~85 km per degree at the latitude of Paris and an average speed of 20 km/h in urban traffic, i.e. ~15,000 s per degree. Cross-checked against OSRM: 750 s predicted versus 801 s measured on a 4.7 km crossing.

**A documented workaround for an upstream regression.** Since OR-Tools 9.15, `SetAllowedVehiclesForIndex` is unusable from Python — the C++ signature moved to `absl::Span<const int>` without a SWIG typemap ([or-tools#4982](https://github.com/google/or-tools/issues/4982)). The workaround constrains the node's vehicle variable directly, preserving the `-1` sentinel without which the disjunctions would stop working.

## Known limitations

This is an operations-research prototype, and some simplifications are deliberate:

- **The solver's distances are Euclidean**, not road distances. OSRM itineraries feed the display and the animation, not the cost matrix — so the solver optimises over a straight-line approximation. This is the highest-value improvement to make next.
- **The imbalance indicator** is based on residual load at the end of a route, which is an imperfect proxy for real workload. Customers served or time per vehicle would be better.
- **Reported computation time is hard-coded to zero**: it is not instrumented yet.
- **The data is synthetic**, generated around Paris. The input format (`colis.json`, `livreurs.json`, `hubs.json`) accepts real data without code changes.

## License

MIT
