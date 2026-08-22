"""
Mise en forme d'une solution pour un consommateur web.

Le solveur produit des routes, des heures d'arrivée et des charges indexées par
numéro de nœud : une structure faite pour OR-Tools, pas pour une carte animée.
Ce module la convertit en un document JSON autoportant (arrêts géolocalisés,
segments tracés, indicateurs) que le navigateur peut rejouer sans rien savoir du
modèle de routage.

Ce format existait auparavant dans un script de conversion externe, qui lisait le
`var jsData = {...}` de la page `vrp_visualization.html`. Le format n'était donc
spécifié nulle part dans ce dépôt, et une solution servie en direct par
`optimizer.scenario` n'aurait pas pu garantir la même forme. En le ramenant ici,
gel hors ligne et résolution en direct partagent la **même** fonction, donc la
même forme par construction.

Le document produit :

    {
      "meta": {...},                    # provenance, libre
      "bounds": {minLat, maxLat, minLng, maxLng},
      "depot": {lat, lng},
      "hubs": [{node, lat, lng}],
      "customers": [{node, lat, lng, twEnd}],
      "vehicles": [{id, capacity, served, start, end, stops[], legs[]}],
      "horizon": int,                   # fin de la dernière tournée, en secondes
      "serviceTimePerUnit": int,
      "stats": {...},
      "reloadEvents": [{vehicle, at, from, to}],
      "_build": {...}                   # traçabilité de la simplification
    }

Invariants garantis, et vérifiés par `tests/unit/test_tour_format.py` :

* `vehicles[i]["id"] == i` ;
* `len(legs) == len(stops) - 1` ;
* `stops[]["arrive"]` est croissant ;
* `legs[]["pts"]` n'est jamais vide ;
* `horizon == max(vehicle["end"])` et `horizon > 0` ;
* tout arrêt `kind == "customer"` porte un nœud présent dans `customers` ;
* `bounds` n'est pas dégénéré (min != max sur les deux axes).
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Sequence

# Les coordonnées sont stockées avec 5 décimales, soit ~1 m à cette latitude,
# largement sous les ~15 m que couvre un pixel quand toute la journée est à
# l'écran.
COORD_PRECISION = 5

# Tolérance de Douglas-Peucker pour les tracés routiers, en mètres. Également
# sous-pixellaire au niveau de zoom de la démonstration, et elle retire environ
# deux tiers des sommets.
SIMPLIFY_TOLERANCE_M = 4.0

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(a: Sequence[float], b: Sequence[float]) -> float:
    """
    Distance orthodromique entre deux couples (lat, lon), en mètres.

    :param a: Point de départ (latitude, longitude)
    :param b: Point d'arrivée (latitude, longitude)
    :return: Distance en mètres
    """
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _perpendicular_distance_m(
    pt: Sequence[float], start: Sequence[float], end: Sequence[float]
) -> float:
    """
    Distance d'un point au segment start-end, en mètres.

    Les coordonnées sont d'abord projetées sur un plan métrique local. Sans la
    correction en cos(latitude) sur la longitude, les distances est-ouest seraient
    surestimées d'environ 34 % à la latitude de Paris : de quoi conserver des
    sommets qui devraient disparaître, et en supprimer qui comptent.

    :param pt: Point à mesurer (latitude, longitude)
    :param start: Début du segment
    :param end: Fin du segment
    :return: Distance en mètres
    """
    lat0 = math.radians(start[0])
    mx = EARTH_RADIUS_M * math.cos(lat0)
    my = EARTH_RADIUS_M

    px = math.radians(pt[1]) * mx
    py = math.radians(pt[0]) * my
    ax = math.radians(start[1]) * mx
    ay = math.radians(start[0]) * my
    bx = math.radians(end[1]) * mx
    by = math.radians(end[0]) * my

    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(points: List[List[float]], tolerance_m: float) -> List[List[float]]:
    """
    Simplification de Douglas-Peucker, en version itérative.

    Itérative et non récursive : certains segments OSRM comptent quelques
    centaines de sommets, et un ordre de découpe défavorable imbriquerait
    profondément les appels.

    :param points: Suite de [latitude, longitude]
    :param tolerance_m: Écart maximal toléré, en mètres
    :return: Sous-suite des points conservés (extrémités toujours incluses)
    """
    if len(points) < 3:
        return points

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        worst_index, worst_dist = -1, 0.0
        for i in range(first + 1, last):
            d = _perpendicular_distance_m(
                (points[i][0], points[i][1]),
                (points[first][0], points[first][1]),
                (points[last][0], points[last][1]),
            )
            if d > worst_dist:
                worst_index, worst_dist = i, d
        if worst_dist > tolerance_m:
            keep[worst_index] = True
            stack.append((first, worst_index))
            stack.append((worst_index, last))

    return [p for p, k in zip(points, keep) if k]


def round_point(p: Sequence[float]) -> List[float]:
    """Arrondit un point à la précision de stockage."""
    return [round(p[0], COORD_PRECISION), round(p[1], COORD_PRECISION)]


def polyline_length_m(points: Sequence[Sequence[float]]) -> float:
    """Longueur cumulée d'une polyligne, en mètres."""
    return sum(
        haversine_m(points[i - 1], points[i])
        for i in range(1, len(points))
    )


