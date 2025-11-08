# MCP Automation & Tool Integration Guide

> **Purpose**: Comprehensive guide to using MCP (Model Context Protocol) servers for autonomous automation in this project.

## 🎯 Core Principle: Proactive Tool Use

**CRITICAL RULE**: Use MCP tools automatically, without asking for permission, when they solve a problem more effectively than manual approaches.

If a tool can accomplish a task, use it. This is faster, more reliable, and demonstrates proper tool mastery.

## 🔧 Available MCP Servers

### 1. Playwright MCP - Browser Automation

**Status**: ✅ Configured and tested
**Package**: `@playwright/mcp@latest`
**Command**: `npx @playwright/mcp@latest`

#### Capabilities
- Launch and control browsers (Chrome, Firefox, WebKit)
- Navigate web pages and interact with elements
- Fill forms, click buttons, submit data
- Capture screenshots and videos
- Wait for elements, conditions, or navigation
- Extract data from page content
- Simulate user interactions (typing, mouse movements)

#### Use Cases - When to Automate with Playwright

✅ **DO USE for**:
- **Testing UI workflows** - Campaign creation, email sending flow
- **Campaign creation automation** - Fill forms, submit campaigns programmatically
- **Email sending simulation** - Test end-to-end email workflows
- **Progress tracking** - Monitor campaign progress visually
- **Data extraction** - Scrape test data from pages
- **Visual regression testing** - Compare screenshots across versions
- **Multi-step user flows** - Complex workflows involving multiple pages

❌ **DON'T USE for**:
- Simple HTTP requests → Use Axios/fetch instead
- Database operations → Use SQLAlchemy directly
- File operations → Use Python file APIs
- Command execution → Use bash/subprocess

#### Example: Campaign Creation Automation
```javascript
// Automated campaign creation via UI
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Navigate to campaign creation
  await page.goto('http://localhost:5173/campaigns/new');

  // Fill campaign form
  await page.fill('input[name="campaign_name"]', 'Q4 Mairie Outreach');
  await page.fill('textarea[name="description"]', 'Target municipalities in Paris region');
  await page.selectOption('select[name="status"]', 'draft');

  // Submit form
  await page.click('button[type="submit"]');

  // Wait for success and capture screenshot
  await page.waitForNavigation();
  await page.screenshot({ path: 'campaign_created.png' });

  await browser.close();
})();
```

#### MCP Commands Reference
```javascript
// Launch browser
await mcp.invoke('playwright', {
  action: 'launch',
  headless: false  // Set true for CI/testing
});

// Navigate to URL
await mcp.invoke('playwright', {
  action: 'goto',
  url: 'http://localhost:5173'
});

// Fill form field
await mcp.invoke('playwright', {
  action: 'fill',
  selector: 'input[name="email"]',
  text: 'user@example.com'
});

// Click element
await mcp.invoke('playwright', {
  action: 'click',
  selector: 'button.submit'
});

// Wait for element
await mcp.invoke('playwright', {
  action: 'waitForSelector',
  selector: '.success-message',
  timeout: 5000
});

// Get element text
await mcp.invoke('playwright', {
  action: 'textContent',
  selector: '.campaign-status'
});

// Take screenshot
await mcp.invoke('playwright', {
  action: 'screenshot',
  path: 'screenshot.png',
  fullPage: true
});

// Close browser
await mcp.invoke('playwright', {
  action: 'close'
});
```

#### Common Patterns

**Pattern 1: Wait for Element Before Interaction**
```javascript
// Good - Wait for element to appear
await page.waitForSelector('.modal-open', { timeout: 5000 });
await page.fill('input.modal-input', 'data');

// Bad - No waiting, element might not exist yet
await page.fill('input.modal-input', 'data');
```

**Pattern 2: Error Handling**
```javascript
// Good - Handle navigation errors
try {
  await page.goto('http://localhost:5173/campaigns', { waitUntil: 'networkidle' });
} catch (error) {
  console.error('Failed to navigate:', error);
}

// Bad - No error handling
await page.goto('http://localhost:5173/campaigns');
```

**Pattern 3: Headless Mode for Testing**
```javascript
// Production/CI: Use headless
const browser = await chromium.launch({ headless: true });

// Development: Use headed for debugging
const browser = await chromium.launch({ headless: false });
```

---

### 2. Zilliz Claude Context MCP - Semantic Code Search

**Status**: ✅ Configured and tested
**Package**: `@zilliz/claude-context-mcp@latest`
**Command**: `npx -y @zilliz/claude-context-mcp@latest`
**Purpose**: Semantic search for code similarity and exploration

