#!/usr/bin/env node

/**
 * Cleanup Temporary Files Script
 *
 * Removes temporary files created during Claude Code execution.
 * Safe to run at any time - only removes known temporary file patterns.
 *
 * Usage:
 *   node .github/cleanup-temp.js
 *
 * Removes:
 * - Test files in .github/temp/tests/
 * - Scratch files in .github/temp/scratch/
 * - Individual temporary files with patterns: *.tmp, *.temp, .claude-work-*
 */

const fs = require('fs');
const path = require('path');

const TEMP_DIRECTORIES = [
  path.join(__dirname, 'temp', 'tests'),
  path.join(__dirname, 'temp', 'scratch')
];

const TEMP_FILE_PATTERNS = [
  '*.tmp',
  '*.temp',
  '.claude-work-*',
  'test-results-*.json'
];

function log(level, message) {
  const colors = {
    info: '\x1b[36m',    // Cyan
    success: '\x1b[32m', // Green
    warn: '\x1b[33m',    // Yellow
    error: '\x1b[31m'    // Red
  };
  const reset = '\x1b[0m';

  const icon = {
    info: 'ℹ️',
    success: '✅',
    warn: '⚠️',
    error: '❌'
  };

  console.log(`${colors[level]}${icon[level]} ${message}${reset}`);
}

function deleteRecursive(dirPath) {
  if (!fs.existsSync(dirPath)) {
    return 0;
  }

  let deletedCount = 0;

  try {
    const files = fs.readdirSync(dirPath);

    for (const file of files) {
      const filePath = path.join(dirPath, file);
      const stat = fs.statSync(filePath);

      if (stat.isDirectory()) {
        deletedCount += deleteRecursive(filePath);
      } else {
        fs.unlinkSync(filePath);
        deletedCount++;
      }
    }

    // Try to remove the now-empty directory
    try {
      fs.rmdirSync(dirPath);
    } catch (e) {
      // Directory might not be empty or might not exist, that's ok
    }
  } catch (error) {
    log('warn', `Could not fully clean ${dirPath}: ${error.message}`);
  }

  return deletedCount;
}

function cleanTempDirectories() {
  let totalDeleted = 0;

  log('info', 'Cleaning temporary directories...');

  for (const dir of TEMP_DIRECTORIES) {
    const count = deleteRecursive(dir);
    if (count > 0) {
      log('success', `Cleaned ${dir}: ${count} files removed`);
      totalDeleted += count;
    }
  }

  return totalDeleted;
}

function cleanTempFiles() {
  let totalDeleted = 0;

  log('info', 'Cleaning temporary files in project root...');

  const projectRoot = path.join(__dirname, '..');

  try {
    const files = fs.readdirSync(projectRoot);

    for (const file of files) {
      // Check various temp file patterns
      const isTmpFile = file.endsWith('.tmp') ||
                       file.endsWith('.temp') ||
                       file.startsWith('.claude-work-') ||
                       file.match(/^test-results-.*\.json$/);

      if (isTmpFile) {
        const filePath = path.join(projectRoot, file);
        try {
          fs.unlinkSync(filePath);
          log('success', `Removed: ${file}`);
          totalDeleted++;
        } catch (error) {
          log('warn', `Could not remove ${file}: ${error.message}`);
        }
      }
    }
  } catch (error) {
    log('warn', `Could not read project root: ${error.message}`);
  }

  return totalDeleted;
}

function main() {
  console.log('');
  log('info', '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  log('info', 'Claude Code Temporary Files Cleanup');
  log('info', '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('');

  const dirsDeleted = cleanTempDirectories();
  console.log('');
  const filesDeleted = cleanTempFiles();

  const totalDeleted = dirsDeleted + filesDeleted;

  console.log('');
  log('info', '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

  if (totalDeleted > 0) {
    log('success', `Cleanup Complete: ${totalDeleted} items removed`);
  } else {
    log('info', 'No temporary files to clean');
  }

  log('info', '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('');
}

main();
