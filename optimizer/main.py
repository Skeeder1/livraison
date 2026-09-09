"""Interface en ligne de commande du solveur.

Résout un scénario et écrit le document de tournée — exactement le contrat que
consomme l'interface web (`web/`) et que sert l'API de scénario. Une seule
représentation de la solution circule donc dans tout le projet.

Cette commande remplace un ancien parcours qui produisait une carte folium
autonome : une seconde implémentation de la visualisation, avec son propre
interpolateur de positions qui ignorait la correction en cos(latitude), et donc
ses propres écarts. Elle résolvait aussi le problème une fois de plus, sans
hubs, dans le seul but d'afficher une distance de référence.

    cvrptw-solve --customers 45 --vehicles 3 --hubs 2 --out tour.json
    cd web && npm run dev        # puis charger le fichier produit
"""
import argparse
import json
import sys
from pathlib import Path

from optimizer.scenario import (
    NoSolutionError,
    SCENARIO_DEFAULTS,
    SCENARIO_LIMITS,
    ScenarioParamsError,
    solve_scenario,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cvrptw-solve",
        description="Résout une instance de livraison et écrit le document de tournée.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    for name in ("customers", "vehicles", "hubs", "capacity"):
        low, high = SCENARIO_LIMITS[name]
        parser.add_argument(f"--{name}", type=int, default=SCENARIO_DEFAULTS[name],
                            help=f"entre {low} et {high}")
    low, high = SCENARIO_LIMITS["budget_seconds"]
    parser.add_argument("--budget", type=int, default=SCENARIO_DEFAULTS["budget_seconds"],
                        dest="budget_seconds", help=f"budget de résolution, en secondes ({low}-{high})")
    parser.add_argument("--seed", type=int, default=SCENARIO_DEFAULTS["seed"],
                        help="graine d'instance ; omettre pour une instance non reproductible")
    parser.add_argument("--time-windows", action="store_true", dest="time_windows_binding",
                        help="resserrer les fenêtres de temps jusqu'à les rendre contraignantes")
    parser.add_argument("--out", type=Path, default=Path("tour.json"),
                        help="fichier de sortie")
    parser.add_argument("--workdir", type=Path, default=Path("data"),
                        help="répertoire des données d'instance générées")
    parser.add_argument("--no-roads", action="store_true",
                        help="ne pas interroger OSRM ; tracés à vol d'oiseau")
    return parser


def _resume(tour: dict) -> str:
    s = tour["stats"]
    lignes = [
        f"  clients servis     {s['customersServed']} / {s['customers']}",
        f"  distance           {s['roadKm']} km" + ("" if s.get("roadKm") is None else
                                                    ("  (à vol d'oiseau)" if not tour["vehicles"][0]["legs"][0]["road"] else "")),
        f"  horizon            {tour['horizon']} s",
        f"  conduite cumulée   {s['cumulativeDriveTime']} s",
        f"  rechargements      {s['reloads']}",
        f"  retard             {s['tardinessMinutes']} min",
    ]
    if s["hubsAvailable"]:
        lignes.append(f"  rendez-vous        {s['hubsActivated']} sur {s['hubsAvailable']} hubs proposés")
    return "\n".join(lignes)


def main() -> int:
    args = build_parser().parse_args()
    params = {
        "customers": args.customers,
        "vehicles": args.vehicles,
        "hubs": args.hubs,
        "capacity": args.capacity,
        "budget_seconds": args.budget_seconds,
        "seed": args.seed,
        "time_windows_binding": args.time_windows_binding,
    }

    print(f"Résolution : {args.customers} clients, {args.vehicles} véhicules, "
          f"{args.hubs} hub(s), budget {args.budget_seconds} s…")
    try:
        tour = solve_scenario(params, workdir=args.workdir, fetch_roads=not args.no_roads)
    except ScenarioParamsError as exc:
        print(f"Paramètres invalides : {exc}", file=sys.stderr)
        return 2
    except NoSolutionError as exc:
        print(f"Aucune solution trouvée : {exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(tour), encoding="utf-8")

    print(_resume(tour))
    print(f"\nDocument de tournée écrit dans {args.out}")
    print(f"Pour le visualiser :  cd web && npm run dev   (puis charger {args.out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
