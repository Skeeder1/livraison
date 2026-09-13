# Criteria for the "optimal computation time" of an anytime metaheuristic

Scope: a per-instance best-so-far curve `(time_ms, best_objective)` from a 60 s OR-Tools GLS run
(monotone non-increasing, piecewise constant, steep drop then plateau), plus a population of such
curves. All claims below are checked against the primary source cited; where I could not find a
primary source I say so.

## Recommendation (five sentences)

1. Adopt the **anytime / deliberation-scheduling criterion**: for a chosen cost of time `c`
   (quality units per second), the optimal time is `t* = argmax_t [ -f(t) - c·t ]`, which on a
   diminishing-returns curve is the first moment where the marginal improvement rate of the
   best-so-far objective falls below `c` (Zilberstein 1996, Theorem 5; Boddy & Dean 1994; Russell
   & Wefald's "intrinsic utility minus time cost").
2. Do this instead of a knee detector because every geometric knee (Kneedle, max distance to the
   chord, max curvature after normalisation) is *exactly* this same optimisation with `c` silently
   fixed to the chord slope `(f(0) - f(T)) / T`, i.e. the knee moves when you change the 60 s
   horizon or the quality of the initial solution — the knee is not a property of the algorithm,
   it is a property of your plotting window.
3. Choose `c` explicitly from the user context (for an interactive demo: how much route-cost
   improvement justifies one more second of a visitor's wait, anchored on Nielsen's 1 s / 10 s
   attention limits), and report `t*(c)` for two or three values of `c` rather than one number.
4. For the **population budget** keep what you already do, but describe it with the standard
   vocabulary of Hoos & Stützle: the time-to-target for relative target `q'` is a random variable
   per instance; your budget is the empirical `p`-quantile of the time-to-target distribution
   (median of the 0.5 % TTT, third quartile of the 5 % TTT) — that is a *qualified run-time
   distribution* (QRTD) analysis in Hoos & Stützle's "type 2" application scenario.
5. Compute `t*` on the raw improvement events (no smoothing, no interpolation): because the curve
   is piecewise constant, `argmax` over the event list is exact and trivially O(n), and it avoids
   the flat-extrema / non-uniform-sampling failure modes that break Kneedle on this kind of data.

---

## 1. Knee / elbow detection methods

### 1.1 Kneedle (Satopää, Albrecht, Irwin, Raghavan 2011)

Source (author copy): https://raghavan.usc.edu/papers/kneedle-simplex11.pdf — ICDCS Workshops
2011, pp. 166–171, doi:10.1109/ICDCSW.2011.20.

Definition of a knee (their §II.A): the point of maximum curvature of the continuous function,
`K_f(x) = f''(x) / (1 + f'(x)^2)^{1.5}`. Quoted rationale: "curvature is a mathematical measure of
how much a function differs from a straight line. As a result, maximum curvature captures the
leveling off effect operators use to identify knees."

Algorithm (their §III, verbatim structure):

1. Smooth: "First we use a smoothing spline to preserve the shape of the original data set as
   much as possible, although other smoothing techniques, such as an exponentially weighted
   moving average, could also be used." → `D_s = {(x_si, y_si)}`.
2. Normalise to the unit square: `x_sni = (x_si − min x_s)/(max x_s − min x_s)`,
   `y_sni = (y_si − min y_s)/(max y_s − min y_s)`.
3. Difference curve: `D_d = {(x_di, y_di)}` with `x_di = x_sni`, `y_di = y_sni − x_sni`
   (the vertical distance to the diagonal y = x, i.e. to the chord joining the end points).
4. Candidate knees = local maxima of the difference curve:
   `y_lmx_i = y_di | y_d(i−1) < y_di, y_d(i+1) < y_di`.
5. Threshold per local maximum, with sensitivity `S`:
   `T_lmx_i = y_lmx_i − S · (1/(n−1)) · Σ_{i=1}^{n−1} (x_sn(i+1) − x_sn(i))`
   i.e. `S` times the *mean normalised x-spacing*. "Smaller values for S detect knees quicker,
   while larger values are more conservative. Put simply, S is a measure of how many 'flat'
   points we expect to see in the unmodified data curve before declaring a knee."
6. "If any difference value (x_dj, y_dj), where j > i, drops below the threshold y = T_lmx_i
   ... before the next local maximum in the difference curve is reached, Kneedle declares a knee
   at the x-value of the corresponding local maximum x = x_lmx_i. If the difference values reach
   a local minimum and starts to increase before y = T_lmx_i is reached, we reset the threshold
   value to 0 and wait for another local maximum to be reached."

Orientation: "we assume that the curves under consideration have negative concavity. For curves
with consistently positive concavity (e.g., forming 'elbows' rather than knees) it is trivial to
invert the graph by replacing each y_i with y_max − y_i and x_i with x_max − x_i." Your curve is
decreasing and convex → `curve="convex", direction="decreasing"` in `kneed`.

Parameter choice (their §IV.D): "in offline settings where Kneedle has perfect information, the
highest F-Score occurs when S = 0. In online settings ... overall S = 1 has the best results."
So for an offline post-mortem of a full 60 s trace the paper's own evidence says S = 0, which
reduces Kneedle to "the point farthest from the chord".

Failure modes on a monotone-decreasing, long-plateau best-so-far curve (each item: what the
source says, then why it bites here):

- **Horizon dependence (chord dependence).** Step 2 normalises by `max x − min x`, and step 3
  measures distance to the chord between the first and last point. For a smooth convex curve the
  maximiser of `y_sn − x_sn` satisfies `f'(t*) = (f(T) − f(0))/T` (first-order condition). Hence
  the "knee" is the point where the instantaneous improvement rate equals the *average* rate over
  the whole window; extend the run from 60 s to 120 s and the knee moves right; start recording
  from a worse initial solution and it moves left. The paper never claims horizon invariance;
  Salvador & Chan (§3.3, below) document the same effect for the L-method ("When there are far
  too many points on the right side of the actual knee, the knee that is located ... will most
  likely be larger than the actual knee").
- **Flat extrema / staircase.** Your curve is piecewise constant, so the difference curve has
  runs of equal values. The paper's local-maximum test uses strict inequalities (step 4), which
  never fires on a plateau. This is the bug reported in kneed issue #52 "KneeLocator fails if
  there are flat extrema" (https://github.com/arvkevi/kneed/issues/52); the fix (use
  `np.greater_equal`/`np.less_equal`) makes "every step ... detected as a local maximum/minimum"
  (issue thread), so `S` then decides which one wins.
- **Non-uniform sampling.** The threshold (step 5) is `S ×` the *mean* x-spacing. If you record
  one point per improvement event, spacing is milliseconds early and seconds late; the mean is
  meaningless and the online rule fires on the first plateau after the initial descent. Resample
  the best-so-far curve onto a uniform (or log-uniform) time grid before applying Kneedle
  (the paper's synthetic data are uniformly spaced; kneed's `interp1d` does not resample).
- **Long head.** If the first recorded point is the construction heuristic (very high cost),
  the chord is dominated by the first drop and the knee lands within the first few hundred ms,
  ignoring a later 2–3 % improvement. Antunes et al. describe this generically as a "long head"
  and add "an iterative refinement method to increase the resilience to long heads"
  (Antunes, Gomes, Aguiar, BigDataService 2018, doi:10.1109/BigDataService.2018.00042; abstract
  on ResearchGate). Salvador & Chan's iterative cutoff (`cutoff = currentKnee*2`) is the same idea.
- **Multiple knees.** Offline Kneedle "returns the first knee found"; online mode "corrects old
  knee points as it traverses the curve" and `kl.knee` is then "the last (most significant)
  knee" (kneed docs, https://kneed.readthedocs.io/en/latest/user-guide/multi-knee/). A curve with
  a fast descent, a plateau, and a late improvement gives two defensible answers; the method has
  no principled way to choose.
- **Smoothing.** The original uses a smoothing spline; kneed's default `interp1d` is a plain
  linear interpolant (no smoothing) and `polynomial` (degree 7 by default) overshoots on plateaus
  (kneed API doc, https://kneed.readthedocs.io/en/latest/api/). Neither reproduces the paper.

### 1.2 L-method (Salvador & Chan 2004)

Source: "Determining the Number of Clusters/Segments in Hierarchical Clustering/Segmentation
Algorithms", ICTAI 2004, pp. 576–584. Author copy: https://cs.fit.edu/~pkc/papers/ictai04salvador.pdf
(also FIT tech report CS-2003-18).

Defining sentence: "The knee is determined by finding the area between the two lines that most
closely fit the curve." Formally (their eq. 1–2), with points `x = 2..b`, left sequence `L_c`
(`x = 2..c`) and right sequence `R_c` (`x = c+1..b`), `c = 3..b−2`:

```
RMSE_c = (c−1)/(b−1) · RMSE(L_c) + (b−c)/(b−1) · RMSE(R_c)
ĉ      = argmin_c RMSE_c
```

"where RMSE(L_c) is the root mean squared error of the best-fit line for the sequence of points
in L_c (and similarly for R_c). The weights are proportional to the lengths of L_c (c−1) and
R_c (b−c)." They stress "The L method is very general and contains no parameters or constants."

Refinement (their §3.3) — directly relevant to plateaus: "The L method performs best when the
sizes of the two lines on each side of the knee are reasonably balanced. When there are far too
many points on the right side of the actual knee, the knee that is located by the L method will
most likely be larger than the actual knee." Their iterative refinement reruns the L-method on
`[0, 2·currentKnee]` until the knee stops moving, with a floor of ~20 points: "The cutoff value is
not permitted to drop below ~20". Complexity O(N²).

Failure modes for your curve: (i) it assumes both sides are approximately linear — an
exponential-like descent has no linear left branch, so the left fit is poor and the knee is
biased toward the plateau; (ii) the plateau is 90 % of the points, exactly their "too many points
on the right" case, so refinement is mandatory; (iii) on a piecewise-constant staircase the RMSE
is minimised by putting the split after the *last* big step, not at the point of best trade-off.

### 1.3 Maximum curvature (continuous and Menger)

Continuous definition: `K_f(x) = f''(x)/(1 + f'(x)^2)^{1.5}` (Kneedle §II.A). Discrete version:
"Menger curvature defines the curvature for three discrete points as the curvature of the circle
circumscribed about those points ... we define the Menger curvature for each point p_i in an
n-point data set as being equal to 1/r for the circle of radius r circumscribed about p_1, p_i,
and p_n" (Kneedle §II.B; Kneeliverse implements this as `menger.knee`).

Known problems, from the same source: curvature "is not well-defined for discrete data sets";
"end-points in a data set do not have curvature values by definition"; and "while Menger closely
approximates curvature for offline data drawn from ideal continuous functions, it does not work
well for the noisy online data sets typical of computing systems" (§II.B, §IV). Two further
points that follow from the formula: curvature is not invariant to rescaling one axis (changing
the objective from € to k€ or time from ms to s moves the maximum), which is why Kneedle
normalises to the unit square — and normalisation reintroduces the horizon dependence of §1.1.
On a piecewise-constant curve the second derivative is a sum of deltas, so "max curvature" is
undefined without smoothing.

### 1.4 Maximum perpendicular distance to the chord

Definition: with end points `P_1 = (x_1, y_1)`, `P_n = (x_n, y_n)`, the knee is
`argmax_i d_i`, `d_i = |(y_n − y_1)·x_i − (x_n − x_1)·y_i + x_n·y_1 − y_n·x_1| / sqrt((y_n − y_1)^2 + (x_n − x_1)^2)`.

Provenance: I could not find a single primary paper that "owns" this method. It appears as item 5
in Salvador & Chan's list of known methods ("The point on the curve that is furthest from a line
fitted to the entire curve" — note they say *fitted line*, not chord) with the comment that it
"only works well for continuous functions, and not curves where the knee is a sharp jump"; it is
what Kneedle Fig. 2(a) draws ("the perpendicular distance from y = x with the maximum distance
indicated"); and the Kneeliverse paper (Antunes et al., SoftwareX 2025,
doi:10.1016/j.softx.2025.102161) summarises Kneedle as "uses the point on the curve that is
furthest away from a line, defined by the head and tail points of the curve." The same max-distance
split is the recursion criterion of Ramer–Douglas–Peucker line simplification, which Kneeliverse
uses as a pre-processing step; that connection is my observation, not a quoted claim.

Property that matters here (derivation, not a quote): for a smooth convex `f` on `[0, T]`, the
maximiser of the distance to the chord is where the tangent is parallel to the chord,
`f'(t*) = (f(T) − f(0))/T`. So this method — and Kneedle with S = 0 — is the anytime optimum of
§2 with cost of time `c = (f(0) − f(T))/T`. Everything said about horizon dependence applies.

---

## 2. Time–quality trade-off as an optimisation (anytime algorithms)

Primary sources:
- Zilberstein, "Using Anytime Algorithms in Intelligent Systems", AI Magazine 17(3):73–83, 1996.
  http://rbr.cs.umass.edu/papers/Zaimag96.pdf
- Boddy & Dean, "Decision-Theoretic Deliberation Scheduling for Problem Solving in
  Time-Constrained Environments", Artificial Intelligence 67(2):245–285, 1994.
  https://cs.brown.edu/people/tdean/publications/archive/BoddyandDeanAIJ-94.pdf
- Dean & Boddy, "An Analysis of Time-Dependent Planning", AAAI 1988 (coins "anytime algorithm").

**Performance profile.** Zilberstein, Definition 1: "A PP of an anytime algorithm, Q(t), denotes
the expected output quality with execution time t." Built empirically from a *quality map*: "Each
point (t, q) represents an instance for which quality q was achieved with run-time t." His
worked example is a randomised TSP tour-improvement algorithm — i.e. your setting. Boddy & Dean
fitted `Q(t) = 1 − e^{−λt}`. Extensions: conditional PP `Pr(q_out | q_in, t)` (a distribution,
not an expectation) and dynamic PP `Pr(q_j | q_i, Δt)` (Markov model of improvement given the
current incumbent).

**Diminishing returns** is a *required* property: "The improvement in solution quality is larger
at the early stages of the computation, and it diminishes over time" (Zilberstein, desired
property 5). Boddy & Dean formalise it as a monotone increasing profile with monotone decreasing
first derivative (piecewise-linear with decreasing slopes in their scheduler).

**Utility = value of the result minus cost of time.** Boddy & Dean, quoting Russell & Wefald:
"the net value of computation is defined to be the difference between the utility of the state
resulting from the computation minus the utility of the state resulting from executing [the
default action] ... Russell and Wefald separate the intrinsic utility, that is, the utility of
an action independent of time, from the time cost of computational actions, defining the utility
of a state as the difference between these two: U(A_i, S_j) = U_I(A_i) − TC(S_j)". Horvitz's
version: the "comprehensive value of computation" is the "object-related value" (quality) discounted
by "a discounting factor for delayed treatment", combined under the assumption of "time cost
separability (object related value and the cost of delaying a decision are independent functions
of time)". Boddy & Dean caution: "determining an appropriate time cost function can become quite
complicated ... costs concerning hard and soft deadlines must be accounted for by this function."

**Optimal stopping.**
- Contract setting (allocation fixed before the run — your case, since you pick `time_limit`):
  Zilberstein, Theorem 4: "The fixed-contract monitoring strategy is optimal when the domain has
  predictable utility, and the system has a deterministic PP." The optimal contract is
  `t* = argmax_t [ U(Q(t)) − C(t) ]`.
- Interruptible setting: Theorem 5: "Monitoring interruptible algorithms using the value of
  computation criterion is optimal when the PP is monotonically increasing and concave down, and
  the cost of time is monotonically increasing and concave up." The rule is myopic: "the monitor
  must calculate the difference between the expected utility after one time increment ... and the
  current expected utility ... Deliberation is interrupted once this value becomes negative."
  With linear cost `C(t) = c·t` this is: stop when `dQ/dt < c`. Boddy & Dean's scheduler uses the
  same quantity — the slope of the profile is called the *gain*, and time is allocated to the
  procedure with the largest gain.

**Choosing the cost-of-time term for an interactive web demo.** The framework leaves `C(t)` to
the application; the sources give three shapes, and all three are usable:

1. *Linear* `C(t) = c·t`, `c` in quality units per second. If quality is the relative gap
   `g(t) = f(t)/f_ref − 1`, then `c` reads as "percent of route cost per second of waiting". With
   linear cost the optimum is the tangent criterion `−g'(t*) = c` and the answer is easy to
   audit. This is also the only form under which knees and utility coincide (§1.4).
2. *Convex (concave-up) cost*, as Theorem 5 requires for the myopic rule to be optimal: marginal
   impatience grows with the wait. A natural anchor is Nielsen's attention limits: "1.0 second is
   about the limit for the user's flow of thought to stay uninterrupted" and "10 seconds is about
   the limit for keeping the user's attention focused on the dialogue. For longer delays, users
   will want to perform other tasks" (Nielsen, "Response Times: The 3 Important Limits", 1993,
   https://www.nngroup.com/articles/response-times-3-important-limits/). A piecewise-linear cost
   that is cheap below 1 s, moderate to 10 s, and steep after 10 s encodes exactly that.
3. *Hard deadline* (Hoos & Stützle "type 2", §4): `C(t) = 0` for `t ≤ t_max`, `∞` after. Then the
   question degenerates to "best quality within t_max", which is what a fixed `time_limit` already
   does — the utility framework only adds value if you are willing to state `c`.

Practical recommendation: use (1) with two or three named values, e.g. `c ∈ {0.5, 0.1, 0.02} %/s`
("impatient / normal / patient visitor"), and check that `t*(c)` sits inside Nielsen's 1–10 s band
for the middle value. If `t*` is highly sensitive to `c`, the curve has no real knee and you should
say so instead of reporting one number.

---

## 3. Diminishing-returns / termination criteria used in VRP metaheuristics

Three families are in use; each states the value in the paper.

**(a) Iterations without improvement — HGS (Vidal 2022).** Source: Vidal, "Hybrid genetic search
for the CVRP: Open-source implementation and SWAP* neighborhood", C&OR 140:105643, 2022; arXiv
https://arxiv.org/abs/2012.10384 (PDF https://export.arxiv.org/pdf/2012.10384v2.pdf). Quote:
"This process is repeated until a termination criterion is attained, typically a number of
consecutive iterations N_it without improvement or a time limit T_max." Algorithm 1, line 2:
"while number of iterations without improvement < It_ni and time < T_max do". Values: "The
algorithm can be run with a termination criterion based on a number of consecutive iterations
without improvement N_it (20,000 per default) or a CPU time limit T_max. In the latter case, the
algorithm restarts after each N_it iterations without improvement and collects the best solution
until the time limit." The README (https://github.com/vidalt/HGS-CVRP) exposes these as
`-it` (default 20,000) and `-t`. Note the design: *no* "improvement below ε" rule; a plateau of
20,000 offspring is the stopping signal, and under a time limit the plateau triggers a restart.

**(b) Fixed iteration budget scaled with instance size — SISR (Christiaens & Vanden Berghe
2020).** Source: Transportation Science 54(2):417–433, 2020; technical-report version (7 May
2018) at https://lirias.kuleuven.be/retrieve/29d92f01-b92c-43f8-9d02-e3cb9210f33f/ . Table 3
(SISRs and SA parameters): `c̄ = 10`, `L_max = 10`, `α = 0.01`, `β = 0.01` (blink rate),
`T_0 = 100`, `T_f = 1`, "Fleet minimisation iterations = 10% of all iterations", and the
termination: "iterations = it(v). The number of iterations it is determined as a function of
problem size v by linear interpolation. The minimum and maximum problem size is 100 and 1000
respectively, as per Uchoa et al. (2017). The present study set it(100) = 3×10^7 and
it(1000) = 3×10^8, thus enabling the direct comparison of SISRs' calculation times against those
from the aforementioned paper." The SA schedule is exponential from `T_0` to `T_f` over exactly
those iterations, so the budget is not adaptive at all: the run length *is* the cooling schedule.
(I verified the 2018 technical report; the final 2020 typeset version was not open to me — if a
value differs there, the technical report is what I quote.)

**(c) Wall-clock budget proportional to n — KGLS (Arnold & Sörensen 2019) and Arnold, Gendreau &
Sörensen 2019.**
- Arnold & Sörensen, "Knowledge-guided local search for the vehicle routing problem", C&OR
  105:32–46, 2019; author PDF
  https://repository.uantwerpen.be/docman/irua/4b36e9/158505_2019_11_01.pdf . Quote (§4.5 and
  §6.1): "We assume that larger instances with more customers require more computation time and,
  thus, we define the abortion criterion as a maximum runtime with respect to the number of
  customers." "On each instance we run KGLS up to a defined time limit of 3·N/100 minutes, i.e.,
  we allow 3 minutes of computation time per 100 customers. We observed in pre-tests that larger
  time limits yield only marginal improvements in solutions quality, whereas most solutions are
  found in significant less time. When we double the time limit, we observe an average improvement
  by 0.05% on the U-instances." Algorithm 3, line 3: "while time limit not reached do". This is
  the clearest published example of the criterion you are after: budget fixed where doubling it
  buys 0.05 %.
