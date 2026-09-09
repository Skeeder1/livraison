"""
Tests des statistiques et des verdicts d'analyse.

C'est là que se fabriquent les conclusions publiées : une erreur ici ne fait pas
planter la campagne, elle lui fait dire le contraire de ce qu'elle a mesuré.
Deux propriétés sont vérifiées en priorité :

* un facteur **sans effet** doit être déclaré sans effet, et la recommandation
  doit alors **garder la valeur livrée** — ne pas déplacer un réglage sur la foi
  d'une différence de médiane qu'on ne sait pas distinguer du hasard ;
* un facteur qui gagne sur toutes les graines appariées doit être détecté.
"""
from __future__ import annotations

import pytest

from experiments import stats
from experiments.analyse import analyse_factor, build_report, group, recommend


def row(config_key, seed, served=45, horizon=7791, road_km=104.8, *, baseline=False,
        memberships=(), factors=None, scenario=None, ok=True):
    return {
        "schema": 1,
        "config_key": config_key,
        "config_label": config_key,
        "is_baseline": baseline,
        "memberships": [list(m) for m in memberships],
        "factors": factors or {"TIME_SPAN_COEFFICIENT": 200},
        "scenario": scenario or {"customers": 45, "hubs": 0},
        "budget_seconds": 10,
        "seed": seed,
        "ok": ok,
        "stats": {"customersServed": served, "horizon": horizon, "roadKm": road_km},
    }


class TestMedianEtQuantiles:
    def test_médiane_impaire(self):
        assert stats.median([3, 1, 2]) == 2

    def test_médiane_paire_interpole(self):
        assert stats.median([1, 2, 3, 4]) == 2.5

    def test_échantillon_vide_donne_none(self):
        assert stats.median([]) is None
        assert stats.quantile([], 0.5) is None
        assert stats.iqr([]) is None

    def test_iqr_encadre_la_médiane(self):
        values = list(range(1, 11))
        q1, q3 = stats.iqr(values)
        assert q1 <= stats.median(values) <= q3

    def test_spread_est_la_largeur_interquartile(self):
        assert stats.spread([1, 2, 3, 4, 5]) == pytest.approx(2.0)

    def test_format_médiane_iqr(self):
        # [1..5] : médiane 3, Q1 = 2, Q3 = 4 en convention « type 7 ».
        assert stats.format_median_iqr([1, 2, 3, 4, 5], 0) == "3 [2 ; 4]"

    def test_format_échantillon_vide(self):
        assert stats.format_median_iqr([]) == "—"


class TestSignTest:
    def test_égalité_parfaite_n_est_pas_significative(self):
        assert stats.sign_test(5, 5) == 1.0

    def test_que_des_égalités_donne_un(self):
        # 30 graines toutes nulles : le facteur ne change rien du tout.
        assert stats.sign_test(0, 0) == 1.0

    def test_dix_victoires_sur_dix_est_significatif(self):
        assert stats.sign_test(10, 0) == pytest.approx(2 / 1024)

    def test_est_symétrique(self):
        assert stats.sign_test(9, 1) == stats.sign_test(1, 9)

    def test_reste_borné_par_un(self):
        for wins in range(6):
            assert 0.0 <= stats.sign_test(wins, 5 - wins) <= 1.0

    def test_six_contre_quatre_n_est_pas_significatif(self):
        assert stats.sign_test(6, 4) > 0.05

    def test_cinq_paires_ne_peuvent_jamais_être_significatives(self):
        # 2 / 2**5 = 0,0625 : le plancher du test dépasse le seuil usuel.
        assert stats.sign_test(5, 0) == pytest.approx(0.0625)
        assert stats.sign_test(5, 0) > 0.05


class TestPuissance:
    def test_six_paires_suffisent_au_seuil_usuel(self):
        assert stats.min_pairs_for_significance(0.05) == 6

    def test_un_seuil_plus_exigeant_demande_plus_de_paires(self):
        assert stats.min_pairs_for_significance(0.01) > stats.min_pairs_for_significance(0.05)

    def test_le_plancher_du_test_est_bien_atteint(self):
        n = stats.min_pairs_for_significance(0.05)
        assert stats.sign_test(n, 0) <= 0.05
        assert stats.sign_test(n - 1, 0) > 0.05


