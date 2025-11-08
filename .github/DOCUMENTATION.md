# Email SaaS Platform - Documentation Complète 📧

> **Dernière mise à jour** : 29 octobre 2025  
> **Environnement** : Windows 11, PowerShell 5.1, Python 3.10, PostgreSQL 18  
> **Status** : ✅ Système opérationnel - Campagne Mairie 100% fonctionnelle

---

## 📋 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture](#architecture)
3. [Installation et démarrage](#installation-et-démarrage)
4. [Configuration](#configuration)
5. [Développement](#développement)
6. [API et routes](#api-et-routes)
7. [Fonctionnalités avancées](#fonctionnalités-avancées)
8. [Troubleshooting](#troubleshooting)
9. [Scripts PowerShell](#scripts-powershell)
10. [Base de données](#base-de-données)

---

## Vue d'ensemble

Plateforme SaaS multi-tenant pour l'envoi d'emails via vos propres comptes email (Gmail, Outlook, SMTP). Approche **"Bring Your Own Email Provider" (BYOEP)** avec API unifiée, analytics, rate limiting et gestion automatisée des campagnes de prospection.

### Fonctionnalités principales

#### ✅ Backend (FastAPI)
- **Multi-tenant** avec isolation complète
- **Providers multiples** : Gmail (OAuth2), Outlook (OAuth2), SMTP
- **Auto-sélection** intelligente des comptes selon quota et santé
- **Rate limiting** par tenant et par compte
- **Historique complet** avec filtres et recherche
- **Webhooks** pour notifications temps réel
- **Token refresh** automatique OAuth

#### ✅ Frontend (React)
- Dashboard moderne avec statistiques temps réel
- Gestion des comptes email
- Envoi simple et par batch
- Tracking quota et alertes
- Design responsive (TailwindCSS)

#### ✅ Campagne Mairie (Feature unique)
- **Géocodage automatique** des villes françaises
- **Recherche géographique** dans un rayon donné
- **Récupération automatique** des emails officiels
- **APIs gouvernementales** : geo.api.gouv.fr + etablissements-publics
- **Métadonnées enrichies** : population, distance, téléphone, site web

---

## Architecture

### Stack technique

**Backend**
- Framework : FastAPI (Python 3.10+)
- Base de données : PostgreSQL 18 avec asyncpg
- Cache/Queue : Redis 7+ (local Windows)
- ORM : SQLAlchemy (async)
- Migrations : Alembic
- Auth : JWT + bcrypt
- Vault : Stockage sécurisé credentials (local/HashiCorp/AWS)

**Frontend**
- Framework : React 18 + TypeScript
- Build : Vite
- Routing : React Router v6
- Styling : TailwindCSS
- State : React Query + Context API
- Icons : Lucide React
- Forms : React Hook Form + Zod

**Environnement**
- OS : Windows 11 (PowerShell 5.1)
- Python : 3.10 (venv)
- Node.js : 18+
- PostgreSQL : 18 (installé localement, **PAS Docker**)
- Redis : Local Windows

### Structure du projet

```
saas_prospection/
├── .github/
│   ├── copilot-instructions.md     # Instructions GitHub Copilot
│   └── DOCUMENTATION.md             # Ce fichier
├── src/                             # Backend Python/FastAPI
│   ├── api/
│   │   ├── main.py                  # Point d'entrée API
│   │   ├── dependencies.py          # Dépendances FastAPI
│   │   ├── routes/                  # Endpoints API
│   │   └── schemas/                 # Schémas Pydantic
│   ├── core/
│   │   ├── config.py                # Configuration app
│   │   ├── database.py              # Connexion DB async
│   │   └── security.py              # Auth JWT/bcrypt
│   ├── models/                      # SQLAlchemy models
│   │   ├── tenant.py
│   │   ├── account.py
│   │   ├── campaign.py              # Campagnes (UUID)
│   │   └── email.py
│   ├── services/                    # Business logic
│   │   ├── mairie_service.py        # Recherche mairies (géo + emails)
│   │   ├── campaign_service.py      # Orchestration campagnes
│   │   ├── email_service.py
│   │   └── ...
│   ├── providers/                   # Implémentations email
│   │   ├── gmail.py
│   │   ├── outlook.py
│   │   └── smtp.py
│   └── workers/                     # Tâches background
│       ├── token_refresher.py
│       └── webhook_dispatcher.py
├── frontend/                        # React/TypeScript
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── types/
│   └── package.json
├── migrations/                      # Alembic migrations
│   ├── env.py                       # Config Alembic (timeouts!)
│   └── versions/
│       ├── 2025_10_26_1430-001_initial_schema.py
│       ├── 2025_10_28_2330-b5c9dffc31cb_add_campaigns_with_uuid.py
│       └── 2025_10_28_2338-27c8a820a2f4_add_mairie_fields_to_campaigns.py
├── tests/                           # Tests automatisés
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── .env                             # Variables d'environnement
├── alembic.ini                      # Config Alembic
├── requirements.txt                 # Dépendances Python
├── start.ps1                        # ✅ Script démarrage principal
├── stop.ps1                         # ✅ Script arrêt complet
├── check_and_create_db.ps1          # Création DB sans destruction
└── setup_postgres.bat               # Setup initial PostgreSQL
```

---

## Installation et démarrage

### ⚡ Démarrage rapide (RECOMMANDÉ)

**Prérequis** : PostgreSQL 18 installé, dossier de données `C:\pgdata18`

```powershell
# 1. Démarrer l'application complète
.\start.ps1

# Ce script fait TOUT automatiquement :
# - Démarre PostgreSQL (pg_ctl avec flag -w)
# - Crée la base de données si nécessaire (check_and_create_db.ps1)
# - Active l'environnement virtuel Python
# - Applique les migrations Alembic
# - Lance le backend (Uvicorn port 8000)
# - Lance le frontend (Vite port 5173)

# 2. Arrêter l'application complète
.\stop.ps1

# Ce script nettoie TOUT :
# - Arrête les processus Node.js/Frontend
# - Arrête les processus Python/Backend
# - Arrête PostgreSQL proprement (fast → immediate → kill)
# - Nettoie les zombies PostgreSQL
# - Libère les ports 5432, 8000, 5173
```

### URLs après démarrage

- **Frontend** : http://localhost:5173
- **Backend API** : http://localhost:8000
- **Swagger Docs** : http://localhost:8000/docs
- **ReDoc** : http://localhost:8000/redoc
- **Health Check** : http://localhost:8000/health

### Démarrage manuel (si besoin de contrôle)

#### 1. PostgreSQL

```powershell
# Démarrer PostgreSQL directement (sans droits admin)
cd "C:\Program Files\PostgreSQL\18\bin"
.\pg_ctl.exe start -D "C:\pgdata18" -l "C:\pgdata18\logfile" -w

# Vérifier que PostgreSQL répond
.\pg_isready.exe -h localhost -p 5432
```

#### 2. Base de données (première fois uniquement)

```cmd
# Créer la base et l'utilisateur
setup_postgres.bat

# Ou manuellement :
psql -U postgres -h localhost
CREATE USER emailsaas_user WITH PASSWORD 'emailsaas_pass';
CREATE DATABASE emailsaas OWNER emailsaas_user;
```

#### 3. Backend

```powershell
# Activer l'environnement virtuel
.\venv\Scripts\activate.ps1

# Installer les dépendances (première fois)
pip install -r requirements.txt

# Appliquer les migrations
alembic upgrade head

# Démarrer le serveur
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

#### 4. Frontend

```powershell
cd frontend

# Installer les dépendances (première fois)
npm install

# Démarrer le dev server
npm run dev
```

---

## Configuration

### Variables d'environnement backend (`.env`)

```env
# Application
APP_ENV=development
DEBUG=True
SECRET_KEY=your-super-secret-key-change-in-production

# Database (TOUJOURS utiliser ces identifiants)
DATABASE_URL=postgresql+asyncpg://emailsaas_user:emailsaas_pass@localhost:5432/emailsaas

# Redis
REDIS_URL=redis://localhost:6379/0

# CORS (IMPORTANT : inclure port 5173 pour Vite)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8000

# OAuth Google
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/v1/accounts/callback/gmail

# OAuth Microsoft
MICROSOFT_CLIENT_ID=your-microsoft-client-id
MICROSOFT_CLIENT_SECRET=your-microsoft-client-secret
MICROSOFT_REDIRECT_URI=http://localhost:8000/v1/accounts/callback/outlook

# Vault (local, hashicorp, aws)
VAULT_TYPE=local
VAULT_PATH=./vault_data
```

### Variables d'environnement frontend (`frontend/.env`)

```env
VITE_API_URL=http://localhost:8000
```

### Configuration PostgreSQL

**⚠️ CRITIQUE** : Identifiants standardisés

```
Host:     localhost
Port:     5432
Database: emailsaas
User:     emailsaas_user
Password: emailsaas_pass
Data Dir: C:\pgdata18
```

**Fichiers à synchroniser** :
1. `.env` → `DATABASE_URL`
2. `alembic.ini` → `sqlalchemy.url`
3. `src/core/config.py` → Settings
4. `setup_postgres.bat` → CREATE USER/DATABASE

### Configuration pg_hba.conf

**Localisation** : `C:\pgdata18\pg_hba.conf`

**Configuration requise pour localhost** :
```conf
# IPv4 local connections:
host    all             all             127.0.0.1/32            scram-sha-256

# IPv6 local connections:
host    all             all             ::1/128                 scram-sha-256
```

---

## Développement

### Commandes utiles

**Backend**
```bash
# Créer une nouvelle migration
alembic revision --autogenerate -m "description"

# Appliquer toutes les migrations
alembic upgrade head

# Rollback une migration
alembic downgrade -1

# Voir l'historique
alembic history

# Connexion PostgreSQL
psql -U emailsaas_user -h localhost -d emailsaas
# Ou avec variable d'environnement :
$env:PGPASSWORD="emailsaas_pass"; psql -U emailsaas_user -h localhost -d emailsaas
```

**Frontend**
```bash
cd frontend

# Dev server avec hot reload
npm run dev

# Build production
npm run build

# Preview build production
npm run preview

# Linting
npm run lint
```

**Tests**
```bash
# Backend
pytest
pytest tests/unit/
pytest tests/integration/
pytest -v -s  # Verbose avec output

# Frontend
cd frontend && npm test
```

### Bonnes pratiques Copilot

**Lors de la création de scripts**
- ✅ TOUJOURS ajouter des timeouts pour connexions réseau/DB
- ✅ Utiliser `Start-Job` + `Wait-Job -Timeout` dans PowerShell
- ✅ Ajouter `PGCONNECT_TIMEOUT` pour psql
- ✅ Gérer les erreurs et donner des messages clairs

**Lors de la modification de la config DB**
- ✅ Vérifier `.env`, `alembic.ini`, `src/core/config.py`
- ✅ TOUJOURS utiliser `emailsaas_user:emailsaas_pass`
- ✅ TOUJOURS utiliser `postgresql+asyncpg://` (pas juste `postgresql://`)

**Lors de l'ajout de dépendances**
- ✅ Backend : Ajouter dans `requirements.txt`
- ✅ Frontend : Ajouter avec `npm install`
- ❌ **NE JAMAIS créer de Dockerfile ou docker-compose** (Docker pose problèmes sur cet environnement Windows)

---

## API et routes

### Authentification

- `POST /v1/auth/register` - Créer un compte tenant
  ```json
  {
    "company_name": "Ma Société",
    "email": "admin@societe.com",
    "password": "mot_de_passe_securise"
  }
  ```

- `POST /v1/auth/login` - Se connecter (obtenir JWT)
  ```json
  {
    "email": "admin@societe.com",
    "password": "mot_de_passe_securise"
  }
  ```

- `GET /v1/auth/me` - Infos utilisateur connecté (requiert JWT)

### Email Accounts

- `GET /v1/accounts` - Lister les comptes email
- `POST /v1/accounts/smtp` - Ajouter compte SMTP
- `GET /v1/accounts/connect/gmail` - Initier OAuth Gmail
- `GET /v1/accounts/connect/outlook` - Initier OAuth Outlook
- `GET /v1/accounts/callback/gmail` - Callback OAuth Gmail
- `GET /v1/accounts/callback/outlook` - Callback OAuth Outlook
- `DELETE /v1/accounts/{id}` - Supprimer un compte

### Campagnes

- `GET /v1/campaigns` - Liste des campagnes
- `POST /v1/campaigns` - Créer une campagne mairie
  ```json
  {
    "name": "Campagne Angers",
    "city_name": "Angers",
    "radius_km": 25,
    "limit": 5
  }
  ```
- `GET /v1/campaigns/{id}` - Détails d'une campagne
- `GET /v1/campaigns/{id}/recipients` - Liste des destinataires

### Envoi d'emails

- `POST /v1/emails/send` - Envoyer un email simple
  ```json
  {
    "to": "destinataire@example.com",
    "subject": "Sujet du message",
    "html_body": "<h1>Bonjour!</h1><p>Message HTML.</p>"
  }
  ```

- `POST /v1/emails/batch` - Envoyer un batch d'emails
  ```json
  {
    "recipients": ["dest1@example.com", "dest2@example.com"],
    "subject": "Sujet du message",
    "html_body": "<h1>Bonjour!</h1>"
  }
  ```

- `GET /v1/emails/logs` - Logs des emails envoyés

### Usage & Stats

- `GET /v1/usage/current-month` - Usage du mois en cours
- `GET /v1/dashboard/stats` - Statistiques dashboard

### Webhooks

- `POST /v1/webhooks/configure` - Configurer webhook
- `GET /v1/webhooks/config` - Obtenir config webhook

---

## Fonctionnalités avancées

### Campagne Mairie - Documentation complète

#### Vue d'ensemble

Fonctionnalité permettant de créer automatiquement des campagnes de prospection vers les mairies françaises dans un rayon géographique donné.

#### APIs gouvernementales utilisées

```python
# ⚠️ IMPORTANT : Utiliser geo.api.gouv.fr (PAS geo.gouv.fr)
GEO_API_BASE = "https://geo.api.gouv.fr"
ETABLISSEMENTS_API = "https://etablissements-publics.api.gouv.fr"
ANNUAIRE_API = "https://api-lannuaire.service-public.fr"
```

**Erreur commune** : `geo.gouv.fr` ne résout pas en DNS → Toujours utiliser `geo.api.gouv.fr`

#### Modèles de données

**Campaign (UUID primary keys)**
```python
class Campaign(Base):
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    status = Column(SQLEnum(CampaignStatus), default=CampaignStatus.DRAFT)
    
    # Champs spécifiques mairie
    source_type = Column(String(50))         # "mairie_search"
    search_city = Column(String(255))        # Ville de recherche
    search_latitude = Column(Float)          # Latitude centre
    search_longitude = Column(Float)         # Longitude centre
    search_radius_km = Column(Float)         # Rayon en km
    search_limit = Column(Integer)           # Nombre max de résultats
```

**CampaignRecipient (UUID + métadonnées mairie)**
```python
class CampaignRecipient(Base):
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"))
    
    # Infos mairie
    commune_name = Column(String(255))
    code_insee = Column(String(10))
    email = Column(String(255))
    site_web = Column(String(500))
    telephone = Column(String(20))
    population = Column(Integer)
    distance_km = Column(Float)
    
    status = Column(SQLEnum(RecipientStatus), default=RecipientStatus.PENDING)
```

#### Services implémentés

**MairieService** (`src/services/mairie_service.py`)

```python
@staticmethod
async def geocode_city(city_name: str) -> Optional[Tuple[float, float]]:
    """
    Géocode une ville française → (latitude, longitude)
    
    API : geo.api.gouv.fr/communes?nom={city}
    Retourne GeoJSON coordinates inversées : [lon, lat] → (lat, lon)
    """

@staticmethod
async def search_mairies(lat, lon, radius_km, limit) -> List[Dict]:
    """
    Cherche mairies dans un rayon géographique
    
    Algorithme :
    1. Récupère toutes les communes par département (01-95 + DOM-TOM)
    2. Calcule distance Haversine pour chaque commune
    3. Filtre par radius_km, trie par distance
    4. Appelle get_mairie_info() pour chaque commune
    5. Retourne {commune, code_insee, email, site_web, telephone, population, distance_km}
    """

@staticmethod
async def get_mairie_info(code_insee, nom_commune) -> Dict:
    """
    Récupère email/contact de la mairie
    
    Essaie etablissements-publics.api.gouv.fr/v3/communes/{code_insee}/mairie
    Fallback sur api-lannuaire.service-public.fr si email non trouvé
    """
```

**CampaignService** (`src/services/campaign_service.py`)

```python
async def fetch_mairies(self, *, city_name, latitude, longitude, radius_km, limit) -> dict:
    """
    Fetch mairies et coordonnées du centre
    
    - Géocode city si fourni, sinon utilise lat/lon directes
    - Retourne {"results": [...], "latitude": ..., "longitude": ...}
    """
```

#### Temps de réponse (mesurés en production)

- **Géocodage ville** : ~1-2s
- **Recherche 5 communes** : ~7-11s
- **Recherche 10 communes** : ~10-15s
- **Recherche 50 communes** : ~30-60s
- **Recherche 200 communes** : ~2-5 minutes

**⚠️ Recommandation** : Limiter à 5-10 communes pour les tests, 10-50 pour la production.

#### Exemple de flux complet

```
1. Frontend → POST /v1/campaigns
   {
     "name": "Campagne Angers",
     "city_name": "Angers",
     "radius_km": 25,
     "limit": 5
   }

2. Backend geocode la ville
   → (47.4819, -0.5629)

3. Backend cherche communes dans 25km
   - Parcourt départements 01-95 + DOM-TOM
   - Calcule distance Haversine
   - Filtre + trie par distance

4. Backend récupère emails des mairies
   - API établissements-publics
   - Fallback API annuaire

5. Backend crée Campaign + CampaignRecipients
   - Status: scheduled
   - 5 destinataires avec emails réels

6. Frontend affiche la liste → Bouton "Exporter"

7. Clic "Exporter" → Redirect /send?campaignId=xxx
   - Pre-rempli avec emails des mairies
```

#### Test validé (29 octobre 2025)

**Résultats automatisés** :
```
✅ Health Check
✅ CORS Verification (localhost:5173)
✅ User Registration
✅ Create Campaign (Angers, 25km, 5 mairies trouvées)
✅ Get Campaigns List
✅ Get Campaign Recipients
```

**Mairies trouvées (Angers 25km)** :
1. Angers - mairie.angers@ville.angers.fr - 157,555 hab - 0 km
2. Avrillé - mairie@ville-avrille.fr - 15,225 hab - 3.69 km
3. Beaucouzé - maire@beaucouze.fr - 5,618 hab - 5.55 km
4. Écouflant - mairie@ecouflant.fr - 4,614 hab - 5.73 km
5. Sainte-Gemmes-sur-Loire - mairie@sainte-gemmes-sur-loire.fr - 3,617 hab - 5.84 km

#### Pièges résolus

**1. Enum vs String**
```python
# ❌ ERREUR
campaign.status = "ready"  # InvalidTextRepresentationError

# ✅ CORRECT
from src.models.campaign import CampaignStatus
campaign.status = CampaignStatus.SCHEDULED
```

**2. Pydantic v2 - Champs optionnels**
```python
# ❌ ERREUR (Pydantic v2)
class Schema(BaseModel):
    sent_at: Optional[datetime]  # Field required error!

# ✅ CORRECT
class Schema(BaseModel):
    sent_at: Optional[datetime] = None  # Valeur par défaut explicite
```

**3. URL API Géo**
```python
# ❌ ERREUR - DNS ne résout pas
GEO_API_BASE = "https://geo.gouv.fr"  # getaddrinfo failed

# ✅ CORRECT
GEO_API_BASE = "https://geo.api.gouv.fr"  # Fonctionne
```

---

## Troubleshooting

### 1. `asyncio.exceptions.TimeoutError`

**Cause** : PostgreSQL ne répond pas ou refuse les connexions

**Diagnostic** :
```powershell
# Vérifier si PostgreSQL écoute
netstat -ano | Select-String ":5432"

# Vérifier si PostgreSQL répond
cd "C:\Program Files\PostgreSQL\18\bin"
.\pg_isready.exe -h localhost -p 5432
```

**Solutions** :
1. PostgreSQL pas démarré → `.\start.ps1` (ou démarrer manuellement avec pg_ctl)
2. PostgreSQL refuse connexions → Vérifier `pg_hba.conf` (doit contenir scram-sha-256 pour localhost)
3. Base inexistante → `setup_postgres.bat`

### 2. `Connection refused (0x0000274D/10061)`

**Cause** : PostgreSQL écoute mais refuse les connexions TCP/IP

**Solution** :
```powershell
# Vérifier pg_hba.conf
cat C:\pgdata18\pg_hba.conf | Select-String "127.0.0.1"

# Doit contenir :
# host    all    all    127.0.0.1/32    scram-sha-256
```

### 3. PostgreSQL "Stopped" mais port 5432 en écoute

**Explication** : Un autre processus peut occuper le port 5432

**Diagnostic** :
```powershell
netstat -ano | Select-String ":5432"
# Exemple : TCP    0.0.0.0:5432    0.0.0.0:0    LISTENING    12345

Get-Process -Id 12345
# Vérifier si c'est postgres.exe, python.exe, etc.
```

**Solution si processus zombie** :
```powershell
Stop-Process -Id 12345 -Force
.\start.ps1  # Redémarrer proprement
```

### 4. CORS "blocked by CORS policy"

**Symptôme** :
```
Access to XMLHttpRequest at 'http://localhost:8000/v1/campaigns' 
from origin 'http://localhost:5173' has been blocked by CORS policy
```

**Cause** : Backend ne charge pas la config CORS ou backend pas redémarré

**Solution** :
```powershell
# 1. Vérifier .env
cat .env | Select-String "CORS_ORIGINS"
# Doit contenir : CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8000

# 2. Redémarrer le backend
.\stop.ps1
.\start.ps1

# 3. Tester CORS
curl http://127.0.0.1:8000/ -Headers @{"Origin"="http://localhost:5173"} -UseBasicParsing
# Doit afficher : Access-Control-Allow-Origin: http://localhost:5173
```

### 5. Migrations Alembic échouent

**Cause** : Timeout de connexion, incohérence schéma, ou migration invalide

**Solutions** :
```bash
# Voir l'état actuel
alembic current

# Voir l'historique
alembic history

# Rollback si problème
alembic downgrade -1

# Forcer upgrade (attention!)
alembic upgrade head

# Supprimer migration invalide
rm migrations/versions/XXXXX_migration_invalide.py
alembic upgrade head
```

### 6. Frontend ne se connecte pas au backend

**Diagnostic** :
```bash
# Vérifier VITE_API_URL
cd frontend
cat .env

# Vérifier backend actif
curl http://localhost:8000/health
```

**Solutions** :
- Vérifier `VITE_API_URL=http://localhost:8000` dans `frontend/.env`
- Vérifier CORS (voir problème 4)
- Redémarrer frontend : `cd frontend && npm run dev`

---

## Scripts PowerShell

### Scripts principaux (en utilisation)

#### `start.ps1` (285 lignes)

**Description** : Script de démarrage complet de l'application

**Fonctionnalités** :
- Vérification PostgreSQL avec `pg_isready`
- Démarrage PostgreSQL avec `pg_ctl start -w` (flag `-w` critique!)
- Création base de données (appelle `check_and_create_db.ps1`)
- Activation environnement virtuel Python
- Application migrations Alembic
- Démarrage backend (Uvicorn port 8000)
- Démarrage frontend (Vite port 5173)
- Affichage couleurs (Cyan/Green/Yellow/Red)
- Délai 5s avant auto-fermeture

**Usage** :
```powershell
.\start.ps1
```

**Dépendances** :
- `check_and_create_db.ps1`
- PostgreSQL tools (`pg_ctl.exe`, `pg_isready.exe`)
- Python venv
- npm

#### `stop.ps1` (384 lignes)

**Description** : Script d'arrêt complet et nettoyage

**Fonctionnalités** :
- Arrêt processus Node.js/frontend (ports 5173, 3000)
- Arrêt processus Python/backend (port 8000)
- Arrêt PostgreSQL en 3 niveaux (fast → immediate → kill)
- Nettoyage zombies PostgreSQL
- Libération agressive ports (5432, 8000, 5173)
- Affichage couleurs
- Délai 5s avant auto-fermeture

**Usage** :
```powershell
.\stop.ps1
```

**Points clés** :
- Utilise `$portPid` (pas `$pid` qui est réservé PowerShell)
- Tue TOUS les processus `*postgres*` après shutdown normal
- Gère les ports même si occupés par d'autres processus

#### `check_and_create_db.ps1` (48 lignes)

**Description** : Crée la base de données sans détruire les données existantes

**Fonctionnalités** :
- Vérifie existence de la base `emailsaas`
- Crée uniquement si inexistante
- Préserve les données en production

**Usage** :
```powershell
.\check_and_create_db.ps1
```

**Appelé par** : `start.ps1` (lignes 127, 142)

### Scripts supprimés (obsolètes)

Les scripts suivants ont été **supprimés le 29 octobre 2025** car remplacés par `start.ps1` et `stop.ps1` :

- `check_postgres.ps1` - Remplacé par `pg_isready` dans `start.ps1`
- `check_quick.ps1` - Intégré dans `start.ps1`
- `fix_postgres_config.ps1` - Utilisé une fois au setup initial
- `launch_app.ps1` - Remplacé par `start.ps1`
- `quick_start.ps1` - Workaround temporaire
- `start_postgres_admin.ps1` - Nécessitait droits admin
- `start_postgres_direct.ps1` - Intégré dans `start.ps1`
- `stop_postgres.ps1` - Intégré dans `stop.ps1`

### Timeouts dans les scripts

**Tous les scripts utilisent des timeouts** pour éviter les blocages :

**PostgreSQL**
```powershell
# Variables d'environnement
$env:PGCONNECT_TIMEOUT = "10"

# Avec pg_ctl (flag -w = wait for completion)
pg_ctl.exe start -D "$pgDataDir" -l "$logFile" -w
# Sans -w, le script pend indéfiniment!

# Test de connexion avec timeout
$job = Start-Job -ScriptBlock { pg_isready -h localhost -p 5432 }
$completed = Wait-Job $job -Timeout 30
if (-not $completed) { Stop-Job $job }
```

**Migrations Alembic** (`migrations/env.py`)
```python
# Timeout de 30s pour les connexions
connectable = AsyncEngine(
    create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        connect_args={"timeout": 30, "command_timeout": 30}
    )
)
```

---

## Base de données

### Schéma PostgreSQL

**Identifiants** :
```
Host:     localhost
Port:     5432
Database: emailsaas
User:     emailsaas_user
Password: emailsaas_pass
Data Dir: C:\pgdata18
```

### Tables principales

**tenants** - Comptes clients (multi-tenant)
```sql
- id (UUID, PK)
- company_name (VARCHAR)
- email (VARCHAR, UNIQUE)
- password_hash (VARCHAR)
- api_key_hash (VARCHAR)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
```

**accounts** - Comptes email (Gmail/Outlook/SMTP)
```sql
- id (UUID, PK)
- tenant_id (UUID, FK → tenants.id)
- provider_type (ENUM: gmail, outlook, smtp)
- account_name (VARCHAR)
- email_address (VARCHAR)
- daily_quota (INTEGER)
- is_active (BOOLEAN)
- health_status (ENUM: healthy, degraded, failed)
- created_at (TIMESTAMP)
```

**campaigns** - Campagnes de prospection (UUID)
```sql
- id (UUID, PK)
- tenant_id (UUID, FK → tenants.id)
- name (VARCHAR)
- status (ENUM: draft, scheduled, running, completed, failed)
- source_type (VARCHAR)           # "mairie_search"
- search_city (VARCHAR)            # Ville recherchée
- search_latitude (FLOAT)          # Latitude centre
- search_longitude (FLOAT)         # Longitude centre
- search_radius_km (FLOAT)         # Rayon en km
- search_limit (INTEGER)           # Limite résultats
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
```

**campaign_recipients** - Destinataires des campagnes (UUID)
```sql
- id (UUID, PK)
- campaign_id (UUID, FK → campaigns.id)
- commune_name (VARCHAR)
- code_insee (VARCHAR)
- email (VARCHAR)
- site_web (VARCHAR)
- telephone (VARCHAR)
- population (INTEGER)
- distance_km (FLOAT)
- status (ENUM: pending, sent, failed, bounced)
- created_at (TIMESTAMP)
```

**email_logs** - Historique des envois
```sql
- id (UUID, PK)
- tenant_id (UUID, FK → tenants.id)
- account_id (UUID, FK → accounts.id)
- to_address (VARCHAR)
- subject (VARCHAR)
- status (ENUM: sent, failed, bounced, delivered)
- sent_at (TIMESTAMP)
- error_message (TEXT)
```

### Migrations

**Ordre chronologique** :
1. `2025_10_26_1430-001_initial_schema.py` - Schéma initial
2. `2025_10_28_2330-b5c9dffc31cb_add_campaigns_with_uuid.py` - Campaigns avec UUID
3. `2025_10_28_2338-27c8a820a2f4_add_mairie_fields_to_campaigns.py` - Champs mairie

**Commandes** :
```bash
# Créer migration
alembic revision --autogenerate -m "description"

# Appliquer toutes
alembic upgrade head

# Rollback
alembic downgrade -1

# État actuel
alembic current

# Historique
alembic history
```

### Connexion manuelle

```powershell
# Méthode 1 : Variable d'environnement
$env:PGPASSWORD="emailsaas_pass"
psql -U emailsaas_user -h localhost -d emailsaas

# Méthode 2 : Connexion directe
psql postgresql://emailsaas_user:emailsaas_pass@localhost:5432/emailsaas

# Commandes utiles
\dt                    # Lister les tables
\d campaigns           # Décrire table
\l                     # Lister bases de données
\q                     # Quitter
```

---

## Historique des problèmes résolus

1. **28 oct 2025** - Docker désactivé (bugs Windows)
2. **28 oct 2025** - Incohérence identifiants DB corrigée
3. **28 oct 2025** - Ajout de timeouts partout (10-30s)
4. **28 oct 2025** - Fix configuration `pg_hba.conf` pour localhost
5. **28 oct 2025** - Scripts de diagnostic créés
6. **28 oct 2025** - Scripts rendus autonomes (pause retirés)
7. **28 oct 2025** - Découverte dossier données PostgreSQL : `C:\pgdata18`
8. **28 oct 2025** - Port 5432 occupé par Python - résolu
9. **28 oct 2025** - PostgreSQL démarré SANS droits admin (`pg_ctl` direct)
10. **28 oct 2025** - Migrations corrigées (suppression migration 003 invalide)
11. **28 oct 2025** - Script `launch_app.ps1` créé - lancement complet autonome
12. **28 oct 2025** - Intégration complète Campagne Mairie (`MairieService` + migrations)
13. **28 oct 2025** - Fix CORS pour frontend sur port 5173
14. **29 oct 2025** - Fix DNS : `geo.gouv.fr` → `geo.api.gouv.fr`
15. **29 oct 2025** - Fix Enum : strings → `CampaignStatus.SCHEDULED`
16. **29 oct 2025** - Fix Pydantic v2 : `Optional[T]` → `Optional[T] = None`
17. **29 oct 2025** - Tests end-to-end complets : 6/6 passés ✅
18. **29 oct 2025** - Validation recherche mairies Angers : 5 emails récupérés
19. **29 oct 2025** - Création scripts `start.ps1` et `stop.ps1` fonctionnels
20. **29 oct 2025** - Suppression 8 scripts PowerShell obsolètes
21. **29 oct 2025** - Centralisation documentation dans `.github/`

---

## Points critiques à retenir

### ⚠️ RÈGLES ABSOLUES

1. **NE JAMAIS utiliser Docker** sur cet environnement (bugs Windows)
2. **TOUJOURS** utiliser les identifiants DB : `emailsaas_user:emailsaas_pass`
3. **TOUJOURS** utiliser `postgresql+asyncpg://` (pas `postgresql://`)
4. **TOUJOURS** ajouter des timeouts pour connexions réseau/DB
5. **TOUJOURS** utiliser `geo.api.gouv.fr` (PAS `geo.gouv.fr`)

### ✅ Bonnes pratiques

- PostgreSQL peut tourner même si service Windows dit "Stopped"
- `netstat -ano | Select-String ":5432"` plus fiable que `Get-Service`
- `pg_ctl start -w` (flag `-w` OBLIGATOIRE pour éviter script qui pend)
- `pg_isready` est l'outil officiel pour tester PostgreSQL (pas psql)
- Variable `$pid` est réservée PowerShell → utiliser `$portPid`
- Dossier de données PostgreSQL : `C:\pgdata18` (pas Program Files)
- **Enums** : `CampaignStatus.DRAFT` (pas `"draft"`)
- **Pydantic v2** : `Optional[T] = None` obligatoire
- **UUID** : Campaign et CampaignRecipient utilisent UUID (pas Integer)

---

## Checklist avant commit

- [ ] Pas de références Docker ajoutées
- [ ] Identifiants DB cohérents (`emailsaas_user:emailsaas_pass`)
- [ ] Timeouts ajoutés si connexion réseau/DB
- [ ] Scripts PowerShell testés sur Windows
- [ ] `.env.example` à jour avec bonnes valeurs
- [ ] Migrations testées avec `alembic upgrade head`
- [ ] Tests automatisés passent (`pytest`)
- [ ] Frontend build sans erreurs (`npm run build`)

---

## Support et ressources

**Documentation API** : http://localhost:8000/docs (Swagger)  
**Health Check** : http://localhost:8000/health  
**Metrics** : http://localhost:8000/metrics (Prometheus)

**Fichiers de référence** :
- `.github/copilot-instructions.md` - Instructions GitHub Copilot
- `.github/DOCUMENTATION.md` - Cette documentation
- `README.md` - Quick start général

---

**Dernière révision** : 29 octobre 2025  
**Auteur** : Équipe EmailSaaS  
**License** : MIT
