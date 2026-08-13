# Inventaire des fonctionnalités

Une ligne par capacité offerte par le dépôt, avec son point d'entrée et ses
tests. À tenir à jour à chaque fonctionnalité terminée.

## Résolution

| Fonctionnalité | Point d'entrée | Tests |
|---|---|---|
| Résolution CVRPTW avec capacités, fenêtres horaires et équilibrage | `optimizer.solver.solve_vrp` | `tests/unit/test_solver_compat.py` |
| Rechargement en cours de tournée (nœuds de dépôt dupliqués) | `optimizer.solver.setup_data_extensions` | `tests/integration/test_scenario.py` |
| Transfert de colis entre véhicules via un hub (nœuds et véhicules fictifs) | `optimizer.solver.add_hub_constraints` | `tests/integration/test_scenario.py::TestSolveScenario::test_transferts_en_hub_actives` |
| Arbitrage avec / sans hubs, sur le temps total de livraison | `optimizer.solver.solve_vrp_with_optimal_hubs` | manuel (`python -m optimizer.main`) |
| Contournement de la régression OR-Tools 9.15 sur `SetAllowedVehiclesForIndex` | `optimizer.solver.set_allowed_vehicles` | `tests/unit/test_solver_compat.py` |
| Budgets de recherche bornés par appel (temps total, LNS, parallélisme) | `optimizer.solver.configure_search_parameters` | `tests/integration/test_scenario.py` |

## Données

| Fonctionnalité | Point d'entrée | Tests |
|---|---|---|
| Génération d'un jeu de données synthétique reproductible (graine fixée) | `optimizer.create_toy_data.create_toy_data` | `tests/integration/test_scenario.py` |
| Chargement JSON + NumPy et mise en forme | `optimizer.data_loader.load_data` | `tests/integration/test_scenario.py` |
| Distance de référence sans hubs | `optimizer.preprocessor.preprocess` | manuel |

## Restitution

| Fonctionnalité | Point d'entrée | Tests |
|---|---|---|
| Extraction des routes, charges et indicateurs | `optimizer.postprocessor.get_results` | `tests/unit/test_postprocessor.py` |
| Indicateur de déséquilibre de charge | `optimizer.postprocessor.compute_load_imbalance` | `tests/unit/test_postprocessor.py` |
| Lecture d'une solution : attentes, charges par étape, sérialisation JSON | `optimizer.trace` | `tests/unit/test_trace.py` |
| Carte animée Leaflet avec curseur temporel | `optimizer.print_solution.create_visualization` | manuel |
| Tracé des tournées sur le réseau routier réel (OSRM, cache disque, repli) | `optimizer.road_routing.build_road_legs` | `tests/integration/test_scenario.py` |
| Capture de la démonstration en images et vidéo | `tools/capture_demo.py` | manuel |
| Analyses comparatives paramétriques | `optimizer.stats` | manuel |

## API

| Fonctionnalité | Point d'entrée | Tests |
|---|---|---|
| Résolution d'un scénario à la demande, appelable depuis un service web | `optimizer.scenario.solve_scenario` | `tests/integration/test_scenario.py` |
| Validation et bornage des paramètres côté serveur | `optimizer.scenario.SCENARIO_LIMITS` | `tests/integration/test_scenario.py::TestValidationDesParametres` |
| Mise en forme de la tournée pour un consommateur web (contrat JSON) | `optimizer.tour_format.build_tour` | `tests/unit/test_tour_format.py` |
