#!/usr/bin/env node
/**
 * Post-Install Script for Kailash Plugin
 *
 * Runs after plugin installation to:
 * - Verify hook scripts are executable
 * - Initialize learning directory
 * - Detect package manager
 * - Show welcome message
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const CLAUDE_DIR = path.join(os.homedir(), '.claude');
const LEARNING_DIR = path.join(os.homedir(), '.claude', 'kailash-learning');

function main() {
  console.log('\n=== Kailash Vibe CC Setup - Post Install ===\n');

  // 1. Verify .claude directory
  if (!fs.existsSync(CLAUDE_DIR)) {
    console.log('Creating .claude directory...');
    fs.mkdirSync(CLAUDE_DIR, { recursive: true });
  }
  console.log('✓ .claude directory exists');

  // 2. Initialize learning directory
  const learningDirs = [
    LEARNING_DIR,
    path.join(LEARNING_DIR, 'instincts', 'personal'),
    path.join(LEARNING_DIR, 'instincts', 'inherited'),
    path.join(LEARNING_DIR, 'evolved', 'skills'),
    path.join(LEARNING_DIR, 'evolved', 'commands'),
    path.join(LEARNING_DIR, 'checkpoints')
  ];

  learningDirs.forEach(dir => {
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  });
  console.log('✓ Learning directory initialized');

  // 3. Create identity file
  const identityPath = path.join(LEARNING_DIR, 'identity.json');
  if (!fs.existsSync(identityPath)) {
    const identity = {
      system: 'kailash-vibe-cc-setup',
      version: '1.0.0',
      installed_at: new Date().toISOString(),
      learning_enabled: true,
      focus_areas: [
        'workflow-patterns',
        'error-fixes',
        'dataflow-patterns',
        'testing-patterns',
        'framework-selection'
      ]
    };
    fs.writeFileSync(identityPath, JSON.stringify(identity, null, 2));
    console.log('✓ Learning identity created');
  }

  // 4. Make hook scripts executable (Unix only)
  if (process.platform !== 'win32') {
    const hooksDir = path.join(process.cwd(), 'scripts', 'hooks');
    if (fs.existsSync(hooksDir)) {
      const hooks = fs.readdirSync(hooksDir).filter(f => f.endsWith('.js'));
      hooks.forEach(hook => {
        const hookPath = path.join(hooksDir, hook);
        try {
          fs.chmodSync(hookPath, 0o755);
        } catch (e) {
          // Ignore permission errors
        }
      });
      console.log(`✓ ${hooks.length} hook scripts marked executable`);
    }
  }

  // 5. Show summary
  console.log('\n=== Installation Complete ===\n');
  console.log('Components installed:');
  console.log('  - 25 specialized agents');
  console.log('  - 18 skill categories');
  console.log('  - 9 slash commands (/sdk, /db, /api, /ai, /test, /validate, /learn, /evolve, /checkpoint)');
  console.log('  - 8 automation hooks');
  console.log('  - 3 MCP configurations');
  console.log('  - Continuous learning system');
  console.log('  - CI validation suite\n');

  console.log('Quick Start:');
  console.log('  /sdk   - Core SDK patterns');
  console.log('  /db    - DataFlow database operations');
  console.log('  /api   - Nexus multi-channel deployment');
  console.log('  /ai    - Kaizen AI agents');
  console.log('  /test  - Testing strategies');
  console.log('  /learn - Learning system status\n');

  console.log('Documentation: See CLAUDE.md for complete reference.\n');
}

if (require.main === module) {
  main();
}

module.exports = { main };
