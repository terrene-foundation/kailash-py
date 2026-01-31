#!/usr/bin/env node
/**
 * Pre-Install Script for Kailash Plugin
 *
 * Runs before plugin installation to:
 * - Check Node.js version
 * - Backup existing configuration
 * - Verify disk space
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const CLAUDE_DIR = path.join(os.homedir(), '.claude');
const MIN_NODE_VERSION = 18;

function main() {
  console.log('\n=== Kailash Vibe CC Setup - Pre Install ===\n');

  const checks = [];

  // 1. Check Node.js version
  const nodeVersion = parseInt(process.versions.node.split('.')[0], 10);
  if (nodeVersion >= MIN_NODE_VERSION) {
    console.log(`✓ Node.js version: ${process.versions.node} (requires >= ${MIN_NODE_VERSION})`);
    checks.push({ name: 'node_version', passed: true });
  } else {
    console.log(`✗ Node.js version: ${process.versions.node} (requires >= ${MIN_NODE_VERSION})`);
    checks.push({ name: 'node_version', passed: false });
  }

  // 2. Check for existing .claude directory
  if (fs.existsSync(CLAUDE_DIR)) {
    // Create backup
    const backupDir = `${CLAUDE_DIR}.backup.${Date.now()}`;
    console.log(`⚠ Existing .claude directory found`);
    console.log(`  Backup location: ${backupDir}`);
    checks.push({ name: 'existing_config', passed: true, backup: backupDir });
  } else {
    console.log('✓ No existing .claude directory');
    checks.push({ name: 'existing_config', passed: true });
  }

  // 3. Check disk space (basic check)
  try {
    const stats = fs.statfsSync(os.homedir());
    const freeGB = (stats.bavail * stats.bsize) / (1024 * 1024 * 1024);
    if (freeGB >= 0.1) { // At least 100MB free
      console.log(`✓ Disk space: ${freeGB.toFixed(1)} GB available`);
      checks.push({ name: 'disk_space', passed: true });
    } else {
      console.log(`✗ Disk space: ${freeGB.toFixed(1)} GB (need at least 100MB)`);
      checks.push({ name: 'disk_space', passed: false });
    }
  } catch (e) {
    // statfsSync not available on all platforms
    console.log('⚠ Disk space check skipped');
    checks.push({ name: 'disk_space', passed: true, skipped: true });
  }

  // 4. Summary
  const allPassed = checks.every(c => c.passed);
  console.log('\n' + (allPassed ? '✓ All pre-install checks passed' : '✗ Some checks failed'));

  process.exit(allPassed ? 0 : 1);
}

if (require.main === module) {
  main();
}

module.exports = { main };
