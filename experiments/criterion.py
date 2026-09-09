"""
Le critère externe d'évaluation. **Fixé à l'avance, jamais réajusté.**

------------------------------------------------------------------------------
LA RÈGLE MÉTHODOLOGIQUE CENTRALE
------------------------------------------------------------------------------

**On ne peut pas régler une pénalité contre l'objectif qu'elle définit.**

Demander « quelle pénalité d'abandon minimise l'objectif du solveur ? » a pour
réponse « la plus faible » : dès qu'abandonner un client devient bon marché,
l'objectif chute, et il chute d'autant plus que le bouton descend. L'objectif
bouge quand le bouton bouge ; il ne peut donc pas servir de mètre.

Toute configuration est par conséquent jugée ici sur un critère **extérieur au
solveur**, arrêté avant la première mesure et jamais renégocié ensuite :

    1. clients servis          — MAXIMISER   (`tour['stats']['customersServed']`)
    2. makespan                — MINIMISER   (`tour['horizon']`)
    3. kilomètres réels        — MINIMISER   (`tour['stats']['roadKm']`)

Ordre **lexicographique** : un client servi de plus l'emporte sur n'importe quel
gain de makespan, et un makespan plus court l'emporte sur n'importe quel gain de
kilométrage. Ce n'est pas une pondération, c'est une hiérarchie.

Si vous modifiez ce module, vous invalidez toutes les mesures déjà collectées.
La seule modification légitime est un changement de contrat métier, discuté et
documenté, suivi d'une nouvelle campagne complète.
"""
from __future__ import annotations

import math
from typing import Any

#: Clé de tri d'une exécution qui n'a produit aucune solution. Pire que tout le
#: reste sur les trois composantes : un plantage ne doit jamais gagner.
WORST_KEY: tuple[float, float, float] = (math.inf, math.inf, math.inf)

#: Nom lisible de chaque composante, dans l'ordre lexicographique, avec le sens
#: de l'amélioration une fois la composante convertie en « plus petit = mieux ».
CRITERION_COMPONENTS = (
    ("customersServed", "clients servis", "max"),
    ("horizon", "makespan (s)", "min"),
    ("roadKm", "kilomètres", "min"),
)


def criterion_key(row: dict[str, Any]) -> tuple[float, float, float]:
    """
    Clé lexicographique comparable d'une ligne de résultat. **Plus petit = mieux.**

    Les trois composantes sont ramenées à une convention unique de minimisation :
    le nombre de clients servis est nié, les deux autres sont laissées telles
    quelles. Deux clés se comparent alors directement avec `<`, et une liste de
    lignes se trie avec `sorted(rows, key=criterion_key)`.

    :param row: Ligne de résultat produite par `experiments.runner`
    :return: `(-clients_servis, makespan, kilomètres)`, ou `WORST_KEY` si
        l'exécution a échoué ou si une statistique manque
    """
    if not row.get("ok"):
        return WORST_KEY

    stats = row.get("stats") or {}
    try:
        served = float(stats["customersServed"])
        horizon = float(stats["horizon"])
        road_km = float(stats["roadKm"])
    except (KeyError, TypeError, ValueError):
        # Une solution dont on ne sait pas lire les statistiques n'est pas une
        # solution exploitable : elle est traitée comme un échec, pas comme un
        # zéro (qui gagnerait sur le makespan et le kilométrage).
        return WORST_KEY

    return (-served, horizon, road_km)


def is_better(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """
    Vrai si `left` est strictement meilleure que `right` au sens du critère.

    :param left: Ligne de résultat
    :param right: Ligne de résultat
    :return: Vrai si `left` domine strictement `right`
    """
    return criterion_key(left) < criterion_key(right)


def compare(left: dict[str, Any], right: dict[str, Any]) -> int:
    """
    Compare deux lignes : `-1` si `left` est meilleure, `1` si pire, `0` si égales.

    :param left: Ligne de résultat
    :param right: Ligne de résultat
    :return: `-1`, `0` ou `1`
    """
    a, b = criterion_key(left), criterion_key(right)
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def format_key(key: tuple[float, float, float]) -> str:
    """
    Rend une clé de critère lisible, en réinversant le nombre de clients servis.

    :param key: Clé produite par `criterion_key`
    :return: Représentation courte, par exemple `45 servis / 7791 s / 104.8 km`
    """
    if key == WORST_KEY:
        return "échec"
    served, horizon, road_km = key
    return f"{-served:g} servis / {horizon:g} s / {road_km:g} km"


def describe() -> str:
    """
    Retourne l'énoncé du critère, pour l'en-tête des rapports.

    :return: Texte multiligne
    """
    return (
        "Critère externe (lexicographique, fixé à l'avance) :\n"
        "  1. clients servis  — MAXIMISER\n"
        "  2. makespan        — MINIMISER\n"
        "  3. kilomètres      — MINIMISER\n"
        "Aucune configuration n'est jugée sur l'objectif interne du solveur :\n"
        "une pénalité ne peut pas être réglée contre l'objectif qu'elle définit."
    )


def paired_delta(
    candidate: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, float] | None:
    """
    Écart apparié candidat − référence, composante par composante.

    Convention de signe : **négatif = le candidat est meilleur**, sur les trois
    composantes, puisque les clés sont toutes exprimées en minimisation.

    :param candidate: Ligne de la configuration testée
    :param baseline: Ligne de la configuration de référence, **même graine**
    :return: Dictionnaire des écarts, ou `None` si l'une des deux a échoué
    """
    a, b = criterion_key(candidate), criterion_key(baseline)
    if a == WORST_KEY or b == WORST_KEY:
        return None
    return {
        "customersServed": -(a[0] - b[0]),  # remis en « plus grand = mieux »
        "horizon": a[1] - b[1],
        "roadKm": a[2] - b[2],
    }
