"""
Courbes de convergence : quand la recherche cesse-t-elle de progresser ?

Le budget de recherche est un **plafond**, jamais un critère d'arrêt. La
métaheuristique améliore tant qu'on la laisse tourner et rend la meilleure
solution qu'elle a vue ; de l'extérieur, une résolution qui a convergé et une
résolution coupée en pleine progression rendent toutes deux « une solution ».
Rien ne distingue les deux. C'est pourquoi ce module existe : il enregistre la
trajectoire, pas seulement son point d'arrivée.

Trois propriétés mesurées avant d'en tirer quoi que ce soit, parce que la méthode
en dépend :

* **la trajectoire est déterministe.** Deux exécutions du même couple
  (instance, graine) rendent la même suite d'objectifs, à la gigue d'horloge
  près sur les dates ;
* **une trajectoire courte est le préfixe exact d'une trajectoire longue.** La
  recherche ne connaît pas son plafond et ne change pas de comportement selon
  lui. Mesurer une fois à budget large donne donc la courbe de **tous** les
  budgets plus courts, ce qui divise le coût de l'étude par le nombre de budgets
  étudiés ;
* **la suite des objectifs rendus n'est pas décroissante.** La recherche locale
  guidée accepte des dégradations pour sortir d'un optimum local, et le rappel
  de solution voit ces solutions-là aussi. Le chiffre qui a un sens est donc le
  **minimum courant**, celui que le solveur finira par rendre, et non la
  dernière valeur observée.

Cette dernière propriété n'est pas un détail de mise en œuvre. Confondre les
deux — lire la date du dernier rappel plutôt que celle de la dernière
amélioration — fait conclure que la recherche progressait encore à la dernière
milliseconde alors qu'elle n'avait rien amélioré depuis longtemps. C'est
exactement l'erreur que ce module sert à ne plus commettre.

Usage ::

    python -m experiments.convergence --out experiments/out/convergence.jsonl

Le journal est un JSONL append-only : une ligne par exécution, reprise par
soustraction des couples déjà mesurés. Voir `experiments/store.py`.
"""
from __future__ import annotations

import argparse
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from experiments.store import ResultStore, read_rows
from optimizer.config import Config
from optimizer.create_toy_data import create_toy_data
from optimizer.data_loader import load_data
from optimizer.solver import solve_vrp

#: Attributs de `Config` que la génération d'instance écrase, et qu'il faut donc
#: restaurer. `Config` porte des attributs de **classe** : un oubli ici fuit sur
#: toutes les exécutions suivantes du même processus.
CONFIG_KEYS = (
    "NUM_CUSTOMERS",
    "NUM_VEHICLES",
    "NUM_HUBS",
    "VEHICLE_CAPACITY_MIN",
    "VEHICLE_CAPACITY_MAX",
    "TW_END_MIN",
    "TW_END_MAX",
    "RANDOM_SEED",
)

#: Fenêtres ouvertes sur la journée : on mesure la convergence, pas la capacité
#: du modèle à respecter des horaires. Des fenêtres serrées changeraient la forme
#: de la courbe pour une raison qui n'est pas celle qu'on étudie.
OPEN_TW = 86400


def trajectoire(
    *,
    customers: int,
    vehicles: int,
    capacity: int,
    seed: int,
    budget_seconds: int,
    road_matrix: bool,
) -> list[tuple[int, int]]:
    """
    Résout une instance et rend la suite ``(date_ms, objectif)`` des solutions.

    La date est relevée dans le rappel, donc au plus près de la solution. Le
    rappel se contente d'ajouter un couple à une liste : il s'exécute dans la
    boucle de recherche, et tout ce qu'il consomme est pris sur le budget qu'il
    sert à mesurer.

    :return: Couples ``(millisecondes depuis le départ, objectif)``, dans
        l'ordre où le solveur les a rendus — suite **non décroissante**, cf. le
        docstring du module.
    """
    saved = {key: getattr(Config, key) for key in CONFIG_KEYS}
    try:
        Config.update(
            NUM_CUSTOMERS=customers,
            NUM_VEHICLES=vehicles,
            NUM_HUBS=0,
            VEHICLE_CAPACITY_MIN=float(capacity),
            VEHICLE_CAPACITY_MAX=float(capacity),
            TW_END_MIN=OPEN_TW,
            TW_END_MAX=OPEN_TW,
            RANDOM_SEED=seed,
        )
        with tempfile.TemporaryDirectory(prefix="convergence-") as workdir:
            create_toy_data(workdir, verbose=False, road_matrix=road_matrix)
            data = load_data(workdir)
            data["time_limit"] = budget_seconds

            points: list[tuple[int, int]] = []
            depart = time.monotonic()

            def observer(routing: Any) -> None:
                points.append(
                    (round((time.monotonic() - depart) * 1000), routing.CostVar().Max())
                )

            solve_vrp(data, on_solution=observer)
            return points
    finally:
        Config.update(**saved)


