"""
Une résolution, dans un processus isolé, et son contrôle.

`Config` porte des attributs de **classe** : les écrire change le comportement
de tout le processus. Un banc d'essai qui fait tourner plusieurs instances en
parallèle doit donc isoler chaque résolution dans son propre processus, ce que
`benchmarks.run_benchmark` organise et ce que ce module suppose acquis. Rien
ici ne restaure `Config` : le processus meurt avec la mesure.

Deux contrôles séparent une mesure d'une affirmation :

* `audit_arc_costs` relit, arc par arc, le coût que le modèle a **réellement**
  employé, et le compare à la distance Solomon attendue. Le repli du temps de
  service dans la matrice est une transformation subtile ; la supposer correcte
  sans la lire serait exactement le genre de raccourci que ce banc d'essai
  existe pour éviter ;
* `benchmarks.verifier` recalcule ensuite tout depuis les seules tournées.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from benchmarks.convert import build_plan, write_dataset
from benchmarks.solomon import Convention, SolomonInstance
from benchmarks.verifier import check_solution


@dataclass
class RunOutcome:
    """Tout ce qu'une résolution a produit, mesures et contrôles compris."""

    instance: str
    convention: str
    fleet_offered: int
    budget_seconds: int
    solved: bool
    solve_seconds: float = 0.0
    routes: list[list[int]] = field(default_factory=list)
    vehicles_used: int = 0
    distance: float = 0.0
    feasible: bool = False
    failures: list[str] = field(default_factory=list)
    served_customers: int = 0
    arc_cost_mismatches: list[str] = field(default_factory=list)
    time_transit_mismatches: list[str] = field(default_factory=list)
    solver_objective: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def apply_plan(config_values: dict) -> None:
    """
    Écrit le plan de conversion dans `Config`, pour ce processus uniquement.

    :param config_values: Clés de `Config` à écrire
    """
    from optimizer.config import Config

    Config.update(**config_values)


def extract_routes(manager, routing, solution, num_customers: int) -> list[list[int]]:
    """
    Extrait les tournées de l'assignation, en numéros de clients Solomon.

    Aucun nœud additionnel n'existe ici : `NUM_UNLOAD_DEPOTS` et `NUM_HUBS`
    valent 0, donc les seuls nœuds sont le dépôt (0) et les clients (1..n), et
    la numérotation du modèle coïncide avec celle de Solomon.

    :param manager: Gestionnaire d'indices OR-Tools
    :param routing: Modèle de routage
    :param solution: Assignation retournée par le solveur
    :param num_customers: Nombre de clients de l'instance
    :return: Une liste de numéros de clients par véhicule
    """
    routes: list[list[int]] = []
    for vehicle in range(routing.vehicles()):
        index = routing.Start(vehicle)
        sequence: list[int] = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if 1 <= node <= num_customers:
                sequence.append(node)
            index = solution.Value(routing.NextVar(index))
        routes.append(sequence)
    return routes


def audit_arc_costs(
    instance: SolomonInstance,
    convention: Convention,
    manager,
    routing,
    solution,
    meters_factor: int,
    time_scale: int,
) -> tuple[list[str], list[str]]:
    """
    Relit les coûts d'arc et les transits temporels réellement employés.

    Pour chaque arc parcouru, on interroge le modèle — `GetArcCostForVehicle`
    pour le coût, la dimension `Time` pour le transit — et on compare à ce que
    la conversion promet :

    * coût attendu : :math:`\\lfloor (d_{ij} + s_i) \\times \\text{meters} \\rfloor` ;
    * transit attendu : :math:`\\lfloor (d_{ij} + s_i) \\times \\text{time} \\rfloor`,
      c'est-à-dire le temps de service au départ plus le trajet, la sémantique
      de Solomon.

    :return: Les écarts de coût, puis les écarts de transit ; deux listes vides
        si le modèle calcule bien ce qu'on croit lui avoir donné
    """
    cost_issues: list[str] = []
    transit_issues: list[str] = []
    time_dimension = routing.GetDimensionOrDie('Time')

    for vehicle in range(routing.vehicles()):
        index = routing.Start(vehicle)
        while not routing.IsEnd(index):
            nxt = solution.Value(routing.NextVar(index))
            from_node = manager.IndexToNode(index)
            to_node = manager.IndexToNode(nxt)

            # L'arc dépôt→dépôt d'un véhicule inutilisé est délibérément écrasé
            # par le solveur (sentinelle de rechargement) : on l'exclut du
            # contrôle, et on le signale ailleurs comme une distorsion connue.
            if from_node == 0 and to_node == 0:
                index = nxt
                continue

            leg = instance.distance(from_node, to_node, convention)
            folded = leg + instance.nodes[from_node].service

            actual_cost = routing.GetArcCostForVehicle(index, nxt, vehicle)
            expected_cost = int(folded * meters_factor)
            if actual_cost != expected_cost:
                cost_issues.append(
                    f"arc {from_node}→{to_node} : coût {actual_cost}, attendu {expected_cost}"
                )

            # `GetTransitValue` interroge l'évaluateur enregistré. Passer par
            # `solution.Value(TransitVar(index))` fait tomber l'interpréteur :
            # la variable de transit n'est pas dans l'assignation, le solveur ne
            # lève pas, il déréférence.
            actual_transit = time_dimension.GetTransitValue(index, nxt, vehicle)
            expected_transit = int(folded * time_scale)
            if actual_transit != expected_transit:
                transit_issues.append(
                    f"arc {from_node}→{to_node} : transit {actual_transit}, "
                    f"attendu {expected_transit}"
                )

            index = nxt

    return cost_issues, transit_issues


