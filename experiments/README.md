# `experiments/` — harnais de calibration

Mise en œuvre du §6 du document de conception
[`docs/superpowers/specs/2026-09-09-refonte-livraison-design.md`](../docs/superpowers/specs/2026-09-09-refonte-livraison-design.md).

Ce paquet ne modifie rien dans `optimizer/`. Il l'importe, le pilote depuis des
processus isolés, et écrit ses observations dans un fichier JSONL.

---

## La règle méthodologique centrale

**On ne peut pas régler une pénalité contre l'objectif qu'elle définit.**

Demander « quelle pénalité d'abandon minimise l'objectif du solveur ? » a pour
réponse « la plus faible » : abandonner devient bon marché, l'objectif chute, et
il chute d'autant plus que le bouton descend. L'objectif bouge quand le bouton
bouge ; il ne peut pas servir de mètre.

Toute configuration est donc jugée sur un **critère extérieur au solveur**,
arrêté avant la première mesure et jamais renégocié :

| Rang | Critère | Sens | Champ du document de tournée |
|---|---|---|---|
| 1 | clients servis | maximiser | `stats.customersServed` |
| 2 | makespan | minimiser | `horizon` |
| 3 | kilomètres | minimiser | `stats.roadKm` |

L'ordre est **lexicographique** : un client servi de plus l'emporte sur
n'importe quel gain de makespan, et un makespan plus court l'emporte sur
n'importe quel gain de kilométrage. Ce n'est pas une pondération.

Le critère vit dans [`criterion.py`](criterion.py), seul et testé. Le modifier
invalide toutes les mesures déjà collectées.

---

## Protocole

**Blocs appariés.** Un jeu fixe de graines (30 par défaut, `1000`…`1029`) ;
*toute* configuration est évaluée sur *les mêmes* graines. La variance entre
instances dépasse largement la plupart des effets de paramètres — sans
appariement, elle les enterre tous. Le rapport donne les écarts appariés graine
par graine, pas seulement des moyennes agrégées.

**Un facteur à la fois (phase 1).** Chaque facteur balayé seul, en échelle
logarithmique, les autres à leur valeur de référence. Sortie : une courbe de
réponse par facteur, et un verdict honnête sur ceux dont l'effet dépasse le
bruit. La plupart n'en auront pas. **C'est un résultat, pas un échec.**

**Budget fixe, puis contrôle de stabilité.** Le balayage tourne à budget court
et constant (10 s). Un réglage mesuré à budget court peut n'être qu'une
compensation d'une recherche non convergée ; il s'évapore dès qu'on laisse
tourner plus longtemps. La configuration gagnante est donc rejouée à 3× le
budget — voir [`stability.py`](stability.py).

**Médianes et intervalles interquartiles**, jamais une exécution isolée.
Test des signes pour les comparaisons appariées : il ne suppose ni normalité ni
échelle, seulement que la même instance a été résolue des deux façons.

---

## Déterminisme : mesuré, pas supposé

```bash
.venv/bin/python -m experiments.determinism --repeats 4 --budget 5
```

**Réponse mesurée le 2026-09-09 : `solve_scenario` est déterministe**, entre
processus comme au sein d'un même processus — quatre exécutions de la même
entrée donnent des statistiques strictement identiques.

Conséquence sur le plan d'expérience : **une exécution par (configuration,
graine) suffit**, pas de réplicats. Toute la variance observée est de la
variance *entre instances*, que l'appariement neutralise. Refaire la sonde après
toute modification du solveur ou des paramètres de recherche.

---

## Facteurs

Tous sont des attributs de classe de `optimizer.config.Config`, écrits dans le
processus fils avant la résolution puis **relus et journalisés**
(`factors_effective`) : chaque ligne porte la preuve que la configuration
mesurée est celle demandée.

