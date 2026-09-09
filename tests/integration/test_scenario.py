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

# Ce que le modèle GARANTIT sur ce scénario. Ces valeurs-là sont exactes : un
# écart est un défaut, pas une variation de machine.
REFERENCE_EXACT = {
    'customers': 45,
    'customersServed': 45,
    'hubsAvailable': 0,
    'hubsActivated': 0,
    'hubFlybys': 0,
    'tardinessMinutes': 0,
}

# Ce que la RECHERCHE produit, relevé le 2026-09-09 après calibration de
# TIME_SPAN_COEFFICIENT (cf. `experiments/`).
#
# Ces valeurs sont encadrées, pas figées, et c'est délibéré. La recherche est
# bornée en temps de mur : sur une machine plus lente, ou simplement sous
# charge, elle explore moins et atterrit ailleurs. Les figer à l'unité près
# rendait la suite rouge dès qu'une autre tâche tournait en parallèle — c'est
# arrivé pendant la campagne de calibration, sans qu'aucune régression n'existe.
#
# La tolérance de 15 % est calibrée sur l'écart interquartile mesuré entre
# graines à budget constant (makespan 1 419 s, soit ~18 % de la médiane) : elle
# laisse passer la variation de trajectoire, et rattrape une vraie régression,
# qui se compte en dizaines de pour cent.
REFERENCE_RECHERCHE = {
    'horizon': 7453,
    'cumulativeDriveTime': 21946,
    'roadKm': 139.4,
}
TOLERANCE = 0.15

# Nombre de rechargements : petit entier, donc encadré en absolu.
REFERENCE_RELOADS = 3

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

    def test_sert_tout_le_monde_sans_retard_ni_hub(self, reference_tour):
        """Ce que le modèle doit garantir, à l'unité près."""
        # ── ACT ────────────────────────────────────────────────────
        stats = reference_tour['stats']

        # ── ASSERT ─────────────────────────────────────────────────
        obtenu = {key: stats[key] for key in REFERENCE_EXACT}
        assert obtenu == REFERENCE_EXACT

    def test_reste_dans_la_plage_de_qualite_attendue(self, reference_tour):
        """La recherche doit retomber près du relevé, sans y tomber pile.

        Une égalité stricte transformerait toute variation de charge machine en
        échec. Une plage large laisse quand même passer la seule chose qu'on
        veut attraper : une régression qui dégrade la solution d'un ordre de
        grandeur.
        """
        # ── ACT / ASSERT ───────────────────────────────────────────
        for cle, attendu in REFERENCE_RECHERCHE.items():
            obtenu = reference_tour['stats'].get(cle, reference_tour.get(cle))
            assert obtenu == pytest.approx(attendu, rel=TOLERANCE), (
                f"{cle} vaut {obtenu}, attendu {attendu} à {TOLERANCE:.0%} près. "
                "La recherche est bornée en temps de mur : vérifier la charge de "
                "la machine avant de conclure à une régression."
            )
        assert reference_tour['stats']['reloads'] <= REFERENCE_RELOADS + 2

    def test_repartit_les_clients_entre_tous_les_coursiers(self, reference_tour):
        """L'équilibrage est une propriété, pas un relevé.

        Figer la répartition exacte, [19, 18, 17] hier et [16, 13, 16]
        aujourd'hui, revenait à réécrire le test à chaque changement de
        coefficient. Ce qui compte est qu'aucun coursier ne reste à quai et
        qu'aucun ne prenne tout.
        """
        # ── ACT ────────────────────────────────────────────────────
        servis = [v['served'] for v in reference_tour['vehicles']]

        # ── ASSERT ─────────────────────────────────────────────────
        assert sum(servis) == 45
        assert all(n > 0 for n in servis), f"un coursier ne sert personne : {servis}"
        assert max(servis) <= 2 * min(servis), f"répartition très déséquilibrée : {servis}"

    def test_reproduit_le_kilometrage_routier(self, reference_tour):
        """Ne vaut que si OSRM a répondu : à défaut, le tracé est en lignes
        droites et le kilométrage mesure du vol d'oiseau."""
        # ── ARRANGE ────────────────────────────────────────────────
        if not _road_geometry_available(reference_tour):
            pytest.skip("OSRM injoignable : tracé en lignes droites, kilométrage non comparable")

        # ── ASSERT ─────────────────────────────────────────────────
        assert reference_tour['stats']['roadKm'] == pytest.approx(
            REFERENCE_RECHERCHE['roadKm'], rel=TOLERANCE
        )

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
