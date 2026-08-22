"""
Tests de la lecture de solution (`optimizer.trace`).

Deux points sont vérifiés ici sans faire tourner le solveur :
la sérialisation des scalaires NumPy, et la mise à zéro des charges des
véhicules fictifs. Le calcul des attentes exige une vraie solution : il est
couvert par `tests/integration/test_scenario.py`.
"""
import numpy as np

from optimizer.trace import compute_cumulative_loads, convert_to_json_serializable


class TestConvertToJsonSerializable:
    """Les scalaires NumPy traversent tout le pipeline et cassent json.dumps."""

    def test_convertit_les_scalaires_numpy(self):
        # ── ARRANGE ────────────────────────────────────────────────
        payload = {'demande': np.int64(3), 'distance': np.float64(1.5)}

        # ── ACT ────────────────────────────────────────────────────
        result = convert_to_json_serializable(payload)

        # ── ASSERT ─────────────────────────────────────────────────
        assert result == {'demande': 3, 'distance': 1.5}
        assert isinstance(result['demande'], int)
        assert isinstance(result['distance'], float)

    def test_descend_dans_les_structures_imbriquees(self):
        # ── ARRANGE ────────────────────────────────────────────────
        payload = {'routes': [[np.int64(0), np.int64(4)]], 'fenetre': (np.int64(0), np.int64(86400))}

        # ── ACT ────────────────────────────────────────────────────
        result = convert_to_json_serializable(payload)

        # ── ASSERT ─────────────────────────────────────────────────
        assert result == {'routes': [[0, 4]], 'fenetre': (0, 86400)}
        assert all(isinstance(node, int) for node in result['routes'][0])

    def test_laisse_intacts_les_types_natifs(self):
        # ── ACT ────────────────────────────────────────────────────
        result = convert_to_json_serializable({'a': 1, 'b': 'texte', 'c': None, 'd': 2.5})

        # ── ASSERT ─────────────────────────────────────────────────
        assert result == {'a': 1, 'b': 'texte', 'c': None, 'd': 2.5}


class TestComputeCumulativeLoads:
    """Charges par étape, véhicules fictifs compris."""

    def test_met_a_zero_les_vehicules_fictifs(self):
        # ── ARRANGE ────────────────────────────────────────────────
        # Deux véhicules réels (capacités connues) et un fictif, ajouté par le
        # solveur pour matérialiser un transfert en hub.
        data = {'num_vehicles': 3, 'vehicle_capacities': [10, 10]}
        results = {
            'per_livreur': {
                'routes': [[0, 1, 0], [0, 2, 0], [0, 5, 0]],
                'current_loads': [[10, 9, 9], [10, 9, 9], [0, 0, 0]],
            }
        }

        # ── ACT ────────────────────────────────────────────────────
        loads = compute_cumulative_loads(data, results)

        # ── ASSERT ─────────────────────────────────────────────────
        assert loads[0] == [10, 9, 9]
        assert loads[1] == [10, 9, 9]
        assert loads[2] == [0, 0, 0], "un véhicule fictif ne transporte rien"

    def test_reste_aligne_sur_la_longueur_des_routes(self):
        # ── ARRANGE ────────────────────────────────────────────────
        data = {'num_vehicles': 2, 'vehicle_capacities': [10]}
        results = {
            'per_livreur': {
                'routes': [[0, 1, 2, 0], [0, 7, 0]],
                'current_loads': [[10, 9, 8, 8], [0, 0, 0]],
            }
        }

        # ── ACT ────────────────────────────────────────────────────
        loads = compute_cumulative_loads(data, results)

        # ── ASSERT ─────────────────────────────────────────────────
        assert [len(row) for row in loads] == [4, 3], (
            "l'affichage lit charge et position au même indice"
        )
