# Project Knowledge Base

> **Purpose**: Living documentation of project context, architecture, decisions, and lessons learned.
> **Maintenance**: Updated continuously by Claude as discoveries are made and patterns emerge.
> **Usage**: Consult this before major tasks for essential context.

---

## 📊 Project Overview

### Project Type
**Multi-tenant SaaS Email Prospection Platform**
- Allows users to manage email campaigns targeting French municipalities (mairies)
- Implements "Bring Your Own Email Provider" (BYOEP) model
- Users connect their own Gmail/Outlook accounts for sending
- Platform orchestrates campaigns across multiple user accounts per tenant

### Primary Market
**France** - Targeting city/municipality contact campaigns
- Integration with French government APIs (geo.api.gouv.fr, etablissements-publics.api.gouv.fr)
- Specialized "Mairie Campaigns" feature for municipality targeting
- French-primary documentation (project docs mostly in French)

### Core Value Proposition
- **No email infrastructure needed** - Users bring their own providers
- **Smart account selection** - Auto-selects best account based on quota/health
- **Campaign automation** - Target municipalities by radius, population, etc.
- **Progress tracking** - Real-time campaign progress visualization
- **Multi-tenant isolation** - Complete data separation between customers

---

## 🏗️ Architecture Overview

### System Components

```
Frontend (React 19 + TypeScript)
    ↓ (REST API, Axios client)
Backend (FastAPI + Python 3.11)
    ↓ (SQLAlchemy async ORM)
Database (PostgreSQL 18, local)
    ↓
    ↑ (Redis for caching)
Cache Layer (Redis, local)
```

### Infrastructure Notes
- **NO Docker** - All services run locally on Windows
- **Local PostgreSQL** - Port 5432, user: `emailsaas_user`, password: `emailsaas_pass`
- **Local Redis** - Port 6379 (used for caching)
- **Windows PowerShell scripts** - `start.ps1` and `stop.ps1` for orchestration

### Key URLs
- Frontend Dev: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs` (Swagger UI)
- Database: `postgresql://emailsaas_user:emailsaas_pass@localhost:5432/emailsaas`

---

## 🎯 Core Features & Architecture

### 1. Multi-Tenant Architecture

**Implementation**: Tenant isolation via `tenant_id` foreign key on all tables

**Pattern**:
```python
# Every query must filter by tenant_id
campaigns = await session.execute(
    select(Campaign)
    .where(Campaign.tenant_id == tenant_id)  # CRITICAL!
)
```

**Critical Rule**: ALWAYS verify `tenant_id` is included in:
- All SELECT queries
- All UPDATE queries (WHERE clause)
- All DELETE queries (WHERE clause)
- Authorization checks in route handlers

**Multi-Tenant Test Example**:
```python
# Every multi-tenant feature MUST have isolation test
def test_campaign_respects_tenant_boundaries():
    tenant1_campaigns = get_campaigns(tenant_id=1)
    tenant2_campaigns = get_campaigns(tenant_id=2)

    # Verify no cross-contamination
    assert no_common_ids(tenant1_campaigns, tenant2_campaigns)
```

### 2. "Bring Your Own Email Provider" (BYOEP) Model

**How It Works**:
1. User connects their Gmail account (OAuth2) → Creates `email_account` record
2. User connects their Outlook account → Another `email_account` record
3. When sending campaign, system auto-selects best account based on:
   - Remaining quota for today
   - Account health (bounce rate, complaints)
   - Load balancing (distribute across accounts)

**Key Tables**:
- `email_accounts` - Stores OAuth tokens, health metrics
- `email_account_quotas` - Daily/hourly limits per account
- `email_account_health` - Bounce rates, complaint rates, status

**Critical Implementation Details**:
- OAuth tokens must be encrypted at rest
- Tokens refreshed automatically before expiration
- Health metrics updated real-time
- Quota checked before sending to prevent violations

### 3. Campaign System

**Campaign Lifecycle**:
```
Draft → Configured → Ready → Running → Completed → Archived
         ↓ (validation)
        Error (if validation fails)
```

