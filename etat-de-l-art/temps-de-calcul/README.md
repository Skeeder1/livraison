# Combien de temps donner à la recherche ?

Trois revues de littérature, sources primaires lues, sur une question que le
projet posait mal : « quel est le temps de calcul optimal ? ». Elles se
complètent, et chacune corrige une hypothèse que le code portait.

| fichier | question | ce qui en sort |
|---|---|---|
| [1-critere-du-temps-optimal.md](1-critere-du-temps-optimal.md) | Qu'est-ce qu'un temps « optimal », formellement ? | Il n'existe qu'à **prix du temps explicite** : `t* = argmax_t [ −écart(t) − c·t ]` (Zilberstein 1996, Boddy & Dean 1994). Tout détecteur de coude (Kneedle, distance à la corde) est ce même calcul avec `c` fixé en silence à la pente de la corde — le coude dépend donc de la fenêtre de tracé, pas de l'algorithme. |
| [2-arret-des-solveurs-vrp.md](2-arret-des-solveurs-vrp.md) | Comment les solveurs de référence s'arrêtent-ils, et OR-Tools ? | HGS : 20 000 itérations sans amélioration ; PyVRP : `NoImprovement` ; GLS n'a « aucun signal naturel d'arrêt » selon ses auteurs. OR-Tools n'a pas de limite de stagnation native — `ImprovementSearchLimit` ne mesure pas cela — mais `FinishCurrentSearch()` depuis le rappel de solution la réalise, vérifié sur 9.15. |
| [3-prediction-du-temps.md](3-prediction-du-temps.md) | Peut-on prédire le temps sans exécuter ? | Oui, c'est une discipline (Hutter et al. 2014) : forêt aléatoire sur le log du temps, validée par validation croisée. Les transferts sont **qualitativement** plus coûteux — 6 à 20× de CPU chez Masson, Lehuédé & Péton — donc les hubs sont un facteur de premier rang, pas une correction. |

## Ce que cela change ici

La règle de budget par nombre de clients répondait à « combien de temps pour que
trois instances sur quatre soient à 5 % du meilleur ? » — une **garantie**, donc
longue (30 s à 45 clients). La question du visiteur est « quand attendre cesse-t-il
de payer ? » — un **rapport**, donc court. Appliqué aux 204 trajectoires mesurées,
avec `c = 0,2 %` de coût de tournée par seconde d'attente :

| instance | t* médian | règle précédente |
|---|---|---|
| 10 clients | 0,1 s | 2 s |
| 25 clients | 1,5 s | 20 s |
| 25 clients, 1 hub | 14 s | 20 s |
| 45 clients | 5 s | 30 s |
| 60 clients | 8 s | 45 s |

Les deux sont légitimes ; elles ne servent pas le même usage. Le bouton « Auto »
doit afficher `t*`, et le dire avec son prix du temps.