def classify(
    node: int,
    demand: float,
    num_customers: int,
    hub_nodes: Iterable[int] = (),
    reload_nodes: Iterable[int] = (),
) -> str:
    """
    Nature d'un nœud, du point de vue de l'affichage.

    Quatre valeurs seulement : `depot`, `customer`, `reload`, `hub`. Les nœuds de
    dépôt et de retrait d'un hub sont rangés en `hub` : ils se trouvent à la
    position du hub, et le consommateur n'a pas à connaître la mécanique de
    transfert.

    Les ensembles `hub_nodes` et `reload_nodes` sont facultatifs. Fournis, ils
    tranchent sans ambiguïté ; absents, on retombe sur le signe de la demande :
    négative pour un rechargement, nulle ou positive pour un hub. Ce repli est
    exact pour un scénario sans transfert, où les seuls nœuds à demande négative
    sont les points de rechargement.

    :param node: Numéro de nœud
    :param demand: Demande portée par le nœud
    :param num_customers: Nombre de clients
    :param hub_nodes: Nœuds de hub connus (hub, dépôt, retrait)
    :param reload_nodes: Nœuds de rechargement au dépôt connus
    :return: `depot`, `customer`, `reload` ou `hub`
    """
    if node == 0:
        return "depot"
    if 1 <= node <= num_customers:
        return "customer"
    if node in hub_nodes:
        return "hub"
    if node in reload_nodes:
        return "reload"
    return "reload" if demand < 0 else "hub"


def _real_vehicle_count(src: Dict[str, Any]) -> int:
    """
    Nombre de véhicules à afficher.

    Les véhicules fictifs, qui matérialisent les transferts en hub, ne roulent
    pas et ne doivent pas être dessinés. Ils suivent toujours les véhicules
    réels. `num_real_vehicles` le dit explicitement lorsqu'il est présent ; sinon
    on retombe sur le seul signal disponible dans la charge utile historique : la
    capacité nulle qui marque le début des véhicules fictifs. Ce repli confondrait
    un véhicule réel de capacité 0 avec un véhicule fictif, d'où la préférence
    donnée à la clé explicite.
    """
    explicit = src.get("num_real_vehicles")
    if explicit is not None:
        return int(explicit)
    capacities = src["vehicle_capacities"]
    return next((i for i, c in enumerate(capacities) if c == 0), len(capacities))


