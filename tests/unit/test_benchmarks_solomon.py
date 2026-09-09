"""
Contrôles du banc d'essai Solomon.

Deux natures de tests, et la seconde est la plus importante.

Les premiers vérifient la mécanique : la lecture des deux formats d'instance,
les deux conventions d'arrondi, l'arithmétique du vérificateur, le repli du
temps de service dans la matrice.

Les seconds vérifient la **calibration** : relire les tournées publiées et
retrouver, au centième, les distances publiées. C'est ce qui donne le droit
d'annoncer un écart. Sans eux, un écart mesuré pourrait aussi bien venir d'une
instance mal lue, d'une convention mal appliquée ou d'un vérificateur qui
compte faux — et rien ne le dirait.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from benchmarks.bks import best_known, gap_percent
from benchmarks.convert import build_plan, write_dataset
from benchmarks.reference import parse_reference
from benchmarks.solomon import (
    Convention,
    check_agreement,
    load_instance,
    parse_solomon,
    parse_vrplib,
)
from benchmarks.verifier import check_solution

INSTANCES = Path(__file__).resolve().parents[2] / 'benchmarks' / 'instances'

NAMES = ('C101', 'R101', 'RC101')


pytestmark = pytest.mark.skipif(
    not (INSTANCES / 'C101.vrp').exists(),
    reason="instances Solomon absentes du cache (voir benchmarks/README.md)",
)


@pytest.fixture(scope='module')
def instances():
    return {name: load_instance(INSTANCES, name) for name in NAMES}


# ── Lecture des instances ────────────────────────────────────────────────

@pytest.mark.parametrize('name', NAMES)
def test_les_deux_formats_portent_la_meme_instance(name):
    """Le fichier Solomon d'un miroir GitHub et le VRPLIB de PyVRP coïncident."""
    issues = check_agreement(parse_vrplib(INSTANCES / f'{name}.vrp'),
                             parse_solomon(INSTANCES / f'{name}.txt'))
    assert issues == []


@pytest.mark.parametrize('name,service', [('C101', 90), ('R101', 10), ('RC101', 10)])
def test_le_temps_de_service_est_constant_par_client(instances, name, service):
    """
    Le constat qui fonde tout le repli de matrice.

    Solomon donne un temps de service identique pour tous les clients d'une
    instance, sans rapport avec leur demande. Le modèle du dépôt, lui, calcule
    ``|demande| × SERVICE_TIME_PER_UNIT``.
    """
    instance = instances[name]
    assert instance.constant_service_time == service
    assert instance.depot.service == 0
    assert len({node.demand for node in instance.customers}) > 1


def test_toutes_les_instances_ont_cent_clients(instances):
    for instance in instances.values():
        assert instance.num_customers == 100
        assert instance.capacity == 200


# ── Conventions de distance ──────────────────────────────────────────────

def test_dimacs_tronque_au_dixieme_par_arc(instances):
    """
    :math:`d_{ij} = \\lfloor 10 e_{ij} \\rfloor / 10`, et jamais un arrondi.

    Un arrondi au plus proche donnerait la même chose une fois sur deux, ce qui
    suffit à faire passer un test bâclé et à manquer la valeur publiée.
    """
    instance = instances['R101']
    for i, j in ((0, 1), (1, 2), (5, 40), (17, 83)):
        a, b = instance.nodes[i], instance.nodes[j]
        euclid = math.hypot(a.x - b.x, a.y - b.y)
        assert instance.distance(i, j, Convention.DIMACS) == math.floor(euclid * 10) / 10
        assert instance.distance(i, j, Convention.EXACT) == pytest.approx(euclid)


def test_la_matrice_coincide_avec_la_distance_arc_par_arc(instances):
    instance = instances['RC101']
    for convention in Convention:
        matrix = instance.distance_matrix(convention)
        assert matrix.shape == (101, 101)
        assert np.all(np.diag(matrix) == 0.0)
        for i, j in ((0, 7), (3, 3), (42, 11), (99, 100)):
            assert matrix[i, j] == pytest.approx(instance.distance(i, j, convention))


# ── Calibration : reproduire les valeurs publiées ────────────────────────

