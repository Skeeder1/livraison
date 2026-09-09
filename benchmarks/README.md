# Banc d'essai — le solveur contre les meilleures solutions connues

Jusqu'ici le solveur n'avait été comparé qu'à lui-même, ce qui ne prouve rien.
Ce répertoire le mesure contre les valeurs **publiées** sur les instances
Solomon (1987) à 100 clients, une par classe : `C101` (clients groupés),
`R101` (aléatoires), `RC101` (mixte).

Rien sous `optimizer/` n'est modifié. Le banc d'essai traduit l'instance vers
le format de jeu de données que `optimizer.data_loader` sait relire, appelle
`optimizer.solver.solve_vrp`, puis **recontrôle tout** avec sa propre
arithmétique.

```bash
.venv/bin/python -m benchmarks.run_benchmark                       # campagne complète
.venv/bin/python -m benchmarks.run_benchmark --budgets 10 --instances C101
.venv/bin/python -m pytest tests/unit/test_benchmarks_solomon.py   # contrôles
```

Les résultats sont écrits dans `benchmarks/results/` (`results.json` et
`table.txt`).

## Le piège central : il y a deux familles de valeurs publiées

Elles portent sur les mêmes instances et ne sont **pas** comparables. Les
confondre fabrique un écart fantôme de plusieurs pour cent, silencieusement.

|                | SINTEF (registre TOP)                  | CVRPLIB / DIMACS / PyVRP        |
| -------------- | -------------------------------------- | ------------------------------- |
| Objectif       | hiérarchique : véhicules puis distance | distance totale seule           |
| Flotte         | minimisée en premier                   | libre                           |
| Arithmétique   | double précision                       | troncature au dixième, par arc  |
| Statut         | meilleure connue                       | **optimum prouvé**              |
| C101           | 10 véh. / 828,94                       | 10 tournées / 827,30            |
| R101           | 19 véh. / 1 650,80                     | 20 tournées / 1 637,70          |
| RC101          | 14 véh. / 1 696,95                     | 15 tournées / 1 619,80          |

SINTEF l'écrit en tête de sa page : « Exact methods typically use a monolithic
total distance objective and use integral or low precision distance and time
calculations. Hence, results are not directly comparable. »

Sources :

