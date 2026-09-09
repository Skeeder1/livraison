"""
Tests du journal JSONL et de la reprise.

Ces tests encodent la promesse de robustesse du harnais : une campagne
interrompue ne perd que les exécutions en vol, et une relance ne refait pas ce
qui est déjà mesuré. Le cas de la **ligne tronquée en fin de fichier** est
traité à part : c'est la signature d'une coupure au milieu d'une écriture, et
elle doit être absorbée en silence, alors qu'une ligne illisible au milieu du
journal doit lever.
"""
from __future__ import annotations

import json

import pytest

from experiments.store import ResultStore, completed_keys, iter_rows, read_rows


def make_row(config_key="abc123", seed=1000, ok=True):
    return {"config_key": config_key, "seed": seed, "ok": ok, "stats": {"customersServed": 45}}


class TestResultStore:
    def test_écrit_une_ligne_json_par_exécution(self, tmp_path):
        path = tmp_path / "resultats.jsonl"
        with ResultStore(path) as store:
            store.append(make_row(seed=1))
            store.append(make_row(seed=2))
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["seed"] == 1

    def test_chaque_ligne_est_lisible_avant_la_fermeture(self, tmp_path):
        # C'est la propriété qui permet de suivre `wc -l` pendant la campagne et
        # de ne rien perdre à un plantage.
        path = tmp_path / "resultats.jsonl"
        with ResultStore(path) as store:
            store.append(make_row(seed=1))
            assert len(read_rows(path)) == 1
            store.append(make_row(seed=2))
            assert len(read_rows(path)) == 2

    def test_ajoute_à_la_suite_d_un_fichier_existant(self, tmp_path):
        path = tmp_path / "resultats.jsonl"
        with ResultStore(path) as store:
            store.append(make_row(seed=1))
        with ResultStore(path) as store:
            store.append(make_row(seed=2))
        assert [row["seed"] for row in read_rows(path)] == [1, 2]

    def test_crée_les_répertoires_manquants(self, tmp_path):
        path = tmp_path / "a" / "b" / "resultats.jsonl"
        with ResultStore(path) as store:
            store.append(make_row())
        assert path.exists()

    def test_compte_les_lignes_écrites(self, tmp_path):
        with ResultStore(tmp_path / "r.jsonl") as store:
            store.append(make_row())
            store.append(make_row())
            assert store.written == 2

    def test_refuse_d_écrire_hors_contexte(self, tmp_path):
        store = ResultStore(tmp_path / "r.jsonl")
        with pytest.raises(RuntimeError):
            store.append(make_row())

    def test_sérialise_les_valeurs_non_json_sans_planter(self, tmp_path):
        # Une exception capturée peut arriver dans la ligne sous une forme
        # inattendue ; perdre la campagne pour un `default=` manquant serait absurde.
        from pathlib import Path

        path = tmp_path / "r.jsonl"
        with ResultStore(path) as store:
            store.append({"config_key": "k", "seed": 1, "chemin": Path("/tmp/x")})
        assert read_rows(path)[0]["chemin"] == "/tmp/x"


class TestReadRows:
    def test_fichier_absent_donne_une_liste_vide(self, tmp_path):
        assert read_rows(tmp_path / "rien.jsonl") == []

    def test_ignore_les_lignes_vides(self, tmp_path):
        path = tmp_path / "r.jsonl"
        path.write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf-8")
        assert len(read_rows(path)) == 2

    def test_absorbe_une_dernière_ligne_tronquée(self, tmp_path):
        # Coupure au milieu d'une écriture : les lignes complètes restent lisibles.
        path = tmp_path / "r.jsonl"
        path.write_text('{"a": 1}\n{"a": 2}\n{"a": 3, "incom', encoding="utf-8")
        assert [row["a"] for row in read_rows(path)] == [1, 2]

    def test_lève_sur_une_ligne_illisible_au_milieu(self, tmp_path):
        path = tmp_path / "r.jsonl"
        path.write_text('{"a": 1}\ncassé\n{"a": 3}\n', encoding="utf-8")
        with pytest.raises(ValueError, match="illisible au milieu"):
            read_rows(path)

    def test_ignore_les_lignes_qui_ne_sont_pas_des_objets(self, tmp_path):
        path = tmp_path / "r.jsonl"
        path.write_text('{"a": 1}\n[1, 2]\n', encoding="utf-8")
        assert len(read_rows(path)) == 1


class TestIterRows:
    def test_ignore_silencieusement_toute_ligne_illisible(self, tmp_path):
        # Contrairement à read_rows : ce mode sert à surveiller un fichier
        # en cours d'écriture, où une ligne partielle est normale.
        path = tmp_path / "r.jsonl"
        path.write_text('{"a": 1}\ncassé\n{"a": 3}\n', encoding="utf-8")
        assert [row["a"] for row in iter_rows(path)] == [1, 3]

    def test_fichier_absent_ne_produit_rien(self, tmp_path):
        assert list(iter_rows(tmp_path / "rien.jsonl")) == []


class TestCompletedKeys:
    def test_rend_les_couples_configuration_graine(self, tmp_path):
        path = tmp_path / "r.jsonl"
        with ResultStore(path) as store:
            store.append(make_row("aaa", 1000))
            store.append(make_row("bbb", 1000))
            store.append(make_row("aaa", 1001))
        assert completed_keys(path) == {("aaa", 1000), ("bbb", 1000), ("aaa", 1001)}

    def test_un_échec_compte_comme_fait(self, tmp_path):
        # Le rejouer à l'identique redonnerait le même échec en consommant le
        # même budget : sa cause est journalisée, cela suffit.
        path = tmp_path / "r.jsonl"
        with ResultStore(path) as store:
            store.append(make_row("aaa", 1000, ok=False))
        assert ("aaa", 1000) in completed_keys(path)

    def test_ignore_une_ligne_sans_clé_ou_sans_graine(self, tmp_path):
        path = tmp_path / "r.jsonl"
        path.write_text('{"seed": 1}\n{"config_key": "a"}\n{"config_key":"b","seed":2}\n', encoding="utf-8")
        assert completed_keys(path) == {("b", 2)}

    def test_fichier_absent_donne_un_ensemble_vide(self, tmp_path):
        assert completed_keys(tmp_path / "rien.jsonl") == set()


class TestRepriseBoutEnBout:
    def test_une_campagne_interrompue_reprend_où_elle_en_est(self, tmp_path):
        """Scénario complet : développer, exécuter la moitié, reprendre."""
        from experiments.grid import expand, filter_pending

        defaults = {"TIME_SPAN_COEFFICIENT": 200}
        spec = {
            "name": "reprise",
            "scenario": {"customers": 4, "vehicles": 1},
            "scenario_variants": [{"hubs": 0}],
            "sweeps": [{"factor": "TIME_SPAN_COEFFICIENT", "values": [50, 200]}],
        }
        campaign = expand(spec, [1, 2], defaults=defaults)
        assert len(campaign.runs) == 4  # 2 configurations × 2 graines

        path = tmp_path / "r.jsonl"
        with ResultStore(path) as store:
            for run in campaign.runs[:2]:
                store.append({"config_key": run.config_key, "seed": run.seed, "ok": True})

        pending = filter_pending(campaign.runs, completed_keys(path))
        assert len(pending) == 2
        assert [run.seed for run in pending] == [2, 2]

        # Une seconde reprise, une fois tout journalisé, ne laisse rien.
        with ResultStore(path) as store:
            for run in pending:
                store.append({"config_key": run.config_key, "seed": run.seed, "ok": True})
        assert filter_pending(campaign.runs, completed_keys(path)) == []
