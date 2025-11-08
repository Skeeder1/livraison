# MCPAutomatician - Automated MCP Server Integration & Usage Guide

This document catalogs all available MCP servers and their automation capabilities, including automatic use cases where these tools should be invoked without explicit user requests.

## ⚠️ Important: Cleanup Policy

**After each task execution with MCP servers:**
```bash
# Always cleanup temporary files before finishing
node .github/cleanup-temp.js
```

All temporary files are created in `.github/temp/` only:
- Test files → `.github/temp/tests/`
- Work files → `.github/temp/scratch/`
- Must cleanup before task completion

See `.github/claude/INSTRUCTIONS.md` for cleanup policy details.

---

## 📋 Quick Reference Matrix

| MCP Server | Auto-Invoke | Category | Primary Use Case | Auto-Trigger |
|------------|------------|----------|------------------|--------------|
| Playwright | No | Testing/Automation | UI testing, screenshots | Code changes affecting UI |
| Claude Context | Yes | RAG/Search | Semantic search in code | Documentation queries |
| Brave Search | Yes | Research/Search | Web research | External info needed |

---

## 🎯 MCP Server Catalog

### 1. Brave Search (@modelcontextprotocol/server-brave-search)

**Status**: ✅ Configured and Active

#### Capabilities
- Web search with 20 result limit
- Local business search
- News search
- Pagination support (offset)
- Content filtering

#### API Endpoint
- **Service**: Brave Search API
- **Rate Limits**: Standard tier - check Brave dashboard
- **Authentication**: API Key

#### Automatic Invocation Cases

**✅ Case 1: External Information Required**
```
Trigger: User asks about current events, latest news, or recent developments
Action: Automatically invoke brave_web_search
Example Query: "What are the latest Claude AI announcements?"
Result: Fetch current information from web
```

**✅ Case 2: Business Research**
```
Trigger: User asks to research competitors, technologies, or services
Action: Automatically invoke brave_web_search
Example Query: "Find information about AI vector database pricing"
Result: Gather competitive intelligence
```

**✅ Case 3: Local Business Discovery**
```
Trigger: User needs to find services or businesses nearby
Action: Automatically invoke brave_local_search
Example Query: "Find restaurants in Paris"
Result: Return business listings with ratings and contact info
```

**✅ Case 4: Technology Stack Research**
```
Trigger: User asks about technologies, libraries, frameworks to use
Action: Automatically invoke brave_web_search
Example Query: "What's the best Node.js ORM for PostgreSQL?"
Result: Fetch latest comparisons and reviews
```

**✅ Case 5: Code Examples from Web**
```
Trigger: User asks for code examples or patterns not in codebase
Action: Automatically invoke brave_web_search
Example Query: "TypeScript generics patterns for React components"
Result: Find real-world examples and best practices
```

#### Manual Invocation

Use when:
- User explicitly requests web search
- Need to validate information
- Research specific websites

#### Configuration
```json
{
  "brave-search": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-brave-search"],
    "env": {
      "BRAVE_API_KEY": "${BRAVE_API_KEY}"
    }
  }
}
```

#### Testing
```bash
# Start services
.\start.ps1

# In separate terminal, test Brave search
node .github/test_brave_mcp_server.js

# Stop services
.\stop.ps1
```

---

### 2. Claude Context (@zilliz/claude-context-mcp)

**Status**: ✅ Configured and Active

#### Capabilities
- Semantic search in project files
- Vector embeddings via OpenAI
- RAG (Retrieval-Augmented Generation)
- Code understanding and navigation
- Context injection for AI

#### Services Required
- **OpenAI Embeddings**: For generating vectors
- **Zilliz Cloud**: For vector storage
- **Milvus**: Alternative vector database

#### Automatic Invocation Cases

**✅ Case 1: Complex Code Navigation**
```
Trigger: User asks about code structure, dependencies, or patterns
Action: Automatically invoke claude-context search
Example Query: "How is error handling implemented across the codebase?"
Result: Return relevant code snippets and patterns
```

