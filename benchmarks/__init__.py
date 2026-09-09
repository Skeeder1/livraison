"""
Banc d'essai du solveur contre les meilleures solutions connues publiées.

Ce paquet ne modifie rien sous `optimizer/`. Il traduit une instance Solomon
(1987) vers le format de jeu de données que `optimizer.data_loader` sait relire,
appelle `optimizer.solver.solve_vrp`, puis recontrôle le résultat avec sa propre
arithmétique — sans faire confiance à ce que le solveur annonce.

Modules :

``solomon``
    Lecture des instances (format Solomon en colonnes, et format VRPLIB), et
    les deux conventions de distance en usage dans la littérature.
``bks``
    Registre des meilleures solutions connues, avec leur source et l'objectif
    exact auquel elles se rapportent.
``verifier``
    Contrôle de faisabilité indépendant, en arithmétique Solomon exacte.
``convert``
    Écriture des six fichiers attendus par `optimizer.data_loader`.
``runner``
    Exécution d'une résolution dans un sous-processus isolé.
``run_benchmark``
    Programme : lance la campagne et écrit le tableau d'écarts.
"""
