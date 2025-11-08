# Detailed Technical Analysis: Time Calculation Bug with Hubs

## Executive Summary

| Metric | Value |
|--------|-------|
| **Bug Location** | `postprocessor.py` line 378 |
| **Cause** | Summing dummy vehicle times (1,440,000s each) with real vehicle times |
| **Symptom** | total_time_all_vehicles: 837h instead of ~14-37h |
| **Impact** | Makes hub solutions appear 56x worse than they actually are |
| **Root** | Dummy vehicles intentionally have long time limits for OR-Tools constraints |
| **Severity** | HIGH - Metric comparison completely wrong |

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      SOLVER.PY: solve_vrp()                     │
└─────────────────────────────────────────────────────────────────┘
                                │
                    Phase 1: setup_data_extensions()
                                │
                ┌───────────────┴───────────────┐
                │                               │
           num_real_vehicles = 3         Add dummy vehicles
                │                               │
                │                    for i in range(num_hubs):
                │                        data['num_vehicles']++
                │                        capacity[i] = 0
                │                        max_time[i] = 1,440,000
                │                               │
                └───────────────┬───────────────┘
                                │
                        data['num_vehicles'] = 5
                        capacities = [10,10,10,0,0]
                        max_times = [86400,86400,86400,1440000,1440000]
                                │
                    Phase 5: setup_time_constraints()
                                │
         ┌──────────────────────┴──────────────────────┐
         │                                             │
    Real vehicles (0-2):              Dummy vehicles (3-4):
    Set end time to                   Set end time to
    data['end_times'][v]              data['vehicle_max_time']
    (e.g., 86400 seconds)             = 1,440,000 seconds
         │                                             │
         └──────────────────────┬──────────────────────┘
                                │
                    Solver creates solution
                                │
    ┌───────────────────────────┴───────────────────────┐
    │        POSTPROCESSOR.PY: get_results()             │
    └───────────────────────────────────────────────────┘
                                │
              for v in range(data['num_vehicles']):  ← v = 0..4
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
          v=0,1,2           v=3,4
          Real vehicles     Dummy vehicles
              │                 │
          routes[v]:        routes[v]:
          [0→...→0]         [0→62→0] or [0→63→0]
          times[v]:         times[v]:
          [0,...,59617]     [13h11m38s, 400h0m0s]
              │                 │ ← PROBLEM!
              │                 │ times[-1] = 1,440,000
              │                 │
              └─────────────────┤
                                │
    Line 378: total_time_all_vehicles = 
      sum(times[-1] for times in estimated_times)
                                │
         ┌──────────────────────┴──────────────────────┐
         │                                             │
    59617 + 61063 + 14551                    1440000 + 1440000
    = 135231 seconds                         = 2,880,000 seconds
    = 37h 33m 51s (CORRECT)                  = 800h (BUG!)
                                             │
                    RESULT: 135231 + 2,880,000 = 3,015,231
                           = 837 hours (WRONG!)
