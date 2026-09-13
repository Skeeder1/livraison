# Can the search time an instance needs be predicted from its parameters? — literature check

Primary sources only. Every quote below was read from the publisher page, arXiv/HAL full text or the authors' own PDF; the URL is given next to each quote. Items marked **[not verified]** could not be read in full (paywall or anti-bot block) and are reported only from their abstract.

## Verdict (five sentences)

1. Yes: predicting run time from instance features without running the instance is an established discipline ("empirical hardness / performance models"), and the field's reference paper explicitly does it for a *local-search, anytime* solver (LKH) by defining run time as time-to-reach-a-target-quality — exactly what this demo's "convergence time" is (Hutter et al. 2014, §6.1: "For the latter, we computed runtimes as the time required to find an optimal solution.").
2. The recipe that works is: predict **log** run time, use a **tree ensemble (random forest)** rather than a linear fit when the instance set is heterogeneous (hubs vs. no hubs is exactly the kind of regime split that breaks linear/ridge models on "BIGMIX"-like data), and validate with **k-fold cross-validation on unseen instances**; a few hundred measured points already give correlation ≥ 0.9 in that paper, so 7 392 configurations is far above the minimum.
3. The literature also says what the current lookup gets wrong: run time of a stochastic metaheuristic to a target is a *random variable* (shifted-exponential per instance/target pair — Aiex/Resende/Ribeiro, Hoos/Stützle), so the thing to predict is a quantile (median or 80th percentile) from several seeds, not a single measured number; and predictions of variable-size data are markedly worse than fixed-size (Leyton-Brown et al. 2009: RMSE 1.14 vs 0.31–0.51 log10 units for linear models), so size must be an explicit feature and the model must not be trusted outside the measured grid.
4. Transfers/hubs are known to be qualitatively more expensive: with transfers, route feasibility can no longer be checked route-by-route ("an interdependence problem"), millions of feasibility checks are executed per run, and the only same-algorithm, same-iteration-budget comparison found (Masson, Lehuédé, Péton, DARPT research report, Table 6) shows a **6× to 20× increase in CPU time** when 2–33 transfer points are added to the same instances — consistent with the 0.7 s → 17 s jump observed in this demo, and a strong argument that hub count must be a first-class feature (or a separate model), not a correction factor.
5. So the defensible design is a fitted model (RF on log-time with features: customers, hubs, vehicles, demand/(vehicles×capacity), TW flag, customers/vehicles), reported as a quantile with an uncertainty band, validated by grouped cross-validation over held-out parameter combinations — and, where the model's own variance is high (hubs, small n), a short *probing run* (the "landmarking" / probing-feature idea of Smith-Miles, Hutter et al., Kotthoff et al.) is the literature's answer, i.e. "measure a little, then predict", not "measure everything".

---

## Q1. Empirical hardness models / algorithm runtime prediction

### Hutter, Xu, Hoos, Leyton-Brown, "Algorithm runtime prediction: Methods & evaluation", Artificial Intelligence 206 (2014) 79–111
- Publisher: https://www.sciencedirect.com/science/article/pii/S0004370213001082 — open preprint: https://arxiv.org/abs/1211.0906 (PDF https://arxiv.org/pdf/1211.0906, read in full).

**What they predict — and yes, it includes time-to-quality for a local-search solver.**
> "For TSP, we used three instance distributions (detailed in Appendix A.3): random uniform Euclidean instances (RUE), random clustered Euclidean instances (RCE), and TSPLIB, a heterogeneous set of prominent TSP instances. On these instance sets, we ran the state-of-the-art systematic and local search algorithms, Concorde [2] and LK-H [40]. For the latter, we computed runtimes as the time required to find an optimal solution." (§6.1)

> "Similar regression models can also be used to predict objectives other than runtime; examples include an algorithm's success probability [45, 97], the solution quality an optimization algorithm achieves in a fixed time [96, 20, 56], approximation ratio of greedy local search [82], or the SAT competition scoring function [119]. We reflect this broadened scope by using the term EPMs [empirical performance models]" (§1)

> "In principle, EPMs can predict any type of performance measure that can be evaluated in single algorithm runs, such as runtime, solution quality, memory usage, energy consumption, or communication overhead." (§3)

