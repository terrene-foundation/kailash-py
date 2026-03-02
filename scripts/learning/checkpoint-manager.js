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

const fs = require("fs");
const path = require("path");
const os = require("os");
const { resolveLearningDir } = require("../hooks/lib/learning-utils");

/**
 * Resolve paths for a given learning directory.
 * @param {string} [learningDir] - Override; falls back to resolveLearningDir()
 */
function resolvePaths(learningDir) {
  const dir = learningDir || resolveLearningDir();
  return {
    learningDir: dir,
    checkpointsDir: path.join(dir, "checkpoints"),
    observationsFile: path.join(dir, "observations.jsonl"),
    instinctsDir: path.join(dir, "instincts", "personal"),
    identityFile: path.join(dir, "identity.json"),
  };
}

/**
 * Initialize checkpoint directory
 * @param {string} [learningDir]
 */
function initCheckpointDir(learningDir) {
  const p = resolvePaths(learningDir);
  if (!fs.existsSync(p.checkpointsDir)) {
    fs.mkdirSync(p.checkpointsDir, { recursive: true });
  }
}

/**
 * Get last N observations
 * @param {number} [limit=100]
 * @param {string} [learningDir]
 */
function getRecentObservations(limit = 100, learningDir) {
  const p = resolvePaths(learningDir);
  if (!fs.existsSync(p.observationsFile)) {
    return [];
  }

  const content = fs.readFileSync(p.observationsFile, "utf8");
  const lines = content
    .trim()
    .split("\n")
    .filter((l) => l);
  const observations = [];

  const start = Math.max(0, lines.length - limit);
  for (let i = start; i < lines.length; i++) {
    try {
      observations.push(JSON.parse(lines[i]));
    } catch (e) {}
  }

  return observations;
}

/**
 * Get all instincts
 * @param {string} [learningDir]
 */
function getAllInstincts(learningDir) {
  const p = resolvePaths(learningDir);
  const instincts = {};

  if (!fs.existsSync(p.instinctsDir)) {
    return instincts;
  }

  const files = fs.readdirSync(p.instinctsDir);
  files.forEach((file) => {
    if (file.endsWith(".json")) {
      const category = file.replace(".json", "");
      instincts[category] = JSON.parse(
        fs.readFileSync(path.join(p.instinctsDir, file), "utf8"),
      );
    }
  });

  return instincts;
}

/**
 * Get identity
 * @param {string} [learningDir]
 */
function getIdentity(learningDir) {
  const p = resolvePaths(learningDir);
  if (!fs.existsSync(p.identityFile)) {
    return null;
  }
  return JSON.parse(fs.readFileSync(p.identityFile, "utf8"));
}

/**
 * Save checkpoint
 * @param {string} [name]
 * @param {string} [learningDir]
 */
function saveCheckpoint(name, learningDir) {
  const p = resolvePaths(learningDir);
  initCheckpointDir(learningDir);

  const timestamp = Date.now();
  const checkpointId = `checkpoint_${timestamp}`;

  const allObservations = getRecentObservations(10000, learningDir);
  const instincts = getAllInstincts(learningDir);

  const checkpoint = {
    id: checkpointId,
    name: name || checkpointId,
    created_at: new Date().toISOString(),
    observations: allObservations.slice(-100),
    instincts,
    identity: getIdentity(learningDir),
    stats: {
      observation_count: allObservations.length,
      instinct_categories: Object.keys(instincts).length,
    },
  };

  const filePath = path.join(p.checkpointsDir, `${checkpointId}.json`);
  fs.writeFileSync(filePath, JSON.stringify(checkpoint, null, 2));

  // Update latest copy
  const latestPath = path.join(p.checkpointsDir, "latest.json");
  if (fs.existsSync(latestPath)) {
    fs.unlinkSync(latestPath);
  }
  fs.copyFileSync(filePath, latestPath);

  return {
    success: true,
    checkpoint_id: checkpointId,
    file: filePath,
    stats: checkpoint.stats,
  };
}

