# Workflow Rules & Development Conventions

> **Purpose**: Established conventions and best practices for consistent, maintainable development in this project.

## 📏 Code Style & Formatting

### Backend (Python)

**Line Length**: 100 characters (enforced by Black)
```python
# Good
result = function_with_long_name(param1, param2, param3,
                                  param4, param5)

# Bad
result = function_with_long_name(param1, param2, param3, param4, param5, param6)
```

**Imports**: Follow PEP 8 order
```python
# Standard library
import asyncio
from datetime import datetime
from typing import Optional

# Third-party
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local
from src.core.security import get_current_user
from src.services.campaign_service import CampaignService
```

**Type Hints**: Always use for function signatures
```python
# Good
async def create_campaign(
    name: str,
    description: Optional[str] = None,
    tenant_id: int = Depends(get_tenant_id),
) -> CampaignResponse:
    """Create a new campaign for the current tenant."""
    pass

# Bad
async def create_campaign(name, description=None, tenant_id=None):
    pass
```

**Docstrings**: Google style for all public functions
```python
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two geographic points using Haversine formula.

    Args:
        lat1: Latitude of first point in degrees
        lon1: Longitude of first point in degrees
        lat2: Latitude of second point in degrees
        lon2: Longitude of second point in degrees

    Returns:
        Distance in kilometers

    Raises:
        ValueError: If coordinates are invalid
    """
    pass
```

### Frontend (TypeScript)

**Line Length**: 100 characters (ESLint configured)
```typescript
// Good
const result = longFunctionName(param1, param2, param3,
                                param4, param5);

// Bad
const result = longFunctionName(param1, param2, param3, param4, param5, param6);
```

**Component Props**: Always use interfaces
```typescript
// Good
interface CampaignCardProps {
  id: number;
  title: string;
  status: 'draft' | 'running' | 'completed';
  progress?: number;
  onDelete?: () => void;
}

export const CampaignCard: React.FC<CampaignCardProps> = ({
  id,
  title,
  status,
  progress,
  onDelete,
}) => {
  // Implementation
};

// Bad
export const CampaignCard = ({ id, title, status, progress, onDelete }) => {
  // Implementation
};
```

**Hooks Documentation**: Comment complex hooks
```typescript
// Fetch campaigns for current tenant with auto-refresh
const { data, isLoading, error, refetch } = useQuery({
  queryKey: ['campaigns', tenantId],
  queryFn: () => api.getCampaigns(tenantId),
  refetchInterval: 30000, // Refresh every 30 seconds
});
```

### Database (SQL)

**Naming**: snake_case for tables and columns
```sql
-- Good
CREATE TABLE campaigns (
  id SERIAL PRIMARY KEY,
  tenant_id INTEGER NOT NULL REFERENCES tenants(id),
  name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  is_active BOOLEAN DEFAULT true
);

-- Bad
CREATE TABLE Campaign (
  ID int,
  TenantID int,
  Name varchar(255)
);
```

**Constraints**: Always include
```sql
-- Good
CREATE TABLE email_accounts (
  id SERIAL PRIMARY KEY,
  tenant_id INTEGER NOT NULL REFERENCES tenants(id),
  email VARCHAR(255) NOT NULL,
  provider VARCHAR(50) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(tenant_id, email),
  CHECK(provider IN ('gmail', 'outlook', 'smtp'))
);

-- Bad
CREATE TABLE email_accounts (
  id SERIAL,
  tenant_id INTEGER,
  email VARCHAR(255),
  provider VARCHAR(50)
);
```

## 📝 Comments & Documentation

### When to Comment
✅ **DO Comment**:
- Complex algorithms or business logic
- Non-obvious design decisions
- Workarounds or temporary solutions
- Integration with external APIs
- Security or performance considerations

❌ **DON'T Comment**:
- Obvious code that reads like English
- Method names that explain their purpose
- Setup/initialization that's self-explanatory

### Comment Format
```python
# BAD: Restates obvious code
count = count + 1  # Increment count

# GOOD: Explains why
count += 1  # Skip validation entries (they're counted separately in audit log)

# EXCELLENT: Explains complex logic
# Haversine formula: calculates great-circle distance between two points
# on a sphere given their longitudes and latitudes
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    pass
```

