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
const MAX_OBSERVATIONS = 1000;

/**
 * Resolve paths for a given learning directory.
 * @param {string} [learningDir] - Override learning dir; falls back to resolveLearningDir()
 * @returns {{ learningDir: string, observationsFile: string, archiveDir: string, identityFile: string }}
 */
function resolvePaths(learningDir) {
  const dir = learningDir || resolveLearningDir();
  return {
    learningDir: dir,
    observationsFile: path.join(dir, "observations.jsonl"),
    archiveDir: path.join(dir, "observations.archive"),
    identityFile: path.join(dir, "identity.json"),
  };
}

/**
 * Initialize learning directory structure
 * @param {string} [learningDir] - Override learning directory
 */
function initializeLearningDir(learningDir) {
  const p = resolvePaths(learningDir);
  const dirs = [
    p.learningDir,
    p.archiveDir,
    path.join(p.learningDir, "instincts", "personal"),
    path.join(p.learningDir, "instincts", "inherited"),
    path.join(p.learningDir, "evolved", "skills"),
    path.join(p.learningDir, "evolved", "commands"),
    path.join(p.learningDir, "evolved", "agents"),
  ];
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

// Observation types for Kailash-specific patterns
const OBSERVATION_TYPES = {
  TOOL_USE: "tool_use",
  WORKFLOW_PATTERN: "workflow_pattern",
  ERROR_OCCURRENCE: "error_occurrence",
  ERROR_FIX: "error_fix",
  FRAMEWORK_SELECTION: "framework_selection",
  NODE_USAGE: "node_usage",
  CONNECTION_PATTERN: "connection_pattern",
  TEST_PATTERN: "test_pattern",
  DATAFLOW_MODEL: "dataflow_model",
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
