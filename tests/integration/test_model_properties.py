"""
Propriétés du modèle, vérifiées sur de vraies résolutions.

Les tests existants vérifient la **forme** du document de tournée et la
**stabilité** de quelques nombres relevés une fois. Aucun ne vérifie que la
solution rendue **respecte le modèle** : un solveur qui livrerait douze colis
avec un véhicule de capacité dix, ou qui ferait repartir un coursier avant son
arrivée, passerait la suite entière sans une rougeur.

Ce module comble ce trou. Chaque test y affirme une propriété qui doit tenir
pour **toute** solution valide, quel que soit le scénario : elle est déduite du
document, jamais comparée à un relevé. Un chiffre gelé dit « rien n'a bougé » ;
ces tests-là disent « la réponse est correcte ».

Organisation :

* `SCENARIOS` décrit une petite matrice — cinq graines, avec et sans hub, plus
  un cas à capacité serrée et deux cas à fenêtres horaires contraignantes. Elle
  couvre les rechargements au dépôt, les transferts entre coursiers et le retard.
* Chaque scénario n'est résolu **qu'une fois** (`tour`, mémoïsé au niveau du
  module) et sert ensuite à toutes les propriétés. Résoudre par assertion
  ferait passer la suite de la minute au quart d'heure.
* La résolution est toujours demandée avec `fetch_roads=False` : aucun test ne
  doit dépendre d'un serveur OSRM public.

Deux propriétés sont marquées `xfail` : elles décrivent le comportement attendu
du transfert entre coursiers et **ne tiennent pas** aujourd'hui. Voir
`TestTransfertsEnHub` pour le détail du défaut ; le marqueur n'est pas là pour
faire taire l'échec mais pour le conserver écrit, exécuté, et daté.
"""
import math

import pytest

from optimizer.config import Config
from optimizer.scenario import solve_scenario
from tests.tour_invariants import assert_tour_invariants

# ── Matrice de scénarios ────────────────────────────────────────────────────
#
# Volontairement petits et courts : ces tests cherchent des violations de
# contraintes, pas de bonnes tournées. Un budget de 3 s suffit à produire une
# solution complète sur douze clients, et la propriété à vérifier ne dépend pas
# de sa qualité.
#
# `lent` porte la marque `slow` du dépôt : `pytest -m "not slow"` laisse alors
# le scénario de côté **sans le résoudre**, la mémoïsation étant paresseuse.
SCENARIOS = {}

for _graine in (1, 7, 42, 123, 2024):
    for _hubs in (0, 2):
        SCENARIOS[f'base-h{_hubs}-graine{_graine}'] = {
            'params': {
                'customers': 12, 'vehicles': 3, 'hubs': _hubs, 'capacity': 10,
                'budget_seconds': 3, 'seed': _graine,
            },
            'lent': False,
        }

#: Capacité 3 pour 18 clients et 2 véhicules : impossible sans repasser par le
#: dépôt. C'est le seul moyen d'exercer réellement les nœuds de rechargement.
SCENARIOS['capacite-serree'] = {
    'params': {
        'customers': 18, 'vehicles': 2, 'hubs': 0, 'capacity': 3,
        'budget_seconds': 4, 'seed': 42,
    },
    'lent': False,
}

#: Fenêtres contraignantes, mais tenables : 15 clients pour 3 véhicules. Sert à
#: vérifier qu'aucun retard n'est inventé quand il n'y en a pas.
SCENARIOS['fenetres-tenables'] = {
    'params': {
        'customers': 15, 'vehicles': 3, 'hubs': 2, 'capacity': 5,
        'time_windows_binding': True, 'budget_seconds': 4, 'seed': 7,
    },
    'lent': False,
}

#: Fenêtres contraignantes et intenables : 40 clients pour **un seul** véhicule.
#: La tournée dépasse largement les fenêtres, et `tardinessMinutes` sort non nul.
#: Sans ce scénario, la cohérence du retard se vérifierait uniquement contre
#: zéro, c'est-à-dire à peu près contre rien.
SCENARIOS['retard-inevitable'] = {
    'params': {
        'customers': 40, 'vehicles': 1, 'hubs': 0, 'capacity': 10,
        'time_windows_binding': True, 'budget_seconds': 5, 'seed': 42,
    },
    'lent': False,
}

#: Le scénario de vitrine, cette fois avec transferts. Vingt secondes de budget :
#: c'est la taille à laquelle le solveur commence à arbitrer les hubs au lieu de
#: les prendre tous.
SCENARIOS['reference-avec-hubs'] = {
    'params': {
        'customers': 45, 'vehicles': 3, 'hubs': 2, 'capacity': 10,
        'budget_seconds': 20, 'seed': 42,
    },
    'lent': True,
}

#: Les scénarios sous forme de paramètres pytest, les lourds portant `slow`.
CAS = [
    pytest.param(nom, id=nom, marks=[pytest.mark.slow] if cas['lent'] else [])
    for nom, cas in SCENARIOS.items()
]

