# Claude Code - Core Instructions for Autonomous Development

> **Purpose**: This document guides Claude's autonomous development workflow for the SaaS email prospection platform. Read this before any significant task.

## 🧹 Cleanup Policy

**CRITICAL**: At the end of EVERY task execution, always:

1. **Delete temporary files created during execution**
   ```bash
   node .github/cleanup-temp.js
   ```

2. **Where to create temp files**
   - ✅ All temp files → `.github/temp/`
   - ✅ Temp test files → `.github/temp/tests/`
   - ✅ Scratch/work files → `.github/temp/scratch/`
   - ❌ NEVER leave temp files in project root
   - ❌ NEVER leave temp files in any other location

3. **What gets cleaned**
   - All files in `.github/temp/`
   - Files matching: `*.tmp`, `*.temp`, `.claude-work-*`
   - Test result files: `test-results-*.json`

4. **When to cleanup**
   - ✅ At END of every task (before marking complete)
   - ✅ Before stopping services (after `.\stop.ps1`)
   - ✅ Before committing (git should see clean directory)

**Example Workflow:**
```bash
# Do your work
[create files in .github/temp/]

# Before finishing
node .github/cleanup-temp.js

# Verify clean
git status  # Should show no new untracked files in .github/

# Now safe to commit or stop services
```

## 🧠 Thinking Process

Before acting on any request, always follow this mental framework:

### 1. **Understand the Request**
- What is explicitly being asked?
- What are the implicit requirements?
- What dependencies or side effects exist?
- Are there any ambiguities that need clarification?

### 2. **Gather Context**
- Read `.github/claude/KNOWLEDGE_BASE.md` for project context
- Consult `.github/claude/WORKFLOW_RULES.md` for conventions
- Review `.github/claude/MCP_AUTOMATION.md` for available tools
- Check recent git history for related changes

### 3. **Plan the Approach**
- Break the task into logical steps
- Identify interdependencies between steps
- Estimate resources and time
- Consider alternative approaches
- Identify potential issues before they occur

### 4. **Verify Against Guidelines**
- Does the approach respect project conventions?
- Are we following the file organization rules?
- Is the code quality meeting standards?
- Are we using appropriate tools (MCP, bash, etc.)?

### 5. **Execute Methodically**
- Use `TodoWrite` to track complex tasks
- Test each component in isolation
- Document decisions and rationales
- Preserve git history with meaningful commits

### 6. **Validate Quality**
- Run appropriate tests
- Check code meets style standards
- Verify the original objective is met
- Confirm no regressions occurred

## 📋 Project Context at a Glance

**Project Type**: Multi-tenant SaaS email prospection platform
**Frontend**: React 19 + TypeScript (Vite)
**Backend**: FastAPI (Python 3.11) + AsyncPG + SQLAlchemy
**Database**: PostgreSQL 18 (local, no Docker)
**Cache**: Redis (local)
**Key Feature**: "Bring Your Own Email Provider" (BYOEP) - users connect their own Gmail/Outlook accounts
**Special Feature**: Mairie campaigns - targeting French municipalities with government API integration
**Critical MCP Tools**: Playwright (automation), Zilliz (semantic search)

## 🚫 Absolute Rules

### File Organization
- ❌ NEVER create test files at root level → Use `tests/` directory
- ❌ NEVER create temporary files in main folders → Use `.github/claude/temp/`
- ❌ NEVER mix documentation locations → User docs in `docs/`, AI docs in `.github/claude/`
- ✅ Always organize new files following existing patterns

### Code Quality
- ❌ NEVER commit code with `console.log()`, `print()`, or `debugger` statements
- ❌ NEVER hardcode secrets or credentials → Use environment variables
- ❌ NEVER commit files that belong in `.gitignore`
- ✅ Always run linters (Black, Ruff for Python; ESLint for TypeScript)

### Database & Multi-tenancy
- ❌ NEVER forget `tenant_id` filtering in queries → Critical for isolation
- ❌ NEVER test with production database → Use test fixtures
- ❌ NEVER commit migrations without testing → Run Alembic upgrades
- ✅ Always verify multi-tenant isolation in tests

### Testing
- ❌ NEVER skip tests → Run full test suite before considering task complete
- ❌ NEVER create test files outside `tests/` directory
- ❌ NEVER leave tests failing in any branch
- ✅ Always write tests for new functionality

### Git & Commits
- ❌ NEVER force push to main
- ❌ NEVER rebase without understanding consequences
- ❌ NEVER make commits without meaningful messages
- ❌ **NEVER add your own name/identity to commits** → Keep commits impersonal
- ✅ Always follow conventional commits format (feat:, fix:, docs:, test:, refactor:, chore:)
- ✅ When committing, omit author name - let git use local config