**✅ Case 2: Feature Implementation Research**
```
Trigger: User asks how to implement similar feature
Action: Automatically invoke claude-context search
Example Query: "Find how user authentication is implemented"
Result: Return authentication code and patterns
```

**✅ Case 3: Architecture Understanding**
```
Trigger: User asks about system architecture or design
Action: Automatically invoke claude-context search
Example Query: "Show me the data flow for email sending"
Result: Return relevant files and architecture diagrams
```

**✅ Case 4: Similar Pattern Matching**
```
Trigger: User needs pattern similar to existing code
Action: Automatically invoke claude-context search
Example Query: "Find similar error handling patterns in API layer"
Result: Return matching patterns from codebase
```

**✅ Case 5: Documentation Generation**
```
Trigger: User asks to document code or generate documentation
Action: Automatically invoke claude-context search
Example Query: "Generate API documentation based on codebase"
Result: Return all relevant API endpoints and schemas
```

#### Manual Invocation

Use when:
- Explicitly requesting semantic search
- Need to find code patterns
- Searching for specific functionality

#### Configuration
```json
{
  "claude-context": {
    "command": "npx",
    "args": ["-y", "@zilliz/claude-context-mcp@latest"],
    "env": {
      "OPENAI_API_KEY": "${OPENAI_API_KEY}",
      "MILVUS_ADDRESS": "${ZILLIZ_CLUSTER_URL}",
      "MILVUS_TOKEN": "${MILVUS_TOKEN}",
      "EMBEDDING_PROVIDER": "OpenAI"
    }
  }
}
```

#### Testing
```bash
# Start services
.\start.ps1

# Test Claude Context indexing and search
# (Requires Zilliz connection)

# Stop services
.\stop.ps1
```

---

### 3. Playwright (@playwright/mcp)

**Status**: ✅ Configured and Active

#### Capabilities
- Browser automation
- UI testing
- Screenshot capture
- Form filling
- DOM navigation
- Network interception

#### Automatic Invocation Cases

**✅ Case 1: Code Changes Affecting UI**
```
Trigger: User modifies UI components or styling
Action: Automatically invoke Playwright for screenshot validation
Example: After CSS changes, capture before/after screenshots
Result: Verify visual changes
```

**✅ Case 2: Frontend Bug Investigation**
```
Trigger: User reports UI issue or bug
Action: Automatically invoke Playwright to reproduce
Example Query: "Why is the login form not submitting?"
Result: Capture screenshots, inspect DOM, identify issue
```

**✅ Case 3: E2E Test Creation**
```
Trigger: User wants to create end-to-end tests
Action: Automatically invoke Playwright
Example: "Test the complete checkout flow"
Result: Generate and run E2E test
```

**✅ Case 4: Cross-Browser Testing**
```
Trigger: User needs to verify browser compatibility
Action: Automatically invoke Playwright with different browsers
Example: "Test if our app works on Firefox and Safari"
Result: Run tests on multiple browsers, capture results
```

**✅ Case 5: Visual Regression Testing**
```
Trigger: Before committing UI changes
Action: Automatically invoke Playwright for regression testing
Example: After component refactor, test visual consistency
Result: Detect unintended visual changes
```

#### Manual Invocation

Use when:
- Explicitly requesting UI testing
- Debugging visual issues
- Recording browser sessions

#### Configuration
```json
{
  "playwright": {
    "command": "npx",
    "args": ["@playwright/mcp@latest"]
  }
}
```

#### Testing
```bash
# Start services
.\start.ps1

# Run Playwright tests
npm test -- --playwright

# Stop services
.\stop.ps1
```

---

## 🤖 Automation Decision Logic

```
User Request
    ↓
Is it asking about external information?
├─ YES → Use Brave Search ✅
│   ├─ Current events? → web_search
│   ├─ Competitors? → web_search
│   └─ Local business? → local_search
│
├─ NO → Is it about code in this project?
│   ├─ YES → Use Claude Context ✅
│   │   ├─ Navigation needed? → semantic_search
│   │   ├─ Pattern matching? → semantic_search
│   │   └─ Documentation? → semantic_search
│   │
│   └─ NO → Is it about UI/testing?
│       ├─ YES → Use Playwright ✅
│       │   ├─ Screenshot needed? → capture
│       │   ├─ DOM inspection? → inspect
│       │   └─ E2E test? → execute
│       │
│       └─ NO → Use standard Claude reasoning
```

