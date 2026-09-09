"""Primitives géométriques de l'audit de qualité.

Ces fonctions décident si une tournée « a l'air intelligente ». Une erreur de
signe dans le test d'orientation ferait passer des croisements inaperçus, ou en
inventerait à chaque virage : d'où des cas construits à la main, dont on connaît
la réponse sans calcul.
"""
import pytest

from optimizer.audit import (
    croisements_internes,
    deux_opt_restants,
    facteurs_de_detour,
    relocalisations_restantes,
    segments_se_croisent,
)


class TestSegmentsSeCroisent:
    def test_deux_segments_en_croix(self):
        # ── ARRANGE / ACT / ASSERT ─────────────────────────────────
        assert segments_se_croisent((0, 0), (2, 2), (0, 2), (2, 0))

    def test_deux_segments_paralleles(self):
        assert not segments_se_croisent((0, 0), (2, 0), (0, 1), (2, 1))

    def test_segments_disjoints(self):
        assert not segments_se_croisent((0, 0), (1, 1), (5, 5), (6, 6))

    def test_une_extremite_partagee_n_est_pas_un_croisement(self):
        """Deux segments consécutifs d'une tournée partagent toujours un point.

        Les compter croiserait à chaque arrêt et noierait les vrais défauts.
        """
        assert not segments_se_croisent((0, 0), (1, 1), (1, 1), (2, 0))

    def test_contact_tangent_non_compte(self):
        """Un sommet posé sur un segment n'est pas un croisement franc."""
        assert not segments_se_croisent((0, 0), (2, 0), (1, 0), (1, 1))


class TestCroisementsInternes:
    def test_un_carre_ne_se_recoupe_pas(self):
        carre = [(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]
        assert croisements_internes(carre) == []

    def test_un_noeud_papillon_se_recoupe(self):
        """L'ordre 0→2→1→3 croise : c'est la signature d'un 2-opt manqué."""
        papillon = [(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)]
        assert len(croisements_internes(papillon)) >= 1

    def test_une_tournee_trop_courte_ne_croise_rien(self):
        assert croisements_internes([(0, 0), (1, 1)]) == []


class TestMouvementsRestants:
    def test_un_trace_optimal_ne_laisse_aucun_2_opt(self):
        """Quatre points en carré, parcourus dans l'ordre : rien à gagner."""
        carre = [(48.85, 2.35), (48.86, 2.35), (48.86, 2.36), (48.85, 2.36), (48.85, 2.35)]
        nombre, gain = deux_opt_restants(carre)
        assert nombre == 0
        assert gain == pytest.approx(0.0)

    def test_un_croisement_laisse_un_2_opt_ameliorant(self):
        croise = [(48.85, 2.35), (48.86, 2.36), (48.86, 2.35), (48.85, 2.36), (48.85, 2.35)]
        nombre, gain = deux_opt_restants(croise)
        assert nombre >= 1
        assert gain > 0

    def test_un_detour_evident_se_relocalise(self):
        """Un arrêt inséré loin de sa place se déplace avec gain."""
        trace = [(48.85, 2.35), (48.90, 2.35), (48.851, 2.351), (48.852, 2.352), (48.85, 2.35)]
        nombre, gain = relocalisations_restantes(trace)
        assert nombre >= 1
        assert gain > 0


class TestFacteursDeDetour:
    def test_un_arret_sur_le_chemin_vaut_un(self):
        aligne = [(48.85, 2.35), (48.855, 2.35), (48.86, 2.35)]
        assert facteurs_de_detour(aligne)[0] == pytest.approx(1.0, abs=0.01)

    def test_un_arret_a_l_ecart_coute_davantage(self):
        ecarte = [(48.85, 2.35), (48.87, 2.40), (48.86, 2.35)]
        assert facteurs_de_detour(ecarte)[0] > 2.0
