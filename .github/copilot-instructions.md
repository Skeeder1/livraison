# Instructions GitHub Copilot - Email SaaS Platform

## 🤖 AUTONOMOUS MCP SERVERS - READ FIRST

**⚠️ CRITICAL**: Claude is now **autonomous** in using MCP servers.

**📖 Full Guidelines**: See **`/CLAUDE.md`** in repository root for complete autonomous MCP usage rules.

**Quick Summary**:
- Claude **automatically uses** MCP servers when needed (no permission required)
- No need to ask "Should I search?" or "Can I use...?"
- Available servers: `brave-search`, `claude-context`, `playwright`, `railway`, `context7`
- When Claude identifies an information gap → Uses appropriate MCP server immediately
- When Claude needs to solve a problem → Uses MCP servers proactively as part of solution

See `/CLAUDE.md` for detailed autonomous rules and decision-making flow.

---

## ⚠️ RÈGLES CRITIQUES - À LIRE EN PREMIER

### Docker
**❌ NE JAMAIS UTILISER DOCKER** - Docker pose des problèmes sur cet environnement.
**✅ TOUJOURS** utiliser PostgreSQL et Redis installés localement sur Windows.

### Tests
**✅ TOUJOURS** placer les fichiers de test dans le dossier `tests/`
- **Interdiction** : Créer des fichiers `test_*.py` à la racine du projet
- **Structure correcte** :
  - `tests/unit/` - Tests unitaires
  - `tests/integration/` - Tests d'intégration
  - `tests/e2e/` - Tests end-to-end
- **Nettoyage** : Supprimer immédiatement tout fichier `test_*.py` à la racine

### Environnement
- **OS** : Windows avec PowerShell
- **Python** : 3.10
- **PostgreSQL** : 15+ (actuellement 18)
- **Redis** : Installé localement
- **Services** : Doivent être démarrés manuellement

---

## 🗄️ Configuration Base de Données

### Identifiants standardisés (TOUJOURS utiliser ceux-ci)
```
Host:     localhost
Port:     5432
Database: emailsaas
User:     emailsaas_user
Password: emailsaas_pass
```

### URLs de connexion
```bash
# PostgreSQL avec asyncpg (pour l'application)
DATABASE_URL=postgresql+asyncpg://emailsaas_user:emailsaas_pass@localhost:5432/emailsaas

# PostgreSQL standard (pour psql et setup)
postgresql://emailsaas_user:emailsaas_pass@localhost:5432/emailsaas
```

### Fichiers de configuration critiques
1. **`.env`** - URL de connexion principale
2. **`alembic.ini`** - Même URL pour les migrations
3. **`setup_postgres.bat`** - Création de l'utilisateur
4. **`src/core/config.py`** - Settings de l'application

**⚠️ IMPORTANT** : Tous ces fichiers doivent utiliser les mêmes identifiants !

---

## 🚀 Ordre de démarrage

### **MÉTHODE RECOMMANDÉE (Scripts PowerShell 2025)**

```powershell
# Démarrer l'application complète
.\start.ps1

# Arrêter l'application complète
.\stop.ps1
```

**Ce que fait `start.ps1`** :
1. Démarre PostgreSQL avec `pg_ctl start -w` (flag -w OBLIGATOIRE!)
2. Crée la base de données si nécessaire (via `check_and_create_db.ps1`)
3. Active l'environnement virtuel Python
4. Applique les migrations Alembic
5. Lance backend (Uvicorn port 8000)
6. Lance frontend (Vite port 5173)
7. Affichage couleurs + délai 5s avant auto-fermeture

**Ce que fait `stop.ps1`** :
1. Arrête processus Node.js/frontend (ports 5173, 3000)
2. Arrête processus Python/backend (port 8000)
3. Arrête PostgreSQL proprement (fast → immediate → kill)
4. Nettoie les zombies PostgreSQL
5. Libère les ports (5432, 8000, 5173)
6. Affichage couleurs + délai 5s avant auto-fermeture

### Démarrage manuel (si besoin de contrôle)