- SINTEF TOP, 100 clients — <https://www.sintef.no/projectweb/top/vrptw/solomon-benchmark/100-customers/>
- CVRPLIB — <https://vrp.atd-lab.inf.puc-rio.br/index.php/en/instances/2>
- Instances et solutions redistribuées par PyVRP — <https://github.com/PyVRP/Instances/tree/main/VRPTW/Solomon>
- Règles DIMACS (convention d'arrondi) — <https://dimacs.rutgers.edu/images/programs/implementation_challenges/archive/VRPTW_Competition_Rules.pdf>

### Conventions appliquées

- distance **euclidienne plane** sur les coordonnées données ;
- temps de trajet **égal** à la distance (vitesse unitaire) ;
- temps de service **constant par client** (90 pour C1, 10 pour R1 et RC1),
  indépendant de la demande ;
- attendre l'ouverture d'une fenêtre est permis et **gratuit** ; arriver après
  sa fermeture est une violation ;
- convention `dimacs` : `d_ij = ⌊10 e_ij⌋ / 10`, **arc par arc**. Tronquer le
  total au lieu de chaque arc est l'erreur de reproduction classique, et ne
  donne ni l'une ni l'autre des deux familles ;
- convention `exact` : euclidien en double précision, sans arrondi.

Le fait que ces conventions soient les bonnes n'est pas supposé : les tournées
publiées sont relues et redonnent les six valeurs publiées au centième
(`test_reproduit_l_optimum_cvrplib_sous_convention_dimacs` et son pendant
SINTEF). Tant que ces contrôles passent, l'instance lue, la convention
appliquée et le vérificateur sont simultanément validés.

Démonstration que les deux familles sont bien deux problèmes distincts :
l'optimum CVRPLIB de RC101, valide sous troncature, **viole une fenêtre
horaire** dès qu'on repasse en double précision.

## Ce que le modèle du dépôt sait exprimer, et ce qu'il ne sait pas

Détail complet et démonstrations dans l'en-tête de `benchmarks/convert.py`.

**Le temps de service ne correspond pas.** `optimizer.solver.service_time`
calcule `|demande| × SERVICE_TIME_PER_UNIT` — proportionnel à la demande.
Solomon donne un temps de service constant par client. Aucune valeur de
`SERVICE_TIME_PER_UNIT` ne réconcilie les deux dès que deux clients ont des
demandes différentes, ce qui est le cas sur les trois instances.

Le contournement est **exact** et ne touche pas au solveur : `SERVICE_TIME_PER_UNIT`
passe à 0 et le temps de service est replié dans la matrice, au nœud d'origine,
`M[i][j] = d_ij + s_i`. Le transit du modèle redevient `s_i + d_ij`, la
sémantique exacte de Solomon. Le surcoût sur la dimension Distance vaut
`Σ s_i`, une constante pour toute solution servant tous les clients, donc sans
effet sur l'optimum — et le banc d'essai recalcule de toute façon la distance
depuis les tournées plutôt que de lire l'objectif du solveur.

**Réglages neutralisés**, tous par `Config` : `NUM_HUBS = 0` et
`NUM_UNLOAD_DEPOTS = 0` (Solomon n'a ni transfert ni rechargement en cours de
tournée), `TIME_WINDOWS_OPTIONAL = False` (fenêtres dures), les trois
coefficients d'étalement à 0, `VEHICLE_FIXED_COST_METERS = 0`.

**Ce qui reste, et qui n'est piloté par aucune clé.**
`setup_time_constraints` appelle `SetSlackCostCoefficientForVehicle(100, v)`.
L'appel porte sur toute la dimension temporelle : **attendre coûte 100 par
unité de temps**, alors que chez Solomon attendre est gratuit. Le terme est
mesurable — sur R101, `objectif − somme des coûts d'arc` vaut exactement
`attente totale × 100`. Il ne se débranche pas, mais il se dilue : le rapport
entre le poids d'une unité de distance et celui d'une unité d'attente est
réglable par `DISTANCE_TO_METERS_FACTOR` / `DISTANCE_TO_TIME_FACTOR`. C'est le
paramètre `cost_scale`, à 10 000 par défaut (distance 100 fois l'attente).
Mesuré sur R101 à 20 s : 1 841,7 à poids égal, 1 669,1 à rapport 100, et plus
aucune amélioration au-delà.

**Fausse alerte, vérifiée.** L'évaluateur de distance écrase le coût de l'arc
dépôt→dépôt par `vehicle_max_distance`, ce qui reviendrait à facturer une
tournée entière à qui laisse un véhicule inutilisé. `RoutingModel` ne compte ni
le coût d'arc ni le coût fixe d'une tournée vide : sur C101 avec 25 véhicules
pour 10 utilisés, `GetArcCostForVehicle` retourne 0 sur cet arc et l'objectif
égale la somme des coûts d'arc des seules tournées non vides. La sentinelle est
inerte.

## Ce qui est vérifié plutôt que supposé

- **les coûts d'arc du modèle.** `benchmarks.runner.audit_arc_costs` relit, sur
  chaque arc parcouru, `GetArcCostForVehicle` et le transit de la dimension
  `Time`, et les compare à ce que la conversion promet. Une campagne dont ce
  contrôle échoue est annoncée comme telle : les écarts n'y voudraient rien
  dire ;
- **la faisabilité.** `optimizer.verify` contrôle le *document de tournée* du
  dépôt, que ce chemin ne produit pas, et raisonne en mètres et en secondes.
  `benchmarks.verifier` refait donc les contrôles depuis les seules tournées et
  l'instance publiée : chaque client servi exactement une fois, capacité,
  fenêtres horaires, retour au dépôt avant sa fermeture. Rien de ce que le
  solveur annonce n'est repris ;
- **l'échelle.** Le modèle tronque (`int(distance × facteur)`). Sous DIMACS
  toutes les distances sont des multiples d'un dixième, donc un facteur 10 ne
  perd rien et l'arithmétique du solveur est celle de Solomon **exactement**.
  Sous `exact` la troncature est inévitable ; elle joue à la baisse, donc elle
  relâche imperceptiblement les fenêtres — raison de plus pour que le
  vérificateur recontrôle en arithmétique non tronquée.

## Régimes de flotte

Deux régimes sont mesurés, et l'écart entre eux est lui-même un résultat.

- `bks` — exactement le nombre de véhicules de la solution publiée. Comparaison
  honnête sur la distance : à flotte égale, quelle distance ?
- `libre` — la flotte annoncée par l'instance (25 véhicules), ce que le solveur
  choisit quand on le laisse faire. C'est le régime qui correspond à l'objectif
  CVRPLIB, où la flotte est libre.

## Isolation et parallélisme

`optimizer.config.Config` porte des attributs de **classe** : deux instances
converties différemment se corrompraient dans un même interpréteur. Chaque
mesure part donc dans son propre processus. Le parallélisme est plafonné à 12
processus sur cette machine à 16 cœurs : la recherche d'OR-Tools est
mono-thread — `RoutingSearchParameters` n'expose aucun réglage de parallélisme
— et saturer les cœurs ferait concurrencer les mesures entre elles, au
détriment du budget qu'on croit leur avoir donné.

## Provenance des fichiers d'instance

Chaque instance est présente en deux formats, et ils sont comparés champ à
champ au chargement (`solomon.check_agreement`) : un désaccord lève plutôt que
de mesurer sur une instance douteuse.

| Fichier            | Contenu                             | Origine |
| ------------------ | ----------------------------------- | ------- |
| `<I>.vrp`          | instance, format VRPLIB             | `PyVRP/Instances` |
| `<I>.txt`          | instance, format Solomon historique | miroir `iRB-Lab/py-ga-VRPTW` |
| `<I>.sol`          | tournées optimales CVRPLIB          | `PyVRP/Instances` |
| `<I>.sintef.sol`   | tournées du registre SINTEF         | `sintef.no` |