@pytest.mark.parametrize('name', NAMES)
def test_reproduit_l_optimum_cvrplib_sous_convention_dimacs(instances, name):
    """
    Les tournées optimales de CVRPLIB, relues, redonnent la distance publiée.

    C'est le test qui autorise à parler d'écart : il valide d'un seul coup
    l'instance, la convention DIMACS et le vérificateur.
    """
    instance = instances[name]
    reference = parse_reference(INSTANCES / f'{name}.sol')
    check = check_solution(instance, [list(route) for route in reference.routes],
                           Convention.DIMACS)
    published = best_known(name, 'distance')

    assert check.feasible, check.failures()
    assert check.vehicles_used == published.vehicles
    assert check.total_distance == pytest.approx(published.distance, abs=0.005)
    assert reference.reported_cost == pytest.approx(published.distance, abs=0.005)


@pytest.mark.parametrize('name', NAMES)
def test_reproduit_la_valeur_sintef_sous_convention_exacte(instances, name):
    """Idem pour le registre SINTEF, en double précision et objectif hiérarchique."""
    instance = instances[name]
    reference = parse_reference(INSTANCES / f'{name}.sintef.sol')
    check = check_solution(instance, [list(route) for route in reference.routes],
                           Convention.EXACT)
    published = best_known(name, 'hierarchical')

    assert check.feasible, check.failures()
    assert check.vehicles_used == published.vehicles
    assert check.total_distance == pytest.approx(published.distance, abs=0.005)


def test_les_deux_familles_ne_sont_pas_interchangeables(instances):
    """
    Appliquer la mauvaise convention fabrique un écart fantôme, et peut même
    rendre infaisable une solution publiée comme optimale.

    Sur RC101, l'optimum CVRPLIB — valide sous troncature au dixième — viole
    une fenêtre horaire dès qu'on repasse en double précision : les distances
    non tronquées sont plus longues, et le retard s'accumule. C'est la
    démonstration la plus nette que les deux familles décrivent deux problèmes
    différents, et non deux mesures du même.
    """
    instance = instances['RC101']
    routes = [list(route) for route in parse_reference(INSTANCES / 'RC101.sol').routes]

    dimacs = check_solution(instance, routes, Convention.DIMACS)
    exact = check_solution(instance, routes, Convention.EXACT)

    assert dimacs.feasible
    assert not exact.feasible
    assert exact.total_distance > dimacs.total_distance


# ── Vérificateur ─────────────────────────────────────────────────────────

def test_le_verificateur_refuse_un_client_oublie(instances):
    instance = instances['C101']
    routes = [list(route) for route in parse_reference(INSTANCES / 'C101.sol').routes]
    routes[0] = routes[0][1:]  # on retire un client

    check = check_solution(instance, routes, Convention.DIMACS)

    assert not check.feasible
    assert len(check.missing_customers) == 1
    assert any('non servis' in problem for problem in check.failures())


def test_le_verificateur_refuse_un_client_servi_deux_fois(instances):
    instance = instances['C101']
    routes = [list(route) for route in parse_reference(INSTANCES / 'C101.sol').routes]
    routes[1] = routes[1] + [routes[0][0]]

    check = check_solution(instance, routes, Convention.DIMACS)

    assert not check.feasible
    assert check.duplicate_customers == (routes[0][0],)


def test_le_verificateur_refuse_une_fenetre_violee(instances):
    """
    Une tournée en ordre inversé rate ses fenêtres : c'est ce qu'on veut voir
    refusé, sans quoi un « résultat » pourrait décrire un trajet impossible.
    """
    instance = instances['C101']
    routes = [list(route) for route in parse_reference(INSTANCES / 'C101.sol').routes]
    routes[0] = list(reversed(routes[0]))

    check = check_solution(instance, routes, Convention.DIMACS)

    assert not check.feasible
    assert check.routes[0].time_window_violations


def test_le_verificateur_refuse_un_depassement_de_capacite(instances):
    """Tous les clients sur un seul véhicule : 1 810 unités pour une capacité de 200."""
    instance = instances['C101']
    routes = [list(range(1, 101))]

    check = check_solution(instance, routes, Convention.DIMACS)

    assert not check.feasible
    assert check.routes[0].capacity_violation is not None
    assert check.routes[0].load == sum(node.demand for node in instance.customers)