#### 1. Démarrer PostgreSQL
```powershell
cd "C:\Program Files\PostgreSQL\18\bin"
.\pg_ctl.exe start -D "C:\pgdata18" -l "C:\pgdata18\logfile" -w
.\pg_isready.exe -h localhost -p 5432  # Vérifier
```

#### 2. Créer la base (si première fois)
```cmd
setup_postgres.bat
```

#### 3. Backend
```powershell
.\venv\Scripts\activate.ps1
alembic upgrade head
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

#### 4. Frontend
```powershell
cd frontend
npm run dev
```

---

## 🛠️ Scripts disponibles

### ✅ Scripts actifs (en utilisation)

| Script | Lignes | Description |
|--------|--------|-------------|
| **`start.ps1`** | 285 | **Script principal de démarrage** - PostgreSQL + Backend + Frontend |
| **`stop.ps1`** | 384 | **Script principal d'arrêt** - Nettoyage complet + zombies |
| `check_and_create_db.ps1` | 48 | Crée la base si inexistante (appelé par start.ps1) |
| `setup_postgres.bat` | - | Setup initial PostgreSQL (CREATE USER/DATABASE) |

**Fonctionnalités clés** :
- ✅ `start.ps1` utilise `pg_ctl start -w` (flag `-w` OBLIGATOIRE pour éviter script qui pend)
- ✅ `start.ps1` utilise `pg_isready` (outil officiel) pour tester PostgreSQL
- ✅ `stop.ps1` nettoie les zombies PostgreSQL (`*postgres*`)
- ✅ `stop.ps1` libère agressivement les ports (utilise `$portPid` pas `$pid`)
- ✅ Affichage couleurs : Cyan (headers), Green (success), Yellow (warning), Red (error)
- ✅ Délai 5s avant auto-fermeture

### ❌ Scripts supprimés (29 octobre 2025)

Ces scripts ont été **supprimés** car remplacés par `start.ps1` et `stop.ps1` :
- `check_postgres.ps1` - Remplacé par `pg_isready` dans `start.ps1`
- `check_quick.ps1` - Intégré dans `start.ps1`
- `fix_postgres_config.ps1` - Utilisé une fois au setup initial
- `launch_app.ps1` - Remplacé par `start.ps1`
- `quick_start.ps1` - Workaround temporaire
- `start_postgres_admin.ps1` - Nécessitait droits admin
- `start_postgres_direct.ps1` - Intégré dans `start.ps1`
- `stop_postgres.ps1` - Intégré dans `stop.ps1`

---

## ⏱️ Gestion des Timeouts

**TOUS les scripts de connexion utilisent des timeouts** pour éviter de rester bloqués :

### PostgreSQL
- **Variables d'environnement** : `PGCONNECT_TIMEOUT=5-10`
- **Scripts PowerShell** : Utilisation de `Start-Job` avec `Wait-Job -Timeout`
- **Migrations Alembic** : `timeout: 30, command_timeout: 30` dans `migrations/env.py`

### Exemple de connexion sécurisée
```powershell
$env:PGPASSWORD = "emailsaas_pass"
$env:PGCONNECT_TIMEOUT = "10"
$job = Start-Job -ScriptBlock { psql -U emailsaas_user ... }
$completed = Wait-Job $job -Timeout 15
if (-not $completed) { Stop-Job $job }
```

---

## ❗ Problèmes courants et solutions

### 1. `asyncio.exceptions.TimeoutError`
**Cause** : PostgreSQL ne répond pas ou refuse les connexions

**Diagnostic** :
```powershell
.\check_quick.ps1
```

**Solutions par ordre** :
1. PostgreSQL pas démarré → `start_postgres_admin.ps1` (admin)
2. PostgreSQL refuse connexions → `fix_postgres_config.ps1` (admin)
3. Base inexistante → `setup_postgres.bat`

### 2. `Connection refused (0x0000274D/10061)`
**Cause** : PostgreSQL écoute mais refuse les connexions TCP/IP

**Solution** :
```powershell
# Clic droit -> Admin
fix_postgres_config.ps1
# Puis redémarrer PostgreSQL (le script vous guide)
```

### 3. PostgreSQL "Stopped" mais port 5432 en écoute
**Explication** : Un autre processus (souvent Python) peut occuper le port 5432

**Vérification** :
```powershell
netstat -ano | Select-String ":5432"  # Voir le PID
Get-Process -Id <PID>                 # Vérifier le processus
```

**Solution si c'est Python** :
```powershell
Stop-Process -Id <PID> -Force        # Arrêter le processus
Start-Service postgresql-x64-18      # Démarrer PostgreSQL (admin requis)
```

### 4. Identifiants invalides / Base inexistante
**Cause** : `setup_postgres.bat` pas exécuté ou échec

**Solution** :
```cmd
setup_postgres.bat
```

### 5. Script bloqué sur "Test de connexion..."
**Cause** : Timeout pas configuré ou PostgreSQL ne répond pas

**Solution immédiate** : Ctrl+C pour annuler

**Fix** : Utiliser `check_quick.ps1` qui ne teste pas la connexion DB

---

## 🔐 Configuration PostgreSQL (pg_hba.conf)

### Dossier de données PostgreSQL
**⚠️ IMPORTANT** : Le dossier de données PostgreSQL est à `C:\pgdata18`

### Configuration requise pour localhost
```conf
# IPv4 local connections:
host    all             all             127.0.0.1/32            scram-sha-256