#### Capabilities
- Find similar code patterns across the codebase
- Semantic search (understands meaning, not just keywords)
- Identify code duplication
- Explore unfamiliar code sections
- Find related implementations

#### Use Cases - When to Use Zilliz

✅ **DO USE for**:
- **Learning unfamiliar code** - "Show me how campaign creation works"
- **Finding patterns** - "Where else is multi-tenant filtering done?"
- **Avoiding duplication** - "Does similar email validation exist elsewhere?"
- **Code exploration** - "How is user authentication structured?"
- **Refactoring** - "Find all places where this pattern is used"

❌ **DON'T USE for**:
- Exact keyword search → Use Grep tool instead
- Specific file navigation → Use Read/Glob tools
- Code modification → Use Edit tool
- Execution → Use Bash

#### Example: Finding Tenant Isolation Patterns
```
Query: "Where is tenant_id filtering applied in queries?"
Result: Multiple locations where .where(Model.tenant_id == tenant_id) is used
Use: Understand the multi-tenant filtering pattern used throughout
```

#### When to Use Zilliz vs Other Tools

| Task | Tool | Reason |
|------|------|--------|
| Find similar auth patterns | **Zilliz** | Understands semantic meaning |
| Find line 42 in file X | **Read** | Exact location known |
| Find all `def create_*` functions | **Grep** | Exact pattern matching |
| Explore unfamiliar service | **Zilliz** | Discover related code |
| Find campaign service implementation | **Glob** + **Read** | Specific file path |

---

## 🤖 Automation Patterns

### Pattern 1: Automated Campaign Creation Testing
**When**: Testing campaign creation workflow end-to-end
**Tools**: Playwright MCP
**Steps**:
1. Launch browser
2. Navigate to campaign creation page
3. Fill form with test data
4. Submit campaign
5. Verify success via screenshot
6. Check database to confirm creation
7. Close browser

### Pattern 2: Code Understanding When Stuck
**When**: Need to understand unfamiliar code section
**Tools**: Zilliz (search) + Read (examine)
**Steps**:
1. Use Zilliz to find similar patterns
2. Read relevant files to understand
3. Check tests for usage examples
4. Trace git history if needed

### Pattern 3: Multi-Step Automation
**When**: Need to automate complex user workflows
**Tools**: Playwright MCP with error handling
**Steps**:
1. Define workflow steps clearly
2. Add waits between steps (elements loading)
3. Handle errors with try/catch
4. Log progress for debugging
5. Take screenshots at key points

### Pattern 4: Test Data Setup
**When**: Need to create complex test scenarios
**Tools**: Python fixtures + optional Playwright
**Approach**:
- Use Python fixtures for API-level setup (database, services)
- Use Playwright only if UI-specific interaction is needed
- Keep test setup isolated and repeatable

---

## 🔌 MCP Configuration

### Current Configuration (mcp.json)
```json
{
  "mcpServers": {
    "@playwright/mcp": {
      "command": "npx @playwright/mcp@latest"
    },
    "@zilliz/claude-context-mcp": {
      "command": "npx -y @zilliz/claude-context-mcp@latest",
      "env": {
        "OPENAI_API_KEY": "[configured]",
        "MILVUS_ADDRESS": "[configured]",
        "MILVUS_TOKEN": "[configured]",
        "EMBEDDING_PROVIDER": "openai"
      }
    }
  }
}
```

### Verifying MCP Configuration
```bash
# Test Playwright MCP
npx @playwright/mcp@latest --version

# Test Zilliz MCP
npx -y @zilliz/claude-context-mcp@latest --version

# View all configured servers
cat mcp.json
```

### Adding New MCP Servers
1. Research MCP package at npm registry
2. Add entry to `mcp.json`:
   ```json
   "new-mcp-name": {
     "command": "npx new-mcp-name@latest",
     "env": {
       "API_KEY": "value if needed"
     }
   }
   ```
3. Update this document with new server info
4. Commit changes with message: `chore(mcp): add new-mcp-name server`

---

## 🚀 MCP Best Practices

### 1. Use MCP Proactively
```
❌ WRONG:
User: "Can you create a test for this campaign flow?"
Claude: "I could use Playwright, but let me just write a Python test instead..."

✅ RIGHT:
User: "Can you create a test for this campaign flow?"
Claude: "I'll use Playwright to automate the UI workflow, then verify results in Python."
```

