# 🚂 Déploiement sur Railway

## 📋 Vue d'ensemble

Cette application est **100% Dockerisée** et utilise **la même configuration** en local et sur Railway. Le `Dockerfile` construit automatiquement le frontend et le backend dans une seule image, simpliant grandement le déploiement.

---

## ✅ Configuration Actuelle

### Architecture
```
┌─────────────────────────────────────┐
│         Dockerfile (Production)     │
├─────────────────────────────────────┤
│ Stage 1: Build Frontend             │
│  - Node.js 22-alpine                │
│  - npm ci && npm run build          │
│  - Output: frontend/dist/           │
├─────────────────────────────────────┤
│ Stage 2: Backend + Frontend Built   │
│  - Python 3.12-slim                 │
│  - Copie frontend/dist/             │
│  - Lance uvicorn sur $PORT          │
└─────────────────────────────────────┘
```

### Fonctionnement
- **Frontend** : Compilé lors du build Docker (Vite)
- **Backend** : Sert le frontend compilé + API
- **Port** : Unique (défini par `$PORT` sur Railway)
- **URLs** :
  - Frontend : `https://votre-app.railway.app/`
  - API : `https://votre-app.railway.app/v1/*`
  - Docs : `https://votre-app.railway.app/docs`

---

## 🔧 Configuration Railway

### 1. Créer un Nouveau Projet