def build_tour(src: Dict[str, Any], meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Convertit une solution en document de tournée prêt à être rejoué.

    :param src: Charge utile de la solution, telle que la produisent
        `optimizer.scenario` et la page `vrp_visualization.html`. Clés lues :

        * `locations`, `demands`, `time_windows`, `num_customers`
        * `time_per_demand_unit` : temps de service par unité de demande
        * `vehicle_capacities` : capacités, véhicules fictifs compris
        * `road_legs` : géométrie routière par segment, clé `"depart-arrivee"`
          (facultatif : sans elle, les segments sont des droites)
        * `results.per_livreur.{routes, estimated_times, cumulative_loads, slacks}`
        * `results.indicators.{total_time_all_vehicles, total_tardiness_minutes,
          activated_hubs}`
        * facultatifs : `num_real_vehicles`, `num_hubs`, `hub_deposits`,
          `hub_pickups`, `unload_depots`
    :param meta: Bloc de provenance recopié tel quel dans le document. Purement
        descriptif : aucun consommateur ne doit en dépendre pour fonctionner.
    :return: Document de tournée (voir l'en-tête du module)
    """
    locations = src["locations"]
    demands = src["demands"]
    time_windows = src["time_windows"]
    num_customers = src["num_customers"]
    service_per_unit = src["time_per_demand_unit"]
    road_legs = src.get("road_legs", {})

    per = src["results"]["per_livreur"]
    routes = per["routes"]
    arrivals = per["estimated_times"]
    loads = per["cumulative_loads"]
    slacks = per["slacks"]

    capacities = src["vehicle_capacities"]
    num_real = _real_vehicle_count(src)

    # Nœuds de hub : les hubs eux-mêmes, plus leurs points de dépôt et de retrait
    # lorsque les transferts sont actifs.
    num_hubs = src.get("num_hubs", 0)
    base_hub_nodes = list(range(1 + num_customers, 1 + num_customers + num_hubs))
    if not base_hub_nodes:
        # Scénario sans transfert : les hubs restent des positions traversables,
        # mais `num_hubs` vaut 0 dans les données du solveur. On les retrouve par
        # leur demande nulle au-delà des clients.
        base_hub_nodes = [
            n
            for n in range(1 + num_customers, len(locations))
            if classify(n, demands[n], num_customers) == "hub"
        ]
    hub_nodes = set(base_hub_nodes) | set(src.get("hub_deposits", [])) | set(src.get("hub_pickups", []))
    reload_nodes = set(src.get("unload_depots", []))

    vehicles: List[Dict[str, Any]] = []
    reload_events: List[Dict[str, Any]] = []
    hub_flybys: List[Dict[str, Any]] = []
    total_road_m = 0.0
    kept_points = 0
    source_points = 0

    for v in range(num_real):
        route, times, load_trace, slack = routes[v], arrivals[v], loads[v], slacks[v]
        capacity = capacities[v]

        stops: List[Dict[str, Any]] = []
        legs: List[Dict[str, Any]] = []

        for i, node in enumerate(route):
            kind = classify(node, demands[node], num_customers, hub_nodes, reload_nodes)
            service = abs(demands[node]) * service_per_unit
            # Le dernier arrêt n'a pas d'arc sortant, donc pas d'attente associée.
            wait = slack[i] if i < len(slack) else 0
            arrive = times[i]
            stop = {
                "node": node,
                "kind": kind,
                "lat": round(locations[node][0], COORD_PRECISION),
                "lng": round(locations[node][1], COORD_PRECISION),
                "arrive": arrive,
                "service": service,
                "depart": arrive + service + wait,
                # Charge transportée en repartant de cet arrêt. Le solveur intègre
                # déjà les rechargements dans la trace : un nœud de rechargement
                # affiche donc simplement la valeur reconstituée.
                "load": load_trace[i],
                "twEnd": time_windows[node][1],
            }
            stops.append(stop)

            if kind == "reload" and i > 0:
                reload_events.append(
                    {"vehicle": v, "at": arrive, "from": load_trace[i - 1], "to": load_trace[i]}
                )
            elif kind == "hub":
                hub_flybys.append({"vehicle": v, "at": arrive, "node": node})

        for i in range(len(route) - 1):
            key = f"{route[i]}-{route[i + 1]}"
            raw_points = road_legs.get(key)
            if raw_points:
                source_points += len(raw_points)
                pts = [round_point(p) for p in simplify(raw_points, SIMPLIFY_TOLERANCE_M)]
            else:
                # Aucune géométrie routière pour ce couple : on retombe sur le
                # segment droit, pour que le véhicule se déplace quand même, et on
                # le signale.
                pts = [
                    [stops[i]["lat"], stops[i]["lng"]],
                    [stops[i + 1]["lat"], stops[i + 1]["lng"]],
                ]
            kept_points += len(pts)
            meters = polyline_length_m(pts)
            total_road_m += meters
            legs.append(
                {
                    "depart": stops[i]["depart"],
                    "arrive": stops[i + 1]["arrive"],
                    "meters": round(meters),
                    "road": bool(raw_points),
                    "pts": pts,
                }
            )

        served = sum(1 for s in stops if s["kind"] == "customer")
        vehicles.append(
            {
                "id": v,
                "capacity": capacity,
                "served": served,
                "start": stops[0]["arrive"],
                "end": stops[-1]["arrive"],
                "stops": stops,
                "legs": legs,
            }
        )

    customers = [
        {
            "node": n,
            "lat": round(locations[n][0], COORD_PRECISION),
            "lng": round(locations[n][1], COORD_PRECISION),
            "twEnd": time_windows[n][1],
        }
        for n in range(1, num_customers + 1)
    ]
    hubs = [
        {
            "node": n,
            "lat": round(locations[n][0], COORD_PRECISION),
            "lng": round(locations[n][1], COORD_PRECISION),
        }
        for n in base_hub_nodes
    ]

    lats = [p[0] for p in locations]
    lngs = [p[1] for p in locations]

    horizon = max(v["end"] for v in vehicles)
    indicators = src["results"]["indicators"]

    # Tous les clients effectivement atteints, recoupés avec la liste des clients :
    # abandonner un client est une issue légitime du solveur, et la démonstration
    # ne doit pas afficher un taux de service complet en silence.
    visited_customers = {s["node"] for veh in vehicles for s in veh["stops"] if s["kind"] == "customer"}

    return {
        "meta": dict(meta or {}),
        "bounds": {
            "minLat": round(min(lats), COORD_PRECISION),
            "maxLat": round(max(lats), COORD_PRECISION),
            "minLng": round(min(lngs), COORD_PRECISION),
            "maxLng": round(max(lngs), COORD_PRECISION),
        },
        "depot": {
            "lat": round(locations[0][0], COORD_PRECISION),
            "lng": round(locations[0][1], COORD_PRECISION),
        },
        "hubs": hubs,
        "customers": customers,
        "vehicles": vehicles,
        "horizon": horizon,
        "serviceTimePerUnit": service_per_unit,
        "stats": {
            "customers": num_customers,
            "customersServed": len(visited_customers),
            "vehicles": len(vehicles),
            "capacity": capacities[0] if capacities else 0,
            "roadKm": round(total_road_m / 1000, 1),
            "horizon": horizon,
            "cumulativeDriveTime": indicators["total_time_all_vehicles"],
            "tardinessMinutes": indicators["total_tardiness_minutes"],
            "hubsAvailable": len(hubs),
            "hubsActivated": indicators["activated_hubs"],
            "reloads": len(reload_events),
            "hubFlybys": len(hub_flybys),
            # Dit si les fenêtres horaires contraignent réellement le problème.
            # Étalées sur la journée entière, elles ne mordent jamais : autant
            # l'annoncer plutôt que de laisser croire le contraire.
            "timeWindowsBinding": any(c["twEnd"] < 86400 for c in customers),
        },
        "reloadEvents": sorted(reload_events, key=lambda e: e["at"]),
        "_build": {
            "polylinePoints": kept_points,
            "sourcePolylinePoints": source_points,
            "simplifyToleranceM": SIMPLIFY_TOLERANCE_M,
            "coordPrecision": COORD_PRECISION,
        },
    }