#: Écart toléré, en secondes, entre le temps de trajet reconstruit depuis les
#: coordonnées publiées et celui qu'a réellement appliqué le solveur. Le document
#: arrondit les coordonnées à 5 décimales (`tour_format.COORD_PRECISION`) et le
#: solveur tronque le temps à l'entier : les deux réunis valent au plus une
#: seconde d'écart, mesurée sur l'ensemble de la matrice. Deux, donc, avec marge.
TOLERANCE_TRAJET_S = 2

#: Correction de la longitude, identique à celle de `create_toy_data` : à Paris
#: un degré de longitude vaut ~73 km contre ~111 km pour un degré de latitude.
ECHELLE_LONGITUDE = math.cos(math.radians(Config.DEPOT_POSITION[0]))


# ── Résolution mémoïsée ─────────────────────────────────────────────────────

_TOURNEES = {}


@pytest.fixture(scope='module')
def tour(request, tmp_path_factory):
    """
    Résout un scénario **une seule fois** pour tout le module.

    Le paramètre est le nom du scénario, passé par `indirect=True`. La
    mémoïsation est paresseuse et non un `params=` de fixture : un scénario
    désélectionné (par exemple par `-m "not slow"`) ne doit pas être résolu.

    :param request: Requête pytest, dont `param` porte le nom du scénario
    :param tmp_path_factory: Fabrique de répertoires temporaires
    :return: Document de tournée
    """
    nom = request.param
    if nom not in _TOURNEES:
        workdir = tmp_path_factory.mktemp(nom.replace('-', '_'))
        _TOURNEES[nom] = solve_scenario(
            SCENARIOS[nom]['params'], workdir=workdir, fetch_roads=False
        )
    return _TOURNEES[nom]


# ── Lecture du document ─────────────────────────────────────────────────────


class Roles:
    """
    Numérotation des nœuds telle que `solver.setup_data_extensions` la construit.

    Le document de tournée ne conserve que quatre catégories d'affichage
    (`depot`, `customer`, `reload`, `hub`) et range dans `hub` aussi bien le hub
    lui-même que ses points de dépôt et de retrait. Or les propriétés de
    transfert portent précisément sur la distinction entre les deux : il faut
    donc remonter aux numéros.

    Ceux-ci sont entièrement déterminés par la taille du problème :

    ===================================  ============================
    Nœud                                 Plage
    ===================================  ============================
    dépôt                                0
    clients                              1 .. C
    hubs                                 C+1 .. C+H
    rechargements au dépôt               C+H+1 .. C+H+U
    dépôt / retrait du hub *i*           C+H+U+1+2i et +2i+1
    ===================================  ============================

    avec U = `Config.NUM_UNLOAD_DEPOTS`. Les paires dépôt/retrait sont
    **consécutives**, ce que `solver.create_base_node_mapping` documente déjà
    comme la seule façon de rester aligné sur les numéros.

    `test_la_numerotation_concorde_avec_les_categories` vérifie que cette
    reconstruction concorde arrêt par arrêt avec le champ `kind`. Sans elle, une
    dérive de la numérotation ferait passer les tests de transfert pour vrais en
    ne regardant plus rien.
    """

    def __init__(self, tour):
        nb_clients = tour['stats']['customers']
        nb_hubs = len(tour['hubs'])
        premier_transfert = 1 + nb_clients + nb_hubs + Config.NUM_UNLOAD_DEPOTS

        self.nb_clients = nb_clients
        self.nb_hubs = nb_hubs
        self.clients = set(range(1, nb_clients + 1))
        self.hubs = {h['node'] for h in tour['hubs']}
        self.rechargements = set(range(1 + nb_clients + nb_hubs, premier_transfert))
        self.depots_hub = [premier_transfert + 2 * i for i in range(nb_hubs)]
        self.retraits_hub = [premier_transfert + 2 * i + 1 for i in range(nb_hubs)]

    def categorie(self, node):
        """Catégorie d'affichage attendue pour un nœud, d'après sa seule position."""
        if node == 0:
            return 'depot'
        if node in self.clients:
            return 'customer'
        if node in self.rechargements:
            return 'reload'
        return 'hub'

    def variation_de_charge(self, node, charge_avant, capacite):
        """
        Variation de charge attendue en franchissant ce nœud.

        Un client consomme une unité, un dépôt en hub aussi (le colis quitte le
        véhicule), un retrait en hub en ajoute une, un rechargement au dépôt
        refait le plein. Le dépôt et le hub lui-même ne portent aucune demande.

        :param node: Numéro de nœud
        :param charge_avant: Charge publiée à l'arrêt précédent
        :param capacite: Capacité du véhicule
        :return: Variation attendue de la charge publiée
        """
        if node in self.clients or node in self.depots_hub:
            return -1
        if node in self.retraits_hub:
            return 1
        if node in self.rechargements:
            return capacite - charge_avant
        return 0


