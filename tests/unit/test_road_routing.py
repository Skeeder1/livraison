"""
Tests du cache d'itinéraires OSRM.

Le tracé routier est un agrément : il embellit la carte, il ne conditionne pas
la résolution. Le module doit donc se comporter comme tel et ne jamais faire
échouer un appel, ni quand le réseau tombe, ni quand le disque refuse l'écriture.
Ce dernier cas n'était pas couvert : l'écriture du cache se trouvait hors du
bloc protégé, si bien qu'un appel OSRM **réussi** faisait échouer la requête sur
un système de fichiers en lecture seule.
"""
import io
import json
import os

import pytest

from optimizer import road_routing

#: Racine du dépôt, pour que les sous-processus du test d'étranglement importent
#: le même `optimizer` que le reste de la suite.
RACINE_DEPOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WAYPOINTS = [(48.8566, 2.3522), (48.8584, 2.2945), (48.8606, 2.3376)]

# Réponse OSRM minimale : deux segments de deux points chacun.
OSRM_PAYLOAD = {
    "code": "Ok",
    "routes": [
        {
            "legs": [
                {"steps": [{"geometry": {"coordinates": [[2.3522, 48.8566], [2.2945, 48.8584]]}}]},
                {"steps": [{"geometry": {"coordinates": [[2.2945, 48.8584], [2.3376, 48.8606]]}}]},
            ]
        }
    ],
}


class _FakeResponse(io.StringIO):
    """Objet fichier utilisable comme gestionnaire de contexte, comme urlopen."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


@pytest.fixture(autouse=True)
def sans_etranglement(monkeypatch):
    """Supprime l'attente d'une seconde entre deux requêtes, le temps des tests.

    L'intervalle est une obligation envers le serveur de FOSSGIS, pas une
    propriété du cache ni du repli : le faire payer à chaque test qui simule un
    appel réseau rendrait la suite lente sans rien vérifier de plus. Il est
    éprouvé une fois, explicitement, par `TestEtranglement`.
    """
    monkeypatch.setattr(road_routing, "INTERVALLE_MINIMAL_S", 0.0)
    monkeypatch.setattr(road_routing, "_derniere_requete", 0.0)


@pytest.fixture
def osrm_repond(monkeypatch):
    """Remplace l'appel réseau par une réponse OSRM valide, et compte les appels."""
    appels = []

    def faux_urlopen(requete, timeout=None):
        appels.append(requete)
        return _FakeResponse(json.dumps(OSRM_PAYLOAD))

    monkeypatch.setattr(road_routing.urllib.request, "urlopen", faux_urlopen)
    return appels