So the answer to "do they predict time-to-quality for anytime metaheuristics or only time-to-completion?" is: **both**. LK-H is a stochastic local search; its "runtime" in this paper is time-to-target (target = optimal tour length known from Concorde). The same group later did this at scale for LKH and EAX (Kotthoff, Kerschke, Hoos, Trautmann, LION 2015, below).

**Target transformation.**
> "In this article, we focus on runtime as a performance measure and use a log-transformation, thus effectively predicting log runtime. […] In our experience, we have found this transformation to be very important due to the large variation in runtimes for hard combinatorial problems." (§3.1)

**Features used for TSP** (Figure 3, 64 features): problem size; distance-matrix statistics; node-distribution / clustering (DBSCAN cluster count, outliers, cluster-size variation); centroid, radius, area; nearest-neighbour distance statistics; minimum-spanning-tree statistics; **local-search probing** ("based on 20 short runs (1000 steps each) of LK", tour length, improvement per step, steps to local minimum, distance between local minima); **branch-and-cut probing** ("based on 2-second runs of Concorde"); ruggedness/autocorrelation.

**Models compared and accuracy** (Table 2, 10-fold CV RMSE of log10 runtime; RR = ridge, SP = SPORE-FoBa, NN = neural net, PP = projected-process GP, RT = regression tree, RF = random forest):
| benchmark | RR | SP | NN | PP | RT | RF |
|---|---|---|---|---|---|---|
| LK-H-RUE | 0.61 | 0.63 | 0.64 | 0.61 | 0.89 | 0.67 |
| LK-H-RCE | 0.71 | 0.72 | 0.75 | 0.71 | 1.02 | 0.76 |
| LK-H-TSPLIB | 9.55 | 1.11 | 1.77 | 1.30 | 1.21 | 1.06 |
| Concorde-RUE | 0.41 | 0.43 | 0.43 | 0.42 | 0.59 | 0.45 |
| Concorde-TSPLIB | 120.6 | 0.69 | 0.99 | 0.87 | 0.64 | 0.52 |
| Minisat-COMPETITION | 1.01 | 1.25 | 0.62 | 0.92 | 0.68 | 0.47 |

> "quantitatively, the RMSE for predicting log10 runtime was low – e.g., 0.47 for random forests, which means an average misprediction of a factor of 10^0.47 < 3)." (§6.3)

> "In our experiments, random forests were the overall winner among the different methods, yielding the best predictions in terms of all our quantitative measures. For SAT, random forests were always the best method, and for MIP they yielded the best performance for the most heterogeneous instance set, BIGMIX […]. We attribute the strong performance of random forests on highly heterogeneous data sets to the fact that, as a tree-based approach, they can model very different parts of the data separately; in contrast, the other methods allow the fit in a given part of the space to be influenced more by data in distant parts of the space. Indeed, the ridge regression variants made extremely bad predictions for some outlying points on BIGMIX." (§6.3)

Note the two heterogeneous TSP rows (TSPLIB): ridge regression explodes (RMSE 9.55 / 120.6) while RF stays at ~1.0 / 0.5. The demo's corpus is heterogeneous in the same sense (hubs on/off, TW on/off).

**How much data.**
> "Overall, random forests performed best across training set sizes. Both versions of ridge regression (SP and RR) performed poorly for small training sets." (§6.6, learning curves in Fig. 5)

> "Overall, we note that most models already performed remarkably well (yielding correlation coefficients of 0.9 and higher) based on a few hundred training data points. This confirmed the practicality of our methods: on a single machine, it takes at most 12.5 hours to execute 150 algorithm runs with a cutoff time of 300 seconds. Thus, even users without access to a cluster can expect to be able to execute sufficiently many algorithm runs overnight to build a decent empirical performance model for their algorithm and instance distribution" (§8.3)

**Validation protocol.** 10-fold cross-validation on unseen instances, RMSE + correlation coefficient + log-likelihood, Wilcoxon signed-rank test across folds (§6.2). Capped runs (time-outs) are right-censored; §9 shows survival-analysis treatment in RF improves predictions — relevant if some demo configurations never "converge" within the cap.

### Leyton-Brown, Nudelman, Shoham, "Empirical hardness models: Methodology and a case study on combinatorial auctions", J. ACM 56(4), 2009
- Publisher: https://dl.acm.org/doi/10.1145/1538902.1538906 — authors' PDF: https://www.cs.ubc.ca/~kevinlb/papers/EmpiricalHardness.pdf (read in full).