**Campaign Types**:
1. **Standard Campaigns** - Manual recipient lists
2. **Mairie Campaigns** - Auto-generated from French municipality data
   - Search by radius and GPS coordinates
   - Filter by population size
   - Auto-populate emails from government databases

**Key Tables**:
- `campaigns` - Campaign metadata (name, status, date created)
- `campaign_recipients` - Email addresses to send to
- `campaign_emails` - Email content templates
- `campaign_progress` - Tracking metrics (sent, bounced, opened)

### 4. Mairie (Municipality) Campaign Feature

**Purpose**: Specialized feature for targeting French municipalities

**How It Works**:
1. User enters search criteria:
   - Center GPS coordinates
   - Search radius (km)
   - Population filters
2. System queries French government APIs:
   - `geo.api.gouv.fr` - Geocoding
   - `etablissements-publics.api.gouv.fr` - Municipality data
3. Returns matching municipalities with contact emails
4. User creates campaign, system auto-generates recipients

**Key Service**: `src/services/mairie_service.py`
- Haversine formula for radius calculations
- API integration with French government databases
- Email extraction from municipality records

### 5. Authentication & Authorization

**JWT-Based Authentication**:
```python
# Token payload includes tenant_id and user_id
{
    "sub": "user_id",
    "tenant_id": 123,
    "exp": 1234567890,
    "iat": 1234567800
}
```

**Authorization Pattern**:
```python
# Route handlers use dependency injection
async def get_campaign(
    campaign_id: int,
    current_user: User = Depends(get_current_user),
) -> CampaignResponse:
    # Implicit tenant_id from current_user.tenant_id
    campaign = await campaign_service.get_campaign(campaign_id, current_user.tenant_id)
    return campaign
```

**OAuth2 Integration**:
- Gmail: Google API OAuth2 flow
- Outlook: Microsoft Graph + MSAL
- User accounts created via social login
- Email accounts linked to user account

---

## 🗄️ Database Schema Highlights

### Core Tables

**tenants**
- `id` (PK)
- `name`, `domain`
- `created_at`, `updated_at`
- `is_active` (soft delete capability)

**users**
- `id` (PK)
- `tenant_id` (FK) - Multi-tenant key
- `email`, `password_hash`
- `first_name`, `last_name`
- OAuth tokens for Gmail/Outlook
- `created_at`, `updated_at`

**campaigns**
- `id` (PK)
- `tenant_id` (FK) - CRITICAL for isolation
- `name`, `description`
- `status` enum: draft, running, completed, failed
- `created_by` (FK to users)
- `created_at`, `updated_at`

**email_accounts**
- `id` (PK)
- `tenant_id` (FK) - Multiple accounts per tenant
- `user_id` (FK) - Account owner
- `email`, `provider` (gmail, outlook, smtp)
- `oauth_token` (encrypted)
- `refresh_token` (encrypted)
- Health metrics: `bounce_rate`, `complaint_rate`

**campaign_recipients**
- `id` (PK)
- `campaign_id` (FK)
- `email_address`
- `status` (pending, sent, bounced, opened)

**campaign_emails**
- `id` (PK)
- `campaign_id` (FK)
- `subject`, `body`, `html_content`
- Created from template or manual entry

### Important Constraints

- `UNIQUE(tenant_id, email)` on `email_accounts`
- `CHECK(provider IN ('gmail', 'outlook', 'smtp'))` on `email_accounts`
- Foreign key constraints with CASCADE delete on `tenant_id`

### Common Query Pattern
```python
# Template for querying with tenant isolation
async def get_campaign(campaign_id: int, tenant_id: int) -> Campaign:
    """Get campaign, respecting tenant isolation."""
    result = await session.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .where(Campaign.tenant_id == tenant_id)  # ALWAYS include
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404)
    return campaign
```

---

## 📚 Technology Stack Details

### Backend (Python 3.11)