class TestEtranglement:
    """Les règles du serveur public : une identité, et une requête par seconde."""

    def test_l_identite_de_l_application_est_envoyee(self, osrm_repond, cache_temporaire):
        """Les conditions de FOSSGIS écartent le `User-Agent` d'une bibliothèque.

        `urllib` annonce `Python-urllib/3.x`, précisément ce qu'elles jugent
        insuffisant, et l'usurpation vaut un blocage immédiat.
        """
        # ── ACT ────────────────────────────────────────────────────
        road_routing.fetch_route_legs(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        envoye = osrm_repond[0].get_header("User-agent")
        assert envoye == road_routing.USER_AGENT
        assert "urllib" not in envoye.lower(), "le UA d'une bibliothèque est refusé"

    def test_l_etranglement_tient_entre_processus(self, tmp_path):
        """Le débit est une obligation envers un tiers, il ne se divise pas.

        Le compteur de module a un exemplaire par processus : quatre ouvriers de
        pré-calcul émettraient quatre requêtes par seconde là où le serveur en
        autorise une. Avec `OSRM_THROTTLE_FILE`, ils se sérialisent.

        Le test lance de vrais processus. Un test à un seul processus ne
        prouverait rien : c'est précisément la frontière de processus que le
        verrou doit franchir.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        import subprocess
        import sys
        import textwrap

        verrou = tmp_path / "etranglement.lock"
        programme = textwrap.dedent(
            f"""
            import sys, time
            sys.path.insert(0, {str(RACINE_DEPOT)!r})
            from optimizer import road_routing
            for _ in range(2):
                road_routing._attendre_son_tour()
                print(time.time(), flush=True)
            """
        )
        environnement = {**os.environ, "OSRM_THROTTLE_FILE": str(verrou)}

        # ── ACT ────────────────────────────────────────────────────
        ouvriers = [
            subprocess.Popen(
                [sys.executable, "-c", programme],
                stdout=subprocess.PIPE, text=True, env=environnement,
            )
            for _ in range(3)
        ]
        dates = sorted(
            float(ligne)
            for ouvrier in ouvriers
            for ligne in ouvrier.communicate()[0].split()
        )

        # ── ASSERT ─────────────────────────────────────────────────
        assert len(dates) == 6, "les six requêtes doivent avoir été émises"
        ecarts = [b - a for a, b in zip(dates, dates[1:], strict=False)]
        assert all(ecart >= 0.95 for ecart in ecarts), (
            f"deux requêtes trop rapprochées : {[round(e, 3) for e in ecarts]}"
        )

    def test_deux_requetes_sont_espacees(self, osrm_repond, cache_temporaire, monkeypatch):
        """Une requête par seconde au plus : la géométrie est demandée une fois
        par véhicule, donc jusqu'à six fois d'affilée."""
        # ── ARRANGE ────────────────────────────────────────────────
        monkeypatch.setattr(road_routing, "INTERVALLE_MINIMAL_S", 1.0)
        monkeypatch.setattr(road_routing, "_derniere_requete", 0.0)
        dormi = []
        monkeypatch.setattr(road_routing.time, "sleep", dormi.append)

        # ── ACT ────────────────────────────────────────────────────
        road_routing._ouvrir("http://exemple/1").close()
        road_routing._ouvrir("http://exemple/2").close()

        # ── ASSERT ─────────────────────────────────────────────────
        assert len(dormi) == 1, "la seconde requête doit attendre, pas la première"
        assert 0 < dormi[0] <= 1.0, f"attente incohérente : {dormi[0]}"


@pytest.fixture
def cache_temporaire(tmp_path, monkeypatch):
    """Isole le cache du dépôt : les tests ne doivent pas polluer .cache/osrm."""
    repertoire = tmp_path / "osrm"
    monkeypatch.setenv("OSRM_CACHE_DIR", str(repertoire))
    return repertoire


class TestCacheOsrm:
    """Écriture, relecture et robustesse du cache."""

    def test_ecrit_puis_relit_sans_rappeler_le_reseau(self, osrm_repond, cache_temporaire):
        # ── ACT ────────────────────────────────────────────────────
        premier = road_routing.fetch_route_legs(WAYPOINTS)
        second = road_routing.fetch_route_legs(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        assert premier == second
        assert len(osrm_repond) == 1, "le second appel devait être servi par le cache"

    def test_l_ecriture_est_atomique(self, osrm_repond, cache_temporaire):
        """Aucun fichier temporaire ne doit survivre à une écriture réussie."""
        # ── ACT ────────────────────────────────────────────────────
        road_routing.fetch_route_legs(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        fichiers = sorted(p.name for p in cache_temporaire.iterdir())
        assert len(fichiers) == 1, f"fichiers résiduels : {fichiers}"
        assert not fichiers[0].endswith(".tmp")

    @pytest.mark.skipif(os.geteuid() == 0, reason="root écrit malgré les permissions")
    def test_un_disque_en_lecture_seule_ne_fait_pas_echouer_l_appel(
        self, osrm_repond, tmp_path, monkeypatch
    ):
        """Le cas de l'hébergement sans serveur : seul /tmp est inscriptible."""
        # ── ARRANGE ────────────────────────────────────────────────
        racine = tmp_path / "lecture-seule"
        racine.mkdir()
        racine.chmod(0o500)
        monkeypatch.setenv("OSRM_CACHE_DIR", str(racine / "osrm"))

        try:
            # ── ACT ────────────────────────────────────────────────
            legs = road_routing.fetch_route_legs(WAYPOINTS)

            # ── ASSERT ─────────────────────────────────────────────
            assert len(legs) == 2, "la géométrie OSRM doit être rendue malgré l'échec du cache"
            assert legs[0][0] == [48.8566, 2.3522]
        finally:
            racine.chmod(0o700)

    def test_une_entree_de_cache_corrompue_est_ignoree(self, osrm_repond, cache_temporaire):
        # ── ARRANGE ────────────────────────────────────────────────
        cache_temporaire.mkdir(parents=True)
        chemin = road_routing._cache_path(WAYPOINTS)
        with open(chemin, "w", encoding="utf-8") as handle:
            handle.write('[[[48.85, 2.35], [48.86')  # écriture interrompue

        # ── ACT ────────────────────────────────────────────────────
        legs = road_routing.fetch_route_legs(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        assert len(legs) == 2
        assert len(osrm_repond) == 1, "le cache illisible devait déclencher un recalcul"

    def test_le_profil_et_le_serveur_separent_les_caches(self, monkeypatch):
        """Deux moteurs de routage ne doivent jamais se relire l'un l'autre.

        Le projet livre en vélo cargo, et le serveur public de démonstration
        ignore le profil dans l'URL : `driving` et `bike` y rendent la même
        matrice voiture. Le jour où l'on pointe vers une instance qui, elle,
        sert le profil, une clé de cache aveugle au profil relirait les
        itinéraires voiture déjà écrits et le changement de moteur n'aurait
        aucun effet — sans que rien ne le signale.
        """
        # ── ARRANGE / ACT ──────────────────────────────────────────
        monkeypatch.setattr(road_routing, "OSRM_PROFILE", "driving")
        voiture = road_routing._cache_path(WAYPOINTS)
        monkeypatch.setattr(road_routing, "OSRM_PROFILE", "bike")
        velo = road_routing._cache_path(WAYPOINTS)
        monkeypatch.setattr(road_routing, "OSRM_BASE_URL", "http://localhost:5000")
        velo_ailleurs = road_routing._cache_path(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        assert voiture != velo, "le profil doit entrer dans la clé de cache"
        assert velo != velo_ailleurs, "le serveur doit entrer dans la clé de cache"

    def test_le_repertoire_est_relu_dans_l_environnement(self, tmp_path, monkeypatch):
        """`OSRM_CACHE_DIR` doit pouvoir être posée après l'import du module."""
        # ── ARRANGE ────────────────────────────────────────────────
        monkeypatch.setenv("OSRM_CACHE_DIR", str(tmp_path / "ailleurs"))

        # ── ACT ────────────────────────────────────────────────────
        chemin = road_routing._cache_path(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        assert chemin.startswith(str(tmp_path / "ailleurs"))


class TestRepliEnLigneDroite:
    """Le module ne lève jamais, et n'invente jamais de géométrie routière.

    Un échec réseau renvoie `None` par segment plutôt qu'une ligne droite.
    C'est ce qui permet à `tour_format` de marquer `legs[].road = false` : tant
    que le repli renvoyait deux points, il était indiscernable d'un vrai tracé
    et le document publié annonçait une géométrie routière hors ligne.
    """

    def test_osrm_injoignable_ne_produit_aucune_geometrie(self, cache_temporaire, monkeypatch):
        # ── ARRANGE ────────────────────────────────────────────────
        def urlopen_qui_echoue(url, timeout=None):
            raise road_routing.urllib.error.URLError("réseau coupé")

        monkeypatch.setattr(road_routing.urllib.request, "urlopen", urlopen_qui_echoue)

        # ── ACT ────────────────────────────────────────────────────
        legs = road_routing.fetch_route_legs(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        assert legs == [None, None], "un échec réseau ne fabrique pas de tracé"

    def test_une_reponse_en_erreur_ne_produit_aucune_geometrie(self, cache_temporaire, monkeypatch):
        # ── ARRANGE ────────────────────────────────────────────────
        def urlopen_en_erreur(url, timeout=None):
            return _FakeResponse(json.dumps({"code": "NoRoute"}))

        monkeypatch.setattr(road_routing.urllib.request, "urlopen", urlopen_en_erreur)

        # ── ACT ────────────────────────────────────────────────────
        legs = road_routing.fetch_route_legs(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        assert all(leg is None for leg in legs)

    def test_un_echec_n_ecrit_rien_dans_le_cache(self, cache_temporaire, monkeypatch):
        """Un repli en lignes droites ne doit pas se figer en cache."""
        # ── ARRANGE ────────────────────────────────────────────────
        def urlopen_qui_echoue(url, timeout=None):
            raise road_routing.urllib.error.URLError("réseau coupé")

        monkeypatch.setattr(road_routing.urllib.request, "urlopen", urlopen_qui_echoue)

        # ── ACT ────────────────────────────────────────────────────
        road_routing.fetch_route_legs(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        assert not cache_temporaire.exists() or not list(cache_temporaire.iterdir())


class TestBuildRoadLegs:
    """Le dictionnaire ne contient que des tracés réellement routiers."""

    def test_omet_les_segments_sans_geometrie(self, cache_temporaire, monkeypatch):
        """Hors ligne, aucune clé n'est produite.

        `tour_format` retombe alors sur le segment droit et marque
        `road: false`. Auparavant les clés existaient avec deux points, et le
        document publié annonçait `road: true` sans réseau.
        """
        # ── ARRANGE ────────────────────────────────────────────────
        def urlopen_qui_echoue(url, timeout=None):
            raise road_routing.urllib.error.URLError("réseau coupé")

        monkeypatch.setattr(road_routing.urllib.request, "urlopen", urlopen_qui_echoue)
        locations = [(48.85, 2.35), (48.86, 2.36), (48.87, 2.37)]

        # ── ACT ────────────────────────────────────────────────────
        road_legs = road_routing.build_road_legs(locations, [[0, 1, 2, 0]])

        # ── ASSERT ─────────────────────────────────────────────────
        assert road_legs == {}
