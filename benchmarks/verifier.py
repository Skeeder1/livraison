"""
Contrôle de faisabilité indépendant, en arithmétique Solomon.

`optimizer.verify` recontrôle le *document de tournée* produit par le dépôt :
il parle de mètres, de secondes, de hubs et de rechargements. Le chemin du banc
d'essai ne produit pas ce document — il extrait les tournées directement de
l'assignation OR-Tools — et l'unité y est l'unité Solomon, pas le mètre. Les
contrôles sont donc réécrits ici, à partir de la seule instance publiée.

Rien de ce que le solveur annonce n'est repris : ni sa distance, ni ses heures
d'arrivée, ni sa charge. On repart des tournées, c'est-à-dire des suites de
numéros de clients, et on recalcule tout.

Sémantique appliquée, celle de Solomon (1987) :

* le véhicule quitte le dépôt à l'instant :math:`e_0 = 0` ;
* l'arrivée au client *j* vaut le départ de *i* plus :math:`d_{ij}` ;
* le service commence à :math:`\\max(\\text{arrivée}, e_j)` — attendre est
  autorisé et **gratuit** ;
* le service doit commencer au plus tard à :math:`l_j` ; arriver après
  :math:`l_j` est une violation, arriver avant :math:`e_j` n'en est pas une ;
* le départ vaut le début de service plus :math:`s_j` ;
* le retour au dépôt doit avoir lieu au plus tard à :math:`l_0`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from benchmarks.solomon import Convention, SolomonInstance

#: Tolérance sur les comparaisons temporelles, en unités Solomon.
#:
#: Utile uniquement sous la convention EXACT, où les temps sont des flottants
#: en double précision et où une fenêtre peut être frôlée au bit près. Sous la
#: convention DIMACS tout est multiple d'un dixième et la tolérance ne sert pas.
TIME_TOLERANCE = 1e-6


@dataclass
class RouteCheck:
    """Résultat du contrôle d'une tournée."""

    vehicle: int
    customers: tuple[int, ...]
    distance: float = 0.0
    load: int = 0
    return_time: float = 0.0
    time_window_violations: list[str] = field(default_factory=list)
    capacity_violation: str | None = None
    horizon_violation: str | None = None

    @property
    def feasible(self) -> bool:
        return (
            not self.time_window_violations
            and self.capacity_violation is None
            and self.horizon_violation is None
        )


@dataclass
class SolutionCheck:
    """Résultat du contrôle d'une solution complète."""

    instance: str
    convention: Convention
    routes: list[RouteCheck]
    missing_customers: tuple[int, ...]
    duplicate_customers: tuple[int, ...]
    unknown_nodes: tuple[int, ...]

    @property
    def vehicles_used(self) -> int:
        """Nombre de tournées non vides. Une tournée vide n'est pas un véhicule."""
        return sum(1 for route in self.routes if route.customers)

    @property
    def total_distance(self) -> float:
        return sum(route.distance for route in self.routes)

    @property
    def feasible(self) -> bool:
        return (
            not self.missing_customers
            and not self.duplicate_customers
            and not self.unknown_nodes
            and all(route.feasible for route in self.routes)
        )

    def failures(self) -> list[str]:
        """Liste lisible de tout ce qui cloche. Vide si la solution est valide."""
        problems: list[str] = []
        if self.missing_customers:
            problems.append(f"clients non servis : {list(self.missing_customers)}")
        if self.duplicate_customers:
            problems.append(f"clients servis plusieurs fois : {list(self.duplicate_customers)}")
        if self.unknown_nodes:
            problems.append(f"nœuds inconnus dans les tournées : {list(self.unknown_nodes)}")
        for route in self.routes:
            if route.capacity_violation:
                problems.append(f"véhicule {route.vehicle} : {route.capacity_violation}")
            if route.horizon_violation:
                problems.append(f"véhicule {route.vehicle} : {route.horizon_violation}")
            for violation in route.time_window_violations:
                problems.append(f"véhicule {route.vehicle} : {violation}")
        return problems


def check_solution(
    instance: SolomonInstance,
    routes: list[list[int]],
    convention: Convention,
    *,
    tolerance: float = TIME_TOLERANCE,
) -> SolutionCheck:
    """
    Recalcule et contrôle une solution, sans rien reprendre du solveur.

    :param instance: Instance publiée
    :param routes: Une liste par véhicule, contenant les numéros de clients
        Solomon dans l'ordre de visite, dépôt exclu
    :param convention: Convention d'arrondi des distances et des temps
    :param tolerance: Tolérance sur les comparaisons temporelles
    :return: Le compte rendu complet
    """
    depot = instance.depot
    served: dict[int, int] = {}
    unknown: list[int] = []
    checks: list[RouteCheck] = []

    for vehicle, sequence in enumerate(routes):
        check = RouteCheck(vehicle=vehicle, customers=tuple(sequence))

        for number in sequence:
            if not 1 <= number <= instance.num_customers:
                unknown.append(number)
            else:
                served[number] = served.get(number, 0) + 1

        clock = float(depot.ready)
        previous = 0
        load = 0

        for number in sequence:
            if not 1 <= number <= instance.num_customers:
                continue
            node = instance.nodes[number]
            leg = instance.distance(previous, number, convention)
            check.distance += leg
            arrival = clock + leg
            start = max(arrival, float(node.ready))
            if start > node.due + tolerance:
                check.time_window_violations.append(
                    f"client {number} servi à {start:.4f}, fenêtre [{node.ready}, {node.due}]"
                )
            clock = start + node.service
            load += node.demand
            previous = number

        if sequence:
            back = instance.distance(previous, 0, convention)
            check.distance += back
            check.return_time = clock + back
            if check.return_time > depot.due + tolerance:
                check.horizon_violation = (
                    f"retour au dépôt à {check.return_time:.4f}, "
                    f"limite {depot.due}"
                )

        check.load = load
        if load > instance.capacity:
            check.capacity_violation = (
                f"charge {load} au-delà de la capacité {instance.capacity}"
            )

        checks.append(check)

    missing = tuple(sorted(set(range(1, instance.num_customers + 1)) - set(served)))
    duplicates = tuple(sorted(number for number, count in served.items() if count > 1))

    return SolutionCheck(
        instance=instance.name,
        convention=convention,
        routes=checks,
        missing_customers=missing,
        duplicate_customers=duplicates,
        unknown_nodes=tuple(sorted(set(unknown))),
    )
