"""
Tests de l'indicateur de déséquilibre de charge.

Ces tests verrouillent la correction d'un bug d'inversion silencieuse : l'ancienne
implémentation calculait `max / min * 100` et renvoyait 0 lorsqu'un véhicule
terminait à vide — soit le score « parfaitement équilibré », en vert, pour le cas
le plus déséquilibré possible.
"""
import pytest

from optimizer.postprocessor import compute_load_imbalance


class TestComputeLoadImbalance:
    """Comportement de compute_load_imbalance."""

    def test_charges_identiques_renvoie_zero(self):
        # ── ARRANGE ────────────────────────────────────────────────
        final_loads = [10, 10, 10]

        # ── ACT ────────────────────────────────────────────────────
        result = compute_load_imbalance(final_loads)

        # ── ASSERT ─────────────────────────────────────────────────
        assert result == 0.0, (
            f"Un équilibre parfait doit valoir 0 %, obtenu {result} % "
            "(l'ancienne formule max/min renvoyait 100 %)"
        )

    def test_vehicule_termine_a_vide_signale_un_fort_desequilibre(self):
        """Le bug historique : min == 0 renvoyait 0 %, c'est-à-dire « parfait »."""
        # ── ARRANGE ────────────────────────────────────────────────
        # Deux véhicules à vide, un chargé : le pire déséquilibre possible.
        final_loads = [0, 0, 12]

        # ── ACT ────────────────────────────────────────────────────
        result = compute_load_imbalance(final_loads)

        # ── ASSERT ─────────────────────────────────────────────────
        assert result > 100.0, (
            f"Un véhicule à vide face à un véhicule chargé doit produire un fort "
            f"déséquilibre, obtenu {result} % (l'ancienne formule renvoyait 0 %)"
        )

    def test_desequilibre_croit_avec_l_ecart(self):
        # ── ARRANGE ────────────────────────────────────────────────
        proche = [9, 10, 11]
        eloigne = [2, 10, 18]

        # ── ACT ────────────────────────────────────────────────────
        imbalance_proche = compute_load_imbalance(proche)
        imbalance_eloigne = compute_load_imbalance(eloigne)

        # ── ASSERT ─────────────────────────────────────────────────
        assert imbalance_eloigne > imbalance_proche, (
            f"Un écart plus large doit donner un déséquilibre plus élevé : "
            f"{eloigne} → {imbalance_eloigne} % vs {proche} → {imbalance_proche} %"
        )

    @pytest.mark.parametrize(
        "final_loads, expected",
        [
            ([10, 10, 10], 0.0),      # équilibre parfait
            ([5, 10, 15], 100.0),     # étendue 10, moyenne 10
            ([0, 10, 20], 200.0),     # étendue 20, moyenne 10
            ([8], 0.0),               # un seul véhicule : rien à comparer
        ],
    )
    def test_valeurs_de_reference(self, final_loads, expected):
        # ── ACT ────────────────────────────────────────────────────
        result = compute_load_imbalance(final_loads)

        # ── ASSERT ─────────────────────────────────────────────────
        assert result == pytest.approx(expected), (
            f"Charges {final_loads} → attendu {expected} %, obtenu {result} %"
        )

    @pytest.mark.parametrize(
        "degenerate_input, label",
        [
            ([], "liste vide"),
            ([0, 0, 0], "aucune charge transportée"),
        ],
    )
    def test_cas_degeneres_renvoient_zero_sans_lever(self, degenerate_input, label):
        """Aucune charge à répartir : 0 % est légitime, et surtout pas de ZeroDivisionError."""
        # ── ACT ────────────────────────────────────────────────────
        result = compute_load_imbalance(degenerate_input)

        # ── ASSERT ─────────────────────────────────────────────────
        assert result == 0.0, f"{label} → attendu 0 %, obtenu {result} %"
