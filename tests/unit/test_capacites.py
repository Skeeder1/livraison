"""
Tests des capacités de véhicule non entières.

Le solveur tronque les capacités (`setup_data_extensions` fait `int(cap)`), mais
le chargeur les laissait telles quelles. Une capacité de 13,7 était donc annoncée
à 13,7, contrainte à 13, et faisait planter le rapport console sur un format
entier. Le défaut restait invisible avec les données jouet : leur colonne de
capacités, entièrement à 10.0, est relue en int64 par pandas.

Le paramètre est désormais exposé par l'API de scénario, donc réglable de
l'extérieur : le cas doit être verrouillé.
"""
import io
from contextlib import redirect_stdout

import pytest

from optimizer.config import Config
from optimizer.create_toy_data import create_toy_data
from optimizer.data_loader import load_data
from optimizer.postprocessor import display_detailed_results


@pytest.fixture
def config_restauree():
    """Config porte des attributs de classe : les remettre après chaque test."""
    sauvegarde = {
        cle: getattr(Config, cle)
        for cle in ('NUM_CUSTOMERS', 'NUM_VEHICLES', 'NUM_HUBS',
                    'VEHICLE_CAPACITY_MIN', 'VEHICLE_CAPACITY_MAX')
    }
    yield
    Config.update(**sauvegarde)


class TestCapacitesEntieres:
    """Le chargeur aligne la capacité annoncée sur celle que le modèle applique."""

    def test_une_capacite_fractionnaire_est_ramenee_a_l_entier(self, tmp_path, config_restauree):
        # ── ARRANGE ────────────────────────────────────────────────
        Config.update(NUM_CUSTOMERS=4, NUM_VEHICLES=2, NUM_HUBS=1,
                      VEHICLE_CAPACITY_MIN=13.7, VEHICLE_CAPACITY_MAX=13.7)

        # ── ACT ────────────────────────────────────────────────────
        create_toy_data(str(tmp_path), verbose=False)
        data = load_data(str(tmp_path))

        # ── ASSERT ─────────────────────────────────────────────────
        assert all(isinstance(capacity, int) for capacity in data['vehicle_capacities']), (
            f"capacités non entières : {data['vehicle_capacities']}"
        )

    def test_la_capacite_annoncee_est_celle_que_le_solveur_applique(self, tmp_path, config_restauree):
        """`setup_data_extensions` tronque : le chargeur doit dire la même chose."""
        # ── ARRANGE ────────────────────────────────────────────────
        Config.update(NUM_CUSTOMERS=4, NUM_VEHICLES=1, NUM_HUBS=0,
                      VEHICLE_CAPACITY_MIN=9.0, VEHICLE_CAPACITY_MAX=9.0)

        # ── ACT ────────────────────────────────────────────────────
        create_toy_data(str(tmp_path), verbose=False)
        data = load_data(str(tmp_path))

        # ── ASSERT ─────────────────────────────────────────────────
        assert data['vehicle_capacities'] == [9]
        assert [int(c) for c in data['vehicle_capacities']] == data['vehicle_capacities']


class TestRapportConsole:
    """Le rapport détaillé ne doit pas dépendre du type des charges."""

    def test_supporte_des_charges_flottantes(self):
        """Défense en profondeur : un jeu de données externe peut en produire."""
        # ── ARRANGE ────────────────────────────────────────────────
        data = {
            'num_vehicles': 1,
            'num_customers': 2,
            'num_hubs': 0,
            'vehicle_capacities': [13.7],
            'demands': [0, 1.0, 1.0],
            'time_windows': [(0, 86400)] * 3,
        }

        # ── ACT ────────────────────────────────────────────────────
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            display_detailed_results(
                data,
                routes=[[0, 1, 2, 0]],
                estimated_times=[[0, 100, 200, 300]],
                current_loads=[[13.7, 12.7, 11.7, 11.7]],
                remaining_charges=[[0.0, 1.0, 2.0, 2.0]],
                total_distance=42,
                total_tardiness=0,
                activated_hubs=set(),
                load_imbalance_percentage=0.0,
                final_loads=[11.7],
                calc_time=0,
            )

        # ── ASSERT ─────────────────────────────────────────────────
        assert 'VÉHICULE 1' in sortie.getvalue(), (
            "le rapport doit s'afficher au lieu de lever ValueError sur le format entier"
        )
