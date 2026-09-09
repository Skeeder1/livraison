# Delivery Route Optimizer — CVRPTW with hub reloading

> Urban delivery route planning under capacity and time-window constraints, with mid-route reloading. Solved with Google OR-Tools, rendered as an animated map on real road geometry.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![OR-Tools](https://img.shields.io/badge/OR--Tools-9.15-4285F4?logo=google&logoColor=white)
![Leaflet](https://img.shields.io/badge/Leaflet-OpenStreetMap-199900?logo=leaflet&logoColor=white)
![Tests](https://img.shields.io/badge/tests-547%20passing-success)
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

**Reloading, modelled with duplicated depot nodes.** OR-Tools cannot natively "refill" a vehicle mid-route. Ten copies of the depot are added, each carrying a demand of minus one full load, and each optional at zero penalty. Visiting one resets the vehicle's capacity; the reset is constrained to be complete, so returning to the depot means leaving full again.

**Nodes are droppable, and that is what makes the model honest.** Every node sits in a disjunction with an explicit penalty (`AddDisjunction`). Rather than declaring the problem infeasible when a constraint cannot be met, the solver may sacrifice a customer at a stated cost — and the report says which. The same mechanism is what makes a courier hand-over *optional* rather than imposed; see below.

### The courier hand-over

This is the part of the model that is not in any textbook sample, and the reason
the project exists. The original brief was **mobile hubs**: two cargo-bike
couriers meeting at a well-chosen point in the city to pass parcels between
them, so that neither has to ride back to the depot.

Each candidate meeting point is split into two nodes — a **deposit** and a
**collection** at the same coordinates — tied together by four constraints:

| Constraint | Why |
|---|---|
| `ActiveVar(deposit) == ActiveVar(collection)` | both, or neither: a parcel put down must be picked up |
| `IsDifferentVar(vehicle(deposit), vehicle(collection)) >= ActiveVar(deposit)` | two *different* couriers — but only if the meeting happens |
| `CumulVar(deposit) <= CumulVar(collection)` | you cannot collect before it is dropped |
| customer count strictly increases after a collection | a parcel taken on must be delivered to someone |

The second one is reified for a reason. Written as a plain `!=`, dropping the
pair became **infeasible**: both vehicle variables equal `-1` when the nodes are
inactive, and `-1 != -1` is false. The meeting was therefore compulsory at every
hub — which is not a model of collaboration, it is a model of forced detours.

> Whether the hand-over actually pays is an empirical question, and this
> repository answers it by measurement rather than assertion. See
> [`experiments/`](experiments/).

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
pip install -e ".[dev]"
```

No API key is required: routing uses the public OSRM server and basemaps come from OpenStreetMap.

The core install is the solver and nothing else — `ortools` and `numpy`. That is
what a service calling `optimizer.scenario` wants, and nothing is pulled in that
it never runs.

```bash
pip install .                    # solver only
pip install ".[experiments]"     # + plots for the calibration campaign
pip install ".[dev]"             # + pytest and ruff
```

## Usage

```bash
# Solve, and write the tour document
cvrptw-solve --customers 45 --vehicles 3 --hubs 2 --out tour.json

# Check that the answer is coherent, recomputed from scratch
cvrptw-verify tour.json --data data/

# Ask whether it also looks intelligent
cvrptw-audit tour.json --carte
```

`cvrptw-solve` writes the same tour document the web interface consumes, so the
whole loop runs locally:

```bash
cd web && npm install && npm run dev     # then load the tour.json produced above
```

Defaults live in [`optimizer/config.py`](optimizer/config.py):

```python
NUM_CUSTOMERS = 45          # customers to serve
NUM_VEHICLES  = 3           # couriers
NUM_HUBS      = 2           # candidate reload points
TIME_TO_SOLVE = 30          # search budget, in seconds
DEPOT_POSITION = (48.8566, 2.3522)   # Paris, Île de la Cité
RANDOM_SEED   = 42          # None for a different scenario each run
```

### Solving a scenario from code

`cvrptw-solve` is a program: it regenerates the data, solves, writes a file and
prints a summary. To call the solver from code instead, `optimizer/scenario.py`
exposes the same computation as a function — and it is the function the command
line itself calls, so there is one code path, not two:

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

## Tests

```bash
pytest                  # everything, about 55 s
pytest -m "not slow"    # fast loop, about 20 s
```

```
547 passed, 37 skipped in 117s
```

Most of them assert **properties of the solution**, not frozen numbers: that no
vehicle ever exceeds its capacity, that a reload restores a full load, that
arrival times respect their windows, that a parcel handed over is collected by a
*different* courier and afterwards delivered to somebody. A solver returning
routes that violate the model fails the suite — which was not true before: the
earlier tests checked document shape and pinned figures, and would have passed a
physically impossible answer.

Three of them are worth pointing out:

- an **upstream regression sentinel**: it asserts that `SetAllowedVehiclesForIndex` is still broken on the OR-Tools side, and will fail the day the fix ships, signalling that our workaround can be removed;
- a **model-property suite** (`tests/integration/test_model_properties.py`): every property above, replayed across a matrix of seeds, hub counts, a tight-capacity case and a case where tardiness is unavoidable, so the tardiness assertion is checked against a non-zero value rather than a comfortable zero;
- a **non-regression test on the showcase scenario** (marked `slow`): it replays the reference scenario, 45 customers and 3 vehicles on seed 42, and checks that it lands on the same indicators. It spends its full 30 second budget. The search being time-bounded, those values depend on machine speed: a deviation is not necessarily a regression, and the failure message says so.

## Architecture

```
optimizer/
├── config.py           # Scenario and solver parameters
├── create_toy_data.py  # Dataset generation (seed-reproducible)
├── data_loader.py      # Loading and shaping
├── solver.py           # OR-Tools model: dimensions, constraints, hand-overs
├── postprocessor.py    # Route extraction and indicator computation
├── trace.py            # Reading a solution: waits, loads, JSON
├── scenario.py         # API: a scenario in, a tour document out
├── tour_format.py      # Contract of the document served to a web consumer
├── road_routing.py     # Real road-network itineraries (OSRM)
├── verify.py           # Independent correctness check of a tour
├── audit.py            # Geometric quality: crossings, residual 2-opt, map
└── main.py             # Command line

web/                    # The React interface, shared with the portfolio site
experiments/            # Penalty calibration campaign
explorations/           # Earlier models kept as a research trail
tests/unit/             # Unit tests
tests/integration/      # Model properties and the scenario API
features-inventory.md   # Inventory of the features and their tests
```

There is exactly **one** rendering of a solution, in `web/`, and exactly one
document format between the solver and it. Both used to be duplicated: a folium
map generated in Python sat alongside the React page, each with its own
interpolation code — and the map still carried a latitude-projection bug that had
already been fixed on the Python side. A second implementation does not stay in
agreement with the first; it drifts, quietly.

## Notable technical choices

**Routes follow streets, not straight lines.** Connecting customers as the crow flies produces paths through buildings and across the Seine. Each segment is therefore replaced by its real road itinerary, obtained from OSRM. OSRM was chosen over OpenRouteService or GraphHopper for one specific reason: **no API key**, therefore no secret to store in a public repository. One request per route rather than per segment (thanks to `steps=true`), a disk cache, and a silent fallback to straight lines when the network is unavailable — the project stays runnable offline.

**The distance metric is corrected for latitude.** Distances are Euclidean in degrees, but a degree of longitude is only ~73 km in Paris against ~111 km for a degree of latitude. Treating them as equal overstates east-west travel by half, and the solver then avoids east-west legs it should take. The longitude difference is therefore scaled by cos(latitude) — a correction the point *generator* already applied and the metric did not. One degree then means 111 km everywhere, and at 20 km/h in urban traffic that is ~20,000 s per degree.

**A documented workaround for an upstream regression.** Since OR-Tools 9.15, `SetAllowedVehiclesForIndex` is unusable from Python — the C++ signature moved to `absl::Span<const int>` without a SWIG typemap ([or-tools#4982](https://github.com/google/or-tools/issues/4982)). The workaround constrains the node's vehicle variable directly, preserving the `-1` sentinel without which the disjunctions would stop working.

## Known limitations

This is an operations-research prototype, and some simplifications are deliberate:

- **The solver's distances are Euclidean**, not road distances. OSRM itineraries feed the display and the animation, not the cost matrix — so the solver optimises over a straight-line approximation. This is the highest-value improvement to make next.
- **The imbalance indicator** is based on residual load at the end of a route, which is an imperfect proxy for real workload. Customers served or time per vehicle would be better.
- **A hand-over moves an anonymous unit of capacity, not an identified parcel.** The model guarantees that what is put down is picked up by another courier and that the collector then serves someone, but not that *this particular* parcel reaches *that particular* customer. A faithful hand-over needs parcel identity — a transshipment formulation, which is a materially harder problem.
- **The reported computation time in `get_results` is hard-coded to zero.** The scenario API reports the real figure as `meta.solveSeconds`; the console report does not.
- **The data is synthetic**, generated around Paris. The input format (`colis.json`, `livreurs.json`, `hubs.json`) accepts real data without code changes.

## What a systematic review found

This project was written early, then reviewed line by line much later. The
defects below were all found by reading the code against what it claimed, or by
checking a solution instead of trusting the report attached to it. They are
listed because the way each one hid is more interesting than the fix.

**An objective that was never applied.** `get_distance` returned `int(distance)`
on a matrix expressed in degrees. Over a city, no arc reaches 1, so all 420
entries truncated to zero: the arc-cost evaluator scored nothing, and the
`vehicle_max_distance` cap could never bind. The comment above it announced that
distance was being optimised. Counter-intuitively, fixing it did not shorten
routes — travel time is proportional to distance, so distance was already being
minimised *indirectly* through the time dimension. The bug was real; its effect
was masked.

**A hand-over that could not be declined.** The deposit and collection nodes
carried no disjunction, so they were mandatory: `hubs > 0` did not *permit* an
exchange, it *imposed* one at every hub regardless of cost. A two-pass solve
existed to work around this, arbitrating between "a forced transfer everywhere"
and "none at all" — a false dilemma created by the missing disjunction.

**Two inverted signs, and parcels that vanished.** Depositing a parcel credited a
courier with a delivery it had not made, while collecting one debited the courier
doing the favour. The exchange became a gift of capacity, and the collector paid
nothing if its route ended straight after. Routes of the form *depot → collect →
collect → depot* appeared on four seeds out of five: a courier that served nobody
and made the parcels disappear.

**A published timeline that contradicted the solve.** The solver constrained
60 seconds of service per unit; a line in the data setup overwrote the value with
5, and the tour document was built from the overwritten one. Couriers left each
stop 55 seconds per unit too early, the difference absorbed silently into travel
time. The function computing service time carries a comment warning against
exactly this divergence — the formula was never duplicated, the *constant* was.

**Indicators that flattered the result.** `hubsActivated` counted a courier
*driving past* a hub as a completed exchange. The published load was recomputed
by hand with sign rules that contradicted the solver, then clamped into range —
which hid the disagreement rather than surfacing it. Both now read from the
solver's own dimensions.

Two tools came out of this and are part of the repository:
[`cvrptw-verify`](optimizer/verify.py) recomputes every published quantity from
the coordinates and timestamps and refuses to trust the report, and
[`cvrptw-audit`](optimizer/audit.py) asks the harder question — whether a valid
solution also looks *sensible*: a route that crosses itself is provably
improvable, and counting the 2-opt moves still available measures how far the
search actually converged.

## Provenance

This solver did not start from a blank file. `optimizer/solver.py` descends from
the **OR-Tools "CVRPTW with reload" sample** (Copyright 2015 Tin Arm Engineering
AB, Copyright 2018 Google LLC, Apache 2.0), which arrived in the initial commit
as `cvrptw_reload_V2.py` alongside the untouched originals in an `official/`
folder.

The sample supplied the shape of a capacitated VRP with time windows and
mid-route reloading. What was built on top of it:

- **the courier hand-over** — a deposit/pickup node pair per hub, with a reified
  different-vehicle constraint, linked activations and time precedence. This is
  not in the sample, and it is the part of the model worth reading.
- a full restructuring into functions — no top-level function name is shared
- the scenario API, the tour document, the solution trace, and OSRM road geometry
- the Paris instance generator and a distance metric corrected for cos(latitude)
- the web interface in `web/`

See [`NOTICE`](NOTICE) for the original licence text and the full list of
changes. Contributions original to this repository are MIT.

## License

MIT
