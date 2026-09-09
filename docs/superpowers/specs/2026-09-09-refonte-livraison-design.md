# Refonte du dépôt livraison — document de conception

Date : 2026-09-09
Statut : **en attente de relecture**
Portée : l'algorithme, la structure du dépôt, et l'unification de l'interface avec le portfolio.

---

## 1. Pourquoi ce document

Le dépôt est une vitrine professionnelle. Il doit être lisible par un recruteur
en trente secondes, crédible en trois minutes, et solide s'il est lu en trente.
Aujourd'hui il ne l'est pas : le modèle d'optimisation contient des constructions
mortes, les chiffres publiés ne correspondent pas à ce que le solveur calcule, et
la même notion est implémentée jusqu'à cinq fois.

Ce document fixe ce qu'on construit et dans quel ordre. Il ne contient pas de code.

---

## 2. État des lieux — constats vérifiés

Chaque ligne a été vérifiée dans le code, pas déduite d'un commentaire.

### 2.1 Le transfert entre coursiers existe, fonctionne, et ne peut jamais être choisi

`add_hub_constraints` (`optimizer/solver.py:474-507`) construit un vrai transfert :
un nœud de dépôt (demande −1) et un nœud de retrait (+1) aux coordonnées du hub,
avec précédence temporelle (`:493`), obligation de deux véhicules distincts
(`:496`) et une égalité de capacité (`:499-502`).

Mais `configure_constraints_and_penalties` (`:311-347`) ne pose **aucune
disjonction** sur ces deux nœuds : ils sont donc **obligatoires**. Mesuré après
`CloseModel()` : `ActiveVar = [1, 1]`.

Conséquence : `hubs > 0` ne *permet* pas un échange, il en **impose** un à chaque
hub. D'où la dégradation mesurée :

| | servis | roadKm | horizon |
|---|---|---|---|
| `hubs=0` | 45/45 | 104.8 | 7 791 |
| `hubs=2` | 45/45 | 162.8 | 23 024 |

`solve_vrp_with_optimal_hubs` (`:603`) contourne le problème en résolvant deux
fois et en gardant le meilleur — un faux dilemme entre « 2 transferts imposés »
et « 0 transfert ». Il n'existe aucun moyen d'exprimer « un transfert, s'il est
rentable ».

### 2.2 L'égalité de capacité ne conserve rien

Avec des demandes −1/+1, `CumulVar(dépôt) + (−1) == CumulVar(retrait) − (+1)`
se réduit à `CumulVar(dépôt) == CumulVar(retrait)` : la charge du coursier qui
dépose à son arrivée égale celle du coursier qui collecte à la sienne. Ce n'est
pas une conservation de colis, c'est une coïncidence algébrique.

### 2.3 Le temps de service publié est faux

`service_time` (`:8-22`) utilise `Config.SERVICE_TIME_PER_UNIT` = 60 s. Mais
`setup_data_extensions` (`:78`) écrase `data['time_per_demand_unit']` avec `5`,
et c'est ce 5 que `tour_format.py:291` utilise pour construire la chronologie
publiée. Le `delivery-tour.json` en ligne annonce `serviceTimePerUnit: 5`.

Les coursiers repartent 55 s par unité trop tôt ; l'écart est absorbé
silencieusement par le temps de trajet. La docstring de `service_time` met en
garde contre exactement cette divergence — elle est arrivée par une autre porte :
non pas deux copies de la formule, mais deux valeurs de la constante.

### 2.4 Une notion, plusieurs implémentations

| Notion | Aujourd'hui |
|---|---|
| Distance | 4 implémentations (degrés avec cos, haversine, projection locale, degrés bruts en JS) |
| Temps de service | 60 dans `data_loader`, 5 après le solveur |
| Nombre de véhicules réels | 5 dérivations différentes |
| Classification des nœuds | 4 implémentations |
| Visualisation | folium + JS **et** React |

