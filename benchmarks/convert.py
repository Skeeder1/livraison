"""
Traduction d'une instance Solomon vers le jeu de données que le dépôt sait lire.

`optimizer.data_loader.load_data` attend un répertoire contenant `colis.json`,
`livreurs.json`, `hubs.json`, `weights.json` et `distance_matrix.npy`. Ce module
les écrit à partir d'une instance publiée, sans toucher à `optimizer/`.

Trois obstacles séparent le modèle du dépôt du CVRPTW standard. Deux se
contournent par la seule configuration ; le troisième demande un changement de
variables, et le quatrième ne se contourne pas du tout.

**1. Le temps de service est proportionnel à la demande.**
`optimizer.solver.service_time` calcule ``|demande| × SERVICE_TIME_PER_UNIT``.
Solomon donne un temps de service **constant par client**, indépendant de la
demande : 90 pour la famille C1, 10 pour R1 et RC1. Aucune valeur de
`SERVICE_TIME_PER_UNIT` ne rend les deux formules égales dès que deux clients
ont des demandes différentes — ce qui est le cas partout ici.

Le contournement est un changement de variables, et il est **exact**. Le temps
de transit du modèle vaut ``service(i) + trajet(i, j)``. On met
`SERVICE_TIME_PER_UNIT` à 0 et on replie le temps de service dans la matrice,
au nœud d'origine :

.. math:: M_{ij} = d_{ij} + s_i

Le temps de transit redevient alors exactement :math:`s_i + d_{ij}`, la
sémantique de Solomon. Les fenêtres horaires sont donc respectées au sens
strict, ce qui est le point qui compte.

Le prix de ce repli porte sur la **dimension Distance**, qui lit la même
matrice : le coût d'arc devient :math:`d_{ij} + s_i` au lieu de :math:`d_{ij}`.
Mais chaque client possède exactement un arc sortant dans une solution qui le
sert, et le dépôt a :math:`s_0 = 0` ; le surcoût vaut donc
:math:`\\sum_i s_i`, une **constante** identique pour toute solution servant
tous les clients. Elle ne déplace pas l'optimum, et la distance vraie se
retrouve en la retranchant. Le banc d'essai ne s'en remet d'ailleurs pas au
coût annoncé par le solveur : il recalcule la distance depuis les tournées
(`benchmarks.verifier`).

**2. Les fenêtres horaires sont molles par défaut.**
`Config.TIME_WINDOWS_OPTIONAL` vaut True : les fenêtres deviennent des
pénalités, pas des contraintes. Une solution qui livre en retard reste
acceptée. Mis à False, `setup_time_constraints` pose de vraies bornes sur la
variable de cumul, ce qu'exige Solomon.

**3. Le rechargement en cours de tournée n'existe pas chez Solomon.**
`Config.NUM_UNLOAD_DEPOTS` duplique le dépôt en autant de nœuds de
rechargement. Mis à 0, aucun nœud n'est ajouté et le modèle redevient celui du
CVRPTW standard. Idem pour `NUM_HUBS`, qui commande les transferts entre
coursiers.

**4. Un terme d'objectif étranger à Solomon, qu'aucune clé ne débranche.**
`setup_time_constraints` appelle ``SetSlackCostCoefficientForVehicle(100, v)``.
Le nom suggère un réglage du départ, mais l'appel porte sur **toute** la
dimension temporelle et tous ses nœuds : **attendre coûte 100 par unité de
temps**. Chez Solomon, attendre est gratuit.

Le terme est réel et mesurable. Sur R101, ``objectif − somme des coûts d'arc``
vaut exactement ``attente totale × 100``, au dernier chiffre près.

Il ne se débranche pas, mais il se **dilue**, parce qu'il est constant quand les
coûts de distance, eux, sont réglables : une unité Solomon d'attente coûte
``100 × DISTANCE_TO_TIME_FACTOR``, une unité Solomon de distance coûte
``DISTANCE_TO_METERS_FACTOR``. Leur rapport est libre, et c'est `cost_scale`.
Mesuré sur R101 à 20 s, à flotte de 20 : à poids égal la distance sort à
1 841,7, à rapport 100 elle tombe à 1 669,1 et n'améliore plus au-delà. D'où
`DEFAULT_COST_SCALE`.

**Ce qui, en revanche, n'est pas un problème.** `create_evaluator_functions`
remplace le coût de l'arc dépôt→dépôt par ``vehicle_max_distance``, et c'est
l'arc d'un véhicule inutilisé — de quoi facturer une tournée entière à qui
laisse un véhicule au garage, soit l'inverse de la minimisation de flotte.
Vérification faite, cela ne se produit pas : `RoutingModel` ne compte ni le
coût d'arc ni le coût fixe d'une tournée vide. Mesuré sur C101 avec 25
véhicules pour 10 utilisés, ``GetArcCostForVehicle`` retourne 0 sur l'arc
Start→End d'un véhicule vide, et l'objectif égale la somme des coûts d'arc des
seules tournées non vides. La sentinelle est donc inerte ici.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from benchmarks.solomon import Convention, SolomonInstance

#: Facteur d'échelle temporel par convention.
#:
#: Le modèle tronque à l'entier (``int(distance × facteur)``). Sous la
#: convention DIMACS toutes les distances sont des multiples d'un dixième, donc
#: un facteur 10 rend l'arithmétique **exacte** : aucune troncature ne se
#: produit, et les temps du solveur sont ceux de Solomon au bit près.
#:
#: Sous la convention EXACT les distances sont des flottants quelconques ; la
#: troncature est inévitable et on la rend négligeable par un facteur élevé.
#: Elle joue **à la baisse** — un trajet tronqué est plus court que le vrai —
#: donc elle relâche imperceptiblement les fenêtres. C'est exactement pourquoi
#: `benchmarks.verifier` recontrôle en arithmétique non tronquée.
TIME_SCALE: dict[Convention, int] = {
    Convention.DIMACS: 10,
    Convention.EXACT: 1000,
}

#: Rapport entre le poids d'une unité de distance et celui d'une unité
#: d'attente dans l'objectif, divisé par 100.
#:
#: Le coefficient d'attente est écrit en dur à 100 dans `optimizer.solver`. Une
#: unité Solomon d'attente coûte donc ``100 × TIME_SCALE`` ; une unité Solomon
#: de distance coûte ``DISTANCE_TO_METERS_FACTOR = TIME_SCALE × cost_scale``.
#: Le rapport distance/attente vaut ``cost_scale / 100``. À 10 000, la distance
#: pèse cent fois l'attente, ce qui ramène le terme parasite au niveau du bruit
#: sans faire exploser les coûts d'arc.
DEFAULT_COST_SCALE = 10_000

#: Pénalité d'abandon d'un client, en unités de coût d'arc.
#:
#: `optimizer.solver` pose une disjonction sur chaque client : l'abandonner est
#: toujours permis, contre pénalité. Solomon exige que tous soient servis. La
#: pénalité est donc portée très au-delà du coût de n'importe quel détour, ce
#: qui rend l'abandon économiquement impossible sans être interdit — et un
#: abandon résiduel serait de toute façon détecté comme une infaisabilité.
DROP_PENALTY = 10 ** 14


@dataclass(frozen=True)
class ConversionPlan:
    """
    Ce qu'il faut écrire dans `Config` pour que le modèle lise l'instance juste.

    :param config: Les clés de `Config` à écrire, telles quelles
    :param service_offset: La constante :math:`\\sum_i s_i` repliée dans la
        matrice, exprimée en unités Solomon. À retrancher du coût d'arc cumulé
        si l'on veut lire une distance dans l'objectif du solveur.
    :param time_scale: Facteur d'échelle temporel appliqué
    :param meters_factor: Facteur d'échelle des coûts d'arc
    """

    config: dict[str, object]
    service_offset: float
    time_scale: int
    meters_factor: int


def build_plan(
    instance: SolomonInstance,
    convention: Convention,
    *,
    cost_scale: int = DEFAULT_COST_SCALE,
) -> ConversionPlan:
    """
    Calcule la configuration à appliquer au processus avant la résolution.

    :param instance: Instance publiée
    :param convention: Convention d'arrondi
    :param cost_scale: Poids relatif de la distance devant l'attente (voir
        `DEFAULT_COST_SCALE`)
    :return: Le plan de conversion
    """
    time_scale = TIME_SCALE[convention]
    meters_factor = time_scale * cost_scale

    service_offset = float(sum(node.service for node in instance.customers))

    # Borne haute du cumul de la dimension Distance, service replié compris.
    # La borne sert aussi de coût sentinelle sur l'arc dépôt→dépôt : la garder
    # au plus juste limite ce que coûte un véhicule laissé inutilisé.
    matrix = instance.distance_matrix(convention)
    span = float(matrix.max()) * (instance.num_customers + 1) + service_offset
    max_distance = int(math.ceil(span)) * meters_factor

    horizon = instance.depot.due * time_scale

    return ConversionPlan(
        config={
            # Le temps de service n'est plus calculé par le modèle : il est
            # replié dans la matrice (voir l'en-tête du module).
            'SERVICE_TIME_PER_UNIT': 0,
            # Temps de trajet = distance, à l'échelle près.
            'DISTANCE_TO_TIME_FACTOR': float(time_scale),
            'DISTANCE_TO_METERS_FACTOR': float(meters_factor),
            # Ni hub de transfert, ni rechargement en cours de tournée :
            # le CVRPTW de Solomon n'en a pas.
            'NUM_HUBS': 0,
            'NUM_UNLOAD_DEPOTS': 0,
            # Fenêtres horaires dures, comme l'exige Solomon.
            'TIME_WINDOWS_OPTIONAL': False,
            # Aucun terme d'équilibrage : ils n'appartiennent pas à l'objectif
            # publié, qui ne connaît que le nombre de véhicules et la distance.
            'TIME_SPAN_COEFFICIENT': 0,
            'CAPACITY_SPAN_COEFFICIENT': 0,
            'DISTANCE_SPAN_COEFFICIENT': 0,
            # La flotte est fixée par le nombre de livreurs écrits dans le jeu
            # de données ; un coût fixe par véhicule fausserait la distance sans
            # rien apporter.
            'VEHICLE_FIXED_COST_METERS': 0,
            'TRANSFER_PENALTY_METERS': 0,
            'DROP_CUSTOMER_PENALTY_METERS': DROP_PENALTY,
            'VEHICLE_MAX_DISTANCE_METERS': max_distance,
            'TIME_HORIZON_SECONDS': horizon,
            'DEPOT_POSITION': (instance.depot.x, instance.depot.y),
        },
        service_offset=service_offset,
        time_scale=time_scale,
        meters_factor=meters_factor,
    )


def write_dataset(
    instance: SolomonInstance,
    convention: Convention,
    directory: str | Path,
    *,
    fleet: int,
    plan: ConversionPlan | None = None,
) -> ConversionPlan:
    """
    Écrit les cinq fichiers du jeu de données, plus le plan de conversion.

    :param instance: Instance publiée
    :param convention: Convention d'arrondi
    :param directory: Répertoire à remplir ; créé s'il n'existe pas
    :param fleet: Nombre de véhicules à mettre à disposition
    :param plan: Plan déjà calculé, ou None pour le calculer ici
    :return: Le plan de conversion appliqué
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    plan = plan or build_plan(instance, convention)

    # Matrice repliée : le temps de service du nœud d'origine est ajouté à
    # chaque arc sortant. La ligne du dépôt n'en reçoit aucun (s_0 = 0), et la
    # diagonale non plus, ce qui laisse l'arc dépôt→dépôt à 0 — il sera de toute
    # façon écrasé par la sentinelle du solveur.
    matrix = instance.distance_matrix(convention)
    service = np.array([node.service for node in instance.nodes], dtype=float)
    folded = matrix + service[:, None]
    np.fill_diagonal(folded, 0.0)
    np.save(directory / 'distance_matrix.npy', folded)

    scale = plan.time_scale
    colis = [
        {
            'id': node.number,
            'position': [node.x, node.y],
            'volume': node.demand,
            'tw_start': node.ready * scale,
            'tw_end': node.due * scale,
        }
        for node in instance.customers
    ]
    _dump(directory / 'colis.json', colis)

    livreurs = [
        {
            'id': vehicle,
            'capacity': instance.capacity,
            'start_time': instance.depot.ready * scale,
            'end_time': instance.depot.due * scale,
        }
        for vehicle in range(fleet)
    ]
    _dump(directory / 'livreurs.json', livreurs)

    # Aucun hub : Solomon ne connaît pas le transfert entre coursiers.
    _dump(directory / 'hubs.json', [])

    # `load_data` exige les colonnes `criterion` et `weight`, mais rien en aval
    # du chemin de résolution ne relit ce tableau ; il est écrit pour satisfaire
    # la validation, pas pour peser sur quoi que ce soit.
    _dump(directory / 'weights.json', [{'criterion': 'distance', 'weight': 1.0}])

    return plan


def _dump(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding='utf-8')
