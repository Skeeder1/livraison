"""
Tests du contournement de la régression OR-Tools sur les véhicules autorisés.

Depuis OR-Tools 9.15, `RoutingModel.SetAllowedVehiclesForIndex` est inutilisable
depuis Python : la signature C++ est passée de `const std::vector<int>&` à
`absl::Span<const int>` sans typemap SWIG correspondant, et tout appel lève
`TypeError`, quel que soit le type passé.
Suivi amont : https://github.com/google/or-tools/issues/4982

`set_allowed_vehicles` contourne la régression en contraignant directement la
variable de véhicule du nœud. Ces tests vérifient que le contournement fait bien
ce que l'API native était censée faire — et qu'il préserve la possibilité
d'abandonner un nœud, indispensable au fonctionnement des disjonctions.
"""
import pytest
from ortools.constraint_solver import pywrapcp

from optimizer.solver import set_allowed_vehicles


@pytest.fixture
def routing_model():
    """Un modèle de routage minimal : 5 nœuds, 3 véhicules, dépôt au nœud 0."""
    manager = pywrapcp.RoutingIndexManager(5, 3, 0)
    routing = pywrapcp.RoutingModel(manager)
    return manager, routing


class TestSetAllowedVehicles:
    """Comportement de set_allowed_vehicles."""

    def test_restreint_bien_les_vehicules_autorises(self, routing_model):
        # ── ARRANGE ────────────────────────────────────────────────
        manager, routing = routing_model
        node_index = manager.NodeToIndex(1)

        # ── ACT ────────────────────────────────────────────────────
        set_allowed_vehicles(routing, [0, 2], node_index)

        # ── ASSERT ─────────────────────────────────────────────────
        vehicle_var = routing.VehicleVar(node_index)
        assert vehicle_var.Contains(0), "Le véhicule 0 devait rester autorisé"
        assert vehicle_var.Contains(2), "Le véhicule 2 devait rester autorisé"
        assert not vehicle_var.Contains(1), (
            "Le véhicule 1 n'était pas dans la liste autorisée et devait être exclu"
        )

    def test_un_seul_vehicule_autorise(self, routing_model):
        # ── ARRANGE ────────────────────────────────────────────────
        manager, routing = routing_model
        node_index = manager.NodeToIndex(2)

        # ── ACT ────────────────────────────────────────────────────
        set_allowed_vehicles(routing, [1], node_index)

        # ── ASSERT ─────────────────────────────────────────────────
        vehicle_var = routing.VehicleVar(node_index)
        assert vehicle_var.Contains(1), "Le véhicule 1 devait rester autorisé"
        assert not vehicle_var.Contains(0), "Le véhicule 0 devait être exclu"

    def test_preserve_la_possibilite_d_abandonner_un_noeud(self, routing_model):
        """
        Un nœud placé en disjonction peut être abandonné contre pénalité : sa
        variable de véhicule contient alors -1. Écraser ce sentinelle rendrait la
        disjonction inopérante et peut rendre le modèle infaisable.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        manager, routing = routing_model
        node_index = manager.NodeToIndex(3)
        routing.AddDisjunction([node_index], 1000)
        assert routing.VehicleVar(node_index).Contains(-1), (
            "Pré-condition : un nœud en disjonction doit accepter -1 (non desservi)"
        )

        # ── ACT ────────────────────────────────────────────────────
        set_allowed_vehicles(routing, [0, 1], node_index)

        # ── ASSERT ─────────────────────────────────────────────────
        assert routing.VehicleVar(node_index).Contains(-1), (
            "Le sentinelle -1 (nœud non desservi) doit être préservé, sinon la "
            "disjonction devient inopérante"
        )

    def test_accepte_les_entiers_non_natifs(self, routing_model):
        """Les indices issus de numpy ou d'un range doivent passer sans erreur."""
        # ── ARRANGE ────────────────────────────────────────────────
        manager, routing = routing_model
        node_index = manager.NodeToIndex(4)

        # ── ACT ────────────────────────────────────────────────────
        set_allowed_vehicles(routing, range(2), node_index)

        # ── ASSERT ─────────────────────────────────────────────────
        vehicle_var = routing.VehicleVar(node_index)
        assert vehicle_var.Contains(0) and vehicle_var.Contains(1), (
            "Un range doit être accepté comme n'importe quel itérable d'entiers"
        )

    def test_l_api_native_ortools_est_toujours_cassee(self, routing_model):
        """
        Sentinelle de régression amont : le jour où OR-Tools corrigera le typemap
        SWIG (jalon 9.16), ce test échouera et signalera que le contournement peut
        être retiré.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        manager, routing = routing_model
        node_index = manager.NodeToIndex(1)

        # ── ACT & ASSERT ───────────────────────────────────────────
        with pytest.raises(TypeError, match="absl::Span"):
            routing.SetAllowedVehiclesForIndex([0, 1], node_index)