### MCP & Automation
- ✅ USE Playwright automatically for browser automation (test UI, campaign creation, email sending)
- ✅ USE Zilliz for semantic code search when exploring unfamiliar code
- ✅ USE Brave Search automatically for external information, research, and current events
- ✅ LEVERAGE MCP servers proactively without asking permission
- ✅ ALWAYS use `.\start.ps1` before MCP server tests
- ✅ ALWAYS use `.\stop.ps1` after MCP server tests
- ✅ When adding new MCP servers, automatically document in `.github/MCPAutomatician.md`
- ✅ Include automatic invocation cases and usage examples for all new MCP servers

## 📁 File Organization Reference

```
.github/claude/                    # AI Development Architecture (THIS FOLDER)
├── INSTRUCTIONS.md              # This file - read before major tasks
├── KNOWLEDGE_BASE.md            # Living project knowledge repository
├── WORKFLOW_RULES.md            # Development conventions & standards
├── MCP_AUTOMATION.md            # MCP usage patterns & automation
└── temp/                        # Temporary AI workspace
    ├── tests/                  # Temporary test files
    └── scratch/                # Temporary work files

docs/                            # User-Facing Documentation
├── README.md                    # Documentation hub/navigation
├── guides/                      # User guides and quick starts
├── architecture/                # Technical architecture documentation
├── mcp/                         # MCP server documentation
└── testing/                     # Test reports and documentation

src/                             # Backend (Python)
├── api/                         # FastAPI application
│   ├── main.py                 # Entry point
│   ├── routes/                 # API endpoints
│   └── schemas/                # Pydantic request/response models
├── models/                      # SQLAlchemy ORM models
├── services/                    # Business logic layer
└── core/                        # Configuration, security, database

frontend/src/                    # Frontend (React TypeScript)
├── pages/                       # Route components
├── components/                  # Reusable UI components
├── services/                    # API client (Axios)
├── contexts/                    # React context (auth, etc.)
└── types/                       # TypeScript interfaces

tests/                           # Test Suite
├── unit/                        # Unit tests
├── integration/                 # Integration tests
├── e2e/                         # End-to-end tests
└── conftest.py                 # Pytest fixtures

scripts/                         # Utility scripts
├── test/                        # Manual test scripts (not pytest)
└── [other scripts]

.github/copilot-instructions.md # Existing AI assistant guidelines (reference)
.github/DOCUMENTATION.md        # Comprehensive technical docs (reference)
```

## 🔄 Before Each Development Session

1. Read `.github/claude/KNOWLEDGE_BASE.md` to refresh project context
2. Check `.github/claude/WORKFLOW_RULES.md` for relevant conventions
3. Review any open todos from previous sessions
4. Verify the current git branch and status
5. Confirm access to all necessary tools (MCP servers, databases)

## 🎯 When Starting a Task

### For Bug Fixes
1. Identify and read the affected code files
2. Understand the root cause (not just symptoms)
3. Write a test that reproduces the bug
4. Implement the fix
5. Verify the test passes
6. Check for similar issues elsewhere
7. Run full test suite

### For New Features
1. Understand requirements completely (ask if ambiguous)
2. Design the solution (API contract, database schema, UI layout)
3. Implement backend first, then frontend
4. Write tests as you go
5. Test end-to-end with Playwright if UI-related
6. Document any new APIs or configuration

### For Refactoring
1. Identify the scope clearly
2. Write tests for current behavior first
3. Refactor while maintaining tests
4. Ensure no functionality changes
5. Update documentation if interfaces change

### For Documentation
1. Use Markdown with clear formatting
2. Include code examples for technical docs
3. Place in appropriate `docs/` subdirectory
4. Keep root README.md as navigation hub
5. Update docs/README.md index when adding new docs

## 🔍 Code Review Checklist

Before marking any coding task as complete:

- [ ] Code follows project conventions (naming, style, structure)
- [ ] No debug statements left (print, console.log, debugger)
- [ ] Tests written and passing
- [ ] No new linting errors (Black, Ruff, ESLint, MyPy)
- [ ] Multi-tenant isolation verified (if database-related)
- [ ] Git history is clean with meaningful commits
- [ ] Documentation updated (docstrings, API docs, README)
- [ ] No untracked files left except in `.github/claude/temp/`
- [ ] Full test suite passes

## 🛠️ Common Commands Reference

### Backend (Python)
```bash
# Install dependencies
pip install -r requirements.txt

# Run backend dev server
python -m uvicorn src.api.main:app --reload

# Run tests
pytest
pytest tests/unit/
pytest tests/integration/

# Code quality
black src/ tests/
ruff check src/ tests/ --fix
mypy src/

# Database migrations
alembic upgrade head
alembic downgrade -1
```

### Frontend (TypeScript)
```bash
# Install dependencies
cd frontend && npm install

# Run dev server
npm run dev

# Build
npm run build

# Linting
npm run lint
npm run lint:fix

# Type checking
npx tsc --noEmit
```

