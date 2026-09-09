"""
Contrôle de stabilité : la configuration gagnante tient-elle à budget triplé ?

    .venv/bin/python -m experiments.stability resultats.jsonl \\
        --multiplier 3 --out stabilite.jsonl

Pourquoi ce contrôle est obligatoire
------------------------------------

Le balayage se fait à budget **fixe et court** — dix secondes — pour tenir en une
nuit. Ce choix a un effet pervers connu : à budget court, la recherche n'a pas
convergé, et une pénalité peut sembler « meilleure » simplement parce qu'elle
guide la recherche plus vite vers une solution acceptable. Le réglage compense
alors l'inachèvement de la recherche, pas une propriété du problème. Laissez
tourner trois fois plus longtemps et l'avantage s'évapore : le réglage prétendu
optimal devient au mieux neutre, au pire nuisible.

Le contrôle rejoue donc, à budget multiplié, **la référence et la gagnante**, sur
les mêmes graines, et compare de nouveau. Trois issues :

* la gagnante bat toujours la référence — le réglage est réel ;
* l'écart disparaît — le réglage ne compensait qu'une recherche non convergée,
  et il faut garder la référence ;
* la gagnante devient perdante — le réglage est activement mauvais à budget
  réaliste. C'est l'issue la plus instructive, et celle qu'on ne verrait jamais
  sans ce contrôle.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from experiments import criterion, stats
from experiments.analyse import group
from experiments.grid import RunSpec, config_key_for
from experiments.run import DEFAULT_SCRATCH
from experiments.runner import RunPool
from experiments.store import ResultStore, completed_keys, read_rows


def pick_winners(entry: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """
    Désigne la référence et la meilleure configuration d'une variante de scénario.

    « Meilleure » est entendue au sens du **rang moyen** sur les graines, selon
    le critère externe : c'est le résumé le plus robuste d'un classement, et il
    ne se laisse pas retourner par une instance aberrante.

    :param entry: Groupe produit par `experiments.analyse.group`
    :return: Liste `[("référence", ligne), ("gagnante", ligne)]`, éventuellement
        réduite à la seule référence si elle gagne déjà
    """
    if not entry["baseline"]:
        return []

    scores = {
        key: {seed: criterion.criterion_key(row) for seed, row in rows_by_seed.items()}
        for key, rows_by_seed in entry["by_config"].items()
    }
    ranks = stats.average_ranks(scores)
    if not ranks:
        return []

    baseline_row = next(iter(entry["baseline"].values()))
    baseline_key = baseline_row["config_key"]
    best_key = min(ranks, key=lambda key: (ranks[key], key != baseline_key))

    picks: list[tuple[str, dict[str, Any]]] = [("référence", baseline_row)]
    if best_key != baseline_key:
        picks.append(("gagnante", next(iter(entry["by_config"][best_key].values()))))
    return picks


def build_specs(
    picks: list[tuple[str, dict[str, Any]]], seeds: list[int], budget: int
) -> list[RunSpec]:
    """
    Reconstruit les exécutions à rejouer au nouveau budget.

    :param picks: Sorties de `pick_winners`
    :param seeds: Graines à rejouer — les mêmes que le balayage
    :param budget: Nouveau budget, en secondes
    :return: Exécutions planifiées
    """
    specs: list[RunSpec] = []
    for seed in seeds:
        for role, row in picks:
            factors = dict(row.get("factors") or {})
            scenario = dict(row.get("scenario") or {})
            specs.append(
                RunSpec(
                    config_key=config_key_for(factors, scenario, budget),
                    label=f"{row.get('config_label', '?')} @ {budget}s [{role}]",
                    factors=factors,
                    scenario=scenario,
                    budget_seconds=budget,
                    seed=seed,
                    memberships=(("__stabilite__", role),),
                    is_baseline=(role == "référence"),
                )
            )
    return specs


def report(rows: list[dict[str, Any]], budget: int) -> str:
    """
    Compare référence et gagnante au budget long, sur les graines communes.

    :param rows: Lignes du journal de stabilité
    :param budget: Budget utilisé
    :return: Rapport texte
    """
    out = [
        "=" * 100,
        f"CONTRÔLE DE STABILITÉ — budget {budget} s",
        "=" * 100,
        "",
        criterion.describe(),
        "",
    ]

    for label, entry in sorted(group(rows).items()):
        out.append(f"SCÉNARIO : {label}")
        if not entry["baseline"]:
            out.append("  Aucune référence rejouée.")
            continue

        others = {
            key: rows_by_seed
            for key, rows_by_seed in entry["by_config"].items()
            if key != next(iter(entry["baseline"].values()))["config_key"]
        }
        if not others:
            out.append("  La référence était déjà la meilleure : rien à contrôler.")
            out.append("")
            continue

        for key, rows_by_seed in others.items():
            seeds = sorted(set(rows_by_seed) & set(entry["baseline"]))
            wins = losses = ties = 0
            deltas: dict[str, list[float]] = {"customersServed": [], "horizon": [], "roadKm": []}
            for seed in seeds:
                verdict = criterion.compare(rows_by_seed[seed], entry["baseline"][seed])
                if verdict < 0:
                    wins += 1
                elif verdict > 0:
                    losses += 1
                else:
                    ties += 1
                delta = criterion.paired_delta(rows_by_seed[seed], entry["baseline"][seed])
                if delta:
                    for name, amount in delta.items():
                        deltas[name].append(amount)

            p_value = stats.sign_test(wins, losses)
            out.append(f"  Candidate : {entry['labels'][key]}")
            out.append(f"    Graines appariées : {len(seeds)}")
            out.append(f"    Victoires/Défaites/Nuls : {wins}/{losses}/{ties}   p = {p_value:.4f}")
            out.append(
                f"    Écart apparié médian : {stats.median(deltas['customersServed']) or 0:+.2f} client, "
                f"{stats.median(deltas['horizon']) or 0:+.0f} s, "
                f"{stats.median(deltas['roadKm']) or 0:+.2f} km"
            )
            minimum = stats.min_pairs_for_significance(0.05)
            if wins + losses < minimum:
                # Le test des signes plafonne à 2/2^n : sous `minimum` paires,
                # aucun verdict n'est possible, et prétendre le contraire ferait
                # passer un manque de puissance pour une conclusion.
                out.append(
                    f"    → INCONCLUSIF : {wins + losses} paire(s) non nulle(s), "
                    f"{minimum} au minimum pour que le test des signes puisse "
                    "franchir 0,05. Rejouer le contrôle sur davantage de graines."
                )
            elif wins > losses and p_value < 0.05:
                out.append("    → STABLE : l'avantage tient au budget long. Le réglage est réel.")
            elif losses > wins and p_value < 0.05:
                out.append(
                    "    → RENVERSÉ : la gagnante du balayage PERD au budget long. Le réglage "
                    "compensait une recherche non convergée. Garder la référence."
                )
            else:
                out.append(
                    "    → ÉVAPORÉ : plus d'avantage distinguable au budget long. Le gain "
                    "mesuré au balayage court n'était pas une propriété du problème."
                )
            out.append("")

    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée en ligne de commande."""
    parser = argparse.ArgumentParser(
        prog="python -m experiments.stability",
        description="Rejoue la configuration gagnante à budget multiplié.",
    )
    parser.add_argument("results", type=Path, help="Journal du balayage")
    parser.add_argument("--out", type=Path, required=True, help="Journal de stabilité (JSONL)")
    parser.add_argument("--multiplier", type=float, default=3.0, help="Multiplicateur de budget (défaut 3)")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seeds", type=int, default=None, help="Limite le nombre de graines rejouées")
    parser.add_argument("--scratch", type=Path, default=DEFAULT_SCRATCH)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--report-only", action="store_true", help="N'exécute rien, relit --out")
    args = parser.parse_args(argv)

    sweep_rows = read_rows(args.results)
    if not sweep_rows:
        print(f"Journal vide : {args.results}", file=sys.stderr)
        return 1

    budgets = {row.get("budget_seconds") for row in sweep_rows if row.get("budget_seconds")}
    if len(budgets) != 1:
        print(
            f"Le journal mélange les budgets {sorted(budgets)} : impossible d'en "
            "déduire un budget de contrôle. Analyser un seul budget à la fois.",
            file=sys.stderr,
        )
        return 2
    base_budget = int(next(iter(budgets)))
    long_budget = int(round(base_budget * args.multiplier))

    if args.report_only:
        print(report(read_rows(args.out), long_budget))
        return 0

    specs: list[RunSpec] = []
    for _, entry in sorted(group(sweep_rows).items()):
        picks = pick_winners(entry)
        if not picks:
            continue
        seeds = sorted(entry["baseline"])
        if args.seeds:
            seeds = seeds[: args.seeds]
        specs.extend(build_specs(picks, seeds, long_budget))

    if not specs:
        print("Aucune configuration à contrôler.", file=sys.stderr)
        return 1

    done = completed_keys(args.out) if args.resume else set()
    pending = [spec for spec in specs if spec.resume_key not in done]

    print(f"Contrôle de stabilité : budget {base_budget} s → {long_budget} s")
    print(f"{len(pending)} exécution(s) à faire sur {len(specs)}.")

    pool = RunPool(workers=args.workers, scratch_root=Path(args.scratch))
    with ResultStore(args.out) as store:
        for index, row in enumerate(pool.imap(pending), start=1):
            store.append(row)
            print(
                f"[{index}/{len(pending)}] {'ok ' if row.get('ok') else 'ÉCHEC'} "
                f"{row['config_label']:<56} graine={row['seed']} "
                f"{criterion.format_key(criterion.criterion_key(row))}",
                flush=True,
            )

    print()
    print(report(read_rows(args.out), long_budget))
    return 0


if __name__ == "__main__":
    sys.exit(main())
