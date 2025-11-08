# Commandes disponibles

## 🚀 Démarrage rapide

### `start.bat`
Lance le projet directement:
- Crée l'environnement virtuel s'il n'existe pas
- Installe les dépendances
- Exécute le projet `optimizer/main.py`

```bash
start.bat
```

### `dev.bat`
Ouvre un terminal PowerShell avec l'environnement virtuel activé pour le développement:
- Crée l'environnement virtuel s'il n'existe pas
- Installe les dépendances
- Active le venv et ouvre un terminal prêt à développer

```bash
dev.bat
```

## 📋 Commandes manuelles

### Activer l'environnement virtuel
```bash
venv\Scripts\activate
```

### Lancer le projet
```bash
python optimizer/main.py
```

### Lancer les tests
```bash
python -m pytest optimizer/tests/ -v
```

### Générer des données de test
```bash
python optimizer/create_toy_data.py
```

### Analyser les performances
```bash
python optimizer/stats.py
```

### Créer une visualisation
```bash
python optimizer/print_solution.py
```

## 📦 Installer de nouvelles dépendances

Avec l'environnement activé:
```bash
pip install <nom_du_package>
```

## 🔍 Lister les packages installés
```bash
pip list
```

## 🧹 Désactiver l'environnement virtuel
```bash
deactivate
```
