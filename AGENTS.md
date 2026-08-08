# AGENTS.md — mémoire projet

Notes destinées à un agent qui reprend ce dépôt. Le README couvre l'usage ;
ce fichier retient ce qui n'est pas déductible du code.

## Lancer le projet

```bash
python -m optimizer.main     # résout et génère vrp_visualization.html
pytest                       # 14 tests
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

## Chantiers ouverts

1. **Alimenter la matrice de coûts avec les distances OSRM.** Aujourd'hui le
   solveur optimise sur des distances euclidiennes tandis que l'affichage montre
   des itinéraires routiers : les deux ne sont pas cohérents. C'est l'amélioration
   la plus rentable.
2. **Revoir l'indicateur de déséquilibre.** Il se fonde sur la charge résiduelle
   en fin de tournée (`final_loads`), qui mesure mal la charge de travail. Le
   nombre de clients servis ou le temps par véhicule seraient de meilleurs proxys.
3. **Instrumenter `calc_time`**, actuellement figé à 0 dans `postprocessor.py`.