# IPv6 local connections:
host    all             all             ::1/128                 scram-sha-256
```

**Localisation du fichier** : `C:\pgdata18\pg_hba.conf`

**Automatisation** : Utiliser `fix_postgres_config.ps1` (créé automatiquement les backups)

---

## 📁 Structure du projet

### Backend (Python/FastAPI)
```
src/
├── api/           # Routes FastAPI
├── core/          # Configuration (database, security)
├── models/        # SQLAlchemy models
├── services/      # Business logic
├── providers/     # Email providers (Gmail, Outlook, SMTP)
└── workers/       # Background tasks
```

### Frontend (React/TypeScript/Vite)
```
frontend/src/
├── components/    # React components
├── contexts/      # Context providers
├── pages/         # Page components
├── services/      # API client
└── types/         # TypeScript types
```

### Migrations
```
migrations/
├── env.py                      # Alembic config (avec timeouts!)
└── versions/
    └── *.py                    # Migration files
```

---

## 🔧 Commandes utiles

### Backend
```bash
# Activer l'environnement virtuel
.\venv\Scripts\activate

# Migrations
alembic upgrade head              # Appliquer toutes les migrations
alembic revision --autogenerate   # Créer nouvelle migration

# Démarrer le serveur
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### PostgreSQL
```bash
# Connexion directe
psql -U emailsaas_user -h localhost -d emailsaas

# Avec variable d'environnement
$env:PGPASSWORD="emailsaas_pass"; psql -U emailsaas_user -h localhost -d emailsaas
```

---

## 🎯 Bonnes pratiques pour Copilot

### Lors de la création de nouveaux scripts
- ✅ TOUJOURS ajouter des timeouts pour les connexions réseau/DB
- ✅ Utiliser `Start-Job` + `Wait-Job -Timeout` dans PowerShell
- ✅ Ajouter `PGCONNECT_TIMEOUT` pour psql
- ✅ Gérer les erreurs et donner des messages clairs

### Lors de la modification de la config DB
- ✅ Vérifier `.env`, `alembic.ini`, et `src/core/config.py`
- ✅ TOUJOURS utiliser `emailsaas_user:emailsaas_pass`
- ✅ TOUJOURS utiliser `postgresql+asyncpg://` (pas juste `postgresql://`)

### Lors de l'ajout de dépendances
- ✅ Backend : Ajouter dans `requirements.txt`
- ✅ Frontend : Ajouter avec `npm install`
- ❌ NE PAS créer de Dockerfile ou docker-compose

---

## 📊 État actuel du système (29 octobre 2025)