**Scope: deterministic complete solver (CPLEX on WDP), but the methodology is stated to extend to incomplete/anytime algorithms via time-to-target.**
> "Although this paper discusses only deterministic algorithms, more recent work has also demonstrated that our methodology may be used to build empirical hardness models for both randomized tree search algorithms and stochastic local search algorithms [Nudelman et al. 2004b; Hutter et al. 2006; Xu et al. 2007; Xu et al. 2008]. […] Incomplete algorithms are trickier, because the notion of running time is not always well defined when the algorithm can lack a termination condition. […] As discussed in the introduction, optimization problems can be converted to decision problems by asking whether a solution exists with an objective function value of at least some amount k. Leveraging this idea, models for incomplete optimization algorithms can predict the amount of time the algorithm will take to exceed an objective function value of k. Another way of working with incomplete algorithms is to predict solution quality directly rather than predicting the amount of time the algorithm will run." (§2.1)

**Model, target, split.** Linear then quadratic (pairwise-product) regression on log10 runtime; data split "training set, a validation set, and a test set, according to the ratio 70:15:15" (§3); ~4 300–5 000 instances per fixed-size data set (§3: "We collected a total of 4987 instances, or roughly 500 instances per distribution").

**Accuracy (test data, log10 units).** Table I (linear): RMSE 0.51 / 0.46 / 0.37 for the three fixed-size sets, adj-R² 0.89–0.91; **Variable Size: RMSE 1.14, adj-R² 0.71**. Table II (quadratic): RMSE 0.31 / 0.35 / 0.30, adj-R² 0.95–0.97; Variable Size: RMSE 0.54, adj-R² 0.95.
> "Overall, runtimes for 96% of the data instances in our fixed-size test set were predicted to the correct order of magnitude (i.e., with an absolute error of less than 1.0), even without knowing the distribution from which each instance was drawn. On the variable-size data, 64% of instances were predicted within the correct order of magnitude." (§3, linear models)
> "quadratic models would classify 98% of test instances in the fixed-size data set and 93% of instances in the variable-sized data set to within the correct order of magnitude—a dramatic improvement over linear models." (§3.4)

Lesson for a 10–60-customer demo: size variation is the hardest part of the prediction; a purely linear-in-features model on variable-size data was off by more than an order of magnitude for a third of the instances, and interaction terms (size × other features) fixed most of it.

### Kotthoff, Kerschke, Hoos, Trautmann, "Improving the State of the Art in Inexact TSP Solving using Per-Instance Algorithm Selection", LION 9 (2015)
- PDF: http://www.cs.uwyo.edu/~larsko/papers/kotthoff_improving_2015.pdf
Feature-based runtime models for two *inexact* (anytime) TSP solvers, LKH and EAX; performance = time to find the optimum, PAR10-penalised, **median of 10 seeds**:
> "We ran each solver 10 times on an instance with different random seeds and took the median of the results."
> "The overall best model is random forest regression and achieves better performance than the single best solver on average."
They also introduce cheap **probing features from the first seconds of an EAX run** and note that, if the probed solver is the one then run, "the features are obtained at no additional cost, by simply continuing the probing run." This is the "measure a little, then predict" pattern.

---

## Q2. Instance features that predict VRP hardness for metaheuristics

### Rasku, Kärkkäinen, Musliu, "Feature Extractors for Describing Vehicle Routing Problem Instances", SCOR 2016 (OASIcs 50)
- https://doi.org/10.4230/OASIcs.SCOR.2016.7 (open access, read).
Purpose statement:
> "Heuristic, metaheuristic, and hybrid algorithms that are typically used to solve these problems are sensitive to this variation and can exhibit erratic performance when applied on new, previously unseen instances."
Feature families (Table 1): (a) node distribution incl. distance-matrix statistics, DBSCAN cluster count/size/outliers, silhouette, minimum bottleneck cost; (b) MST features incl. "MST depth from the depot"; (c) local-search probing (solution quality after construction and LS, improvement per step, steps to local minimum, autocorrelation length); (d) branch-and-cut probing; and VRP-specific demand/capacity features:
> "In describing the demands and capacity, we followed [22]. As an extension to the VRP specific features, we propose measuring the distance between the depot and the centroid of the client points. Also, describing the shape of the distribution of distances from clients to the depot is included in our feature set. Furthermore, the size of the problem (number of clients) is included here."
Result: 386 features, validated by clustering 168 CVRPLIB instances and by feature-assisted SMAC configuration; the paper is a feature catalogue, not a ranking of which features matter most.

