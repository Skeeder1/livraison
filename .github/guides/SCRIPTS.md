# 📜 Guide des Scripts - Email SaaS Platform

Ce document décrit tous les scripts disponibles pour gérer l'application.

---

## 🚀 Scripts Principaux

### `start.sh` - Démarrer l'application

Démarre tous les services de l'application (PostgreSQL, Backend, Frontend).

```bash
./start.sh
```

**Ce qu'il fait:**
1. ✅ Vérifie et démarre PostgreSQL via Docker
2. ✅ Crée/vérifie la base de données
3. ✅ Configure l'environnement virtuel Python
4. ✅ Installe les dépendances Python si nécessaire
5. ✅ Applique les migrations Alembic
6. ✅ Vérifie les dépendances frontend
7. ✅ Lance le backend (FastAPI + Uvicorn)
8. ✅ Lance le frontend (React + Vite avec Node.js 22)

**Résultat:**
- Backend disponible sur: `http://localhost:8000`
- Frontend disponible sur: `http://localhost:5173`
- API Docs: `http://localhost:8000/docs`

---

### `stop.sh` - Arrêter l'application

Arrête proprement tous les services de l'application.

```bash
./stop.sh
```

**Ce qu'il fait:**
1. ✅ Arrête le frontend (Node.js/Vite)
2. ✅ Arrête le backend (Python/Uvicorn)
3. ✅ Nettoie les ports réseau (5173, 8000)
4. ✅ Arrête le container PostgreSQL (Docker)
5. ✅ Nettoie les fichiers PID et logs temporaires

**Temps d'exécution:** ~5-15 secondes

---

### `restart.sh` - Redémarrer l'application

Redémarre complètement l'application en exécutant `stop.sh` puis `start.sh`.

```bash
./restart.sh
```

**Ce qu'il fait:**
1. ✅ Exécute `./stop.sh` pour arrêter tous les services
2. ⏳ Attend 5 secondes pour s'assurer que tout est bien arrêté
3. ✅ Exécute `./start.sh` pour redémarrer tous les services

**Utilité:**
- Appliquer des modifications de configuration
- Résoudre des problèmes de connexion
- Repartir sur une base propre

**Temps d'exécution:** ~30-60 secondes

---

## 🔧 Scripts Auxiliaires

### `frontend/start-frontend.sh` - Démarrer uniquement le frontend

Script interne utilisé par `start.sh` pour lancer le frontend avec la bonne version de Node.js.

```bash
cd frontend
./start-frontend.sh
```

**Ce qu'il fait:**
- Charge nvm (Node Version Manager)
- Active Node.js 22
- Lance Vite dev server

**⚠️ Note:** Ce script est appelé automatiquement par `start.sh`, vous n'avez généralement pas besoin de l'exécuter manuellement.

---

### `check_and_create_db.sh` - Gestion de la base de données

Script interne pour créer et configurer la base de données PostgreSQL.

```bash
./check_and_create_db.sh
```

**Ce qu'il fait:**
- Vérifie si la base `emailsaas` existe
- Crée la base si nécessaire
- Crée l'utilisateur `emailsaas_user` avec les permissions
- Configure les droits d'accès

**⚠️ Note:** Ce script est appelé automatiquement par `start.sh`.

---

## 🐳 Docker

### Démarrer uniquement PostgreSQL

```bash
docker-compose up -d
```

### Arrêter PostgreSQL

```bash
docker-compose down
```

### Réinitialiser complètement la base de données

```bash
docker-compose down -v
```

**⚠️ Attention:** Supprime toutes les données de la base!

---

## 📊 Gestion des Logs

### Consulter les logs

```bash
# Backend
tail -f .logs/backend.log

# Frontend
tail -f .logs/frontend.log

# PostgreSQL (Docker)
docker-compose logs -f
```

### Nettoyer les logs

```bash
rm -rf .logs/*.log
```

---

## 🔍 Vérifications

### Vérifier l'état des services

```bash
# Services en cours d'exécution
docker ps                    # PostgreSQL
lsof -i :8000               # Backend
lsof -i :5173               # Frontend

# Tester les endpoints
curl http://localhost:8000/          # Backend health
curl http://localhost:8000/health    # Backend detailed
curl http://localhost:5173/          # Frontend
```

### Vérifier les versions

```bash
# Node.js (doit être 22+)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
node --version

# Python
python3 --version

# PostgreSQL
docker exec emailsaas-postgres psql -U postgres -c "SELECT version();"
```

---

## 🚨 Dépannage

### Le frontend ne démarre pas

**Problème:** Node.js 18 utilisé au lieu de 22

**Solution:**
```bash
# Vérifier la version
node --version

# Charger nvm et activer Node 22
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm use 22
```

### Ports déjà utilisés

**Solution:**
```bash
# Tuer les processus sur les ports
./stop.sh

# Si ça ne marche pas, forcer:
lsof -ti :5173 | xargs kill -9
lsof -ti :8000 | xargs kill -9
docker-compose down -v
```

### Base de données corrompue

**Solution:**
```bash
# Réinitialiser complètement
./stop.sh
docker-compose down -v
./start.sh
```

### Migrations échouent

**Solution:**
```bash
# Appliquer manuellement
source venv/bin/activate
python -m alembic upgrade head
```

---

## ⚡ Raccourcis Utiles

```bash
# Démarrage rapide
./start.sh

# Redémarrage rapide
./restart.sh

# Arrêt propre
./stop.sh

# Voir les logs en direct
tail -f .logs/backend.log .logs/frontend.log

# Tester l'API
curl http://localhost:8000/health | python3 -m json.tool
```

---

## 📝 Résumé des Commandes

| Commande | Description | Durée |
|----------|-------------|-------|
| `./start.sh` | Démarre tout | ~30-60s |
| `./stop.sh` | Arrête tout | ~5-15s |
| `./restart.sh` | Redémarre tout | ~30-60s |
| `docker-compose up -d` | PostgreSQL uniquement | ~5s |
| `docker-compose down` | Arrête PostgreSQL | ~5s |

---

## 🎯 Workflow Recommandé

### Développement quotidien

```bash
# Matin
./start.sh

# Développement...
# (Le HMR recharge automatiquement les changements)

# Soir
./stop.sh
```

### Après modification des dépendances

```bash
./restart.sh
```

### Après modification de la base de données

```bash
./stop.sh
docker-compose down -v
./start.sh
```

---

**🚀 Bon développement!**