- Arnold, Gendreau, Sörensen, "Efficiently solving very large-scale routing problems", C&OR
  107:32–42, 2019; author PDF
  https://repository.uantwerpen.be/docman/irua/e11288/160227_2020_01_01.pdf . Quote: "In the
  'short' runtime setup we allow the same computational time as that used by the GVNS, given that
  our machine is about 4 times faster. In the 'long' runtime setup we allow 5 minutes per 1,000
  customers." Also: "For most instances with up to 1000 customers, it does not require more than a
  few minutes to compute a solution with a gap of 1% and less to the best known solutions ... gaps
  between 0.5% and 1% ... are perfectly acceptable in many real applications."

**(d) Your solver — OR-Tools.** The routing search parameters expose only `solution_limit`,
`time_limit` and `lns_time_limit` as search limits (routing options page,
https://developers.google.com/optimization/routing/routing_options; proto
https://github.com/google/or-tools/blob/stable/ortools/constraint_solver/routing_parameters.proto,
which also has `secondary_ls_time_limit_ratio` for a clean-up phase). There is no
"iterations without improvement" or "ε-improvement" stop in the routing API; the docs' examples
use `time_limit.seconds = 30`. I could not locate, on the pages I fetched, the sentence stating
that GLS never terminates by itself — the claim is consistent with the parameter list but I am
not quoting it.

