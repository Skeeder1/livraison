"""
Spécification d'une campagne, et développement en exécutions élémentaires.

Le format est du **JSON**, pas du YAML : `pyyaml` n'est pas installé dans
`.venv` et le harnais ne doit pas ajouter de dépendance pour lire un fichier de
trente lignes.

Format
------

.. code-block:: json

    {
      "name": "phase1-ofat",
      "budget_seconds": 10,
      "scenario": {"customers": 45, "vehicles": 3, "capacity": 10},
      "scenario_variants": [{"hubs": 0}, {"hubs": 2}],
      "baseline_factors": {"TIME_SPAN_COEFFICIENT": 200},
      "sweeps": [
        {"factor": "TIME_SPAN_COEFFICIENT", "values": [10, 50, 200, 1000]},
        {"factor": "DROP_CUSTOMER_PENALTY_METERS",
         "log_range": {"from": 1e4, "to": 1e7, "points": 7, "round": "int"}}
      ]
    }

* `scenario` porte les paramètres communs, `scenario_variants` les variations
  du scénario lui-même (typiquement `hubs`, dont dépend le sens même de
  `TRANSFER_PENALTY_METERS`). Chaque balayage est répété sur chaque variante.
* `baseline_factors` ne liste que ce qui s'écarte des valeurs livrées dans
  `optimizer.config.Config` ; le reste est lu dans `Config` au développement,
  de sorte que la référence de la campagne **est** la configuration du dépôt.
* Un point de balayage égal à la valeur de référence produit exactement la
  configuration de référence : il est fusionné avec elle, et donc exécuté une
  seule fois. C'est ce qui rend l'appariement gratuit.

Un seul facteur varie à la fois (`OFAT`, phase 1 du protocole) : chaque
exécution ne s'écarte de la référence que par un attribut.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Origine du jeu de graines par défaut. Arbitraire, mais **fixe** : c'est ce qui
#: garantit que deux campagnes lancées à six mois d'écart restent comparables.
SEED_ORIGIN = 1000

#: Facteurs sondés par le harnais. Tous sont des attributs de classe de
#: `optimizer.config.Config`, donc modifiables depuis le processus fils.
#:
#: `VEHICLE_FIXED_COST_METERS` a longtemps été une constante **écrite en dur**
#: dans `optimizer/solver.py` (`routing.SetFixedCostOfAllVehicles(50)`). Elle est
#: désormais lue dans `Config`, donc balayable. Le garde-fou de `_check_factor`
#: reste en place : si l'attribut disparaissait de `Config`, le développement de
#: la grille échouerait bruyamment au lieu de produire une courbe plate qu'on
#: lirait comme une absence d'effet.
KNOWN_FACTORS: tuple[str, ...] = (
    "TRANSFER_PENALTY_METERS",
    "DROP_CUSTOMER_PENALTY_METERS",
    "TIME_SPAN_COEFFICIENT",
    "CAPACITY_SPAN_COEFFICIENT",
    "DISTANCE_SPAN_COEFFICIENT",
    "TIME_WINDOW_VIOLATION_PENALTY",
    "SERVICE_TIME_PER_UNIT",
    "VEHICLE_FIXED_COST_METERS",
)

#: Clés de scénario acceptées, reprises de `optimizer.scenario.SCENARIO_DEFAULTS`
#: moins `seed` et `budget_seconds`, que le harnais pilote lui-même.
SCENARIO_KEYS: tuple[str, ...] = (
    "customers",
    "vehicles",
    "hubs",
    "capacity",
    "time_windows_binding",
)


class GridError(ValueError):
    """Spécification de campagne invalide."""


@dataclass(frozen=True)
class RunSpec:
    """
    Une exécution élémentaire : une configuration, un scénario, une graine.

    :ivar config_key: Empreinte stable de (facteurs, scénario, budget). C'est la
        clé de reprise, avec `seed`.
    :ivar label: Étiquette lisible, par exemple `TIME_SPAN_COEFFICIENT=1000 | hubs=0`.
    :ivar factors: Valeurs **complètes** des facteurs, référence comprise.
    :ivar scenario: Paramètres complets du scénario.
    :ivar budget_seconds: Budget de recherche imposé au solveur.
    :ivar seed: Graine de l'instance.
    :ivar memberships: Balayages auxquels cette configuration appartient, sous la
        forme `(facteur, valeur)`. Une configuration égale à la référence
        appartient à *tous* les balayages, à leur point de référence.
    :ivar is_baseline: Vrai si la configuration est exactement la référence.
    """

    config_key: str
    label: str
    factors: dict[str, Any]
    scenario: dict[str, Any]
    budget_seconds: int
    seed: int
    memberships: tuple[tuple[str, Any], ...] = ()
    is_baseline: bool = False

    @property
    def resume_key(self) -> tuple[str, int]:
        """Couple qui identifie une ligne déjà présente dans le journal."""
        return (self.config_key, self.seed)


@dataclass
class Campaign:
    """Campagne développée : la liste ordonnée des exécutions et son contexte."""

    name: str
    baseline_factors: dict[str, Any]
    scenario_variants: list[dict[str, Any]]
    budget_seconds: int
    seeds: list[int]
    runs: list[RunSpec] = field(default_factory=list)
    #: Points demandés par balayage, dans l'ordre du fichier, pour le rapport.
    sweep_points: dict[str, list[Any]] = field(default_factory=dict)

    @property
    def unique_configs(self) -> int:
        """Nombre de configurations distinctes, graines mises à part."""
        return len({run.config_key for run in self.runs})


def default_seeds(count: int) -> list[int]:
    """
    Jeu de graines par défaut : `SEED_ORIGIN`, `SEED_ORIGIN + 1`, …

    Le protocole impose des **blocs appariés** : toute configuration est évaluée
    sur les mêmes graines. La liste est donc déterministe et ne dépend que du
    nombre demandé — allonger une campagne conserve les graines déjà mesurées.

    :param count: Nombre de graines
    :return: Liste croissante de graines entières
    :raises GridError: si `count` n'est pas strictement positif
    """
    if count <= 0:
        raise GridError(f"Il faut au moins une graine, reçu {count}")
    return [SEED_ORIGIN + i for i in range(count)]


def log_range(
    low: float, high: float, points: int, rounding: str = "int"
) -> list[float]:
    """
    Suite géométrique de `low` à `high`, bornes comprises.

    L'échelle logarithmique est imposée par le protocole : ces facteurs sont des
    pénalités dont l'effet se joue en ordres de grandeur, pas en increments.

    :param low: Borne basse, strictement positive
    :param high: Borne haute, supérieure ou égale à `low`
    :param points: Nombre de points, au moins 2
    :param rounding: `"int"` pour arrondir à l'entier, `"none"` pour laisser
        les flottants, `"sig3"` pour trois chiffres significatifs
    :return: Points croissants, dédoublonnés en conservant l'ordre
    :raises GridError: bornes ou nombre de points invalides
    """
    if low <= 0 or high <= 0:
        raise GridError("Une échelle logarithmique exige des bornes > 0")
    if high < low:
        raise GridError(f"Borne haute {high} inférieure à la borne basse {low}")
    if points < 2:
        raise GridError(f"Il faut au moins 2 points, reçu {points}")

    step = (math.log(high) - math.log(low)) / (points - 1)
    raw = [math.exp(math.log(low) + i * step) for i in range(points)]

    if rounding == "int":
        values: list[Any] = [int(round(v)) for v in raw]
    elif rounding == "sig3":
        values = [float(f"{v:.3g}") for v in raw]
    elif rounding == "none":
        values = list(raw)
    else:
        raise GridError(f"Arrondi inconnu : {rounding!r}")

    seen, ordered = set(), []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _config_defaults() -> dict[str, Any]:
    """
    Valeurs livrées des facteurs, lues dans `optimizer.config.Config`.

    L'import est local : les tests unitaires du développement de grille peuvent
    injecter leurs propres valeurs sans charger le paquet optimiseur.

    :return: Valeurs par défaut des facteurs connus effectivement présents
    """
    from optimizer.config import Config

    return {name: getattr(Config, name) for name in KNOWN_FACTORS if hasattr(Config, name)}


def _canonical_key(
    factors: dict[str, Any], scenario: dict[str, Any], budget_seconds: int
) -> str:
    """
    Empreinte stable d'une configuration. Sert de clé de reprise.

    Le sérialisé est trié et sans espace : deux fichiers de grille écrits
    différemment mais décrivant la même configuration produisent la même clé, et
    une reprise reconnaît donc le travail déjà fait.

    :param factors: Valeurs complètes des facteurs
    :param scenario: Paramètres complets du scénario
    :param budget_seconds: Budget de recherche
    :return: Empreinte hexadécimale de 12 caractères
    """
    payload = json.dumps(
        {"factors": factors, "scenario": scenario, "budget": budget_seconds},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def config_key_for(
    factors: dict[str, Any], scenario: dict[str, Any], budget_seconds: int
) -> str:
    """
    Empreinte publique d'une configuration, identique à celle du développement.

    Sert à reconstruire une exécution depuis une ligne déjà journalisée — par
    exemple pour rejouer une configuration gagnante à un autre budget. Le budget
    entre dans l'empreinte : deux budgets donnent deux clés, et la reprise ne les
    confond donc jamais.

    :param factors: Valeurs complètes des facteurs
    :param scenario: Paramètres complets du scénario
    :param budget_seconds: Budget de recherche
    :return: Empreinte hexadécimale de 12 caractères
    """
    return _canonical_key(factors, scenario, budget_seconds)


def _scenario_label(scenario: dict[str, Any]) -> str:
    """Étiquette courte d'une variante de scénario."""
    return f"hubs={scenario.get('hubs', 0)}"


