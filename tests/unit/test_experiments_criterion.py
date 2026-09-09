"""
Tests du critère externe d'évaluation.

Ce module est le pivot méthodologique du harnais : si l'ordre qu'il définit est
faux, toute la campagne mesure autre chose que ce qu'elle annonce. Les tests
vérifient donc l'ordre **lexicographique** lui-même, y compris dans les cas où
il contredit l'intuition — un client servi de plus l'emporte sur n'importe quel
gain de kilométrage.
"""
from __future__ import annotations

import math

import pytest

from experiments.criterion import (
    WORST_KEY,
    compare,
    criterion_key,
    format_key,
    is_better,
    paired_delta,
)


def row(served=45, horizon=7791, road_km=104.8, ok=True, **extra):
    """Fabrique une ligne de résultat minimale."""
    return {
        "ok": ok,
        "stats": {"customersServed": served, "horizon": horizon, "roadKm": road_km},
        **extra,
    }


class TestCriterionKey:
    def test_clients_servis_sont_niés_pour_être_minimisés(self):
        assert criterion_key(row(served=45))[0] == -45

    def test_makespan_et_kilomètres_sont_laissés_tels_quels(self):
        key = criterion_key(row(horizon=7791, road_km=104.8))
        assert key[1] == 7791
        assert key[2] == pytest.approx(104.8)

    def test_échec_reçoit_la_pire_clé(self):
        assert criterion_key(row(ok=False)) == WORST_KEY

    def test_statistique_manquante_vaut_échec_et_non_zéro(self):
        # Un zéro gagnerait sur le makespan et les kilomètres : une solution
        # illisible ne doit jamais remonter en tête du classement.
        incomplete = {"ok": True, "stats": {"customersServed": 45}}
        assert criterion_key(incomplete) == WORST_KEY

    def test_stats_absentes_valent_échec(self):
        assert criterion_key({"ok": True}) == WORST_KEY

    def test_clé_est_comparable_et_triable(self):
        rows = [
            row(served=44, horizon=1, road_km=1),
            row(served=45, horizon=9000, road_km=200),
            row(ok=False),
        ]
        best = sorted(rows, key=criterion_key)[0]
        assert best["stats"]["customersServed"] == 45


class TestOrdreLexicographique:
    def test_un_client_de_plus_bat_tout_gain_de_kilométrage(self):
        many_km = row(served=45, horizon=99999, road_km=9999)
        few_km = row(served=44, horizon=1, road_km=1)
        assert is_better(many_km, few_km)

    def test_à_service_égal_le_makespan_départage(self):
        assert is_better(row(horizon=7000, road_km=200), row(horizon=8000, road_km=100))

    def test_à_service_et_makespan_égaux_les_kilomètres_départagent(self):
        assert is_better(row(road_km=100.0), row(road_km=100.1))

    def test_lignes_identiques_sont_nulles(self):
        assert compare(row(), row()) == 0

    def test_compare_rend_les_trois_valeurs(self):
        assert compare(row(served=45), row(served=44)) == -1
        assert compare(row(served=44), row(served=45)) == 1

    def test_un_échec_perd_contre_toute_solution_même_mauvaise(self):
        assert is_better(row(served=0, horizon=10**9, road_km=10**9), row(ok=False))

    def test_deux_échecs_sont_nuls(self):
        assert compare(row(ok=False), row(ok=False)) == 0


class TestPairedDelta:
    def test_signe_négatif_signifie_candidat_meilleur(self):
        delta = paired_delta(row(horizon=7000, road_km=100), row(horizon=8000, road_km=110))
        assert delta is not None
        assert delta["horizon"] == -1000
        assert delta["roadKm"] == pytest.approx(-10.0)

    def test_clients_servis_restent_en_plus_grand_est_mieux(self):
        delta = paired_delta(row(served=45), row(served=43))
        assert delta is not None
        assert delta["customersServed"] == 2

    def test_échec_de_part_ou_d_autre_donne_none(self):
        assert paired_delta(row(ok=False), row()) is None
        assert paired_delta(row(), row(ok=False)) is None


class TestFormatKey:
    def test_réinverse_les_clients_servis(self):
        assert "45 servis" in format_key(criterion_key(row(served=45)))

    def test_échec_est_nommé(self):
        assert format_key(WORST_KEY) == "échec"

    def test_worst_key_est_bien_infinie(self):
        assert all(math.isinf(component) for component in WORST_KEY)
