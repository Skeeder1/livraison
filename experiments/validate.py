"""
Auto-validation du harnais sur une dégénérescence déjà connue.

    .venv/bin/python -m experiments.validate --seeds 5 --budget 5

Le principe
-----------

Un harnais de mesure doit être étalonné sur un phénomène **déjà connu par une
autre voie**. Sinon rien ne distingue « ce facteur n'a pas d'effet » de « ce
harnais ne mesure rien ».

`AGENTS.md` documente une dégénérescence mesurée à la main : avec un seul
véhicule, `TIME_SPAN_COEFFICIENT` cesse d'équilibrer une flotte et devient un
péage forfaitaire sur le temps de conduite. Le solveur abandonne alors un client
dès que le servir coûte, en temps, plus cher que la pénalité d'abandon :

    seuil (secondes par client servi) ≈ DROP_CUSTOMER_PENALTY_METERS
                                        ÷ TIME_SPAN_COEFFICIENT

Le relevé d'origine — dix clients, un véhicule — donne 10 clients servis sur 10
à un coefficient de 50, et 0 sur 10 à 200, sur une tournée de 7 006 s.

Trois contrôles, pas un
-----------------------

Le relevé d'origine isolait le terme d'étendue **temporelle**. Le reproduire
exige donc de neutraliser le terme d'étendue **en distance** : mesuré ici,
`DISTANCE_SPAN_COEFFICIENT = 30` suffit à lui seul à rendre l'abandon rentable
dès `TIME_SPAN_COEFFICIENT = 1` lorsque la pénalité d'abandon vaut 100 000. Sans
cette neutralisation, on croirait mesurer le seuil du temps alors qu'on observe
celui de la distance.

**A — reproduction.** Pénalité d'abandon 100 000, service 5 s/unité (la valeur
réellement appliquée à l'époque, cf. §2.3 du document de conception),
`DISTANCE_SPAN_COEFFICIENT = 0`. Attendu : service complet aux petits
coefficients, effondrement autour de 200 — le relevé d'AGENTS.md.

**B — prédiction.** Mêmes conditions, pénalité d'abandon **multipliée par dix**.
La formule annonce un seuil dix fois plus haut : ~2 000.

**C — configuration livrée.** Les valeurs du dépôt telles quelles. Ce contrôle
ne vérifie rien : il **mesure** où se trouve le seuil aujourd'hui, ce qui est
l'information dont la calibration a besoin.

A prouve qu'on retrouve un chiffre connu. B prouve qu'on retrouve le
*mécanisme* : le seuil se déplace là où la formule l'annonce quand on change un
autre paramètre. Reproduire un nombre ne démontre qu'une recopie de conditions ;
prédire son déplacement démontre une mesure.

Si A échoue, c'est le harnais qui est faux — pas le solveur : le phénomène a été
mesuré à la main avant lui.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from experiments import criterion, stats
from experiments.grid import RunSpec, config_key_for, default_seeds
from experiments.run import DEFAULT_SCRATCH
from experiments.runner import RunPool
from experiments.store import ResultStore, completed_keys, read_rows

#: Scénario du relevé d'origine : un seul véhicule, dix clients.
#: C'est bien la flotte d'**un** véhicule qui déclenche la dégénérescence — avec
#: plusieurs véhicules, le terme d'étendue fait ce pour quoi il est là.
VALIDATION_SCENARIO: dict[str, Any] = {
    "customers": 10,
    "vehicles": 1,
    "capacity": 10,
    "hubs": 0,
}

#: Points de balayage. La plage descend jusqu'à 1 pour encadrer le seuil du
#: contrôle B, qui est attendu très bas.
COEFFICIENTS: tuple[int, ...] = (1, 5, 20, 50, 100, 200, 500, 1000, 2000, 5000)

#: Les trois jeux de conditions comparés : `(nom, pénalité d'abandon,
#: temps de service par unité, coefficient d'étendue en distance, attendu)`.
CHECKS: tuple[tuple[str, int, int, int, str], ...] = (
    ("A-releve", 100_000, 5, 0,
     "conditions du relevé AGENTS.md, étendue en distance neutralisée ; seuil attendu ~200"),
    ("B-abandon10x", 1_000_000, 5, 0,
     "mêmes conditions, abandon ×10 ; seuil attendu ~10× plus haut, soit ~2000"),
    ("C-livre", 1_000_000, 60, 30,
     "configuration livrée telle quelle ; ce contrôle mesure, il ne vérifie pas"),
)


def build_specs(seeds: list[int], budget: int) -> list[RunSpec]:
    """
    Construit le plan d'auto-validation.

    :param seeds: Graines, communes aux trois contrôles
    :param budget: Budget de résolution, en secondes
    :return: Exécutions planifiées, en ordre graine-majeur
    """
    from optimizer.config import Config

    specs: list[RunSpec] = []
    for seed in seeds:
        for check_name, drop_penalty, service_time, distance_span, _ in CHECKS:
            for coefficient in COEFFICIENTS:
                factors = {
                    "TIME_SPAN_COEFFICIENT": coefficient,
                    "DROP_CUSTOMER_PENALTY_METERS": drop_penalty,
                    "SERVICE_TIME_PER_UNIT": service_time,
                    "CAPACITY_SPAN_COEFFICIENT": Config.CAPACITY_SPAN_COEFFICIENT,
                    "DISTANCE_SPAN_COEFFICIENT": distance_span,
                }
                scenario = dict(VALIDATION_SCENARIO)
                specs.append(
                    RunSpec(
                        config_key=config_key_for(factors, scenario, budget),
                        label=f"{check_name} | TIME_SPAN={coefficient}",
                        factors=factors,
                        scenario=scenario,
                        budget_seconds=budget,
                        seed=seed,
                        memberships=(("__validation__", check_name),),
                    )
                )
    return specs


def _rows_of_check(
    rows: list[dict[str, Any]], drop_penalty: int, service_time: int, distance_span: int
) -> dict[int, list[dict[str, Any]]]:
    """Lignes d'un contrôle, regroupées par coefficient."""
    grouped: dict[int, list[dict[str, Any]]] = {value: [] for value in COEFFICIENTS}
    for row in rows:
        factors = row.get("factors") or {}
        if factors.get("DROP_CUSTOMER_PENALTY_METERS") != drop_penalty:
            continue
        if factors.get("SERVICE_TIME_PER_UNIT") != service_time:
            continue
        if factors.get("DISTANCE_SPAN_COEFFICIENT") != distance_span:
            continue
        coefficient = factors.get("TIME_SPAN_COEFFICIENT")
        if coefficient in grouped and row.get("ok"):
            grouped[coefficient].append(row)
    return grouped


