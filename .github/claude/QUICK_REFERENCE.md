# Quick Reference - Before Every Development Session

> **Read this in 2 minutes before starting any significant development work**

## ⚡ Critical Rules - NEVER Violate

1. **Multi-tenant isolation** → Always filter by `tenant_id` in database queries
2. **Secrets** → NEVER hardcode credentials → Use environment variables
3. **Test organization** → ALL tests go in `tests/` directory, NOT root level
4. **Temporary files** → Use `.github/claude/temp/`, NOT root directories
5. **File locations** → User docs in `docs/`, AI docs in `.github/claude/`
6. **Git** → NO force pushes to main, meaningful commit messages required

## 📚 Essential Documents (Read These First)

| Document | Purpose | When to Read |
|----------|---------|--------------|
| `.github/claude/INSTRUCTIONS.md` | Core behavior guidelines | Every major task |
| `.github/claude/WORKFLOW_RULES.md` | Code standards | Before coding |
| `.github/claude/KNOWLEDGE_BASE.md` | Project context | When unfamiliar with topic |
| `.github/claude/MCP_AUTOMATION.md` | Available tools | When automating |

## 🚀 Project At a Glance

**Type**: Multi-tenant SaaS email platform
**Frontend**: React 19 + TypeScript (Vite) @ `http://localhost:5173`
**Backend**: FastAPI + Python 3.11 @ `http://localhost:8000`
**Database**: PostgreSQL 18 (local, no Docker) @ `localhost:5432`
**Cache**: Redis (local) @ `localhost:6379`
**Key Feature**: "Bring Your Own Email Provider" (BYOEP)
**Special**: Mairie (French municipality) campaign system

## 🔐 Security Checklist

Before committing code:
- [ ] No hardcoded secrets (API keys, tokens, passwords)
- [ ] No credentials in test files
- [ ] Environment variables used for all config
- [ ] `.env` files in `.gitignore`

## 🧪 Testing Checklist

- [ ] Write tests for new features
- [ ] Multi-tenant isolation verified (if DB-related)
- [ ] Run: `pytest`
- [ ] Check coverage: `pytest --cov=src tests/`

## 💻 Code Quality Checklist

**Python (Backend)**:
```bash
black src/ tests/
ruff check --fix
mypy src/
pytest
```

**TypeScript (Frontend)**:
```bash
npm run lint:fix
npx tsc --noEmit
```

## 🤖 MCP Tools Available

- **Playwright** → Browser automation, UI testing, screenshots
- **Zilliz** → Semantic code search, understanding unfamiliar code

Use these automatically when they solve a problem faster.

## 📁 Quick File Location Reference

```
.github/claude/              ← Your AI development guidelines (READ FIRST!)
├── INSTRUCTIONS.md         ← Core behavior guidelines
├── WORKFLOW_RULES.md       ← Code standards
├── KNOWLEDGE_BASE.md       ← Project knowledge (update after learning!)
├── MCP_AUTOMATION.md       ← Available tools
└── temp/                   ← Temporary work files (tests/, scratch/)

docs/                        ← User-facing documentation
├── README.md               ← Documentation hub
├── mcp/                    ← MCP automation guides
├── guides/                 ← Getting started guides
├── architecture/           ← System design docs
└── testing/                ← Test reports

tests/                       ← All project tests
├── unit/                   ← Unit tests
├── integration/            ← Integration tests
└── e2e/                    ← End-to-end tests

scripts/test/               ← Manual test scripts (examples)
```

## 🎯 Before Each Task

1. **Understand** → What is being asked?
2. **Context** → Read relevant KNOWLEDGE_BASE section
3. **Plan** → Break into steps, use TodoWrite for complex tasks
4. **Check** → Verify plan respects WORKFLOW_RULES.md
5. **Code** → Follow conventions
6. **Test** → Run full test suite
7. **Verify** → Code quality checks pass
8. **Update** → KNOWLEDGE_BASE.md with discoveries

## 🆘 When Stuck

1. **Check KNOWLEDGE_BASE.md** → Search for related topics
2. **Use Zilliz** → Semantic search for similar code patterns
3. **Read tests** → Tests often explain expected behavior
4. **Check git history** → Recent commits explain changes
5. **Ask user** → Use AskUserQuestion when truly unclear

## 🔄 Key Git Commands

```bash
# Check status
git status

# Create feature branch
git checkout -b feature/name

# Commit with type
git commit -m "feat(scope): description"

# Never do this
git push --force              # ❌ FORBIDDEN on main!
```

## 📞 Important URLs

- **Frontend Dev**: `http://localhost:5173`
- **Backend API**: `http://localhost:8000`
- **API Docs**: `http://localhost:8000/docs`
- **Database**: `postgresql://emailsaas_user:emailsaas_pass@localhost:5432/emailsaas`

## 💡 Pro Tips

1. **Use TodoWrite** for complex multi-step tasks
2. **Consult KNOWLEDGE_BASE.md** - it's your best friend
3. **Use MCP tools** - they're there to help
4. **Write tests first** for new features
5. **Keep commits small** - one feature per commit
6. **Document decisions** - update KNOWLEDGE_BASE
7. **Ask questions** - use AskUserQuestion liberally

## 🚫 Common Mistakes to Avoid

- ❌ Testing without checking multi-tenant isolation
- ❌ Creating files outside organized directories
- ❌ Committing debug statements (`print()`, `console.log()`)
- ❌ Forgetting `tenant_id` in database queries
- ❌ Skipping tests
- ❌ Force pushing
- ❌ Hardcoding secrets

---

**Remember**: Read INSTRUCTIONS.md for detailed behavioral guidelines, WORKFLOW_RULES.md for coding standards, and KNOWLEDGE_BASE.md when you need context.

**Happy coding!** 🚀
