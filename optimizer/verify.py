"""Vérification indépendante d'un document de tournée.

Ce module ne fait confiance à rien de ce que la tournée affirme sur elle-même :
il recalcule chaque grandeur à partir des positions et des horaires publiés, et
compare. C'est délibéré. Les statistiques d'une solution sont produites par le
même code que la solution ; s'il se trompe, il se trompe deux fois de la même
manière et rien ne le signale.

Ce contrôle a déjà servi. Il a montré que `hubsActivated` comptait les simples
passages devant un hub comme des transferts de colis : la tournée annonçait un
rendez-vous là où aucun nœud de dépôt ni de retrait n'était desservi.

Utilisation :

    cvrptw-verify tour.json
    cvrptw-verify tour.json --data data/     # recoupe avec l'instance résolue
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TOLERANCE_METRES = 2.0
TOLERANCE_SECONDES = 1


@dataclass
class Rapport:
    """Résultat d'une vérification : ce qui tient, et ce qui ne tient pas."""

    reussites: list[str] = field(default_factory=list)
    echecs: list[tuple[str, str]] = field(default_factory=list)

    def verifier(self, condition: bool, intitule: str, detail: str = "") -> bool:
        if condition:
            self.reussites.append(intitule)
        else:
            self.echecs.append((intitule, detail))
        return condition

    @property
    def valide(self) -> bool:
        return not self.echecs

    def afficher(self) -> None:
        total = len(self.reussites) + len(self.echecs)
        print(f"\n  {len(self.reussites)}/{total} vérifications passées\n")
        for intitule in self.reussites:
            print(f"  ok     {intitule}")
        for intitule, detail in self.echecs:
            print(f"  ÉCHEC  {intitule}")
            if detail:
                print(f"         {detail}")


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance géodésique en mètres entre deux couples (latitude, longitude)."""
    rayon = 6371000.0
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat = lat2 - lat1
    dlon = math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * rayon * math.asin(math.sqrt(h))


def verifier_tournee(tour: dict[str, Any], instance: dict[str, Any] | None = None) -> Rapport:
    """Contrôle la cohérence interne d'une tournée, et sa fidélité à l'instance.

    :param tour: Document de tournée tel que produit par `optimizer.tour_format`
    :param instance: Facultatif — données lues depuis le répertoire de travail,
        pour recouper positions, capacités et demandes avec ce qui a été résolu
    :return: Le rapport, dont `valide` dit si tout tient
    """
    r = Rapport()
    vehicules = tour["vehicles"]
    stats = tour["stats"]
    service_unitaire = tour["serviceTimePerUnit"]

    r.verifier(bool(vehicules), "la tournée contient au moins un véhicule")

    # ── Structure ──────────────────────────────────────────────────
    r.verifier(all(len(v["legs"]) == len(v["stops"]) - 1 for v in vehicules),
               "un segment entre chaque paire d'arrêts consécutifs",
               str([(v["id"], len(v["stops"]), len(v["legs"])) for v in vehicules]))
    r.verifier([v["id"] for v in vehicules] == list(range(len(vehicules))),
               "les identifiants de véhicule suivent leur position")

    # ── Couverture des clients ─────────────────────────────────────
    vus: dict[int, int] = {}
    for v in vehicules:
        for arret in v["stops"]:
            if arret["kind"] == "customer":
                vus[arret["node"]] = vus.get(arret["node"], 0) + 1
    doublons = [n for n, c in vus.items() if c > 1]
    r.verifier(not doublons, "aucun client n'est servi deux fois", f"nœuds {doublons[:5]}")
    r.verifier(len(vus) == stats["customersServed"],
               "`customersServed` égale le nombre de clients réellement servis",
               f"comptés {len(vus)}, annoncés {stats['customersServed']}")
    r.verifier(stats["customersServed"] <= stats["customers"],
               "on ne sert pas plus de clients qu'il n'en existe")

    # ── Charges ────────────────────────────────────────────────────
    depassements, negatives = [], []
    for v in vehicules:
        for arret in v["stops"]:
            if arret["load"] > v["capacity"]:
                depassements.append((v["id"], arret["node"], arret["load"], v["capacity"]))
            if arret["load"] < 0:
                negatives.append((v["id"], arret["node"], arret["load"]))
    r.verifier(not depassements, "la charge ne dépasse jamais la capacité du véhicule",
               f"{depassements[:3]}")
    r.verifier(not negatives, "la charge n'est jamais négative", f"{negatives[:3]}")

    # ── Horaires ───────────────────────────────────────────────────
    service_incoherent, depart_avant_service, arrivees_desordonnees = [], [], []
    for v in vehicules:
        arrets = v["stops"]
        for arret in arrets:
            if arret["depart"] < arret["arrive"] + arret["service"] - TOLERANCE_SECONDES:
                depart_avant_service.append(
                    (v["id"], arret["node"], arret["arrive"], arret["service"], arret["depart"]))
            if arret["kind"] == "customer" and arret["service"] % service_unitaire != 0:
                service_incoherent.append((v["id"], arret["node"], arret["service"]))
        for i in range(len(arrets) - 1):
            if arrets[i + 1]["arrive"] < arrets[i]["arrive"]:
                arrivees_desordonnees.append((v["id"], i))
    r.verifier(not depart_avant_service, "un véhicule ne repart jamais avant d'avoir servi",
               f"{depart_avant_service[:3]}")
    r.verifier(not service_incoherent,
               "le temps de service est un multiple du temps unitaire publié",
               f"{service_incoherent[:3]}")
    r.verifier(not arrivees_desordonnees, "les arrivées croissent le long de chaque tournée",
               f"{arrivees_desordonnees[:3]}")

    # Un segment ne peut pas être parcouru avant d'avoir été entamé.
    segments_impossibles = [
        (v["id"], i) for v in vehicules for i, seg in enumerate(v["legs"])
        if seg["arrive"] < seg["depart"]
    ]
    r.verifier(not segments_impossibles, "chaque segment arrive après être parti",
               f"{segments_impossibles[:3]}")

    # ── Fenêtres de temps ──────────────────────────────────────────
    hors_fenetre = [
        (arret["node"], arret["arrive"], arret["twEnd"])
        for v in vehicules for arret in v["stops"]
        if arret["kind"] == "customer" and arret.get("twEnd") is not None
        and arret["arrive"] > arret["twEnd"]
    ]
    r.verifier(bool(hors_fenetre) == bool(stats["tardinessMinutes"]),
               "le retard annoncé correspond aux arrivées hors fenêtre",
               f"{len(hors_fenetre)} arrivée(s) en retard, `tardinessMinutes` = "
               f"{stats['tardinessMinutes']}")

    # ── Dépôt ──────────────────────────────────────────────────────
    extremites = [(v["stops"][0]["kind"], v["stops"][-1]["kind"]) for v in vehicules if v["stops"]]
    r.verifier(all(d == "depot" and f == "depot" for d, f in extremites),
               "chaque tournée part du dépôt et y revient", f"{extremites}")

    # ── Horizon ────────────────────────────────────────────────────
    if any(v["stops"] for v in vehicules):
        derniere = max(v["stops"][-1]["arrive"] for v in vehicules if v["stops"])
        r.verifier(derniere == tour["horizon"], "`horizon` égale la dernière arrivée",
                   f"dernière arrivée {derniere}, horizon annoncé {tour['horizon']}")

    # ── Géométrie ──────────────────────────────────────────────────
    longueurs_fausses, total_m = [], 0.0
    for v in vehicules:
        for i, seg in enumerate(v["legs"]):
            longueur = sum(haversine_m(seg["pts"][j], seg["pts"][j + 1])
                           for j in range(len(seg["pts"]) - 1))
            total_m += longueur
            if abs(seg["meters"] - longueur) > TOLERANCE_METRES:
                longueurs_fausses.append((v["id"], i, seg["meters"], round(longueur)))
    r.verifier(not longueurs_fausses, "la longueur annoncée de chaque segment est la vraie",
               f"{longueurs_fausses[:3]}")
    r.verifier(abs(total_m / 1000 - stats["roadKm"]) < 0.15,
               "`roadKm` est la somme des longueurs de segments",
               f"recalculé {total_m / 1000:.1f} km, annoncé {stats['roadKm']} km")

    # Les extrémités d'un segment sont les arrêts qu'il relie.
    extremites_fausses = [
        (v["id"], i) for v in vehicules for i, seg in enumerate(v["legs"])
        if haversine_m(seg["pts"][0], (v["stops"][i]["lat"], v["stops"][i]["lng"])) > TOLERANCE_METRES
        or haversine_m(seg["pts"][-1], (v["stops"][i + 1]["lat"], v["stops"][i + 1]["lng"])) > TOLERANCE_METRES
    ]
    r.verifier(not extremites_fausses, "chaque segment relie bien les deux arrêts qu'il borne",
               f"{extremites_fausses[:3]}")

    # ── Rendez-vous entre coursiers ────────────────────────────────
    _verifier_transferts(tour, r)

    # ── Recoupement avec l'instance résolue ────────────────────────
    if instance is not None:
        _verifier_contre_instance(tour, instance, r)

    return r


def _verifier_transferts(tour: dict[str, Any], r: Rapport) -> None:
    """Contrôle les échanges de colis, s'il y en a.

    Un transfert n'existe que si un colis change effectivement de mains : les
    deux nœuds de la paire desservis, par deux coursiers différents, le dépôt
    avant le retrait. Un passage devant le hub n'en est pas un.
    """
    hubs_declares = {h["node"] for h in tour.get("hubs", [])}
    arrets_hub: dict[int, list[tuple[int, int]]] = {}
    for v in tour["vehicles"]:
        for arret in v["stops"]:
            if arret["kind"] == "hub":
                arrets_hub.setdefault(arret["node"], []).append((v["id"], arret["arrive"]))

    survols = {n: v for n, v in arrets_hub.items() if n in hubs_declares}
    paires = {n: v for n, v in arrets_hub.items() if n not in hubs_declares}

    r.verifier(len(survols) == 0 or tour["stats"]["hubFlybys"] >= len(survols),
               "les passages devant un hub sont comptés comme survols, pas comme transferts",
               f"{len(survols)} nœud(s) de hub visité(s), `hubFlybys` = {tour['stats']['hubFlybys']}")

    # Les nœuds de dépôt et de retrait sont créés par paires consécutives.
    noeuds = sorted(paires)
    apparies = {n: n + 1 for n in noeuds if n % 2 == min(noeuds, default=0) % 2 and n + 1 in paires}
    transferts = 0
    for depot_n, retrait_n in apparies.items():
        depose, collecte = paires[depot_n][0], paires[retrait_n][0]
        r.verifier(depose[0] != collecte[0],
                   f"transfert {depot_n}→{retrait_n} : deux coursiers distincts",
                   f"véhicule {depose[0]} des deux côtés")
        r.verifier(depose[1] <= collecte[1],
                   f"transfert {depot_n}→{retrait_n} : le dépôt précède le retrait",
                   f"dépôt à {depose[1]} s, retrait à {collecte[1]} s")
        transferts += 1

    orphelins = [n for n in noeuds if n not in apparies and n - 1 not in apparies]
    r.verifier(not orphelins,
               "aucun nœud de transfert orphelin : les colis déposés sont collectés",
               f"nœuds {orphelins}")
    r.verifier(transferts == tour["stats"]["hubsActivated"],
               "`hubsActivated` égale le nombre de transferts réellement effectués",
               f"comptés {transferts}, annoncés {tour['stats']['hubsActivated']}")


def _verifier_contre_instance(tour: dict[str, Any], instance: dict[str, Any], r: Rapport) -> None:
    """Recoupe la tournée avec les données que le solveur a réellement lues."""
    colis = instance["colis"]
    livreurs = instance["livreurs"]

    r.verifier(len(tour["vehicles"]) == len(livreurs),
               "le nombre de véhicules est celui de l'instance",
               f"{len(tour['vehicles'])} contre {len(livreurs)}")
    capacites_ok = all(v["capacity"] == int(livreurs[v["id"]]["capacity"])
                       for v in tour["vehicles"] if v["id"] < len(livreurs))
    r.verifier(capacites_ok, "les capacités sont celles de l'instance")

    positions = {i + 1: tuple(c["position"]) for i, c in enumerate(colis)}
    ecarts = []
    for v in tour["vehicles"]:
        for arret in v["stops"]:
            attendue = positions.get(arret["node"])
            if attendue is not None and arret["kind"] == "customer":
                d = haversine_m((arret["lat"], arret["lng"]), attendue)
                if d > TOLERANCE_METRES:
                    ecarts.append((arret["node"], round(d)))
    r.verifier(not ecarts, "chaque arrêt client est à la position de l'instance",
               f"écarts en mètres : {ecarts[:5]}")

    servis = {a["node"] for v in tour["vehicles"] for a in v["stops"] if a["kind"] == "customer"}
    r.verifier(servis <= set(positions),
               "aucun client servi n'est absent de l'instance",
               f"inconnus : {sorted(servis - set(positions))[:5]}")


def charger_instance(repertoire: Path) -> dict[str, Any]:
    """Lit les fichiers d'instance produits par `create_toy_data`."""
    return {
        "colis": json.loads((repertoire / "colis.json").read_text(encoding="utf-8")),
        "livreurs": json.loads((repertoire / "livreurs.json").read_text(encoding="utf-8")),
        "hubs": json.loads((repertoire / "hubs.json").read_text(encoding="utf-8")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cvrptw-verify",
        description="Vérifie qu'un document de tournée décrit une solution cohérente.",
    )
    parser.add_argument("tour", type=Path, help="document de tournée à vérifier")
    parser.add_argument("--data", type=Path, default=None,
                        help="répertoire d'instance, pour recouper avec ce qui a été résolu")
    parser.add_argument("--quiet", action="store_true", help="n'afficher que les échecs")
    args = parser.parse_args()

    tour = json.loads(args.tour.read_text(encoding="utf-8"))
    instance = charger_instance(args.data) if args.data else None

    rapport = verifier_tournee(tour, instance)
    if args.quiet:
        for intitule, detail in rapport.echecs:
            print(f"ÉCHEC  {intitule}\n       {detail}")
    else:
        rapport.afficher()

    if rapport.valide:
        if not args.quiet:
            print("\n  La tournée est cohérente.")
        return 0
    print(f"\n  {len(rapport.echecs)} incohérence(s).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