### Rasku, Musliu, Kärkkäinen, "Feature and Algorithm Selection for Capacitated Vehicle Routing Problems", ESANN 2019
- https://www.esann.org/sites/default/files/proceedings/legacy/es2019-110.pdf
433 features, 454 CVRPLIB instances, algorithm selection among classical heuristics:
> "Unsurprisingly, the final scoring reveals that the local search probing (LSP) features are highly relevant in the heuristic selection task, but also features related to exact solving attempt (BCP), constraints (DC), and nearest neighbor digraph (NN) are important."
> "Regarding the validity of our results, please note that we did not use a separate training set for the feature selection or discretization due to the limited number of samples. We acknowledge that this may induce some positive bias to the selection accuracy. In an extended study it would be advisable to use nested cross-validation"
(The "DC" group is the demand/capacity constraint tightness family.)

### Uchoa, Pecin, Pessoa, Poggi, Vidal, Subramanian, "New benchmark instances for the Capacitated Vehicle Routing Problem", EJOR 257(3) 2017
- Publisher: https://www.sciencedirect.com/science/article/abs/pii/S0377221716306270 (paywalled); preprint https://optimization-online.org/wp-content/uploads/2014/10/4597.pdf (read); authors' ROUTE 2014 slides https://www.route2014.transport.dtu.dk/-/media/bcb1f19570e641f6b62577a510ba2c0c.pdf.
The generator varies exactly the demo's kind of parameters — "number of customers, depot positioning, customer positioning, demand distribution, and average route size" — and the authors' findings on which ones matter:
> "The previous experience of the authors with CVRP algorithms indicated that the value n/Kmin, the average route size (assuming solutions with the minimum possible number of routes) has a large impact on the performance of current exact methods. The impact of this attribute on heuristic methods is not so pronounced, but is still quite significant. We can not make a general statement that instances with shorter routes are easier than instances with longer routes or the opposite. What happens is that some methods are more suited for short routes and other methods for longer routes." (preprint §3.1.4)
> "UHGS produces solutions of generally higher quality than ILS for a comparable amount of CPU time, except for some instances containing few customers per route. […] On the other hand, for problems with a large number of customers per route, the hybrid ILS exhibits a slower convergence and generally leads to solutions of lower quality." (preprint §4.1)
From the authors' slides (ROUTE 2014): "What makes an instance X harder to BCP? Besides the obvious value of n: Large n/K: a very significant effect; The absolute value of Q: significant effect; Surprisingly, depot and customer positioning does not have a clear influence" and for the metaheuristic UHGS: "Small n/K good for BCP, bad for UHGS"; "Effect of demand type on UHGS: Box-plots indicate significant influence of some demand types"; "Effect of depot position on UHGS: Box-plots do not indicate significant influence".
**[not verified]**: the EJOR version's §4 statistical analysis on the 600-instance extended benchmark could not be read (paywall).

Take-away: after n, the strongest hardness driver is **customers per route (n/K), i.e. capacity tightness**, then demand distribution; depot/customer positioning matters less. For the demo, `customers/vehicles` and `total demand/(vehicles×capacity)` are therefore the features to add next to `customers`.

### Gouvêa, Paulos, Uchoa, Nascimento, "Instance space analysis of the capacitated vehicle routing problem", IJCNN 2025
- https://arxiv.org/html/2507.10397v1 (read), DOI https://doi.org/10.1109/ijcnn64981.2025.11228608
ISA over the DIMACS-12 CVRP challenge data; performance metric is the **primal integral** (quality × time, i.e. an anytime measure); 23 features retained; among the retained features are "VRP4", "ND5 (mean)" (cluster count), MST and nearest-neighbour statistics and LK probing features. Honest limitation stated by the authors: "While we also addressed the challenge of understanding which features determine an instance's position in the projected space […], this proved to be a complex task that warrants further investigation." Only "a moderate correlation … between the number of customers and axis Z₁ (r=-0.6)" is reported.

