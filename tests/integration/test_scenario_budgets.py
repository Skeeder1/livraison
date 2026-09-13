"""
Quatre tournées d'une seule recherche : la propriété de préfixe, vérifiée.

Une recherche de 15 s est le préfixe exact d'une recherche de 60 s sur la même
instance. On relève donc l'ordre des tournées à chaque amélioration et on
reconstruit l'état à chaque budget — et l'objectif de ce que l'on reconstruit
doit être celui qui a été relevé.
"""
import tempfile
from pathlib import Path

import pytest

from optimizer.scenario import solve_scenario_at_budgets

PARAMS = {"customers": 20, "vehicles": 2, "hubs": 1, "capacity": 5,
          "time_windows_binding": False, "seed": 42}


@pytest.fixture(scope="module")
def quatre():
    tours, curve = solve_scenario_at_budgets(
        PARAMS, workdir=Path(tempfile.mkdtemp()), budgets=(2, 4, 8), road_matrix=False,
    )
    return tours, curve


def _objectif_au_budget(curve, budget_s):
    """L'objectif du dernier point de la courbe à ou avant le budget."""
    points = [o for t, o in curve if t <= budget_s * 1000]
    return points[-1] if points else None


def test_la_tournee_finale_porte_l_objectif_final_de_la_courbe(quatre):
    """À budget maximal la tournée stockée est la solution finale du solveur :
    son objectif est le dernier point de la courbe."""
    tours, curve = quatre
    assert tours[8]["meta"]["objective"] == curve[-1][1]


def test_une_tournee_reconstruite_reproduit_exactement_son_instantane(quatre):
    """La reconstruction par `ReadAssignmentFromRoutes` doit rendre l'objectif
    relevé au moment de l'instantané, à l'unité près — c'est ce qui rend
    honnête « la tournée à 4 s » : ce n'est pas une approximation."""
    tours, curve = quatre
    for budget in (2, 4):
        if tours[budget] is None:
            continue
        assert tours[budget]["meta"]["objective"] == _objectif_au_budget(curve, budget)


def test_la_courbe_est_strictement_decroissante(quatre):
    _, curve = quatre
    objectifs = [o for _, o in curve]
    assert objectifs == sorted(objectifs, reverse=True)
    assert len(set(objectifs)) == len(objectifs), "chaque point est une amélioration"


def test_la_qualite_ne_regresse_pas_avec_le_budget(quatre):
    tours, _ = quatre
    km = [tours[b]["stats"]["roadKm"] for b in (2, 4, 8) if tours[b]]
    assert km == sorted(km, reverse=True)


def test_chaque_budget_porte_son_propre_meta(quatre):
    tours, _ = quatre
    for b, doc in tours.items():
        if doc:
            assert doc["meta"]["budgetSeconds"] == b