**Web Framework**:
- **FastAPI 0.109.0** - Async web framework
- **Uvicorn 0.27.0** - ASGI server with hot reload
- **Pydantic 2.5.3** - Data validation

**Database**:
- **SQLAlchemy 2.0.25** - Async ORM
- **Asyncpg 0.29.0** - Async PostgreSQL driver
- **Alembic 1.13.1** - Database migration tool
- **PostgreSQL 18** - Local database

**Caching & Background Jobs**:
- **Redis 5.0.1** - In-memory cache
- **Aioredis 2.0.1** - Async Redis client
- **Celery** - Background task queue (if installed)

**Email & OAuth**:
- **python-jose** - JWT token handling
- **Bcrypt** - Password hashing
- **Google API Client** - Gmail integration
- **Microsoft Graph SDK** - Outlook integration
- **MSAL** - Microsoft authentication

**Code Quality**:
- **Black 24.1.1** - Code formatting (line length: 100)
- **Ruff 0.1.14** - Fast linter
- **Mypy 1.8.0** - Static type checking
- **Pytest 7.4.4** - Testing framework with async support

### Frontend (React 19)

**Core**:
- **React 19.1.1** - UI library
- **React DOM 19.1.1** - DOM rendering
- **TypeScript 5.9.3** - Type safety
- **Vite 7.1.7** - Build tool and dev server

**Routing & State**:
- **React Router DOM 7.9.4** - Client-side routing
- **TanStack React Query 5.90.5** - Server state management
- **Context API** - Client state (auth)

**UI & Styling**:
- **TailwindCSS 4.1.16** - Utility-first CSS
- **Lucide React 0.548.0** - Icon library
- **Recharts 3.3.0** - Data visualization

**Forms & API**:
- **React Hook Form 7.65.0** - Form state management
- **Zod 4.1.12** - Schema validation
- **Axios 1.13.0** - HTTP client

**Code Quality**:
- **ESLint 9.36.0** - JavaScript linting
- **TypeScript ESLint** - TypeScript linting

---

## 🔐 Security Considerations

### Environment Variables (CRITICAL)
```bash
# Backend (.env)
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/db
REDIS_URL=redis://localhost:6379
JWT_SECRET_KEY=your-secret-key-here
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...

# Frontend (.env)
VITE_API_URL=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=...
```

### Secrets Management
- ❌ NEVER commit `.env` files
- ✅ Use `.env.example` with placeholders
- ✅ Encrypt sensitive data at rest (OAuth tokens)
- ✅ Rotate secrets regularly
- ✅ Use HTTPS in production

### OAuth Token Security
```python
# Tokens must be encrypted before storage
from cryptography.fernet import Fernet

cipher_suite = Fernet(settings.encryption_key)
encrypted_token = cipher_suite.encrypt(oauth_token.encode())
# Store encrypted_token in database

# Decrypt when needed
decrypted_token = cipher_suite.decrypt(encrypted_token).decode()
```

### Rate Limiting
- Email sending: Limited by provider quotas
- API requests: Should implement rate limiting (Redis)
- Campaign creation: Throttle to prevent abuse

---

## 🧪 Testing Patterns

### Key Testing Principles

1. **Always use fixtures for setup**
   ```python
   @pytest.fixture
   async def test_tenant(async_session):
       tenant = Tenant(name="Test Tenant")
       async_session.add(tenant)
       await async_session.flush()
       return tenant
   ```

2. **Test multi-tenant isolation separately**
   ```python
   def test_tenant_isolation():
       # Create resources for two tenants
       # Verify tenant1 can't access tenant2's data
   ```

3. **Use async fixtures for async code**
   ```python
   @pytest.fixture
   async def client(async_session):
       # Set up async client with test database
       pass
   ```

4. **Test error cases**
   ```python
   # Not just happy path
   def test_create_campaign_missing_name():
       # Should raise validation error
   ```

