"""
Courbes de convergence : quand la recherche cesse-t-elle de progresser ?

Le budget de recherche est un **plafond**, jamais un critère d'arrêt. La
métaheuristique améliore tant qu'on la laisse tourner et rend la meilleure
solution qu'elle a vue ; de l'extérieur, une résolution qui a convergé et une
résolution coupée en pleine progression rendent toutes deux « une solution ».
Rien ne distingue les deux. C'est pourquoi ce module existe : il enregistre la
trajectoire, pas seulement son point d'arrivée.

Trois propriétés mesurées avant d'en tirer quoi que ce soit, parce que la méthode
en dépend :

* **la trajectoire est déterministe.** Deux exécutions du même couple
  (instance, graine) rendent la même suite d'objectifs, à la gigue d'horloge
  près sur les dates ;
* **une trajectoire courte est le préfixe exact d'une trajectoire longue.** La
  recherche ne connaît pas son plafond et ne change pas de comportement selon
  lui. Mesurer une fois à budget large donne donc la courbe de **tous** les
  budgets plus courts, ce qui divise le coût de l'étude par le nombre de budgets
  étudiés ;
* **la suite des objectifs rendus n'est pas décroissante.** La recherche locale
  guidée accepte des dégradations pour sortir d'un optimum local, et le rappel
  de solution voit ces solutions-là aussi. Le chiffre qui a un sens est donc le
  **minimum courant**, celui que le solveur finira par rendre, et non la
  dernière valeur observée.

Cette dernière propriété n'est pas un détail de mise en œuvre. Confondre les
deux — lire la date du dernier rappel plutôt que celle de la dernière
amélioration — fait conclure que la recherche progressait encore à la dernière
milliseconde alors qu'elle n'avait rien amélioré depuis longtemps. C'est
exactement l'erreur que ce module sert à ne plus commettre.

Usage ::

    python -m experiments.convergence --out experiments/out/convergence.jsonl

Le journal est un JSONL append-only : une ligne par exécution, reprise par
soustraction des couples déjà mesurés. Voir `experiments/store.py`.
"""
from __future__ import annotations

import argparse
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from experiments.store import ResultStore, read_rows
from optimizer.config import Config
from optimizer.create_toy_data import create_toy_data
from optimizer.data_loader import load_data
from optimizer.solver import solve_vrp

#: Attributs de `Config` que la génération d'instance écrase, et qu'il faut donc
#: restaurer. `Config` porte des attributs de **classe** : un oubli ici fuit sur
#: toutes les exécutions suivantes du même processus.
CONFIG_KEYS = (
    "NUM_CUSTOMERS",
    "NUM_VEHICLES",
    "NUM_HUBS",
    "VEHICLE_CAPACITY_MIN",
    "VEHICLE_CAPACITY_MAX",
    "TW_END_MIN",
    "TW_END_MAX",
    "RANDOM_SEED",
)

#: Fenêtres ouvertes sur la journée : on mesure la convergence, pas la capacité
#: du modèle à respecter des horaires. Des fenêtres serrées changeraient la forme
#: de la courbe pour une raison qui n'est pas celle qu'on étudie.
OPEN_TW = 86400


def trajectoire(
    *,
    customers: int,
    vehicles: int,
    capacity: int,
    seed: int,
    budget_seconds: int,
    road_matrix: bool,
) -> tuple[list[tuple[int, int]], bool]:
    """
    Résout une instance et rend la suite ``(date_ms, objectif)`` des solutions.

    La date est relevée dans le rappel, donc au plus près de la solution. Le
    rappel se contente d'ajouter un couple à une liste : il s'exécute dans la
    boucle de recherche, et tout ce qu'il consomme est pris sur le budget qu'il
    sert à mesurer.

    :return: Le couple ``(points, routiere)``. `points` est la suite
        ``(millisecondes depuis le départ, objectif)`` dans l'ordre où le
        solveur les a rendus — suite **non décroissante**, cf. le docstring du
        module. `routiere` dit si la matrice routière a réellement été obtenue.

        Ce second drapeau n'est pas décoratif. `create_toy_data` retombe
        silencieusement sur les distances euclidiennes quand le serveur de
        routage refuse la requête — un HTTP 429 suffit — et ne le signale que
        par une ligne sur la sortie standard. Une campagne qui ne le consigne
        pas mélange donc, sans que rien ne le montre, des mesures routières et
        des mesures à vol d'oiseau. C'est arrivé, et c'est ce qui a coûté une
        campagne.
    """
    saved = {key: getattr(Config, key) for key in CONFIG_KEYS}
    try:
        Config.update(
            NUM_CUSTOMERS=customers,
            NUM_VEHICLES=vehicles,
            NUM_HUBS=0,
            VEHICLE_CAPACITY_MIN=float(capacity),
            VEHICLE_CAPACITY_MAX=float(capacity),
            TW_END_MIN=OPEN_TW,
            TW_END_MAX=OPEN_TW,
            RANDOM_SEED=seed,
        )
        with tempfile.TemporaryDirectory(prefix="convergence-") as workdir:
            create_toy_data(workdir, verbose=False, road_matrix=road_matrix)
            data = load_data(workdir)
            data["time_limit"] = budget_seconds

            points: list[tuple[int, int]] = []
            depart = time.monotonic()

            def observer(routing: Any) -> None:
                points.append(
                    (round((time.monotonic() - depart) * 1000), routing.CostVar().Max())
                )

            solve_vrp(data, on_solution=observer)
            return points, data.get("time_matrix") is not None
    finally:
        Config.update(**saved)