| Facteur | Livré | Remarque |
|---|---|---|
| `TRANSFER_PENALTY_METERS` | 0 | n'a de sens qu'avec `hubs > 0` |
| `DROP_CUSTOMER_PENALTY_METERS` | 1 000 000 | |
| `TIME_SPAN_COEFFICIENT` | 200 | dégénère à un seul véhicule, cf. auto-validation |
| `CAPACITY_SPAN_COEFFICIENT` | 50 | |
| `DISTANCE_SPAN_COEFFICIENT` | 30 | |
| `TIME_WINDOW_VIOLATION_PENALTY` | 50 000 | **inerte** si `time_windows_binding` est faux |
| `SERVICE_TIME_PER_UNIT` | 60 | |
| `VEHICLE_FIXED_COST_METERS` | 50 | lu par `solver.py` depuis le 2026-09-09 |

`TIME_WINDOW_VIOLATION_PENALTY` ne pèse que si les fenêtres horaires mordent :
étalées sur la journée entière, elles ne sont jamais violées et la pénalité ne
s'applique à rien. La grille livrée comporte donc une troisième variante de
scénario, `time_windows_binding: true`, sans quoi ce facteur produirait une
courbe plate qu'on lirait à tort comme « aucun effet ».

Un facteur déclaré connu mais absent de `Config` fait **échouer** le
développement de la grille. C'est délibéré : mesurer un bouton débranché produit
exactement la même courbe qu'un bouton sans effet.

---

## Utilisation

### Auto-validation (à lancer en premier)

```bash
.venv/bin/python -m experiments.validate --seeds 5 --budget 5
```

Vérifie que le harnais redécouvre seul une dégénérescence déjà mesurée à la
main. Voir « Auto-validation » plus bas.

### Plan de campagne, sans rien exécuter

```bash
.venv/bin/python -m experiments.run --grid experiments/grids/ofat.json \
    --seeds 30 --budget 10 --out /dev/null --dry-run
```

### Campagne complète

```bash
nohup .venv/bin/python -m experiments.run \
    --grid experiments/grids/ofat.json \
    --seeds 30 --workers 12 --budget 10 \
    --out experiments/out/ofat.jsonl --resume \
    > experiments/out/ofat.log 2>&1 &

wc -l experiments/out/ofat.jsonl   # avancement, à tout moment
```

Interrompue à `Ctrl-C` ou par une coupure, la campagne se reprend avec **la même
commande** : les couples `(configuration, graine)` déjà journalisés sont sautés.

### Analyse

```bash
.venv/bin/python -m experiments.analyse experiments/out/ofat.jsonl \
    --json experiments/out/ofat-resume.json \
    --plots experiments/out/figures
```

Le rapport texte est la sortie de référence ; les figures ne sont qu'un confort
de relecture et `matplotlib` reste optionnel.

### Contrôle de stabilité de la gagnante

```bash
.venv/bin/python -m experiments.stability experiments/out/ofat.jsonl \
    --multiplier 3 --out experiments/out/stabilite.jsonl --resume
```

---

## Format de grille

JSON — `pyyaml` n'est pas installé dans `.venv`, et lire trente lignes ne
justifie pas une dépendance de plus.

```json
{
  "name": "phase1-ofat",
  "budget_seconds": 10,
  "scenario": {"customers": 45, "vehicles": 3, "capacity": 10},
  "scenario_variants": [{"hubs": 0}, {"hubs": 2}],
  "baseline_factors": {},
  "sweeps": [
    {"factor": "TIME_SPAN_COEFFICIENT", "values": [5, 50, 200, 1500]},
    {"factor": "DROP_CUSTOMER_PENALTY_METERS",
     "log_range": {"from": 10000, "to": 10000000, "points": 7}}
  ]
}
```

`baseline_factors` ne liste que ce qui s'écarte de `Config` : la référence de la
campagne **est** la configuration du dépôt. Un point de balayage égal à la
référence est fusionné avec elle et n'est donc exécuté qu'une fois — c'est ce
qui rend l'appariement gratuit et fait passer chaque courbe de réponse par le
point de référence.

Grilles livrées : [`grids/ofat.json`](grids/ofat.json) (phase 1 complète) et
[`grids/pilote.json`](grids/pilote.json) (validation de bout en bout, quelques
minutes).

---

## Robustesse

