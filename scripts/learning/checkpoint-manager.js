#!/usr/bin/env node
/**
 * Checkpoint Manager for Kailash Continuous Learning System
 *
 * Saves and restores learning state checkpoints.
 * Part of Phase 4: Continuous Learning implementation.
 *
 * Usage:
 *   node checkpoint-manager.js --save
 *   node checkpoint-manager.js --list
 *   node checkpoint-manager.js --restore <id>
 *   node checkpoint-manager.js --diff <id>
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

// Learning directory structure - supports env var override for testing
const LEARNING_DIR = process.env.KAILASH_LEARNING_DIR || path.join(os.homedir(), '.claude', 'kailash-learning');
const CHECKPOINTS_DIR = path.join(LEARNING_DIR, 'checkpoints');
const OBSERVATIONS_FILE = path.join(LEARNING_DIR, 'observations.jsonl');
const INSTINCTS_DIR = path.join(LEARNING_DIR, 'instincts', 'personal');
const IDENTITY_FILE = path.join(LEARNING_DIR, 'identity.json');

/**
 * Initialize checkpoint directory
 */
function initCheckpointDir() {
  if (!fs.existsSync(CHECKPOINTS_DIR)) {
    fs.mkdirSync(CHECKPOINTS_DIR, { recursive: true });
  }
}

/**
 * Get last N observations
 */
function getRecentObservations(limit = 100) {
  if (!fs.existsSync(OBSERVATIONS_FILE)) {
    return [];
  }

  const content = fs.readFileSync(OBSERVATIONS_FILE, 'utf8');
  const lines = content.trim().split('\n').filter(l => l);
  const observations = [];

  // Get last N lines
  const start = Math.max(0, lines.length - limit);
  for (let i = start; i < lines.length; i++) {
    try {
      observations.push(JSON.parse(lines[i]));
    } catch (e) { }
  }

  return observations;
}

/**
 * Get all instincts
 */
function getAllInstincts() {
  const instincts = {};

  if (!fs.existsSync(INSTINCTS_DIR)) {
    return instincts;
  }

  const files = fs.readdirSync(INSTINCTS_DIR);
  files.forEach(file => {
    if (file.endsWith('.json')) {
      const category = file.replace('.json', '');
      instincts[category] = JSON.parse(fs.readFileSync(path.join(INSTINCTS_DIR, file), 'utf8'));
    }
  });

  return instincts;
}

/**
 * Get identity
 */
function getIdentity() {
  if (!fs.existsSync(IDENTITY_FILE)) {
    return null;
  }
  return JSON.parse(fs.readFileSync(IDENTITY_FILE, 'utf8'));
}

/**
 * Save checkpoint
 */
function saveCheckpoint(name = null) {
  initCheckpointDir();

  const timestamp = Date.now();
  const checkpointId = `checkpoint_${timestamp}`;

  const checkpoint = {
    id: checkpointId,
    name: name || checkpointId,
    created_at: new Date().toISOString(),
    observations: getRecentObservations(100),
    instincts: getAllInstincts(),
    identity: getIdentity(),
    stats: {
      observation_count: getRecentObservations(10000).length,
      instinct_categories: Object.keys(getAllInstincts()).length
    }
  };

  const filePath = path.join(CHECKPOINTS_DIR, `${checkpointId}.json`);
  fs.writeFileSync(filePath, JSON.stringify(checkpoint, null, 2));

  // Update latest symlink
  const latestPath = path.join(CHECKPOINTS_DIR, 'latest.json');
  if (fs.existsSync(latestPath)) {
    fs.unlinkSync(latestPath);
  }
  fs.copyFileSync(filePath, latestPath);

  return {
    success: true,
    checkpoint_id: checkpointId,
    file: filePath,
    stats: checkpoint.stats
  };
}

/**
 * List all checkpoints
 */
