#!/usr/bin/env node
/**
 * Observation Logger for Kailash Continuous Learning System
 *
 * Captures tool usage, patterns, and session data for learning.
 * Part of Phase 4: Continuous Learning implementation.
 *
 * Usage:
 *   echo '{"type": "tool_use", "data": {...}}' | node observation-logger.js
 *
 * Output:
 *   Appends observation to <project>/.claude/learning/observations.jsonl
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const { resolveLearningDir } = require("../hooks/lib/learning-utils");

// Maximum observations before archiving
const MAX_OBSERVATIONS = 500;

/**
 * Resolve paths for a given learning directory.
 * @param {string} [learningDir] - Override learning dir; falls back to resolveLearningDir()
 * @returns {{ learningDir: string, observationsFile: string, archiveDir: string }}
 */
function resolvePaths(learningDir) {
  const dir = learningDir || resolveLearningDir();
  return {
    learningDir: dir,
    observationsFile: path.join(dir, "observations.jsonl"),
    archiveDir: path.join(dir, "observations.archive"),
  };
}

/**
 * Initialize learning directory structure
 * @param {string} [learningDir] - Override learning directory
 */
function initializeLearningDir(learningDir) {
  const p = resolvePaths(learningDir);
  const dirs = [p.learningDir, p.archiveDir];
  dirs.forEach((dir) => {
    try {
      fs.mkdirSync(dir, { recursive: true });
    } catch {}
  });
}

/**
 * Observation schema
 */
function createObservation(type, data, context = {}) {
  return {
    id: `obs_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    timestamp: new Date().toISOString(),
    type: type,
    data: data,
    context: {
      session_id: context.session_id || "unknown",
      cwd: context.cwd || process.cwd(),
      framework: context.framework || "unknown",
      ...context,
    },
    metadata: {
      version: "1.0",
      source: "hook",
    },
  };
}

/**
 * Log an observation to the JSONL file
 * @param {Object} observation - The observation object
 * @param {string} [learningDir] - Override learning directory
 */
function logObservation(observation, learningDir) {
  initializeLearningDir(learningDir);
  const p = resolvePaths(learningDir);

  const line = JSON.stringify(observation) + "\n";
  fs.appendFileSync(p.observationsFile, line);

  // Check if archiving needed
  checkAndArchive(learningDir);

  return observation.id;
}

/**
 * Check observation count and archive if needed
 * @param {string} [learningDir] - Override learning directory
 */
function checkAndArchive(learningDir) {
  const p = resolvePaths(learningDir);
  if (!fs.existsSync(p.observationsFile)) return;

  const content = fs.readFileSync(p.observationsFile, "utf8");
  const lines = content
    .trim()
    .split("\n")
    .filter((l) => l);

  if (lines.length >= MAX_OBSERVATIONS) {
    // Archive current file
    const archiveName = `observations_${Date.now()}.jsonl`;
    const archivePath = path.join(p.archiveDir, archiveName);
    try {
      fs.mkdirSync(p.archiveDir, { recursive: true });
    } catch {}
    fs.renameSync(p.observationsFile, archivePath);

    // Create new empty observations file
    fs.writeFileSync(p.observationsFile, "");
  }
}

/**
 * Get observation statistics
 * @param {string} [learningDir] - Override learning directory
 */
function getStats(learningDir) {
  initializeLearningDir(learningDir);
  const p = resolvePaths(learningDir);

  let totalObservations = 0;
  let typeBreakdown = {};

  // Count current observations
  if (fs.existsSync(p.observationsFile)) {
    const content = fs.readFileSync(p.observationsFile, "utf8");
    const lines = content
      .trim()
      .split("\n")
      .filter((l) => l);
    totalObservations += lines.length;

    lines.forEach((line) => {
      try {
        const obs = JSON.parse(line);
        typeBreakdown[obs.type] = (typeBreakdown[obs.type] || 0) + 1;
      } catch (e) {}
    });
  }

  // Count archived observations
  if (fs.existsSync(p.archiveDir)) {
    const archives = fs.readdirSync(p.archiveDir);
    archives.forEach((archive) => {
      const content = fs.readFileSync(path.join(p.archiveDir, archive), "utf8");
      const lines = content
        .trim()
        .split("\n")
        .filter((l) => l);
      totalObservations += lines.length;
    });
  }

  return {
    total_observations: totalObservations,
    current_file: fs.existsSync(p.observationsFile)
      ? fs
          .readFileSync(p.observationsFile, "utf8")
          .trim()
          .split("\n")
          .filter((l) => l).length
      : 0,
    archives: fs.existsSync(p.archiveDir)
      ? fs.readdirSync(p.archiveDir).length
      : 0,
    type_breakdown: typeBreakdown,
  };
}

// Observation types — meaningful signals only (noise types removed)
const OBSERVATION_TYPES = {
  // Kept from original — capture real code patterns
  WORKFLOW_PATTERN: "workflow_pattern",
  FRAMEWORK_SELECTION: "framework_selection",
  NODE_USAGE: "node_usage",
  DATAFLOW_MODEL: "dataflow_model",
  // Replaced: error_occurrence → rule_violation (with specific rule name)
  RULE_VIOLATION: "rule_violation",
  // New — meaningful learning signals
  USER_CORRECTION: "user_correction",
  SESSION_ACCOMPLISHMENT: "session_accomplishment",
  DECISION_REFERENCE: "decision_reference",
  // Kept but deprioritized
  SESSION_SUMMARY: "session_summary",
};

// Main execution
if (require.main === module) {
  const args = process.argv.slice(2);

  // Handle --stats flag
  if (args.includes("--stats")) {
    initializeLearningDir();
    console.log(JSON.stringify(getStats(), null, 2));
    process.exit(0);
  }

  // Handle --help flag
  if (args.includes("--help")) {
    console.log(`
Observation Logger for Kailash Continuous Learning

Usage:
  echo '{"type": "...", "data": {...}}' | node observation-logger.js
  node observation-logger.js --stats   Show observation statistics
  node observation-logger.js --help    Show this help
`);
    process.exit(0);
  }

  // Default: read from stdin
  let input = "";

  process.stdin.on("data", (chunk) => {
    input += chunk;
  });

  process.stdin.on("end", () => {
    try {
      const data = JSON.parse(input);
      const type = data.type || OBSERVATION_TYPES.TOOL_USE;
      const observation = createObservation(
        type,
        data.data || data,
        data.context || {},
      );
      const id = logObservation(observation);

      // Output result
      console.log(
        JSON.stringify({
          success: true,
          observation_id: id,
          stats: getStats(),
        }),
      );

      process.exit(0);
    } catch (error) {
      console.error(
        JSON.stringify({
          success: false,
          error: error.message,
        }),
      );
      process.exit(1);
    }
  });
}

// Export for use in other scripts
module.exports = {
  createObservation,
  logObservation,
  getStats,
  initializeLearningDir,
  resolvePaths,
  OBSERVATION_TYPES,
};
