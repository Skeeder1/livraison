"""
Tests du développement de grille.

Les points sensibles vérifiés ici :

* un point de balayage égal à la référence ne doit produire **qu'une seule**
  exécution, partagée — c'est ce qui rend l'appariement gratuit ;
* l'ordre doit être graine-majeur, pour qu'une campagne interrompue laisse un
  plan d'expérience complet sur les premières graines ;
* un facteur non branché sur `Config` doit faire **échouer** le développement, et
  non produire une courbe plate qu'on lirait comme une absence d'effet.
"""
from __future__ import annotations

import json

import pytest

from experiments.grid import (
    KNOWN_FACTORS,
    SEED_ORIGIN,
    GridError,
    config_key_for,
    default_seeds,
    expand,
    filter_pending,
    load_spec,
    log_range,
)

#: Facteurs disponibles simulés : ni `Config` ni le paquet optimiseur ne sont
#: chargés, les tests restent instantanés.
DEFAULTS = {
    "TIME_SPAN_COEFFICIENT": 200,
    "CAPACITY_SPAN_COEFFICIENT": 50,
    "DISTANCE_SPAN_COEFFICIENT": 30,
    "TRANSFER_PENALTY_METERS": 0,
    "DROP_CUSTOMER_PENALTY_METERS": 1_000_000,
}

SPEC = {
    "name": "test",
    "budget_seconds": 10,
    "scenario": {"customers": 45, "vehicles": 3, "capacity": 10},
    "scenario_variants": [{"hubs": 0}, {"hubs": 2}],
    "sweeps": [{"factor": "TIME_SPAN_COEFFICIENT", "values": [50, 200, 800]}],
}


class TestDefaultSeeds:
    def test_est_déterministe_et_croissant(self):
        assert default_seeds(3) == [SEED_ORIGIN, SEED_ORIGIN + 1, SEED_ORIGIN + 2]

    def test_allonger_conserve_le_préfixe(self):
        # Une campagne étendue de 5 à 10 graines doit pouvoir réutiliser les 5
        # premières, déjà mesurées.
        assert default_seeds(10)[:5] == default_seeds(5)

    def test_refuse_zéro_graine(self):
        with pytest.raises(GridError):
            default_seeds(0)


class TestLogRange:
    def test_bornes_incluses(self):
        values = log_range(10, 1000, 3)
        assert values[0] == 10
        assert values[-1] == 1000

    def test_espacement_géométrique(self):
        assert log_range(10, 1000, 3) == [10, 100, 1000]

    def test_dédoublonne_en_conservant_l_ordre(self):
        # Un arrondi entier sur une plage étroite écrase des points.
        values = log_range(1, 3, 6)
        assert values == sorted(set(values), key=values.index)

    def test_refuse_une_borne_nulle(self):
        with pytest.raises(GridError):
            log_range(0, 100, 3)

    def test_refuse_moins_de_deux_points(self):
        with pytest.raises(GridError):
            log_range(1, 100, 1)

    def test_arrondi_inconnu_est_refusé(self):
        with pytest.raises(GridError):
            log_range(1, 100, 3, "octal")


