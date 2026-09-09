"""
Exécution d'une configuration sur une graine, dans un processus dédié.

Pourquoi un processus système et non un fil d'exécution
-------------------------------------------------------

`optimizer.config.Config` n'a que des attributs de **classe** : ils sont donc
partagés par tout le processus. `solve_scenario` les écrit, puis les restaure en
sortie, ce qui suffit à des appels **séquentiels** et à rien d'autre. Par
ailleurs `create_toy_data` initialise le générateur aléatoire **global** de
NumPy. Deux configurations évaluées en parallèle dans le même processus se
corrompraient donc mutuellement, en silence, et la campagne mesurerait un
mélange de deux réglages sans jamais lever d'exception.

Un processus par exécution, sans réutilisation, ferme la question : chaque
exécution part d'un interpréteur neuf, écrit ses facteurs, résout, rend sa ligne
et meurt. Le surcoût — quelques secondes d'import d'OR-Tools — est négligeable
devant un budget de résolution de dix secondes, et il achète une garantie que
nul verrou ne donnerait aussi simplement.

Chaque exécution reçoit également **son propre répertoire de travail** :
`create_toy_data` y écrit six fichiers que `load_data` relit ensuite. Un
répertoire partagé ferait relire à une exécution les données d'une autre.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import platform
import shutil
import time
import traceback
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.grid import RunSpec

#: Version du schéma de ligne. À incrémenter si le contenu d'une ligne change de
#: sens, pour qu'une analyse refuse de mélanger deux générations de mesures.
SCHEMA_VERSION = 1

#: Statistiques relevées sur le document de tournée. Toutes celles que produit
#: `optimizer.tour_format.build_tour`, y compris celles qui ne participent pas au
#: critère : elles ne coûtent rien à enregistrer et permettront de relire la
#: campagne autrement sans avoir à la relancer.
TOUR_STATS = (
    "customers",
    "customersServed",
    "vehicles",
    "capacity",
    "roadKm",
    "horizon",
    "cumulativeDriveTime",
    "tardinessMinutes",
    "hubsAvailable",
    "hubsActivated",
    "reloads",
    "hubFlybys",
    "timeWindowsBinding",
)

#: Marge accordée au-delà du budget de résolution avant de tuer un processus.
#: OR-Tools respecte sa limite de temps, mais la génération des données, l'import
#: du paquet et la mise en forme du document s'y ajoutent. Un facteur généreux
#: évite de tuer une exécution lente ; le but est d'attraper un blocage franc,
#: pas de chronométrer.
TIMEOUT_MULTIPLIER = 6
TIMEOUT_OVERHEAD_SECONDS = 120


def run_one(spec: dict[str, Any], scratch_root: str, *, keep_workdir: bool = False) -> dict[str, Any]:
    """
    Exécute une configuration et retourne sa ligne de résultat.

    **Cette fonction est destinée à s'exécuter dans un processus fils dédié.**
    Elle écrit dans `optimizer.config.Config` sans rien restaurer : c'est licite
    parce que le processus meurt juste après.

    Aucune exception ne remonte : un échec de résolution est un **résultat**, pas
    un incident. Il est journalisé avec son message et sa trace, et la campagne
    continue. Une campagne qui s'arrête au premier plantage perd les mesures
    qu'elle aurait faites pendant la nuit.

    :param spec: Exécution sérialisée, telle que produite par `spec_to_payload`
    :param scratch_root: Répertoire racine où créer le répertoire de travail
    :param keep_workdir: Conserve le répertoire de travail après l'exécution,
        pour inspecter les données d'une exécution suspecte
    :return: Ligne de résultat, prête à être journalisée
    """
    started_wall = time.monotonic()
    row: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "config_key": spec["config_key"],
        "config_label": spec["label"],
        "is_baseline": spec["is_baseline"],
        "memberships": [list(m) for m in spec["memberships"]],
        "factors": dict(spec["factors"]),
        "scenario": dict(spec["scenario"]),
        "budget_seconds": spec["budget_seconds"],
        "seed": spec["seed"],
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": platform.node(),
        "pid": os.getpid(),
        "ok": False,
        "error": None,
        "traceback": None,
        "stats": None,
        "wall_seconds": None,
    }

    workdir = Path(scratch_root) / f"{spec['config_key']}-s{spec['seed']}-{os.getpid()}"

    try:
        from optimizer.config import Config
        from optimizer.scenario import solve_scenario

        for name, value in spec["factors"].items():
            if not hasattr(Config, name):
                raise AttributeError(
                    f"{name} n'est pas un attribut de Config : le facteur n'est pas branché"
                )
            setattr(Config, name, value)

        # On relit les facteurs *après* écriture et on les journalise. C'est la
        # preuve, ligne par ligne, que la configuration mesurée est bien celle
        # demandée — et non celle qu'un autre module aurait réécrite entre-temps.
        row["factors_effective"] = {name: getattr(Config, name) for name in spec["factors"]}

        params = dict(spec["scenario"])
        params["seed"] = spec["seed"]
        params["budget_seconds"] = spec["budget_seconds"]

        # `fetch_roads=False` : aucun appel réseau. La campagne devient
        # reproductible hors ligne et bien plus rapide. Le prix est connu et
        # assumé — `roadKm` mesure alors des segments droits et non le réseau
        # routier, si bien que sa valeur absolue n'est **pas** comparable à celle
        # d'une exécution avec OSRM. Comme *toutes* les configurations subissent
        # la même convention, la comparaison entre configurations reste valide.
        # Une campagne ne doit jamais mélanger les deux modes.
        tour = solve_scenario(params, workdir=workdir, fetch_roads=False)

        stats = dict(tour.get("stats") or {})
        row["stats"] = {name: stats.get(name) for name in TOUR_STATS}
        # `horizon` existe aussi à la racine du document ; on garde la valeur de
        # `stats`, mais on signale une divergence si les deux se contredisent.
        if tour.get("horizon") != stats.get("horizon"):
            row["warning"] = (
                f"horizon racine {tour.get('horizon')} != stats {stats.get('horizon')}"
            )
        row["solve_seconds"] = (tour.get("meta") or {}).get("solveSeconds")
        row["ok"] = True

    except BaseException as exc:  # noqa: BLE001 — un échec est une donnée
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["traceback"] = traceback.format_exc(limit=12)

    finally:
        row["wall_seconds"] = round(time.monotonic() - started_wall, 3)
        if not keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)

    return row


def spec_to_payload(spec: RunSpec) -> dict[str, Any]:
    """
    Sérialise une `RunSpec` pour la transmettre à un processus fils.

    :param spec: Exécution planifiée
    :return: Dictionnaire simple, picklable et journalisable tel quel
    """
    return {
        "config_key": spec.config_key,
        "label": spec.label,
        "factors": dict(spec.factors),
        "scenario": dict(spec.scenario),
        "budget_seconds": spec.budget_seconds,
        "seed": spec.seed,
        "memberships": [list(m) for m in spec.memberships],
        "is_baseline": spec.is_baseline,
    }


def _child_entry(payload_json: str, scratch_root: str, keep_workdir: bool, conn: Any) -> None:
    """
    Point d'entrée du processus fils : exécute, renvoie la ligne, se tait.

    La charge utile transite en JSON plutôt qu'en objet pickle pour que le
    contrat entre parent et fils soit exactement celui du journal.

    :param payload_json: `spec_to_payload` sérialisé
    :param scratch_root: Répertoire racine des répertoires de travail
    :param keep_workdir: Conserve le répertoire de travail
    :param conn: Extrémité fille du tube de retour
    """
    try:
        row = run_one(json.loads(payload_json), scratch_root, keep_workdir=keep_workdir)
        conn.send(json.dumps(row, ensure_ascii=False, default=str))
    except BaseException as exc:  # noqa: BLE001
        conn.send(json.dumps({"__child_error__": f"{type(exc).__name__}: {exc}"}))
    finally:
        conn.close()


class RunPool:
    """
    Ordonnanceur : N exécutions en vol, un processus neuf par exécution.

    `multiprocessing.Pool` conviendrait presque, mais il ne sait pas imposer un
    **délai maximal par tâche**. Or une résolution bloquée immobiliserait un
    créneau jusqu'à la fin de la campagne, et une campagne nocturne se réveille
    alors à moitié faite sans que rien n'ait signalé le problème. L'ordonnanceur
    ci-dessous tue tout processus qui dépasse son délai et journalise l'incident
    comme un résultat ordinaire.

    .. warning::

       La méthode de démarrage est « spawn » : le processus fils **réimporte** le
       module principal. Tout script appelant `RunPool` doit donc protéger son
       code de lancement par ``if __name__ == "__main__":``, faute de quoi chaque
       fils relance la campagne entière et échoue. Les points d'entrée du paquet
       le font déjà ; un script d'analyse écrit à la main doit y penser. Le
       symptôme est net : *toutes* les exécutions échouent d'un coup, avec un
       message de `multiprocessing` sur `freeze_support`.
    """

    def __init__(
        self,
        workers: int,
        scratch_root: Path,
        *,
        keep_workdirs: bool = False,
        timeout_seconds: float | None = None,
    ) -> None:
        """
        :param workers: Nombre d'exécutions simultanées
        :param scratch_root: Répertoire racine des répertoires de travail
        :param keep_workdirs: Conserve les répertoires de travail
        :param timeout_seconds: Délai maximal par exécution ; par défaut
            `TIMEOUT_MULTIPLIER × budget + TIMEOUT_OVERHEAD_SECONDS`
        """
        if workers < 1:
            raise ValueError(f"Il faut au moins un processus, reçu {workers}")
        self.workers = workers
        self.scratch_root = Path(scratch_root)
        self.keep_workdirs = keep_workdirs
        self.timeout_seconds = timeout_seconds
        # « spawn » plutôt que « fork » : le fils repart d'un interpréteur vierge,
        # sans hériter d'un état du parent qu'on aurait oublié.
        self._ctx = mp.get_context("spawn")

    def _timeout_for(self, spec: RunSpec) -> float:
        if self.timeout_seconds is not None:
            return float(self.timeout_seconds)
        return TIMEOUT_MULTIPLIER * spec.budget_seconds + TIMEOUT_OVERHEAD_SECONDS

    def imap(self, specs: Iterable[RunSpec]) -> Iterator[dict[str, Any]]:
        """
        Exécute les spécifications et rend les lignes **au fur et à mesure**.

        L'ordre de sortie n'est pas celui d'entrée : les lignes sortent dans
        l'ordre d'achèvement, pour que l'appelant puisse les journaliser sans
        attendre. L'ordre du journal n'a aucune importance, l'analyse regroupant
        par `(config_key, seed)`.

        :param specs: Exécutions à réaliser
        :return: Itérateur sur les lignes de résultat
        """
        self.scratch_root.mkdir(parents=True, exist_ok=True)
        pending = iter(specs)
        in_flight: list[dict[str, Any]] = []
        exhausted = False

        while True:
            while not exhausted and len(in_flight) < self.workers:
                try:
                    spec = next(pending)
                except StopIteration:
                    exhausted = True
                    break
                in_flight.append(self._launch(spec))

            if not in_flight:
                return

            time.sleep(0.05)

            still: list[dict[str, Any]] = []
            for job in in_flight:
                row = self._poll(job)
                if row is None:
                    still.append(job)
                else:
                    yield row
            in_flight = still

    def _launch(self, spec: RunSpec) -> dict[str, Any]:
        parent_conn, child_conn = self._ctx.Pipe(duplex=False)
        payload = json.dumps(spec_to_payload(spec), ensure_ascii=False, default=str)
        process = self._ctx.Process(
            target=_child_entry,
            args=(payload, str(self.scratch_root), self.keep_workdirs, child_conn),
            daemon=True,
        )
        process.start()
        child_conn.close()  # seul le fils doit garder son extrémité ouverte
        return {
            "spec": spec,
            "process": process,
            "conn": parent_conn,
            "deadline": time.monotonic() + self._timeout_for(spec),
        }

    def _poll(self, job: dict[str, Any]) -> dict[str, Any] | None:
        """Rend la ligne si l'exécution est terminée, `None` si elle court encore."""
        conn = job["conn"]
        process = job["process"]
        spec: RunSpec = job["spec"]

        if conn.poll(0):
            try:
                row = json.loads(conn.recv())
            except (EOFError, json.JSONDecodeError) as exc:
                row = self._failure_row(spec, f"réponse illisible du fils : {exc}")
            conn.close()
            process.join(timeout=10)
            if "__child_error__" in row:
                row = self._failure_row(spec, row["__child_error__"])
            return row

        if not process.is_alive():
            # Mort sans avoir rien envoyé : segfault, OOM killer, ou plantage de
            # la couche SWIG d'OR-Tools, qui ne se rattrape pas depuis Python.
            conn.close()
            process.join(timeout=10)
            return self._failure_row(
                spec,
                f"le processus s'est terminé sans résultat (code {process.exitcode})",
            )

        if time.monotonic() > job["deadline"]:
            process.terminate()
            process.join(timeout=10)
            if process.is_alive():
                process.kill()
                process.join(timeout=10)
            conn.close()
            return self._failure_row(
                spec, f"délai dépassé ({self._timeout_for(spec):.0f} s), processus tué"
            )

        return None

    def _failure_row(self, spec: RunSpec, message: str) -> dict[str, Any]:
        """Ligne d'échec fabriquée côté parent, quand le fils n'a rien pu dire."""
        payload = spec_to_payload(spec)
        return {
            "schema": SCHEMA_VERSION,
            "config_key": payload["config_key"],
            "config_label": payload["label"],
            "is_baseline": payload["is_baseline"],
            "memberships": payload["memberships"],
            "factors": payload["factors"],
            "scenario": payload["scenario"],
            "budget_seconds": payload["budget_seconds"],
            "seed": payload["seed"],
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "host": platform.node(),
            "pid": None,
            "ok": False,
            "error": message,
            "traceback": None,
            "stats": None,
            "wall_seconds": None,
        }