### TODO Comments
Include date and author:
```python
# TODO [2025-10-30] [Claude]: Implement OAuth2 token refresh when token expires
# TODO [2025-10-30] [Claude]: Add rate limiting for email sending (currently 100/hour)
```

## 🧪 Testing Standards

### Test File Organization
```
tests/
├── conftest.py                 # Shared fixtures
├── unit/
│   ├── test_models.py
│   ├── test_services.py
│   └── test_utils.py
├── integration/
│   ├── test_campaign_workflow.py
│   └── test_email_sending.py
└── e2e/
    └── test_campaign_progress.py
```

### Test Naming
```python
# Good: Describes behavior in plain English
def test_create_campaign_with_valid_data_returns_200():
    pass

def test_create_campaign_without_authentication_returns_401():
    pass

def test_campaign_respects_tenant_isolation():
    pass

# Bad: Vague or incomplete
def test_create_campaign():
    pass

def test_returns_200():
    pass
```

### Test Structure: Arrange-Act-Assert
```python
@pytest.mark.asyncio
async def test_delete_campaign_removes_associated_emails(async_session):
    # Arrange
    tenant = await create_test_tenant(async_session)
    campaign = await create_test_campaign(async_session, tenant_id=tenant.id)
    await create_test_emails(async_session, campaign_id=campaign.id, count=5)

    # Act
    await campaign_service.delete_campaign(campaign.id, tenant_id=tenant.id)

    # Assert
    remaining = await async_session.execute(
        select(Email).where(Email.campaign_id == campaign.id)
    )
    assert remaining.scalars().all() == []
```

### Multi-Tenant Testing
Always verify tenant isolation:
```python
@pytest.mark.asyncio
async def test_campaign_list_respects_tenant_boundaries(async_session):
    """Verify tenant can only see their own campaigns."""
    # Arrange
    tenant1 = await create_test_tenant(async_session)
    tenant2 = await create_test_tenant(async_session)
    campaign1 = await create_test_campaign(async_session, tenant_id=tenant1.id)
    campaign2 = await create_test_campaign(async_session, tenant_id=tenant2.id)

    # Act
    campaigns = await campaign_service.list_campaigns(tenant_id=tenant1.id)

    # Assert
    assert len(campaigns) == 1
    assert campaigns[0].id == campaign1.id
    assert campaign2.id not in [c.id for c in campaigns]
```

### Coverage Requirements
- **Critical paths** (authentication, email sending, payment): 100%
- **Business logic**: 85%+
- **Utilities**: 70%+
- **Views/Components**: UI logic only (not render tests)

### Running Tests
```bash
# All tests
pytest

# Specific directory
pytest tests/unit/
pytest tests/integration/

# Specific file
pytest tests/unit/test_models.py

# Specific test
pytest tests/unit/test_models.py::test_campaign_creation

# With coverage
pytest --cov=src tests/

# Specific coverage
pytest --cov=src.services tests/
```

## 🔄 Git Workflow

### Branch Naming
```
feature/[feature-name]          # New features
fix/[bug-name]                  # Bug fixes
refactor/[scope]                # Refactoring
docs/[doc-type]                 # Documentation
test/[test-scope]               # Test improvements
```

### Commit Message Format
Use conventional commits:
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation change
- `style`: Code style (formatting, missing semicolons, etc.)
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `test`: Adding or updating tests
- `chore`: Build, dependency, or tooling changes

**Examples**:
```
feat(campaigns): add search and filtering by status

- Implement full-text search on campaign name
- Add status filter (draft, running, completed)
- Add pagination (default 20 per page)

Closes #123
```

```
fix(auth): correct JWT token expiration validation

JWT tokens were being accepted even after expiration.
Now properly validates exp claim against current time.

Fixes #456
```

```
docs(api): add email sending endpoint examples

Added comprehensive examples for POST /campaigns/{id}/send
including success and error response formats.
```

### Commit Best Practices
- ✅ One logical change per commit
- ✅ Commits should compile/pass tests individually
- ✅ Use present tense ("add" not "added")
- ✅ Reference issues/PRs in footer
- ✅ Keep messages concise but descriptive
- ❌ Never: Force push to main
- ❌ Never: Mix multiple unrelated changes
- ❌ Never: Commit with debug statements

## 🔐 Security & Credentials

