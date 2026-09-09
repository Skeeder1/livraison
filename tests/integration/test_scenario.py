"""
Tests de bout en bout de `optimizer.scenario.solve_scenario`.

Ces tests font réellement tourner OR-Tools. Le plus long, celui du scénario de
référence, consomme son budget complet de 30 secondes : il porte la marque
`slow`, et `pytest -m "not slow"` le laisse de côté.

Ce qu'il verrouille mérite ce prix : le scénario servi en vitrine. Toute dérive
de ces valeurs signale que la démonstration ne rejoue plus le même problème.
"""
import pytest

from optimizer.scenario import (
    SCENARIO_DEFAULTS,
    SCENARIO_LIMITS,
    NoSolutionError,
    ScenarioParamsError,
    solve_scenario,
)
from tests.tour_invariants import assert_tour_invariants

# Scénario de référence : 45 clients, 3 véhicules, aucun hub, graine 42,
# budget 30 s. Ce sont les valeurs par défaut, laissées explicites pour que le
# test dise lui-même ce qu'il rejoue.
REFERENCE_PARAMS = {
    'customers': 45,
    'vehicles': 3,
    'hubs': 0,
    'capacity': 10,
    'budget_seconds': 30,
    'seed': 42,
}

# Relevé sur ce scénario après le retrait effectif des hubs (`strip_hubs`),
# puis remis à jour après la correction du coût d'arc en distance (la
# troncature `int()` ramenait à zéro les 420 arcs de la matrice, et la métrique
# ignorait le cos(latitude) — voir `optimizer/config.py`).
#
# La durée cumulée monte de 21 415 s à 23 333 s parce que le temps de trajet
# est désormais calibré à 20 km/h sur une distance réelle, contre une vitesse
# implicite trop optimiste auparavant. Le kilométrage, lui, ne bouge presque
# pas (150,3 → 149,2 km) : la distance était déjà minimisée indirectement, le
# temps de trajet étant proportionnel à elle.
#
# Ces valeurs ne sont PAS celles de l'instantané publié dans le portfolio
# (`delivery-tour.json` : horizon 7178, 21516 s cumulées, 140,9 km, arrêts
# 20/17/19, 2 passages en hub). Cet instantané provient de la variante « sans
# hubs » défectueuse, qui laissait les deux nœuds de hub dans le modèle en
# passages obligatoires. Les livreurs les traversaient sous contrainte.
REFERENCE_STATS = {
    'horizon': 7791,
    'cumulativeDriveTime': 23333,
    'reloads': 3,
    'customers': 45,
    'customersServed': 45,
    'hubsAvailable': 0,
    'hubsActivated': 0,
    'hubFlybys': 0,
    'tardinessMinutes': 0,
}
REFERENCE_STOPS_PER_VEHICLE = [19, 18, 17]
REFERENCE_ROAD_KM = 149.2

# Un scénario minuscule suffit pour tout ce qui ne dépend pas des valeurs de
# référence : la forme du document et la stabilité des appels.
SMALL_PARAMS = {'customers': 10, 'vehicles': 2, 'hubs': 0, 'budget_seconds': 2}


@pytest.fixture(scope='module')
def reference_tour(tmp_path_factory):
    """Résout le scénario de référence une seule fois pour tout le module."""
    workdir = tmp_path_factory.mktemp('reference')
    return solve_scenario(REFERENCE_PARAMS, workdir=workdir)


def _road_geometry_available(tour):
    """
    Vrai si OSRM a réellement répondu.

    `road_routing` ne lève jamais : réseau coupé, il rend des segments droits
    sous les mêmes clés, et le champ `road` reste à vrai. Le seul indice fiable
    est donc la forme du tracé : un itinéraire routier compte plus de deux
    sommets, une droite exactement deux.
    """
    return any(len(leg['pts']) > 2 for veh in tour['vehicles'] for leg in veh['legs'])