### Diagnostic
- PostgreSQL 18 installé ✅
- Dossier de données : `C:\pgdata18` ✅
- Configuration pg_hba.conf : ✅ Correcte (scram-sha-256 pour localhost)
- Port 5432 : ✅ PostgreSQL actif
- Base de données créée : ✅ `emailsaas` opérationnelle
- Migrations appliquées : ✅ À jour (campaigns avec UUID + champs mairie)
- Backend testé : ✅ Tous les endpoints fonctionnels
- Campagne Mairie : ✅ Intégration complète et testée

### Fonctionnalités validées
- ✅ Authentification (register/login)
- ✅ CORS configuré (localhost:5173)
- ✅ Création campagne par ville (géocodage automatique)
- ✅ Création campagne par coordonnées GPS
- ✅ Recherche mairies dans rayon (algorithme Haversine)
- ✅ Récupération emails mairies (2 APIs gouvernementales)
- ✅ Stockage destinataires avec métadonnées (population, distance, etc.)
- ✅ Gestion status campagne (ENUM: draft, scheduled, running, completed)

### Fichiers récents importants
- `check_quick.ps1` - Vérification rapide sans blocage
- `fix_postgres_config.ps1` - Fix configuration PostgreSQL
- `migrations/env.py` - Ajout de timeouts (30s)
- `src/services/mairie_service.py` - Service complet recherche mairies
- `src/services/campaign_service.py` - Orchestration campagnes
- `test_backend_complete.py` - Suite de tests automatisés (6/6 passés)
- `test_geocoding.py` - Tests API géo gouvernementale

---

## 📝 Notes de développement

### Historique des problèmes résolus
1. **28 oct 2025** - Docker désactivé (bugs Windows)
2. **28 oct 2025** - Incohérence identifiants DB corrigée
3. **28 oct 2025** - Ajout de timeouts partout (10-30s)
4. **28 oct 2025** - Fix configuration pg_hba.conf pour localhost
5. **28 oct 2025** - Scripts de diagnostic créés (check_quick, check_postgres)
6. **28 oct 2025** - Tous les scripts rendus autonomes (pause retirés)
7. **28 oct 2025** - Découverte dossier données PostgreSQL : C:\pgdata18
8. **28 oct 2025** - Port 5432 occupé par Python - résolu
9. **28 oct 2025** - PostgreSQL démarré SANS droits admin (pg_ctl direct)
10. **28 oct 2025** - Migrations corrigées (suppression migration 003 invalide)
11. **28 oct 2025** - Script `launch_app.ps1` créé - lancement complet autonome
12. **28 oct 2025** - Intégration complète Campagne Mairie (MairieService + migrations)
13. **28 oct 2025** - Fix CORS pour frontend sur port 5173
14. **29 oct 2025** - Fix DNS : `geo.gouv.fr` → `geo.api.gouv.fr`
15. **29 oct 2025** - Fix Enum : strings → `CampaignStatus.SCHEDULED`
16. **29 oct 2025** - Fix Pydantic v2 : `Optional[T]` → `Optional[T] = None`
17. **29 oct 2025** - Tests end-to-end complets : 6/6 passés ✅
18. **29 oct 2025** - Validation recherche mairies Angers : 5 emails récupérés

### CORS - Résolution erreur "blocked by CORS policy"
**Symptôme** : `Access to XMLHttpRequest at 'http://localhost:8000/v1/campaigns' from origin 'http://localhost:5173' has been blocked by CORS policy`

**Cause** : Le fichier `.env` contient la configuration CORS mais le backend doit être redémarré pour la charger.

**Solution** :
```powershell
# 1. Arrêter tous les processus uvicorn
Get-Process | Where-Object {$_.ProcessName -eq "uvicorn"} | Stop-Process -Force

# 2. Vérifier que .env contient le bon port frontend
# CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8000

# 3. Redémarrer le backend
.\venv\Scripts\activate.ps1
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000

# 4. Tester CORS
curl http://127.0.0.1:8000/ -Headers @{"Origin"="http://localhost:5173"} -UseBasicParsing
# Doit afficher : Access-Control-Allow-Origin: http://localhost:5173
```