def _served(rows: list[dict[str, Any]]) -> list[float]:
    """Clients servis, ligne par ligne."""
    return [float(row["stats"]["customersServed"]) for row in rows if (row.get("stats") or {}).get("customersServed") is not None]


def _seconds_per_customer(rows: list[dict[str, Any]]) -> float | None:
    """Coût temporel médian d'un client servi, sur les lignes à service complet."""
    ratios = [
        row["stats"]["horizon"] / row["stats"]["customersServed"]
        for row in rows
        if (row.get("stats") or {}).get("customersServed")
    ]
    return stats.median(ratios)


def _collapse_point(grouped: dict[int, list[dict[str, Any]]], total: int) -> int | None:
    """
    Premier coefficient, en ordre croissant, où le service médian n'est plus complet.

    :param grouped: Lignes par coefficient
    :param total: Nombre de clients de l'instance
    :return: Coefficient d'effondrement, ou `None` s'il n'y en a pas
    """
    for coefficient in sorted(grouped):
        values = _served(grouped[coefficient])
        median = stats.median(values)
        if values and median is not None and median < total:
            return coefficient
    return None


def report(rows: list[dict[str, Any]]) -> tuple[str, bool]:
    """
    Rend le rapport d'auto-validation et le verdict global.

    :param rows: Lignes du journal de validation
    :return: `(rapport, succès)`
    """
    total = VALIDATION_SCENARIO["customers"]
    out = [
        "=" * 100,
        "AUTO-VALIDATION DU HARNAIS — dégénérescence de TIME_SPAN_COEFFICIENT",
        "=" * 100,
        "",
        "Phénomène attendu (AGENTS.md, relevé manuel) : avec UN seul véhicule, le",
        "terme d'étendue temporelle devient un péage sur le temps de conduite. Dès",
        "que servir un client coûte plus de DROP_CUSTOMER_PENALTY_METERS /",
        "TIME_SPAN_COEFFICIENT secondes, le solveur l'abandonne — et il a raison :",
        "il répond correctement à un objectif mal calibré pour une flotte d'un.",
        "",
        f"Scénario : {VALIDATION_SCENARIO}",
        "",
    ]

    collapses: dict[str, int | None] = {}
    predicted: dict[str, float | None] = {}

    for check_name, drop_penalty, service_time, distance_span, note in CHECKS:
        grouped = _rows_of_check(rows, drop_penalty, service_time, distance_span)
        out.append(
            f"--- Contrôle {check_name} : abandon = {drop_penalty:,} m, "
            f"service = {service_time} s/unité, étendue-distance = {distance_span} ---"
        )
        out.append(f"    {note}")
        out.append(f"    {'TIME_SPAN':>10}  {'n':>3}  {'servis méd. [IQR]':>22}  {'seuil (s/client)':>18}")
        for coefficient in sorted(grouped):
            values = _served(grouped[coefficient])
            out.append(
                f"    {coefficient:>10}  {len(values):>3}  "
                f"{stats.format_median_iqr(values, 1):>22}  {drop_penalty / coefficient:>18,.0f}"
            )

        point = _collapse_point(grouped, total)
        collapses[check_name] = point
        cost = _seconds_per_customer(
            [row for coefficient in grouped for row in grouped[coefficient]]
        )
        predicted[check_name] = (drop_penalty / cost) if cost else None
        out.append(
            f"    Coût temporel mesuré : {cost:.0f} s par client servi"
            if cost
            else "    Coût temporel mesuré : indisponible (aucun client servi)"
        )
        if predicted[check_name]:
            out.append(
                f"    → seuil PRÉDIT par la formule : TIME_SPAN ≈ {predicted[check_name]:,.0f}"
            )
        out.append(
            f"    → seuil OBSERVÉ (1er coefficient à service incomplet) : {point}"
            if point is not None
            else "    → aucun effondrement observé sur la plage balayée"
        )
        out.append("")

    a = collapses.get("A-releve")
    b = collapses.get("B-abandon10x")
    c = collapses.get("C-livre")

    out.append("=== VERDICT ===")

    # Bande d'acceptation de A : le relevé annonce 10/10 servis à 50 et 0/10 à
    # 200, donc un effondrement dans ]50 ; 200]. On élargit d'un cran de la
    # grille logarithmique, la position exacte n'étant connue qu'à un point près.
    ok_a = a is not None and 50 < a <= 500
    out.append(
        f"  A — reproduction du relevé : {'RÉUSSI' if ok_a else 'ÉCHOUÉ'} — "
        f"effondrement observé à {a}, attendu dans ]50 ; 500]."
    )

    # B est le vrai test : la pénalité d'abandon est multipliée par dix, tout le
    # reste est identique, et la formule prédit un seuil dix fois plus haut. La
    # bande [3 ; 30] tient compte de la granularité logarithmique du balayage —
    # deux points consécutifs sont déjà séparés d'un facteur 2 à 4.
    ratio_ab = (b / a) if (a and b) else None
    ok_b = ratio_ab is not None and 3.0 <= ratio_ab <= 30.0
    out.append(
        f"  B — prédiction du déplacement : {'RÉUSSI' if ok_b else 'ÉCHOUÉ'} — "
        f"seuil {b} contre {a}, soit ×{ratio_ab:.1f} pour un abandon ×10."
        if ratio_ab is not None
        else "  B — prédiction du déplacement : ÉCHOUÉ — seuil indéterminé."
    )

    out.append(
        f"  C — mesure de la configuration livrée : effondrement à {c}. "
        "Aucune attente n'est vérifiée ici, c'est la valeur à retenir."
    )

    # La granularité du balayage est logarithmique : le seuil observé est encadré
    # par deux points, pas localisé. On vérifie donc un ordre de grandeur, pas une
    # égalité — exiger mieux serait exiger une précision que le plan n'a pas.
    ok_formula = True
    for name, _, _, _, _ in CHECKS:
        observed, expected = collapses.get(name), predicted.get(name)
        if observed is None or not expected:
            continue
        ratio = observed / expected
        agrees = 0.2 <= ratio <= 5.0
        if name != "C-livre":
            ok_formula = ok_formula and agrees
        out.append(
            f"  Formule sur {name:<13} : observé {observed}, prédit {expected:,.0f} "
            f"(rapport {ratio:.2f}) — {'cohérent' if agrees else 'INCOHÉRENT'}"
        )

    success = bool(ok_a and ok_b and ok_formula)
    out.append("")
    if success:
        out.append("  → Le harnais retrouve seul la dégénérescence documentée, ET prédit")
        out.append("    correctement le déplacement de son seuil quand la pénalité")
        out.append("    d'abandon change. Il mesure le mécanisme, pas une coïncidence.")
    else:
        out.append("  → ÉCHEC. Si le contrôle A échoue, c'est le HARNAIS qui est faux, pas")
        out.append("    le solveur : le phénomène a été mesuré à la main avant lui.")
        out.append("    Vérifier d'abord que les facteurs atteignent bien Config — champ")
        out.append("    `factors_effective` de chaque ligne du journal.")

    out.append("")
    out.append("  Note mesurée, hors contrôle : à pénalité d'abandon 100 000, le seul")
    out.append("  DISTANCE_SPAN_COEFFICIENT = 30 livré suffit à rendre l'abandon rentable")
    out.append("  dès TIME_SPAN_COEFFICIENT = 1. Les deux termes d'étendue se cumulent ;")
    out.append("  aucun ne s'interprète isolément à pénalité d'abandon faible.")

    return "\n".join(out), success


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée en ligne de commande."""
    parser = argparse.ArgumentParser(
        prog="python -m experiments.validate",
        description="Vérifie que le harnais redécouvre une dégénérescence connue.",
    )
    parser.add_argument("--seeds", type=int, default=5, help="Nombre de graines (défaut 5)")
    parser.add_argument("--budget", type=int, default=5, help="Budget de résolution (défaut 5 s)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/out/validation.jsonl"),
        help="Journal de validation",
    )
    parser.add_argument("--scratch", type=Path, default=DEFAULT_SCRATCH)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--report-only", action="store_true", help="Relit --out sans rien exécuter")
    args = parser.parse_args(argv)

    if args.report_only:
        text, success = report(read_rows(args.out))
        print(text)
        return 0 if success else 1

    specs = build_specs(default_seeds(args.seeds), args.budget)
    done = completed_keys(args.out) if args.resume else set()
    pending = [spec for spec in specs if spec.resume_key not in done]

    print(f"Auto-validation : {len(pending)} exécution(s) sur {len(specs)}.")
    pool = RunPool(workers=args.workers, scratch_root=Path(args.scratch))
    with ResultStore(args.out) as store:
        for index, row in enumerate(pool.imap(pending), start=1):
            store.append(row)
            print(
                f"[{index}/{len(pending)}] {'ok ' if row.get('ok') else 'ÉCHEC'} "
                f"{row['config_label']:<40} graine={row['seed']} "
                f"{criterion.format_key(criterion.criterion_key(row))}",
                flush=True,
            )

    print()
    text, success = report(read_rows(args.out))
    print(text)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