@pytest.mark.slow
class TestScenarioDeReference:
    """Le scénario de vitrine, rejoué à l'identique."""

    def test_reproduit_les_indicateurs_de_reference(self, reference_tour):
        # ── ACT ────────────────────────────────────────────────────
        stats = reference_tour['stats']

        # ── ASSERT ─────────────────────────────────────────────────
        obtenu = {key: stats[key] for key in REFERENCE_STATS}
        assert obtenu == REFERENCE_STATS, (
            "les indicateurs s'écartent du relevé de référence.\n"
            "La recherche est bornée en temps : sur une machine sensiblement plus "
            "lente, ou sous forte charge, la trajectoire de la recherche locale "
            "diffère et ces valeurs bougent sans qu'il y ait de régression. "
            "Vérifier d'abord ce point avant de conclure à un défaut."
        )

    def test_reproduit_la_repartition_des_arrets(self, reference_tour):
        # ── ACT ────────────────────────────────────────────────────
        stops = [len(v['stops']) for v in reference_tour['vehicles']]

        # ── ASSERT ─────────────────────────────────────────────────
        assert stops == REFERENCE_STOPS_PER_VEHICLE
        assert sum(v['served'] for v in reference_tour['vehicles']) == 45

    def test_reproduit_le_kilometrage_routier(self, reference_tour):
        """Ne vaut que si OSRM a répondu : à défaut, le tracé est en lignes
        droites et le kilométrage mesure du vol d'oiseau."""
        # ── ARRANGE ────────────────────────────────────────────────
        if not _road_geometry_available(reference_tour):
            pytest.skip("OSRM injoignable : tracé en lignes droites, kilométrage non comparable")

        # ── ASSERT ─────────────────────────────────────────────────
        assert reference_tour['stats']['roadKm'] == REFERENCE_ROAD_KM

    def test_respecte_les_invariants_du_consommateur(self, reference_tour):
        # ── ASSERT ─────────────────────────────────────────────────
        assert_tour_invariants(reference_tour)

    def test_decrit_sa_propre_provenance(self, reference_tour):
        # ── ACT ────────────────────────────────────────────────────
        meta = reference_tour['meta']

        # ── ASSERT ─────────────────────────────────────────────────
        assert meta['seed'] == 42
        assert meta['budgetSeconds'] == 30
        assert 'OR-Tools' in meta['solver']


class TestSolveScenario:
    """Comportement général de l'API, sur un scénario court."""

    def test_produit_un_document_conforme(self, tmp_path):
        # ── ACT ────────────────────────────────────────────────────
        tour = solve_scenario(SMALL_PARAMS, workdir=tmp_path, fetch_roads=False)

        # ── ASSERT ─────────────────────────────────────────────────
        assert_tour_invariants(tour)
        assert tour['stats']['customers'] == 10
        assert tour['stats']['vehicles'] == 2

    def test_sans_hub_aucun_hub_ne_subsiste(self, tmp_path):
        """À `hubs` 0, aucun nœud de hub ne doit rester dans les tournées.

        L'implémentation précédente de la variante sans hubs se contentait de
        mettre `num_hubs` à 0 : les nœuds restaient dans le modèle, sans
        disjonction, donc obligatoires. Les tournées les traversaient sous
        contrainte pendant que l'indicateur annonçait 0 hub activé.
        """
        # ── ACT ────────────────────────────────────────────────────
        tour = solve_scenario(SMALL_PARAMS, workdir=tmp_path, fetch_roads=False)

        # ── ASSERT ─────────────────────────────────────────────────
        assert tour['hubs'] == []
        assert tour['stats']['hubsAvailable'] == 0
        assert tour['stats']['hubFlybys'] == 0
        arrets = [stop for veh in tour['vehicles'] for stop in veh['stops']]
        assert not [stop for stop in arrets if stop['kind'] == 'hub']
        # Les nœuds au-delà des clients ne peuvent plus être que des
        # rechargements au dépôt.
        assert max(stop['node'] for stop in arrets) < 1 + 10 + 10

    def test_deux_appels_successifs_donnent_le_meme_resultat(self, tmp_path):
        """Le scénario est reproductible dans un même processus : graine fixée,
        configuration restaurée en sortie."""
        # ── ACT ────────────────────────────────────────────────────
        premier = solve_scenario(SMALL_PARAMS, workdir=tmp_path / 'a', fetch_roads=False)
        second = solve_scenario(SMALL_PARAMS, workdir=tmp_path / 'b', fetch_roads=False)

        # ── ASSERT ─────────────────────────────────────────────────
        for document in (premier, second):
            # Seul le temps de calcul mesuré diffère d'un appel à l'autre.
            document['meta'].pop('solveSeconds')
        assert premier == second

    def test_un_scenario_intercale_ne_contamine_pas_le_suivant(self, tmp_path):
        """`Config` porte des attributs de classe : sans restauration, le
        scénario précédent déborderait sur le suivant."""
        # ── ARRANGE ────────────────────────────────────────────────
        attendu = solve_scenario(SMALL_PARAMS, workdir=tmp_path / 'avant', fetch_roads=False)
        solve_scenario(
            {'customers': 20, 'vehicles': 3, 'hubs': 0, 'capacity': 5, 'budget_seconds': 2},
            workdir=tmp_path / 'autre',
            fetch_roads=False,
        )

        # ── ACT ────────────────────────────────────────────────────
        obtenu = solve_scenario(SMALL_PARAMS, workdir=tmp_path / 'apres', fetch_roads=False)

        # ── ASSERT ─────────────────────────────────────────────────
        for document in (attendu, obtenu):
            document['meta'].pop('solveSeconds')
        assert obtenu == attendu

    def test_sans_geometrie_routiere_les_segments_restent_tracables(self, tmp_path):
        # ── ACT ────────────────────────────────────────────────────
        tour = solve_scenario(SMALL_PARAMS, workdir=tmp_path, fetch_roads=False)

        # ── ASSERT ─────────────────────────────────────────────────
        segments = [leg for veh in tour['vehicles'] for leg in veh['legs']]
        assert segments
        assert all(len(leg['pts']) == 2 and leg['road'] is False for leg in segments)

    def test_des_fenetres_horaires_contraignantes_sont_signalees(self, tmp_path):
        # ── ACT ────────────────────────────────────────────────────
        tour = solve_scenario(
            {**SMALL_PARAMS, 'time_windows_binding': True},
            workdir=tmp_path,
            fetch_roads=False,
        )

        # ── ASSERT ─────────────────────────────────────────────────
        assert tour['stats']['timeWindowsBinding'] is True
        assert all(client['twEnd'] < 86400 for client in tour['customers'])

    def test_cree_le_repertoire_de_travail(self, tmp_path):
        """Le jeu de données est écrit là où l'appelant le demande, jamais
        relativement au répertoire courant du processus."""
        # ── ARRANGE ────────────────────────────────────────────────
        workdir = tmp_path / 'inexistant' / 'encore'

        # ── ACT ────────────────────────────────────────────────────
        solve_scenario(SMALL_PARAMS, workdir=workdir, fetch_roads=False)

        # ── ASSERT ─────────────────────────────────────────────────
        assert (workdir / 'colis.json').exists()
        assert (workdir / 'distance_matrix.npy').exists()

    def test_transferts_en_hub_actives(self, tmp_path):
        """Avec des hubs, le solveur ajoute nœuds et véhicules fictifs :
        le document ne doit décrire que les véhicules qui roulent."""
        # ── ACT ────────────────────────────────────────────────────
        tour = solve_scenario(
            {**SMALL_PARAMS, 'hubs': 2, 'budget_seconds': 3},
            workdir=tmp_path,
            fetch_roads=False,
        )

        # ── ASSERT ─────────────────────────────────────────────────
        assert_tour_invariants(tour)
        assert tour['stats']['vehicles'] == 2, "les véhicules fictifs ne se dessinent pas"
        assert tour['stats']['hubsAvailable'] == 2, (
            "seuls les hubs comptent, pas leurs points de dépôt et de retrait"
        )


