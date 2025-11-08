# 🐳 Guide d'utilisation Docker

Ce document explique comment utiliser les scripts `start.sh` et `stop.sh` avec Docker.

## 📋 Prérequis

- **Docker** installé et actif
- **Docker Compose** installé
- **Sudo** access (pour arrêter les services locaux si nécessaire)

## 🚀 Démarrage rapide

### Première utilisation

```bash
# Arrêter les services locaux (si nécessaire)
sudo systemctl stop redis-server
sudo systemctl stop postgresql

# Lancer l'application
./start.sh
```

Le script va automatiquement :
1. ✅ Vérifier Docker
2. ✅ Détecter et arrêter les services locaux en conflit
3. ✅ Construire l'image Docker (3-5 min la première fois)
4. ✅ Lancer PostgreSQL, Redis et l'application
5. ✅ Vérifier les health checks

### Utilisations suivantes

```bash
./start.sh  # Démarrage instantané (utilise le cache Docker)
```

## 🛑 Arrêt de l'application

```bash
./stop.sh
```

Le script va :
- Arrêter tous les conteneurs Docker
- Vérifier que les ports sont libérés
- Afficher un résumé

## 🌐 URLs disponibles

Une fois démarrée, l'application est accessible sur :

- **Application complète** : http://localhost:8000
- **Documentation API** : http://localhost:8000/docs
- **Frontend** : http://localhost:8000/index.html

## 🔧 Commandes utiles

### Voir les logs en temps réel

```bash
# Tous les services
docker compose logs -f

# Application seulement
docker compose logs -f app

# PostgreSQL seulement
docker compose logs -f postgres

# Redis seulement
docker compose logs -f redis
```

### Vérifier l'état des services

```bash
docker compose ps
```

### Redémarrer un service spécifique

```bash
# Redémarrer l'application
docker compose restart app

# Redémarrer PostgreSQL
docker compose restart postgres
```

### Reconstruire l'image

Si vous avez modifié le code et voulez reconstruire :

```bash
docker compose build app
docker compose up -d
```

ou simplement relancer `./start.sh`

### Accéder au shell du conteneur

```bash
# Application
docker exec -it emailsaas-app bash

# PostgreSQL
docker exec -it emailsaas-postgres psql -U postgres -d emailsaas

# Redis
docker exec -it emailsaas-redis redis-cli
```

## ⚠️ Problèmes courants

### Port déjà utilisé (Redis ou PostgreSQL)

**Problème** : `Error: address already in use`

**Solution** :
```bash
# Arrêter Redis local
sudo systemctl stop redis-server

# Arrêter PostgreSQL local
sudo systemctl stop postgresql

# Relancer
./start.sh
```

### L'image ne se reconstruit pas

**Problème** : Les changements de code ne sont pas pris en compte

**Solution** :
```bash
# Forcer la reconstruction
docker compose build --no-cache app
docker compose up -d
```

### Nettoyer complètement

**Attention** : Cela supprime TOUTES les données (base de données incluse)

```bash
# Arrêter et supprimer tout
docker compose down -v

# Supprimer l'image
docker rmi saas_prospection-app

# Redémarrer from scratch
./start.sh
```

### Migrations Alembic échouent

Si vous avez une erreur de migration au démarrage :

```bash
# Arrêter l'application
./stop.sh

# Réinitialiser la base de données
docker compose down -v

# Relancer (va recréer la DB et appliquer les migrations)
./start.sh
```

## 🔄 Workflow de développement

### Développement Frontend

Le frontend est construit **une seule fois** lors du build Docker. Si vous modifiez le frontend :

```bash
# Option 1 : Reconstruire l'image complète
./start.sh

# Option 2 : Développement local (sans Docker)
cd frontend
npm run dev  # Lance Vite en mode dev sur port 5173
```

### Développement Backend

Le backend est dans le conteneur. Pour voir les changements :

1. **Modifier le code** dans `src/`
2. **Reconstruire** : `./start.sh`
3. **Vérifier** : `docker compose logs -f app`

### Développement avec hot-reload (optionnel)

Si vous voulez le hot-reload pendant le développement, modifiez `docker-compose.yml` :

```yaml
app:
  volumes:
    - ./src:/app/src  # Monte le code source
    - ./frontend:/app/frontend
  command: uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

## 📊 Architecture Docker

```
┌─────────────────────────────────────────┐
│         docker-compose.yml              │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────┐  ┌──────────┐           │
│  │ postgres │  │  redis   │           │
│  │  :5432   │  │  :6379   │           │
│  └────┬─────┘  └─────┬────┘           │
│       │              │                 │
│       └──────┬───────┘                 │
│              │                         │
│         ┌────▼─────┐                   │
│         │   app    │                   │
│         │  :8000   │                   │
│         │          │                   │
│         │ backend  │                   │
│         │ frontend │                   │
│         └──────────┘                   │
│                                         │
└─────────────────────────────────────────┘
```

## 🆚 Comparaison : Avant vs Après

### Avant (scripts classiques)

```bash
./start.sh
# → Crée venv Python
# → Install pip dependencies (2-3 min)
# → Install npm dependencies (2-3 min)
# → Lance PostgreSQL Docker
# → Lance backend Python local
# → Lance frontend npm local
# ⏱️  Total : 5-10 minutes à chaque démarrage
```

### Après (scripts Docker)

```bash
./start.sh
# → Build image Docker (3-5 min PREMIÈRE FOIS seulement)
# → Lance tous les services
# ⏱️  Première fois : 3-5 minutes
# ⏱️  Après : 10-15 secondes
```

## 🎯 Avantages de Docker

1. **Cohérence** : Même environnement partout (dev, staging, prod)
2. **Isolation** : Pas de conflits avec services système
3. **Rapidité** : Cache Docker = démarrage ultra-rapide
4. **Simplicité** : Un seul commande pour tout
5. **Production-ready** : Même config qu'en production

## 📝 Notes

- Les **données PostgreSQL** sont persistées dans un volume Docker
- Les **anciens scripts** sont sauvegardés en `*.backup`
- Les **logs** sont accessibles via `docker compose logs`
- Le **hot-reload** n'est pas activé par défaut (rebuild requis)

## 🔗 Liens utiles

- [Documentation Docker](https://docs.docker.com/)
- [Documentation Docker Compose](https://docs.docker.com/compose/)
- [CLOUD.md](./CLOUD.md) - Documentation principale du projet
