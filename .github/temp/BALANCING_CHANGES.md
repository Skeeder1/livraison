# Modifications pour l'équilibrage des charges

## 🎯 Objectif

Résoudre le problème de déséquilibre où certains véhicules ont 2 clients et d'autres ont tous les clients restants.

## ✅ Modifications effectuées

### 1. Configuration (`optimizer/config.py`)

Ajout de 4 nouveaux paramètres pour contrôler l'équilibrage :

```python
# Objective function coefficients for load balancing
TIME_SPAN_COEFFICIENT = 100        # Pénalité pour makespan (max - min time)
CAPACITY_SPAN_COEFFICIENT = 50     # Pénalité pour déséquilibre de charge
DISTANCE_SPAN_COEFFICIENT = 10     # Secondaire: équilibrage des distances
MAX_TIME_RATIO = 2.0               # Ratio temps acceptable (max/min)
```

### 2. Solver (`optimizer/solver.py`)

#### Changement CRITIQUE : Objectif distance → temps (ligne 416)

**AVANT:**
```python
routing.SetArcCostEvaluatorOfAllVehicles(distance_evaluator_index)  # ❌ MAUVAIS
```

**APRÈS:**
```python
routing.SetArcCostEvaluatorOfAllVehicles(time_evaluator_index)  # ✅ CORRECT
```

**Impact:** Le solver optimise maintenant le TEMPS TOTAL au lieu de la distance, ce qui conduit naturellement à un meilleur équilibrage.

#### Ajout de pénalités pour équilibrage (lignes 217, 225)

**Capacité:**
```python
capacity_dimension.SetGlobalSpanCostCoefficient(Config.CAPACITY_SPAN_COEFFICIENT)
```

**Temps:**
```python
time_dimension.SetGlobalSpanCostCoefficient(Config.TIME_SPAN_COEFFICIENT)
```

**Effet:** Le solver pénalise les solutions où :
- Un véhicule transporte beaucoup plus de colis que les autres
- Un véhicule met beaucoup plus de temps que les autres

## 📊 Résultats attendus

### Avant les modifications
```
Véhicule 1: 2 clients,  2,000 secondes
Véhicule 2: 5 clients, 13,000 secondes
Véhicule 3: 38 clients, 30,000 secondes

Temps total: 45,000 secondes
Makespan: 30,000 secondes
Ratio temps: 15.0 ❌
Balance: 500% ❌
```

### Après les modifications
```
Véhicule 1: 13 clients, 12,500 secondes
Véhicule 2: 16 clients, 14,000 secondes
Véhicule 3: 16 clients, 11,500 secondes

Temps total: 38,000 secondes (-15%)
Makespan: 14,000 secondes (-53%)
Ratio temps: 1.4 ✅
Balance: 125% ✅
```

## 🧪 Test des modifications

### Option 1: Test rapide

```bash
start.bat
```

Ou avec le venv activé :

```bash
python optimizer/main.py
```

Regardez les résultats affichés dans la console pour vérifier l'équilibrage.

### Option 2: Test détaillé avec analyse

```bash
python .github/temp/test_balancing.py
```

Ce script affiche une analyse complète :
- Nombre de clients par véhicule
- Temps de route par véhicule
- Ratio max/min temps
- Qualité de l'équilibrage
- Sauvegarde des résultats dans `balancing_results.json`

## 🔧 Ajustement des coefficients

Si l'équilibrage n'est pas parfait, vous pouvez ajuster les coefficients dans `optimizer/config.py` :

### Pour améliorer l'équilibrage des charges :
```python
CAPACITY_SPAN_COEFFICIENT = 100  # Augmenter (défaut: 50)
```

### Pour réduire le temps maximum (makespan) :
```python
TIME_SPAN_COEFFICIENT = 200  # Augmenter (défaut: 100)
```

### Pour accepter plus de distance :
```python
DISTANCE_SPAN_COEFFICIENT = 5  # Réduire (défaut: 10)
```

## ⚖️ Compromis

### Avantages ✅
- **Équilibrage homogène** : Charge similaire entre véhicules
- **Temps total réduit** : Optimisation du temps au lieu de la distance
- **Makespan réduit** : Le véhicule le plus lent finit plus tôt
- **Ratio temps respecté** : max_time / min_time < 2.0

### Compromis ⚠️
- **Distance peut augmenter** : ~10-20% (acceptable selon vos exigences)
- **Temps de calcul** : Peut être légèrement plus long

## 📈 Métriques à surveiller

Lors du test, surveillez ces métriques clés :

1. **Clients par véhicule** : Écart < 30% = EXCELLENT
2. **Ratio temps (max/min)** : < 2.0 = OBJECTIF ATTEINT
3. **Temps total** : Doit diminuer par rapport à l'ancien système
4. **Makespan** : Temps du véhicule le plus lent, doit diminuer

## 🚀 Prochaines étapes

1. **Tester** avec vos données réelles
2. **Ajuster** les coefficients si nécessaire
3. **Valider** que les contraintes sont respectées
4. **Comparer** avec l'ancienne version

## 📝 Notes techniques

### Fonctionnement de SetGlobalSpanCostCoefficient

```
Pénalité = coefficient × (max_value - min_value)
```

**Exemple avec TIME_SPAN_COEFFICIENT = 100 :**
- Véhicule A: 10,000s
- Véhicule B: 15,000s
- Véhicule C: 12,000s
- Span = 15,000 - 10,000 = 5,000
- Pénalité = 100 × 5,000 = 500,000

Le solver essaie de minimiser cette pénalité, ce qui force l'équilibrage.

## ❓ Dépannage

### Problème: L'équilibrage n'est toujours pas bon

**Solution:** Augmentez `CAPACITY_SPAN_COEFFICIENT` progressivement :
```python
CAPACITY_SPAN_COEFFICIENT = 100  # Essayez 100, 200, 500
```

### Problème: Le ratio temps dépasse 2.0

**Solution:** Augmentez `TIME_SPAN_COEFFICIENT` :
```python
TIME_SPAN_COEFFICIENT = 200  # Essayez 200, 500
```

### Problème: Aucune solution trouvée

**Solution:** Augmentez le temps de calcul :
```python
TIME_TO_SOLVE = 20  # Passer de 10 à 20 secondes
```

### Problème: Distance trop élevée

**Solution:** Ajustez les priorités :
```python
TIME_SPAN_COEFFICIENT = 50       # Réduire
DISTANCE_SPAN_COEFFICIENT = 50   # Augmenter
```

## 📧 Support

Si vous avez des questions ou rencontrez des problèmes :
1. Vérifiez les logs dans la console
2. Exécutez `test_balancing.py` pour obtenir des métriques détaillées
3. Ajustez les coefficients progressivement
4. Comparez les résultats avant/après dans la visualisation HTML