### 2. Combine Tools Intelligently
```javascript
// Good: Use Playwright for UI, then verify with database
const browser = await chromium.launch();
const page = await browser.newPage();

// UI-level automation
await page.goto('http://localhost:5173/campaigns/new');
await page.fill('input[name="name"]', 'Test Campaign');
await page.click('button[type="submit"]');
await page.waitForNavigation();

// Backend verification (not via Playwright)
const campaign = await session.execute(
  select(Campaign).where(Campaign.name == 'Test Campaign')
);
assert campaign.id is not None

await browser.close();
```

### 3. Handle Timing Issues
```javascript
// Good: Explicit waits
await page.waitForSelector('.success-message', { timeout: 5000 });
await page.waitForFunction(
  () => document.querySelectorAll('.email-row').length > 0,
  { timeout: 10000 }
);

// Bad: Hope timing works out
await page.wait(2000);  // Brittle!
```

### 4. Error Recovery
```javascript
// Good: Retry logic for flaky operations
for (let attempt = 1; attempt <= 3; attempt++) {
  try {
    await page.click('.submit-button');
    await page.waitForNavigation({ timeout: 5000 });
    break;
  } catch (error) {
    if (attempt === 3) throw error;
    console.log(`Attempt ${attempt} failed, retrying...`);
    await page.reload();
  }
}

// Bad: No retry mechanism
await page.click('.submit-button');
```

### 5. Cleanup Resources
```javascript
// Good: Always close browser
try {
  // ... automation code ...
} finally {
  await browser.close();
}

// Bad: Browser left open
await page.goto(url);
await page.fill(selector, text);
// Forgot to close browser!
```

---

## 📊 MCP Performance Tips

### Optimize Playwright
- **Use headless mode** in tests/CI (faster)
- **Reuse browser context** for multiple pages
- **Set viewport size** to consistent value
- **Use waitForLoadState** instead of arbitrary waits

### Optimize Zilliz
- **Cache search results** when possible
- **Use specific search queries** (more relevant results)
- **Limit search scope** if available
- **Batch similar searches** together

---

## 🐛 Debugging MCP Issues

### Playwright Debugging
```javascript
// Enable debugging mode
const browser = await chromium.launch({
  headless: false,
  slowMo: 1000  // Slow down actions by 1 second
});

// Debug with inspector
const context = await browser.newContext();
const page = await context.newPage();
// Inspector opens automatically

// Verbose logging
page.on('console', msg => console.log(msg));
page.on('error', err => console.error(err));
```

### Zilliz Debugging
```bash
# Check API connectivity
curl -X GET https://milvus-endpoint/health

# Verify credentials
echo "OPENAI_API_KEY: $OPENAI_API_KEY"
echo "MILVUS_TOKEN: ${MILVUS_TOKEN:0:10}..."  # Show first 10 chars

# Test search
npx -y @zilliz/claude-context-mcp@latest --search "campaign creation"
```

### Common Issues & Solutions

**Issue: Playwright timeouts**
```
Solution: Increase timeout, check if element exists, verify page loaded
await page.waitForSelector('.element', { timeout: 10000 });
```

**Issue: Zilliz authentication errors**
```
Solution: Verify environment variables are set correctly
echo $MILVUS_TOKEN  # Should not be empty
```

**Issue: MCP server not starting**
```
Solution: Verify npm packages installed, check mcp.json syntax
npm list | grep mcp
node -c mcp.json  # Check JSON syntax
```

---

## 📚 MCP Documentation References

- **Playwright**: https://playwright.dev (full API reference)
- **Playwright MCP**: Check npm @playwright/mcp documentation
- **Zilliz**: https://cloud.zilliz.com (vector database docs)
- **Claude Context MCP**: GitHub @zilliz/claude-context-mcp
- **MCP Specification**: https://modelcontextprotocol.io

---

## 🎯 When to Automate vs Manual

### Use MCP for Automation
- Repetitive tasks (100+ lines of code saved)
- Testing workflows (UI interactions)
- Data gathering from UI
- Visual verification (screenshots)

### Handle Manually Instead
- One-off quick tasks
- Tasks requiring approval/confirmation
- Simple API calls
- Database operations without UI

---

## 📝 Logging Automation Activity

When using MCP tools, log your activity:
```python
# Update KNOWLEDGE_BASE.md with:
# - What you automated
# - Why you chose that approach
# - Any challenges encountered
# - Results achieved
```

Example:
```
## Automation: Campaign Creation Testing [2025-10-30]
**What**: Automated end-to-end campaign creation workflow
**How**: Used Playwright MCP to simulate user interactions
**Why**: Needed to verify UI flow works with new form validation
**Result**: Successfully created 10 test campaigns, verified in database
```

---

**Last Updated**: October 30, 2025
**Applies To**: All automation and tool integration
**Maintained By**: Claude + Project Team
