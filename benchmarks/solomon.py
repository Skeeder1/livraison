"""
Lecture des instances Solomon (1987) et conventions de distance.

Deux formats d'entrée sont acceptés, parce que les miroirs publics ne
distribuent pas tous le même :

* le format Solomon historique, en colonnes (`C101.txt`) : une ligne de nom,
  puis `VEHICLE` / `NUMBER CAPACITY`, puis `CUSTOMER` et sept colonnes
  ``CUST NO. / XCOORD. / YCOORD. / DEMAND / READY TIME / DUE DATE / SERVICE
  TIME``. Le client 0 est le dépôt ;
* le format VRPLIB (`C101.vrp`), tel que distribué par le dépôt
  ``PyVRP/Instances``, qui porte les mêmes grandeurs en sections nommées.

Les deux sont lus, et `check_agreement` les compare champ à champ : c'est ce
qui permet d'affirmer que le fichier de commodité téléchargé sur un miroir
GitHub porte bien l'instance publiée, et pas une copie retouchée.

**Conventions de distance.** La littérature en emploie deux, incompatibles, et
les mélanger fabrique un écart fantôme de plusieurs pour cent :

* ``EXACT`` — distance euclidienne en double précision, sans arrondi
  intermédiaire. C'est la convention du registre SINTEF, qui écrit :
  « Distance and time should be calculated with double precision, total
  distance results are rounded to two decimals » ;
* ``DIMACS`` — distance euclidienne tronquée au dixième, **arc par arc** :
  :math:`d_{ij} = \\lfloor 10\\,e_{ij} \\rfloor / 10`. C'est la convention
  originale de Solomon (1987), reprise par le 12e DIMACS Implementation
  Challenge, par CVRPLIB et par PyVRP.

Tronquer le total plutôt que chaque arc est l'erreur de reproduction classique :
elle ne donne ni l'une ni l'autre des deux familles de valeurs publiées.

Dans les deux cas le temps de trajet **égale** la distance (vitesse unitaire),
et le temps de service est **constant par client**, indépendant de la demande.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np


class Convention(str, Enum):
    """Convention d'arrondi des distances, et donc des temps de trajet."""

    #: Euclidien en double précision, aucun arrondi par arc (registre SINTEF).
    EXACT = 'exact'
    #: Euclidien tronqué au dixième arc par arc (Solomon 1987, DIMACS, CVRPLIB).
    DIMACS = 'dimacs'


@dataclass(frozen=True)
class Customer:
    """Un nœud de l'instance. Le dépôt est le client de numéro 0."""

    number: int
    x: float
    y: float
    demand: int
    ready: int
    due: int
    service: int


@dataclass(frozen=True)
class SolomonInstance:
    """
    Une instance Solomon telle que publiée.

    :param name: Nom de l'instance (`C101`, `R101`, …)
    :param num_vehicles: Taille de flotte annoncée dans l'en-tête (25 pour les
        instances à 100 clients). Ce n'est pas une contrainte de l'objectif :
        la formulation « distance seule » de CVRPLIB laisse la flotte libre.
    :param capacity: Capacité d'un véhicule, identique pour tous
    :param nodes: Dépôt en position 0, puis les clients dans l'ordre du fichier
    """

    name: str
    num_vehicles: int
    capacity: int
    nodes: tuple[Customer, ...]

    @property
    def depot(self) -> Customer:
        return self.nodes[0]

    @property
    def customers(self) -> tuple[Customer, ...]:
        """Les clients à servir, dépôt exclu."""
        return self.nodes[1:]

    @property
    def num_customers(self) -> int:
        return len(self.nodes) - 1

    @property
    def constant_service_time(self) -> int | None:
        """
        Le temps de service commun à tous les clients, ou None s'il varie.

        Sur les instances à 100 clients il vaut 90 pour la famille C1 et 10 pour
        les familles R1 et RC1. Le dépôt est exclu du constat : son temps de
        service est nul par construction.
        """
        values = {node.service for node in self.customers}
        return values.pop() if len(values) == 1 else None

    def distance(self, i: int, j: int, convention: Convention) -> float:
        """Distance de l'arc i→j sous la convention demandée."""
        a, b = self.nodes[i], self.nodes[j]
        euclid = math.hypot(a.x - b.x, a.y - b.y)
        if convention is Convention.DIMACS:
            return math.floor(euclid * 10) / 10
        return euclid

    def distance_matrix(self, convention: Convention) -> np.ndarray:
        """
        Matrice complète des distances, en flottants.

        La diagonale est nulle dans les deux conventions.
        """
        coords = np.array([(node.x, node.y) for node in self.nodes], dtype=float)
        diff = coords[:, None, :] - coords[None, :, :]
        euclid = np.sqrt((diff ** 2).sum(axis=-1))
        if convention is Convention.DIMACS:
            # `floor` et non `round` : la convention DIMACS tronque, elle
            # n'arrondit pas. Le décalage est d'un dixième au plus par arc, mais
            # il porte sur une centaine d'arcs et déplace le total d'unités
            # entières — assez pour manquer la valeur publiée.
            return np.floor(euclid * 10) / 10
        return euclid