### Notice, Soleimani, Pavlidis, Kheiri, Muñoz, "Instance Space Analysis of the CVRP with Mixture Discriminant Analysis", GECCO 2025
- https://doi.org/10.1145/3712256.3726405
> "Our analysis highlights that the performance comparison between the two CVRP metaheuristics is nuanced and the best algorithm depends on the time budget, as well as certain key characteristics of the problem instance."

### Barros-Everett, Montero, Rojas-Morales, "Parameter Prediction for Metaheuristic Algorithms Solving Routing Problem Instances Using Machine Learning", Applied Sciences 15(6) 2025
- https://doi.org/10.3390/app15062946 (open access)
CVRPTW with HGS; features = spatial, clustering and four time-window features (overlap ratios, normalised window length, window-length heterogeneity). SHAP ranking:
> "We determine that client clustering, client number, and vehicle capacity are the most relevant features when predicting HGS' optimal parametrization. In addition, features related to the time windows were considered within the top ten most relevant for four of five parameters of HGS."
> "Considering that time-window constraints greatly reduce the solution space and complicate the search for feasible and good-quality solutions, we expect instances with narrow time-windows to be more computationally expensive and produce more unfeasible solutions."
(Prediction target is parameters, not run time, but the feature ranking is the point: number of clients, capacity ratio, clustering, then TW tightness.)

### Smith-Miles & Lopes, "Measuring instance difficulty for combinatorial optimization problems", C&OR 39 (2012)
- https://www.cs.ubc.ca/labs/algorithms/EARG/stack/2012_ComputersAndOperationResearch_SmithMiles_MeasuringInstanceDifficulty.pdf
On the two kinds of features:
> "As a preliminary step for automated algorithm selection though, we need to ensure that the set of features used to characterize problem instances are quickly measurable."
> "The final set of problem-independent features […] are based on the concept of landmarking [101]. Here, metrics gathered from the performance of simple and quick algorithms (such as gradient descent) are used to characterize the relative difficulty of the problem instances, as a proxy measure and as an alternative to a computationally expensive feature calculation or exploration of the entire landscape."
> "If our goal is to obtain a good set of features within a time constrained setting, as required for automated algorithm selection, then it makes sense to combine landmarking with problem specific features constructed with knowledge of what makes problem instances challenging."

**No paper was found that ranks "presence of transfers/cross-docking" as an instance feature in a hardness model**; transfer cost is documented only in the transfer-specific literature (Q3).

---

## Q3. Transfers / cross-docking: what do the papers say about computational cost?

### Masson, Lehuédé, Péton, "An Adaptive Large Neighborhood Search for the Pickup and Delivery Problem with Transfers", Transportation Science 47(3) 2013
- https://pubsonline.informs.org/doi/10.1287/trsc.1120.0432 — **[full text not verified: paywalled]**. Abstract:
> "Solving the PDPT leads to new modeling and algorithmic difficulties. We propose new heuristics capable of efficiently inserting requests through transfer points. These heuristics are embedded into an adaptive large neighborhood search. […] On these real-life instances we show that the introduction of transfer points can bring significant improvements (up to 9%) to the value of the objective function."

### Masson, Lehuédé, Péton, "Efficient feasibility testing for request insertion in the pickup and delivery problem with transfers", Operations Research Letters 41(3) 2013
- https://www.sciencedirect.com/science/article/abs/pii/S0167637713000084 (abstract + excerpts read)
> "In this problem, routes are strongly interdependent due to request transfers. Then it is critical to efficiently check if inserting a request into a partial solution is feasible or not. In this article, we present a method to perform this check in constant time."
> "The constant time complexity requires some preprocessing each time a current solution of the problem is actually updated. This preprocessing has a quadratic complexity in the number of vertices of the precedence graph, which is efficient provided that the number of actual updates is substantially smaller"

### Masson, Lehuédé, Péton, "The Dial-A-Ride Problem with Transfers", research report 12/7/AUTO (Oct 2012), published in Computers & OR 41 (2014) 12–23
- Open full text: https://hal.science/hal-00818800/document (read in full); journal DOI 10.1016/j.cor.2013.07.020.
This is the one primary source found that gives **same-algorithm, same-iteration-budget CPU time with vs. without transfers**.

