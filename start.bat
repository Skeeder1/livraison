@echo off
REM Fichier de démarrage du projet optimiseur de routage

echo ======================================
echo   Démarrage du projet optimisation VRP
echo ======================================
echo.

REM Vérifier si l'environnement virtuel existe
if not exist "venv" (
    echo [!] Environnement virtuel non trouvé. Création en cours...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo [+] Installation des dépendances...
    pip install ortools pandas numpy matplotlib seaborn colorama pytest folium
    echo [+] Dépendances installées avec succès
    echo.
) else (
    echo [+] Environnement virtuel détecté
)

REM Activer l'environnement virtuel
echo [+] Activation de l'environnement virtuel...
call venv\Scripts\activate.bat

REM Lancer le projet
echo [+] Lancement du projet...
echo.
python optimizer/main.py

REM Garder la fenêtre ouverte en cas d'erreur
if %ERRORLEVEL% neq 0 (
    echo.
    echo [!] Une erreur s'est produite. Appuyez sur une touche pour quitter...
    pause
)
