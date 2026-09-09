"""
Campagne de mesure : le solveur du dépôt contre les valeurs publiées.

Chaque résolution part dans son propre processus, pour deux raisons. La
première est technique : `optimizer.config.Config` porte des attributs de
classe, et deux instances converties différemment se corrompraient
mutuellement dans un même interpréteur. La seconde est méthodologique : une
mesure qui fait tomber l'interpréteur ne doit pas emporter la campagne.

Le parallélisme est plafonné (`--workers`, 12 par défaut) parce que la
recherche d'OR-Tools est mono-thread — `RoutingSearchParameters` n'expose aucun
réglage de parallélisme — et que saturer les seize cœurs de la machine ferait
concurrencer les mesures entre elles, au détriment du budget qu'on croit leur
avoir donné.

Deux régimes de flotte sont mesurés, et l'écart entre les deux est lui-même un
résultat :

``bks``
    Exactement le nombre de véhicules de la solution publiée. C'est la
    comparaison honnête sur la distance : à flotte égale, quelle distance ?
``libre``
    La flotte annoncée par l'instance (25 véhicules). Mesure ce que le solveur
    choisit quand on le laisse faire — et met en évidence la sentinelle qui
    facture un véhicule inutilisé (voir `benchmarks.convert`).

Usage :

    .venv/bin/python -m benchmarks.run_benchmark
    .venv/bin/python -m benchmarks.run_benchmark --budgets 10 --instances C101
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from benchmarks.bks import best_known, gap_percent
from benchmarks.runner import run_case
from benchmarks.solomon import Convention, load_instance

#: Répertoire de cache des instances, relatif à ce paquet.
INSTANCES_DIR = Path(__file__).parent / 'instances'

#: Répertoire où sont déposés les résultats bruts et le tableau final.
RESULTS_DIR = Path(__file__).parent / 'results'

#: Les trois classes de Solomon : groupée, aléatoire, mixte.
DEFAULT_INSTANCES = ('C101', 'R101', 'RC101')

DEFAULT_BUDGETS = (10, 60, 300)

#: Chaque famille de valeurs publiées impose sa convention d'arrondi et son
#: objectif ; les mélanger fabrique un écart fantôme. Voir `benchmarks.bks`.
FAMILIES = (
    ('distance', Convention.DIMACS),
    ('hierarchical', Convention.EXACT),
)


def build_cases(instances, budgets, fleets, cost_scale):
    """
    Construit la liste des mesures à lancer.

    Les cas sont ordonnés du budget le plus long au plus court : un
    ordonnanceur qui prend les tâches dans l'ordre garde ainsi tous ses
    processus occupés jusqu'à la fin, au lieu de finir sur une longue mesure
    solitaire pendant que onze cœurs attendent.

    :param instances: Instances chargées, par nom
    :param budgets: Budgets de recherche, en secondes
    :param fleets: Régimes de flotte à mesurer (`bks`, `libre`)
    :param cost_scale: Poids de la distance devant l'attente
    :return: Liste de charges utiles pour `benchmarks.runner.run_case`
    """
    cases = []
    for objective, convention in FAMILIES:
        for name, instance in instances.items():
            reference = best_known(name, objective)
            for regime in fleets:
                fleet = reference.vehicles if regime == 'bks' else instance.num_vehicles
                for budget in budgets:
                    cases.append({
                        'instance': instance,
                        'convention': convention.value,
                        'fleet': fleet,
                        'budget_seconds': budget,
                        'workdir': tempfile.mkdtemp(prefix=f'bench-{name}-'),
                        'cost_scale': cost_scale,
                        'label': f'{objective}/{regime}',
                    })
    cases.sort(key=lambda case: -case['budget_seconds'])
    return cases


def annotate(result: dict) -> dict:
    """
    Ajoute à un résultat l'écart à la valeur publiée qui lui correspond.

    :param result: Compte rendu brut d'une mesure
    :return: Le même, enrichi des champs de comparaison
    """
    objective, regime = result['label'].split('/')
    reference = best_known(result['instance'], objective)
    result['objective'] = objective
    result['fleet_regime'] = regime
    result['bks_vehicles'] = reference.vehicles
    result['bks_distance'] = reference.distance
    result['bks_source'] = reference.source
    result['bks_proven_optimal'] = reference.proven_optimal
    # L'écart n'a de sens que sur une solution valide. Sur une solution qui
    # viole une fenêtre ou laisse un client de côté, il mesurerait la distance
    # d'un trajet que personne ne peut effectuer.
    result['gap_percent'] = (
        round(gap_percent(result['distance'], reference.distance), 2)
        if result['feasible'] and result['solved'] else None
    )
    return result


def format_table(results: list[dict]) -> str:
    """Met en tableau les résultats, une ligne par mesure."""
    header = (
        f"{'instance':8s} {'objectif':13s} {'flotte':7s} {'budget':>7s} "
        f"{'veh':>4s} {'BKS':>4s} {'distance':>10s} {'BKS dist':>10s} "
        f"{'ecart %':>8s} {'valide':>7s}"
    )
    lines = [header, '-' * len(header)]
    ordering = {'C101': 0, 'R101': 1, 'RC101': 2}
    for row in sorted(results, key=lambda r: (
        r['objective'], ordering.get(r['instance'], 9), r['fleet_regime'], r['budget_seconds']
    )):
        gap = f"{row['gap_percent']:+8.2f}" if row['gap_percent'] is not None else '       —'
        lines.append(
            f"{row['instance']:8s} {row['objective']:13s} {row['fleet_regime']:7s} "
            f"{row['budget_seconds']:6d}s {row['vehicles_used']:4d} {row['bks_vehicles']:4d} "
            f"{row['distance']:10.2f} {row['bks_distance']:10.2f} {gap} "
            f"{'oui' if row['feasible'] else 'NON':>7s}"
        )
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--instances', nargs='+', default=list(DEFAULT_INSTANCES))
    parser.add_argument('--budgets', nargs='+', type=int, default=list(DEFAULT_BUDGETS))
    parser.add_argument('--fleets', nargs='+', default=['bks', 'libre'],
                        choices=['bks', 'libre'])
    parser.add_argument('--workers', type=int, default=12,
                        help="Processus simultanés (12 par défaut sur une machine à 16 cœurs)")
    parser.add_argument('--cost-scale', type=int, default=None,
                        help="Poids de la distance devant l'attente ; voir benchmarks.convert")
    parser.add_argument('--out', type=Path, default=RESULTS_DIR)
    args = parser.parse_args(argv)

    instances = {name: load_instance(INSTANCES_DIR, name) for name in args.instances}
    cases = build_cases(instances, args.budgets, args.fleets, args.cost_scale)

    total_cpu = sum(case['budget_seconds'] for case in cases)
    print(f"{len(cases)} mesures, {total_cpu} s de budget cumulé, "
          f"{args.workers} processus", file=sys.stderr)

    # Import tardif : sous « spawn », le module est réimporté dans chaque
    # processus enfant, et `main` ne doit pas y être rejoué.
    from concurrent.futures import ProcessPoolExecutor

    started = time.monotonic()
    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for done, result in enumerate(pool.map(run_case, cases), start=1):
            results.append(annotate(result))
            print(f"  [{done}/{len(cases)}] {result['instance']} {result['label']} "
                  f"{result['budget_seconds']}s → {result['vehicles_used']} veh, "
                  f"{result['distance']:.2f}", file=sys.stderr, flush=True)
    elapsed = time.monotonic() - started

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'results.json').write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    table = format_table(results)
    (args.out / 'table.txt').write_text(table + '\n', encoding='utf-8')

    print(f"\n{table}")
    print(f"\n{len(results)} mesures en {elapsed:.0f} s de temps réel.")

    invalid = [r for r in results if not r['feasible']]
    if invalid:
        print(f"\n{len(invalid)} mesure(s) non valides :")
        for row in invalid:
            reason = row['error'] or ' ; '.join(row['failures'][:3]) or 'inconnue'
            print(f"  {row['instance']} {row['label']} {row['budget_seconds']}s — {reason}")

    audited = [r for r in results if r['arc_cost_mismatches'] or r['time_transit_mismatches']]
    if audited:
        print(f"\n{len(audited)} mesure(s) où les coûts d'arc du modèle ne sont pas "
              f"ceux de Solomon — la conversion est fausse, les écarts ne veulent rien dire.")
        for row in audited[:5]:
            print(f"  {row['instance']} {row['label']} : "
                  f"{(row['arc_cost_mismatches'] + row['time_transit_mismatches'])[:2]}")
    else:
        print("\nCoûts d'arc et transits temporels vérifiés conformes à Solomon "
              "sur toutes les mesures.")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
