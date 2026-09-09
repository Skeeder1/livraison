"""
Statistiques descriptives et tests non paramétriques, sans dépendance externe.

`scipy` n'est pas installé et le harnais n'a pas de raison de l'exiger : tout ce
dont le protocole a besoin tient en quelques dizaines de lignes.

Le choix des outils suit la nature des données :

* **médiane et intervalle interquartile**, jamais moyenne et écart-type. La
  distribution des résultats sur un jeu d'instances n'est pas symétrique, et une
  seule instance pathologique — un client isolé en bord de zone — déplace la
  moyenne sans rien dire du comportement typique ;
* **test des signes** sur les comparaisons appariées. Il ne suppose ni normalité
  ni échelle : il compte seulement combien de fois le candidat bat la référence
  sur la même instance. C'est exactement ce que le plan apparié produit, et
  c'est le test le plus faible qu'on puisse utiliser sans rien supposer de faux.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def median(values: Sequence[float]) -> float | None:
    """
    Médiane d'un échantillon.

    :param values: Échantillon, éventuellement vide
    :return: Médiane, ou `None` si l'échantillon est vide
    """
    data = sorted(values)
    if not data:
        return None
    middle = len(data) // 2
    if len(data) % 2:
        return float(data[middle])
    return (data[middle - 1] + data[middle]) / 2.0


def quantile(values: Sequence[float], q: float) -> float | None:
    """
    Quantile par interpolation linéaire entre ordres (convention « type 7 »).

    :param values: Échantillon
    :param q: Position dans [0, 1]
    :return: Quantile, ou `None` si l'échantillon est vide
    """
    data = sorted(values)
    if not data:
        return None
    if len(data) == 1:
        return float(data[0])
    position = q * (len(data) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(data[low])
    return data[low] + (data[high] - data[low]) * (position - low)


def iqr(values: Sequence[float]) -> tuple[float, float] | None:
    """
    Intervalle interquartile `(Q1, Q3)`.

    :param values: Échantillon
    :return: Couple `(Q1, Q3)`, ou `None` si l'échantillon est vide
    """
    q1, q3 = quantile(values, 0.25), quantile(values, 0.75)
    if q1 is None or q3 is None:
        return None
    return (q1, q3)


def binomial_tail(k: int, n: int) -> float:
    """
    `P(X >= k)` pour `X ~ Binomiale(n, 1/2)`.

    :param k: Nombre de succès
    :param n: Nombre d'épreuves
    :return: Probabilité de la queue supérieure
    """
    if n <= 0:
        return 1.0
    k = max(0, min(k, n))
    total = sum(math.comb(n, i) for i in range(k, n + 1))
    return total / (2.0**n)


def sign_test(wins: int, losses: int) -> float:
    """
    Test des signes bilatéral sur des comparaisons appariées.

    Les égalités sont **exclues** de l'épreuve, conformément à l'usage : elles ne
    portent aucune information de direction. Un facteur qui n'égalise que des
    résultats identiques produit donc `n = 0`, et la fonction rend 1.0 —
    « indiscernable », ce qui est la lecture correcte.

    :param wins: Instances où le candidat bat la référence
    :param losses: Instances où il perd
    :return: Valeur p bilatérale dans [0, 1]
    """
    n = wins + losses
    if n == 0:
        return 1.0
    upper = binomial_tail(wins, n)
    lower = binomial_tail(losses, n)
    return min(1.0, 2.0 * min(upper, lower))


def min_pairs_for_significance(alpha: float) -> int:
    """
    Plus petit nombre de comparaisons appariées pouvant atteindre le seuil `alpha`.

    Le test des signes est discret : avec `n` paires non nulles, la plus petite
    valeur p atteignable est `2 / 2**n`, obtenue quand toutes les comparaisons
    vont dans le même sens. En dessous d'un certain `n`, **aucun** résultat ne
    peut être déclaré significatif, si net soit-il — un balayage à cinq graines
    plafonne à p = 0,0625 et ne franchira jamais 0,05.

    C'est une propriété du plan d'expérience, pas des données. Un rapport qui ne
    la signale pas laisse croire à une absence d'effet là où il n'y a qu'un
    manque de puissance.

    :param alpha: Seuil de significativité visé
    :return: Nombre minimal de paires non nulles
    """
    n = 1
    while 2.0 / (2.0**n) > alpha:
        n += 1
        if n > 60:  # garde-fou : alpha absurdement petit
            break
    return n


def average_ranks(scores_by_label: dict) -> dict:
    """
    Rang moyen de chaque étiquette, instance par instance.

    Pour chaque graine, les étiquettes sont classées du meilleur au moins bon et
    reçoivent un rang ; les ex æquo se partagent le rang moyen. La moyenne de ces
    rangs sur toutes les graines résume l'ordre d'un balayage sans dépendre de
    l'échelle des valeurs — un seul résultat aberrant ne peut pas la retourner.

    :param scores_by_label: `{étiquette: {graine: clé_comparable}}` ; les clés
        sont supposées « plus petit = mieux »
    :return: `{étiquette: rang moyen}` ; les étiquettes sans aucune graine
        commune sont absentes
    """
    labels = list(scores_by_label)
    if not labels:
        return {}

    common = set.intersection(*(set(scores_by_label[label]) for label in labels))
    if not common:
        return {}

    totals = dict.fromkeys(labels, 0.0)
    for seed in common:
        ordered = sorted(labels, key=lambda label: scores_by_label[label][seed])
        index = 0
        while index < len(ordered):
            stop = index
            while (
                stop + 1 < len(ordered)
                and scores_by_label[ordered[stop + 1]][seed] == scores_by_label[ordered[index]][seed]
            ):
                stop += 1
            shared = (index + stop) / 2.0 + 1.0
            for position in range(index, stop + 1):
                totals[ordered[position]] += shared
            index = stop + 1

    return {label: totals[label] / len(common) for label in labels}


def format_median_iqr(values: Sequence[float], digits: int = 1) -> str:
    """
    Formate `médiane [Q1 ; Q3]`.

    :param values: Échantillon
    :param digits: Décimales affichées
    :return: Texte, ou `—` si l'échantillon est vide
    """
    med = median(values)
    if med is None:
        return "—"
    bounds = iqr(values)
    assert bounds is not None
    return f"{med:.{digits}f} [{bounds[0]:.{digits}f} ; {bounds[1]:.{digits}f}]"


def spread(values: Iterable[float]) -> float:
    """
    Largeur de l'intervalle interquartile — la mesure de bruit du rapport.

    :param values: Échantillon
    :return: `Q3 − Q1`, ou 0.0 si l'échantillon est vide
    """
    data: list[float] = list(values)
    bounds = iqr(data)
    return 0.0 if bounds is None else bounds[1] - bounds[0]