class TestAverageRanks:
    def test_le_meilleur_a_le_rang_un(self):
        ranks = stats.average_ranks({"a": {1: (0, 0, 0)}, "b": {1: (0, 0, 1)}})
        assert ranks["a"] == 1.0
        assert ranks["b"] == 2.0

    def test_les_ex_æquo_partagent_le_rang_moyen(self):
        ranks = stats.average_ranks({"a": {1: (0, 0, 0)}, "b": {1: (0, 0, 0)}})
        assert ranks["a"] == ranks["b"] == 1.5

    def test_seules_les_graines_communes_comptent(self):
        ranks = stats.average_ranks({"a": {1: (0,), 2: (0,)}, "b": {1: (1,)}})
        assert ranks["a"] == 1.0 and ranks["b"] == 2.0

    def test_aucune_graine_commune_ne_produit_rien(self):
        assert stats.average_ranks({"a": {1: (0,)}, "b": {2: (0,)}}) == {}

    def test_dictionnaire_vide(self):
        assert stats.average_ranks({}) == {}


class TestAnalyseFactor:
    def _rows(self, candidate_horizon):
        """Référence à 200, candidat à 800, sur cinq graines."""
        rows = []
        for seed in range(5):
            rows.append(row("base", seed, horizon=7800, baseline=True,
                            memberships=[("TIME_SPAN_COEFFICIENT", 200)]))
            rows.append(row("cand", seed, horizon=candidate_horizon,
                            factors={"TIME_SPAN_COEFFICIENT": 800},
                            memberships=[("TIME_SPAN_COEFFICIENT", 800)]))
        return rows

    def test_compte_les_victoires_appariées(self):
        entry = group(self._rows(7000))["customers=45, hubs=0"]
        summary = analyse_factor(entry, "TIME_SPAN_COEFFICIENT")
        candidate = next(p for p in summary["points"] if p["value"] == 800)
        assert (candidate["wins"], candidate["losses"], candidate["ties"]) == (5, 0, 0)

    def test_compte_les_défaites_appariées(self):
        entry = group(self._rows(9000))["customers=45, hubs=0"]
        summary = analyse_factor(entry, "TIME_SPAN_COEFFICIENT")
        candidate = next(p for p in summary["points"] if p["value"] == 800)
        assert (candidate["wins"], candidate["losses"]) == (0, 5)

    def test_résultats_identiques_donnent_des_nuls(self):
        entry = group(self._rows(7800))["customers=45, hubs=0"]
        summary = analyse_factor(entry, "TIME_SPAN_COEFFICIENT")
        candidate = next(p for p in summary["points"] if p["value"] == 800)
        assert candidate["ties"] == 5
        assert candidate["p_value"] == 1.0

    def test_la_référence_est_marquée_comme_telle(self):
        entry = group(self._rows(7000))["customers=45, hubs=0"]
        summary = analyse_factor(entry, "TIME_SPAN_COEFFICIENT")
        assert [p["value"] for p in summary["points"] if p["is_baseline"]] == [200]

    def test_écart_apparié_médian_est_signé_correctement(self):
        entry = group(self._rows(7000))["customers=45, hubs=0"]
        summary = analyse_factor(entry, "TIME_SPAN_COEFFICIENT")
        candidate = next(p for p in summary["points"] if p["value"] == 800)
        assert candidate["delta_horizon"] == -800  # négatif = meilleur

    def test_un_seul_point_n_est_pas_analysable(self):
        rows = [row("base", 0, baseline=True, memberships=[("X", 1)])]
        entry = group(rows)["customers=45, hubs=0"]
        assert analyse_factor(entry, "X") is None

    def test_seules_les_graines_communes_sont_appariées(self):
        rows = self._rows(7000)
        rows = [r for r in rows if not (r["config_key"] == "cand" and r["seed"] >= 3)]
        entry = group(rows)["customers=45, hubs=0"]
        summary = analyse_factor(entry, "TIME_SPAN_COEFFICIENT")
        candidate = next(p for p in summary["points"] if p["value"] == 800)
        assert candidate["seeds"] == 3