function listCheckpoints() {
  initCheckpointDir();

  const checkpoints = [];
  const files = fs.readdirSync(CHECKPOINTS_DIR);

  files.forEach(file => {
    if (file.endsWith('.json') && file !== 'latest.json') {
      const content = JSON.parse(fs.readFileSync(path.join(CHECKPOINTS_DIR, file), 'utf8'));
      checkpoints.push({
        id: content.id,
        name: content.name,
        created_at: content.created_at,
        observation_count: content.stats?.observation_count || 0,
        instinct_categories: content.stats?.instinct_categories || 0
      });
    }
  });

  // Sort by creation date descending
  checkpoints.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

  return checkpoints;
}

/**
 * Restore checkpoint
 */
function restoreCheckpoint(checkpointId) {
  const filePath = path.join(CHECKPOINTS_DIR, `${checkpointId}.json`);

  if (!fs.existsSync(filePath)) {
    return { success: false, error: `Checkpoint ${checkpointId} not found` };
  }

  const checkpoint = JSON.parse(fs.readFileSync(filePath, 'utf8'));

  // Backup current state first
  const backupResult = saveCheckpoint(`pre-restore-${Date.now()}`);

  // Restore observations (append to current file)
  const restoredObs = checkpoint.observations || [];
  if (restoredObs.length > 0) {
    // Ensure learning directory exists
    if (!fs.existsSync(LEARNING_DIR)) {
      fs.mkdirSync(LEARNING_DIR, { recursive: true });
    }

    // Append restored observations with metadata
    const linesToAppend = restoredObs.map(obs => {
      obs.restored_from = checkpointId;
      obs.restored_at = new Date().toISOString();
      return JSON.stringify(obs);
    }).join('\n') + '\n';

    fs.appendFileSync(OBSERVATIONS_FILE, linesToAppend);
  }

  // Restore instincts
  if (checkpoint.instincts) {
    if (!fs.existsSync(INSTINCTS_DIR)) {
      fs.mkdirSync(INSTINCTS_DIR, { recursive: true });
    }

    Object.keys(checkpoint.instincts).forEach(category => {
      const filePath = path.join(INSTINCTS_DIR, `${category}.json`);
      fs.writeFileSync(filePath, JSON.stringify(checkpoint.instincts[category], null, 2));
    });
  }

  return {
    success: true,
    restored_checkpoint: checkpointId,
    backup_checkpoint: backupResult.checkpoint_id,
    observations_restored: restoredObs.length,
    instinct_categories_restored: Object.keys(checkpoint.instincts || {}).length
  };
}

/**
 * Diff current state with checkpoint
 */
function diffCheckpoint(checkpointId) {
  const filePath = path.join(CHECKPOINTS_DIR, `${checkpointId}.json`);

  if (!fs.existsSync(filePath)) {
    return { success: false, error: `Checkpoint ${checkpointId} not found` };
  }

  const checkpoint = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  const currentInstincts = getAllInstincts();
  const checkpointInstincts = checkpoint.instincts || {};

  const diff = {
    checkpoint_id: checkpointId,
    checkpoint_date: checkpoint.created_at,
    observations: {
      checkpoint: checkpoint.observations?.length || 0,
      current: getRecentObservations(10000).length
    },
    instincts: {
      added: [],
      removed: [],
      modified: []
    }
  };

  // Compare instinct categories
  const currentCategories = new Set(Object.keys(currentInstincts));
  const checkpointCategories = new Set(Object.keys(checkpointInstincts));

  // Find added categories
  currentCategories.forEach(cat => {
    if (!checkpointCategories.has(cat)) {
      diff.instincts.added.push({
        category: cat,
        count: currentInstincts[cat]?.length || 0
      });
    }
  });

  // Find removed categories
  checkpointCategories.forEach(cat => {
    if (!currentCategories.has(cat)) {
      diff.instincts.removed.push({
        category: cat,
        count: checkpointInstincts[cat]?.length || 0
      });
    }
  });

  // Find modified categories
  currentCategories.forEach(cat => {
    if (checkpointCategories.has(cat)) {
      const currentCount = currentInstincts[cat]?.length || 0;
      const checkpointCount = checkpointInstincts[cat]?.length || 0;
      if (currentCount !== checkpointCount) {
        diff.instincts.modified.push({
          category: cat,
          checkpoint_count: checkpointCount,
          current_count: currentCount,
          delta: currentCount - checkpointCount
        });
      }
    }
  });

  return { success: true, diff };
}

