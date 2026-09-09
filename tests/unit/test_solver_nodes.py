"""
Tests de la numérotation des nœuds étendus.

`setup_data_extensions` ajoute des nœuds au modèle (rechargements au dépôt,
dépôts et retraits de hub, nœuds fictifs) et `create_base_node_mapping` dit, pour
chacun, à quelle position physique il correspond. C'est cette table qui indexe la
matrice des distances : une correspondance décalée fait calculer des trajets vers
le mauvais endroit, sans jamais lever d'erreur.

Ces tests verrouillent l'alignement entre les deux fonctions.
"""
from optimizer.config import Config
from optimizer.solver import create_base_node_mapping, setup_data_extensions, strip_hubs


def _donnees_minimales(num_customers=3, num_hubs=2, num_vehicles=2):
    """Jeu de données réduit, dans la forme que produit `load_data`."""
    depot = (48.8566, 2.3522)
    num_nodes = 1 + num_customers + num_hubs
    return {
        'depot': 0,
        'num_customers': num_customers,
        'num_hubs': num_hubs,
        'num_nodes': num_nodes,
        'num_vehicles': num_vehicles,
        'locations': [depot] + [(48.85 + 0.01 * i, 2.35) for i in range(num_nodes - 1)],
        'demands': [0] + [1] * num_customers + [0] * num_hubs,
        'time_windows': [(0, 86400)] * num_nodes,
        'vehicle_capacities': [10] * num_vehicles,
        'start_times': [0] * num_vehicles,
        'end_times': [86400] * num_vehicles,
    }


class TestCreateBaseNodeMapping:
    """Correspondance entre nœuds étendus et positions physiques."""

    def test_les_paires_de_hub_pointent_vers_leur_propre_hub(self):
        """Le défaut historique : au-delà du premier hub, la table était décalée.

        `setup_data_extensions` numérote par paire (dépôt n, retrait n+1). Une
        construction en deux passes, tous les dépôts puis tous les retraits,
        donnait [hub0, hub1, hub0, hub1] au lieu de [hub0, hub0, hub1, hub1].
        """
        # ── ARRANGE ────────────────────────────────────────────────
        # 3 clients et 2 hubs : nœuds 0 (dépôt), 1-3 (clients), 4-5 (hubs),
        # puis 6-7 (rechargements) et 8-11 (dépôts et retraits).
        data = {
            'depot': 0,
            'num_customers': 3,
            'num_hubs': 2,
            'num_nodes': 6,
            'unload_depots': [6, 7],
            'hub_deposits': [8, 10],
            'hub_pickups': [9, 11],
        }
        hub_indices = range(4, 6)

        # ── ACT ────────────────────────────────────────────────────
        base_node = create_base_node_mapping(data, hub_indices)

        # ── ASSERT ─────────────────────────────────────────────────
        assert base_node == [
            0, 1, 2, 3, 4, 5,   # nœuds de base
            0, 0,               # rechargements, au dépôt
            4, 4,               # dépôt et retrait du hub 4
            5, 5,               # dépôt et retrait du hub 5
        ]

    def test_reste_aligne_sur_la_numerotation_reelle(self):
        """Vérification croisée avec la fonction qui crée réellement les nœuds."""
        # ── ARRANGE ────────────────────────────────────────────────
        data = _donnees_minimales(num_customers=3, num_hubs=3)
        _, _, _, hub_indices, _ = setup_data_extensions(data)

        # ── ACT ────────────────────────────────────────────────────
        base_node = create_base_node_mapping(data, hub_indices)

        # ── ASSERT ─────────────────────────────────────────────────
        for hub, deposit, pickup in zip(hub_indices, data['hub_deposits'], data['hub_pickups']):
            assert base_node[deposit] == hub, (
                f"le dépôt {deposit} du hub {hub} pointe vers {base_node[deposit]}"
            )
            assert base_node[pickup] == hub, (
                f"le retrait {pickup} du hub {hub} pointe vers {base_node[pickup]}"
            )

    def test_les_rechargements_pointent_vers_le_depot(self):
        # ── ARRANGE ────────────────────────────────────────────────
        data = _donnees_minimales(num_customers=3, num_hubs=1)
        _, _, _, hub_indices, _ = setup_data_extensions(data)

        # ── ACT ────────────────────────────────────────────────────
        base_node = create_base_node_mapping(data, hub_indices)

        # ── ASSERT ─────────────────────────────────────────────────
        for node in data['unload_depots']:
            assert base_node[node] == data['depot']

    def test_la_table_couvre_exactement_les_noeuds_du_modele(self):
        # ── ARRANGE ────────────────────────────────────────────────
        data = _donnees_minimales(num_customers=4, num_hubs=2)
        _, _, _, hub_indices, _ = setup_data_extensions(data)

        # ── ACT ────────────────────────────────────────────────────
        base_node = create_base_node_mapping(data, hub_indices)

        # ── ASSERT ─────────────────────────────────────────────────
        assert len(base_node) == data['num_locations'], (
            "un nœud sans correspondance ferait sortir get_distance de la table"
        )


class TestStripHubs:
    """Retrait effectif des hubs du problème."""

    def test_retire_les_noeuds_de_hub_des_donnees(self):
        # ── ARRANGE ────────────────────────────────────────────────
        data = _donnees_minimales(num_customers=3, num_hubs=2)
        import numpy as np
        data['distance_matrix'] = np.zeros((6, 6))
        data['time_matrix'] = np.zeros((6, 6))

        # ── ACT ────────────────────────────────────────────────────
        stripped = strip_hubs(data)

        # ── ASSERT ─────────────────────────────────────────────────
        assert stripped['num_hubs'] == 0
        assert stripped['num_nodes'] == 4, "1 dépôt + 3 clients"
        assert len(stripped['locations']) == 4
        assert len(stripped['demands']) == 4
        assert len(stripped['time_windows']) == 4
        assert stripped['distance_matrix'].shape == (4, 4)
        assert stripped['time_matrix'].shape == (4, 4)

    def test_ne_modifie_pas_les_donnees_d_origine(self):
        """`solve_vrp` mute son argument : la copie doit posséder ses listes."""
        # ── ARRANGE ────────────────────────────────────────────────
        data = _donnees_minimales(num_customers=3, num_hubs=2)
        import numpy as np
        data['distance_matrix'] = np.zeros((6, 6))
        data['time_matrix'] = np.zeros((6, 6))

        # ── ACT ────────────────────────────────────────────────────
        stripped = strip_hubs(data)
        stripped['locations'].append((0.0, 0.0))
        stripped['demands'].append(0)

        # ── ASSERT ─────────────────────────────────────────────────
        assert len(data['locations']) == 6
        assert len(data['demands']) == 6
        assert data['num_hubs'] == 2
        assert data['num_nodes'] == 6
