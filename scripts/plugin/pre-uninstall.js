#!/usr/bin/env node
/**
 * Pre-Uninstall Script for Kailash Plugin
 *
 * Runs before plugin uninstallation to:
 * - Save learning checkpoint
 * - Export observations
 * - Offer to preserve data
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const LEARNING_DIR = path.join(os.homedir(), '.claude', 'kailash-learning');
const EXPORT_DIR = path.join(os.homedir(), 'kailash-learning-export');

function main() {
  console.log('\n=== Kailash Vibe CC Setup - Pre Uninstall ===\n');

  // Check if learning data exists
  if (!fs.existsSync(LEARNING_DIR)) {
    console.log('No learning data to preserve.');
    process.exit(0);
  }

  // Check for observations
  const obsFile = path.join(LEARNING_DIR, 'observations.jsonl');
  const instinctsDir = path.join(LEARNING_DIR, 'instincts', 'personal');

  let hasData = false;

  if (fs.existsSync(obsFile)) {
    const content = fs.readFileSync(obsFile, 'utf8');
    const lines = content.trim().split('\n').filter(l => l);
    if (lines.length > 0) {
      console.log(`Found ${lines.length} observations`);
      hasData = true;
    }
  }

  if (fs.existsSync(instinctsDir)) {
    const files = fs.readdirSync(instinctsDir).filter(f => f.endsWith('.json'));
    if (files.length > 0) {
      console.log(`Found ${files.length} instinct categories`);
      hasData = true;
    }
  }

  if (!hasData) {
    console.log('No learning data to preserve.');
    process.exit(0);
  }

  // Export learning data
  console.log('\nExporting learning data...');

  if (!fs.existsSync(EXPORT_DIR)) {
    fs.mkdirSync(EXPORT_DIR, { recursive: true });
  }

  // Copy observations
  if (fs.existsSync(obsFile)) {
    fs.copyFileSync(obsFile, path.join(EXPORT_DIR, 'observations.jsonl'));
    console.log('  ✓ Observations exported');
  }

  // Copy instincts
  if (fs.existsSync(instinctsDir)) {
    const exportInstinctsDir = path.join(EXPORT_DIR, 'instincts');
    fs.mkdirSync(exportInstinctsDir, { recursive: true });

    const files = fs.readdirSync(instinctsDir);
    files.forEach(file => {
      fs.copyFileSync(
        path.join(instinctsDir, file),
        path.join(exportInstinctsDir, file)
      );
    });
    console.log('  ✓ Instincts exported');
  }

  // Create export manifest
  const manifest = {
    exported_at: new Date().toISOString(),
    source: 'kailash-vibe-cc-setup',
    version: '1.0.0',
    contains: {
      observations: fs.existsSync(path.join(EXPORT_DIR, 'observations.jsonl')),
      instincts: fs.existsSync(path.join(EXPORT_DIR, 'instincts'))
    }
  };

  fs.writeFileSync(
    path.join(EXPORT_DIR, 'export-manifest.json'),
    JSON.stringify(manifest, null, 2)
  );

  console.log(`\n✓ Learning data exported to: ${EXPORT_DIR}`);
  console.log('  You can re-import this data after reinstalling.\n');

  process.exit(0);
}

if (require.main === module) {
  main();
}

module.exports = { main };