### Routes API disponibles
- `POST /v1/auth/register` - Créer un compte
- `POST /v1/auth/login` - Se connecter
- `GET /v1/auth/me` - Infos utilisateur
- `GET /v1/campaigns` - Liste des campagnes
- `POST /v1/campaigns` - Créer une campagne mairie
- `GET /v1/campaigns/{id}` - Détails d'une campagne
- `GET /v1/campaigns/{id}/recipients` - Liste des destinataires
- `POST /v1/emails/send` - Envoyer un email
- `POST /v1/emails/batch` - Envoyer un batch
- Docs complètes : http://localhost:8000/docs

### Campagne Mairie - Temps de réponse
- **Géocodage ville** : ~1-2s
- **Recherche 5 communes** : ~7-11s (temps réel mesuré)
- **Recherche 10 communes** : ~10-15s
- **Recherche 50 communes** : ~30-60s
- **Recherche 200 communes** : ~2-5 minutes

**⚠️ Ne pas mettre de limite trop élevée** - Préférer 5-10 communes pour les tests, 10-50 pour la production.

### Campagne Mairie - Implémentation complète (29 oct 2025)

#### APIs utilisées
```python
# ⚠️ IMPORTANT : Utiliser geo.api.gouv.fr (PAS geo.gouv.fr)
GEO_API_BASE = "https://geo.api.gouv.fr"  # API géocodage et communes
ETABLISSEMENTS_API = "https://etablissements-publics.api.gouv.fr"  # Emails mairies
ANNUAIRE_API = "https://api-lannuaire.service-public.fr"  # Emails fallback
```

**Erreur commune** : `geo.gouv.fr` ne résout pas en DNS → **Toujours utiliser `geo.api.gouv.fr`**

#### Modèles (UUID requis)
```python
# Campaign - UUID primary keys
class Campaign(Base):
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    status = Column(SQLEnum(CampaignStatus), default=CampaignStatus.DRAFT)  # ENUM requis
    
    # Champs spécifiques mairie
    source_type = Column(String(50))  # "mairie_search"
    search_city = Column(String(255))
    search_latitude = Column(Float)
    search_longitude = Column(Float)
    search_radius_km = Column(Float)
    search_limit = Column(Integer)

# CampaignRecipient - UUID + champs mairie
class CampaignRecipient(Base):
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"))
    commune_name = Column(String(255))
    code_insee = Column(String(10))
    email = Column(String(255))
    site_web = Column(String(500))
    telephone = Column(String(20))
    population = Column(Integer)
    distance_km = Column(Float)
    status = Column(SQLEnum(RecipientStatus), default=RecipientStatus.PENDING)  # ENUM requis
```

#### Services implémentés
```python
# src/services/mairie_service.py
class MairieService:
    @staticmethod
    async def geocode_city(city_name: str) -> Optional[Tuple[float, float]]:
        """Géocode une ville → (latitude, longitude)"""
        # Utilise httpx async + geo.api.gouv.fr/communes?nom={city}
        # Retourne GeoJSON coordinates inversées : [lon, lat] → (lat, lon)
    
    @staticmethod
    async def search_mairies(lat, lon, radius_km, limit) -> List[Dict]:
        """Cherche mairies dans un rayon"""
        # 1. Récupère toutes les communes par département (01-95 + DOM-TOM)
        # 2. Calcule distance Haversine pour chaque commune
        # 3. Filtre par radius_km, trie par distance
        # 4. Appelle get_mairie_info() pour chaque commune
        # 5. Retourne {commune, code_insee, email, site_web, telephone, population, distance_km}
    
    @staticmethod
    async def get_mairie_info(code_insee, nom_commune) -> Dict:
        """Récupère email/contact de la mairie"""
        # Essaie etablissements-publics.api.gouv.fr/v3/communes/{code_insee}/mairie
        # Fallback sur api-lannuaire.service-public.fr si email non trouvé

# src/services/campaign_service.py
class CampaignService:
    async def fetch_mairies(self, *, city_name, latitude, longitude, radius_km, limit) -> dict:
        """Fetch mairies et coordonnées du centre"""
        # Géocode city si fourni, sinon utilise lat/lon directes
        # Retourne {"results": [...], "latitude": ..., "longitude": ...}
```

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

