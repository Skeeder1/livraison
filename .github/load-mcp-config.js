#!/usr/bin/env node

/**
 * MCP Configuration Loader
 * Loads secrets from .github/secrets.env and resolves variables in mcp.json
 *
 * Usage:
 *   node .github/load-mcp-config.js
 *
 * This script:
 * 1. Reads .github/secrets.env
 * 2. Loads environment variables from the file
 * 3. Reads .github/mcp.json
 * 4. Resolves ${VAR_NAME} references to actual values
 * 5. Returns the fully resolved configuration
 */

const fs = require('fs');
const path = require('path');

// Path to secrets and config files
const GITHUB_DIR = path.join(__dirname);
const SECRETS_FILE = path.join(GITHUB_DIR, 'secrets.env');
const MCP_CONFIG_FILE = path.join(GITHUB_DIR, 'mcp.json');

/**
 * Load environment variables from secrets.env file
 * @returns {Object} Loaded environment variables
 */
function loadSecrets() {
  if (!fs.existsSync(SECRETS_FILE)) {
    console.warn(`⚠️  Warning: ${SECRETS_FILE} not found`);
    console.warn(`   Please run: cp .github/secrets.env.example .github/secrets.env`);
    console.warn(`   Then fill in your actual API keys\n`);
    return {};
  }

  const content = fs.readFileSync(SECRETS_FILE, 'utf8');
  const secrets = {};

  content.split('\n').forEach(line => {
    // Skip empty lines and comments
    if (!line.trim() || line.trim().startsWith('#')) {
      return;
    }

    const [key, ...valueParts] = line.split('=');
    if (key && valueParts.length > 0) {
      secrets[key.trim()] = valueParts.join('=').trim();
    }
  });

  return secrets;
}

/**
 * Resolve variable references in object (${VAR_NAME} → actual value)
 * @param {Object} obj Object to resolve
 * @param {Object} variables Variables to use for resolution
 * @returns {Object} Object with resolved variables
 */
function resolveVariables(obj, variables) {
  if (typeof obj === 'string') {
    // Replace ${VAR_NAME} with actual value
    return obj.replace(/\$\{([A-Z0-9_]+)\}/g, (match, varName) => {
      if (variables[varName]) {
        return variables[varName];
      }
      console.warn(`⚠️  Warning: Variable ${varName} not found in secrets.env`);
      return match; // Keep original if not found
    });
  }

  if (Array.isArray(obj)) {
    return obj.map(item => resolveVariables(item, variables));
  }

  if (typeof obj === 'object' && obj !== null) {
    const resolved = {};
    for (const key in obj) {
      resolved[key] = resolveVariables(obj[key], variables);
    }
    return resolved;
  }

  return obj;
}

/**
 * Load and resolve MCP configuration
 * @returns {Object} Resolved MCP configuration
 */
function loadMcpConfig() {
  // Load secrets
  const secrets = loadSecrets();

  // Load MCP config template
  if (!fs.existsSync(MCP_CONFIG_FILE)) {
    throw new Error(`MCP config file not found: ${MCP_CONFIG_FILE}`);
  }

  const mcpContent = fs.readFileSync(MCP_CONFIG_FILE, 'utf8');
  let mcpConfig = JSON.parse(mcpContent);

  // Resolve variables
  mcpConfig = resolveVariables(mcpConfig, secrets);

  return mcpConfig;
}

/**
 * Validate configuration
 * @param {Object} config Configuration to validate
 */
function validateConfig(config) {
  const issues = [];

  // Check for unresolved variables
  const configStr = JSON.stringify(config);
  const unresolvedVars = configStr.match(/\$\{([A-Z0-9_]+)\}/g);
  if (unresolvedVars && unresolvedVars.length > 0) {
    issues.push(`Configuration contains unresolved variables: ${unresolvedVars.join(', ')}`);
  }

  // Check required servers
  if (!config.mcpServers) {
    issues.push('No mcpServers defined in configuration');
  }

  if (issues.length > 0) {
    console.error('❌ Configuration Validation Issues:');
    issues.forEach(issue => console.error(`   - ${issue}`));
    return false;
  }

  return true;
}

// Main execution
try {
  const config = loadMcpConfig();

  if (!validateConfig(config)) {
    process.exit(1);
  }

  console.log('✅ MCP Configuration loaded successfully');
  console.log('\n📋 Active Servers:');

  for (const serverName in config.mcpServers) {
    const server = config.mcpServers[serverName];
    console.log(`   - ${serverName} (${server.command})`);
  }

  // If called with --output flag, write to stdout for parsing
  if (process.argv.includes('--output')) {
    console.log('\n' + JSON.stringify(config, null, 2));
  }

} catch (error) {
  console.error('❌ Error loading MCP configuration:', error.message);
  process.exit(1);
}
