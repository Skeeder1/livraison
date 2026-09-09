# État de l'art

Ce dossier rassemble les travaux publiés qui portent sur **notre problème précis**, et
ce qu'ils impliquent pour le code de ce dépôt.

Il n'est pas là pour faire savant. Il existe parce que plusieurs décisions du solveur
ont d'abord été prises à l'intuition, puis vérifiées contre la littérature — et que
dans un cas au moins, la littérature a corrigé un diagnostic que nous avions posé de
travers. Chaque entrée dit donc trois choses : ce que l'article établit, ce que cela
implique ici, et **ce que nous avons mesuré pour le vérifier**.

Les articles en libre accès sont conservés dans `articles/`. Les autres ne sont que
cités : les redistribuer serait de la republication sans droit. La référence, le DOI
et un lien suffisent à les retrouver.

---

## Équité des charges et forme des tournées

### Matl, Hartl & Vidal (2018) — *Workload Equity in Vehicle Routing Problems: A Survey and Analysis*

*Transportation Science* 52(2). DOI [10.1287/trsc.2017.0744](https://doi.org/10.1287/trsc.2017.0744).
Préprint conservé : [`articles/2018-matl-hartl-vidal-equite-des-charges.pdf`](articles/2018-matl-hartl-vidal-equite-des-charges.pdf) ([arXiv:1605.08565](https://arxiv.org/abs/1605.08565)).

**Ce que l'article établit.** Sur une métrique à somme variable — la longueur d'une
tournée en est une — les mesures d'inégalité **non monotones**, dont l'**étendue**
(max moins min) et l'écart-type, produisent des solutions pathologiques :

> « les solutions Pareto-optimales peuvent contenir des tournées **non optimales au
> sens du TSP** »

Mesuré chez eux : **moins de 20 %** des solutions Pareto-optimales sont TSP-optimales
sous ces mesures. Leur recommandation est le **min-max**, monotone. Ils ajoutent que
les solutions optimales en coût sont « assez mal équilibrées : la plus longue tournée
fait environ le double de la plus courte », mais que le coût marginal de l'équité est
faible — près de 40 % des solutions efficaces sont à moins de 10 % de l'optimum.

**Ce que cela implique ici.** `SetGlobalSpanCostCoefficient` coûte, d'après la
documentation d'OR-Tools, `coefficient × (max(cumul de fin) − min(cumul de départ))`.
C'est une **étendue** : à la lecture, notre modèle appliquait la mesure déconseillée.

**Ce que nous avons mesuré.** Les cumuls de départ valent `[0, 0, 0]` sur les trois
dimensions portant un coût d'étalement. Le terme se réduit donc à
`coefficient × max(fin)` : c'est le **min-max recommandé**, et le modèle est conforme.

Mais il l'est **par accident de configuration** — tous les véhicules reçoivent la même
heure de départ. Échelonner les départs suffirait à retransformer ce terme en étendue,
sans que rien ne le signale. L'invariant est écrit dans `optimizer/solver.py`, là où il
peut se casser, avec la parade : une borne souple par véhicule, qui reste monotone.

---

## Attractivité visuelle : ce que l'œil attend, et pourquoi ce n'est pas l'optimalité

### Rossit, Vigo, Tohmé & Frutos (2019) — *Visual attractiveness in routing problems: A review*

*Computers & Operations Research* 103:13–34. DOI [10.1016/j.cor.2018.10.012](https://doi.org/10.1016/j.cor.2018.10.012).
Non conservé — accès restreint.

**Ce que l'article établit.** Une tournée « attirante » a trois propriétés :
**compacité** (les points d'une tournée sont proches), **non-chevauchement** (les
tournées ne se croisent pas), **faible complexité**. Ce sont des critères
d'**acceptation par les opérateurs**, explicitement **non déductibles de l'optimalité
en coût**, et explicitement subjectifs.

**Ce que cela implique ici.** L'attente « chaque coursier fait une zone propre » est
légitime et documentée — mais c'est un **objectif distinct** du coût, pas un symptôme
de mauvaise résolution. Les deux se traitent comme un problème bi-objectif.

### Rocha, Aloise, Aloise & Contardo (2022) — *Visual attractiveness in vehicle routing via bi-objective optimization*

*Computers & Operations Research* 137:105507. DOI [10.1016/j.cor.2021.105507](https://doi.org/10.1016/j.cor.2021.105507).
Libre accès conservé : [`articles/2022-rocha-attractivite-visuelle.pdf`](articles/2022-rocha-attractivite-visuelle.pdf) (PolyPublie).

**Ce que l'article établit.** Ils comptent les croisements entre tournées distinctes
(métrique due à Matis, 2008) sur les solutions **de coût minimal** des instances CVRP
de référence. La plupart en comportent, strictement positifs.

**Autrement dit : les solutions optimales se croisent, couramment.**

**Ce que cela implique ici.** Le croisement entre deux véhicules n'est **pas** une
preuve de sous-optimalité. `optimizer/audit.py` le présente correctement comme un
indice, et cette distinction vient de là.

---

## Non-croisement : un théorème, mais pour un seul véhicule

### Flood (1956) — *The Traveling-Salesman Problem*

*Operations Research* 4(1):61–75. DOI [10.1287/opre.4.1.61](https://doi.org/10.1287/opre.4.1.61).
Non conservé — accès restreint.

**Ce que l'article établit.** Une tournée euclidienne optimale ne se recoupe jamais.
La démonstration tient en une ligne et constitue tout le contenu du 2-opt : si les
arêtes `(a,b)` et `(c,d)` se croisent, les remplacer par `(a,c)` et `(b,d)` raccourcit
strictement, par inégalité triangulaire.

**La limite, qui compte pour la suite.** La preuve suppose l'inégalité triangulaire
**stricte le long de segments droits**, c'est-à-dire une métrique euclidienne. Elle ne
vaut plus sur un réseau routier.

**Ce que cela implique ici.** `optimizer/audit.py` qualifie un croisement interne de
« preuve de sous-optimalité ». C'est exact **aujourd'hui**, puisque le solveur minimise
des distances euclidiennes. Le jour où la matrice viendra d'OSRM (issue #13), cette
affirmation devra être affaiblie — la mise en garde est déjà écrite dans le module.

À plusieurs véhicules, le mouvement qui décroise (`2-opt*`) déplace de la charge entre
les deux tournées : il peut violer la capacité ou une fenêtre de temps. Quand il est
infaisable, le croisement survit jusqu'à l'optimum. Et sous min-max, décroiser peut
raccourcir la distance totale tout en **allongeant la plus longue tournée** — une
solution qui se croise peut donc être strictement optimale.

---

## Min-max contre min-somme

### Bertazzi, Golden & Wang (2015) — *Min–max vs. min–sum vehicle routing: A worst-case analysis*

*European Journal of Operational Research* 240(2):372–381. DOI [10.1016/j.ejor.2014.07.025](https://doi.org/10.1016/j.ejor.2014.07.025).
Non conservé — accès restreint.

**Ce que l'article établit.** L'écart en pire cas entre une solution min-max et une
solution min-somme, en distance totale.

**Ce que cela implique ici.** Notre critère d'évaluation externe classe les clients
servis, puis le makespan, puis les kilomètres : il fait donc le choix du min-max. Ce
choix a un prix, et cet article en donne la borne.

**La borne, dans les deux sens**, avec `k` le nombre de véhicules :

- la distance totale du min-max vaut **au plus `k` fois** celle du min-somme — ce que
  l'équilibrage coûte en kilomètres ;
- la plus longue tournée du min-somme vaut **au plus `k` fois** celle du min-max — ce
  que coûte, en makespan, le fait de ne pas équilibrer.

Les deux bornes sont atteintes. À trois coursiers, cela plafonne l'écart à 3× dans
chaque sens : c'est une borne de pire cas, pas une prévision.

**Les moyennes empiriques**, chez Matl et al. (2018, 2019), sont bien plus douces que
la borne :

| relevé | valeur |
|---|---|
| déséquilibre d'une solution optimale en coût | la plus longue tournée fait ~2× la plus courte |
| réduire l'écart de ~40 % | coûte ~2 % de coût total |
| solutions efficaces à moins de 10 % de l'optimum | ~40 % d'entre elles |
| équilibre quasi optimal | atteignable à 5–10 % du coût optimal |

**Ce que nous avons mesuré.** Retirer le coût d'étalement en distance donne −5 % de
kilomètres, +220 s de makespan, et fait passer l'écart de charge entre coursiers de
4,5 à 7,5 clients. Le retirer entièrement porte cet écart à **35 clients** — un
coursier fait presque tout, ce qui rejoint le « deux fois plus long » de Matl et al.

**Nos 5 % tombent donc exactement dans la bande publiée** (5 à 10 %). Le chevauchement
observé n'est pas une anomalie du modèle : c'est le prix normal de l'équilibrage, et
il est payé au tarif que la littérature annonce.

---

## Instances de référence

### Solomon (1987) — *Algorithms for the vehicle routing and scheduling problems with time window constraints*

*Operations Research* 35(2):254–265. DOI [10.1287/opre.35.2.254](https://doi.org/10.1287/opre.35.2.254).

Les jeux C1/C2, R1/R2, RC1/RC2 sont la référence pour le CVRPTW. Ils servent ici à
répondre à la seule question qui vaille sur la qualité d'un solveur : **à quelle
distance des optima publiés se situe-t-il ?** Tant qu'on ne compare le solveur qu'à
lui-même, on ne mesure rien.

Le travail correspondant est dans `benchmarks/`.

---

## Ce que la littérature n'a pas tranché pour nous

- **Le chevauchement observé est-il géométrique ou temporel ?** Une carte dessine une
  solution indexée par le temps comme si tout était simultané. Deux passages du même
  dépôt à deux moments différents se superposent forcément sur une image fixe. Une
  partie de ce qu'on prend pour un conflit de territoire n'en est peut-être pas un.
  Aucune source trouvée là-dessus ; à mesurer sur des tournées contemporaines.
- **Le makespan avant la distance est-il défendable en livraison du dernier
  kilomètre**, ou la convention est-elle la distance totale avec l'équilibrage en
  second ? Question ouverte, elle décide de notre critère d'évaluation.