def load_spec(path: Path) -> dict[str, Any]:
    """
    Charge une spécification JSON et vérifie sa forme.

    :param path: Chemin du fichier de grille
    :return: Spécification brute
    :raises GridError: fichier illisible, JSON invalide, ou clé inconnue
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GridError(f"Grille introuvable : {path}") from None
    except json.JSONDecodeError as exc:
        raise GridError(f"Grille {path} : JSON invalide — {exc}") from None

    if not isinstance(raw, dict):
        raise GridError(f"Grille {path} : un objet JSON est attendu")

    allowed = {
        "name",
        "budget_seconds",
        "scenario",
        "scenario_variants",
        "baseline_factors",
        "sweeps",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise GridError(
            f"Grille {path} : clés inconnues {sorted(unknown)}. "
            f"Attendues : {sorted(allowed)}"
        )
    return raw


def expand(
    spec: dict[str, Any],
    seeds: Sequence[int],
    *,
    budget_seconds: int | None = None,
    defaults: dict[str, Any] | None = None,
) -> Campaign:
    """
    Développe une spécification en liste d'exécutions élémentaires.

    L'ordre est **graine-majeur** : toutes les configurations sur la graine 1000,
    puis toutes sur la graine 1001, etc. Une campagne interrompue laisse donc un
    plan d'expérience *complet* sur les premières graines — analysable tel quel —
    au lieu d'un sous-ensemble de configurations mesurées sur toutes les graines,
    qui ne s'apparie avec rien.

    Au sein d'une graine, la référence passe en premier : elle est le point de
    comparaison de tout le reste, autant l'avoir tôt.

    :param spec: Spécification chargée par `load_spec`
    :param seeds: Jeu de graines, identique pour toutes les configurations
    :param budget_seconds: Budget imposé, prioritaire sur celui de la grille
    :param defaults: Valeurs de référence des facteurs ; par défaut lues dans
        `optimizer.config.Config`
    :return: Campagne développée
    :raises GridError: facteur inconnu, facteur non branché, ou balayage vide
    """
    if not seeds:
        raise GridError("Aucune graine : un plan apparié exige au moins une graine")

    budget = int(budget_seconds if budget_seconds is not None else spec.get("budget_seconds", 10))
    if budget <= 0:
        raise GridError(f"Budget invalide : {budget}")

    available = dict(defaults) if defaults is not None else _config_defaults()

    baseline_factors = dict(available)
    for name, value in (spec.get("baseline_factors") or {}).items():
        _check_factor(name, available)
        baseline_factors[name] = value

    base_scenario = dict(spec.get("scenario") or {})
    unknown = set(base_scenario) - set(SCENARIO_KEYS)
    if unknown:
        raise GridError(
            f"Clés de scénario inconnues {sorted(unknown)} ; attendues {sorted(SCENARIO_KEYS)}"
        )

    variants_raw = spec.get("scenario_variants") or [{}]
    variants: list[dict[str, Any]] = []
    for variant in variants_raw:
        unknown = set(variant) - set(SCENARIO_KEYS)
        if unknown:
            raise GridError(f"Clés de scénario inconnues dans une variante : {sorted(unknown)}")
        merged = dict(base_scenario)
        merged.update(variant)
        variants.append(merged)

    sweep_points: dict[str, list[Any]] = {}
    for sweep in spec.get("sweeps") or []:
        name = sweep.get("factor")
        _check_factor(name, available)
        values = _sweep_values(sweep)
        if not values:
            raise GridError(f"Balayage vide pour {name}")
        sweep_points[name] = values

    # Un dictionnaire par (clé de configuration) : les points de balayage qui
    # tombent sur la référence viennent s'y fusionner au lieu d'être réexécutés.
    configs: dict[str, dict[str, Any]] = {}

    def register(
        factors: dict[str, Any],
        scenario: dict[str, Any],
        membership: tuple[str, Any] | None,
        is_baseline: bool,
        label: str,
    ) -> None:
        key = _canonical_key(factors, scenario, budget)
        entry = configs.setdefault(
            key,
            {
                "factors": factors,
                "scenario": scenario,
                "memberships": [],
                "is_baseline": False,
                "label": label,
                "order": len(configs),
            },
        )
        if membership is not None and membership not in entry["memberships"]:
            entry["memberships"].append(membership)
        if is_baseline:
            entry["is_baseline"] = True
            entry["label"] = label

    for scenario in variants:
        register(dict(baseline_factors), scenario, None, True,
                 f"référence | {_scenario_label(scenario)}")
        for name, values in sweep_points.items():
            for value in values:
                factors = dict(baseline_factors)
                factors[name] = value
                register(
                    factors,
                    scenario,
                    (name, value),
                    False,
                    f"{name}={value} | {_scenario_label(scenario)}",
                )

    ordered = sorted(configs.items(), key=lambda item: (not item[1]["is_baseline"], item[1]["order"]))

    runs: list[RunSpec] = []
    for seed in seeds:
        for key, entry in ordered:
            runs.append(
                RunSpec(
                    config_key=key,
                    label=entry["label"],
                    factors=dict(entry["factors"]),
                    scenario=dict(entry["scenario"]),
                    budget_seconds=budget,
                    seed=int(seed),
                    memberships=tuple(entry["memberships"]),
                    is_baseline=entry["is_baseline"],
                )
            )

    return Campaign(
        name=str(spec.get("name") or "campagne"),
        baseline_factors=baseline_factors,
        scenario_variants=variants,
        budget_seconds=budget,
        seeds=[int(s) for s in seeds],
        runs=runs,
        sweep_points=sweep_points,
    )


def _check_factor(name: Any, available: dict[str, Any]) -> None:
    """
    Refuse un facteur inconnu, ou connu mais non branché sur `Config`.

    Le second cas est celui du coût fixe par véhicule : il existe dans le modèle
    (`routing.SetFixedCostOfAllVehicles(50)`, `optimizer/solver.py:561`) mais pas
    comme attribut de configuration. Le balayer reviendrait à faire varier une
    valeur que le solveur n'ira jamais lire, et à publier une courbe de réponse
    plate qui ressemblerait à une absence d'effet. Mieux vaut échouer bruyamment.

    :param name: Nom du facteur
    :param available: Facteurs effectivement portés par `Config`
    :raises GridError: facteur inconnu ou non branché
    """
    if not isinstance(name, str) or not name:
        raise GridError(f"Nom de facteur invalide : {name!r}")
    if name in available:
        return
    if name == "VEHICLE_FIXED_COST_METERS":
        raise GridError(
            "Le coût fixe par véhicule n'est plus porté par Config. S'il a été "
            "remis en dur dans optimizer/solver.py (SetFixedCostOfAllVehicles), "
            "le balayer ferait varier une valeur que le solveur n'ira jamais "
            "lire, et produirait une courbe plate qu'on lirait comme « aucun "
            "effet ». Le harnais refuse de mesurer un bouton débranché."
        )
    if name in KNOWN_FACTORS:
        raise GridError(
            f"Le facteur {name} est déclaré connu mais absent de "
            "optimizer.config.Config : le harnais refuse de mesurer un bouton "
            "débranché. Vérifier que Config porte bien cet attribut."
        )
    raise GridError(
        f"Facteur inconnu : {name}. Connus : {sorted(KNOWN_FACTORS)}"
    )


def _sweep_values(sweep: dict[str, Any]) -> list[Any]:
    """
    Extrait les points d'un balayage, en `values` explicites ou en `log_range`.

    :param sweep: Entrée `sweeps[i]` de la spécification
    :return: Points du balayage
    :raises GridError: les deux formes sont absentes, ou présentes ensemble
    """
    has_values = "values" in sweep
    has_range = "log_range" in sweep
    if has_values == has_range:
        raise GridError(
            f"Balayage {sweep.get('factor')!r} : indiquer exactement l'un de "
            "'values' ou 'log_range'"
        )
    if has_values:
        values = sweep["values"]
        if not isinstance(values, list):
            raise GridError(f"Balayage {sweep.get('factor')!r} : 'values' doit être une liste")
        return list(values)

    spec = sweep["log_range"]
    try:
        return log_range(
            float(spec["from"]),
            float(spec["to"]),
            int(spec["points"]),
            str(spec.get("round", "int")),
        )
    except KeyError as exc:
        raise GridError(f"'log_range' incomplet : clé {exc} manquante") from None


def filter_pending(runs: Iterable[RunSpec], done: Iterable[tuple[str, int]]) -> list[RunSpec]:
    """
    Retire les exécutions déjà présentes dans le journal de résultats.

    C'est toute la logique de reprise : une exécution est identifiée par
    `(config_key, seed)`, et `config_key` est une empreinte du contenu de la
    configuration. Changer une valeur de la grille change la clé, donc rien
    n'est repris à tort ; réordonner le fichier ne la change pas, donc rien
    n'est réexécuté inutilement.

    :param runs: Exécutions planifiées
    :param done: Couples `(config_key, seed)` déjà journalisés
    :return: Exécutions restant à faire, dans l'ordre d'origine
    """
    already = set(done)
    return [run for run in runs if run.resume_key not in already]