### Environment Variables
```python
# Good: Use config class for all secrets
from src.core.config import Settings

settings = Settings()
DATABASE_URL = settings.database_url  # From env var
API_KEY = settings.google_api_key     # From env var

# Bad: Hardcoded secrets
DATABASE_URL = "postgresql://user:password@localhost/db"
API_KEY = "sk_live_abc123xyz"
```

### Credentials in Tests
```python
# Good: Use fixtures with test credentials
@pytest.fixture
def test_google_credentials():
    return {
        "type": "service_account",
        "project_id": "test-project",
        # ... other fields
    }

async def test_google_auth(test_google_credentials):
    # Use fixture
    pass

# Bad: Hardcode test credentials
async def test_google_auth():
    creds = {
        "token": "ya29.actualtoken123",  # EXPOSED!
        "refresh_token": "1//real_refresh_token",  # EXPOSED!
    }
    pass
```

### API Keys in Code
- ❌ NEVER commit real API keys
- ❌ NEVER commit .env files
- ✅ Use `.env.example` with placeholder values
- ✅ Document required environment variables
- ✅ Rotate keys immediately if accidentally committed

## 🚀 Performance Considerations

### Database Queries
```python
# Good: Use async + batch operations
emails = await session.execute(
    select(Email).where(Email.campaign_id == campaign_id).limit(100)
)
results = emails.scalars().all()

# Bad: Multiple queries in loops
for email in campaign.emails:  # N+1 query problem!
    email.sent_count = calculate_sent(email.id)
```

### API Pagination
```python
# Always paginate large result sets
def list_campaigns(
    tenant_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> List[CampaignResponse]:
    """List campaigns with pagination."""
    # Implementation
    pass
```

### Caching
```python
# Use Redis for frequently accessed data
async def get_campaign(campaign_id: int, tenant_id: int) -> Campaign:
    # Check cache first
    cached = await redis.get(f"campaign:{campaign_id}:{tenant_id}")
    if cached:
        return Campaign(**json.loads(cached))

    # Query database
    campaign = await session.get(Campaign, campaign_id)

    # Cache for 5 minutes
    await redis.setex(
        f"campaign:{campaign_id}:{tenant_id}",
        300,
        campaign.model_dump_json()
    )

    return campaign
```

## 📋 Pre-Commit Checklist

Before committing code:

### Code Quality
- [ ] No `print()`, `console.log()`, or `debugger` statements
- [ ] No hardcoded credentials or API keys
- [ ] No commented-out code blocks
- [ ] Follows naming conventions (snake_case, PascalCase)
- [ ] Type hints on all functions (Python)
- [ ] Props interfaces on all components (TypeScript)

### Testing
- [ ] New code has corresponding tests
- [ ] All tests pass locally (`pytest`, `npm test`)
- [ ] Multi-tenant isolation verified (if applicable)
- [ ] No test files left in wrong directories

### Documentation
- [ ] Docstrings added to public functions
- [ ] Comments explain "why", not "what"
- [ ] README updated if adding features
- [ ] API documentation updated

### Git
- [ ] Meaningful commit message with type and scope
- [ ] Related issue/PR referenced in footer
- [ ] No merge conflicts left unresolved
- [ ] No untracked files except in `.github/claude/temp/`

### Database (if applicable)
- [ ] Migration file created (Alembic)
- [ ] Migration tested with upgrade/downgrade
- [ ] Schema changes documented
- [ ] Backwards compatibility considered

## 🔍 Code Review Self-Checklist

When finishing a feature, review as if someone else wrote it:

1. **Does the code do what it claims?** - Read tests first
2. **Is it understandable?** - Would a new developer get it?
3. **Are there edge cases?** - Empty lists, null values, errors?
4. **Is it performant?** - Any N+1 queries or unnecessary loops?
5. **Is it secure?** - Proper auth/tenant checks?
6. **Is it maintainable?** - Good structure, no duplication?
7. **Is it consistent?** - Follows project patterns?
8. **Are there tests?** - Happy path and error cases?

## 🎓 Learning from Code Reviews

After completing development, consider:
- What patterns did I follow?
- What patterns should I have followed?
- What would I do differently next time?
- Update `.github/claude/KNOWLEDGE_BASE.md` with insights

---

**Last Updated**: October 30, 2025
**Applies To**: All development activities
**Maintained By**: Claude + Project Team