/**
 * List all checkpoints
 * @param {string} [learningDir]
 */
function listCheckpoints(learningDir) {
  const p = resolvePaths(learningDir);
  initCheckpointDir(learningDir);

  const checkpoints = [];
  const files = fs.readdirSync(p.checkpointsDir);

  files.forEach((file) => {
    if (file.endsWith(".json") && file !== "latest.json") {
      const content = JSON.parse(
        fs.readFileSync(path.join(p.checkpointsDir, file), "utf8"),
      );
      checkpoints.push({
        id: content.id,
        name: content.name,
        created_at: content.created_at,
        observation_count: content.stats?.observation_count || 0,
        instinct_categories: content.stats?.instinct_categories || 0,
      });
    }
  });

  checkpoints.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  return checkpoints;
}

/**
 * Restore checkpoint
 * @param {string} checkpointId
 * @param {string} [learningDir]
 */
function restoreCheckpoint(checkpointId, learningDir) {
  const p = resolvePaths(learningDir);
  const cpPath = path.join(p.checkpointsDir, `${checkpointId}.json`);

  if (!fs.existsSync(cpPath)) {
    return { success: false, error: `Checkpoint ${checkpointId} not found` };
  }

  const checkpoint = JSON.parse(fs.readFileSync(cpPath, "utf8"));

  // Backup current state first
  const backupResult = saveCheckpoint(`pre-restore-${Date.now()}`, learningDir);

  // Restore observations
  const restoredObs = checkpoint.observations || [];
  if (restoredObs.length > 0) {
    try {
      fs.mkdirSync(p.learningDir, { recursive: true });
    } catch {}

    const linesToAppend =
      restoredObs
        .map((obs) => {
          obs.restored_from = checkpointId;
          obs.restored_at = new Date().toISOString();
          return JSON.stringify(obs);
        })
        .join("\n") + "\n";

    fs.appendFileSync(p.observationsFile, linesToAppend);
  }

  // Restore instincts
  if (checkpoint.instincts) {
    try {
      fs.mkdirSync(p.instinctsDir, { recursive: true });
    } catch {}

    Object.keys(checkpoint.instincts).forEach((category) => {
      const instinctPath = path.join(p.instinctsDir, `${category}.json`);
      fs.writeFileSync(
        instinctPath,
        JSON.stringify(checkpoint.instincts[category], null, 2),
      );
    });
  }

  return {
    success: true,
    restored_checkpoint: checkpointId,
    backup_checkpoint: backupResult.checkpoint_id,
    observations_restored: restoredObs.length,
    instinct_categories_restored: Object.keys(checkpoint.instincts || {})
      .length,
  };
}

/**
 * Diff current state with checkpoint
 * @param {string} checkpointId
 * @param {string} [learningDir]
 */
function diffCheckpoint(checkpointId, learningDir) {
  const p = resolvePaths(learningDir);
  const cpPath = path.join(p.checkpointsDir, `${checkpointId}.json`);

  if (!fs.existsSync(cpPath)) {
    return { success: false, error: `Checkpoint ${checkpointId} not found` };
  }

  const checkpoint = JSON.parse(fs.readFileSync(cpPath, "utf8"));
  const currentInstincts = getAllInstincts(learningDir);
  const checkpointInstincts = checkpoint.instincts || {};

  const diff = {
    checkpoint_id: checkpointId,
    checkpoint_date: checkpoint.created_at,
    observations: {
      checkpoint: checkpoint.observations?.length || 0,
      current: getRecentObservations(10000, learningDir).length,
    },
    instincts: { added: [], removed: [], modified: [] },
  };

  const currentCategories = new Set(Object.keys(currentInstincts));
  const checkpointCategories = new Set(Object.keys(checkpointInstincts));

  currentCategories.forEach((cat) => {
    if (!checkpointCategories.has(cat)) {
      diff.instincts.added.push({
        category: cat,
        count: currentInstincts[cat]?.length || 0,
      });
    }
  });

  checkpointCategories.forEach((cat) => {
    if (!currentCategories.has(cat)) {
      diff.instincts.removed.push({
        category: cat,
        count: checkpointInstincts[cat]?.length || 0,
      });
    }
  });

  currentCategories.forEach((cat) => {
    if (checkpointCategories.has(cat)) {
      const cc = currentInstincts[cat]?.length || 0;
      const cp = checkpointInstincts[cat]?.length || 0;
      if (cc !== cp) {
        diff.instincts.modified.push({
          category: cat,
          checkpoint_count: cp,
          current_count: cc,
          delta: cc - cp,
        });
      }
    }
  });

  return { success: true, diff };
}

