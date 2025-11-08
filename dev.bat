@echo off
REM Fichier pour ouvrir un terminal de développement avec l'environnement activé

echo ======================================
echo   Ouverture du terminal de développement
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
)

REM Ouvrir PowerShell avec l'environnement activé
echo [+] Ouverture du terminal PowerShell...
echo [+] L'environnement virtuel sera activé automatiquement
echo.
powershell -NoExit -Command "& {Set-Location $pwd; & './venv/Scripts/Activate.ps1'; Write-Host 'Environnement virtuel activé' -ForegroundColor Green}"
