# CLAUDE.md - Autonomous MCP Server Usage Instructions

This file provides guidance to Claude Code when working with this repository. Claude should be **autonomous** in using MCP servers without being explicitly asked.

## 🤖 Autonomous MCP Server Usage

Claude has access to the following MCP servers configured in `.github/mcp.json`:

### Available MCP Servers

| Server | Purpose | Auto-Use Trigger |
|--------|---------|------------------|
| **playwright** | Web automation, browser testing | When testing web interfaces or automating browser interactions |
| **claude-context** | Semantic search in vector database | When needing to search code semantically or find similar patterns |
| **brave-search** | Web search capabilities | When research or external information is needed |
| **railway** | Railway deployment management | When deploying, managing infrastructure, or checking deployment status |
| **context7** | Advanced context management | When organizing complex information or managing project context |

## 📋 Autonomy Rules

**Claude should automatically use MCP servers when:**

1. **Searching Code**: Need to find files, patterns, or understand codebase
   - Auto-trigger: Semantic search needed → Use `claude-context`
   - Auto-trigger: File pattern search → Use Glob/Grep tools first, then `claude-context` if not found

2. **Web Information**: External research or documentation needed
   - Auto-trigger: Need current docs, API reference → Use `brave-search`
   - Auto-trigger: Need to verify external service status → Use `brave-search`

3. **Browser Testing**: Testing web interfaces or automation
   - Auto-trigger: Need to test UI, run E2E tests, verify browser behavior → Use `playwright`

4. **Deployment**: Infrastructure or deployment tasks
   - Auto-trigger: Deploy, check status, manage production → Use `railway`

5. **Context Management**: Complex project information
   - Auto-trigger: Need to organize and retrieve complex information → Use `context7`

## 🎯 Decision-Making During Reflection

**When Claude is thinking through a solution:**

1. **Identify Information Gap**: "I need X to solve this problem"
2. **Check Available Tools**: "Can an MCP server provide this?"
3. **Use Autonomously**: If yes → Use the MCP server immediately without asking user
4. **Proceed with Solution**: Continue implementation with the gathered information

**Example**:
- User: "Help me with the optimizer"
- Claude thinks: "I need to understand the codebase structure"
- Claude acts: Automatically uses `claude-context` to search project
- Claude explains: "I found the solver.py... Let's proceed with..."

## 🚀 No Permission Needed

- **Do NOT ask permission** to use MCP servers
- **Do NOT say** "Would you like me to search...?"
- **Do NOT ask** "Should I use Brave to look this up?"
- **Just use them** when needed, then proceed naturally

## 🔌 Configuration Details

- **Config Location**: `.github/mcp.json`
- **Secrets Location**: `.github/secrets.env`
- **Loader Script**: `.github/load-mcp-config.js`
- **All servers are pre-configured** and ready to use

## 📊 MCP Server Details

### claude-context
- **Use for**: Finding code patterns, semantic search across project
- **Command**: `npx @zilliz/claude-context-mcp`
- **Requires**: OPENAI_API_KEY, ZILLIZ credentials
- **Auto-trigger**: When searching for "how does X work in codebase?"

### brave-search
- **Use for**: External web research, API documentation, service status
- **Command**: `npx @modelcontextprotocol/server-brave-search`
- **Requires**: BRAVE_API_KEY
- **Auto-trigger**: When external information is needed

### playwright
- **Use for**: Browser testing, UI validation, automation
- **Command**: `npx @playwright/mcp`
- **Auto-trigger**: When testing web interfaces or need browser interaction

### railway
- **Use for**: Infrastructure management, deployment status
- **Command**: `npx @jasontanswe/railway-mcp`
- **Requires**: RAILWAY_API_TOKEN
- **Auto-trigger**: When managing deployments or infrastructure

### context7
- **Use for**: Advanced context management and information organization
- **Command**: `npx @context7/mcp-server`
- **Requires**: CONTEXT7_API_KEY
- **Auto-trigger**: When managing complex multi-file changes or context

## 💡 Decision Flow

```
Task Identified
  ↓
Information Needed?
  ├─ YES → Use MCP Server
  │         (No permission needed)
  │         ↓
  │    Gather Information
  │         ↓
  │    Proceed with Implementation
  │
  └─ NO → Proceed Directly
          with Implementation
```

## ✅ Implementation Guidelines

### Before Writing Code:
- [ ] Do I need external information? → Use `brave-search`
- [ ] Do I need to understand the codebase? → Use `claude-context`
- [ ] Do I need to validate something? → Use appropriate MCP tool

### During Implementation:
- [ ] Testing required? → Use `playwright` for UI testing
- [ ] Deployment needed? → Use `railway`
- [ ] Complex coordination? → Use `context7`

### After Implementation:
- [ ] Run tests
- [ ] Verify in target environment
- [ ] Commit with clear message

## 🔐 Security Notes

- All API keys are stored in `.github/secrets.env` (never committed)
- MCP servers are isolated and sandboxed
- No sensitive data should be passed to external services
- Use local tools (Glob, Grep, Read) for sensitive code analysis

## 📝 Project Context

This is a **Vehicle Routing Problem (VRP) optimizer** using Google OR-Tools:
- Capacitated Vehicle Routing with Time Windows (CVRPTW)
- Vehicle reloading capability
- Hub-based cargo transfers
- Multi-objective optimization (distance, time, balance)

**Key directories**:
- `/optimizer/` - Python solver implementation
- `/.github/` - Configuration and documentation
- `/docs/` - Project documentation

## 🎓 When to Use Each Server

| Scenario | Server | Why |
|----------|--------|-----|
| "How does the solver work?" | claude-context | Semantic search in codebase |
| "What's the latest OR-Tools API?" | brave-search | Current documentation |
| "Test the UI" | playwright | Browser automation |
| "Deploy to production" | railway | Infrastructure management |
| "Understand multi-file changes" | context7 | Complex context tracking |
| "Find the config file" | Glob/Grep first, then claude-context | Local search first |

## ⚡ Quick Reference

```
Need to SEARCH code?     → claude-context
Need EXTERNAL info?      → brave-search
Need to TEST UI?         → playwright
Need to DEPLOY?          → railway
Need COMPLEX CONTEXT?    → context7
```

---

**Remember**: You (Claude) are autonomous. Use MCP servers proactively when you identify information needs. The user doesn't need to ask - just use them naturally as part of your problem-solving process.