/**
 * Export checkpoint
 * @param {string} checkpointId
 * @param {string} outputPath
 * @param {string} [learningDir]
 */
function exportCheckpoint(checkpointId, outputPath, learningDir) {
  const p = resolvePaths(learningDir);
  const cpPath = path.join(p.checkpointsDir, `${checkpointId}.json`);

  if (!fs.existsSync(cpPath)) {
    return { success: false, error: `Checkpoint ${checkpointId} not found` };
  }

  const checkpoint = JSON.parse(fs.readFileSync(cpPath, "utf8"));
  fs.writeFileSync(outputPath, JSON.stringify(checkpoint, null, 2));

  return {
    success: true,
    exported_to: outputPath,
    checkpoint_id: checkpointId,
  };
}

/**
 * Import checkpoint
 * @param {string} inputPath
 * @param {string} [learningDir]
 */
function importCheckpoint(inputPath, learningDir) {
  if (!fs.existsSync(inputPath)) {
    return { success: false, error: `File ${inputPath} not found` };
  }

  const p = resolvePaths(learningDir);
  initCheckpointDir(learningDir);

  const checkpoint = JSON.parse(fs.readFileSync(inputPath, "utf8"));

  const newId = `checkpoint_imported_${Date.now()}`;
  checkpoint.id = newId;
  checkpoint.imported_at = new Date().toISOString();
  checkpoint.imported_from = inputPath;

  const cpPath = path.join(p.checkpointsDir, `${newId}.json`);
  fs.writeFileSync(cpPath, JSON.stringify(checkpoint, null, 2));

  return { success: true, imported_checkpoint: newId, file: cpPath };
}

/**
 * Main execution
 */
function main() {
  const args = process.argv.slice(2);
  const command = args[0] || "--help";

  switch (command) {
    case "--save":
      const nameIndex = args.indexOf("--name");
      const name = nameIndex >= 0 ? args[nameIndex + 1] : null;
      const saveResult = saveCheckpoint(name);
      console.log(JSON.stringify(saveResult, null, 2));
      break;

    case "--list":
      const checkpoints = listCheckpoints();
      console.log(JSON.stringify(checkpoints, null, 2));
      break;

    case "--restore":
      const restoreId = args[1];
      if (!restoreId) {
        console.error("Error: checkpoint_id required");
        process.exit(1);
      }
      const restoreResult = restoreCheckpoint(restoreId);
      console.log(JSON.stringify(restoreResult, null, 2));
      break;

    case "--diff":
      const diffId = args[1];
      if (!diffId) {
        console.error("Error: checkpoint_id required");
        process.exit(1);
      }
      const diffResult = diffCheckpoint(diffId);
      console.log(JSON.stringify(diffResult, null, 2));
      break;

    case "--export":
      const exportId = args[1];
      const exportPath = args[2];
      if (!exportId || !exportPath) {
        console.error("Error: checkpoint_id and output_path required");
        process.exit(1);
      }
      const exportResult = exportCheckpoint(exportId, exportPath);
      console.log(JSON.stringify(exportResult, null, 2));
      break;

    case "--import":
      const importPath = args[1];
      if (!importPath) {
        console.error("Error: input_path required");
        process.exit(1);
      }
      const importResult = importCheckpoint(importPath);
      console.log(JSON.stringify(importResult, null, 2));
      break;

    case "--help":
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
  importCheckpoint,
};
