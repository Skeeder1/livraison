# Quick Fix for Time Calculation Bug

## The Problem
```
Without hubs:  14h 59m 46s  ✓ CORRECT
With hubs:    837h 33m 51s  ✗ 56x LARGER - WRONG!
```

## Why It Happens
- Dummy vehicles (for hubs) have end times set to 1,440,000 seconds (400 hours)
- These are counted in the total time calculation at line 378 of postprocessor.py
- 2 dummy vehicles × 400h ≈ 800h extra = 837h total

## The Fix (Choose One)

### Option 1: Store num_real_vehicles in data (SIMPLEST)

**File: optimizer/solver.py, line 72**
```python
# After this line:
data['num_vehicles'] = num_real_vehicles + data['num_hubs']

# Add this line:
data['num_real_vehicles'] = num_real_vehicles
```

**File: optimizer/postprocessor.py, line 378**
```python
# Change from:
total_time_all_vehicles = sum(times[-1] if times else 0 for times in estimated_times)

# To:
num_real_vehicles = data.get('num_real_vehicles', data['num_vehicles'])
total_time_all_vehicles = sum(
    times[-1] if times else 0 
    for times in estimated_times[:num_real_vehicles]
)
```

### Option 2: Pass num_real_vehicles as parameter (CLEANER)

**File: optimizer/solver.py**
Change all calls to `get_results()`:
```python
# From:
results_no_hubs = get_results(data_no_hubs, manager_no_hubs, routing_no_hubs, solution_no_hubs)

# To (pass num_real_vehicles):
results_no_hubs = get_results(data_no_hubs, manager_no_hubs, routing_no_hubs, solution_no_hubs, 
                               data_no_hubs.get('num_real_vehicles'))
```

**File: optimizer/postprocessor.py, line 247**
```python
def get_results(data: Dict[str, Any], manager, routing, solution, num_real_vehicles=None) -> Dict[str, Any]:
    if num_real_vehicles is None:
        num_real_vehicles = data.get('num_real_vehicles', data['num_vehicles'])
    
    # ... rest of function ...
    
    # Line 378:
    total_time_all_vehicles = sum(
        times[-1] if times else 0 
        for times in estimated_times[:num_real_vehicles]
    )
```

## Verification
After applying the fix, test should show:
```
Without hubs:  14h 59m 46s
With hubs:     37h 34m 11s  (or similar reasonable time)
```

The with-hubs time will be higher than without-hubs because hubs add complexity, but it will be:
- In the realm of actual delivery times (24-48 hours typical)
- Not 56x larger than without hubs
- Not including fake 400-hour dummy vehicle constraints
