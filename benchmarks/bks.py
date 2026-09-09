"""
Registre des meilleures solutions connues publiées, et de leur provenance.

**Il existe deux familles de valeurs publiées, et elles ne sont pas
comparables.** C'est le piège central de ce banc d'essai : confondre les deux
fabrique un écart fantôme de quelques dixièmes à quatre pour cent, sans que
rien ne le signale.

===========================  ====================================  ==============================
                             SINTEF (registre TOP)                  CVRPLIB / DIMACS / PyVRP
===========================  ====================================  ==============================
Objectif                     hiérarchique : véhicules puis distance  distance totale seule
Flotte                       minimisée en premier                    libre
Arithmétique                 double précision, affichage à 2 déc.    troncature au dixième par arc
Statut                       meilleure connue, non prouvée optimale  **optimale prouvée**
===========================  ====================================  ==============================

SINTEF l'écrit lui-même en tête de sa page : « Exact methods typically use a
monolithic total distance objective and use integral or low precision distance
and time calculations. Hence, results are not directly comparable. »

Les deux familles sont donc conservées ici, chacune reliée à la convention de
distance qui la produit. Comparer une valeur mesurée à la mauvaise famille est
une faute de méthode, pas une approximation.
"""
from __future__ import annotations

from dataclasses import dataclass

from benchmarks.solomon import Convention


@dataclass(frozen=True)
class BestKnown:
    """
    Une valeur publiée, avec ce qu'il faut pour savoir à quoi elle se compare.

    :param instance: Nom de l'instance
    :param vehicles: Nombre de véhicules de la solution publiée
    :param distance: Distance totale publiée
    :param convention: Convention d'arrondi sous laquelle cette distance vaut
    :param objective: `hierarchical` (véhicules puis distance) ou `distance`
    :param proven_optimal: Vrai si la source annonce l'optimalité prouvée
    :param source: URL d'où la valeur a été relevée
    :param attribution: Auteurs crédités par la source
    """

    instance: str
    vehicles: int
    distance: float
    convention: Convention
    objective: str
    proven_optimal: bool
    source: str
    attribution: str


#: Registre SINTEF, objectif hiérarchique, double précision.
#: Relevé le 2026-09-09 sur la page « 100 customers » du registre TOP.
SINTEF_URL = 'https://www.sintef.no/projectweb/top/vrptw/solomon-benchmark/100-customers/'

#: Registre CVRPLIB, objectif « distance seule », troncature au dixième.
#: Les mêmes valeurs sont redistribuées par PyVRP, qui déclare explicitement la
#: convention DIMACS et déclare les reprendre de CVRPLIB.
CVRPLIB_URL = 'https://vrp.atd-lab.inf.puc-rio.br/index.php/en/instances/2'
PYVRP_URL = 'https://github.com/PyVRP/Instances/tree/main/VRPTW/Solomon'
DIMACS_RULES_URL = (
    'https://dimacs.rutgers.edu/images/programs/implementation_challenges/'
    'archive/VRPTW_Competition_Rules.pdf'
)

BKS: dict[tuple[str, str], BestKnown] = {}


def _register(entry: BestKnown) -> None:
    BKS[(entry.instance, entry.objective)] = entry


for _instance, _vehicles, _distance, _attribution in (
    ('C101', 10, 828.94, 'Rochat & Taillard (1995)'),
    ('R101', 19, 1650.80, 'Homberger (2000)'),
    ('RC101', 14, 1696.95, 'Taillard, Badeau, Gendreau, Guertin & Potvin (1997)'),
):
    _register(BestKnown(
        instance=_instance,
        vehicles=_vehicles,
        distance=_distance,
        convention=Convention.EXACT,
        objective='hierarchical',
        proven_optimal=False,
        source=SINTEF_URL,
        attribution=_attribution,
    ))

for _instance, _vehicles, _distance in (
    ('C101', 10, 827.3),
    ('R101', 20, 1637.7),
    ('RC101', 15, 1619.8),
):
    _register(BestKnown(
        instance=_instance,
        vehicles=_vehicles,
        distance=_distance,
        convention=Convention.DIMACS,
        objective='distance',
        proven_optimal=True,
        source=f'{CVRPLIB_URL} (redistribué par {PYVRP_URL})',
        attribution='CVRPLIB, optimum prouvé ; convention DIMACS',
    ))


def best_known(instance: str, objective: str) -> BestKnown:
    """
    Retourne la valeur publiée pour une instance et un objectif.

    :param instance: Nom de l'instance
    :param objective: `hierarchical` ou `distance`
    :return: L'entrée du registre
    :raises KeyError: couple absent du registre
    """
    try:
        return BKS[(instance, objective)]
    except KeyError:
        raise KeyError(
            f"Aucune valeur publiée pour {instance} / {objective}. "
            f"Disponibles : {sorted(BKS)}"
        ) from None


def gap_percent(measured: float, reference: float) -> float:
    """
    Écart relatif à la référence, en pourcentage : (mesuré − référence) / référence × 100.

    :param measured: Valeur mesurée
    :param reference: Valeur publiée
    :return: Écart en pourcentage, positif quand la mesure est moins bonne
    """
    return (measured - reference) / reference * 100.0