def temps_de_trajet(depart, arrivee):
    """
    Temps de trajet du solveur entre deux positions, reconstruit depuis le document.

    `solver.create_evaluator_functions` calcule ce temps comme la distance
    euclidienne plane en degrés, longitude ramenée à l'échelle de la latitude,
    multipliée par `Config.DISTANCE_TO_TIME_FACTOR` puis tronquée à l'entier.
    On refait exactement ce calcul plutôt que d'utiliser `legs[].meters`, qui
    mesure la polyligne affichée en mètres et n'a aucun rapport avec le temps
    qu'a réellement appliqué le modèle.

    :param depart: Couple (latitude, longitude) de départ
    :param arrivee: Couple (latitude, longitude) d'arrivée
    :return: Temps de trajet en secondes, tronqué comme le fait le solveur
    """
    d_lat = depart[0] - arrivee[0]
    d_lon = (depart[1] - arrivee[1]) * ECHELLE_LONGITUDE
    return int(math.hypot(d_lat, d_lon) * Config.DISTANCE_TO_TIME_FACTOR)


def transferts_realises(tour, roles):
    """
    Rendez-vous effectivement tenus, un par hub dont les deux nœuds sont visités.

    :param tour: Document de tournée
    :param roles: Numérotation des nœuds
    :return: Liste de dictionnaires décrivant chaque transfert observé
    """
    visites = {}
    for vehicule in tour['vehicles']:
        for rang, arret in enumerate(vehicule['stops']):
            visites.setdefault(arret['node'], []).append(
                {'vehicule': vehicule['id'], 'rang': rang, 'arrive': arret['arrive']}
            )

    transferts = []
    for hub, (depot, retrait) in enumerate(zip(roles.depots_hub, roles.retraits_hub)):
        if depot in visites and retrait in visites:
            transferts.append(
                {'hub': hub, 'depot': visites[depot], 'retrait': visites[retrait]}
            )
    return transferts


def _retraits_par_vehicule(tour, roles):
    """
    Rangs des arrêts de retrait en hub, véhicule par véhicule.

    Le premier arrêt d'une tournée est toujours le dépôt, si bien qu'un rang de
    retrait vaut au moins 1 : l'arrêt précédent existe donc toujours.

    :param tour: Document de tournée
    :param roles: Numérotation des nœuds
    :return: Dictionnaire {identifiant de véhicule: [rangs des retraits]}
    """
    retraits = {}
    for vehicule in tour['vehicles']:
        rangs = [
            rang for rang, arret in enumerate(vehicule['stops'])
            if arret['node'] in roles.retraits_hub
        ]
        if rangs:
            retraits[vehicule['id']] = rangs
    return retraits


# ── Propriétés ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize('tour', CAS, indirect=True)
class TestLectureDuDocument:
    """La reconstruction sur laquelle reposent les autres tests est-elle juste ?"""

    def test_la_numerotation_concorde_avec_les_categories(self, tour):
        """
        Chaque arrêt doit tomber dans la catégorie que sa position impose.

        C'est le garde-fou de tous les tests de transfert : ils identifient les
        dépôts et retraits de hub par leur numéro. Si la numérotation dérivait
        (un rechargement de plus, un hub de moins), ils continueraient de passer
        en n'observant plus rien du tout.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        roles = Roles(tour)

        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            for rang, arret in enumerate(vehicule['stops']):
                attendu = roles.categorie(arret['node'])
                assert arret['kind'] == attendu, (
                    f"véhicule {vehicule['id']}, arrêt {rang} : nœud {arret['node']} "
                    f"annoncé « {arret['kind']} » alors que sa position en fait un "
                    f"« {attendu} » (clients 1..{roles.nb_clients}, "
                    f"rechargements {sorted(roles.rechargements)}, "
                    f"dépôts de hub {roles.depots_hub}, retraits {roles.retraits_hub})"
                )

    def test_les_invariants_partages_du_consommateur_tiennent(self, tour):
        """Les sept invariants de forme valent aussi sur toute cette matrice, et
        pas seulement sur le scénario de référence."""
        # ── ASSERT ─────────────────────────────────────────────────
        assert_tour_invariants(tour)


@pytest.mark.parametrize('tour', CAS, indirect=True)
class TestCapacite:
    """La contrainte la plus élémentaire du modèle, et la moins testée."""

    def test_aucun_vehicule_ne_depasse_sa_capacite(self, tour):
        """
        Une charge hors de [0, capacité] décrirait un véhicule impossible.

        Négative, elle voudrait dire qu'on livre un colis qu'on n'a pas ;
        au-delà de la capacité, qu'on en transporte plus que le camion n'en
        contient. C'est la propriété que le consommateur web suppose pour
        dessiner sa jauge de remplissage.
        """
        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            capacite = vehicule['capacity']
            for rang, arret in enumerate(vehicule['stops']):
                assert 0 <= arret['load'] <= capacite, (
                    f"véhicule {vehicule['id']}, arrêt {rang} (nœud {arret['node']}, "
                    f"{arret['kind']}) : charge {arret['load']} hors de [0, {capacite}]"
                )

    def test_le_vehicule_part_du_depot_a_pleine_charge(self, tour):
        """
        Le premier arrêt est le dépôt, et le véhicule en repart chargé à bloc.

        C'est la convention de reconstruction de `postprocessor.get_results` :
        la charge décroît ensuite à chaque livraison. Sans ce point de départ
        connu, la suite de la trace ne veut rien dire.
        """
        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            premier = vehicule['stops'][0]
            assert premier['kind'] == 'depot', (
                f"véhicule {vehicule['id']} : la tournée commence au nœud "
                f"{premier['node']} ({premier['kind']}) et non au dépôt"
            )
            assert premier['load'] == vehicule['capacity'], (
                f"véhicule {vehicule['id']} : part avec {premier['load']} colis "
                f"pour une capacité de {vehicule['capacity']}"
            )

    def test_la_charge_suit_la_demande_du_noeud_visite(self, tour):
        """
        Entre deux arrêts, la charge ne bouge que de la demande du nœud franchi.

        C'est la comptabilité du modèle : un client consomme une unité, un dépôt
        en hub aussi, un rechargement au dépôt refait le plein, le dépôt et le
        hub lui-même ne changent rien. Toute autre variation signalerait des
        colis apparus ou disparus en route.

        Les **retraits en hub** sont exclus ici et traités par
        `TestTransfertsEnHub.test_un_retrait_en_hub_ajoute_une_unite`, qui
        échoue : voir le défaut décrit dans cette classe.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        roles = Roles(tour)

        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            capacite = vehicule['capacity']
            arrets = vehicule['stops']
            for rang in range(1, len(arrets)):
                node = arrets[rang]['node']
                if node in roles.retraits_hub:
                    continue
                avant = arrets[rang - 1]['load']
                obtenu = arrets[rang]['load'] - avant
                attendu = roles.variation_de_charge(node, avant, capacite)
                assert obtenu == attendu, (
                    f"véhicule {vehicule['id']}, arrêt {rang} : nœud {node} "
                    f"({arrets[rang]['kind']}) fait passer la charge de {avant} à "
                    f"{arrets[rang]['load']} (variation {obtenu:+d}) alors que sa "
                    f"demande en impose {attendu:+d}"
                )