* **JSONL append-only**, une ligne écrite puis `flush` + `fsync` avant
  l'exécution suivante : un plantage ne perd que les exécutions en vol.
* **Reprise** sur `(config_key, seed)`, où `config_key` est une empreinte du
  *contenu* de la configuration. Changer une valeur de la grille change la clé —
  rien n'est repris à tort ; réordonner le fichier ne la change pas — rien n'est
  réexécuté inutilement. Le budget entre dans l'empreinte.
* **Un processus système par exécution**, sans réutilisation, et son propre
  répertoire de travail. `Config` n'a que des attributs de **classe** et
  `create_toy_data` initialise le générateur aléatoire **global** de NumPy : deux
  exécutions parallèles dans un même processus se corrompraient en silence, sans
  jamais lever d'exception. Les fils d'exécution sont donc exclus.
* **Délai maximal par exécution** (6 × budget + 120 s). Un solveur bloqué
  immobiliserait un créneau jusqu'au matin ; il est tué et l'incident journalisé
  comme un résultat ordinaire.
* **Un échec est une donnée.** Résolution impossible, processus tué par le noyau,
  plantage de la couche SWIG : la ligne est écrite avec sa cause, et la campagne
  continue.
* `fetch_roads=False` **toujours** : aucun appel réseau, campagne reproductible
  hors ligne. `roadKm` mesure alors des segments droits, donc sa valeur absolue
  n'est pas comparable à celle d'une exécution avec OSRM. Toutes les
  configurations subissant la même convention, la comparaison reste valide — mais
  **ne jamais mélanger les deux modes dans un même journal**.

---

## Auto-validation

Un harnais doit être étalonné sur un phénomène connu par une autre voie, sinon
rien ne distingue « ce facteur n'a pas d'effet » de « ce harnais ne mesure
rien ».

`AGENTS.md` documente une dégénérescence mesurée à la main : avec **un seul**
véhicule, `TIME_SPAN_COEFFICIENT` cesse d'équilibrer une flotte et devient un
péage sur le temps de conduite. Le solveur abandonne alors un client dès que le
servir coûte plus de `DROP_CUSTOMER_PENALTY_METERS / TIME_SPAN_COEFFICIENT`
secondes.

`validate.py` mène **trois** contrôles :

| | Conditions | Attendu |
|---|---|---|
| **A** | abandon 100 000, service **5 s/unité** | effondrement dans ]50 ; 500] — le relevé d'origine |
| **B** | abandon 100 000, service 60 s/unité | seuil nettement **plus bas** |
| **C** | abandon 1 000 000, service 60 s/unité | seuil ~10× **plus haut** que B |

Le contrôle A doit reproduire le service de **5 s par unité** qui avait cours au
moment du relevé : `data_loader` écrasait alors `Config.SERVICE_TIME_PER_UNIT`
(§2.3 du document de conception). Cette divergence corrigée, servir un client
coûte douze fois plus de temps, et le seuil descend d'autant. Comparer sans
rétablir cette valeur, c'est comparer deux problèmes différents.

A prouve qu'on retrouve un chiffre connu ; B prouve qu'on retrouve le
*mécanisme*, en prédisant où le seuil se déplace quand un autre paramètre bouge.
Reproduire un nombre ne démontre qu'une recopie de conditions.

### Résultat mesuré le 2026-09-09 (5 graines, budget 5 s) — **RÉUSSI**

| Contrôle | Seuil prédit | Seuil observé | Rapport |
|---|---|---|---|
| A — relevé | 164 | **100** | 0,61 |
| B — abandon ×10 | 1 597 | **1 000** | 0,63 |
| C — livré | 1 468 | **1 000** | 0,68 |

Le seuil se déplace **exactement ×10** quand la pénalité d'abandon est
multipliée par dix, et la formule reste cohérente à un facteur 1,6 près sur les
trois contrôles — un biais constant, donc un modèle qui décrit la bonne
mécanique à une constante près.