def parse_solomon(path: str | Path) -> SolomonInstance:
    """
    Lit une instance au format Solomon historique (colonnes).

    Le format n'est pas rigoureusement fixe d'un miroir à l'autre : le nombre
    d'espaces varie, l'en-tête de colonnes s'écrit tantôt `SERVICE TIME`
    tantôt `SERVICE   TIME`, et certains fichiers portent une ligne vide de
    séparation. On s'appuie donc sur les mots-clés `VEHICLE` et `CUSTOMER`, puis
    sur les lignes qui comptent exactement sept nombres.

    :param path: Chemin du fichier
    :return: Instance lue
    :raises ValueError: en-tête introuvable ou aucun client
    """
    text = Path(path).read_text(encoding='utf-8')
    lines = text.splitlines()

    name = ''
    for line in lines:
        if line.strip():
            name = line.strip()
            break

    try:
        vehicle_at = next(i for i, line in enumerate(lines) if line.strip().upper().startswith('VEHICLE'))
        customer_at = next(i for i, line in enumerate(lines) if line.strip().upper().startswith('CUSTOMER'))
    except StopIteration:
        raise ValueError(f"{path}: en-tête VEHICLE ou CUSTOMER introuvable") from None

    fleet: tuple[int, int] | None = None
    for line in lines[vehicle_at + 1:customer_at]:
        parts = line.split()
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            fleet = (int(parts[0]), int(parts[1]))
            break
    if fleet is None:
        raise ValueError(f"{path}: ligne NUMBER/CAPACITY introuvable")

    nodes: list[Customer] = []
    for line in lines[customer_at + 1:]:
        parts = line.split()
        if len(parts) != 7:
            continue
        try:
            values = [float(part) for part in parts]
        except ValueError:
            continue  # ligne d'en-tête de colonnes
        nodes.append(Customer(
            number=int(values[0]),
            x=values[1],
            y=values[2],
            demand=int(values[3]),
            ready=int(values[4]),
            due=int(values[5]),
            service=int(values[6]),
        ))

    if not nodes:
        raise ValueError(f"{path}: aucune ligne client")

    return SolomonInstance(
        name=name,
        num_vehicles=fleet[0],
        capacity=fleet[1],
        nodes=tuple(nodes),
    )