### Test File Organization
```
tests/
├── conftest.py              # Shared fixtures (databases, test data)
├── unit/
│   ├── test_models.py      # ORM model tests
│   └── test_services.py    # Business logic tests
├── integration/
│   ├── test_campaign_workflow.py  # Multi-service workflows
│   └── test_auth.py        # Authentication tests
└── e2e/
    └── test_campaign_progress.py  # User-facing workflows
```

### Coverage Goals
- Critical paths (auth, email sending): 100%
- Business logic: 85%+
- Utilities: 70%+

---

## 🔄 Development Workflow

### Daily Workflow
1. Read `.github/claude/INSTRUCTIONS.md` for behavioral guidelines
2. Check git status for any unfinished work
3. Review KNOWLEDGE_BASE.md for context
4. Use TodoWrite for complex tasks
5. Reference WORKFLOW_RULES.md for conventions

### Code Quality Checks
```bash
# Before committing
black src/ tests/          # Format code
ruff check --fix           # Lint and fix
mypy src/                  # Type checking
pytest                     # Run tests

# Frontend
npm run lint:fix           # ESLint auto-fix
npx tsc --noEmit          # Type checking
```

### Git Workflow
- Branch: `feature/name`, `fix/name`, `docs/name`
- Commit format: `type(scope): description`
- Example: `feat(campaigns): add campaign search and filtering`

---

## 🐛 Known Issues & Solutions

### Issue 1: Database Connection Timeouts
**Symptom**: `psycopg2.OperationalError: could not connect to server`
**Cause**: PostgreSQL not running locally
**Solution**:
```bash
pg_ctl -D "C:\Program Files\PostgreSQL\18\data" start
# Or use Windows Services to start PostgreSQL
```

### Issue 2: JWT Token Validation Failures
**Symptom**: 401 Unauthorized on valid tokens
**Cause**: Token claims mismatch (tenant_id field)
**Solution**: Verify JWT payload includes `tenant_id`, not just `sub`

### Issue 3: Email Account OAuth Token Expiration
**Symptom**: Email sending fails with "Invalid OAuth token"
**Cause**: OAuth2 tokens expire (Gmail: 1 hour, Outlook: varies)
**Solution**: Implement automatic token refresh before expiration

### Issue 4: Race Condition in Campaign Status Updates
**Symptom**: Campaign status becomes inconsistent
**Cause**: Multiple workers updating same campaign simultaneously
**Solution**: Use database-level pessimistic locking for campaign updates

---

## 📋 Recent Development Decisions

### Decision 1: Multi-Tenant Isolation Strategy [Oct 30, 2025]
**Context**: Need to ensure no data leakage between tenants
**Decision**: Filter by `tenant_id` at database query level, not application level
**Rationale**: Prevents accidental leakage from logic bugs
**Implementation**: Dependency injection provides `tenant_id` from JWT token
**Status**: ✅ Implemented

### Decision 2: Async SQLAlchemy Over Sync [Oct 30, 2025]
**Context**: Database queries blocking uvicorn event loop
**Decision**: Use async SQLAlchemy with asyncpg
**Rationale**: Better performance, true non-blocking I/O
**Challenges**: More complex to debug, fixture setup complexity
**Status**: ✅ Implemented

### Decision 3: Redis for Campaign Progress Caching [Oct 30, 2025]
**Context**: Campaign progress queries hitting database too frequently
**Decision**: Cache progress in Redis, update periodically
**Rationale**: Reduces database load, faster API responses
**Implementation**: Cache invalidation on campaign events
**Status**: ✅ Implemented

---

## 🎓 Important Code Patterns

### Pattern 1: Multi-Tenant Service Method
```python
class CampaignService:
    async def get_campaign(self, campaign_id: int, tenant_id: int) -> Campaign:
        """Always receive tenant_id as parameter for isolation."""
        campaign = await self.session.execute(
            select(Campaign)
            .where(Campaign.id == campaign_id)
            .where(Campaign.tenant_id == tenant_id)  # Critical!
        )
        return campaign.scalar_one_or_none()
```

