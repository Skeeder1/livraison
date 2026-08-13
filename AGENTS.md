# AGENTS.md — mémoire projet

Notes destinées à un agent qui reprend ce dépôt. Le README couvre l'usage ;
ce fichier retient ce qui n'est pas déductible du code.

## Lancer le projet

```bash
python -m optimizer.main     # résout et génère vrp_visualization.html
pytest                       # 60 tests, environ 50 s
pytest -m "not slow"         # sans la résolution de référence, environ 20 s
python tools/capture_demo.py # regénère la démo animée (images + mp4 + gif)
```

Le point d'entrée est `optimizer/main.py`. Il régénère les données jouet à
chaque exécution (graine fixée par `Config.RANDOM_SEED`).

## Pièges à connaître

**`solve_vrp` mute son argument.** `setup_data_extensions` ajoute les nœuds de
hub et les nœuds fictifs, et porte `num_vehicles` à `num_réels + num_hubs`. La
comparaison avec/sans hubs travaille donc sur deux états de données distincts.
C'est pourquoi `solve_vrp_with_optimal_hubs` retourne `data_used` : toujours
utiliser cette valeur en aval, jamais le `data` d'origine.

**`SetAllowedVehiclesForIndex` est cassé depuis OR-Tools 9.15.** Signature C++
passée à `absl::Span<const int>` sans typemap SWIG côté Python
([or-tools#4982](https://github.com/google/or-tools/issues/4982), jalon 9.16).
Utiliser `set_allowed_vehicles` dans `optimizer/solver.py`. Le test
`test_l_api_native_ortools_est_toujours_cassee` échouera quand le correctif
amont sortira : ce sera le signal pour retirer le contournement.

**Ne pas réimporter `Config` dans une fonction de `data_loader.py`.** Un import
local en fait une variable locale à toute la fonction, y compris avant la ligne
d'import — ce qui provoque un `UnboundLocalError`. L'import est au niveau module.

**La démonstration publiée vient de la résolution SANS hubs.** Dans
`solve_vrp_with_optimal_hubs`, la variante sans hubs met `num_hubs` à 0 mais
**laisse les nœuds de hub dans les données**. Faute de `num_hubs`, aucune
disjonction n'est posée sur eux : ils deviennent des passages **obligatoires**.
C'est ce qui explique un instantané où les deux hubs sont traversés alors que
`activated_hubs` vaut 0. `optimizer.scenario` reproduit cet état exact quand
`hub_transfers` est faux, ce qui est son défaut : c'est la seule façon de
retrouver les valeurs publiées.

**Ne pas appeler `solve_scenario` en parallèle dans un même processus.**
`Config` porte des attributs de **classe** et `create_toy_data` initialise le
générateur aléatoire **global** de NumPy. La fonction restaure `Config` en
sortie, ce qui suffit au séquentiel et à rien d'autre. Sérialiser, ou passer par
des sous-processus.

**Le budget de recherche change la solution.** `GUIDED_LOCAL_SEARCH` consomme
tout le temps qui lui est donné : 10 s et 30 s ne produisent pas la même
tournée, et pas non plus des tournées comparables en qualité (relevé : 30 s
donne un horizon de 7 178 s, 5 s de 8 644 s, 10 s de 11 832 s). Le test de
référence n'est reproductible qu'à budget **et** vitesse machine égaux.

**`RoutingSearchParameters` n'a pas de champ `num_search_workers`.** Le seul
réglage de parallélisme accessible est `sat_parameters.num_workers`, déjà à 1
par défaut. `lns_time_limit` vaut 100 ms par défaut : elle ne peut pas faire
déborder le budget total.

**Le dépôt vient de `Config.DEPOT_POSITION`.** Il était codé en dur à `(0.0, 0.0)`
dans `data_loader.py` — Null Island, en plein Atlantique. Ne pas réintroduire de
coordonnée en dur : les données jouet et le chargeur doivent rester cohérents.

## Conventions

- **Aucune clé d'API** dans ce projet. OSRM et OpenStreetMap sont utilisés sans
  authentification, et c'est délibéré : le dépôt a déjà connu une fuite de 5 clés
  via `.github/secrets.env` (purgée de l'historique). Le `.gitignore` couvre
  désormais `*.env`, `*.key`, `*.pem` — le motif `.env` seul ne matchait pas
  `secrets.env`.
- Les artefacts générés (`vrp_visualization.html`, `optimizer/tests/toy_data/`,
  `.cache/`) ne sont pas versionnés.
- Commentaires et documentation en français.
- Toute fonctionnalité terminée est ajoutée à `features-inventory.md`, avec son
  point d'entrée et ses tests.
- Le format du document de tournée (`optimizer/tour_format.py`) est un contrat
  public : la page de démonstration du portfolio en dépend. Sept invariants y
  sont listés et vérifiés par les tests. Ajouter une clé est sans risque, en
  renommer ou en retirer une casse le consommateur.

## Chantiers ouverts

1. **Alimenter la matrice de coûts avec les distances OSRM.** Aujourd'hui le
   solveur optimise sur des distances euclidiennes tandis que l'affichage montre
   des itinéraires routiers : les deux ne sont pas cohérents. C'est l'amélioration
   la plus rentable.
2. **Revoir l'indicateur de déséquilibre.** Il se fonde sur la charge résiduelle
   en fin de tournée (`final_loads`), qui mesure mal la charge de travail. Le
   nombre de clients servis ou le temps par véhicule seraient de meilleurs proxys.
3. **Instrumenter `calc_time`**, actuellement figé à 0 dans `postprocessor.py`.
