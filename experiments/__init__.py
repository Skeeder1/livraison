"""
Harnais de calibration expérimentale du solveur.

Ce paquet met en œuvre le protocole décrit au §6 du document de conception
`docs/superpowers/specs/2026-09-09-refonte-livraison-design.md` : mesurer les
pénalités et coefficients du solveur au lieu de les deviner.

Il ne modifie rien dans `optimizer/`. Il l'importe, le pilote depuis des
processus isolés, et écrit ses observations dans un fichier JSONL.

Modules
-------
`criterion`
    Le critère externe d'évaluation, fixé à l'avance et jamais réajusté.
`grid`
    Lecture et développement d'une spécification de campagne (JSON).
`store`
    Journal JSONL append-only et logique de reprise.
`runner`
    Exécution d'une configuration sur une graine, dans un processus dédié.
`run`
    Pilote de campagne en ligne de commande.
`analyse`
    Rapport texte : courbes de réponse, comparaisons appariées, recommandation.
`determinism`
    Sonde empirique de déterminisme de `solve_scenario`.
`validate`
    Auto-validation du harnais sur une dégénérescence déjà connue.
"""

__all__ = [
    "criterion",
    "grid",
    "store",
    "runner",
]