def test_attendre_avant_l_ouverture_est_permis_et_gratuit(instances):
    """
    Arriver avant :math:`e_j` n'est pas une violation : le véhicule attend.
    Seul un service commencé après :math:`l_j` en est une.
    """
    instance = instances['C101']
    # Le client dont la fenêtre s'ouvre le plus tard : depuis le dépôt on y
    # arrive très en avance, donc on attend longtemps. Ce n'est pas une faute.
    late = max(instance.customers, key=lambda node: node.ready)
    route = check_solution(instance, [[late.number]], Convention.DIMACS).routes[0]

    assert route.time_window_violations == []
    assert route.horizon_violation is None
    # L'attente ne gonfle pas la distance : elle ne coûte rien.
    aller = instance.distance(0, late.number, Convention.DIMACS)
    assert route.distance == pytest.approx(2 * aller)

    # En revanche, servir ce client puis un autre dont la fenêtre s'est déjà
    # refermée est bien une violation.
    early = min(instance.customers, key=lambda node: node.due)
    tardif = check_solution(instance, [[late.number, early.number]], Convention.DIMACS)
    assert tardif.routes[0].time_window_violations


def test_une_tournee_vide_ne_compte_pas_pour_un_vehicule(instances):
    instance = instances['C101']
    routes = [list(route) for route in parse_reference(INSTANCES / 'C101.sol').routes]

    check = check_solution(instance, routes + [[], [], []], Convention.DIMACS)

    assert check.vehicles_used == 10
    assert check.feasible


# ── Conversion vers le format du dépôt ───────────────────────────────────

def test_la_matrice_replie_le_temps_de_service_au_noeud_d_origine(instances, tmp_path):
    """
    ``M[i][j] = d_ij + s_i`` : c'est ce repli qui rend la fenêtre horaire
    exacte malgré un modèle dont le temps de service dépend de la demande.
    """
    instance = instances['C101']
    write_dataset(instance, Convention.DIMACS, tmp_path, fleet=10)
    matrix = np.load(tmp_path / 'distance_matrix.npy')

    for i, j in ((0, 1), (1, 2), (50, 7)):
        expected = instance.distance(i, j, Convention.DIMACS) + instance.nodes[i].service
        assert matrix[i, j] == pytest.approx(expected)

    # La ligne du dépôt ne reçoit aucun temps de service, et la diagonale non plus.
    assert matrix[0, 1] == pytest.approx(instance.distance(0, 1, Convention.DIMACS))
    assert np.all(np.diag(matrix) == 0.0)


def test_le_surcout_du_repli_est_une_constante(instances):
    """
    Le repli ajoute :math:`\\sum_i s_i` à toute solution servant tous les
    clients — chaque client a exactement un arc sortant — donc il ne déplace
    pas l'optimum.
    """
    instance = instances['C101']
    plan = build_plan(instance, Convention.DIMACS)
    assert plan.service_offset == 100 * 90

    routes = [list(route) for route in parse_reference(INSTANCES / 'C101.sol').routes]
    matrix = instance.distance_matrix(Convention.DIMACS)
    service = np.array([node.service for node in instance.nodes], dtype=float)
    folded = matrix + service[:, None]
    np.fill_diagonal(folded, 0.0)

    replie = sum(
        folded[a, b]
        for route in routes
        for a, b in zip([0] + route, route + [0], strict=True)
    )
    nu = check_solution(instance, routes, Convention.DIMACS).total_distance

    assert replie - nu == pytest.approx(plan.service_offset)


@pytest.mark.parametrize('name,convention,solution,fleet', [
    ('R101', Convention.EXACT, 'R101.sintef.sol', 19),
    ('RC101', Convention.EXACT, 'RC101.sintef.sol', 14),
    ('RC101', Convention.DIMACS, 'RC101.sol', 15),
])
def test_la_solution_publiee_tient_dans_l_arithmetique_du_modele(
    instances, name, convention, solution, fleet
):
    """
    Aux flottes exactes où le solveur abandonne des clients, une solution qui
    les sert tous existe pourtant — et pas seulement au sens de Solomon : au
    sens de l'arithmétique **du modèle**, matrice repliée, mise à l'échelle et
    troncature entière comprises.

    Ce test transforme « le solveur devrait y arriver » en « le solveur avait
    la place d'y arriver ». Sans lui, les abandons observés pourraient tout
    aussi bien venir d'une conversion trop serrée que d'un défaut de recherche.
    """
    instance = instances[name]
    plan = build_plan(instance, convention)
    scale = plan.time_scale

    matrix = instance.distance_matrix(convention)
    service = np.array([node.service for node in instance.nodes], dtype=float)
    folded = matrix + service[:, None]
    np.fill_diagonal(folded, 0.0)

    routes = [list(route) for route in parse_reference(INSTANCES / solution).routes]
    assert len(routes) == fleet

    for route in routes:
        clock, previous = 0, 0
        for customer in route:
            # `int()` et non `round()` : c'est la troncature que fait le modèle.
            clock += int(folded[previous, customer] * scale)
            clock = max(clock, instance.nodes[customer].ready * scale)
            assert clock <= instance.nodes[customer].due * scale
            previous = customer
        clock += int(folded[previous, 0] * scale)
        assert clock <= instance.depot.due * scale