def minimum_courant(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Suite ``(date, meilleur objectif connu à cette date)``, décroissante."""
    meilleur = None
    courbe = []
    for date, objectif in points:
        if meilleur is None or objectif < meilleur:
            meilleur = objectif
        courbe.append((date, meilleur))
    return courbe


def ameliorations(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Ne garde que les solutions qui **améliorent** le minimum courant."""
    meilleur = None
    gardees = []
    for date, objectif in points:
        if meilleur is None or objectif < meilleur:
            meilleur = objectif
            gardees.append((date, objectif))
    return gardees


def coude(points: list[tuple[int, int]], budget_ms: int, tolerance: float) -> int:
    """
    Premier instant après lequel l'objectif ne gagne plus que `tolerance`.

    C'est le critère de l'issue #21, écrit explicitement : on cherche la plus
    petite date `t` telle que l'objectif à `t` soit à moins de `tolerance` près
    du meilleur objectif atteint sur tout le budget. Tout ce qui suit `t` est du
    temps acheté pour un gain inférieur à la tolérance.

    :param tolerance: Écart relatif toléré, par exemple 0.01 pour 1 %
    :return: Date en millisecondes ; `budget_ms` si le seuil n'est jamais atteint
    """
    ameliorants = ameliorations(points)
    if not ameliorants:
        return budget_ms
    final = ameliorants[-1][1]
    seuil = final * (1.0 + tolerance)
    for date, objectif in ameliorants:
        if objectif <= seuil:
            return date
    return budget_ms


#: Budgets candidats, en secondes. La règle choisit parmi eux : proposer une
#: valeur qui n'a pas été mesurée reviendrait à extrapoler une courbe dont on
#: sait qu'elle n'est pas lisse.
BUDGETS_CANDIDATS = (1, 2, 3, 5, 8, 10, 15, 20, 30, 45, 60)

#: Critère d'acceptation d'un budget, écrit une fois et appliqué partout.
#:
#: Deux seuils et non un, parce qu'une seule statistique se laisse tromper. La
#: médiane seule accepterait un budget qui sert bien l'instance typique et
#: abandonne un quart des visiteurs ; un quantile élevé seul ferait payer à tout
#: le monde le pire cas, et sur les grandes instances il n'est atteint qu'au
#: plafond — mesuré, la cellule 45 clients / 2 livreurs reste à 11,2 % au
#: quantile 0,9 de 5 s jusqu'à 30 s, parce qu'une graine sur cinq trouve une
#: grosse amélioration entre 30 et 60 s.
#:
#: Les seuils portent sur l'**écart à ce que trouve une recherche d'une minute**,
#: en pourcentage de l'objectif, et non sur la date de la dernière amélioration.
#: C'est la question du visiteur : non pas « la recherche a-t-elle fini » mais
#: « à combien de la meilleure tournée connue suis-je ».
ECART_MEDIAN_MAX = 0.5
ECART_Q75_MAX = 5.0


def objectif_a(trajectoire: list[list[int]], date_ms: int) -> int | None:
    """Meilleur objectif connu à cette date, ou `None` si rien n'a encore été
    trouvé — ce qui arrive : sur 60 clients, une seconde ne suffit pas toujours
    à produire une première solution."""
    meilleur = None
    for date, objectif in trajectoire:
        if date > date_ms:
            break
        meilleur = objectif
    return meilleur


def ecarts(lignes: list[dict[str, Any]], budget_s: int) -> list[float] | None:
    """
    Écart relatif à l'objectif final, en %, pour chaque exécution.

    Rend `None` si une seule exécution n'a pas de solution à cette date : un
    budget qui laisse un visiteur sans tournée n'est pas un budget acceptable,
    et le moyenner avec ceux qui ont réussi masquerait exactement ce cas.
    """
    valeurs = []
    for ligne in lignes:
        final = ligne["trajectoire"][-1][1]
        obtenu = objectif_a(ligne["trajectoire"], budget_s * 1000)
        if obtenu is None:
            return None
        valeurs.append((obtenu - final) / final * 100.0)
    return valeurs


def _quantile(valeurs: list[float], q: float) -> float:
    ordonnees = sorted(valeurs)
    if len(ordonnees) == 1:
        return ordonnees[0]
    rang = q * (len(ordonnees) - 1)
    bas = int(rang)
    haut = min(bas + 1, len(ordonnees) - 1)
    return ordonnees[bas] + (ordonnees[haut] - ordonnees[bas]) * (rang - bas)


def regle(rows: list[dict[str, Any]]) -> dict[int, int]:
    """
    Budget retenu par nombre de clients : le plus petit qui passe le critère.

    Le budget est indexé sur le **nombre de clients seul**, et c'est un choix
    que les mesures imposent plutôt qu'une simplification. La flotte ne classe
    pas la difficulté : à 45 clients, deux livreurs sont plus faciles que trois
    — moins de tournées, donc un espace de recherche plus petit — alors que
    l'intuition dit le contraire. Le rapport « chargements par véhicule » ne la
    classe pas davantage. Indexer sur un facteur qui n'ordonne pas la difficulté
    donnerait une règle plus compliquée et pas meilleure.

    Chaque taille prend donc le budget qui satisfait le critère pour **toutes**
    les flottes et toutes les capacités mesurées à cette taille : c'est la
    flotte la plus exigeante qui décide, puisque le visiteur choisit la sienne.
    """
    par_taille: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        par_taille.setdefault(row["customers"], []).append(row)

    retenus = {}
    for clients, lignes in sorted(par_taille.items()):
        cellules: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for ligne in lignes:
            cellules.setdefault((ligne["vehicles"], ligne["capacity"]), []).append(ligne)
        choisi = max(BUDGETS_CANDIDATS)
        for budget in BUDGETS_CANDIDATS:
            convient = True
            for cellule in cellules.values():
                valeurs = ecarts(cellule, budget)
                if valeurs is None:
                    convient = False
                    break
                if (
                    _quantile(valeurs, 0.5) > ECART_MEDIAN_MAX
                    or _quantile(valeurs, 0.75) > ECART_Q75_MAX
                ):
                    convient = False
                    break
            if convient:
                choisi = budget
                break
        retenus[clients] = choisi
    return retenus


def empreinte_machine() -> dict[str, Any]:
    """
    De quoi relire une mesure sans se tromper sur ce qu'elle vaut.

    Un coude est une **durée**, donc une propriété de la machine autant que du
    problème : la même instance converge deux fois plus tard sur un processeur
    bridé à 1,3 GHz que sur le même processeur libre. Une campagne dont les
    exécutions ne partagent pas le même profil de fréquence ne mesure rien du
    tout, et rien dans les nombres ne le montrerait.

    Le profil est donc consigné par ligne, et l'analyse refuse d'en mélanger
    deux — au même titre qu'elle refuse de mélanger routier et euclidien.
    """
    profil = "inconnu"
    try:
        profil = subprocess.run(
            ["powerprofilesctl", "get"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    return {
        "profil_energie": profil,
        "processeur": platform.processor() or platform.machine(),
        "python": platform.python_version(),
    }


def empreinte_modele() -> str:
    """SHA du dépôt au moment de la mesure, pour rattacher une ligne au code."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent.parent,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "inconnu"


def plan(
    tailles: list[int],
    vehicules: list[int],
    capacites: list[int],
    graines: list[int],
) -> list[dict[str, int]]:
    """
    Développe la grille en exécutions élémentaires, ordre déterministe.

    La capacité fait partie de la grille et non des constantes, parce que la
    difficulté d'une instance ne tient pas au nombre de clients seul. Mesuré :
    à 25 clients et 3 livreurs le coude à 1 % tombe à 609 ms, à 25 clients et
    2 livreurs la médiane est à 768 ms mais le quantile 0,9 à 35 917 ms. Ce qui
    change entre les deux, c'est le nombre de chargements que chaque véhicule
    doit enchaîner. Une règle calibrée à capacité fixe ne couvrirait donc pas ce
    que le panneau propose, qui va de 5 à 20.
    """
    return [
        {"customers": c, "vehicles": v, "capacity": k, "seed": s}
        for c in tailles
        for v in vehicules
        for k in capacites
        for s in graines
    ]


def cle(run: dict[str, Any]) -> tuple[int, int, int, int]:
    return (run["customers"], run["vehicles"], run["capacity"], run["seed"])


def analyser(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Résume une campagne : par taille et par flotte, quand la recherche s'arrête.

    Deux chiffres par cellule, et ils ne disent pas la même chose :

    * la **dernière amélioration**, date au-delà de laquelle plus rien ne bouge.
      C'est le temps qu'il aurait fallu donner pour obtenir exactement la même
      tournée ;
    * le **coude à 1 %**, date à partir de laquelle l'objectif est déjà à moins
      de 1 % de sa valeur finale. C'est le temps qu'il faut donner pour obtenir
      une tournée qu'on ne saurait distinguer de la meilleure.

    Le second est ce qu'un bouton « temps optimal » doit viser : le premier
    achète une décimale.

    Le résumé retient le **quantile 0,9** sur les graines, pas la moyenne. Un
    budget doit couvrir la plupart des instances de cette taille, pas l'instance
    moyenne — la moitié des visiteurs seraient sinon servis par une recherche
    coupée trop tôt.
    """
    import statistics

    melange = {row.get("matrice_routiere_obtenue") for row in rows}
    if len(melange) > 1:
        raise ValueError(
            "le journal mélange des mesures routières et euclidiennes : "
            "les résumer ensemble n'aurait aucun sens"
        )

    profils = {row.get("profil_energie") for row in rows}
    if len(profils) > 1:
        raise ValueError(
            f"le journal mélange des profils de fréquence {sorted(profils)} : "
            "un coude est une durée, donc dépendant de l'horloge"
        )

    cellules: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        cellules.setdefault(
            (row["customers"], row["vehicles"], row["capacity"]), []
        ).append(row)

    def quantile(valeurs: list[int], q: float) -> int:
        ordonnees = sorted(valeurs)
        if len(ordonnees) == 1:
            return ordonnees[0]
        rang = q * (len(ordonnees) - 1)
        bas = int(rang)
        haut = min(bas + 1, len(ordonnees) - 1)
        return round(ordonnees[bas] + (ordonnees[haut] - ordonnees[bas]) * (rang - bas))

    resume = {}
    for (clients, vehicules, capacite), lignes in sorted(cellules.items()):
        derniere = [ligne["derniere_amelioration_ms"] for ligne in lignes]
        coude1 = [ligne["coude_1pct_ms"] for ligne in lignes]
        resume[f"{clients}c/{vehicules}v/cap{capacite}"] = {
            "chargements_par_vehicule": round(clients / (vehicules * capacite), 2),
            "graines": len(lignes),
            "derniere_amelioration_ms": {
                "mediane": round(statistics.median(derniere)),
                "q90": quantile(derniere, 0.9),
                "max": max(derniere),
            },
            "coude_1pct_ms": {
                "mediane": round(statistics.median(coude1)),
                "q90": quantile(coude1, 0.9),
                "max": max(coude1),
            },
            "budget_ms": lignes[0]["budget_seconds"] * 1000,
        }
    return resume


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--out", type=Path, default=Path("experiments/out/convergence.jsonl"))
    parser.add_argument("--budget", type=int, default=60, help="Plafond de recherche, en secondes")
    parser.add_argument("--tailles", type=int, nargs="+", default=[10, 25, 45, 60])
    parser.add_argument("--vehicules", type=int, nargs="+", default=[2, 3, 5])
    parser.add_argument("--capacites", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--graines", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument(
        "--euclidien",
        action="store_true",
        help="Mesure à vol d'oiseau. Par défaut la matrice routière, "
        "c'est-à-dire ce que résout la démonstration en production.",
    )
    parser.add_argument(
        "--regle",
        action="store_true",
        help="N'exécute rien : dérive le budget par taille et sort.",
    )
    parser.add_argument(
        "--analyser",
        action="store_true",
        help="N'exécute rien : résume le journal existant et sort.",
    )
    args = parser.parse_args(argv)

    if args.regle:
        rows = read_rows(args.out)
        if not rows:
            print(f"aucune mesure dans {args.out}")
            return 1
        retenus = regle(rows)
        print(
            f"{len(rows)} exécutions. Critère : médiane <= {ECART_MEDIAN_MAX} %, "
            f"quantile 0,75 <= {ECART_Q75_MAX} % d'écart à une recherche de "
            f"{rows[0]['budget_seconds']} s.\n"
        )
        print(f"{'clients':>8} {'budget':>8}   détail par cellule (médiane/q75 à ce budget)")
        for clients, budget in retenus.items():
            lignes = [r for r in rows if r["customers"] == clients]
            cellules: dict[tuple[int, int], list[dict[str, Any]]] = {}
            for ligne in lignes:
                cellules.setdefault((ligne["vehicles"], ligne["capacity"]), []).append(ligne)
            detail = []
            for (v, k), cellule in sorted(cellules.items()):
                valeurs = ecarts(cellule, budget)
                if valeurs is None:
                    detail.append(f"{v}v/c{k}:pas de solution")
                else:
                    detail.append(
                        f"{v}v/c{k}:{_quantile(valeurs, 0.5):.2f}/{_quantile(valeurs, 0.75):.2f}"
                    )
            print(f"{clients:>8} {budget:>7} s   " + "  ".join(detail))
        return 0

    if args.analyser:
        rows = read_rows(args.out)
        if not rows:
            print(f"aucune mesure dans {args.out}")
            return 1
        resume = analyser(rows)
        largeur = max(len(cle) for cle in resume)
        print(f"{len(rows)} exécutions, budget {rows[0]['budget_seconds']} s\n")
        print(f"{'instance':<{largeur}}  {'dernière amélioration (ms)':>28}  {'coude 1 % (ms)':>24}")
        print(f"{'':<{largeur}}  {'médiane':>9}{'q90':>9}{'max':>10}  {'médiane':>8}{'q90':>8}{'max':>8}")
        for cle_cellule, valeurs in resume.items():
            d, c = valeurs["derniere_amelioration_ms"], valeurs["coude_1pct_ms"]
            print(
                f"{cle_cellule:<{largeur}}  {d['mediane']:>9}{d['q90']:>9}{d['max']:>10}"
                f"  {c['mediane']:>8}{c['q90']:>8}{c['max']:>8}"
            )
        return 0

    road_matrix = not args.euclidien
    a_faire = plan(args.tailles, args.vehicules, args.capacites, args.graines)
    deja = {
        cle(r)
        for r in read_rows(args.out)
        if r.get("road_matrix") == road_matrix and r.get("budget_seconds") == args.budget
    }
    restant = [r for r in a_faire if cle(r) not in deja]

    print(
        f"{len(a_faire)} exécutions au plan, {len(deja)} déjà mesurées, "
        f"{len(restant)} à faire — budget {args.budget} s, "
        f"matrice {'routière' if road_matrix else 'euclidienne'}",
        flush=True,
    )

    sha = empreinte_modele()
    machine = empreinte_machine()
    print(f"machine : {machine['profil_energie']}, {machine['processeur']}", flush=True)
    with ResultStore(args.out) as store:
        for numero, run in enumerate(restant, start=1):
            depart = time.monotonic()
            points, routiere = trajectoire(
                customers=run["customers"],
                vehicles=run["vehicles"],
                capacity=run["capacity"],
                seed=run["seed"],
                budget_seconds=args.budget,
                road_matrix=road_matrix,
            )
            ameliorants = ameliorations(points)
            budget_ms = args.budget * 1000
            ligne = {
                **run,
                "budget_seconds": args.budget,
                "road_matrix": road_matrix,
                # Ce qui a réellement servi, et non ce qui a été demandé.
                "matrice_routiere_obtenue": routiere,
                "solutions": len(points),
                "ameliorations": len(ameliorants),
                "objectif_final": ameliorants[-1][1] if ameliorants else None,
                "derniere_amelioration_ms": ameliorants[-1][0] if ameliorants else None,
                "dernier_rappel_ms": points[-1][0] if points else None,
                "coude_1pct_ms": coude(points, budget_ms, 0.01),
                "coude_2pct_ms": coude(points, budget_ms, 0.02),
                "coude_5pct_ms": coude(points, budget_ms, 0.05),
                "trajectoire": ameliorants,
                "duree_reelle_s": round(time.monotonic() - depart, 2),
                "modele_sha": sha,
                **machine,
            }
            if road_matrix and not routiere:
                print(
                    "   ⚠️  matrice routière refusée : mesure ignorée, "
                    "elle sera reprise à la reprise de la campagne",
                    flush=True,
                )
                continue
            store.append(ligne)
            print(
                f"[{numero}/{len(restant)}] {run['customers']} clients, "
                f"{run['vehicles']} livreurs, capacité {run['capacity']}, "
                f"graine {run['seed']} : "
                f"{len(ameliorants)} améliorations, dernière à "
                f"{ligne['derniere_amelioration_ms']} ms, "
                f"coude 1 % à {ligne['coude_1pct_ms']} ms",
                flush=True,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
