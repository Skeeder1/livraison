# Principled termination for OR-Tools GLS on small CVRPTW instances — sources and findings

Date: 2026-09-13. OR-Tools sources read from branch `stable` (commit `98c165af62df62b3056c2ee0fca66b24e79097cb`, release v9.15; last change to `routing_parameters.proto` on 2025-12-09). Local runtime used for the probes: `ortools 9.15.6755` (the project's `uv` environment). All line numbers below refer to that commit. Papers were read from the PDFs cited; quotes are verbatim.

## Recommendation

OR-Tools has exactly one non-clock, non-count stopping rule, `improvement_limit_parameters` (`ImprovementSearchLimit`), and it is not a stagnation detector: it fires only *at the moment a new improvement arrives* whose gain-per-neighbour-explored is too small relative to a threshold learned during the initial greedy descent, it never fires when the search has simply stopped improving, and on a 45-customer probe it needed `improvement_rate_coefficient` in the range 10^2–10^4 to do anything other than stop at the first local optimum (0.2 s) — a scale-dependent knob no paper calibrates. The rule the state-of-the-art solvers actually use is "N consecutive iterations without improvement of the best solution, plus a hard time limit" (HGS-CVRP: `nbIter` = 20 000; PyVRP: `NoImprovement`; SISR: fixed iteration count; KGLS: time limit only), and GLS's own authors state that GLS has no natural convergence signal ("Since GLS is not trapped in local minima, it is not clear when to stop the algorithm"). OR-Tools cannot express "iterations without improvement" natively, so the per-instance optimal time must be enforced from the `AddAtSolutionCallback` hook: track the best cost and its timestamp, and when no improvement has occurred for a stagnation window τ (in seconds or accepted solutions) call `routing.solver().FinishCurrentSearch()`, keeping `time_limit` as the hard backstop — verified on 9.15.6755 (a 3 s window stopped a 30 s run at 9.9 s with `status == ROUTING_SUCCESS`). Choose τ from the measured convergence curves (the 1 s / 5 s / 10 s medians already collected), and report the stop reason ("stagnation" vs "time limit") because the OR-Tools `status()` will be `ROUTING_SUCCESS` (1) in both cases; the DIMACS budgets (1 800 s standardised for n ≤ 200) and Vidal's `Tmax = 2.4 s × n` are research budgets for closing the last 0.1 % to BKS and are not the right reference for a demo.

---

## 1. OR-Tools routing termination controls

### 1.1 Every limit field in `RoutingSearchParameters`

Source: `ortools/constraint_solver/routing_parameters.proto`,
https://github.com/google/or-tools/blob/98c165af62df62b3056c2ee0fca66b24e79097cb/ortools/constraint_solver/routing_parameters.proto#L503-L535
(raw: https://raw.githubusercontent.com/google/or-tools/stable/ortools/constraint_solver/routing_parameters.proto)

Lines 503–535, verbatim:

```proto
  // -- Search limits --
  // Limit to the number of solutions generated during the search. 0 means
  // "unspecified".
  int64 solution_limit = 8;
  // Limit to the time spent in the search.
  google.protobuf.Duration time_limit = 9;
  // Limit to the time spent in the completion search for each local search
  // neighbor.
  google.protobuf.Duration lns_time_limit = 10;
  // Ratio of the overall time limit spent in a secondary LS phase with only
  // intra-route and insertion operators, meant to "cleanup" the current
  // solution before stopping the search.
  // TODO(user): Since these operators are very fast, add a parameter to cap
  // the max time allocated for this second phase (e.g.
  // Duration max_secondary_ls_time_limit).
  double secondary_ls_time_limit_ratio = 57;

  // Parameters required for the improvement search limit.
  message ImprovementSearchLimitParameters {
    // Parameter that regulates exchange rate between objective improvement and
    // number of neighbors spent. The smaller the value, the sooner the limit
    // stops the search. Must be positive.
    double improvement_rate_coefficient = 38;
    // Parameter that specifies the distance between improvements taken into
    // consideration for calculating the improvement rate.
    // Example: For 5 objective improvements = (10, 8, 6, 4, 2), and the
    // solutions_distance parameter of 2, then the improvement_rate will be
    // computed for (10, 6), (8, 4), and (6, 2).
    int32 improvement_rate_solutions_distance = 39;
  }
  // The improvement search limit is added to the solver if the following
  // parameters are set.
  ImprovementSearchLimitParameters improvement_limit_parameters = 37;
```

Note: the field is named `improvement_rate_solutions_distance`, not `improvement_rate_solutions_in_history` as guessed in the brief. There is no field named "stagnation", "convergence", "no_improvement" or similar anywhere in the proto (grep over the whole file for `limit|improvement|stagnat|converg`: only the lines above plus `optimization_step` at line 495 — "Minimum step by which the solution must be improved in local search. 0 means "unspecified"." — which is a move-acceptance threshold, not a stop rule).

Two related but non-terminating fields (lines 434–439):

```proto
  // Local search metaheuristics alternatively used to guide the search. Every
  // num_max_local_optima_before_metaheuristic_switch local minima found by a
  // metaheurisitic, the solver will switch to the next metaheuristic. Cannot be
  // defined if local_search_metaheuristic is different from UNSET or AUTOMATIC.
  repeated LocalSearchMetaheuristic.Value local_search_metaheuristics = 63;
  int32 num_max_local_optima_before_metaheuristic_switch = 64;
```

Defaults, from `ortools/constraint_solver/routing_parameters.cc` lines 177–197 (https://github.com/google/or-tools/blob/98c165af62df62b3056c2ee0fca66b24e79097cb/ortools/constraint_solver/routing_parameters.cc#L177-L197):

```cpp
  p.set_num_max_local_optima_before_metaheuristic_switch(200);
  p.set_guided_local_search_lambda_coefficient(0.1);
  p.set_guided_local_search_reset_penalties_on_new_best_solution(false);
  ...
  // No global time_limit by default.
  p.set_solution_limit(kint64max);
  p.mutable_lns_time_limit()->set_nanos(100000000);  // 0.1s.
  p.set_secondary_ls_time_limit_ratio(0);
```

`improvement_limit_parameters` is unset by default (`DefaultRoutingSearchParameters().HasField('improvement_limit_parameters')` returns `False` on 9.15.6755). Validation (`routing_parameters.cc` lines 824–843) requires `improvement_rate_coefficient > 0` and `improvement_rate_solutions_distance > 0`.

The official docs page https://developers.google.com/optimization/routing/routing_options lists only three limits ("Search limits terminate the solver after it reaches a specified limit, such as the maximum length of time, or number of solutions found. … `solution_limit` … `time_limit.seconds` … `lns_time_limit.seconds`"). The improvement limit is not documented there; the doc page also misstates the `lns_time_limit` default as "100" seconds where the code sets 0.1 s. The docs also define status `2` as "`ROUTING_PARTIAL_SUCCESS_LOCAL_OPTIMUM_NOT_REACHED`: Problem solved successfully after calling `RoutingModel.Solve()`, except that a local optimum has not been reached. Leaving more time would allow improving the solution." — in the probes below every run, whether stopped by clock, by the improvement limit or by the callback, returned status `1` (`ROUTING_SUCCESS`), so `status()` cannot be used to distinguish the stop reason.

### 1.2 What `ImprovementSearchLimit` measures and stops on

API comment, `ortools/constraint_solver/constraint_solver.h` lines 2475–2481 (https://github.com/google/or-tools/blob/98c165af62df62b3056c2ee0fca66b24e79097cb/ortools/constraint_solver/constraint_solver.h#L2475-L2481):

```cpp
  /// Limits the search based on the improvements of 'objective_var'. Stops the
  /// search when the improvement rate gets lower than a threshold value. This
  /// threshold value is computed based on the improvement rate during the first
  /// phase of the search.
  ABSL_MUST_USE_RESULT ImprovementSearchLimit* MakeImprovementLimit(
```

Installation in the routing model, `ortools/constraint_solver/routing.cc` lines 6502–6515:

```cpp
void RoutingModel::SetupImprovementLimit(
    const RoutingSearchParameters& search_parameters) {
  if (!search_parameters.has_improvement_limit_parameters()) return;

  SearchMonitor* const improvement_limit = solver_->MakeImprovementLimit(
      cost_, /*maximize=*/false, search_parameters.log_cost_scaling_factor(),
      search_parameters.log_cost_offset(),
      search_parameters.improvement_limit_parameters()
          .improvement_rate_coefficient(),
      search_parameters.improvement_limit_parameters()
          .improvement_rate_solutions_distance());
  monitors_.push_back(improvement_limit);
  secondary_ls_monitors_.push_back(improvement_limit);
}
```

Implementation, `ortools/constraint_solver/search.cc` lines 4872–4955 (https://github.com/google/or-tools/blob/98c165af62df62b3056c2ee0fca66b24e79097cb/ortools/constraint_solver/search.cc#L4872-L4955). The decisive parts:

```cpp
bool ImprovementSearchLimit::CheckWithOffset(absl::Duration) {
  if (!objective_updated_) {
    return false;
  }
  objective_updated_ = false;

  std::vector<double> improvement_rates(improvements_.size());
  for (int i = 0; i < improvements_.size(); ++i) {
    if (improvements_[i].size() <= improvement_rate_solutions_distance_) {
      return false;
    }

    const auto [cur_obj, cur_neighbors] = improvements_[i].back();
    const auto [prev_obj, prev_neighbors] = improvements_[i].front();
    DCHECK_GT(cur_neighbors, prev_neighbors);
    improvement_rates[i] =
        (prev_obj - cur_obj) / (cur_neighbors - prev_neighbors);
    if (gradient_stage_) continue;
    const double scaled_improvement_rate =
        improvement_rate_coefficient_ * improvement_rates[i];
    if (scaled_improvement_rate < thresholds_[i]) {
      return true;
    } else if (scaled_improvement_rate > thresholds_[i]) {
      return false;
    }
  }
  if (gradient_stage_ && std::lexicographical_compare(
                             improvement_rates.begin(), improvement_rates.end(),
                             thresholds_.begin(), thresholds_.end())) {
    thresholds_ = std::move(improvement_rates);
  }
  return false;
}
```

```cpp
bool ImprovementSearchLimit::AtSolution() {
  ...
  const bool is_improvement = std::lexicographical_compare(
      scaled_new_objectives.begin(), scaled_new_objectives.end(),
      best_objectives_.begin(), best_objectives_.end());
  if (gradient_stage_ && !is_improvement) {
    gradient_stage_ = false;
    // In case we haven't got enough solutions during the first stage, the
    // limit never stops the search.
    for (int i = 0; i < objective_vars_.size(); ++i) {
      if (thresholds_[i] == std::numeric_limits<double>::infinity()) {
        thresholds_[i] = -1;
      }
    }
  }

  if (is_improvement) {
    objective_updated_ = true;
    for (int i = 0; i < objective_vars_.size(); ++i) {
      improvements_[i].push_back(
          std::make_pair(scaled_new_objectives[i], solver()->neighbors()));
      // We need to have 'improvement_rate_solutions_distance_' + 1 element in
      // the 'improvements_', so the distance between improvements is
      // 'improvement_rate_solutions_distance_'.
      if (improvements_[i].size() - 1 > improvement_rate_solutions_distance_) {
        improvements_[i].pop_front();
      }
      ...
    }
    best_objectives_ = std::move(scaled_new_objectives);
  }
  return true;
}
```

Reading of the code (verified facts, not paraphrase of the docs):

1. **Unit of "rate".** `improvement_rate = (obj_k−d − obj_k) / (neighbors_k − neighbors_k−d)`: objective gained per *neighbour explored* (`solver()->neighbors()` is the count of neighbours evaluated so far), over the last `d = improvement_rate_solutions_distance` improvements of the best objective. It is not per second and not per accepted solution.
2. **Two stages.** While every accepted solution improves the best (`gradient_stage_`, i.e. the initial greedy descent before GLS accepts its first uphill move), each computed rate that is lower than the current threshold *becomes* the threshold. So the threshold is the smallest improvement-per-neighbour rate observed during the initial descent. The first non-improving accepted solution ends this stage for good.
3. **Stop condition.** After that, at each new improvement, stop iff `improvement_rate_coefficient × rate < threshold`. Because GLS-phase improvements come after thousands of explored neighbours whereas descent improvements come after a handful, GLS-phase rates are orders of magnitude smaller than the threshold; a coefficient ≤ 1 therefore stops at the first GLS improvement.
4. **No stagnation detection.** `CheckWithOffset` returns `false` immediately unless `objective_updated_` is set, and it is only set by an improvement. A search that has stopped improving entirely never triggers the limit; only a *slow* improvement does.
5. **Degenerate case.** If fewer than `d + 1` improvements happen before the first non-improving solution, the threshold is set to −1 and "the limit never stops the search" (comment in the source).

Empirical probe (random 45-customer CVRP, 8 vehicles, PCI + GLS, `time_limit = 30 s`, script `scratchpad/stop/probe_stop.py`, OR-Tools 9.15.6755):

| setting | wall | best | comment |
|---|---|---|---|
| no improvement limit | 30.00 s | 11 358 | last improvement at 24.3 s; 2 455 accepted solutions, 64 improvements |
| coef 0.02 / 0.1 / 0.5 / 2, d = 10 | 0.21 s | 12 106 | stops at the first GLS improvement after the descent (57 solutions) |
| coef 10, d = 10 | 0.81 s | 12 094 | |
| coef 100, d = 10 | 3.70 s | 12 037 | |
| coef 1 000, d = 10 | 24.51 s | 11 405 | |
| coef 10 000, d = 10 | 30.00 s | 11 358 | never fires |
| coef 0.5, d = 50 | 30.00 s | 11 358 | never fires: the descent produced < 51 improvements, threshold forced to −1 |
| coef 100, d = 3 / d = 20 | 3.72 s / 3.75 s | 12 020 / 11 844 | |

Conclusion: the native improvement limit is usable only with a coefficient of order 10^2–10^4, and the "right" value depends on the ratio between descent-phase and GLS-phase rates, i.e. on instance size, cost scale and operators. It is not a stagnation rule and cannot be mapped to "no improvement for τ seconds" or "for N iterations".

### 1.3 Does OR-Tools GLS have a notion of convergence? No.

`search.cc` lines 4234–4272: the GLS monitor's `AtLocalOptimum()` recomputes utilities, increments penalties on the max-utility arcs and unconditionally returns `true`:

```cpp
// Penalize (var, value) pairs of maximum utility, with
// utility(var, value) = cost(var, value) / (1 + penalty(var, value))
template <typename P>
bool GuidedLocalSearch<P>::AtLocalOptimum() {
  solver()->SetUseFastLocalSearch(false);
  ...
  for (int var = 0; var < num_vars_; ++var) {
    if (utilities[var] == max_utility) {
      ...
        penalties_.IncrementPenalty({var, value});
      ...
    }
  }
  SetCurrentInternalValue(0, std::numeric_limits<int64_t>::max());
  return true;
}
```

and `constraint_solver.h` lines 4002–4004 define the contract: "Called when a local optimum is reached. If 'true' is returned, the last solution is discarded and the search proceeds with the next one." The only early `return false` is when the assignment was never synced (infeasible). OR-Tools' own comment when building the metaheuristic (`routing.cc` lines 6351–6355):

```cpp
    // Some metaheuristics will effectively never terminate; warn
    // user if they fail to set a time limit.
    bool limit_too_long = !search_parameters.has_time_limit() &&
                          search_parameters.solution_limit() ==
                              std::numeric_limits<int64_t>::max();
```

So GLS in OR-Tools is run-to-deadline by construction; there is no penalty-saturation or convergence check.

### 1.4 The callback route (verified)

`routing.h` lines 1378–1385: "Adds a callback called each time a solution is found during the search. This is a shortcut to creating a monitor to call the callback on AtSolution() and adding it with AddSearchMonitor." `constraint_solver.h` lines 3217–3219: "Tells the solver to kill or restart the current search. `void FinishCurrentSearch(); void RestartCurrentSearch();`". Both are exposed in Python (`routing.AddAtSolutionCallback`, `routing.solver().FinishCurrentSearch()`), and the project already installs such a callback (`optimizer/solver.py:726`).

Probe: same instance, callback stops when `now − t_best > 3 s` → `wall = 9.92 s, best = 11 582, t_best = 6.92 s, status = 1, 820 accepted solutions`. The callback runs on every accepted solution (improving or not — GLS accepts uphill moves continuously, 2 455 in 30 s on this instance), so a time-based stagnation window is evaluated often enough; the hard `time_limit` remains as backstop in case the solver explores without accepting for a long time. Accepted-solution-count windows are also possible since `routing.solver().Solutions()` and `WallTime()` are readable from the callback; `Solver::neighbors()` (the unit used by `ImprovementSearchLimit`) is not exposed in the Python wrapper on 9.15.6755, so the callback-based rule must be expressed in seconds or in accepted solutions, not in neighbours.

---

## 2. How the state-of-the-art VRP solvers terminate

### 2.1 HGS-CVRP (Vidal 2022)

Paper: T. Vidal, "Hybrid genetic search for the CVRP: Open-source implementation and SWAP* neighborhood", Computers & Operations Research 140 (2022) 105643; arXiv:2012.10384v2 (https://arxiv.org/abs/2012.10384). Quotes from the arXiv v2 PDF:

- Section 2: "This process is repeated until a termination criterion is attained, typically a number of consecutive iterations Nit without improvement or a time limit Tmax."
- Algorithm 1, line 2: "while number of iterations without improvement < Itni and time < Tmax do"
- Section 4 (parameters): "The algorithm can be run with a termination criterion based on a number of consecutive iterations without improvement Nit (20,000 per default) or a CPU time limit Tmax. In the latter case, the algorithm restarts after each Nit iterations without improvement and collects the best solution until the time limit."
- Section 5 (benchmark protocol): "We monitor each algorithm's progress up to a time limit of Tmax = n × 240/100 seconds, where n represents the number of customers. Therefore, the smallest instance with 100 clients is run for 4 minutes, whereas the largest instance containing 1000 clients is run for 40 minutes. During each run, we record the best solution value after 1%, 2%, 5%, 10%, 15%, 20%, 30%, 50%, 75%, and 100% of the time limit" — on "a single thread of an Intel Gold 6148 Skylake 2.4 GHz processor". OR-Tools was included as a baseline: "We use the guided local search (GLS) variant of this solver as recommended in the documentation." Result at Tmax: "HGS-CVRP obtains (with an average gap of 0.11% …) … KGLS (0.53%), HILS (0.66%), LKH-3 (1.00%), and OR-Tools (4.01%)."

Code (https://github.com/vidalt/HGS-CVRP):

- `Program/AlgorithmParameters.h` lines 23–25: `int nbIter; // Nb iterations without improvement until termination (or restart if a time limit is specified). Default value: 20,000 iterations` and `double timeLimit; // CPU time limit until termination in seconds. Default value: 0 (i.e., inactive)`.
- `Program/Genetic.cpp` line 11: `for (nbIter = 0 ; nbIterNonProd <= params.ap.nbIter && (params.ap.timeLimit == 0 || (double)(clock()-params.startTime)/(double)CLOCKS_PER_SEC < params.ap.timeLimit) ; nbIter++)`; lines 26–27: `if (isNewBest) nbIterNonProd = 1; else nbIterNonProd ++ ;`; lines 33–37: `if (params.ap.timeLimit != 0 && nbIterNonProd == params.ap.nbIter) { population.restart(); nbIterNonProd = 1; }`.
- `README.md`: "[-it <int>] sets a maximum number of iterations without improvement. Defaults to 20,000" / "[-t <double>] sets a time limit in seconds. If this parameter is set, the code will be run iteratively until the time limit".

Note "iteration" here = one crossover + one full local-search education of an offspring, i.e. a coarse unit; 20 000 of them is minutes on 100–1000-customer instances.

PyVRP (the HGS implementation that won the DIMACS VRPTW track, https://github.com/PyVRP/PyVRP) exposes the same rule as a class, `pyvrp/stop/NoImprovement.py`: "Criterion that stops if the best solution has not been improved for a fixed number of iterations." with `__call__(best_cost)` incrementing a counter on non-improvement and returning `counter >= max_iterations`; alongside `MaxRuntime`, `MaxIterations`, `FirstFeasible`, `MultipleCriteria` (`pyvrp/stop/__init__.py`).

### 2.2 SISR (Christiaens & Vanden Berghe 2020)

Paper: "Slack Induction by String Removals for Vehicle Routing Problems", Transportation Science 54(2), 2020; technical report version 7.05.2018 read from KU Leuven (Lirias). Quotes:

- Section 3: "The SISRs neighborhood search … is guided by Simulated Annealing (SA). … the system's initial temperature T0 is reduced by the exponential cooling schedule (Equation 1) to its final temperature Tf in f iterations."
- Algorithm 1, line 4: "for f iterations do" (the loop is a fixed-length count; no improvement-based exit).
- Parameters: "T0 = 100, Tf = 1 … The search begins at an initial temperature T0 = 100 and ends at the final temperature Tf = 1." / "iterations = it(v) The number of iterations it is determined as a function of problem size v by linear interpolation. The minimum and maximum problem size is 100 and 1000 respectively, as per Uchoa et al. (2017). The present study set it(100) = 3 × 10^7 and it(1000) = 3 × 10^8, thus enabling the direct comparison of SISRs' calculation times against those from the aforementioned paper."

So SISR's termination is a size-scaled fixed iteration budget dictated by the cooling schedule (SA needs to reach Tf), not a stagnation rule.

### 2.3 KGLS (Arnold, Gendreau & Sörensen 2019)

Paper: "Efficiently solving very large-scale routing problems", Computers & Operations Research 107 (2019) 32–42, https://doi.org/10.1016/j.cor.2019.03.006; accepted manuscript read from https://repository.uantwerpen.be/docman/irua/e11288/160227_2020_01_01.pdf. Quotes:

- Algorithm 1 ("Knowledge-guided local search heuristic (KGLS), as developed in Arnold and Sörensen (2019)"), line 3: "while time limit not reached do" — followed by perturbation ("while not P = 100 moves have been made do … Penalize edge (i, j) with the highest value b(i, j) by incrementing p(i, j)") and optimization until local optimum.
- "KGLS is entirely based on a local search with the steepest descent acceptance criterion, and thus, it works in a deterministic fashion. … For most instances with up to 1000 customers, it does not require more than a few minutes to compute a solution with a gap of 1% and less to the best known solutions".
- Budgets used: "In the 'long' runtime setup we allow 5 minutes per 1,000 customers." and, for the new very-large instances, "given 3 minutes (short runtime) and 12 minutes (longer runtime) of computational time per 1000 customers".

KGLS, the GLS-based state-of-the-art, therefore has no internal stopping rule at all: pure time limit, with the budget chosen per 1 000 customers.

---

## 3. DIMACS 12th Implementation Challenge (2021–2022) protocol

Rules PDFs (read as text): CVRP track, "12th DIMACS Implementation Challenge: CVRP track", December 1st, 2021, http://dimacs.rutgers.edu/images/programs/implementation_challenges/archive/CVRP_Competition_Rules.pdf; VRPTW track, same date, http://dimacs.rutgers.edu/images/programs/implementation_challenges/archive/VRPTW_Competition_Rules.pdf (challenge page: https://dimacs.rutgers.edu/programs/implementation-challenges/vehicle-routing). Controller source: https://github.com/laser-ufpb/VRPTWController.

Time budgets, verbatim:

- CVRP: "5. The time limit: 1,800 seconds for instances with n ≤ 200, 3,600 seconds for 200 < n ≤ 400, and 7,200 seconds for n > 400."
- VRPTW: "4. The time limit: 1,800 seconds for instances with n ≤ 201, 3,600 seconds for 201 < n ≤ 801, and 7,200 seconds for n > 801."

Machine normalisation, verbatim (identical wording in both tracks):

> "4. The CPU mark. In order to compensate for different processor speeds, Controller will standardize (i.e., scale) times according to the CPU marks provided by PassMark Single Thread Performance. Currently, the top CPU mark is 4,202, while mid-range desktop processors have marks around 2,000. So, we choose the mark 2,000 to define our standardized times. This means that if a run is performed in a processor Intel Core i9-9900T @ 2.10GHz that has mark 2,400, all local elapsed times will be multiplied by 1.2 to obtain the corresponding standardized times. This also means that a standardized time limit of 1,800 seconds will actually correspond to 1,500 seconds in that particular machine. • Runs must be performed in a processor listed in PassMark and having a mark of at least 1,500."

Sample Controller header from the rules: "PassMark Single Thread Benchmark: 2367 / Time factor: 1.18 (baseline 2000) / … Standardized Time limit: 1800 secs / Local Machine Time Limit: 1521 secs". Controller invocation: `./VRPTWController <Competitor ID> <Instance path> <CPU mark> <Time limit> <Instance BKS> <If BKS is optimal [0/1]> <Path to solver>`.

Scoring is the *primal integral* over the whole budget, which is what makes "when to stop" moot in the challenge — the solver is killed at T, and stopping earlier only costs points: "Let T be the maximum running time (in seconds) defined for a given instance … PI = 100 × [ (Σ v(i−1)·(t(i)−t(i−1)) + v(n)·(T−t(n))) / (T × BKS) − 1 ]" with v(0) = 1.1 × BKS. Also: "Controller will kill Solver process after the given time limit and compute the Primal Integral of the run. If Solver stops by itself (or crashes), Controller still computes a valid Primal Integral." and "The last parameter [local machine time limit] can be used by the solver in its strategy." The optimal-BKS shortcut is the only early stop: "If 1, means that the BKS is proven to be optimal. Controller saves computing resources by killing a Solver that already obtained an optimal solution."

Interpretation for the demo: the community "fair time" is 1 800 standardised seconds even for a 25-customer Solomon instance, because the goal is the last 0.01 % to BKS under a primal-integral score. This is a research-benchmark budget, not a product-latency budget; it does justify the general shape "budget grows stepwise with n" and "normalise by single-thread speed" if the demo ever runs on heterogeneous machines.

---

## 4. Guided Local Search: is there a natural convergence signal?

Primary sources: C. Voudouris & E. Tsang, "Guided local search and its application to the traveling salesman problem", European Journal of Operational Research 113 (1999) 469–499 (preprint read from https://www.inf.ufpr.br/aurora/disciplinas/topicosia/papers/gls.pdf); C. Voudouris, E. Tsang & A. Alsheddy, "Guided Local Search", in Handbook of Metaheuristics, 2nd ed., Springer 2010, ch. 11 (read from https://www.bracil.net/CSP/papers/VTA-GLS-Handbook2010.pdf).

The method is defined with an abstract `while StoppingCriterion do` loop (both papers). The authors' own answer on termination, Handbook 2010, section 4.2.6 "Stopping criterion", verbatim:

> "There are many choices possible for the StoppingCritetion. Since GLS is not trapped in local minima, it is not clear when to stop the algorithm. Like other meta-heuristics, we usually resort to a measure related to the length of the search process. For example, we may choose to set a limit on the number of moves performed, the number of moves evaluated, or the CPU time spent by the algorithm. If a lower bound is known, we can utilize it as a stopping criterion by setting the gap to be achieved between the best known solution and the lower bound. Criteria can also be combined to allow for a more flexible way to stop the GLS method."

Penalties do not saturate; the 1999 paper describes penalty growth as a *continuous diversification* that keeps the search moving indefinitely:

> "If a feature is penalized many times over a number of iterations then the term ci/(1+pi) in (2) decreases for the feature, diversifying choices and giving the chance for other features to also be penalized."

> "As the penalties build up for both bad and good edges frequently appearing in local minima, the algorithm starts exploring new regions in the search space, incorporating edges not previously seen and therefore not penalized. The speed of this "continuous" diversification of search is controlled by the parameter λ. A low λ slows down the diversification process, allowing the algorithm to spend more time in the current area before it is forced by the penalties to explore other areas. Conversely, a high λ speeds up diversification, at the expense of intensification."

In their own experiments the stop is a fixed iteration count: "The stopping criterion used was a limit on the number of iterations not to be exceeded." (1999, section on TSP experiments), and elsewhere a fixed CPU time ("The same time limit (5 minutes of CPU time on DEC Alpha…"). Both papers list termination as open: 1999 conclusions — "Other potentially interesting research directions include automated tuning of the parameter lambda, definition of effective termination criteria, and different utility functions for selecting the features penalized."; Handbook 2010 conclusions — "automated tuning of the λ or α parameters, definition of effective termination criteria, alternative utility functions for selecting the features to be penalised and also studies about the convergence properties of GLS."

Conclusion: GLS is inherently run-to-deadline (or run-to-count). There is no penalty-saturation or convergence signal in the method as published, and OR-Tools' implementation (section 1.3) faithfully has none either. This is consistent with KGLS (section 2.3) using nothing but a time limit.

---

## 5. What could not be verified / caveats

- The SISR quotes come from the 2018 KU Leuven technical-report version, not the final Transportation Science 2020 typeset article (paywalled); the parameter section is the same in substance but page/section numbering may differ.
- The KGLS quotes are from the accepted manuscript on the Antwerp repository, not the Elsevier final PDF.
- The probes in section 1.2/1.4 use a synthetic CVRP without time windows and one seed; the qualitative behaviour of `ImprovementSearchLimit` (threshold learned from the descent, fires only at improvements, needs coef ≫ 1) follows from the code and is not seed-dependent, but the specific coefficient-to-time mapping is.
- OR-Tools line numbers are for commit `98c165a` on `stable` (v9.15); they will drift with future commits. The proto comments quoted are unchanged since the field was introduced (field numbers 37–39).
- Not searched: whether OR-Tools' newer `ortools/routing` (v10 layout on `main`) changes any of this; the `stable` branch still hosts routing under `constraint_solver/`.
