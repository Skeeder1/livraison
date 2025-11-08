# Claude Code Configuration

This document explains how to configure Claude Code to use the new MCP configuration structure.

## 📍 Configuration Location Change

**Previous**: `mcp.json` (in repository root)
**Current**: `.github/mcp.json` (in .github directory)

This change centralizes configuration with secrets in the `.github/` directory for better organization and security.

## 🔧 How to Configure Claude Code

Claude Code can be configured in multiple ways to use the MCP servers.

### Option 1: Direct File Reference (Recommended for Local Development)

If Claude Code supports custom MCP config paths:

1. Open Claude Code settings
2. Find "MCP Configuration" or "MCP Settings"
3. Set the path to: `.github/mcp.json`

**Result**: Claude Code reads configuration from `.github/mcp.json` with variable resolution

### Option 2: Using Claude Code Status Line (Advanced)

Create `.claude/settings.json`:

```json
{
  "mcpServers": {
    "mcp_config_path": ".github/mcp.json",
    "mcp_secrets_path": ".github/secrets.env"
  }
}
```

### Option 3: Environment Variable Setup (For CI/CD)

Set environment variable before launching Claude Code:

```bash
# Linux/macOS
export MCP_CONFIG_PATH=".github/mcp.json"
export MCP_SECRETS_PATH=".github/secrets.env"
claude-code

# Windows (PowerShell)
$env:MCP_CONFIG_PATH = ".github/mcp.json"
$env:MCP_SECRETS_PATH = ".github/secrets.env"
claude-code

# Windows (Command Prompt)
set MCP_CONFIG_PATH=.github\mcp.json
set MCP_SECRETS_PATH=.github\secrets.env
claude-code
```

### Option 4: Resolved Configuration (For Static Setup)

Generate a resolved configuration file:

```bash
# Generate fully resolved mcp.json
node .github/load-mcp-config.js --output > mcp-resolved.json

# Then point Claude Code to mcp-resolved.json
```

⚠️ **Note**: Only use this for testing. Do NOT commit `mcp-resolved.json` if it contains real secrets.

## 🔄 Automatic Setup

### Self-Contained Configuration

The MCP configuration is self-contained and can be loaded automatically:

1. **Load Script Location**: `.github/load-mcp-config.js`
2. **Secrets Location**: `.github/secrets.env`
3. **Config Template**: `.github/mcp.json`

### What Needs to Happen

For Claude Code to use the new configuration:

```
1. Claude Code reads settings
2. Finds reference to .github/mcp.json
3. Loads configuration file
4. Resolves ${VAR_NAME} references
5. Loads secrets from .github/secrets.env
6. Initializes MCP servers with resolved credentials
```

## 📋 Setup Steps

### First Time Setup

```bash
# 1. Copy secrets template
cp .github/secrets.env.example .github/secrets.env

# 2. Edit secrets and add your API keys
# vim .github/secrets.env

# 3. Verify configuration loads
node .github/load-mcp-config.js

# 4. Expected output:
# ✅ MCP Configuration loaded successfully
# 📋 Active Servers:
#    - playwright (npx)
#    - claude-context (npx)
#    - brave-search (npx)
```

### Configure Claude Code

**For Claude Code CLI Settings**:

Edit `.claude/settings.json` (or equivalent):

```json
{
  "model": "claude-opus-4-1",
  "temperature": 0.8,
  "mcp": {
    "configPath": ".github/mcp.json",
    "secretsPath": ".github/secrets.env",
    "loader": ".github/load-mcp-config.js"
  }
}
```

**For Claude Code Status Line**:

The status line can show MCP server status:

```
📍 main | ✅ MCP: 3 servers | 🚀 Ready
```

## 🧪 Verification

### Check Configuration is Loaded

```bash
# Run the loader
node .github/load-mcp-config.js

# Output should show all active servers
```

### Test Each Server

```bash
# Test Brave Search
node .github/test_brave_mcp_server.js

# Test all servers (if loader script exists)
npm test -- --mcp
```

### Verify in Claude Code

Within Claude Code, test that MCP tools are available:

```
> @mcp brave
> Available MCP Servers: brave-search, playwright, claude-context
```

## 🚀 Configuration Verification Checklist

- [ ] `.github/mcp.json` exists
- [ ] `.github/secrets.env.example` exists with documentation
- [ ] `.github/secrets.env` exists with your actual keys
- [ ] `.github/load-mcp-config.js` works: `node .github/load-mcp-config.js`
- [ ] Claude Code points to `.github/mcp.json`
- [ ] All MCP servers show as available
- [ ] Test: `node .github/test_brave_mcp_server.js` passes
- [ ] Root `mcp.json` is no longer used (optional: can be deleted)

## 📝 Legacy Configuration

### What Changed

| Aspect | Before | After |
|--------|--------|-------|
| Config File | `./mcp.json` | `./.github/mcp.json` |
| Secrets | In mcp.json | `./.github/secrets.env` |
| Variables | Hardcoded | Template: `${VAR_NAME}` |
| Loader | None | `.github/load-mcp-config.js` |
| Documentation | None | `.github/MCP-SETUP.md` |

### Migration from Old Setup

If you're migrating from the old configuration:

```bash
# 1. Backup old configuration
cp mcp.json mcp.json.backup

# 2. Copy secrets to new location
cp .github/secrets.env.example .github/secrets.env
# (Manually add your keys from the old mcp.json)

# 3. Verify new configuration works
node .github/load-mcp-config.js

# 4. Update Claude Code to point to .github/mcp.json

# 5. Test everything works

# 6. Remove old configuration (optional)
rm mcp.json
```

## 🔐 Security Notes

### File Permissions

Ensure proper permissions on secrets file:

```bash
# Recommended for Linux/macOS
chmod 600 .github/secrets.env

# This means: owner read/write, no group/other access
```

### Never Commit

`.github/secrets.env` is in `.gitignore` and will never be committed. Verify:

```bash
git status
# Should NOT show: .github/secrets.env

# Check gitignore includes it
grep "secrets.env" .gitignore
# Should output: .github/secrets.env
```

## 🆘 Troubleshooting

### Claude Code doesn't recognize MCP servers

**Check**:
1. Path to mcp.json is correct in Claude Code settings
2. Secrets are loaded: `node .github/load-mcp-config.js`
3. No unresolved variables: `grep '${' .github/mcp.json`
4. Restart Claude Code

### Load script fails

```bash
node .github/load-mcp-config.js
```

Common errors:
- ❌ `secrets.env not found` → Run: `cp .github/secrets.env.example .github/secrets.env`
- ❌ `Unresolved variables` → Check all vars are in secrets.env
- ❌ `JSON parse error` → Check .github/mcp.json syntax is valid

### MCP servers won't start

1. Check API keys are correct in `.github/secrets.env`
2. Verify package is installed: `npm ls @modelcontextprotocol/server-brave-search`
3. Check network connectivity
4. Look for error messages: `npm list --depth=0`

## 📞 Support

For issues with:
- **MCP Configuration**: See `.github/MCP-SETUP.md`
- **Adding New Servers**: See `.github/MCP-INTEGRATION-GUIDE.md`
- **Claude Code**: Run `/help` within Claude Code
- **MCP Protocol**: Visit https://modelcontextprotocol.io/

---

**Updated**: October 2025
**Status**: ✅ Configuration finalized and documented