def parse_vrplib(path: str | Path) -> SolomonInstance:
    """
    Lit la même instance au format VRPLIB (`.vrp`), tel que distribué par PyVRP.

    Sert de source de contrôle : les fichiers Solomon en colonnes circulent sur
    des miroirs sans autorité, ceux-ci viennent du dépôt qui publie aussi les
    solutions de référence.

    :param path: Chemin du fichier
    :return: Instance lue
    :raises ValueError: section obligatoire absente
    """
    lines = Path(path).read_text(encoding='utf-8').splitlines()

    header: dict[str, str] = {}
    sections: dict[str, list[list[str]]] = {}
    current: str | None = None

    for raw in lines:
        line = raw.strip()
        if not line or line == 'EOF':
            continue
        if line.endswith('_SECTION'):
            current = line
            sections[current] = []
            continue
        if current is None:
            if ':' in line:
                key, _, value = line.partition(':')
                header[key.strip()] = value.strip()
            continue
        if ':' in line and not line[0].isdigit():
            current = None
            key, _, value = line.partition(':')
            header[key.strip()] = value.strip()
            continue
        sections[current].append(line.split())

    for required in ('NODE_COORD_SECTION', 'DEMAND_SECTION', 'TIME_WINDOW_SECTION'):
        if required not in sections:
            raise ValueError(f"{path}: section {required} absente")

    coords = {int(row[0]): (float(row[1]), float(row[2])) for row in sections['NODE_COORD_SECTION']}
    demands = {int(row[0]): int(float(row[1])) for row in sections['DEMAND_SECTION']}
    windows = {int(row[0]): (int(float(row[1])), int(float(row[2])))
               for row in sections['TIME_WINDOW_SECTION']}

    service = int(float(header.get('SERVICE_TIME', 0)))

    nodes: list[Customer] = []
    for number in sorted(coords):
        x, y = coords[number]
        ready, due = windows[number]
        # Numérotation VRPLIB à partir de 1, numérotation Solomon à partir de 0.
        # Le dépôt est le premier nœud dans les deux.
        solomon_number = number - 1
        nodes.append(Customer(
            number=solomon_number,
            x=x,
            y=y,
            demand=demands[number],
            ready=ready,
            due=due,
            service=0 if solomon_number == 0 else service,
        ))

    return SolomonInstance(
        name=header.get('NAME', Path(path).stem),
        num_vehicles=int(float(header.get('VEHICLES', 0))),
        capacity=int(float(header['CAPACITY'])),
        nodes=tuple(nodes),
    )


def check_agreement(left: SolomonInstance, right: SolomonInstance) -> list[str]:
    """
    Compare deux lectures de la même instance, champ à champ.

    :param left: Première lecture
    :param right: Seconde lecture
    :return: Liste des désaccords, vide si les deux instances coïncident
    """
    issues: list[str] = []
    if left.capacity != right.capacity:
        issues.append(f"capacité : {left.capacity} vs {right.capacity}")
    if len(left.nodes) != len(right.nodes):
        issues.append(f"nombre de nœuds : {len(left.nodes)} vs {len(right.nodes)}")
        return issues

    for a, b in zip(left.nodes, right.nodes, strict=True):
        if (a.x, a.y) != (b.x, b.y):
            issues.append(f"nœud {a.number} : position ({a.x}, {a.y}) vs ({b.x}, {b.y})")
        if a.demand != b.demand:
            issues.append(f"nœud {a.number} : demande {a.demand} vs {b.demand}")
        if (a.ready, a.due) != (b.ready, b.due):
            issues.append(
                f"nœud {a.number} : fenêtre [{a.ready}, {a.due}] vs [{b.ready}, {b.due}]"
            )
        if a.service != b.service:
            issues.append(f"nœud {a.number} : service {a.service} vs {b.service}")

    return issues


def load_instance(directory: str | Path, name: str) -> SolomonInstance:
    """
    Charge une instance depuis le cache, en préférant le format VRPLIB.

    Quand les deux formats sont présents, ils sont comparés et un désaccord
    lève : mieux vaut refuser de mesurer que mesurer sur une instance douteuse.

    :param directory: Répertoire de cache des instances
    :param name: Nom de l'instance, par exemple `C101`
    :return: Instance chargée
    :raises FileNotFoundError: aucun fichier pour ce nom
    :raises ValueError: les deux formats ne portent pas la même instance
    """
    directory = Path(directory)
    vrp_path = directory / f"{name}.vrp"
    txt_path = directory / f"{name}.txt"

    vrp = parse_vrplib(vrp_path) if vrp_path.exists() else None
    txt = parse_solomon(txt_path) if txt_path.exists() else None

    if vrp is not None and txt is not None:
        issues = check_agreement(vrp, txt)
        if issues:
            raise ValueError(
                f"{name} : les formats VRPLIB et Solomon divergent — " + " ; ".join(issues[:5])
            )
    chosen = vrp or txt
    if chosen is None:
        raise FileNotFoundError(f"Aucun fichier pour l'instance {name} dans {directory}")
    return chosen