def minimum_courant(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Suite ``(date, meilleur objectif connu à cette date)``, décroissante."""
    meilleur = None
    courbe = []
    for date, objectif in points:
        if meilleur is None or objectif < meilleur:
            meilleur = objectif
        courbe.append((date, meilleur))
    return courbe


def ameliorations(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Ne garde que les solutions qui **améliorent** le minimum courant."""
    meilleur = None
    gardees = []
    for date, objectif in points:
        if meilleur is None or objectif < meilleur:
            meilleur = objectif
            gardees.append((date, objectif))
    return gardees


def coude(points: list[tuple[int, int]], budget_ms: int, tolerance: float) -> int:
    """
    Premier instant après lequel l'objectif ne gagne plus que `tolerance`.

    C'est le critère de l'issue #21, écrit explicitement : on cherche la plus
    petite date `t` telle que l'objectif à `t` soit à moins de `tolerance` près
    du meilleur objectif atteint sur tout le budget. Tout ce qui suit `t` est du
    temps acheté pour un gain inférieur à la tolérance.

    :param tolerance: Écart relatif toléré, par exemple 0.01 pour 1 %
    :return: Date en millisecondes ; `budget_ms` si le seuil n'est jamais atteint
    """
    ameliorants = ameliorations(points)
    if not ameliorants:
        return budget_ms
    final = ameliorants[-1][1]
    seuil = final * (1.0 + tolerance)
    for date, objectif in ameliorants:
        if objectif <= seuil:
            return date
    return budget_ms


def empreinte_modele() -> str:
    """SHA du dépôt au moment de la mesure, pour rattacher une ligne au code."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent.parent,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "inconnu"


def plan(
    tailles: list[int], vehicules: list[int], graines: list[int]
) -> list[dict[str, int]]:
    """Développe la grille en exécutions élémentaires, ordre déterministe."""
    return [
        {"customers": c, "vehicles": v, "seed": s}
        for c in tailles
        for v in vehicules
        for s in graines
    ]


def cle(run: dict[str, Any]) -> tuple[int, int, int]:
    return (run["customers"], run["vehicles"], run["seed"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--out", type=Path, default=Path("experiments/out/convergence.jsonl"))
    parser.add_argument("--budget", type=int, default=60, help="Plafond de recherche, en secondes")
    parser.add_argument("--capacity", type=int, default=10)
    parser.add_argument("--tailles", type=int, nargs="+", default=[10, 25, 45, 60])
    parser.add_argument("--vehicules", type=int, nargs="+", default=[2, 3, 5])
    parser.add_argument("--graines", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument(
        "--euclidien",
        action="store_true",
        help="Mesure à vol d'oiseau. Par défaut la matrice routière, "
        "c'est-à-dire ce que résout la démonstration en production.",
    )
    args = parser.parse_args(argv)

    road_matrix = not args.euclidien
    a_faire = plan(args.tailles, args.vehicules, args.graines)
    deja = {
        (r["customers"], r["vehicles"], r["seed"])
        for r in read_rows(args.out)
        if r.get("road_matrix") == road_matrix and r.get("budget_seconds") == args.budget
    }
    restant = [r for r in a_faire if cle(r) not in deja]

    print(
        f"{len(a_faire)} exécutions au plan, {len(deja)} déjà mesurées, "
        f"{len(restant)} à faire — budget {args.budget} s, "
        f"matrice {'routière' if road_matrix else 'euclidienne'}",
        flush=True,
    )

    sha = empreinte_modele()
    with ResultStore(args.out) as store:
        for numero, run in enumerate(restant, start=1):
            depart = time.monotonic()
            points = trajectoire(
                customers=run["customers"],
                vehicles=run["vehicles"],
                capacity=args.capacity,
                seed=run["seed"],
                budget_seconds=args.budget,
                road_matrix=road_matrix,
            )
            ameliorants = ameliorations(points)
            budget_ms = args.budget * 1000
            ligne = {
                **run,
                "capacity": args.capacity,
                "budget_seconds": args.budget,
                "road_matrix": road_matrix,
                "solutions": len(points),
                "ameliorations": len(ameliorants),
                "objectif_final": ameliorants[-1][1] if ameliorants else None,
                "derniere_amelioration_ms": ameliorants[-1][0] if ameliorants else None,
                "dernier_rappel_ms": points[-1][0] if points else None,
                "coude_1pct_ms": coude(points, budget_ms, 0.01),
                "coude_2pct_ms": coude(points, budget_ms, 0.02),
                "coude_5pct_ms": coude(points, budget_ms, 0.05),
                "trajectoire": ameliorants,
                "duree_reelle_s": round(time.monotonic() - depart, 2),
                "modele_sha": sha,
                "python": platform.python_version(),
            }
            store.append(ligne)
            print(
                f"[{numero}/{len(restant)}] {run['customers']} clients, "
                f"{run['vehicles']} livreurs, graine {run['seed']} : "
                f"{len(ameliorants)} améliorations, dernière à "
                f"{ligne['derniere_amelioration_ms']} ms, "
                f"coude 1 % à {ligne['coude_1pct_ms']} ms",
                flush=True,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