class TestValidationDesParametres:
    """Les bornes sont appliquées côté serveur, avant tout calcul."""

    def test_refuse_une_cle_inconnue(self, tmp_path):
        # ── ACT / ASSERT ───────────────────────────────────────────
        with pytest.raises(ScenarioParamsError, match='inconnus'):
            solve_scenario({'nb_clients': 10}, workdir=tmp_path)

    @pytest.mark.parametrize('cle', sorted(SCENARIO_LIMITS))
    def test_refuse_une_valeur_hors_bornes(self, cle, tmp_path):
        # ── ARRANGE ────────────────────────────────────────────────
        _, maximum = SCENARIO_LIMITS[cle]

        # ── ACT / ASSERT ───────────────────────────────────────────
        with pytest.raises(ScenarioParamsError, match='compris entre'):
            solve_scenario({cle: maximum + 1}, workdir=tmp_path)

    def test_refuse_un_budget_nul(self, tmp_path):
        # ── ACT / ASSERT ───────────────────────────────────────────
        with pytest.raises(ScenarioParamsError):
            solve_scenario({'budget_seconds': 0}, workdir=tmp_path)

    def test_refuse_un_booleen_mal_type(self, tmp_path):
        # ── ACT / ASSERT ───────────────────────────────────────────
        with pytest.raises(ScenarioParamsError, match='booléen'):
            solve_scenario({'time_windows_binding': 'oui'}, workdir=tmp_path)

    def test_les_defauts_sont_ceux_du_scenario_de_reference(self):
        """Un appel sans paramètre doit rejouer la démonstration."""
        # ── ASSERT ─────────────────────────────────────────────────
        for cle, valeur in REFERENCE_PARAMS.items():
            assert SCENARIO_DEFAULTS[cle] == valeur

    def test_toutes_les_bornes_ont_un_defaut_valide(self):
        """Une borne sans valeur par défaut correspondante serait inapplicable."""
        # ── ASSERT ─────────────────────────────────────────────────
        for cle, (minimum, maximum) in SCENARIO_LIMITS.items():
            assert minimum <= SCENARIO_DEFAULTS[cle] <= maximum


def test_l_erreur_d_absence_de_solution_est_typee():
    """Un appelant serveur doit pouvoir distinguer « pas de solution » d'un
    défaut de programmation."""
    # ── ASSERT ─────────────────────────────────────────────────────
    assert issubclass(NoSolutionError, RuntimeError)
    assert issubclass(ScenarioParamsError, ValueError)