1. Connectez-vous sur [Railway.app](https://railway.app)
2. Cliquez sur **"New Project"**
3. Sélectionnez **"Deploy from GitHub repo"**
4. Choisissez votre repository `saas_prospection`

### 2. Ajouter PostgreSQL

1. Dans le projet Railway, cliquez sur **"New"** → **"Database"** → **"Add PostgreSQL"**
2. Railway créera automatiquement la base de données
3. Notez que Railway génère automatiquement `DATABASE_URL`

### 3. Ajouter Redis

1. Dans le projet Railway, cliquez sur **"New"** → **"Database"** → **"Add Redis"**
2. Railway créera automatiquement Redis
3. Notez que Railway génère automatiquement `REDIS_URL`

### 4. Configurer les Variables d'Environnement

Dans les **Settings** → **Variables** de votre service applicatif, ajoutez :

```bash
# App Configuration
APP_ENV=production
DEBUG=false
SECRET_KEY=<générer-une-clé-secrète-forte>

# Database (automatique si PostgreSQL ajouté)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Redis (automatique si Redis ajouté)
REDIS_URL=${{Redis.REDIS_URL}}

# CORS (votre domaine Railway)
CORS_ORIGINS=https://votre-app.railway.app,https://www.votre-domaine.com

# Email (si nécessaire)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=votre-email@gmail.com
SMTP_PASSWORD=votre-mot-de-passe-app

# APIs externes
BRAVE_API_KEY=votre-clé-brave
OPENAI_API_KEY=votre-clé-openai
ZILLIZ_CLUSTER_URL=votre-url-zilliz
MILVUS_TOKEN=votre-token-milvus
```

### 5. Configuration du Build

Railway détecte automatiquement le `Dockerfile`. Si ce n'est pas le cas :

1. Allez dans **Settings** → **Build**
2. **Builder** : `Dockerfile`
3. **Dockerfile Path** : `Dockerfile` (à la racine)
4. **Root Directory** : `/` (racine du projet)

### 6. Configuration du Déploiement

1. **Settings** → **Deploy**
2. **Start Command** : Laissez vide (utilise `CMD` du Dockerfile)
3. **Health Check** : `/docs` (vérifie que l'API répond)
4. **Auto Deploy** : Activé (déploie automatiquement sur push)

---

## 🔍 Vérifications Avant Déploiement

### ✅ Checklist Locale

Avant de déployer, vérifiez en local :

```bash
# 1. Arrêter les services
./stop.sh

# 2. Démarrer en mode production
./start.sh

# 3. Tester l'application
curl http://localhost:8000/            # Frontend (doit retourner HTML)
curl http://localhost:8000/docs        # API Docs (doit retourner 200)
curl http://localhost:8000/health      # Health check

# 4. Vérifier les logs
docker compose logs app
```

### ✅ Structure des Fichiers

Assurez-vous que ces fichiers existent :

```
saas_prospection/
├── Dockerfile                    # ✅ Dockerfile de production
├── docker-compose.yml            # ✅ Pour dev local
├── .env.docker                   # ✅ Variables locales
├── requirements.txt              # ✅ Dépendances Python
├── alembic.ini                   # ✅ Configuration migrations
├── src/                          # ✅ Code backend
│   └── api/main.py              # ✅ Point d'entrée FastAPI
├── frontend/                     # ✅ Code frontend
│   ├── package.json             # ✅ Dépendances Node
│   ├── vite.config.ts           # ✅ Config Vite
│   └── src/                     # ✅ Sources React
└── migrations/                   # ✅ Migrations Alembic
```

---

## 🚀 Processus de Déploiement

### 1. Push sur GitHub

```bash
git add .
git commit -m "feat: Ready for Railway deployment"
git push origin main
```

### 2. Railway Build Automatique

Railway va :
1. Détecter le `Dockerfile`
2. **Stage 1** : Builder le frontend avec Node.js 22
3. **Stage 2** : Créer l'image finale avec Python + frontend compilé
4. Démarrer le conteneur
5. Exécuter les migrations Alembic (`alembic upgrade head`)
6. Lancer uvicorn

### 3. Vérification Post-Déploiement

Une fois déployé, testez :

```bash
# Frontend
curl https://votre-app.railway.app/

# API Docs
curl https://votre-app.railway.app/docs

# Health Check
curl https://votre-app.railway.app/health

# Test API
curl https://votre-app.railway.app/v1/auth/register -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}'
```

---

## 🔄 Différences Local vs Railway

| Aspect | Local (Docker) | Railway |
|--------|---------------|---------|
| **Build** | `docker compose build` | Automatique (GitHub push) |
| **Base de données** | PostgreSQL Docker | PostgreSQL Railway |
| **Redis** | Redis Docker | Redis Railway |
| **Port** | 8000 | Variable `$PORT` (auto) |
| **URL** | http://localhost:8000 | https://votre-app.railway.app |
| **Variables** | `.env.docker` | Railway UI |
| **Migrations** | Manuelles | Automatiques (dans CMD) |

### ⚠️ Important : Variables d'environnement

Railway utilise ses propres variables pour PostgreSQL et Redis :

**Local (`.env.docker`)** :
```bash
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/emailsaas
REDIS_URL=redis://redis:6379/0
```

**Railway** :
```bash
DATABASE_URL=${{Postgres.DATABASE_URL}}  # Auto-généré
REDIS_URL=${{Redis.REDIS_URL}}          # Auto-généré
```

---

## 🐛 Dépannage

### Erreur : "Port 8000 already in use"

Railway utilise `$PORT` automatiquement. Vérifiez `src/api/main.py` :

```python
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

### Erreur : "Frontend not found"

Vérifiez que le frontend est bien servi par le backend dans `src/api/main.py` :

```python
# Servir le frontend en production
if os.getenv("APP_ENV") == "production":
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
```

### Erreur : "Database connection failed"

1. Vérifiez que PostgreSQL est bien ajouté dans Railway
2. Vérifiez que `DATABASE_URL` est bien défini
3. Consultez les logs : Railway Dashboard → Logs

### Build échoue

1. Vérifiez les logs de build dans Railway
2. Testez le build localement :
   ```bash
   docker compose build
   ```
3. Vérifiez que `frontend/package.json` et `requirements.txt` sont à jour

---

## 🔧 Problèmes Résolus et Solutions

Cette section documente les problèmes rencontrés lors du déploiement et leurs solutions définitives.

### 1. Erreur : "Field required" - Variables d'environnement manquantes

**Symptôme** : Alembic crash au démarrage avec `ValidationError: 3 validation errors for Settings`

**Cause** : Les variables `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL` étaient obligatoires mais Railway ne les fournit pas avant le démarrage du container.

**Solution** : Ajout de valeurs par défaut dans `src/core/config.py` :
```python
secret_key: str = "dev-secret-key-for-migrations-only-change-in-production"
database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/emailsaas"
redis_url: str = "redis://localhost:6379/0"
```

Ces valeurs permettent à Alembic de démarrer. Railway override ces valeurs avec ses propres variables d'environnement au runtime.

**Commit** : `82beb43b`

---

### 2. Erreur : "ModuleNotFoundError: No module named 'psycopg2'"

**Symptôme** : Application crash avec erreur d'import psycopg2 même après l'avoir retiré.

**Cause** : `migrations/env.py` lisait `DATABASE_URL` directement de Railway sans conversion. Railway fournit `postgresql://...` mais SQLAlchemy async nécessite `postgresql+asyncpg://...`. Sans le suffixe `+asyncpg`, SQLAlchemy essayait d'utiliser psycopg2 (driver sync).

**Solution** : Ajout de la conversion automatique dans `migrations/env.py` :
```python
database_url = os.getenv("DATABASE_URL")
if database_url:
    # Convert postgresql:// to postgresql+asyncpg:// for Railway compatibility
    if database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    config.set_main_option("sqlalchemy.url", database_url)
```

**Dépendances** :
- ❌ Retirer `psycopg2-binary` de `requirements.txt`
- ✅ Garder uniquement `asyncpg`

**Commits** : `e8c2445e` (ajout psycopg2), `6dbada7f` (retrait), `5802a484` (fix migrations)

---

### 3. Erreur : 502 Bad Gateway

**Symptôme** : Railway renvoie 502 après le déploiement.

**Cause** : Imports manquants dans `src/api/main.py`. Le catch-all route SPA utilisait `HTTPException` et `FileResponse` sans les importer, causant un crash au démarrage.

**Solution** : Ajout des imports manquants :
```python
from fastapi import FastAPI, status, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
```

**Commit** : `0fce0dbc`

---

### 4. Erreur : "ERR_BLOCKED_BY_CLIENT" - CORS

**Symptôme** : Frontend ne peut pas contacter l'API, requêtes bloquées par CORS.

**Cause** : `CORS_ORIGINS` dans Railway ne contenait pas l'URL Railway.

**Solution** : Ajouter dans Railway Variables :
```bash
CORS_ORIGINS=https://your-app.railway.app
```

Ou pour supporter local + production :
```bash
CORS_ORIGINS=https://your-app.railway.app,http://localhost:3000,http://localhost:8000
```

---

### 5. Erreur : Frontend contacte localhost au lieu de Railway

**Symptôme** :
```
Cross-Origin Request Blocked: ... at http://localhost:8000/v1/auth/register
```

Frontend sur Railway essayait de contacter `localhost:8000`.

**Cause** : URL d'API hardcodée dans `frontend/src/services/api.ts` :
```typescript
const API_BASE_URL = 'http://localhost:8000';
```

**Solution** : Auto-détection de l'environnement :
```typescript
const API_BASE_URL = import.meta.env.VITE_API_URL ||
  (typeof window !== 'undefined' && window.location.origin.includes('railway.app')
    ? window.location.origin
    : 'http://localhost:8000');
```

**Commit** : `445a957d`

---

## 📊 Monitoring

### Logs en Temps Réel

Dans Railway Dashboard :
1. Cliquez sur votre service
2. Onglet **"Logs"**
3. Filtrez par niveau : `Info`, `Warning`, `Error`

### Métriques

Railway fournit automatiquement :
- **CPU Usage**
- **Memory Usage**
- **Network Traffic**
- **Request Count**

### Health Checks

Railway ping automatiquement `/docs` pour vérifier la santé de l'application.

---

## 🔐 Sécurité

### Secrets

- ✅ Ne **jamais** committer `.env.docker` ou secrets dans Git
- ✅ Utiliser **Railway Variables** pour les secrets
- ✅ Générer une `SECRET_KEY` forte :
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

### CORS

Configurez `CORS_ORIGINS` avec votre domaine Railway :
```bash
CORS_ORIGINS=https://votre-app.railway.app,https://www.votre-domaine.com
```

### HTTPS

Railway fournit automatiquement HTTPS avec certificat SSL.

---

## 📚 Ressources

- [Documentation Railway](https://docs.railway.app)
- [Railway Discord](https://discord.gg/railway)
- [Railway Status](https://status.railway.app)

---

## ✅ Résumé

**Votre application est déjà prête pour Railway !**

1. ✅ **Dockerfile de production** : Construit frontend + backend
2. ✅ **Configuration identique** : Local = Railway
3. ✅ **Migrations automatiques** : Via `CMD` dans Dockerfile
4. ✅ **Variables d'environnement** : Gérées via Railway UI
5. ✅ **Déploiement automatique** : Push GitHub → Déploiement

**Prochaines étapes :**
1. Push votre code sur GitHub
2. Créez un projet Railway
3. Ajoutez PostgreSQL + Redis
4. Configurez les variables d'environnement
5. Déployez ! 🚀

---

**Dernière mise à jour** : 2 novembre 2024