class TestExpand:
    def test_ordre_est_graine_majeur(self):
        campaign = expand(SPEC, [1, 2], defaults=DEFAULTS)
        seeds = [run.seed for run in campaign.runs]
        assert seeds == sorted(seeds)
        assert seeds[0] == 1 and seeds[-1] == 2
        # Toutes les configurations de la graine 1 précèdent celles de la 2.
        first_block = {run.config_key for run in campaign.runs if run.seed == 1}
        second_block = {run.config_key for run in campaign.runs if run.seed == 2}
        assert first_block == second_block

    def test_la_référence_passe_en_premier_de_chaque_bloc(self):
        campaign = expand(SPEC, [1, 2], defaults=DEFAULTS)
        for seed in (1, 2):
            block = [run for run in campaign.runs if run.seed == seed]
            assert block[0].is_baseline

    def test_point_égal_à_la_référence_est_fusionné(self):
        # 200 est la valeur livrée : il ne doit pas exister deux configurations
        # distinctes pour la référence et pour ce point de balayage.
        campaign = expand(SPEC, [1], defaults=DEFAULTS)
        # 2 variantes × (1 référence + 2 points non-référence) = 6.
        assert campaign.unique_configs == 6

    def test_le_point_fusionné_appartient_quand_même_au_balayage(self):
        campaign = expand(SPEC, [1], defaults=DEFAULTS)
        baseline = next(run for run in campaign.runs if run.is_baseline)
        assert ("TIME_SPAN_COEFFICIENT", 200) in baseline.memberships

    def test_chaque_exécution_porte_les_facteurs_complets(self):
        campaign = expand(SPEC, [1], defaults=DEFAULTS)
        for run in campaign.runs:
            assert set(run.factors) == set(DEFAULTS)

    def test_un_seul_facteur_s_écarte_de_la_référence(self):
        campaign = expand(SPEC, [1], defaults=DEFAULTS)
        for run in campaign.runs:
            differing = [name for name, value in run.factors.items() if DEFAULTS[name] != value]
            assert len(differing) <= 1, "phase 1 : un facteur à la fois"

    def test_les_variantes_de_scénario_héritent_du_scénario_commun(self):
        campaign = expand(SPEC, [1], defaults=DEFAULTS)
        for run in campaign.runs:
            assert run.scenario["customers"] == 45
        assert {run.scenario["hubs"] for run in campaign.runs} == {0, 2}

    def test_budget_de_la_ligne_de_commande_prime(self):
        campaign = expand(SPEC, [1], budget_seconds=42, defaults=DEFAULTS)
        assert campaign.budget_seconds == 42
        assert all(run.budget_seconds == 42 for run in campaign.runs)

    def test_baseline_factors_déplace_la_référence(self):
        spec = dict(SPEC, baseline_factors={"TIME_SPAN_COEFFICIENT": 50})
        campaign = expand(spec, [1], defaults=DEFAULTS)
        assert campaign.baseline_factors["TIME_SPAN_COEFFICIENT"] == 50
        # 50 devient le point fusionné, 200 et 800 sont désormais distincts.
        assert campaign.unique_configs == 6

    def test_refuse_un_facteur_inconnu(self):
        spec = dict(SPEC, sweeps=[{"factor": "INEXISTANT", "values": [1]}])
        with pytest.raises(GridError, match="Facteur inconnu"):
            expand(spec, [1], defaults=DEFAULTS)

    def test_refuse_un_facteur_connu_mais_non_branché(self):
        # Garde-fou : un facteur déclaré connu mais absent de Config ne doit pas
        # produire une courbe plate qu'on lirait comme « aucun effet ». Le cas
        # historique est le coût fixe par véhicule, longtemps écrit en dur dans
        # solver.py ; `DEFAULTS` simule ici sa disparition de Config.
        assert "VEHICLE_FIXED_COST_METERS" in KNOWN_FACTORS
        assert "VEHICLE_FIXED_COST_METERS" not in DEFAULTS
        spec = dict(SPEC, sweeps=[{"factor": "VEHICLE_FIXED_COST_METERS", "values": [10, 50]}])
        with pytest.raises(GridError, match="bouton débranché"):
            expand(spec, [1], defaults=DEFAULTS)

    def test_le_coût_fixe_par_véhicule_est_bien_branché_aujourd_hui(self):
        # Contrepartie du test précédent : sur le dépôt tel qu'il est, le facteur
        # doit exister. Si ce test tombe, le harnais mesurerait un bouton mort.
        from optimizer.config import Config

        assert hasattr(Config, "VEHICLE_FIXED_COST_METERS")
        spec = dict(SPEC, sweeps=[{"factor": "VEHICLE_FIXED_COST_METERS", "values": [10, 50]}])
        campaign = expand(spec, [1])
        assert campaign.unique_configs > len(campaign.scenario_variants)

    def test_refuse_une_clé_de_scénario_inconnue(self):
        spec = dict(SPEC, scenario={"customers": 45, "couleur": "bleu"})
        with pytest.raises(GridError, match="inconnues"):
            expand(spec, [1], defaults=DEFAULTS)

    def test_refuse_values_et_log_range_ensemble(self):
        spec = dict(
            SPEC,
            sweeps=[{
                "factor": "TIME_SPAN_COEFFICIENT",
                "values": [1],
                "log_range": {"from": 1, "to": 10, "points": 2},
            }],
        )
        with pytest.raises(GridError, match="exactement l'un"):
            expand(spec, [1], defaults=DEFAULTS)

    def test_refuse_un_plan_sans_graine(self):
        with pytest.raises(GridError):
            expand(SPEC, [], defaults=DEFAULTS)


