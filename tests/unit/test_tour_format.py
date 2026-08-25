"""
Tests du format de tournée servi au consommateur web.

Le document produit par `build_tour` est un contrat : la page qui le rejoue
suppose sept invariants, et n'en vérifie aucun. Ils sont donc vérifiés ici, sur
une solution minuscule construite à la main, sans solveur, donc en quelques
millisecondes.

Les mêmes invariants sont revérifiés sur une vraie résolution dans
`tests/integration/test_scenario.py`, via le même assistant partagé.
"""
from copy import deepcopy
import pytest

from optimizer.tour_format import (
    build_tour,
    classify,
    haversine_m,
    polyline_length_m,
    simplify,
)
from tests.tour_invariants import assert_tour_invariants


@pytest.fixture
def solution_source():
    """
    Solution minimale : 2 clients, 1 hub, 1 rechargement, 1 véhicule.

    Numérotation identique à celle du solveur : dépôt 0, clients 1-2, hub 3,
    puis les nœuds ajoutés : ici un unique point de rechargement, 4.
    """
    return {
        'locations': [
            (48.8566, 2.3522),   # 0 dépôt
            (48.8600, 2.3600),   # 1 client
            (48.8500, 2.3400),   # 2 client
            (48.8700, 2.3700),   # 3 hub
            (48.8566, 2.3522),   # 4 rechargement, au dépôt
        ],
        'demands': [0, 1, 1, 0, -10],
        'time_windows': [(0, 86400)] * 5,
        'num_customers': 2,
        'num_hubs': 1,
        'unload_depots': [4],
        'hub_deposits': [],
        'hub_pickups': [],
        'time_per_demand_unit': 5,
        'vehicle_capacities': [10],
        'num_real_vehicles': 1,
        'road_legs': {},
        'results': {
            'per_livreur': {
                'routes': [[0, 1, 4, 2, 3, 0]],
                'estimated_times': [[0, 100, 250, 400, 500, 700]],
                'cumulative_loads': [[10, 9, 10, 9, 9, 9]],
                # Une attente de 30 s au premier client ; un élément de moins
                # que la route, comme le produit le solveur.
                'slacks': [[0, 30, 0, 0, 0]],
            },
            'indicators': {
                'total_time_all_vehicles': 700,
                'total_tardiness_minutes': 0,
                'activated_hubs': 0,
            },
        },
    }


class TestBuildTour:
    """Forme du document produit."""

    def test_respecte_les_invariants_du_consommateur(self, solution_source):
        # ── ARRANGE ────────────────────────────────────────────────
        # (fixture)

        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(solution_source)

        # ── ASSERT ─────────────────────────────────────────────────
        assert_tour_invariants(tour)

    def test_le_retard_est_en_minutes_pas_en_secondes(self, solution_source):
        """`tardinessMinutes` porte des minutes, malgré la source en secondes.

        L'indicateur interne s'appelle `total_tardiness_minutes` et contient des
        SECONDES, ce que son propre commentaire dans `postprocessor` reconnaît.
        Toutes les autres durées du document étant elles aussi en secondes, le
        mauvais nom est passé inaperçu jusqu'à ce qu'une tournée aux fenêtres
        horaires contraignantes annonce 1292 « minutes » de retard sur une
        journée de 165 minutes. La conversion se fait à la frontière du contrat
        web, et ce test l'y maintient.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        source = deepcopy(solution_source)
        source['results']['indicators']['total_tardiness_minutes'] = 1292

        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(source)

        # ── ASSERT ─────────────────────────────────────────────────
        assert tour['stats']['tardinessMinutes'] == 22

    def test_classe_chaque_arret_selon_son_role(self, solution_source):
        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(solution_source)

        # ── ASSERT ─────────────────────────────────────────────────
        kinds = [stop['kind'] for stop in tour['vehicles'][0]['stops']]
        assert kinds == ['depot', 'customer', 'reload', 'customer', 'hub', 'depot']

    def test_le_depart_integre_service_et_attente(self, solution_source):
        """`depart = arrive + service + attente` : l'animation en dépend pour
        savoir quand le véhicule redémarre."""
        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(solution_source)

        # ── ASSERT ─────────────────────────────────────────────────
        premier_client = tour['vehicles'][0]['stops'][1]
        assert premier_client['arrive'] == 100
        assert premier_client['service'] == 5   # 1 colis × 5 s
        assert premier_client['depart'] == 135  # 100 + 5 + 30 d'attente

    def test_le_dernier_arret_n_a_pas_d_attente(self, solution_source):
        """La liste d'attentes compte un élément de moins que la route."""
        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(solution_source)

        # ── ASSERT ─────────────────────────────────────────────────
        dernier = tour['vehicles'][0]['stops'][-1]
        assert dernier['depart'] == dernier['arrive'] + dernier['service']

    def test_compte_les_rechargements_et_les_passages_en_hub(self, solution_source):
        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(solution_source)

        # ── ASSERT ─────────────────────────────────────────────────
        assert tour['stats']['reloads'] == 1
        assert tour['stats']['hubFlybys'] == 1
        assert tour['reloadEvents'] == [{'vehicle': 0, 'at': 250, 'from': 9, 'to': 10}]

    def test_sans_geometrie_routiere_les_segments_sont_des_droites(self, solution_source):
        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(solution_source)

        # ── ASSERT ─────────────────────────────────────────────────
        for leg in tour['vehicles'][0]['legs']:
            assert leg['road'] is False
            assert len(leg['pts']) == 2

    def test_utilise_la_geometrie_routiere_quand_elle_existe(self, solution_source):
        # ── ARRANGE ────────────────────────────────────────────────
        # Un détour marqué : le point du milieu s'écarte de plus de 4 m de la
        # corde, la simplification doit donc le conserver.
        solution_source['road_legs'] = {
            '0-1': [[48.8566, 2.3522], [48.8590, 2.3540], [48.8600, 2.3600]],
        }

        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(solution_source)

        # ── ASSERT ─────────────────────────────────────────────────
        premier_segment = tour['vehicles'][0]['legs'][0]
        assert premier_segment['road'] is True
        assert len(premier_segment['pts']) == 3

    def test_ignore_les_vehicules_fictifs(self, solution_source):
        """Les véhicules de transfert ne roulent pas : ils ne sont pas dessinés."""
        # ── ARRANGE ────────────────────────────────────────────────
        per = solution_source['results']['per_livreur']
        per['routes'].append([0, 0])
        per['estimated_times'].append([0, 0])
        per['cumulative_loads'].append([0, 0])
        per['slacks'].append([0])
        solution_source['vehicle_capacities'] = [10, 0]
        del solution_source['num_real_vehicles']  # repli sur la capacité nulle

        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(solution_source)

        # ── ASSERT ─────────────────────────────────────────────────
        assert len(tour['vehicles']) == 1
        assert tour['stats']['vehicles'] == 1

    def test_num_real_vehicles_prime_sur_la_capacite_nulle(self, solution_source):
        """Un véhicule réel de capacité nulle ne doit pas être pris pour un fictif."""
        # ── ARRANGE ────────────────────────────────────────────────
        solution_source['vehicle_capacities'] = [0]
        solution_source['num_real_vehicles'] = 1

        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(solution_source)

        # ── ASSERT ─────────────────────────────────────────────────
        assert len(tour['vehicles']) == 1, (
            "le repli sur la capacité nulle aurait supprimé ce véhicule"
        )

    def test_signale_des_fenetres_horaires_contraignantes(self, solution_source):
        # ── ARRANGE ────────────────────────────────────────────────
        solution_source['time_windows'] = [(0, 86400), (0, 7200), (0, 86400), (0, 86400), (0, 86400)]

        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(solution_source)

        # ── ASSERT ─────────────────────────────────────────────────
        assert tour['stats']['timeWindowsBinding'] is True

    def test_recopie_le_bloc_de_provenance(self, solution_source):
        # ── ACT ────────────────────────────────────────────────────
        tour = build_tour(solution_source, {'seed': 42})

        # ── ASSERT ─────────────────────────────────────────────────
        assert tour['meta'] == {'seed': 42}


