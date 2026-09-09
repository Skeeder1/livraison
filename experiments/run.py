"""
Pilote de campagne.

    .venv/bin/python -m experiments.run \\
        --grid experiments/grids/ofat.json \\
        --seeds 30 --workers 12 --budget 10 \\
        --out resultats.jsonl --resume

Le pilote développe la grille, retranche ce qui est déjà journalisé, puis
distribue le reste sur `--workers` processus. Chaque ligne est écrite et
poussée sur le disque dès qu'elle arrive : interrompre la campagne à `Ctrl-C`,
ou la perdre sur une coupure, ne coûte au pire que les exécutions en vol.

Campagne longue, sans consommer de jetons ::

    nohup .venv/bin/python -m experiments.run --grid experiments/grids/ofat.json \\
        --seeds 30 --workers 12 --budget 10 --out resultats.jsonl --resume \\
        > campagne.log 2>&1 &

    wc -l resultats.jsonl        # avancement, à tout moment
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from experiments import criterion
from experiments.grid import Campaign, GridError, default_seeds, expand, filter_pending, load_spec
from experiments.runner import RunPool
from experiments.store import ResultStore, completed_keys

#: Répertoire de travail par défaut. Surchargé par `LIVRAISON_SCRATCH`, ce qui
#: permet de déporter les écritures sur un disque rapide sans toucher au code.
DEFAULT_SCRATCH = Path(os.environ.get("LIVRAISON_SCRATCH", Path(tempfile.gettempdir()) / "livraison-experiments"))


def build_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments."""
    parser = argparse.ArgumentParser(
        prog="python -m experiments.run",
        description="Lance une campagne de calibration en blocs appariés.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=criterion.describe(),
    )
    parser.add_argument("--grid", type=Path, required=True, help="Fichier de grille JSON")
    parser.add_argument("--seeds", type=int, default=30, help="Nombre de graines (défaut 30)")
    parser.add_argument(
        "--seed-list",
        type=str,
        default=None,
        help="Graines explicites, séparées par des virgules ; prioritaire sur --seeds",
    )
    parser.add_argument("--workers", type=int, default=12, help="Processus simultanés (défaut 12)")
    parser.add_argument(
        "--budget", type=int, default=None,
        help="Budget de résolution en secondes ; prioritaire sur celui de la grille",
    )
    parser.add_argument("--out", type=Path, required=True, help="Journal JSONL de sortie")
    parser.add_argument(
        "--resume", action="store_true",
        help="Saute les couples (configuration, graine) déjà présents dans --out",
    )
    parser.add_argument("--scratch", type=Path, default=DEFAULT_SCRATCH, help="Répertoire de travail")
    parser.add_argument(
        "--keep-workdirs", action="store_true",
        help="Conserve les répertoires de travail, pour inspecter une exécution",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Affiche le plan et le coût estimé, sans rien exécuter",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Ne réalise que les N premières exécutions restantes (pilote)",
    )
    parser.add_argument(
        "--timeout", type=float, default=None,
        help="Délai maximal par exécution, en secondes (défaut : 6×budget + 120)",
    )
    parser.add_argument(
        "--no-fsync", action="store_true",
        help="N'appelle pas fsync après chaque ligne (plus rapide, moins sûr)",
    )
    return parser


def resolve_seeds(args: argparse.Namespace) -> list[int]:
    """
    Détermine le jeu de graines de la campagne.

    :param args: Arguments analysés
    :return: Liste de graines
    :raises GridError: liste explicite invalide
    """
    if args.seed_list:
        try:
            return [int(part) for part in args.seed_list.split(",") if part.strip()]
        except ValueError:
            raise GridError(f"--seed-list invalide : {args.seed_list!r}") from None
    return default_seeds(args.seeds)


