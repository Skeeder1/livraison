"""
Lecture des solutions de référence publiées, et contrôle des conventions.

Une valeur de référence recopiée d'une page web ne prouve rien : elle peut être
mal lue, mal attribuée, ou relever d'une convention d'arrondi différente de
celle qu'on croit appliquer. Les deux registres publient aussi les **tournées**,
et c'est ce qui permet de fermer la boucle : on relit les tournées, on
recalcule la distance avec notre propre arithmétique, et on vérifie qu'on
retombe sur le nombre publié.

Si ce contrôle passe, alors trois choses sont établies d'un coup : l'instance
lue est la bonne, la convention déclarée est la bonne, et le vérificateur
calcule juste. S'il échoue, aucun écart mesuré plus loin ne veut dire quoi que
ce soit.

Deux formats de solution :

* PyVRP / CVRPLIB (`C101.sol`) : ``Route #1: 5 3 7 …`` puis ``Cost 827.3`` ;
* SINTEF (`C101.sintef.sol`) : un en-tête `Instance name` / `Authors` / `Date`
  / `Reference`, la ligne `Solution`, puis ``Route 1 : 5 3 7 …`` sans coût.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_PYVRP_ROUTE = re.compile(r'^\s*Route\s*#(\d+)\s*:\s*(.*)$', re.IGNORECASE)
_SINTEF_ROUTE = re.compile(r'^\s*Route\s+(\d+)\s*:\s*(.*)$', re.IGNORECASE)
_COST = re.compile(r'^\s*Cost\s+([0-9.]+)\s*$', re.IGNORECASE)


@dataclass(frozen=True)
class ReferenceSolution:
    """Une solution publiée : ses tournées, et le coût annoncé s'il en porte un."""

    routes: tuple[tuple[int, ...], ...]
    reported_cost: float | None

    @property
    def vehicles(self) -> int:
        return len(self.routes)


def parse_reference(path: str | Path) -> ReferenceSolution:
    """
    Lit une solution de référence, dans l'un ou l'autre des deux formats.

    :param path: Chemin du fichier
    :return: Les tournées et le coût annoncé
    :raises ValueError: aucune tournée reconnue
    """
    routes: list[tuple[int, ...]] = []
    cost: float | None = None

    for line in Path(path).read_text(encoding='utf-8').splitlines():
        match = _PYVRP_ROUTE.match(line) or _SINTEF_ROUTE.match(line)
        if match:
            numbers = tuple(int(token) for token in match.group(2).split() if token.lstrip('-').isdigit())
            if numbers:
                routes.append(numbers)
            continue
        cost_match = _COST.match(line)
        if cost_match:
            cost = float(cost_match.group(1))

    if not routes:
        raise ValueError(f"{path}: aucune tournée reconnue")

    return ReferenceSolution(routes=tuple(routes), reported_cost=cost)
