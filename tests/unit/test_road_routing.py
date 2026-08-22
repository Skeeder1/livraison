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


@pytest.fixture
def osrm_repond(monkeypatch):
    """Remplace l'appel réseau par une réponse OSRM valide, et compte les appels."""
    appels = []

    def faux_urlopen(url, timeout=None):
        appels.append(url)
        return _FakeResponse(json.dumps(OSRM_PAYLOAD))

    monkeypatch.setattr(road_routing.urllib.request, "urlopen", faux_urlopen)
    return appels


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

    def test_le_repertoire_est_relu_dans_l_environnement(self, tmp_path, monkeypatch):
        """`OSRM_CACHE_DIR` doit pouvoir être posée après l'import du module."""
        # ── ARRANGE ────────────────────────────────────────────────
        monkeypatch.setenv("OSRM_CACHE_DIR", str(tmp_path / "ailleurs"))

        # ── ACT ────────────────────────────────────────────────────
        chemin = road_routing._cache_path(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        assert chemin.startswith(str(tmp_path / "ailleurs"))


class TestRepliEnLigneDroite:
    """Le module ne lève jamais, quoi que fasse le réseau."""

    def test_osrm_injoignable_donne_des_segments_droits(self, cache_temporaire, monkeypatch):
        # ── ARRANGE ────────────────────────────────────────────────
        def urlopen_qui_echoue(url, timeout=None):
            raise road_routing.urllib.error.URLError("réseau coupé")

        monkeypatch.setattr(road_routing.urllib.request, "urlopen", urlopen_qui_echoue)

        # ── ACT ────────────────────────────────────────────────────
        legs = road_routing.fetch_route_legs(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        assert legs == [
            [list(WAYPOINTS[0]), list(WAYPOINTS[1])],
            [list(WAYPOINTS[1]), list(WAYPOINTS[2])],
        ]

    def test_une_reponse_en_erreur_donne_des_segments_droits(self, cache_temporaire, monkeypatch):
        # ── ARRANGE ────────────────────────────────────────────────
        def urlopen_en_erreur(url, timeout=None):
            return _FakeResponse(json.dumps({"code": "NoRoute"}))

        monkeypatch.setattr(road_routing.urllib.request, "urlopen", urlopen_en_erreur)

        # ── ACT ────────────────────────────────────────────────────
        legs = road_routing.fetch_route_legs(WAYPOINTS)

        # ── ASSERT ─────────────────────────────────────────────────
        assert all(len(leg) == 2 for leg in legs)

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