class TestRecommend:
    def _summary(self, wins, losses, ties, p_value, delta_horizon=-500.0):
        return {
            "factor": "F",
            "baseline_value": 200,
            "noise_horizon": 0.0,
            "noise_roadkm": 0.0,
            "points": [
                {"value": 200, "is_baseline": True, "wins": 0, "losses": 0, "ties": 0,
                 "p_value": 1.0, "delta_served": 0.0, "delta_horizon": 0.0,
                 "delta_roadkm": 0.0, "rank": 1.5},
                {"value": 800, "is_baseline": False, "wins": wins, "losses": losses,
                 "ties": ties, "p_value": p_value, "delta_served": 0.0,
                 "delta_horizon": delta_horizon, "delta_roadkm": 0.0, "rank": 1.5},
            ],
        }

    def test_sans_significativité_on_garde_la_référence(self):
        reco = recommend(self._summary(wins=6, losses=4, ties=0, p_value=0.75))
        assert reco["value"] == 200
        assert reco["significant"] is False
        assert "hasard" in reco["reason"]

    def test_un_plan_trop_petit_est_dit_inconclusif_et_non_sans_effet(self):
        # 5 paires : le test des signes plafonne à p = 0,0625 et ne peut pas
        # franchir 0,05. Annoncer « aucun effet » serait un mensonge par omission.
        reco = recommend(self._summary(wins=5, losses=0, ties=0, p_value=0.0625))
        assert reco["value"] == 200
        assert reco["significant"] is False
        assert "INCONCLUSIF" in reco["reason"]
        assert "puissance" in reco["reason"]

    def test_un_gain_significatif_déplace_la_recommandation(self):
        reco = recommend(self._summary(wins=10, losses=0, ties=0, p_value=0.002))
        assert reco["value"] == 800
        assert reco["significant"] is True

    def test_une_perte_significative_ne_déplace_rien(self):
        # p faible mais dans le mauvais sens : le candidat perd.
        reco = recommend(self._summary(wins=0, losses=10, ties=0, p_value=0.002))
        assert reco["value"] == 200
        assert reco["significant"] is False

    def test_facteur_totalement_inerte_garde_la_référence(self):
        reco = recommend(self._summary(wins=0, losses=0, ties=10, p_value=1.0))
        assert reco["value"] == 200
        assert reco["significant"] is False


class TestBuildReport:
    def test_le_rapport_énonce_le_critère(self, tmp_path):
        rows = [row("base", 0, baseline=True, memberships=[("F", 200)]),
                row("cand", 0, memberships=[("F", 800)], factors={"F": 800})]
        report, machine = build_report(rows, tmp_path / "r.jsonl")
        assert "clients servis" in report and "makespan" in report
        assert "SYNTHÈSE" in report
        assert machine["scenarios"]

    def test_le_rapport_signale_un_mélange_de_budgets(self, tmp_path):
        a = row("base", 0, baseline=True, memberships=[("F", 200)])
        b = row("cand", 0, memberships=[("F", 800)], factors={"F": 800})
        b["budget_seconds"] = 30
        report, _ = build_report([a, b], tmp_path / "r.jsonl")
        assert "plusieurs budgets" in report

    def test_le_rapport_signale_un_plan_sous_dimensionné(self, tmp_path):
        rows = [row("base", 0, baseline=True, memberships=[("F", 200)]),
                row("cand", 0, memberships=[("F", 800)], factors={"F": 800})]
        report, _ = build_report(rows, tmp_path / "r.jsonl")
        assert "PUISSANCE INSUFFISANTE" in report

    def test_le_rapport_compte_les_échecs(self, tmp_path):
        failed = row("cand", 0, memberships=[("F", 800)], factors={"F": 800}, ok=False)
        failed["error"] = "NoSolutionError: rien trouvé"
        rows = [row("base", 0, baseline=True, memberships=[("F", 200)]), failed]
        report, _ = build_report(rows, tmp_path / "r.jsonl")
        assert "ÉCHECS (1)" in report
        assert "NoSolutionError" in report