@pytest.mark.parametrize('tour', CAS, indirect=True)
class TestRechargements:
    """Le rechargement au dépôt est ce qui permet de servir plus de clients que
    la capacité d'un véhicule. Encore faut-il qu'il recharge."""

    def test_un_rechargement_restitue_la_pleine_capacite(self, tour):
        """Après un passage par un point de rechargement, le véhicule repart
        plein : c'est la définition même du nœud, dont la demande vaut moins la
        capacité maximale."""
        # ── ARRANGE ────────────────────────────────────────────────
        roles = Roles(tour)

        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            for rang, arret in enumerate(vehicule['stops']):
                if arret['node'] not in roles.rechargements:
                    continue
                assert arret['load'] == vehicule['capacity'], (
                    f"véhicule {vehicule['id']}, arrêt {rang} : rechargement au "
                    f"nœud {arret['node']} laissant la charge à {arret['load']} "
                    f"au lieu de {vehicule['capacity']}"
                )

    def test_les_evenements_de_rechargement_recensent_tous_les_arrets(self, tour):
        """
        `reloadEvents` est la seule liste que le consommateur lit pour animer les
        retours au dépôt : elle doit recenser exactement les arrêts de
        rechargement, avec les charges avant et après.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        observes = []
        for vehicule in tour['vehicles']:
            arrets = vehicule['stops']
            for rang in range(1, len(arrets)):
                if arrets[rang]['kind'] == 'reload':
                    observes.append({
                        'vehicle': vehicule['id'],
                        'at': arrets[rang]['arrive'],
                        'from': arrets[rang - 1]['load'],
                        'to': arrets[rang]['load'],
                    })
        observes.sort(key=lambda evenement: evenement['at'])

        # ── ASSERT ─────────────────────────────────────────────────
        assert tour['reloadEvents'] == observes, (
            f"reloadEvents annonce {tour['reloadEvents']} là où les tournées "
            f"montrent {observes}"
        )
        assert tour['stats']['reloads'] == len(observes), (
            f"stats.reloads vaut {tour['stats']['reloads']} pour "
            f"{len(observes)} rechargements observés"
        )


@pytest.mark.parametrize('tour', CAS, indirect=True)
class TestChronologie:
    """Une tournée est une suite d'instants ; ils doivent se suivre."""

    def test_un_arret_ne_se_quitte_pas_avant_d_avoir_ete_servi(self, tour):
        """`depart` doit couvrir au moins l'arrivée plus le temps de service.
        Un départ antérieur ferait repartir le coursier avant d'avoir livré."""
        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            for rang, arret in enumerate(vehicule['stops']):
                minimum = arret['arrive'] + arret['service']
                assert arret['depart'] >= minimum, (
                    f"véhicule {vehicule['id']}, arrêt {rang} (nœud {arret['node']}) : "
                    f"départ à {arret['depart']} s alors que le service s'achève à "
                    f"{minimum} s (arrivée {arret['arrive']} + service {arret['service']})"
                )

    def test_les_heures_d_arrivee_ne_reculent_jamais(self, tour):
        """Le temps ne remonte pas : le curseur de l'animation, qui balaye
        `horizon` de gauche à droite, s'appuie dessus."""
        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            arrivees = [arret['arrive'] for arret in vehicule['stops']]
            for rang in range(1, len(arrivees)):
                assert arrivees[rang] >= arrivees[rang - 1], (
                    f"véhicule {vehicule['id']} : arrivée {arrivees[rang]} s à "
                    f"l'arrêt {rang} après {arrivees[rang - 1]} s à l'arrêt "
                    f"{rang - 1}"
                )

    def test_le_trajet_entre_deux_arrets_est_effectivement_parcouru(self, tour):
        """
        L'arrivée suivante laisse la place au temps de trajet du modèle.

        Le temps de trajet est reconstruit depuis les coordonnées publiées avec
        la formule du solveur (`temps_de_trajet`), et non lu dans
        `legs[].meters`, qui mesure la polyligne affichée. Un écart de
        `TOLERANCE_TRAJET_S` est admis : les coordonnées du document sont
        arrondies à cinq décimales.
        """
        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            arrets = vehicule['stops']
            for rang in range(len(arrets) - 1):
                ici, la = arrets[rang], arrets[rang + 1]
                ecoule = la['arrive'] - ici['depart']
                trajet = temps_de_trajet((ici['lat'], ici['lng']), (la['lat'], la['lng']))
                assert ecoule >= 0, (
                    f"véhicule {vehicule['id']}, segment {rang} : arrivée au nœud "
                    f"{la['node']} à {la['arrive']} s, avant le départ du nœud "
                    f"{ici['node']} à {ici['depart']} s"
                )
                assert ecoule >= trajet - TOLERANCE_TRAJET_S, (
                    f"véhicule {vehicule['id']}, segment {rang} "
                    f"({ici['node']} → {la['node']}) : {ecoule} s écoulées entre le "
                    f"départ et l'arrivée pour un trajet de {trajet} s"
                )

    def test_les_segments_encadrent_les_arrets_qu_ils_relient(self, tour):
        """Chaque segment porte les heures des deux arrêts qu'il relie :
        l'animation interpole la position entre ces deux bornes."""
        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            for rang, segment in enumerate(vehicule['legs']):
                ici, la = vehicule['stops'][rang], vehicule['stops'][rang + 1]
                assert segment['depart'] == ici['depart'], (
                    f"véhicule {vehicule['id']}, segment {rang} : part à "
                    f"{segment['depart']} s, l'arrêt à {ici['depart']} s"
                )
                assert segment['arrive'] == la['arrive'], (
                    f"véhicule {vehicule['id']}, segment {rang} : arrive à "
                    f"{segment['arrive']} s, l'arrêt à {la['arrive']} s"
                )

    def test_l_horizon_est_la_fin_de_la_derniere_tournee(self, tour):
        """`horizon` borne le curseur temporel : plus court, l'animation
        s'arrêterait avant le retour du dernier coursier."""
        # ── ARRANGE ────────────────────────────────────────────────
        fins = {vehicule['id']: vehicule['stops'][-1]['arrive'] for vehicule in tour['vehicles']}

        # ── ASSERT ─────────────────────────────────────────────────
        for identifiant, fin in fins.items():
            assert tour['vehicles'][identifiant]['end'] == fin, (
                f"véhicule {identifiant} : end vaut "
                f"{tour['vehicles'][identifiant]['end']} pour un dernier arrêt à {fin}"
            )
        assert tour['horizon'] == max(fins.values()), (
            f"horizon {tour['horizon']} pour des fins de tournée {fins}"
        )
        assert tour['stats']['horizon'] == tour['horizon']