---

## 📊 Usage Tracking

### Brave Search Usage
- **Primary**: Research, competitive analysis, current events
- **Average Calls/Session**: 1-3
- **Result Quality**: High (relevant results)
- **Cost**: Per query from API

### Claude Context Usage
- **Primary**: Code navigation, pattern matching, architecture
- **Average Calls/Session**: 2-5
- **Result Quality**: High (semantically relevant)
- **Cost**: OpenAI embeddings + Zilliz storage

### Playwright Usage
- **Primary**: UI testing, visual validation, E2E tests
- **Average Calls/Session**: 1-10 (depending on tests)
- **Result Quality**: Perfect (captures actual behavior)
- **Cost**: Free (no external API)

---

## 🎯 Future MCP Servers

When new MCP servers are added, document them here:

### Server Template (for future additions)

```markdown
### N. Server Name (@vendor/package-name)

**Status**: ⚠️ In Development / ✅ Active / ❌ Deprecated

#### Capabilities
- Feature 1
- Feature 2
- Feature 3

#### Automatic Invocation Cases

**✅ Case 1: Description**
```
Trigger: When to automatically invoke
Action: What this server does
Example: Real-world example
Result: Expected outcome
```

#### Configuration
```json
{ ... }
```

#### Testing
```bash
# How to test
```
```

---

## 🔄 Instructions for Adding New Servers

When you request to add a new MCP server, I will:

1. **Update mcp.json**
   - Add server configuration with variable references
   - Follow naming conventions

2. **Update secrets.env.example**
   - Document all required API keys
   - Include instructions for obtaining credentials
   - Add use cases and examples

3. **Update this MCPAutomatician.md**
   - Add server entry with capabilities
   - Define automatic invocation cases
   - Document testing procedure
   - Update decision logic diagram

4. **Create tests**
   - Build server startup test
   - Validate configuration loading
   - Test capability execution

5. **Update instructions**
   - Show how to use with start/stop.ps1
   - Add examples
   - Document troubleshooting

6. **Verify integration**
   - Run `node .github/load-mcp-config.js`
   - Test each capability
   - Document any issues

---

## ⚡ Quick Start for Development

### Testing MCP Changes

```bash
# 1. Start all services (including MCP servers)
.\start.ps1

# 2. In separate terminal, load configuration
cd .github
node load-mcp-config.js

# 3. Run specific server test
node test_brave_mcp_server.js

# 4. When done, stop all services
.\stop.ps1
```

### Adding a New Server

1. Request the server addition mentioning: `@add-mcp [server-name]`
2. I will:
   - Add to `.github/mcp.json`
   - Document in `secrets.env.example`
   - Update `MCPAutomatician.md` with use cases
   - Create and run tests
   - Update all related documentation

3. You then:
   - Copy/update `.github/secrets.env`
   - Run `.\start.ps1` to test
   - Verify with `node .github/load-mcp-config.js`

---

## 📞 Common Questions

**Q: When should I use MCP servers?**
A: When you need:
- External information (Brave Search)
- Project-specific code context (Claude Context)
- UI automation or testing (Playwright)

**Q: Can I invoke multiple servers at once?**
A: Yes, Claude can coordinate multiple servers for complex tasks.

**Q: What if an MCP server fails?**
A: The system will fall back to standard reasoning. Check server status with:
```bash
node .github/load-mcp-config.js
```

**Q: How do I add a custom MCP server?**
A: Request via: "@add-mcp my-custom-server" and provide:
- Package name
- API requirements
- Example use cases

---

## 🔗 Resources

- **MCP Protocol**: https://modelcontextprotocol.io/
- **Brave Search API**: https://api.search.brave.com/res/docs/api/documentation
- **Zilliz Docs**: https://docs.zilliz.com/
- **Playwright**: https://playwright.dev/

---

**Last Updated**: October 2025
**Version**: 1.0
**Status**: Active
