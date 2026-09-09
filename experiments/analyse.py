"""
Analyse d'une campagne : courbes de réponse, comparaisons appariées, verdicts.

    .venv/bin/python -m experiments.analyse resultats.jsonl

Trois principes de lecture, appliqués partout dans le rapport :

1. **Rien n'est jugé sur l'objectif du solveur.** Le classement est celui du
   critère externe de `experiments.criterion`, fixé avant la campagne.
2. **Rien n'est jugé sur une exécution isolée.** Chaque point de balayage est
   résumé par une médiane et son intervalle interquartile sur le jeu de graines.
3. **Rien n'est comparé sans appariement.** Un point n'est comparé à la référence
   que sur les graines où *les deux* ont été mesurées. La variance entre
   instances dépasse largement la plupart des effets de paramètres ; sans
   appariement, elle les enterre tous.

Le rapport indique aussi, explicitement, les facteurs **sans effet mesurable**.
C'est un résultat de la campagne, pas un échec : il dit que le bouton peut être
laissé où il est, et que le temps de réglage doit aller ailleurs.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from experiments import criterion, stats
from experiments.store import read_rows

#: Seuil du test des signes. 0,05 est conventionnel ; il est affiché dans le
#: rapport pour que le lecteur puisse en juger, et la valeur p brute est toujours
#: donnée à côté du verdict.
ALPHA = 0.05


def scenario_label(scenario: dict[str, Any]) -> str:
    """Étiquette lisible et stable d'une variante de scénario."""
    return ", ".join(f"{key}={scenario[key]}" for key in sorted(scenario))


def load(path: Path) -> list[dict[str, Any]]:
    """
    Charge un journal et écarte ce qui n'est pas exploitable.

    :param path: Chemin du journal JSONL
    :return: Lignes retenues
    :raises SystemExit: journal vide ou introuvable
    """
    rows = read_rows(path)
    if not rows:
        print(f"Aucun résultat exploitable dans {path}", file=sys.stderr)
        raise SystemExit(1)
    return rows