@pytest.mark.parametrize('tour', CAS, indirect=True)
class TestFenetresHoraires:
    """Le retard publié doit être celui qu'on observe, pas zéro par défaut."""

    def test_le_retard_publie_est_celui_des_arrets(self, tour):
        """
        `tardinessMinutes` doit se retrouver en additionnant les dépassements
        constatés arrêt par arrêt.

        On ne suppose surtout pas qu'il vaut zéro : les fenêtres sont
        *optionnelles* dans le modèle (`Config.TIME_WINDOWS_OPTIONAL`), donc le
        solveur a le droit d'arriver en retard. Ce qu'il n'a pas le droit de
        faire, c'est de l'arriver sans le dire.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        fin_de_fenetre = {client['node']: client['twEnd'] for client in tour['customers']}

        # ── ACT ────────────────────────────────────────────────────
        retard_observe = sum(
            max(0, arret['arrive'] - fin_de_fenetre[arret['node']])
            for vehicule in tour['vehicles']
            for arret in vehicule['stops']
            if arret['kind'] == 'customer'
        )

        # ── ASSERT ─────────────────────────────────────────────────
        assert tour['stats']['tardinessMinutes'] == round(retard_observe / 60), (
            f"stats.tardinessMinutes vaut {tour['stats']['tardinessMinutes']} min "
            f"pour {retard_observe} s de retard cumulé sur les arrêts, soit "
            f"{round(retard_observe / 60)} min"
        )

    def test_sans_retard_publie_aucun_client_n_est_servi_hors_delai(self, tour):
        """
        La réciproque du test précédent, prise par l'autre bout.

        Un retard annoncé nul doit se lire sur chaque arrêt : c'est ce qu'affirme
        la vitrine quand elle publie « 0 min de retard ». Le test ne s'applique
        que si le document annonce effectivement zéro ; sinon il n'y a rien à
        vérifier ici.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        if tour['stats']['tardinessMinutes'] != 0:
            pytest.skip("ce scénario accuse un retard : cf. le test de cohérence")
        fin_de_fenetre = {client['node']: client['twEnd'] for client in tour['customers']}

        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            for rang, arret in enumerate(vehicule['stops']):
                if arret['kind'] != 'customer':
                    continue
                limite = fin_de_fenetre[arret['node']]
                assert arret['arrive'] <= limite, (
                    f"véhicule {vehicule['id']}, arrêt {rang} : client "
                    f"{arret['node']} servi à {arret['arrive']} s pour une fenêtre "
                    f"fermée à {limite} s, alors que le document annonce 0 min de retard"
                )

    def test_le_caractere_contraignant_des_fenetres_est_annonce(self, tour):
        """`timeWindowsBinding` dit si les fenêtres mordent réellement. Étalées
        sur la journée entière, elles ne contraignent rien, et l'annoncer évite
        de faire passer une tournée sans retard pour une performance."""
        # ── ARRANGE ────────────────────────────────────────────────
        attendu = any(client['twEnd'] < 86400 for client in tour['customers'])

        # ── ASSERT ─────────────────────────────────────────────────
        assert tour['stats']['timeWindowsBinding'] is attendu


