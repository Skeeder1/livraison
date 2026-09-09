"""
Sonde de déterminisme : `solve_scenario` rend-il deux fois le même résultat ?

C'est la **première** question à trancher, avant toute mesure. Elle décide du
plan d'expérience :

* si la fonction est déterministe, une exécution par couple (configuration,
  graine) suffit, et toute la variance observée est de la variance **entre
  instances** — que l'appariement neutralise ;
* si elle ne l'est pas, il faut des **réplicats** par couple, et un écart entre
  deux configurations ne signifie plus rien tant qu'il n'excède pas le bruit de
  la résolution elle-même.

La sonde répond empiriquement, en deux volets :

* **inter-processus** — la même entrée dans N processus neufs. C'est le mode
  exact de la campagne ;
* **intra-processus** — la même entrée deux fois de suite dans un seul
  processus. Un écart ici, alors que l'inter-processus est stable, dénoncerait un
  état résiduel entre appels (`Config` mal restauré, générateur aléatoire global
  de NumPy, cache).

Usage ::

    .venv/bin/python -m experiments.determinism --repeats 4 --budget 5
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from experiments.criterion import criterion_key, format_key
from experiments.grid import RunSpec
from experiments.runner import RunPool, run_one, spec_to_payload


def _make_spec(scenario: dict[str, Any], seed: int, budget: int, tag: int) -> RunSpec:
    """Fabrique une exécution de sonde ; `tag` distingue les réplicats."""
    return RunSpec(
        config_key=f"probe-{tag}",
        label=f"sonde #{tag}",
        factors={},
        scenario=dict(scenario),
        budget_seconds=budget,
        seed=seed,
    )


def _fingerprint(row: dict[str, Any]) -> str:
    """Empreinte comparable d'une ligne : toutes ses statistiques, triées."""
    if not row.get("ok"):
        return f"ÉCHEC: {row.get('error')}"
    return json.dumps(row.get("stats"), sort_keys=True, default=str)


def probe_cross_process(
    scenario: dict[str, Any], seed: int, budget: int, repeats: int, scratch: Path
) -> list[dict[str, Any]]:
    """
    Résout `repeats` fois la même entrée, chaque fois dans un processus neuf.

    :param scenario: Paramètres du scénario
    :param seed: Graine de l'instance
    :param budget: Budget de résolution, en secondes
    :param repeats: Nombre de réplicats
    :param scratch: Répertoire racine de travail
    :return: Lignes de résultat
    """
    specs = [_make_spec(scenario, seed, budget, i) for i in range(repeats)]
    pool = RunPool(workers=min(repeats, 4), scratch_root=scratch)
    return list(pool.imap(specs))


def probe_same_process(
    scenario: dict[str, Any], seed: int, budget: int, repeats: int, scratch: Path
) -> list[dict[str, Any]]:
    """
    Résout `repeats` fois la même entrée **dans ce processus**, séquentiellement.

    :param scenario: Paramètres du scénario
    :param seed: Graine de l'instance
    :param budget: Budget de résolution, en secondes
    :param repeats: Nombre de réplicats
    :param scratch: Répertoire racine de travail
    :return: Lignes de résultat
    """
    return [
        run_one(spec_to_payload(_make_spec(scenario, seed, budget, i)), str(scratch))
        for i in range(repeats)
    ]


def _verdict(rows: list[dict[str, Any]], title: str) -> bool:
    """Affiche le détail d'un volet et retourne vrai si tout est identique."""
    print(f"\n--- {title} ---")
    prints = [_fingerprint(row) for row in rows]
    for index, row in enumerate(rows):
        print(
            f"  #{index}  {format_key(criterion_key(row)):<38}"
            f"  mur={row.get('wall_seconds')} s"
        )
    identical = len(set(prints)) == 1
    if identical:
        print(f"  → {len(rows)} exécutions, statistiques IDENTIQUES")
    else:
        print(f"  → {len(set(prints))} résultats distincts sur {len(rows)} : NON déterministe")
        for value in sorted(set(prints)):
            print(f"     {value}")
    return identical


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée en ligne de commande."""
    parser = argparse.ArgumentParser(
        prog="python -m experiments.determinism",
        description="Vérifie empiriquement si solve_scenario est déterministe.",
    )
    parser.add_argument("--repeats", type=int, default=4, help="Réplicats par volet (défaut 4)")
    parser.add_argument("--budget", type=int, default=5, help="Budget de résolution en s (défaut 5)")
    parser.add_argument("--seed", type=int, default=42, help="Graine de l'instance (défaut 42)")
    parser.add_argument("--customers", type=int, default=45)
    parser.add_argument("--vehicles", type=int, default=3)
    parser.add_argument("--capacity", type=int, default=10)
    parser.add_argument("--hubs", type=int, default=0)
    parser.add_argument(
        "--scratch",
        type=Path,
        default=Path(tempfile.gettempdir()) / "livraison-determinisme",
        help="Répertoire de travail",
    )
    parser.add_argument(
        "--skip-same-process",
        action="store_true",
        help="N'exécute que le volet inter-processus",
    )
    args = parser.parse_args(argv)

    scenario = {
        "customers": args.customers,
        "vehicles": args.vehicles,
        "capacity": args.capacity,
        "hubs": args.hubs,
    }

    print("Sonde de déterminisme de optimizer.scenario.solve_scenario")
    print(f"  scénario : {scenario}, graine {args.seed}, budget {args.budget} s")
    print(f"  réplicats : {args.repeats} par volet, fetch_roads=False")

    cross = probe_cross_process(scenario, args.seed, args.budget, args.repeats, args.scratch)
    cross_ok = _verdict(cross, "volet inter-processus (mode de la campagne)")

    same_ok = None
    if not args.skip_same_process:
        same = probe_same_process(scenario, args.seed, args.budget, args.repeats, args.scratch)
        same_ok = _verdict(same, "volet intra-processus (appels séquentiels)")

    print("\n=== CONCLUSION ===")
    if cross_ok:
        print("solve_scenario est DÉTERMINISTE dans le mode de la campagne.")
        print("→ une exécution par (configuration, graine) suffit ; pas de réplicats.")
        print("→ toute la variance observée est de la variance ENTRE INSTANCES,")
        print("  que les blocs appariés neutralisent.")
    else:
        print("solve_scenario n'est PAS déterministe : la campagne doit répliquer")
        print("chaque couple (configuration, graine) et comparer des médianes.")
    if same_ok is False and cross_ok:
        print("ATTENTION : stable entre processus mais pas au sein d'un même processus.")
        print("Un état résiduel subsiste entre deux appels — raison de plus pour")
        print("n'exécuter qu'une seule résolution par processus.")

    return 0 if cross_ok else 1


if __name__ == "__main__":
    sys.exit(main())