def run_once(
    instance: SolomonInstance,
    convention: Convention,
    *,
    fleet: int,
    budget_seconds: int,
    workdir: str | Path,
    cost_scale: int | None = None,
) -> RunOutcome:
    """
    Convertit, résout et contrôle une instance. À exécuter dans un processus dédié.

    :param instance: Instance publiée
    :param convention: Convention d'arrondi
    :param fleet: Nombre de véhicules mis à disposition
    :param budget_seconds: Budget de recherche, en secondes
    :param workdir: Répertoire de travail du jeu de données converti
    :param cost_scale: Poids de la distance devant l'attente ; défaut du module
        `benchmarks.convert` si None
    :return: Le compte rendu de la mesure
    """
    from optimizer.data_loader import load_data
    from optimizer.solver import solve_vrp

    outcome = RunOutcome(
        instance=instance.name,
        convention=convention.value,
        fleet_offered=fleet,
        budget_seconds=budget_seconds,
        solved=False,
    )

    try:
        kwargs = {} if cost_scale is None else {'cost_scale': cost_scale}
        plan = build_plan(instance, convention, **kwargs)
        apply_plan(plan.config)
        write_dataset(instance, convention, workdir, fleet=fleet, plan=plan)

        data = load_data(str(workdir))
        data['time_limit'] = int(budget_seconds)
        # Épinglé comme dans `optimizer.scenario` : sans cela la valeur par
        # défaut de la recherche à grand voisinage pourrait changer d'une
        # version d'OR-Tools à l'autre et brouiller la comparaison des budgets.
        data['lns_time_limit_ms'] = 100

        started = time.monotonic()
        manager, routing, solution = solve_vrp(data)
        outcome.solve_seconds = round(time.monotonic() - started, 2)

        if solution is None:
            outcome.failures.append("aucune solution trouvée dans le budget")
            return outcome

        outcome.solved = True
        outcome.solver_objective = solution.ObjectiveValue()
        outcome.routes = extract_routes(manager, routing, solution, instance.num_customers)
        outcome.served_customers = sum(len(route) for route in outcome.routes)

        cost_issues, transit_issues = audit_arc_costs(
            instance, convention, manager, routing, solution,
            plan.meters_factor, plan.time_scale,
        )
        outcome.arc_cost_mismatches = cost_issues[:10]
        outcome.time_transit_mismatches = transit_issues[:10]

        check = check_solution(instance, outcome.routes, convention)
        outcome.vehicles_used = check.vehicles_used
        outcome.distance = round(check.total_distance, 4)
        outcome.feasible = check.feasible
        outcome.failures = check.failures()

    except Exception as exc:  # noqa: BLE001 — un échec doit être rapporté, pas masqué
        outcome.error = f"{type(exc).__name__}: {exc}"

    return outcome


def run_case(payload: dict) -> dict:
    """
    Point d'entrée d'un processus de travail.

    L'instance est repassée en clair plutôt que par son chemin : elle est
    immuable et petite, et la relire dans chaque processus multiplierait les
    occasions de lire un fichier différent de celui qui a été validé.

    :param payload: Arguments sérialisables de la mesure
    :return: Le compte rendu, sérialisable
    """
    outcome = run_once(
        payload['instance'],
        Convention(payload['convention']),
        fleet=payload['fleet'],
        budget_seconds=payload['budget_seconds'],
        workdir=payload['workdir'],
        cost_scale=payload.get('cost_scale'),
    )
    result = outcome.to_dict()
    result['label'] = payload.get('label', '')
    return result
