"""Audit de qualité géométrique d'une tournée.

`optimizer.verify` répond à « la solution est-elle valide ? ». Ce module répond
à une question différente et plus difficile : « a-t-elle l'air intelligente ? »

Une tournée peut satisfaire toutes les contraintes et rester manifestement
mauvaise à l'œil : elle se recoupe, elle fait des allers-retours, un client isolé
provoque un détour absurde, un coursier attend une heure pendant qu'un autre
enchaîne. Aucun de ces défauts n'apparaît dans `roadKm` ou `horizon`, et c'est
précisément ce qui les rend difficiles à percevoir : les indicateurs restent
plausibles.

Les contrôles reposent sur des propriétés démontrables plutôt que sur une
impression :

* **Croisement interne.** Une tournée euclidienne optimale ne se recoupe jamais
  (Flood, *The Traveling-Salesman Problem*, Operations Research, 1956). Si deux
  segments d'un même véhicule se croisent, inverser la portion comprise entre eux
  raccourcit strictement le trajet — c'est le mouvement 2-opt. Un croisement est
  donc une preuve de sous-optimalité, pas une opinion.

  **La preuve tient à la métrique**, et il faut le savoir avant de s'y fier : elle
  repose sur l'inégalité triangulaire stricte le long de segments droits. Elle vaut
  tant que le solveur minimise des distances euclidiennes, ce qui est le cas
  aujourd'hui. Le jour où la matrice viendra du réseau routier, deux tronçons
  pourront se croiser à l'écran sans que la tournée soit améliorable : le
  croisement redeviendra un indice, comme celui entre deux véhicules.

* **Croisement entre tournées.** Contrairement au cas précédent, rien n'interdit à
  deux véhicules de se croiser dans une solution optimale : la capacité et les
  fenêtres de temps peuvent l'imposer. C'est un indice de découpage discutable,
  jamais une preuve.
* **2-opt et relocalisation résiduels.** On énumère tous les mouvements et on
  compte ceux qui raccourcissent encore. Une recherche convergée n'en laisse
  presque aucun ; il en reste beaucoup lorsque le budget a manqué.
* **Facteur de détour.** Pour chaque arrêt, le surcoût de son insertion rapporté
  au trajet direct entre ses voisins. Les valeurs extrêmes désignent les clients
  qui coûtent cher.
* **Attente.** Du temps passé à l'arrêt sans servir, invisible dans la distance.
* **Déséquilibre.** L'écart entre le coursier le plus chargé et le moins chargé.

Utilisation :

    cvrptw-audit tour.json
    cvrptw-audit tour.json --carte      # rendu ASCII pour l'œil
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from optimizer.verify import haversine_m

Point = tuple[float, float]

# En degrés, les produits vectoriels utiles valent ~1e-4 ; en deçà, on est sur
# un alignement, pas sur un croisement.
EPSILON_ORIENTATION = 1e-12


# ── Géométrie ──────────────────────────────────────────────────────

def _orientation(a: Point, b: Point, c: Point) -> float:
    """Produit vectoriel : signe = sens de rotation de a→b→c."""
    return (b[1] - a[1]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[1] - a[1])


def segments_se_croisent(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """Vrai si [p1p2] et [p3p4] se croisent proprement.

    On exige un croisement franc : les extrémités partagées et les contacts
    tangents ne comptent pas, sans quoi deux segments consécutifs d'une même
    tournée seraient signalés à chaque arrêt.
    """
    d1 = _orientation(p3, p4, p1)
    d2 = _orientation(p3, p4, p2)
    d3 = _orientation(p1, p2, p3)
    d4 = _orientation(p1, p2, p4)
    # Une orientation nulle signale un point aligné : extrémité partagée ou
    # contact tangent. Les compter ferait détecter un croisement à chaque arrêt,
    # deux segments consécutifs partageant toujours un point. On exige donc les
    # quatre orientations strictement non nulles avant de conclure.
    if min(abs(d1), abs(d2), abs(d3), abs(d4)) < EPSILON_ORIENTATION:
        return False
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _longueur(points: list[Point]) -> float:
    return sum(haversine_m(points[i], points[i + 1]) for i in range(len(points) - 1))


def croisements_internes(points: list[Point]) -> list[tuple[int, int]]:
    """Paires de segments non adjacents qui se croisent dans une même tournée."""
    croisements = []
    for i in range(len(points) - 1):
        for j in range(i + 2, len(points) - 1):
            # Les segments adjacents partagent un point : jamais un croisement franc.
            if i == 0 and j == len(points) - 2:
                continue
            if segments_se_croisent(points[i], points[i + 1], points[j], points[j + 1]):
                croisements.append((i, j))
    return croisements


def deux_opt_restants(points: list[Point]) -> tuple[int, float]:
    """Compte les inversions 2-opt qui raccourciraient encore la tournée.

    Le dépôt de départ et d'arrivée reste fixe ; seul l'ordre intermédiaire
    bouge. Retourne le nombre de mouvements améliorants et le meilleur gain, en
    mètres.
    """
    n = len(points)
    if n < 5:
        return 0, 0.0
    base = _longueur(points)
    ameliorants, meilleur = 0, 0.0
    for i in range(1, n - 2):
        for j in range(i + 1, n - 1):
            candidat = points[:i] + points[i:j + 1][::-1] + points[j + 1:]
            gain = base - _longueur(candidat)
            if gain > 1.0:  # un mètre, pour ignorer le bruit de l'arithmétique
                ameliorants += 1
                meilleur = max(meilleur, gain)
    return ameliorants, meilleur


def relocalisations_restantes(points: list[Point]) -> tuple[int, float]:
    """Compte les déplacements d'un arrêt unique qui raccourciraient la tournée."""
    n = len(points)
    if n < 5:
        return 0, 0.0
    base = _longueur(points)
    ameliorants, meilleur = 0, 0.0
    for i in range(1, n - 1):
        reste = points[:i] + points[i + 1:]
        for j in range(1, len(reste)):
            if j == i:
                continue
            candidat = reste[:j] + [points[i]] + reste[j:]
            gain = base - _longueur(candidat)
            if gain > 1.0:
                ameliorants += 1
                meilleur = max(meilleur, gain)
    return ameliorants, meilleur