### Database
```bash
# Start PostgreSQL (local)
pg_ctl -D "C:\Program Files\PostgreSQL\18\data" start

# Start Redis (local)
redis-server

# Connect to database
psql -U emailsaas_user -d emailsaas -h localhost
```

### Startup/Shutdown
```bash
# Start entire stack (including MCP servers)
.\start.ps1

# Stop entire stack (including MCP servers)
.\stop.ps1
```

### MCP Server Testing
```bash
# Always use start.ps1 first to initialize all services
.\start.ps1

# Load and verify MCP configuration
cd .github
node load-mcp-config.js

# Test specific MCP server
node test_brave_mcp_server.js

# When done, always cleanup
.\stop.ps1
```

## 💡 Pro Tips for Autonomous Development

1. **Use TodoWrite liberally** - Break complex tasks into tracked steps
2. **Read git diffs carefully** - Understand what changed before and after your changes
3. **Test early and often** - Don't wait until "complete" to test
4. **Document as you go** - Update docs while changes are fresh
5. **Commit frequently** - Small, logical commits are easier to understand
6. **Ask for clarification** - Use AskUserQuestion when requirements are ambiguous
7. **Leverage MCP tools** - They make automation and search much faster
8. **Keep git history clean** - One feature = one focused set of commits
9. **Update KNOWLEDGE_BASE.md** - Record discoveries and decisions
10. **Review existing code patterns** - Follow established conventions

## 🚀 How to Approach Unknown Code

1. **Use semantic search** → Zilliz MCP to find similar patterns
2. **Read the tests** → Tests often explain expected behavior
3. **Trace the flow** → Start from entry point (API route, component mount)
4. **Check git history** → Recent commits explain recent changes
5. **Look for docstrings** → Functions should explain their purpose
6. **Ask questions** → Use AskUserQuestion if truly stuck

## 📞 When to Ask for Help

Use `AskUserQuestion` when:
- Requirements are ambiguous or conflicting
- Need to choose between multiple valid approaches
- Uncertain about architectural impact of a change
- Project conventions aren't clear for a specific situation
- Need to understand user/business requirements

Don't guess - ask and get clear direction.

## 🤖 MCP Server Management

### When Adding New MCP Servers

Every time a new MCP server is requested, follow this process:

1. **Update `.github/mcp.json`**
   - Add server configuration with `${VAR_NAME}` variable references
   - Keep configuration clean and minimal

2. **Document in `.github/secrets.env.example`**
   - Add complete API key documentation
   - Include links to where to get credentials
   - Document rate limits and pricing
   - Add example configuration

3. **Update `.github/MCPAutomatician.md`**
   - Add server entry with capabilities
   - Define at least 3-5 automatic invocation cases
   - Include trigger conditions and real-world examples
   - Document testing procedure
   - Update the decision logic diagram

4. **Create/Update Tests**
   - Build server startup test (e.g., `test_servername.js`)
   - Validate configuration loading works
   - Test at least one capability

5. **Always Run Tests with start/stop**
   ```bash
   .\start.ps1                    # Start all services
   node .github/load-mcp-config.js # Verify config loads
   node .github/test_newserver.js  # Test the server
   .\stop.ps1                     # Stop all services
   ```

6. **Document Automatic Invocation**
   - Be proactive: Use new MCP servers automatically when their use case arises
   - Don't wait for explicit user request if conditions match MCPAutomatician rules
   - Example: User asks about competitors → Automatically use Brave Search

### MCP Server Reference

See `.github/MCPAutomatician.md` for:
- All available MCP servers
- Their capabilities and automatic invocation rules
- Real-world usage examples
- Testing procedures
- How to add new servers

### Active MCP Servers

**Brave Search** (Web Research)
```
Trigger: External information, competitive research, current events
Invocation: Automatic when user asks about external topics
Test: node .github/test_brave_mcp_server.js
```

**Claude Context** (Code Search)
```
Trigger: Code navigation, pattern matching, architecture questions
Invocation: Automatic when exploring codebase
Note: Requires Zilliz connection
```

**Playwright** (UI Testing)
```
Trigger: Browser automation, UI testing, visual validation
Invocation: Automatic when UI changes made
Test: npm test -- --playwright
```

## 🎓 Continuous Learning

After completing tasks, update `.github/claude/KNOWLEDGE_BASE.md` with:
- Important discoveries about project architecture
- Common patterns and conventions observed
- Known issues and their solutions
- Recent decisions and their rationale

Also update `.github/MCPAutomatician.md` when:
- New MCP servers are added
- New automatic invocation patterns are discovered
- Usage examples improve or change

This keeps both knowledge bases current and helps future Claude sessions work more effectively.

---

**Last Updated**: October 30, 2025
**Status**: Production - Active Use
**Applies To**: All development tasks in this project
**MCP Version**: 1.0 - All servers configured and active
