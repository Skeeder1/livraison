"""
Journal de résultats : JSONL append-only, et reprise.

Le format est une ligne JSON par exécution. Le choix n'est pas cosmétique :

* **un plantage ne perd rien.** Chaque ligne est écrite puis vidée (`flush` +
  `fsync`) avant que l'exécution suivante ne démarre. Une campagne de six heures
  tuée à la cinquième conserve cinq heures de mesures ;
* **la reprise est triviale.** Relire le fichier donne l'ensemble des couples
  `(config_key, seed)` déjà mesurés, qu'il suffit de retrancher du plan ;
* **le fichier reste lisible pendant la campagne.** `wc -l resultats.jsonl`
  donne l'avancement sans rien interrompre.

Une ligne tronquée en fin de fichier — la signature d'une coupure d'alimentation
au milieu d'une écriture — est ignorée à la lecture et écrasée à la reprise. Une
ligne illisible **au milieu** du fichier est signalée, car elle indique autre
chose qu'une interruption propre.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO


class ResultStore:
    """
    Écrivain append-only sur un fichier JSONL.

    S'utilise comme gestionnaire de contexte ::

        with ResultStore(Path("resultats.jsonl")) as store:
            store.append(row)
    """

    def __init__(self, path: Path, *, fsync: bool = True) -> None:
        """
        :param path: Chemin du journal ; les répertoires manquants sont créés
        :param fsync: Force l'écriture sur le disque après chaque ligne. À faux,
            seul le tampon Python est vidé : plus rapide, mais une coupure
            d'alimentation peut perdre les dernières lignes.
        """
        self.path = Path(path)
        self._fsync = fsync
        self._handle: TextIO | None = None
        self._written = 0

    def __enter__(self) -> ResultStore:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def close(self) -> None:
        """Ferme le journal. Idempotent."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    @property
    def written(self) -> int:
        """Nombre de lignes écrites par cette instance."""
        return self._written

    def append(self, row: dict[str, Any]) -> None:
        """
        Ajoute une ligne et la pousse immédiatement sur le disque.

        :param row: Objet JSON-sérialisable
        :raises RuntimeError: si le journal n'est pas ouvert
        """
        if self._handle is None:
            raise RuntimeError("ResultStore doit être utilisé comme gestionnaire de contexte")
        self._handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        self._handle.flush()
        if self._fsync:
            os.fsync(self._handle.fileno())
        self._written += 1


def read_rows(path: Path) -> list[dict[str, Any]]:
    """
    Lit toutes les lignes exploitables d'un journal.

    :param path: Chemin du journal ; un fichier absent donne une liste vide
    :return: Lignes décodées, dans l'ordre du fichier
    :raises ValueError: si une ligne illisible se trouve ailleurs qu'en dernière
        position — signe d'une corruption, et non d'une simple interruption
    """
    path = Path(path)
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    last_index = len(lines) - 1

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            if index == last_index:
                # Écriture interrompue en cours de route : la ligne sera
                # simplement réécrite à la reprise.
                break
            raise ValueError(
                f"{path}:{index + 1} — ligne JSON illisible au milieu du journal. "
                "Ce n'est pas une interruption propre ; inspecter le fichier."
            ) from None
        if isinstance(decoded, dict):
            rows.append(decoded)

    return rows


def iter_rows(path: Path) -> Iterator[dict[str, Any]]:
    """
    Parcourt les lignes d'un journal sans tout charger en mémoire.

    Contrairement à `read_rows`, cette fonction ignore silencieusement toute
    ligne illisible : elle sert aux usages de surveillance pendant une campagne,
    où le fichier est lu alors qu'il est en cours d'écriture.

    :param path: Chemin du journal
    :return: Itérateur sur les lignes décodées
    """
    path = Path(path)
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                yield decoded


def completed_keys(path: Path) -> set[tuple[str, int]]:
    """
    Couples `(config_key, seed)` déjà journalisés.

    Une exécution **en échec** compte comme faite : elle a été tentée, sa cause
    est enregistrée, et la rejouer à l'identique redonnerait le même échec en
    consommant le même budget. Pour la rejouer volontairement, retirer sa ligne
    du journal, ou lancer la campagne sans `--resume` vers un fichier neuf.

    :param path: Chemin du journal
    :return: Ensemble des couples déjà mesurés
    """
    keys: set[tuple[str, int]] = set()
    for row in iter_rows(path):
        config_key = row.get("config_key")
        seed = row.get("seed")
        if isinstance(config_key, str) and isinstance(seed, int):
            keys.add((config_key, seed))
    return keys