/**
 * Export checkpoint
 */
function exportCheckpoint(checkpointId, outputPath) {
  const filePath = path.join(CHECKPOINTS_DIR, `${checkpointId}.json`);

  if (!fs.existsSync(filePath)) {
    return { success: false, error: `Checkpoint ${checkpointId} not found` };
  }

  const checkpoint = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  fs.writeFileSync(outputPath, JSON.stringify(checkpoint, null, 2));

  return {
    success: true,
    exported_to: outputPath,
    checkpoint_id: checkpointId
  };
}

/**
 * Import checkpoint
 */
function importCheckpoint(inputPath) {
  if (!fs.existsSync(inputPath)) {
    return { success: false, error: `File ${inputPath} not found` };
  }

  initCheckpointDir();

  const checkpoint = JSON.parse(fs.readFileSync(inputPath, 'utf8'));

  // Generate new ID for imported checkpoint
  const newId = `checkpoint_imported_${Date.now()}`;
  checkpoint.id = newId;
  checkpoint.imported_at = new Date().toISOString();
  checkpoint.imported_from = inputPath;

  const filePath = path.join(CHECKPOINTS_DIR, `${newId}.json`);
  fs.writeFileSync(filePath, JSON.stringify(checkpoint, null, 2));

  return {
    success: true,
    imported_checkpoint: newId,
    file: filePath
  };
}

/**
 * Main execution
 */
function main() {
  const args = process.argv.slice(2);
  const command = args[0] || '--help';

  switch (command) {
    case '--save':
      const nameIndex = args.indexOf('--name');
      const name = nameIndex >= 0 ? args[nameIndex + 1] : null;
      const saveResult = saveCheckpoint(name);
      console.log(JSON.stringify(saveResult, null, 2));
      break;

    case '--list':
      const checkpoints = listCheckpoints();
      console.log(JSON.stringify(checkpoints, null, 2));
      break;

    case '--restore':
      const restoreId = args[1];
      if (!restoreId) {
        console.error('Error: checkpoint_id required');
        process.exit(1);
      }
      const restoreResult = restoreCheckpoint(restoreId);
      console.log(JSON.stringify(restoreResult, null, 2));
      break;

    case '--diff':
      const diffId = args[1];
      if (!diffId) {
        console.error('Error: checkpoint_id required');
        process.exit(1);
      }
      const diffResult = diffCheckpoint(diffId);
      console.log(JSON.stringify(diffResult, null, 2));
      break;

    case '--export':
      const exportId = args[1];
      const exportPath = args[2];
      if (!exportId || !exportPath) {
        console.error('Error: checkpoint_id and output_path required');
        process.exit(1);
      }
      const exportResult = exportCheckpoint(exportId, exportPath);
      console.log(JSON.stringify(exportResult, null, 2));
      break;

    case '--import':
      const importPath = args[1];
      if (!importPath) {
        console.error('Error: input_path required');
        process.exit(1);
      }
      const importResult = importCheckpoint(importPath);
      console.log(JSON.stringify(importResult, null, 2));
      break;

    case '--help':
    default:
      console.log(`
Checkpoint Manager for Kailash Continuous Learning

Usage:
  node checkpoint-manager.js --save [--name <name>]   Save checkpoint
  node checkpoint-manager.js --list                   List checkpoints
  node checkpoint-manager.js --restore <id>           Restore checkpoint
  node checkpoint-manager.js --diff <id>              Compare with checkpoint
  node checkpoint-manager.js --export <id> <path>     Export checkpoint
  node checkpoint-manager.js --import <path>          Import checkpoint
  node checkpoint-manager.js --help                   Show this help
`);
      break;
  }
}

if (require.main === module) {
  main();
}

module.exports = {
  saveCheckpoint,
  listCheckpoints,
  restoreCheckpoint,
  diffCheckpoint,
  exportCheckpoint,
  importCheckpoint
};