Why transfers cost:
> "Concerning the DARP, Cordeau and Laporte [7] proposed an algorithm to determine the feasibility of a route in O(n²), where n is the number of vertices in the route. However, in the DARPT, the routes are connected through transfer points. The need for synchronization at transfer points leads to an interdependence problem [32], so that checking the feasibility of the routes independently of each other is no longer possible." (§5)
> "Millions of feasibility checks are performed during the execution of the ALNS so this check has to be as efficient as possible." (§5)
> "In the ALNS, BFCT is called to evaluate each insertion position for each unrouted request in routes with transfers. This operation is likely to be performed millions of times during the execution of the algorithm, which may result in a large amount of CPU time spent on this procedure." (§5.2)

How much (Table 6, real-life instances, 5 runs each, 25 000 ALNS iterations or 10 h cap; `|T|` = number of transfer points, CPU in seconds):
| instance | no transfer CPU | with transfers |T| | CPU with transfers | factor |
|---|---|---|---|---|
| Center-81-2 | 1265 | 2 | 15 539 | 12.3× |
| Center-84-2 | 1088 | 2 | 7 725 | 7.1× |
| Center-87-2 | 1572 | 2 | 16 777 | 10.7× |
| Center-109-2 | 1917 | 2 | 23 186 | 12.1× |
| Center-193-5 | 6168 | 5 | time-out (>36 000) | >5.8× |
| School-55-16 | 480 | 16 | 3 044 | 6.3× |
| School-66-13 | 662 | 13 | 4 873 | 7.4× |
| School-84-21 | 1008 | 21 | 12 914 | 12.8× |
| School-84-33 | 991 | 33 | 24 270 | 24.5× |
| School-106-24 | 1475 | 24 | 29 721 | 20.1× |
> "The savings due to transfers range from 2.17% to 8.24% for the Center instances and from 0.97% to 6.50% for the School instances. The counterpart is a large increase in the computing time." (§6.4.2)

And the number of transfer points matters (Table 5, Cordeau–Laporte instances, ALNS with one transfer point at the depot vs. every vertex a potential transfer point): average CPU **1 457 s vs 18 345 s** (12.6×), with time-outs at 10 h for the larger instances:
> "However, solving times tend to be very long. The limit of 10 hours is exceeded – written 't.o.' in the table – when the potential number of transfer points is larger than 140 requests (70 pickup points + 70 delivery points), when all points can be used to perform a transfer." (§6.4.1)

Also the effect of constraint tightness on cost of the feasibility machinery (Table 1): for the tightly constrained "Center" instances only 1.1–2.8 % of evaluated insertions are feasible and the acceleration by necessary/sufficient conditions "can reach 10 or 15", whereas for "School" instances (20–53 % feasible) "the speed-up is almost negligible" (§6.2). I.e. the same code is an order of magnitude slower per iteration when the instance is tight.

### Cortés, Matamala, Contardo, "The pickup and delivery problem with transfers: Formulation and a branch-and-cut solution method", EJOR 200(3) 2010
- https://www.sciencedirect.com/science/article/abs/pii/S0377221709000356 — **[full text not verified: the authors' repository copy at repositorio.uchile.cl is behind an anti-bot challenge]**. Abstract:
> "Solving the PDPT leads to new modeling and algorithmic difficulties" is Masson's phrasing; Cortés et al. write: "Additional variables to keep track of customers along their route are considered. […] Finally, a solution method based on Benders decomposition is addressed. We compare the computational effort of this application with a straight branch and bound strategy; we also provide insights to develop more efficient set partitioning formulations and associated algorithms for solving real-size problems."
From the publisher excerpt: "key issues of this formulation and the presented method that have to be taken into account are, first, the evident symmetries that the problem presents if vehicles are indistinguishable and the depot is the same for all vehicles, and […] the nature of the variables generate a three-[index] formulation, that can become very poor for most of the relaxations." No numeric cost figure could be verified.

