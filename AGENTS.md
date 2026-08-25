# AGENTS.md — mémoire projet

Notes destinées à un agent qui reprend ce dépôt. Le README couvre l'usage ;
ce fichier retient ce qui n'est pas déductible du code.

## Lancer le projet

```bash
python -m optimizer.main     # résout et génère vrp_visualization.html
pytest                       # 77 tests, environ 55 s
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

**Retirer les hubs se fait avec `strip_hubs`, jamais en posant `num_hubs = 0`.**
Les nœuds de hub vivent dans `locations`, `demands` et `time_windows` : baisser
le compteur les laisse dans le modèle, et comme les disjonctions ne sont posées
que sur `range(hub_start, hub_start + num_hubs)`, ils n'en reçoivent aucune. Un
nœud sans disjonction est **obligatoire**. La variante « sans hubs » de
`solve_vrp_with_optimal_hubs` traversait ainsi les hubs sous contrainte pendant
que `get_activated_hubs`, qui boucle sur `num_hubs`, annonçait 0 hub activé.
C'est de cet état défectueux que vient l'instantané publié dans le portfolio
(`delivery-tour.json` : horizon 7178, 140,9 km, arrêts 20/17/19, 2 passages en
hub). Il n'est plus reproductible depuis le correctif, et c'était le but.

Pour vérifier ce genre de mécanisme, deux mesures non ambiguës : le nombre de
disjonctions (`routing.GetNumberOfDisjunctions()`, attendu = clients +
rechargements + hubs + fictifs) et le domaine de `ActiveVar` après
`CloseModel()` : `Min() == 1` signifie « nœud obligatoire ». Éviter
`GetDisjunctionIndices`, surchargé en C++ par identifiant de disjonction et par
index de nœud : depuis Python l'appel est ambigu et sa réponse ininterprétable.

**Un hub ne sert qu'au transfert entre véhicules.** Il ne porte aucune demande :
le traverser sans y échanger de colis ne fait qu'allonger la tournée. Dans
`optimizer.scenario`, `hubs` pilote donc seul le comportement (0 = aucun hub,
au-delà = transferts actifs) ; il n'existe pas d'état intermédiaire.

**Ne pas appeler `solve_scenario` en parallèle dans un même processus.**
`Config` porte des attributs de **classe** et `create_toy_data` initialise le
générateur aléatoire **global** de NumPy. La fonction restaure `Config` en
sortie, ce qui suffit au séquentiel et à rien d'autre. Sérialiser, ou passer par
des sous-processus.

**Le budget de recherche change la solution.** `GUIDED_LOCAL_SEARCH` consomme
tout le temps qui lui est donné : 10 s et 30 s ne produisent pas la même
tournée, et pas non plus des tournées comparables en qualité (relevé avec les
hubs encore obligatoires : 30 s donnait un horizon de 7 178 s, 5 s de 8 644 s,
10 s de 11 832 s ; la qualité n'est donc pas monotone en budget). Le test de
référence n'est reproductible qu'à budget **et** vitesse machine égaux.

**Il n'existe pas de réglage de parallélisme.** `RoutingSearchParameters` n'a
**aucun** champ `num_search_workers` : liste des champs vérifiée sur OR-Tools
9.15.6755. La recherche CP classique est mono-thread. Le champ voisin
`sat_parameters.num_workers` ne concerne que les chemins CP-SAT, inactifs ici
(`use_cp_sat` = BOOL_FALSE). Ne pas repartir à sa recherche.

**`lns_time_limit` vaut 100 millisecondes par défaut**, pas 100 secondes
(`seconds=0, nanos=100_000_000` sur 9.15.6755) : elle ne peut pas faire déborder
le budget total. Et `Duration.FromSeconds` n'accepte qu'un entier :
`FromSeconds(1.5)` lève `TypeError` ; pour un budget inférieur à la seconde,
passer par `FromMilliseconds`.

**Le cache OSRM ne doit jamais faire échouer un calcul.** Son écriture était
hors du bloc protégé : sur un système de fichiers en lecture seule, un appel
OSRM **réussi** levait `OSError` et emportait la requête, alors que le chemin
d'échec réseau, lui, était traité proprement. Lecture et écriture sont désormais
protégées, l'écriture est atomique, et `OSRM_CACHE_DIR` déplace le cache là où
l'on peut écrire.

**Le dépôt vient de `Config.DEPOT_POSITION`.** Il était codé en dur à `(0.0, 0.0)`
dans `data_loader.py` — Null Island, en plein Atlantique. Ne pas réintroduire de
coordonnée en dur : les données jouet et le chargeur doivent rester cohérents.

**L'objectif est calibré pour une flotte, pas pour un véhicule.**
`TIME_SPAN_COEFFICIENT = 200` pose un coût sur l'étendue globale de la dimension
Time. Avec plusieurs véhicules, ce terme équilibre les tournées entre elles ;
avec un seul, l'étendue globale **est** cette tournée, et le terme dégénère en
péage forfaitaire sur le temps de conduite. Face aux 100 000 de pénalité pour
abandonner un client, le seuil de rentabilité tombe à 500 secondes de tournée
par client servi, et une instance peu dense le dépasse largement.

Mesuré, même instance de dix clients et un seul véhicule, en ne faisant varier
que le coefficient : à 200 il sert 0 client sur 10, à 50 et en dessous il les
sert tous les 10 sur une tournée de 7 006 s. Au coefficient livré, deux
véhicules servent 10 sur 10.

Le solveur répond donc correctement à son objectif ; c'est l'objectif qui est
mal calibré pour une flotte d'un. Cela explique aussi le motif contre-intuitif
où les grosses instances réussissent et les petites échouent : plus l'instance
est dense, plus le coût marginal par client baisse, donc plus de clients passent
la barre des 500 s.

Ne pas toucher au coefficient sans mesurer : il est réglé autour du scénario de
référence à trois véhicules, et le déplacer déplace tous les chiffres publiés.

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