@pytest.mark.parametrize('tour', CAS, indirect=True)
class TestCouvertureDuService:
    """Un client se livre une fois. Pas zéro, pas deux."""

    def test_aucun_client_n_est_servi_deux_fois(self, tour):
        """Deux passages chez le même client, c'est un colis livré deux fois et
        un coursier envoyé pour rien."""
        # ── ARRANGE ────────────────────────────────────────────────
        passages = {}
        for vehicule in tour['vehicles']:
            for rang, arret in enumerate(vehicule['stops']):
                if arret['kind'] == 'customer':
                    passages.setdefault(arret['node'], []).append((vehicule['id'], rang))

        # ── ASSERT ─────────────────────────────────────────────────
        doublons = {node: lieux for node, lieux in passages.items() if len(lieux) > 1}
        assert not doublons, (
            "clients servis plusieurs fois (nœud : [(véhicule, arrêt), ...]) : "
            f"{doublons}"
        )

    def test_le_nombre_de_clients_servis_est_celui_des_arrets(self, tour):
        """`customersServed` alimente le taux de service affiché en vitrine :
        il doit se recompter sur les tournées."""
        # ── ARRANGE ────────────────────────────────────────────────
        servis = {
            arret['node']
            for vehicule in tour['vehicles']
            for arret in vehicule['stops']
            if arret['kind'] == 'customer'
        }

        # ── ASSERT ─────────────────────────────────────────────────
        assert tour['stats']['customersServed'] == len(servis), (
            f"stats.customersServed vaut {tour['stats']['customersServed']} pour "
            f"{len(servis)} clients réellement visités"
        )
        assert sum(vehicule['served'] for vehicule in tour['vehicles']) == len(servis), (
            "la somme des vehicles[].served ne recompose pas customersServed"
        )
        assert len(servis) <= tour['stats']['customers']

    def test_tout_client_servi_figure_dans_la_liste_des_clients(self, tour):
        """Un arrêt client portant un nœud inconnu de `customers` n'aurait ni
        position ni fenêtre horaire chez le consommateur."""
        # ── ARRANGE ────────────────────────────────────────────────
        connus = {client['node'] for client in tour['customers']}

        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            for arret in vehicule['stops']:
                if arret['kind'] == 'customer':
                    assert arret['node'] in connus, (
                        f"véhicule {vehicule['id']} sert le nœud {arret['node']}, "
                        f"absent de la liste des clients"
                    )