**Découverte au passage, indépendante du contrôle.** Le premier essai a échoué,
et l'échec était informatif : à pénalité d'abandon 100 000, le seul
`DISTANCE_SPAN_COEFFICIENT = 30` livré rend l'abandon rentable dès
`TIME_SPAN_COEFFICIENT = 1`. Les deux termes d'étendue **se cumulent**, et aucun
ne s'interprète isolément à pénalité d'abandon faible. C'est ce qui a imposé la
neutralisation de l'étendue en distance dans le contrôle A.

---

## Puissance statistique : le nombre de graines n'est pas cosmétique

Le test des signes est **discret** : avec `n` comparaisons appariées non nulles,
la plus petite valeur p atteignable vaut `2 / 2ⁿ`. À cinq graines le plancher est
`0,0625` — **aucun** résultat, si net soit-il, ne peut franchir 0,05. Un balayage
à cinq graines ne peut donc rien conclure, seulement décrire.

Le rapport le dit lui-même : sous six graines, il affiche
`PUISSANCE INSUFFISANTE`, et chaque recommandation devient `INCONCLUSIF` plutôt
que « aucun effet ». Confondre les deux serait faire passer un manque de
puissance pour un résultat — la façon la plus commune de mentir avec un test.

**Trente graines** donnent un plancher de `2 / 2³⁰`, très largement sous le
seuil : c'est le dimensionnement de la campagne complète.

---

## Ce que le harnais ne fait pas

* **Phase 2 (grille croisée sur les facteurs survivants).** Le développement
  n'accepte qu'un facteur à la fois. Croiser deux facteurs demandera un nouveau
  type de balayage — la structure de `grid.py` s'y prête, le code n'y est pas.
* **Réplicats.** Inutiles tant que `solve_scenario` est déterministe. Si la sonde
  venait à répondre le contraire, le plan devrait changer, pas seulement le code.
* **Choix des instances où les transferts sont rentables** (étape 4 du plan de
  travail) : c'est un usage du harnais, pas une fonction du harnais.

## Un facteur retiré du plan, et pourquoi

`SERVICE_TIME_PER_UNIT` figurait au départ parmi les facteurs balayés. La
campagne du 2026-09-09 l'a « recommandé » à 5 au lieu de 60, en gagnant 30
graines sur 30 et 2 632 s de makespan. La recommandation est rejetée, et le
facteur retiré.

Ce n'est pas un réglage : c'est une donnée physique du problème, le temps qu'un
coursier passe à remettre un colis. L'abaisser ne rend pas le solveur meilleur,
cela retire 45 × 55 s de travail à accomplir. Le critère externe baisse donc
mécaniquement, sans qu'aucune tournée ne soit mieux construite.

C'est la circularité que `criterion.py` interdit, revenue par une autre porte.
La règle qu'on en tire, et qu'il faut appliquer avant d'ajouter un facteur :

> Un facteur ne doit pouvoir déplacer le critère externe **qu'en améliorant la
> recherche**. S'il le déplace en changeant l'énoncé du problème, il n'a rien à
> faire dans le plan.

Au même titre, ne jamais balayer le nombre de clients, la capacité des
véhicules, ni le budget de résolution : tous rendraient le critère meilleur en
rendant le problème plus facile.

## Ce que la campagne a établi

Les coefficients d'étalement pesaient lourd — mais sur la **vitesse de
convergence**, pas sur la qualité de l'optimum. À 10 s de budget,
`TIME_SPAN_COEFFICIENT = 5` bat la valeur livrée sur 30 graines sur 30, avec
3 186 s et 30,9 km d'écart. Au triple du budget, il ne reste que 76 s et 2,3 km :
la configuration livrée finit par arriver au même endroit.

C'est exactement ce que le contrôle de stabilité existe pour attraper. Sans lui,
la campagne aurait publié un gain de 30 % qui s'évapore dès qu'on laisse tourner
la recherche plus longtemps.

Retenu : `TIME_SPAN_COEFFICIENT = 5`, seule valeur qui gagne ou égalise aux deux
budgets et dans les deux scénarios. Les autres facteurs restent à leur valeur
livrée, faute d'effet qui survive au changement de budget.