def group(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Regroupe les lignes par variante de scénario.

    :param rows: Lignes brutes
    :return: `{étiquette de scénario: {"baseline": {graine: ligne},
        "by_config": {clé: {graine: ligne}}, "labels": {clé: étiquette},
        "memberships": {clé: [(facteur, valeur)]}, "budget": s}}`
    """
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = scenario_label(row.get("scenario") or {})
        entry = grouped.setdefault(
            label,
            {
                "baseline": {},
                "by_config": defaultdict(dict),
                "labels": {},
                "memberships": {},
                "budgets": set(),
                "scenario": row.get("scenario") or {},
            },
        )
        key = row.get("config_key")
        seed = row.get("seed")
        if key is None or seed is None:
            continue
        entry["by_config"][key][seed] = row
        entry["labels"][key] = row.get("config_label", key)
        entry["memberships"][key] = [tuple(m) for m in (row.get("memberships") or [])]
        entry["budgets"].add(row.get("budget_seconds"))
        if row.get("is_baseline"):
            entry["baseline"][seed] = row
    return grouped


def _values_of(rows_by_seed: dict[int, dict[str, Any]], seeds: list[int], field: str) -> list[float]:
    """Extrait une statistique sur un jeu de graines, en ignorant les échecs."""
    out: list[float] = []
    for seed in seeds:
        row = rows_by_seed.get(seed)
        if row and row.get("ok") and (row.get("stats") or {}).get(field) is not None:
            out.append(float(row["stats"][field]))
    return out


def analyse_factor(
    entry: dict[str, Any], factor: str
) -> dict[str, Any] | None:
    """
    Analyse un facteur dans une variante de scénario.

    :param entry: Groupe produit par `group`
    :param factor: Nom du facteur
    :return: Résumé analysable, ou `None` si le facteur n'a aucun point
    """
    baseline_seeds = set(entry["baseline"])
    if not baseline_seeds:
        return None

    # Chaque configuration appartenant au balayage, avec la valeur qu'elle teste.
    points: dict[Any, str] = {}
    for key, memberships in entry["memberships"].items():
        for name, value in memberships:
            if name == factor:
                points[value] = key

    # La référence est le point de référence de tous les balayages : on lui donne
    # sa propre valeur du facteur, lue dans n'importe laquelle de ses lignes.
    baseline_row = next(iter(entry["baseline"].values()))
    baseline_value = (baseline_row.get("factors") or {}).get(factor)
    baseline_key = baseline_row["config_key"]
    if baseline_value is not None:
        points.setdefault(baseline_value, baseline_key)

    if len(points) < 2:
        return None

    results = []
    scores_by_label: dict[str, dict[int, tuple[float, float, float]]] = {}

    for value in sorted(points, key=lambda v: (isinstance(v, str), v)):
        key = points[value]
        rows_by_seed = entry["by_config"].get(key, {})
        seeds = sorted(set(rows_by_seed) & baseline_seeds)

        wins = losses = ties = 0
        deltas: dict[str, list[float]] = {"customersServed": [], "horizon": [], "roadKm": []}
        failures = 0
        for seed in seeds:
            candidate = rows_by_seed[seed]
            reference = entry["baseline"][seed]
            if not candidate.get("ok"):
                failures += 1
            verdict = criterion.compare(candidate, reference)
            if verdict < 0:
                wins += 1
            elif verdict > 0:
                losses += 1
            else:
                ties += 1
            delta = criterion.paired_delta(candidate, reference)
            if delta is not None:
                for name, amount in delta.items():
                    deltas[name].append(amount)

        scores_by_label[str(value)] = {
            seed: criterion.criterion_key(rows_by_seed[seed]) for seed in seeds
        }

        results.append(
            {
                "value": value,
                "config_key": key,
                "is_baseline": key == baseline_key,
                "seeds": len(seeds),
                "failures": failures,
                "served": _values_of(rows_by_seed, seeds, "customersServed"),
                "horizon": _values_of(rows_by_seed, seeds, "horizon"),
                "roadKm": _values_of(rows_by_seed, seeds, "roadKm"),
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "p_value": stats.sign_test(wins, losses),
                "delta_served": stats.median(deltas["customersServed"]),
                "delta_horizon": stats.median(deltas["horizon"]),
                "delta_roadkm": stats.median(deltas["roadKm"]),
            }
        )

    ranks = stats.average_ranks(scores_by_label)
    for item in results:
        item["rank"] = ranks.get(str(item["value"]))

    return {
        "factor": factor,
        "baseline_value": baseline_value,
        "points": results,
        "noise_horizon": stats.spread(
            _values_of(entry["baseline"], sorted(baseline_seeds), "horizon")
        ),
        "noise_roadkm": stats.spread(
            _values_of(entry["baseline"], sorted(baseline_seeds), "roadKm")
        ),
    }


def recommend(summary: dict[str, Any]) -> dict[str, Any]:
    """
    Recommande une valeur, et dit pourquoi.

    Règle, dans cet ordre :

    1. si **aucun** point ne bat significativement la référence au test des
       signes, on **garde la référence**. Un bouton dont on ne sait pas montrer
       l'effet ne doit pas être déplacé sur la foi d'une différence de médiane ;
    2. sinon, parmi les points significatifs, on retient le meilleur au sens du
       critère externe — d'abord les clients servis, puis le makespan, puis les
       kilomètres, tous trois en écart apparié médian ;
    3. à égalité, on préfère le rang moyen le plus bas, puis la valeur la plus
       proche de la référence : ne pas déplacer un réglage sans gain.

    :param summary: Résumé produit par `analyse_factor`
    :return: `{"value", "reason", "significant"}`
    """
    significant = [
        point
        for point in summary["points"]
        if not point["is_baseline"]
        and point["p_value"] < ALPHA
        and point["wins"] > point["losses"]
    ]

    if not significant:
        # Distinguer « mesuré sans effet » de « plan trop petit pour conclure ».
        # Confondre les deux ferait passer un manque de puissance pour un
        # résultat, ce qui est la façon la plus commune de mentir avec un test.
        pairs = max(
            (point["wins"] + point["losses"] for point in summary["points"] if not point["is_baseline"]),
            default=0,
        )
        minimum = stats.min_pairs_for_significance(ALPHA)
        if pairs < minimum:
            reason = (
                f"INCONCLUSIF : au mieux {pairs} comparaison(s) appariée(s) non "
                f"nulle(s), alors que le test des signes en exige {minimum} pour "
                f"pouvoir franchir le seuil {ALPHA}. Ce n'est pas une absence "
                "d'effet, c'est une absence de puissance. Garder la valeur livrée "
                "et relancer avec davantage de graines."
            )
        else:
            reason = (
                "aucun point ne bat la référence de façon distinguable du hasard "
                f"(test des signes, seuil {ALPHA}, jusqu'à {pairs} paires). L'effet "
                "de ce facteur, s'il existe, est plus petit que la variance entre "
                "instances sur ce plan d'expérience. Garder la valeur livrée."
            )
        return {
            "value": summary["baseline_value"],
            "significant": False,
            "reason": reason,
        }

    def sort_key(point: dict[str, Any]):
        return (
            -(point["delta_served"] or 0.0),
            point["delta_horizon"] if point["delta_horizon"] is not None else 0.0,
            point["delta_roadkm"] if point["delta_roadkm"] is not None else 0.0,
            point["rank"] if point["rank"] is not None else 0.0,
        )

    best = sorted(significant, key=sort_key)[0]
    return {
        "value": best["value"],
        "significant": True,
        "reason": (
            f"bat la référence sur {best['wins']} graines contre {best['losses']} "
            f"(p = {best['p_value']:.4f}), écart apparié médian : "
            f"{best['delta_served']:+.2f} client, {best['delta_horizon']:+.0f} s de "
            f"makespan, {best['delta_roadkm']:+.2f} km."
        ),
    }


def _render_factor(summary: dict[str, Any], out: list[str]) -> dict[str, Any]:
    """Écrit la section d'un facteur et retourne sa recommandation."""
    factor = summary["factor"]
    out.append("")
    out.append(f"  Facteur : {factor}   (référence = {summary['baseline_value']})")
    out.append(
        f"  Bruit entre instances à la référence : makespan IQR "
        f"{summary['noise_horizon']:.0f} s, kilomètres IQR {summary['noise_roadkm']:.1f} km"
    )
    out.append(
        "  {:>14}  {:>3}  {:>20}  {:>26}  {:>24}  {:>5}  {:>13}  {:>8}".format(
            "valeur", "n", "servis méd. [IQR]", "makespan méd. [IQR]",
            "km méd. [IQR]", "rang", "V/D/N vs réf.", "p"
        )
    )
    out.append("  " + "-" * 128)

    for point in summary["points"]:
        marker = " *" if point["is_baseline"] else "  "
        rank = f"{point['rank']:.2f}" if point["rank"] is not None else "—"
        p_text = "—" if point["is_baseline"] else f"{point['p_value']:.4f}"
        wdt = "—" if point["is_baseline"] else f"{point['wins']}/{point['losses']}/{point['ties']}"
        out.append(
            "  {:>14}{}{:>3}  {:>20}  {:>26}  {:>24}  {:>5}  {:>13}  {:>8}".format(
                str(point["value"]),
                marker,
                point["seeds"],
                stats.format_median_iqr(point["served"], 1),
                stats.format_median_iqr(point["horizon"], 0),
                stats.format_median_iqr(point["roadKm"], 1),
                rank,
                wdt,
                p_text,
            )
        )
        if point["failures"]:
            out.append(f"                  ({point['failures']} exécution(s) en échec)")

    out.append("  (* = configuration de référence ; V/D/N = victoires/défaites/nuls appariés)")

    reco = recommend(summary)
    verdict = "EFFET DÉTECTÉ" if reco["significant"] else "AUCUN EFFET DISTINGUABLE DU BRUIT"
    out.append(f"  Verdict     : {verdict}")
    out.append(f"  Recommandé  : {factor} = {reco['value']}")
    out.append(f"  Raison      : {reco['reason']}")
    return reco


def build_report(rows: list[dict[str, Any]], path: Path) -> tuple[str, dict[str, Any]]:
    """
    Construit le rapport texte et son équivalent structuré.

    :param rows: Lignes du journal
    :param path: Chemin du journal, pour l'en-tête
    :return: `(rapport texte, résumé structuré)`
    """
    out: list[str] = []
    machine: dict[str, Any] = {"source": str(path), "scenarios": {}}

    ok_rows = [row for row in rows if row.get("ok")]
    failed = [row for row in rows if not row.get("ok")]

    out.append("=" * 100)
    out.append(f"CAMPAGNE DE CALIBRATION — {path}")
    out.append("=" * 100)
    out.append("")
    out.append(criterion.describe())
    out.append("")
    out.append(f"Lignes : {len(rows)} au total, {len(ok_rows)} résolues, {len(failed)} en échec.")

    seeds_seen = {row.get("seed") for row in rows}
    minimum = stats.min_pairs_for_significance(ALPHA)
    if len(seeds_seen) < minimum:
        out.append("")
        out.append(
            f"  PUISSANCE INSUFFISANTE : {len(seeds_seen)} graine(s). Le test des\n"
            f"  signes est discret — avec n paires, la plus petite valeur p\n"
            f"  atteignable vaut 2/2^n. Il faut au moins {minimum} graines pour\n"
            f"  qu'un résultat, si net soit-il, puisse franchir le seuil {ALPHA}.\n"
            "  Tous les verdicts « aucun effet » ci-dessous sont donc acquis\n"
            "  d'avance : ce journal ne peut rien conclure, seulement décrire.\n"
            "  Relancer la campagne avec --seeds 30."
        )

    budgets = sorted({row.get("budget_seconds") for row in rows})
    out.append(f"Budgets présents : {budgets} s")
    if len(budgets) > 1:
        out.append(
            "  ATTENTION : plusieurs budgets dans le même journal. Un réglage mesuré "
            "à budget court peut n'être qu'une compensation d'une recherche non "
            "convergée ; ne pas mélanger les budgets dans une même conclusion."
        )

    grouped = group(rows)

    for label in sorted(grouped):
        entry = grouped[label]
        out.append("")
        out.append("=" * 100)
        out.append(f"SCÉNARIO : {label}")
        out.append("=" * 100)

        if not entry["baseline"]:
            out.append("  Aucune configuration de référence mesurée : rien à comparer.")
            continue

        out.append(f"  Graines de référence : {len(entry['baseline'])}")

        factors = sorted({name for memberships in entry["memberships"].values() for name, _ in memberships})
        if not factors:
            out.append("  Aucun balayage : seule la référence est présente.")
            continue

        machine["scenarios"][label] = {}
        for factor in factors:
            summary = analyse_factor(entry, factor)
            if summary is None:
                out.append(f"\n  Facteur : {factor} — pas assez de points pour comparer.")
                continue
            reco = _render_factor(summary, out)
            machine["scenarios"][label][factor] = {
                "baseline_value": summary["baseline_value"],
                "recommendation": reco,
                "points": [
                    {
                        key: point[key]
                        for key in (
                            "value", "seeds", "wins", "losses", "ties", "p_value",
                            "delta_served", "delta_horizon", "delta_roadkm", "rank",
                            "is_baseline", "failures",
                        )
                    }
                    for point in summary["points"]
                ],
            }

    out.append("")
    out.append("=" * 100)
    out.append("SYNTHÈSE")
    out.append("=" * 100)
    for label, factors in machine["scenarios"].items():
        moved = [
            f"{factor} → {info['recommendation']['value']}"
            for factor, info in factors.items()
            if info["recommendation"]["significant"]
        ]
        inert = [factor for factor, info in factors.items() if not info["recommendation"]["significant"]]
        out.append(f"  {label}")
        out.append(f"    Effet détecté        : {', '.join(moved) if moved else 'aucun'}")
        out.append(f"    Aucun effet mesurable: {', '.join(inert) if inert else 'aucun'}")
    out.append("")
    out.append(
        "  Un facteur « sans effet mesurable » est un résultat, pas un échec : il dit\n"
        "  que le réglage livré convient et que l'effort de calibration doit aller\n"
        "  ailleurs. Il ne dit pas que le facteur est inerte en toutes circonstances —\n"
        "  seulement qu'il l'est sur ce scénario, à ce budget, sur ces graines."
    )

    if failed:
        out.append("")
        out.append(f"ÉCHECS ({len(failed)})")
        counts: dict[str, int] = defaultdict(int)
        for row in failed:
            counts[str(row.get("error"))[:120]] += 1
        for message, count in sorted(counts.items(), key=lambda item: -item[1]):
            out.append(f"  {count:>4} × {message}")

    return "\n".join(out), machine


def write_plots(rows: list[dict[str, Any]], directory: Path) -> list[Path]:
    """
    Trace une courbe de réponse par facteur, si `matplotlib` est disponible.

    Le rapport texte reste la sortie de référence : ces figures ne servent qu'à
    la relecture rapide. Une absence de `matplotlib` n'est pas une erreur.

    :param rows: Lignes du journal
    :param directory: Répertoire de sortie, créé si besoin
    :return: Chemins des figures écrites
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib absent : figures ignorées.", file=sys.stderr)
        return []

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for label, entry in group(rows).items():
        if not entry["baseline"]:
            continue
        factors = sorted({name for memberships in entry["memberships"].values() for name, _ in memberships})
        for factor in factors:
            summary = analyse_factor(entry, factor)
            if summary is None:
                continue
            numeric = [p for p in summary["points"] if isinstance(p["value"], (int, float))]
            if len(numeric) < 2:
                continue

            figure, axes = plt.subplots(3, 1, figsize=(7, 8), sharex=True)
            xs = [p["value"] for p in numeric]
            for axis, field, title in (
                (axes[0], "served", "clients servis (max)"),
                (axes[1], "horizon", "makespan, s (min)"),
                (axes[2], "roadKm", "kilomètres (min)"),
            ):
                medians = [stats.median(p[field]) or 0.0 for p in numeric]
                lows = [stats.quantile(p[field], 0.25) or 0.0 for p in numeric]
                highs = [stats.quantile(p[field], 0.75) or 0.0 for p in numeric]
                axis.plot(xs, medians, marker="o")
                axis.fill_between(xs, lows, highs, alpha=0.2)
                axis.set_ylabel(title)
                axis.grid(True, alpha=0.3)
                if min(xs) > 0 and max(xs) / max(min(xs), 1e-9) > 20:
                    axis.set_xscale("log")
            axes[2].set_xlabel(factor)
            figure.suptitle(f"{factor} — {label}\nmédiane et intervalle interquartile")
            figure.tight_layout()
            target = directory / f"{factor}__{label.replace(', ', '_').replace('=', '')}.png"
            figure.savefig(target, dpi=110)
            plt.close(figure)
            written.append(target)

    return written


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée en ligne de commande."""
    parser = argparse.ArgumentParser(
        prog="python -m experiments.analyse",
        description="Rapport texte d'une campagne de calibration.",
    )
    parser.add_argument("results", type=Path, help="Journal JSONL produit par experiments.run")
    parser.add_argument("--json", type=Path, default=None, help="Écrit aussi le résumé structuré")
    parser.add_argument("--plots", type=Path, default=None, help="Répertoire des figures (optionnel)")
    args = parser.parse_args(argv)

    rows = load(args.results)
    report, machine = build_report(rows, args.results)
    print(report)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(machine, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"\nRésumé structuré : {args.json}")

    if args.plots:
        written = write_plots(rows, args.plots)
        if written:
            print(f"Figures : {len(written)} dans {args.plots}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