#### Migrations créées
```bash
# Migration initiale avec UUID
2025_10_28_2330-b5c9dffc31cb_add_campaigns_with_uuid.py

# Ajout champs mairie
2025_10_29_0900-003_add_campaign_search_metadata.py
```

#### Test end-to-end validé (29 oct 2025)
```bash
# Résultats des tests automatisés
✅ Health Check
✅ CORS Verification (localhost:5173)
✅ User Registration
✅ Create Campaign (Angers, 25km, 5 mairies trouvées)
✅ Get Campaigns List
✅ Get Campaign Recipients

# Mairies trouvées (exemple Angers 25km)
1. Angers - mairie.angers@ville.angers.fr - 157,555 hab - 0 km
2. Avrillé - mairie@ville-avrille.fr - 15,225 hab - 3.69 km
3. Beaucouzé - maire@beaucouze.fr - 5,618 hab - 5.55 km
4. Écouflant - mairie@ecouflant.fr - 4,614 hab - 5.73 km
5. Sainte-Gemmes-sur-Loire - mairie@sainte-gemmes-sur-loire.fr - 3,617 hab - 5.84 km
```

#### Flux complet
```
1. Frontend (CampaignPage) → POST /v1/campaigns
   {
     "name": "Campagne Angers",
     "city_name": "Angers",
     "radius_km": 25,
     "limit": 5
   }

2. Backend geocode la ville → (47.4819, -0.5629)

3. Backend cherche communes dans 25km
   - Parcourt tous les départements
   - Calcule distance Haversine
   - Filtre + trie par distance

4. Backend récupère emails des mairies
   - API établissements-publics
   - Fallback API annuaire

5. Backend crée Campaign + CampaignRecipients
   - Status: scheduled
   - 5 destinataires avec emails réels

6. Frontend affiche la liste → Bouton "Exporter"

7. Clic "Exporter" → Redirect vers /send?campaignId=xxx
   - Pre-rempli avec emails des mairies
```

### À retenir
- PostgreSQL peut tourner même si le service Windows dit "Stopped"
- `netstat -ano | Select-String ":5432"` est plus fiable que `Get-Service`
- Les timeouts sont OBLIGATOIRES pour éviter les blocages
- Toujours vérifier avec `check_quick.ps1` avant de démarrer
- **Port 5432 peut être occupé par Python** - vérifier avec `Get-Process -Id <PID>`
- Dossier de données PostgreSQL : `C:\pgdata18` (pas Program Files)
- **API Géo** : TOUJOURS `geo.api.gouv.fr` (pas `geo.gouv.fr`)
- **Enums** : Utiliser `CampaignStatus.DRAFT` pas `"draft"`
- **Pydantic v2** : `Optional[T] = None` obligatoire
- **UUID** : Campaign et CampaignRecipient utilisent UUID pas Integer

---

## 🚨 Checklist avant commit

- [ ] Pas de références Docker ajoutées
- [ ] Identifiants DB cohérents (`emailsaas_user:emailsaas_pass`)
- [ ] Timeouts ajoutés si connexion réseau/DB
- [ ] Scripts PowerShell testés sur Windows
- [ ] `.env.example` à jour avec les bonnes valeurs
- [ ] Migrations testées avec `alembic upgrade head`

---

**Dernière mise à jour** : 29 octobre 2025
**Environnement** : Windows 11, PowerShell 5.1, Python 3.10, PostgreSQL 18
**Status** : ✅ Système opérationnel - Campagne Mairie 100% fonctionnelle

## 📚 Documentation complète

Pour la documentation détaillée complète, consultez :
- **`.github/DOCUMENTATION.md`** - Documentation technique exhaustive (architecture, APIs, troubleshooting, etc.)
- **`README.md`** - Quick start général du projet
- **`frontend/README.md`** - Documentation spécifique frontend React