**"Stop when improvement over Δt is below ε".** I did not find this rule stated as the primary
termination criterion in any of the three VRP papers above; they use (a)–(c). It exists in the
anytime literature as the myopic value-of-computation rule (§2, Theorem 5), where `ε = c·Δt`
is derived from the cost of time rather than picked. If you want an ε rule, that is its
justification and its parameter.

---

## 4. Run-time distributions and time-to-target plots

Primary sources:
- Hoos & Stützle, "Evaluating Las Vegas Algorithms — Pitfalls and Remedies", UAI 1998
  (arXiv https://arxiv.org/abs/1301.7383).
- Hoos & Stützle, *Stochastic Local Search: Foundations and Applications*, Morgan Kaufmann 2004,
  Chapter 4 (author slides: https://www.cs.ubc.ca/~hoos/SLS-Book/Slides/Chapter-4/ch4-slides.pdf;
  Stützle's lecture version https://iridia.ulb.ac.be/~stuetzle/Teaching/HO/Slides/Lecture8b.pdf).
- Aiex, Resende, Ribeiro, "TTT plots: a perl program to create time-to-target plots",
  Optimization Letters 1(4):355–366, 2007 (author PDF http://mauricio.resende.info/doc/tttplots.pdf;
  page http://mauricio.resende.info/tttplots/). Earlier: Aiex, Resende, Ribeiro, "Probability
  distribution of solution time in GRASP: An experimental investigation", J. Heuristics 8:343–373,
  2002.

**Application scenarios (UAI 1998 §2)** — this is the frame for "which criterion":
"Type 1: There are no time limits ... Type 2: There is a time limit t_max for finding a solution
... Type 3: The usefulness or utility of a solution depends on the time needed to find it.
Formally ... a utility function U: R → [0,1], where U(t) is the utility of finding a solution
after time t. As can be easily seen, types 1 and 2 are special cases of type 3." And: "An adequate
criterion for a type 2 situation with time-limit t_max is P(RT ≤ t_max), the probability of finding
a solution within the given time-limit. For type 3 ... the run-time behavior can only be adequately
characterized by the run-time distribution function rtd(t) = P(RT ≤ t)." Note that Type 3 is the
anytime utility of §2 restated on the time axis.

**Definitions (SLS book ch. 4, author slides).** For an optimisation algorithm A' on instance π':
- Success probability `P_s(RT ≤ t, SQ ≤ q)`; the RTD is "the probability distribution of the
  bivariate random variable (RT, SQ)", `rtd(t, q) = P_s(RT ≤ t, SQ ≤ q)`.
- **Qualified RTD** for quality `q'`: `qrtd_q'(t) := rtd(t, q') = P_s(RT ≤ t, SQ ≤ q')` — "QRTDs
  characterise the ability of a given SLS algorithm ... to solve the associated decision
  problems." "Solution qualities q are often expressed as relative solution qualities q/q* − 1,
  where q* = optimal solution quality for given problem instance."
- **Solution-quality distribution** for run-time `t'`: `sqd_t'(q) := rtd(t', q)` — "characterise
  the solution qualities achieved ... within a given run-time bound (useful for type 2 application
  scenarios)".
- **SQT curves**: "time-dependent SQD statistics (solution quality over time (SQT) curves) ...
  widely used to illustrate the trade-off between run-time and solution quality ... SQT curves
  based on SQD quantiles (such as median solution quality) correspond to contour lines of the
  two-dimensional bivariate RTD graph." Warning: "Important aspects of an algorithm's run-time
  behaviour may be easily missed when basing an analysis solely on a single SQT curve."
- Measurement protocol: "Perform k independent runs of A' on π' with cutoff time t'. During each
  run, whenever the incumbent solution is improved, record the quality of the improved incumbent
  solution and the time at which the improvement was achieved in a solution quality trace. Let
  sq(t', j) denote the best solution quality encountered in run j up to time t'. The cumulative
  empirical RTD ... P̂_s(RT ≤ t', SQ ≤ q') := #{j | sq(t', j) ≤ q'}/k." "For most purposes, k should
  be at least 50–100." Your `(time_ms, best_objective)` sequence is exactly this "solution quality
  trace".

**Time-to-target plots (Aiex, Resende, Ribeiro).** "For a given problem instance, we measure the
CPU time to find an objective function value at least as good as a given target value. The
heuristic is run n times on the fixed instance and using the given target solution ... the running
times are sorted in increasing order. We associate with the i-th sorted running time t(i) a
probability p(i) = (i − 1/2)/n, and plot the points z(i) = [t(i), p(i)]." Model: "the random
variable time to target solution value is exponentially distributed or fits a two-parameter shifted
exponential distribution, i.e. the probability of not having found a given target solution value in
t time units is given by P(t) = e^{−(t−μ)/λ}". They "have observed in practice that using n = 200"
runs gives good approximations. A TTT plot *is* a QRTD; the shifted-exponential fit is what lets
you extrapolate quantiles beyond the sampled runs.

**Why a quantile of the time-to-target distribution is the standard budget.** UAI 1998 §3 makes
the point directly: "Consider the design of an algorithm for a type 2 application scenario and the
specific question of estimating the cutoff time t_max for solving a given problem instance with a
probability p. If only the mean run-time E(RT) is known, the best estimate we can obtain is given
by the Markov inequality ... But assuming that the run-time is exponentially distributed, we get an
estimate of 460 sec [vs 1100 or 10000]." I.e. `t_max = p-quantile of the TTT distribution`; the
mean is "in the best case unprecise, in the worst case ... erroneous".

**Mapping your current criterion onto this vocabulary.**
- "within 0.5 % of the 60 s result": relative target quality `q' = 0.005` with reference
  `q* := f(60 s)` instead of the optimum/BKS. Say this explicitly — Hoos & Stützle's `q*` is the
  optimum or best-known value, and the 60 s value is a per-run, noisy proxy for it.
- "smallest budget ... at the median": `B = min{ t : P̂(TTT_{0.5 %} ≤ t) ≥ 0.5 }`, the empirical
  median of the time-to-target for `q' = 0.5 %`.
- "5 % at the third quartile": `P̂(TTT_{5 %} ≤ B) ≥ 0.75`.
- The population: Hoos & Stützle define the RTD *per instance over independent runs* (seeds).
  Taking the quantile *across instances* with one run each mixes instance hardness with seed
  noise; they warn against "averaging over inhomogeneous test sets" (UAI 1998 §6). If you keep
  one run per instance, state that your distribution is over the instance population and that it
  answers "for what fraction of instances does budget B reach target q'", which is a legitimate
  type-2 question, but different from a per-instance QRTD.

So: the criterion is not ad hoc in *form* — it is a two-constraint QRTD quantile budget. What is
ad hoc is the choice of `(0.5 %, 50 %)` and `(5 %, 75 %)`; those are utility statements in
disguise, which is why §2 recommends stating `c` instead.

---

## How to apply to a (time, objective) sequence

Inputs per instance: events `E = [(t_0, f_0), (t_1, f_1), …, (t_n, f_n)]`, `t` in ms, `f`
non-increasing (best-so-far), `t_0` = first feasible solution, `t_n ≤ T = 60 000`.
Reference `f_ref = f_n` (or a BKS if you have one). Relative gap `g_i = f_i / f_ref − 1`.

### Recommended: contract-optimal time for an explicit cost of time `c` (§2)

```
function optimal_time(E, f_ref, c_per_s):
    # c_per_s: cost of one second of waiting, in units of relative gap (e.g. 0.001 = 0.1 %/s)
    c = c_per_s / 1000.0                       # per ms
    best_u = -inf; t_star = None
    for (t_i, f_i) in E:                       # exact: the curve is constant between events,
        g_i = f_i / f_ref - 1                  # so the argmax is attained at an event time
        u = -g_i - c * t_i
        if u > best_u + 1e-12:                 # strict '>' keeps the EARLIEST maximiser
            best_u, t_star = u, t_i
    return t_star
```

Equivalent statement (useful for reporting): `t*` is the vertex of the lower convex hull of `E`
at which the hull slope crosses `−c`; the improvement rate after `t*` is below `c` forever
(diminishing returns). Report `t*` for `c ∈ {impatient, normal, patient}`; if the three values
differ by more than an order of magnitude, the curve has no knee — say "flat trade-off".

### Population budget with QRTD vocabulary (§4) — what you already do, renamed

```
function time_to_target(E, f_ref, q):         # first time the gap is <= q
    for (t_i, f_i) in E:
        if f_i / f_ref - 1 <= q: return t_i
    return +inf                                # target not reached within T

TTT_05 = [time_to_target(E_k, f_ref_k, 0.005) for k in instances]
TTT_5  = [time_to_target(E_k, f_ref_k, 0.05)  for k in instances]
B = min over t of { t : ecdf(TTT_05)(t) >= 0.50 and ecdf(TTT_5)(t) >= 0.75 }
```

Add: the shifted-exponential fit of Aiex et al. (`P(t) = e^{−(t−μ)/λ}`) if you want a
parametric quantile, and — if you can afford it — several seeds per instance so that the
distribution is a genuine QRTD (Hoos & Stützle recommend k ≥ 50–100 runs).

### If you must report a geometric knee (for comparison only)

1. Resample the best-so-far curve on a uniform time grid (e.g. 100 ms) — Kneedle's threshold
   assumes uniform spacing; also consider a log-time axis, which removes most of the "long head".
2. Run Kneedle offline with `S = 0`, `curve="convex"`, `direction="decreasing"`; or compute the
   max distance to the chord directly (§1.4). Both are identical to `optimal_time` with
   `c = (g_0 − g_n) / (t_n − t_0)`; print that implied `c` next to the knee so readers see what
   trade-off the knee silently assumes.
3. Run the L-method with iterative refinement (`cutoff = 2·knee`, floor 20 points) as a second
   opinion; if the two disagree by more than the plateau's noise, do not report a knee.

## Source list (all read)

- Satopää, Albrecht, Irwin, Raghavan 2011 — https://raghavan.usc.edu/papers/kneedle-simplex11.pdf
- kneed API/docs — https://kneed.readthedocs.io/en/latest/api/ ,
  https://kneed.readthedocs.io/en/latest/user-guide/multi-knee/ , issue #52
  https://github.com/arvkevi/kneed/issues/52
- Salvador & Chan 2004 — https://cs.fit.edu/~pkc/papers/ictai04salvador.pdf
- Antunes, Gomes, Aguiar 2018 (DFDT) — doi:10.1109/BigDataService.2018.00042 (abstract only;
  full text not open)
- Antunes et al. 2025 (Kneeliverse) — doi:10.1016/j.softx.2025.102161 ,
  https://yifei-liu.github.io/files/Kneeliverse-SoftwareX-2025.pdf
- Zilberstein 1996 — http://rbr.cs.umass.edu/papers/Zaimag96.pdf
- Boddy & Dean 1994 — https://cs.brown.edu/people/tdean/publications/archive/BoddyandDeanAIJ-94.pdf
- Dean & Boddy 1988 — https://aaaipress.org/Papers/AAAI/1988/AAAI88-009.pdf (abstract)
- Nielsen 1993 — https://www.nngroup.com/articles/response-times-3-important-limits/
- Vidal 2022 — https://arxiv.org/abs/2012.10384 ; https://github.com/vidalt/HGS-CVRP
- Christiaens & Vanden Berghe 2018/2020 —
  https://lirias.kuleuven.be/retrieve/29d92f01-b92c-43f8-9d02-e3cb9210f33f/
- Arnold & Sörensen 2019 —
  https://repository.uantwerpen.be/docman/irua/4b36e9/158505_2019_11_01.pdf
- Arnold, Gendreau, Sörensen 2019 —
  https://repository.uantwerpen.be/docman/irua/e11288/160227_2020_01_01.pdf
- OR-Tools routing options — https://developers.google.com/optimization/routing/routing_options ;
  routing_parameters.proto
- Hoos & Stützle 1998 — https://arxiv.org/abs/1301.7383
- Hoos & Stützle 2004 ch. 4 slides — https://www.cs.ubc.ca/~hoos/SLS-Book/Slides/Chapter-4/ch4-slides.pdf
- Aiex, Resende, Ribeiro 2007 — http://mauricio.resende.info/doc/tttplots.pdf ,
  http://mauricio.resende.info/tttplots/