### Rais, Alvelos, Carvalho, "New mixed integer-programming model for the pickup-and-delivery problem with transshipment", EJOR 235(3) 2014
- https://ideas.repec.org/a/eee/ejores/v235y2014i3p530-539.html — **[full text not verified]**. Abstract only: "The number of constraints and variables in the models are bounded by polynomial size of the problem. […] Computational work gave promising results and confirms that transshipment in network can indeed enhance optimization."
What later authors say about its scale (Sampaio, Savelsbergh, Veelenturf, van Woensel, "Delivery systems with crowd-sourced drivers: A pickup and delivery problem with transfers", Networks 2020, https://doi.org/10.1002/net.21963, open preprint https://optimization-online.org/wp-content/uploads/2018/11/6956.pdf):
> "Solving instances of the mathematical model presented in Section 3 in a reasonable amount of computation time is only possible for small instances; Rais et al. [24] presents results for instances with 10 and 14 locations (5 and 7 requests, respectively) and where transfers are allowed at every location. This is due, in part, to the symmetry (vehicles are indistinguishable) and the use of big-M constraints, which results in weak linear relaxations."

**Summary for Q3.** No paper frames "transfer count" as a feature in a runtime model, but the transfer-specific literature is unanimous that transfers (i) couple routes so feasibility is no longer route-local, (ii) multiply the number and cost of insertion evaluations, and (iii) in the only apples-to-apples measurement found, cost 6–25× more CPU for the same iteration budget, growing with the number of transfer points. A 0.7 s → 17 s (≈24×) jump at 25 customers with one hub is inside that range.

---

## Q4. Practical verdict for a 5-parameter demo with 7 392 measured configurations

**Is a fitted model defensible?** Yes, and it is the standard approach — provided it follows what the papers above show empirically:

1. **Predict log time, not time** (Hutter et al. §3.1; Leyton-Brown et al. §2.5.2: "we chose to use the (base-10) logarithm"). Errors are then multiplicative, which is what a UI needs ("within a factor of 2").
2. **Use a tree ensemble, or at least include interactions.** The demo's corpus is heterogeneous by construction (hubs 0–3, TW on/off). Hutter et al. show ridge/linear models blowing up on heterogeneous sets (RMSE 9.55 and 120.6 on the two TSPLIB rows) while RF stays ≈0.5–1.0; Leyton-Brown et al. show linear models on variable-size data placing only 64 % of instances in the right order of magnitude vs 93 % with quadratic (interaction) terms. A log-linear regression on {customers, hubs, vehicles, tightness} alone is therefore *not* the recommended form; a random forest / gradient-boosted trees on those features, or a quadratic-expanded regression, is. RF also gives a per-prediction variance for free (Hutter et al. §4.3.2), which is what should drive the UI's "≈" vs "?" display.
3. **Minimum data.** "correlation coefficients of 0.9 and higher based on a few hundred training data points" (Hutter et al. §8.3); Leyton-Brown et al. used ≈500 instances per distribution. 7 392 points over a 5-dimensional grid is comfortably above that, *if* they cover the hub/vehicle/capacity combinations and are not 180 curves × 41 repeats of the same customer counts. The corpus must be checked for coverage of each (hubs, TW) stratum before trusting it there.
4. **Validation.** 10-fold cross-validation on *unseen instances* with RMSE/CC on log time (Hutter et al. §6.2), or a 70/15/15 train/validation/test split (Leyton-Brown et al. §3); and, because the demo's user can pick any grid cell, folds should hold out whole parameter combinations (grouped CV), not random rows, otherwise the score is optimistic — the same warning Rasku et al. 2019 raise about their own results ("this may induce some positive bias […] it would be advisable to use nested cross-validation"). Report "fraction predicted within a factor of 2 / within one order of magnitude", which is the metric these papers quote.
5. **The target is a distribution, not a number.** For local-search metaheuristics "the random variable time to target solution value is exponentially distributed or fits a two-parameter shifted exponential distribution" (Aiex, Resende, Ribeiro, TTT plots, http://mauricio.resende.info/doc/tttplots.pdf, citing Hoos & Stützle's conjecture "that this is true for all local search based methods"). Kotthoff et al. therefore run "10 times on an instance with different random seeds and took the median". The corpus should store several seeds per configuration and the model should predict a chosen quantile (median for the displayed value, ~80th percentile for the budget actually allotted). A single measured curve per configuration is a noisy label; the 180 curves currently used are far too few to characterise the spread.
6. **Censoring.** Configurations that never reached the target within the cap must be kept as right-censored observations, not dropped and not recorded at the cap (Hutter et al. §6.2 and §9).
7. **Do not extrapolate.** Tree models cannot extrapolate beyond the measured grid and linear models extrapolate badly across size (Leyton-Brown's variable-size results). Keep the UI's slider ranges inside the measured hull, or mark predictions outside it as unknown.

**When to measure instead of predict.** The literature's answer is not "measure every instance" but the hybrid: cheap *probing/landmarking* features from a short run of the solver itself (Hutter et al. §5: LK probing "20 short runs (1000 steps each)", Concorde "2-second runs"; Smith-Miles & Lopes on landmarking; Kotthoff et al. 2015: features "extracted from the initial phase of EAX runs" at "no additional cost, by simply continuing the probing run"). For this demo that means: predict from the five parameters for the instant estimate, and, once the user presses solve, run ~0.5–1 s, feed the early-convergence slope (improvement per iteration, iterations to first local optimum) back into the model to refine the remaining budget. Where the RF's predictive variance is high — small n with hubs is the obvious case, given the 6–25× and instance-dependent transfer overhead in Masson et al. — show a range rather than a point.

**Honest limits.** (a) Nothing in the literature gives a transfer-specific hardness *feature* with a known coefficient; the hub effect has to be learned from this demo's own corpus. (b) All the accuracy figures above are for solvers whose "target" is a proven optimum; the demo's "convergence" target must be defined identically for every corpus row (e.g. within x % of the best value seen in a long reference run), otherwise the label itself is inconsistent and no model will fix that. (c) Cortés et al. 2010, Rais et al. 2014 and the Transportation Science version of Masson et al. 2013 could only be read in abstract.

---

## Sources (all consulted 2026-09-13)
- Hutter, Xu, Hoos, Leyton-Brown 2014 — https://arxiv.org/abs/1211.0906 ; https://www.sciencedirect.com/science/article/pii/S0004370213001082
- Leyton-Brown, Nudelman, Shoham 2009 — https://www.cs.ubc.ca/~kevinlb/papers/EmpiricalHardness.pdf ; https://dl.acm.org/doi/10.1145/1538902.1538906
- Kotthoff, Kerschke, Hoos, Trautmann 2015 — http://www.cs.uwyo.edu/~larsko/papers/kotthoff_improving_2015.pdf
- Rasku, Kärkkäinen, Musliu 2016 — https://doi.org/10.4230/OASIcs.SCOR.2016.7
- Rasku, Musliu, Kärkkäinen 2019 — https://www.esann.org/sites/default/files/proceedings/legacy/es2019-110.pdf
- Uchoa et al. 2017 — https://www.sciencedirect.com/science/article/abs/pii/S0377221716306270 ; preprint https://optimization-online.org/wp-content/uploads/2014/10/4597.pdf ; slides https://www.route2014.transport.dtu.dk/-/media/bcb1f19570e641f6b62577a510ba2c0c.pdf
- Gouvêa, Paulos, Uchoa, Nascimento 2025 — https://arxiv.org/html/2507.10397v1
- Notice et al. 2025 — https://doi.org/10.1145/3712256.3726405
- Barros-Everett, Montero, Rojas-Morales 2025 — https://doi.org/10.3390/app15062946
- Smith-Miles & Lopes 2012 — https://www.cs.ubc.ca/labs/algorithms/EARG/stack/2012_ComputersAndOperationResearch_SmithMiles_MeasuringInstanceDifficulty.pdf
- Masson, Lehuédé, Péton 2013 (Transp. Sci.) — https://pubsonline.informs.org/doi/10.1287/trsc.1120.0432
- Masson, Lehuédé, Péton 2013 (ORL) — https://www.sciencedirect.com/science/article/abs/pii/S0167637713000084
- Masson, Lehuédé, Péton 2012/2014 (DARPT) — https://hal.science/hal-00818800/document
- Cortés, Matamala, Contardo 2010 — https://www.sciencedirect.com/science/article/abs/pii/S0377221709000356
- Rais, Alvelos, Carvalho 2014 — https://ideas.repec.org/a/eee/ejores/v235y2014i3p530-539.html
- Sampaio et al. 2020 (on Rais et al.) — https://optimization-online.org/wp-content/uploads/2018/11/6956.pdf
- Aiex, Resende, Ribeiro, TTT plots — http://mauricio.resende.info/doc/tttplots.pdf