### Pattern 2: Dependency Injection for Tenant Context
```python
async def get_tenant_id(current_user: User = Depends(get_current_user)) -> int:
    """Extract tenant_id from JWT token via dependency injection."""
    return current_user.tenant_id

@router.get("/campaigns")
async def list_campaigns(
    tenant_id: int = Depends(get_tenant_id),
    skip: int = Query(0),
    limit: int = Query(20),
):
    """Tenant ID automatically provided, can't be overridden by user."""
    campaigns = await campaign_service.list_campaigns(tenant_id, skip, limit)
    return campaigns
```

### Pattern 3: Async Database Session with Context Manager
```python
async with AsyncSessionLocal() as session:
    async with session.begin():
        campaign = await session.execute(
            select(Campaign).where(Campaign.id == 1)
        )
        campaign = campaign.scalar_one_or_none()
        # Auto-rollback on exception, auto-commit on success
```

### Pattern 4: React Hook Form with Zod Validation
```typescript
interface CampaignFormData {
  name: string;
  description?: string;
  recipientEmails: string[];
}

const schema = z.object({
  name: z.string().min(1, "Campaign name required"),
  description: z.string().optional(),
  recipientEmails: z.array(z.string().email()),
});

const { register, handleSubmit, formState: { errors } } = useForm<CampaignFormData>({
  resolver: zodResolver(schema),
});
```

---

## 📞 Useful Contacts & Resources

### Internal Resources
- Technical Docs: `.github/DOCUMENTATION.md`
- API Docs (runtime): `http://localhost:8000/docs`
- Existing Instructions: `.github/copilot-instructions.md`

### External APIs
- French Geocoding: `https://geo.api.gouv.fr`
- French Public Institutions: `https://etablissements-publics.api.gouv.fr`
- Google API Documentation: `https://developers.google.com/api-client-library`
- Microsoft Graph API: `https://learn.microsoft.com/en-us/graph`

### Technologies
- FastAPI: `https://fastapi.tiangolo.com`
- React: `https://react.dev`
- SQLAlchemy: `https://docs.sqlalchemy.org`
- Playwright: `https://playwright.dev`

---

## 🚀 Performance Metrics & Optimization

### Database Optimization
- **Connection pooling**: AsyncPG handles automatically
- **Query optimization**: Use async select with indexed columns
- **Caching**: Redis for campaign progress and frequently accessed data

### API Performance
- **Pagination**: Always paginate large result sets (limit 100 max)
- **Response filtering**: Only return necessary fields
- **Compression**: Enabled in production

### Frontend Performance
- **Code splitting**: Vite handles automatically
- **Image optimization**: Use lazy loading for campaign previews
- **State management**: React Query caching prevents refetches

---

## 📝 Recent Session History

### Session [Oct 30, 2025] - Architecture Setup
**Claude**: Set up comprehensive AI development architecture
**Tasks Completed**:
1. ✅ Created `.github/claude/` directory structure
2. ✅ Created INSTRUCTIONS.md with behavioral guidelines
3. ✅ Created WORKFLOW_RULES.md with development conventions
4. ✅ Created MCP_AUTOMATION.md with tool integration guide
5. ⏳ Continuing with documentation reorganization...

**Discoveries**:
- Project has excellent existing documentation (9/10 quality)
- MCP servers (Playwright, Zilliz) already configured
- Multi-tenant architecture well-designed with tenant_id filtering
- Test suite properly organized in `tests/` directory

**Next Actions**:
- Organize existing documentation into `docs/` hierarchy
- Create architecture diagrams with Mermaid
- Populate knowledge base with discovered insights

---

## 🎯 Quick Reference

### When to Consult This Document
- Before starting significant development task
- When working with unfamiliar code section
- When making architectural decisions
- When implementing multi-tenant features
- When setting up tests

### Document Update Frequency
- Updated after major discoveries
- Updated after significant decisions made
- Updated after completing complex features
- At end of each major development session

---

**Last Updated**: October 30, 2025
**Status**: Active - Under Active Development
**Owner**: Claude (maintained by Claude development sessions)
**Version**: 1.0 - Initial setup for AI-guided development