def test_la_conversion_neutralise_la_machinerie_geographique(instances):
    """Hubs, rechargements, coefficients d'étalement et fenêtres molles, tous écartés."""
    plan = build_plan(instances['R101'], Convention.DIMACS)

    assert plan.config['NUM_HUBS'] == 0
    assert plan.config['NUM_UNLOAD_DEPOTS'] == 0
    assert plan.config['TIME_WINDOWS_OPTIONAL'] is False
    assert plan.config['SERVICE_TIME_PER_UNIT'] == 0
    assert plan.config['TIME_SPAN_COEFFICIENT'] == 0
    assert plan.config['CAPACITY_SPAN_COEFFICIENT'] == 0
    assert plan.config['DISTANCE_SPAN_COEFFICIENT'] == 0
    assert plan.config['VEHICLE_FIXED_COST_METERS'] == 0


def test_l_echelle_dimacs_rend_l_arithmetique_du_modele_exacte(instances):
    """
    Le modèle tronque (``int(distance × facteur)``). Sous DIMACS toutes les
    distances sont des multiples d'un dixième : un facteur 10 ne perd rien, et
    les temps du solveur sont ceux de Solomon exactement.
    """
    instance = instances['RC101']
    plan = build_plan(instance, Convention.DIMACS)
    assert plan.time_scale == 10

    matrix = instance.distance_matrix(Convention.DIMACS)
    service = np.array([node.service for node in instance.nodes], dtype=float)
    folded = (matrix + service[:, None])
    scaled = folded * plan.time_scale
    assert np.all(np.abs(scaled - np.rint(scaled)) < 1e-6)


def test_le_jeu_de_donnees_converti_se_relit(instances, tmp_path):
    """`optimizer.data_loader` doit retrouver ses cinq fichiers et ses grandeurs."""
    instance = instances['R101']
    plan = build_plan(instance, Convention.DIMACS)
    write_dataset(instance, Convention.DIMACS, tmp_path, fleet=7, plan=plan)

    for filename in ('colis.json', 'livreurs.json', 'hubs.json',
                     'weights.json', 'distance_matrix.npy'):
        assert (tmp_path / filename).exists()

    colis = json.loads((tmp_path / 'colis.json').read_text())
    livreurs = json.loads((tmp_path / 'livreurs.json').read_text())

    assert len(colis) == 100
    assert len(livreurs) == 7
    assert json.loads((tmp_path / 'hubs.json').read_text()) == []
    assert all(entry['capacity'] == 200 for entry in livreurs)
    # Fenêtres mises à l'échelle du modèle, dépôt compris via les horaires
    # de vacation des livreurs.
    assert colis[0]['tw_start'] == instance.nodes[1].ready * plan.time_scale
    assert livreurs[0]['end_time'] == instance.depot.due * plan.time_scale


# ── Registre des valeurs publiées ────────────────────────────────────────

def test_les_deux_familles_de_bks_sont_distinctes():
    """
    Le registre doit garder les deux familles séparées : même instance, mais
    objectif, convention, valeur et statut d'optimalité différents.
    """
    for name in NAMES:
        hierarchical = best_known(name, 'hierarchical')
        distance = best_known(name, 'distance')

        assert hierarchical.convention is Convention.EXACT
        assert distance.convention is Convention.DIMACS
        assert distance.proven_optimal
        assert not hierarchical.proven_optimal
        assert hierarchical.distance != distance.distance
        assert hierarchical.source.startswith('https://')


def test_l_ecart_est_positif_quand_la_mesure_est_moins_bonne():
    assert gap_percent(1650.0, 1650.0) == pytest.approx(0.0)
    assert gap_percent(1683.0, 1650.0) == pytest.approx(2.0)
    assert gap_percent(1617.0, 1650.0) == pytest.approx(-2.0)


def test_un_couple_inconnu_leve_plutot_que_de_deviner():
    with pytest.raises(KeyError):
        best_known('C101', 'monolithique')
    with pytest.raises(KeyError):
        best_known('R112', 'distance')