@pytest.mark.parametrize('tour', CAS, indirect=True)
class TestTransfertsEnHub:
    """
    Le rendez-vous entre coursiers, c'est-à-dire `solver.add_hub_constraints`.

    Un transfert n'a de sens que si les quatre propriétés suivantes tiennent
    ensemble : le colis déposé est repris (les deux nœuds vivent ou meurent
    ensemble), il change de porteur (véhicules distincts), il est repris après
    avoir été déposé (précédence), et il finit chez un client.

    **Deux d'entre elles ne tiennent pas aujourd'hui**, et les tests
    correspondants portent `xfail`. Le défaut, observé sur douze clients, trois
    véhicules, deux hubs et la graine 1 : un véhicule effectue les deux retraits
    en hub, ne sert **aucun** client, et rentre au dépôt avec les deux colis.
    Rien dans le modèle n'oblige un colis repris en hub à être livré ; la
    dimension de capacité compte les demandes cumulées depuis zéro, si bien que
    deux retraits sans livraison lui coûtent 2 sur 10 et passent sans encombre.
    Le défaut est ensuite masqué dans le document : `postprocessor.get_results`
    borne la charge par `max(0, min(charge, capacite))`, si bien que les deux
    retraits d'un véhicule déjà plein n'y apparaissent pas du tout.

    Les marqueurs sont non stricts : le défaut dépend de la trajectoire de la
    recherche locale, donc du budget et de la machine. Ils doivent être retirés
    dès que le modèle lie un retrait à une livraison.
    """

    def test_depot_et_retrait_d_un_hub_sont_visites_ensemble_ou_pas_du_tout(self, tour):
        """
        Un colis déposé doit être collecté, un colis collecté doit avoir été
        déposé.

        C'est l'égalité des `ActiveVar` posée par `add_hub_constraints`. Sans
        elle, le solveur ferait disparaître ou apparaître des colis en hub.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        roles = Roles(tour)
        visites = {
            arret['node']
            for vehicule in tour['vehicles']
            for arret in vehicule['stops']
        }

        # ── ASSERT ─────────────────────────────────────────────────
        for hub, (depot, retrait) in enumerate(zip(roles.depots_hub, roles.retraits_hub)):
            assert (depot in visites) == (retrait in visites), (
                f"hub {hub} : dépôt (nœud {depot}) "
                f"{'visité' if depot in visites else 'absent'} et retrait "
                f"(nœud {retrait}) {'visité' if retrait in visites else 'absent'} ; "
                "les deux doivent aller ensemble"
            )

    def test_un_transfert_met_en_jeu_deux_vehicules_distincts(self, tour):
        """
        Déposer et reprendre un colis avec le même véhicule n'est pas un
        transfert : c'est un détour gratuit.

        C'est la contrainte réifiée `IsDifferentVar(...) >= ActiveVar(dépôt)`,
        qui n'impose la différence que lorsque le rendez-vous a lieu.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        roles = Roles(tour)
        transferts = transferts_realises(tour, roles)
        if not transferts:
            pytest.skip("aucun transfert réalisé dans ce scénario")

        # ── ASSERT ─────────────────────────────────────────────────
        for transfert in transferts:
            deposants = {passage['vehicule'] for passage in transfert['depot']}
            repreneurs = {passage['vehicule'] for passage in transfert['retrait']}
            assert not (deposants & repreneurs), (
                f"hub {transfert['hub']} : le véhicule "
                f"{sorted(deposants & repreneurs)} dépose et reprend le même colis"
            )

    def test_le_depot_precede_le_retrait(self, tour):
        """On ne reprend pas un colis avant qu'il soit posé. C'est la contrainte
        de précédence sur la dimension temporelle."""
        # ── ARRANGE ────────────────────────────────────────────────
        roles = Roles(tour)
        transferts = transferts_realises(tour, roles)
        if not transferts:
            pytest.skip("aucun transfert réalisé dans ce scénario")

        # ── ASSERT ─────────────────────────────────────────────────
        for transfert in transferts:
            pose = min(passage['arrive'] for passage in transfert['depot'])
            reprise = max(passage['arrive'] for passage in transfert['retrait'])
            assert pose <= reprise, (
                f"hub {transfert['hub']} : colis repris à {reprise} s alors qu'il "
                f"n'est déposé qu'à {pose} s"
            )

    def test_les_hubs_actives_correspondent_aux_noeuds_visites(self, tour):
        """
        `hubsActivated` compte les hubs dont **l'un des trois nœuds** est visité.

        Attention au contresens : ce n'est **pas** le nombre de transferts. Le
        hub lui-même reste un nœud ordinaire, abandonnable contre une pénalité
        de 500 m seulement ; le solveur le traverse dès que le détour coûte
        moins que ça, sans qu'aucun colis ne change de mains. Sur 45 clients,
        3 véhicules, 2 hubs et la graine 42, on relève ainsi `hubsActivated == 1`
        pour **zéro** transfert : le hub est simplement sur le chemin.

        Le test affirme donc la définition réelle de l'indicateur — et vérifie
        qu'il majore le nombre de transferts, ce qui est le seul lien qu'on
        puisse en tirer.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        roles = Roles(tour)
        visites = {
            arret['node']
            for vehicule in tour['vehicles']
            for arret in vehicule['stops']
        }

        # ── ACT ────────────────────────────────────────────────────
        actives = {
            hub
            for hub, (base, depot, retrait) in enumerate(
                zip(sorted(roles.hubs), roles.depots_hub, roles.retraits_hub)
            )
            if base in visites or depot in visites or retrait in visites
        }
        transferts = transferts_realises(tour, roles)

        # ── ASSERT ─────────────────────────────────────────────────
        assert tour['stats']['hubsActivated'] == len(actives), (
            f"stats.hubsActivated vaut {tour['stats']['hubsActivated']} pour les "
            f"hubs {sorted(actives)} dont au moins un nœud est visité"
        )
        assert len(transferts) <= len(actives), (
            f"{len(transferts)} transferts pour seulement {len(actives)} hubs "
            "dont un nœud est visité"
        )
        assert tour['stats']['hubsAvailable'] == roles.nb_hubs

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "défaut du modèle : rien n'oblige un colis repris en hub à être livré. "
            "Relevé sur quatre des cinq graines à 12 clients / 3 véhicules / "
            "2 hubs — un véhicule reprend un colis puis rentre directement au "
            "dépôt (graine 1 : il reprend les deux colis et ne sert personne). "
            "Marqueur non strict : la trajectoire de la recherche locale décide "
            "quelles graines le déclenchent."
        ),
    )
    def test_un_colis_repris_en_hub_finit_chez_un_client(self, tour):
        """
        Après un retrait en hub, le véhicule doit encore avoir des clients à servir.

        C'est la raison d'être du transfert : rééquilibrer la charge entre
        coursiers. Un retrait suivi d'aucune livraison n'est pas un transfert,
        c'est un colis qui fait l'aller-retour. Le nombre de clients servis
        après le premier retrait doit donc couvrir au moins le nombre de colis
        repris par ce véhicule.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        roles = Roles(tour)
        retraits = _retraits_par_vehicule(tour, roles)
        if not retraits:
            pytest.skip("aucun retrait en hub dans ce scénario : rien à vérifier")

        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule, rangs in retraits.items():
            arrets = tour['vehicles'][vehicule]['stops']
            servis_apres = sum(
                1 for arret in arrets[rangs[0]:] if arret['kind'] == 'customer'
            )
            assert servis_apres >= len(rangs), (
                f"véhicule {vehicule} : {len(rangs)} colis repris en hub "
                f"(arrêts {rangs}) pour seulement {servis_apres} clients servis "
                f"ensuite ; la tournée est "
                f"{[arret['node'] for arret in arrets]}"
            )

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "conséquence du défaut précédent : `postprocessor.get_results` borne "
            "la charge par max(0, min(charge, capacité)), si bien qu'un retrait "
            "effectué par un véhicule encore plein n'apparaît pas dans la trace "
            "(12 clients, 3 véhicules, 2 hubs, graine 1). Marqueur non strict : "
            "le cas dépend de la trajectoire de la recherche."
        ),
    )
    def test_un_retrait_en_hub_ajoute_une_unite_a_la_charge(self, tour):
        """
        Reprendre un colis en hub augmente la charge d'exactement une unité.

        C'est le pendant de `TestCapacite.test_la_charge_suit_la_demande_du_noeud_visite`
        pour les retraits, isolé ici parce qu'il échoue : la charge publiée reste
        inchangée quand le véhicule est déjà au maximum, et le colis repris
        disparaît de la comptabilité.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        roles = Roles(tour)
        retraits = _retraits_par_vehicule(tour, roles)
        if not retraits:
            pytest.skip("aucun retrait en hub dans ce scénario : rien à vérifier")

        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule, rangs in retraits.items():
            arrets = tour['vehicles'][vehicule]['stops']
            for rang in rangs:
                avant = arrets[rang - 1]['load']
                assert arrets[rang]['load'] - avant == 1, (
                    f"véhicule {vehicule}, arrêt {rang} : retrait au nœud "
                    f"{arrets[rang]['node']} laissant la charge à "
                    f"{arrets[rang]['load']} après {avant} "
                    f"(capacité {tour['vehicles'][vehicule]['capacity']})"
                )


@pytest.mark.parametrize('tour', CAS, indirect=True)
class TestGeometrie:
    """Ce que le consommateur dessine doit correspondre à ce qu'il anime."""

    def test_chaque_couple_d_arrets_a_son_segment(self, tour):
        """L'animation associe le segment *i* aux arrêts *i* et *i+1* : un
        segment de trop ou de moins décale toute la fin de la tournée."""
        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            assert len(vehicule['legs']) == len(vehicule['stops']) - 1, (
                f"véhicule {vehicule['id']} : {len(vehicule['legs'])} segments "
                f"pour {len(vehicule['stops'])} arrêts"
            )

    def test_hors_ligne_aucun_segment_ne_se_dit_routier(self, tour):
        """
        Tous ces scénarios sont résolus avec `fetch_roads=False` : les segments
        sont des droites entre deux arrêts, et `road` doit le dire.

        Annoncer un tracé routier qu'on n'a pas laisserait croire que `roadKm`
        mesure des kilomètres de voirie, alors qu'il mesure du vol d'oiseau.
        """
        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            for rang, segment in enumerate(vehicule['legs']):
                assert segment['road'] is False, (
                    f"véhicule {vehicule['id']}, segment {rang} : annoncé routier "
                    "alors que la résolution s'est faite hors ligne"
                )
                assert len(segment['pts']) == 2, (
                    f"véhicule {vehicule['id']}, segment {rang} : "
                    f"{len(segment['pts'])} sommets pour une droite"
                )

    def test_les_arrets_sont_situes_dans_l_emprise_annoncee(self, tour):
        """`bounds` sert au cadrage initial de la carte : un arrêt en dehors
        serait invisible au chargement."""
        # ── ARRANGE ────────────────────────────────────────────────
        emprise = tour['bounds']

        # ── ASSERT ─────────────────────────────────────────────────
        for vehicule in tour['vehicles']:
            for rang, arret in enumerate(vehicule['stops']):
                assert emprise['minLat'] <= arret['lat'] <= emprise['maxLat'], (
                    f"véhicule {vehicule['id']}, arrêt {rang} : latitude "
                    f"{arret['lat']} hors de "
                    f"[{emprise['minLat']}, {emprise['maxLat']}]"
                )
                assert emprise['minLng'] <= arret['lng'] <= emprise['maxLng'], (
                    f"véhicule {vehicule['id']}, arrêt {rang} : longitude "
                    f"{arret['lng']} hors de "
                    f"[{emprise['minLng']}, {emprise['maxLng']}]"
                )