class TestClassify:
    """Nature d'un nœud."""

    def test_les_points_de_transfert_sont_des_hubs(self):
        """Dépôt et retrait de hub : demande négative et positive, même endroit."""
        # ── ACT ────────────────────────────────────────────────────
        depot_hub = classify(58, -1, 45, hub_nodes={46, 47, 58, 59}, reload_nodes={48})
        retrait_hub = classify(59, 1, 45, hub_nodes={46, 47, 58, 59}, reload_nodes={48})

        # ── ASSERT ─────────────────────────────────────────────────
        assert depot_hub == 'hub', "un dépôt de hub n'est pas un rechargement au dépôt"
        assert retrait_hub == 'hub'

    def test_repli_sur_le_signe_de_la_demande(self):
        """Sans ensembles fournis, la demande négative marque un rechargement."""
        # ── ACT / ASSERT ───────────────────────────────────────────
        assert classify(50, -10, 45) == 'reload'
        assert classify(46, 0, 45) == 'hub'
        assert classify(3, 1, 45) == 'customer'
        assert classify(0, 0, 45) == 'depot'


class TestGeometrie:
    """Mesures et simplification des tracés."""

    def test_la_distance_correspond_a_la_realite(self):
        """Paris, de l'Île de la Cité à la Tour Eiffel : ~4,1 km."""
        # ── ACT ────────────────────────────────────────────────────
        distance = haversine_m((48.8566, 2.3522), (48.8584, 2.2945))

        # ── ASSERT ─────────────────────────────────────────────────
        assert 4000 < distance < 4300, f"{distance:.0f} m"

    def test_la_simplification_retire_les_points_alignes(self):
        # ── ARRANGE ────────────────────────────────────────────────
        ligne = [[48.85, 2.35], [48.86, 2.36], [48.87, 2.37]]

        # ── ACT ────────────────────────────────────────────────────
        simplifie = simplify(ligne, 4.0)

        # ── ASSERT ─────────────────────────────────────────────────
        assert simplifie == [ligne[0], ligne[-1]]

    def test_la_simplification_conserve_les_detours(self):
        # ── ARRANGE ────────────────────────────────────────────────
        # ~1 km d'écart : bien au-delà de la tolérance de 4 m.
        coude = [[48.85, 2.35], [48.86, 2.35], [48.85, 2.36]]

        # ── ACT ────────────────────────────────────────────────────
        simplifie = simplify(coude, 4.0)

        # ── ASSERT ─────────────────────────────────────────────────
        assert len(simplifie) == 3

    def test_longueur_d_une_polyligne(self):
        # ── ARRANGE ────────────────────────────────────────────────
        trace = [[48.8566, 2.3522], [48.8584, 2.2945], [48.8566, 2.3522]]

        # ── ACT ────────────────────────────────────────────────────
        longueur = polyline_length_m(trace)

        # ── ASSERT ─────────────────────────────────────────────────
        assert longueur == pytest.approx(2 * haversine_m(trace[0], trace[1]))