`optimizer/visualization/script.js:14-24` interpole les positions en degrés bruts
sans correction de latitude — le bug corrigé côté Python le 2026-09-09 (commit
`6f4d7d2`) est toujours vivant côté JS.

### 2.5 Les tests ne testent pas le modèle

78 tests. Aucun n'affirme qu'une charge reste sous la capacité, qu'une arrivée
respecte sa fenêtre, que le rechargement remet la charge à zéro, ni qu'une des
cinq contraintes de transfert (`:493-507`) est satisfaite. `tour_invariants.py`
vérifie la forme du document, pas la validité de la solution.

`optimizer/tests/test_solver.py` est suivi par git et **vide**.

### 2.6 Provenance

`optimizer/solver.py` descend de `cvrptw_reload_V2.py` (commit initial `ec888eb`),
copie modifiée de l'échantillon OR-Tools « CVRPTW with reload », en-tête
`Copyright 2015 Tin Arm Engineering AB / Copyright 2018 Google LLC`, licence
Apache 2.0. Le commit initial contient d'ailleurs un dossier `official/` avec les
échantillons d'origine — la provenance n'a jamais été cachée, elle n'est
simplement plus documentée. Dans HEAD : **aucune attribution ne subsiste**, et
`LICENSE` porte « MIT — Copyright (c) 2026 Elias Bellouti ».

La contrainte `!=` ne provient pas d'une inversion de `explorations/vrpspdtw.py` :
`cvrptw_reload_V2.py:205` la contient déjà dans le même commit initial.

### 2.7 L'exploration est à deux lignes de fonctionner

`explorations/vrpspdtw.py` modélise un enlèvement-livraison **apparié** (un colis
de A vers B), pas simultané : le sigle VRPSPDTW est inexact, c'est un PDPTW.
Deux défauts l'empêchent de calculer quoi que ce soit : `data['manager']` n'est
jamais affecté, et le callback de temps renvoie un flottant. L'exception traverse
la frontière SWIG et **tous** les callbacks renvoient 0 ensuite — d'où
`Distance: 0m`.

Corrigé (deux lignes), il produit une solution vérifiée à la main : objectif 182,
six fenêtres de temps respectées, appariements et précédences corrects.

### 2.8 Divers

