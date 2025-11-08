# Email SaaS Platform 📧

> **Plateforme multi-tenant pour l'envoi d'emails via vos propres comptes (Gmail, Outlook, SMTP)**  
> Approche "Bring Your Own Email Provider" (BYOEP) avec API unifiée et campagnes automatisées

[![Status](https://img.shields.io/badge/status-operational-success)](https://github.com/Skeeder1/saas_prospection)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org)
[![PostgreSQL](https://img.shields.io/badge/postgresql-18-blue)](https://www.postgresql.org)
[![React](https://img.shields.io/badge/react-18-blue)](https://react.dev)

---

## 🚀 Quick Start

### Démarrage rapide (Windows)

```powershell
# Démarrer l'application complète
.\start.ps1

# Arrêter l'application
.\stop.ps1
```

**URLs après démarrage** :
- Frontend : http://localhost:8000 (production Docker)
- Backend API : http://localhost:8000/v1
- Documentation : http://localhost:8000/docs

### Première installation

1. **Prérequis** : Docker + Docker Compose
2. **Configuration** : Copier `.env.docker.example` → `.env.docker`
3. **Démarrer** : `./start.sh` (Linux/Mac) ou via Docker Compose
4. **Arrêter** : `./stop.sh`

### Déploiement Cloud (Railway)

L'application est **production-ready** pour Railway :
- ✅ Configuration unique pour local et cloud
- ✅ Migrations automatiques au démarrage
- ✅ Frontend et backend servis depuis la même origine
- ✅ Documentation complète : [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md)

---

## 🆕 Mises à Jour Récentes (Novembre 2025)

### Corrections Majeures du Déploiement Railway

**Problème 1** : Variables d'environnement requises
- ✅ **Solution** : Valeurs par défaut ajoutées dans `src/core/config.py`
- Commit : `82beb43b`

**Problème 2** : Erreur psycopg2 avec asyncpg
- ✅ **Solution** : Conversion automatique DATABASE_URL dans `migrations/env.py`
- Railway fournit `postgresql://` → converti en `postgresql+asyncpg://`
- Commits : `5802a484`, `6dbada7f`

**Problème 3** : 502 Bad Gateway
- ✅ **Solution** : Imports manquants (HTTPException, FileResponse) ajoutés
- Commit : `0fce0dbc`

**Problème 4** : CORS bloqué
- ✅ **Solution** : Configuration CORS_ORIGINS dans Railway Variables

**Problème 5** : Frontend contacte localhost
- ✅ **Solution** : Auto-détection de l'API URL dans `frontend/src/services/api.ts`
- Détecte automatiquement Railway vs local
- Commit : `445a957d`

**Résultat** : Application **100% fonctionnelle** sur Railway avec la même configuration qu'en local.

---

## ✨ Fonctionnalités principales

### Backend (FastAPI)
- ✅ **Multi-tenant** avec isolation complète
- ✅ **Providers multiples** : Gmail (OAuth2), Outlook (OAuth2), SMTP générique
- ✅ **Auto-sélection** intelligente des comptes selon quota et santé
- ✅ **Rate limiting** par tenant et par compte
- ✅ **Historique complet** avec filtres et recherche
- ✅ **Webhooks** pour notifications temps réel
- ✅ **Token refresh** automatique OAuth

### Frontend (React)
- ✅ Dashboard moderne avec statistiques temps réel
- ✅ Gestion complète des comptes email
- ✅ Envoi simple et par batch
- ✅ Tracking quota avec alertes
- ✅ Design responsive (TailwindCSS + Lucide Icons)

### 🎯 Feature unique : Campagne Mairie
- ✅ **Géocodage automatique** des villes françaises
- ✅ **Recherche géographique** dans un rayon donné (algorithme Haversine)
- ✅ **Récupération automatique** des emails officiels des mairies
- ✅ **APIs gouvernementales** : geo.api.gouv.fr + etablissements-publics.api.gouv.fr
- ✅ **Métadonnées enrichies** : population, distance, téléphone, site web

**Exemple validé** : Recherche "Angers 25km" → 5 mairies avec emails récupérés automatiquement

---

## 🏗️ Architecture

### Stack technique

**Backend**
- Framework : **FastAPI** (Python 3.10+)
- Base de données : **PostgreSQL 18** (asyncpg)
- ORM : **SQLAlchemy** (async)
- Migrations : **Alembic**
- Auth : **JWT** + bcrypt
- Cache : **Redis** 7+

**Frontend**
- Framework : **React 18** + TypeScript
- Build : **Vite**
- Routing : **React Router v6**
- Styling : **TailwindCSS**
- State : **React Query** + Context API
- Forms : **React Hook Form** + Zod

**Environnement (Windows)**
- OS : Windows 11 (PowerShell 5.1)
- PostgreSQL : Installé localement (**PAS Docker**)
- Redis : Installé localement

---

## 📚 Documentation

### For Users & Developers
Pour la documentation complète, consultez :

- **[docs/](docs/)** - 📖 Documentation Hub (organized by topic)
  - [Getting Started Guide](docs/guides/) - Installation et démarrage
  - [Architecture](docs/architecture/) - Aperçu du système
  - [MCP & Automation](docs/mcp/) - Guides d'automatisation

- **[.github/DOCUMENTATION.md](.github/DOCUMENTATION.md)** - Documentation technique exhaustive
  - Architecture détaillée
  - Configuration complète
  - Guide des APIs
  - Troubleshooting
  - Scripts PowerShell
  - Base de données

- **[.github/copilot-instructions.md](.github/copilot-instructions.md)** - Instructions GitHub Copilot
  - Règles critiques
  - Configuration PostgreSQL
  - Scripts de démarrage
  - Problèmes courants

- **[frontend/README.md](frontend/README.md)** - Documentation frontend React

### For Claude AI Development
Guide for autonomous Claude Code development:

- **[.github/claude/INSTRUCTIONS.md](.github/claude/INSTRUCTIONS.md)** - Core development guidelines
- **[.github/claude/WORKFLOW_RULES.md](.github/claude/WORKFLOW_RULES.md)** - Code standards and conventions
- **[.github/claude/KNOWLEDGE_BASE.md](.github/claude/KNOWLEDGE_BASE.md)** - Living project knowledge base
- **[.github/claude/MCP_AUTOMATION.md](.github/claude/MCP_AUTOMATION.md)** - MCP tool integration guide

### Contributing
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contribution guidelines
- **[CHANGELOG.md](CHANGELOG.md)** - Version history

---

## 🔧 Configuration

### Variables d'environnement (`.env`)

```env
# Application
SECRET_KEY=your-super-secret-key-change-in-production

# Database (TOUJOURS utiliser ces identifiants)
DATABASE_URL=postgresql+asyncpg://emailsaas_user:emailsaas_pass@localhost:5432/emailsaas

# Redis
REDIS_URL=redis://localhost:6379/0

# CORS (inclure port 5173 pour Vite)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8000

# OAuth Google/Microsoft (optionnel)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
MICROSOFT_CLIENT_ID=your-microsoft-client-id
MICROSOFT_CLIENT_SECRET=your-microsoft-client-secret
```

---

## 📡 API Endpoints

### Authentification
- `POST /v1/auth/register` - Créer un compte
- `POST /v1/auth/login` - Se connecter
- `GET /v1/auth/me` - Infos utilisateur

### Campagnes Mairie
- `GET /v1/campaigns` - Liste des campagnes
- `POST /v1/campaigns` - Créer une campagne
  ```json
  {
    "name": "Campagne Angers",
    "city_name": "Angers",
    "radius_km": 25,
    "limit": 5
  }
  ```
- `GET /v1/campaigns/{id}/recipients` - Liste des destinataires

### Email
- `POST /v1/emails/send` - Envoyer un email
- `POST /v1/emails/batch` - Envoyer un batch
- `GET /v1/emails/logs` - Historique

**Documentation interactive** : http://localhost:8000/docs

---

## 🧪 Tests

```bash
# Backend
pytest
pytest tests/unit/
pytest tests/integration/

# Frontend
cd frontend && npm test
```

**Tests validés (29 oct 2025)** :
- ✅ Health Check
- ✅ CORS Verification
- ✅ User Registration
- ✅ Create Campaign (Angers 25km → 5 mairies)
- ✅ Get Campaigns List
- ✅ Get Campaign Recipients

---

## 🛠️ Développement

### Commandes utiles

**Backend**
```bash
# Migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Connexion PostgreSQL
psql -U emailsaas_user -h localhost -d emailsaas
```

**Frontend**
```bash
cd frontend
npm run dev        # Dev server
npm run build      # Build production
npm run lint       # Linting
```

---

## ⚠️ Troubleshooting

### PostgreSQL ne démarre pas
```powershell
# Vérifier si PostgreSQL écoute
netstat -ano | Select-String ":5432"

# Vérifier si PostgreSQL répond
cd "C:\Program Files\PostgreSQL\18\bin"
.\pg_isready.exe -h localhost -p 5432
```

### CORS bloqué
```powershell
# Vérifier .env
cat .env | Select-String "CORS_ORIGINS"

# Redémarrer le backend
.\stop.ps1
.\start.ps1
```

**Pour plus de détails** : Consultez [.github/DOCUMENTATION.md](.github/DOCUMENTATION.md#troubleshooting)

---

## 📊 État du système

**Dernière mise à jour** : 29 octobre 2025

- ✅ PostgreSQL 18 opérationnel (dossier `C:\pgdata18`)
- ✅ Base de données `emailsaas` créée
- ✅ Migrations à jour (campaigns UUID + champs mairie)
- ✅ Backend testé (tous endpoints fonctionnels)
- ✅ Frontend opérationnel (Vite port 5173)
- ✅ CORS configuré (localhost:5173)
- ✅ Campagne Mairie 100% fonctionnelle
- ✅ Tests end-to-end validés (6/6)

---

## 🚨 Règles critiques

1. **❌ NE JAMAIS utiliser Docker** (bugs sur cet environnement Windows)
2. **✅ TOUJOURS** utiliser identifiants DB : `emailsaas_user:emailsaas_pass`
3. **✅ TOUJOURS** utiliser `postgresql+asyncpg://` (pas `postgresql://`)
4. **✅ TOUJOURS** utiliser `geo.api.gouv.fr` (PAS `geo.gouv.fr`)

---

## 🤝 Contribution

1. Fork le repository
2. Créer une branche feature (`git checkout -b feature/amazing`)
3. Commit les changements (`git commit -m 'Add amazing feature'`)
4. Push vers la branche (`git push origin feature/amazing`)
5. Ouvrir une Pull Request

**Avant de commit** :
- [ ] Tests passent (`pytest`)
- [ ] Frontend build sans erreurs (`npm run build`)
- [ ] Pas de références Docker ajoutées
- [ ] Identifiants DB cohérents

---

## 📄 License

MIT License - voir fichier LICENSE pour détails

---

## 🔗 Ressources

- **Documentation complète** : [.github/DOCUMENTATION.md](.github/DOCUMENTATION.md)
- **Instructions Copilot** : [.github/copilot-instructions.md](.github/copilot-instructions.md)
- **API Docs** : http://localhost:8000/docs (après démarrage)
- **Health Check** : http://localhost:8000/health
- **Metrics** : http://localhost:8000/metrics

---

**Built with ❤️ using FastAPI, React, and PostgreSQL**