class TestConfigKey:
    def test_est_stable_à_l_ordre_des_clés(self):
        a = config_key_for({"x": 1, "y": 2}, {"hubs": 0}, 10)
        b = config_key_for({"y": 2, "x": 1}, {"hubs": 0}, 10)
        assert a == b

    def test_change_avec_le_budget(self):
        a = config_key_for({"x": 1}, {"hubs": 0}, 10)
        b = config_key_for({"x": 1}, {"hubs": 0}, 30)
        assert a != b

    def test_change_avec_une_valeur_de_facteur(self):
        a = config_key_for({"x": 1}, {"hubs": 0}, 10)
        b = config_key_for({"x": 2}, {"hubs": 0}, 10)
        assert a != b


class TestFilterPending:
    def test_retire_les_couples_déjà_faits(self):
        campaign = expand(SPEC, [1, 2], defaults=DEFAULTS)
        done = {(campaign.runs[0].config_key, 1)}
        pending = filter_pending(campaign.runs, done)
        assert len(pending) == len(campaign.runs) - 1
        assert (campaign.runs[0].config_key, 1) not in {run.resume_key for run in pending}

    def test_une_même_config_sur_une_autre_graine_reste_à_faire(self):
        campaign = expand(SPEC, [1, 2], defaults=DEFAULTS)
        key = campaign.runs[0].config_key
        pending = filter_pending(campaign.runs, {(key, 1)})
        assert (key, 2) in {run.resume_key for run in pending}

    def test_conserve_l_ordre_d_origine(self):
        campaign = expand(SPEC, [1, 2], defaults=DEFAULTS)
        pending = filter_pending(campaign.runs, set())
        assert [run.resume_key for run in pending] == [run.resume_key for run in campaign.runs]

    def test_rien_à_faire_quand_tout_est_journalisé(self):
        campaign = expand(SPEC, [1], defaults=DEFAULTS)
        done = {run.resume_key for run in campaign.runs}
        assert filter_pending(campaign.runs, done) == []


class TestLoadSpec:
    def test_charge_un_fichier_valide(self, tmp_path):
        path = tmp_path / "grille.json"
        path.write_text(json.dumps(SPEC), encoding="utf-8")
        assert load_spec(path)["name"] == "test"

    def test_refuse_un_fichier_absent(self, tmp_path):
        with pytest.raises(GridError, match="introuvable"):
            load_spec(tmp_path / "absent.json")

    def test_refuse_un_json_invalide(self, tmp_path):
        path = tmp_path / "cassé.json"
        path.write_text("{ pas du json", encoding="utf-8")
        with pytest.raises(GridError, match="JSON invalide"):
            load_spec(path)

    def test_refuse_une_clé_de_premier_niveau_inconnue(self, tmp_path):
        path = tmp_path / "grille.json"
        path.write_text(json.dumps(dict(SPEC, sweep="typo")), encoding="utf-8")
        with pytest.raises(GridError, match="clés inconnues"):
            load_spec(path)


class TestGrillesLivrées:
    """
    Les grilles du dépôt doivent se développer sans erreur.

    Ce test lit les vraies valeurs de `optimizer.config.Config` — c'est
    précisément ce qu'il vérifie : que chaque facteur balayé y existe bel et
    bien. `config.py` n'importe rien, le test reste instantané.
    """

    @pytest.mark.parametrize("name", ["ofat.json", "pilote.json"])
    def test_la_grille_livrée_est_valide(self, name):
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "experiments" / "grids" / name
        campaign = expand(load_spec(path), default_seeds(2))
        assert campaign.runs
        assert campaign.unique_configs >= len(campaign.scenario_variants)

    def test_la_référence_de_la_grille_ofat_est_la_config_livrée(self):
        from pathlib import Path

        from optimizer.config import Config

        path = Path(__file__).resolve().parents[2] / "experiments" / "grids" / "ofat.json"
        campaign = expand(load_spec(path), default_seeds(1))
        for name, value in campaign.baseline_factors.items():
            assert value == getattr(Config, name), f"{name} s'écarte de Config"