- `stats.py` : mort et cassé (`Config.MAX_TIME_LIMIT` n'existe pas).
- `time_matrix.npy` : écrit, chargé, jamais utilisé.
- `legs[].road` vaut `true` même quand OSRM est injoignable.
- `cvrptw-solve` écrit en relatif au répertoire courant et lit en relatif au paquet.
- Installation non-éditable cassée : `optimizer/visualization/*` absent du wheel.
- `optimizer/optimizer/tests/toy_data/` : suivi, référencé nulle part, données pré-Paris.
- `optimizer/.github/*.md` : 1 851 lignes décrivant un solveur qui n'existe plus.
- Aucune CI, aucun linter, aucun formateur, aucun vérificateur de types.
- Compteur de tests : badge « 14 », texte « 77 », réalité **78**.

---

## 3. Décisions prises

1. **Ambition** : nettoyer *et* rendre les transferts rentables. Pas de hubs
   mobiles (points de rendez-vous comme variables libres) pour l'instant.
2. **Interface** : la brique React du portfolio devient la source unique,
   hébergée dans ce dépôt sous forme de paquet TypeScript. On reprend telle
   quelle la carte actuelle du site ; l'esthétique sera retravaillée ensemble
   à la fin.
3. **Calibration** : les pénalités seront réglées par une campagne
   expérimentale, pas à la main.

---

## 4. Décisions ouvertes

- **Attribution (bloquant avant toute publication)** : comment créditer
  l'échantillon OR-Tools. Proposition : conserver l'en-tête Apache dans le
  fichier dérivé, ajouter une section « Provenance » au README indiquant le
  point de départ et ce qui a été ajouté, garder MIT sur les ajouts propres.
  La formule « j'ai écrit le CVRP moi-même » n'est pas défendable ; « je suis
  parti de l'échantillon CVRPTW-with-reload et je l'ai étendu avec un transfert
  entre coursiers » l'est, et reste un bon récit.
- **Langue** : proposition — anglais pour les documents publics (README), français
  pour les documents de travail internes (AGENTS.md, ce document). À trancher.
- **Rotation du token Railway** : reportée à la demande de l'utilisateur.

---

## 5. Architecture cible

### 5.1 Principe directeur

**Une seule source de vérité par notion.** Chaque défaut listé en §2 a la même
forme : une valeur définie deux fois, qui diverge en silence.

| Notion | Cible |
|---|---|
| Métrique de distance | une, corrigée en cos(latitude), en mètres |
| Temps de service | une constante, jamais réécrite |
| Nombre de véhicules réels | un champ, porté par le document de tournée |
| Classification des nœuds | un classifieur |
| Visualisation | un composant React |

### 5.2 Découpage Python

```
optimizer/
  instance/   génération, matrice de distance, chargement
  model/      modèle de routage, dimensions, contraintes, transferts
  search/     paramètres de recherche, point d'entrée de résolution
  report/     document de tournée, statistiques, géométrie routière
```

Le dictionnaire `data` cesse d'être muté en cours de route : ce qui entre dans le
solveur est ce qui ressort dans le rapport.

### 5.3 Le transfert, corrigé

```
ActiveVar(dépôt) == ActiveVar(retrait)     # les deux, ou aucun
AddDisjunction([dépôt],  TRANSFER_PENALTY)  # abandonnable
AddDisjunction([retrait], TRANSFER_PENALTY)
```

`ActiveVar` et la sémantique de `AddDisjunction` ont été vérifiées contre
OR-Tools 9.15.6755 installé, pas contre un souvenir.

Avec une pénalité faible, un transfert doit se justifier par la distance qu'il
économise. `solve_vrp_with_optimal_hubs` disparaît : on résout une fois, le
solveur décide.

L'égalité de capacité (§2.2) est remplacée par une vraie conservation, ou
supprimée si elle n'exprime rien.

### 5.4 Interface partagée

```
web/
  src/   <DeliveryReplay/>, types de tournée, client de résolution
  demo/  application Vite autonome  →  remplace vrp_visualization.html
```

Le portfolio la consomme comme dépendance git épinglée, exactement comme il
épingle déjà le solveur Python. `DeliveryDemoPage.astro` ne garde que l'habillage
de page. La couture entre les deux projets est **le schéma JSON de tournée** —
c'est la seule interface à stabiliser, et la raison pour laquelle le Python passe
en premier.

Le chemin folium/`script.js` est supprimé : c'est une seconde implémentation qui
dérive et porte encore un bug déjà corrigé ailleurs.

---

## 6. Méthodologie de calibration

### 6.1 Le piège à éviter

**On ne peut pas régler une pénalité contre l'objectif qu'elle définit.**
Demander « quelle pénalité d'abandon minimise l'objectif ? » a pour réponse « la
plus faible », puisque abandonner devient bon marché. L'objectif bouge quand le
bouton bouge : il ne peut pas servir de mètre.

### 6.2 Critère externe, fixé à l'avance

Ordre lexicographique, jamais ajusté ensuite :

1. **clients servis** (maximiser)
2. **makespan** (minimiser) — quand le dernier coursier rentre
3. **kilomètres réels** (minimiser)

Tout le reste est un bouton, mesuré contre ce critère.

### 6.3 Protocole

- **Blocs appariés** : un jeu fixe d'environ 30 graines ; *toute* configuration
  est évaluée sur *les mêmes* graines. La variance entre instances dépasse
  largement la plupart des effets de paramètres — l'appariement est ce qui rend
  les petits effets visibles.
- **Phase 1, un facteur à la fois** : chaque pénalité balayée seule, en échelle
  logarithmique, les autres au niveau de référence. Sortie : une courbe de
  réponse par facteur, et un verdict honnête sur les facteurs dont l'effet
  dépasse le bruit. La plupart n'en auront pas. C'est un résultat, pas un échec.
- **Phase 2** : seuls les facteurs survivants entrent dans une grille.
- **Budget de résolution fixe pendant le balayage, puis contrôle de stabilité à
  3× le budget.** Sinon on règle les pénalités pour compenser une recherche non
  convergée, et l'optimum s'évapore dès que quelqu'un laisse tourner plus
  longtemps.
- **Médianes et écarts par graine**, jamais une exécution isolée.

Facteurs candidats : `DROP_CUSTOMER_PENALTY_METERS`, `TRANSFER_PENALTY` (nouveau),
`TIME_SPAN_COEFFICIENT`, `CAPACITY_SPAN_COEFFICIENT`, `DISTANCE_SPAN_COEFFICIENT`,
pénalité d'arc de hub, `TIME_WINDOW_VIOLATION_PENALTY`, `SetFixedCostOfAllVehicles`.

### 6.4 Validation du harnais

On sait déjà (AGENTS.md) qu'un `TIME_SPAN_COEFFICIENT` élevé fait dégénérer la
solution vers un véhicule unique autour de 500 s/client. **Si la campagne ne
redécouvre pas ce seuil toute seule, c'est le harnais qui est faux.**

### 6.5 Infrastructure

`experiments/`, résultats en JSONL append-only (un plantage ne perd rien),
reprise possible (les lignes déjà faites sont sautées), un processus système par
exécution avec son propre répertoire de travail — `Config` est global au
processus et muté, les fils d'exécution sont donc exclus.

Machine : 16 cœurs, ~8 Go libres ; un budget de 10 s coûte 10,2 s de temps réel.
À 12 processus : ~4 300 exécutions par heure. Lancement via `nohup`, aucun jeton
consommé pendant la campagne, lecture du fichier de résultats à la fin.

---

## 7. Plan de travail

| # | Étape | Dépend de |
|---|---|---|
| 0 | Attribution + provenance dans le README | décision §4 |
| 1 | Transferts optionnels ; suppression de la double résolution | — |
| 2 | Une source de vérité par notion (temps de service, distance, comptage) | — |
| 3 | Harnais de calibration + campagne nocturne | 1 |
| 4 | Instances où les transferts sont rentables, choisies par la campagne | 3 |
| 5 | Tests sur les propriétés du modèle, pas sur des nombres figés | 1, 2 |
| 6 | Découpage en sous-paquets, suppression du code mort, CI, linter | 5 |
| 7 | Paquet TypeScript `web/`, portfolio bascule dessus | 2 |

L'étape 3 doit suivre l'étape 1 : régler une pénalité de transfert pendant que
les transferts sont obligatoires ne mesure rien.

---

## 8. Critères de succès

- Aucune valeur publiée ne contredit ce que le solveur a calculé.
- Les transferts sont choisis par le solveur, et on sait dire dans quelles
  conditions ils sont rentables — avec des courbes à l'appui.
- Les tests échouent si une contrainte du modèle est violée, pas seulement si un
  nombre bouge.
- Chaque constante du modèle est justifiée par une mesure ou par un calcul
  explicite dans un commentaire.
- Le site et le dépôt affichent la même interface, issue du même code.

## 9. Risques

- **Le découpage en sous-paquets (§7.6) casse des importateurs.** Il est placé
  après les tests de propriétés, précisément pour avoir un filet.
- **La campagne peut ne rien trouver** : il se peut qu'aucun réglage ne rende les
  transferts rentables sur des instances uniformes. Ce serait un résultat
  publiable — et l'étape 4 deviendrait « concevoir l'instance qui les rend
  rentables », ce qui est déjà prévu.
- **Le portfolio dépend du dépôt au moment du build** : une régression ici casse
  le site. L'épinglage par SHA immuable, déjà en place, contient ce risque.