def describe_plan(campaign: Campaign, pending: int, workers: int) -> str:
    """
    Résumé du plan et de son coût, avant lancement.

    :param campaign: Campagne développée
    :param pending: Exécutions restant à faire
    :param workers: Processus simultanés
    :return: Texte multiligne
    """
    total = len(campaign.runs)
    # Chaque exécution coûte son budget, plus quelques secondes d'import et de
    # génération de données. Le facteur 1,4 est une estimation prudente ;
    # l'affichage sert à décider d'un ordre de grandeur, pas à promettre l'heure.
    seconds = pending * campaign.budget_seconds * 1.4 / max(workers, 1)
    lines = [
        f"Campagne      : {campaign.name}",
        f"Configurations: {campaign.unique_configs} distinctes",
        f"Graines       : {len(campaign.seeds)} ({campaign.seeds[0]}…{campaign.seeds[-1]})",
        f"Budget        : {campaign.budget_seconds} s par résolution",
        f"Exécutions    : {total} au total, {pending} à faire",
        f"Processus     : {workers}",
        f"Durée estimée : ~{seconds / 60:.0f} min ({seconds / 3600:.1f} h)",
    ]
    if campaign.sweep_points:
        lines.append("Balayages     :")
        for factor, values in campaign.sweep_points.items():
            lines.append(f"  {factor:<32} {values}")
    lines.append("Variantes de scénario :")
    for variant in campaign.scenario_variants:
        lines.append(f"  {variant}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée en ligne de commande."""
    args = build_parser().parse_args(argv)

    try:
        spec = load_spec(args.grid)
        seeds = resolve_seeds(args)
        campaign = expand(spec, seeds, budget_seconds=args.budget)
    except GridError as exc:
        print(f"Grille refusée : {exc}", file=sys.stderr)
        return 2

    done = completed_keys(args.out) if args.resume else set()
    if not args.resume and args.out.exists():
        print(
            f"Attention : {args.out} existe déjà et --resume n'est pas demandé. "
            "Les nouvelles lignes seront ajoutées à la suite ; l'analyse verra "
            "les deux campagnes. Utiliser --resume, ou un fichier neuf.",
            file=sys.stderr,
        )

    pending = filter_pending(campaign.runs, done)
    if args.limit is not None:
        pending = pending[: args.limit]

    print(describe_plan(campaign, len(pending), args.workers))
    print(f"Déjà journalisées : {len(done)}")
    print()
    print(criterion.describe())
    print()

    if args.dry_run:
        print("--dry-run : rien n'a été exécuté.")
        return 0

    if not pending:
        print("Rien à faire : la campagne est complète.")
        return 0

    # Ctrl-C doit arrêter proprement, pas corrompre le journal. On lève un drapeau
    # et on cesse de soumettre ; les exécutions en vol vont à leur terme.
    interrupted = {"flag": False}

    def _on_sigint(signum: int, frame: Any) -> None:
        if interrupted["flag"]:
            raise KeyboardInterrupt
        interrupted["flag"] = True
        print(
            "\nInterruption demandée : plus aucune exécution n'est lancée, "
            "les exécutions en cours vont à leur terme. Ctrl-C à nouveau pour forcer.",
            file=sys.stderr,
        )

    signal.signal(signal.SIGINT, _on_sigint)

    def feed():
        for spec_run in pending:
            if interrupted["flag"]:
                return
            yield spec_run

    pool = RunPool(
        workers=args.workers,
        scratch_root=args.scratch,
        keep_workdirs=args.keep_workdirs,
        timeout_seconds=args.timeout,
    )

    started = time.monotonic()
    failures = 0
    best: dict[str, Any] | None = None

    with ResultStore(args.out, fsync=not args.no_fsync) as store:
        for index, row in enumerate(pool.imap(feed()), start=1):
            store.append(row)
            if not row.get("ok"):
                failures += 1
            elif best is None or criterion.is_better(row, best):
                best = row

            elapsed = time.monotonic() - started
            rate = index / elapsed if elapsed else 0.0
            remaining = (len(pending) - index) / rate if rate else 0.0
            status = "ok " if row.get("ok") else "ÉCHEC"
            print(
                f"[{index}/{len(pending)}] {status} "
                f"{row['config_label']:<48} graine={row['seed']} "
                f"{criterion.format_key(criterion.criterion_key(row)):<34} "
                f"| {rate * 60:.1f}/min, reste ~{remaining / 60:.0f} min",
                flush=True,
            )

    elapsed = time.monotonic() - started
    print()
    print(f"Terminé : {store.written} lignes en {elapsed / 60:.1f} min, {failures} échec(s).")
    if best is not None:
        print(
            f"Meilleure ligne isolée (indicative, PAS une conclusion) : "
            f"{best['config_label']} graine={best['seed']} "
            f"{criterion.format_key(criterion.criterion_key(best))}"
        )
        print("Les conclusions se tirent de `python -m experiments.analyse`, sur des")
        print("médianes appariées — jamais d'une exécution isolée.")
    if interrupted["flag"]:
        print("Campagne interrompue. Relancer la même commande avec --resume.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