def facteurs_de_detour(points: list[Point]) -> list[float]:
    """Surcoût d'insertion de chaque arrêt, rapporté au trajet direct.

    Un facteur de 1 signifie que l'arrêt est sur le chemin ; 3 signifie qu'il
    triple la distance entre ses deux voisins.
    """
    facteurs = []
    for i in range(1, len(points) - 1):
        direct = haversine_m(points[i - 1], points[i + 1])
        par_arret = haversine_m(points[i - 1], points[i]) + haversine_m(points[i], points[i + 1])
        facteurs.append(par_arret / direct if direct > 1 else float("inf"))
    return facteurs


# ── Audit ──────────────────────────────────────────────────────────

def auditer(tour: dict[str, Any]) -> dict[str, Any]:
    """Produit le rapport de qualité géométrique d'une tournée."""
    rapport: dict[str, Any] = {"vehicules": [], "global": {}}
    traces: list[list[Point]] = []

    for v in tour["vehicles"]:
        pts: list[Point] = [(s["lat"], s["lng"]) for s in v["stops"]]
        traces.append(pts)
        croisements = croisements_internes(pts)
        n_2opt, gain_2opt = deux_opt_restants(pts)
        n_reloc, gain_reloc = relocalisations_restantes(pts)
        detours = facteurs_de_detour(pts)
        # Attente : temps immobile à l'arrêt, au-delà du service rendu.
        attente = sum(s["depart"] - s["arrive"] - s["service"] for s in v["stops"])
        rapport["vehicules"].append({
            "id": v["id"],
            "arrets": len(v["stops"]),
            "servis": v["served"],
            "km": round(_longueur(pts) / 1000, 1),
            "fin": v["end"],
            "croisements": len(croisements),
            "detail_croisements": croisements[:5],
            "deux_opt_restants": n_2opt,
            "gain_2opt_m": round(gain_2opt),
            "relocalisations_restantes": n_reloc,
            "gain_reloc_m": round(gain_reloc),
            "detour_max": round(max(detours), 2) if detours else 0,
            "detour_median": round(sorted(detours)[len(detours) // 2], 2) if detours else 0,
            "attente_s": attente,
        })

    # Croisements entre véhicules distincts : signe d'un découpage territorial
    # discutable. Ce n'est pas une preuve de sous-optimalité — les fenêtres de
    # temps et la capacité peuvent l'imposer — mais c'est ce que l'œil remarque
    # en premier sur la carte.
    entre = 0
    for a in range(len(traces)):
        for b in range(a + 1, len(traces)):
            for i in range(len(traces[a]) - 1):
                for j in range(len(traces[b]) - 1):
                    if segments_se_croisent(traces[a][i], traces[a][i + 1],
                                            traces[b][j], traces[b][j + 1]):
                        entre += 1
    fins = [v["end"] for v in tour["vehicles"]]
    rapport["global"] = {
        "croisements_entre_tournees": entre,
        "croisements_internes_total": sum(v["croisements"] for v in rapport["vehicules"]),
        "deux_opt_restants_total": sum(v["deux_opt_restants"] for v in rapport["vehicules"]),
        "gain_2opt_total_m": sum(v["gain_2opt_m"] for v in rapport["vehicules"]),
        "desequilibre_s": max(fins) - min(fins) if fins else 0,
        "attente_totale_s": sum(v["attente_s"] for v in rapport["vehicules"]),
    }
    return rapport


def carte_ascii(tour: dict[str, Any], largeur: int = 78, hauteur: int = 30) -> str:
    """Rendu texte de la solution, pour vérifier d'un coup d'œil.

    Chaque véhicule a son chiffre, le dépôt vaut `D`, les hubs `H`. Un tracé
    absurde se voit ici bien plus vite que dans un tableau de nombres.
    """
    b = tour["bounds"]
    lat_min, lat_max = b["minLat"], b["maxLat"]
    lng_min, lng_max = b["minLng"], b["maxLng"]

    def projeter(lat: float, lng: float) -> tuple[int, int]:
        x = int((lng - lng_min) / max(lng_max - lng_min, 1e-9) * (largeur - 1))
        # La latitude croît vers le nord, les lignes vers le bas.
        y = int((lat_max - lat) / max(lat_max - lat_min, 1e-9) * (hauteur - 1))
        return max(0, min(largeur - 1, x)), max(0, min(hauteur - 1, y))

    grille = [[" "] * largeur for _ in range(hauteur)]
    for v in tour["vehicles"]:
        marque = str(v["id"])
        for seg in v["legs"]:
            # Quelques points interpolés suffisent à rendre le trait lisible.
            (y1, x1), (y2, x2) = seg["pts"][0], seg["pts"][-1]
            for k in range(0, 21):
                t = k / 20
                x, y = projeter(y1 + (y2 - y1) * t, x1 + (x2 - x1) * t)
                if grille[y][x] == " ":
                    grille[y][x] = "·"
        for s in v["stops"]:
            x, y = projeter(s["lat"], s["lng"])
            if s["kind"] == "customer":
                grille[y][x] = marque
    for h in tour.get("hubs", []):
        x, y = projeter(h["lat"], h["lng"])
        grille[y][x] = "H"
    x, y = projeter(tour["depot"]["lat"], tour["depot"]["lng"])
    grille[y][x] = "D"

    cadre = "+" + "-" * largeur + "+"
    lignes = [cadre] + ["|" + "".join(ligne) + "|" for ligne in grille] + [cadre]
    return "\n".join(lignes)


def afficher(tour: dict[str, Any], rapport: dict[str, Any], avec_carte: bool) -> None:
    if avec_carte:
        print(carte_ascii(tour))
        print("  D dépôt   H hub   chiffre = véhicule   · trajet\n")

    print(f"  {'véh':>3} {'arrêts':>6} {'km':>6} {'crois.':>6} {'2-opt':>6} "
          f"{'gain m':>7} {'reloc':>6} {'détour max':>10} {'attente':>8}")
    for v in rapport["vehicules"]:
        print(f"  {v['id']:>3} {v['arrets']:>6} {v['km']:>6} {v['croisements']:>6} "
              f"{v['deux_opt_restants']:>6} {v['gain_2opt_m']:>7} "
              f"{v['relocalisations_restantes']:>6} {v['detour_max']:>10} {v['attente_s']:>8}")

    g = rapport["global"]
    if tour["stats"].get("timeWindowsBinding"):
        print("\n  ATTENTION : les fenêtres de temps sont contraignantes. Une inversion 2-opt")
        print("  change les heures d'arrivée : les mouvements comptés ci-dessous raccourcissent")
        print("  la distance, mais certains seraient infaisables. À lire comme une borne haute.")
    print(f"\n  croisements internes    {g['croisements_internes_total']}"
          f"   (preuve de sous-optimalité en métrique euclidienne)")
    print(f"  croisements entre véh.  {g['croisements_entre_tournees']}"
          f"   (indice, pas preuve : les contraintes peuvent l'imposer)")
    print(f"  2-opt encore possibles  {g['deux_opt_restants_total']}"
          f"   (gain cumulé jusqu'à {g['gain_2opt_total_m']} m)")
    print(f"  déséquilibre des fins   {g['desequilibre_s']} s")
    print(f"  attente totale          {g['attente_totale_s']} s")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cvrptw-audit",
        description="Audit de qualité géométrique d'une tournée : ce que les indicateurs ne montrent pas.",
    )
    parser.add_argument("tour", type=Path)
    parser.add_argument("--carte", action="store_true", help="afficher la carte ASCII")
    parser.add_argument("--json", action="store_true", dest="en_json")
    args = parser.parse_args()

    tour = json.loads(args.tour.read_text(encoding="utf-8"))
    rapport = auditer(tour)
    if args.en_json:
        print(json.dumps(rapport, indent=2, ensure_ascii=False))
    else:
        afficher(tour, rapport, args.carte)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
