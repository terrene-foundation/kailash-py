/**
 * Shared utility: Per-project learning directory resolution and observation logging.
 *
 * Used by all hooks and learning scripts to ensure observations are stored
 * per-project (in <project>/.claude/learning/) rather than globally.
 */

const fs = require("fs");
const path = require("path");
const os = require("os");

/**
 * Resolve the learning directory for a given project.
 *
 * Priority:
 *   1. KAILASH_LEARNING_DIR env var (for testing)
 *   2. <cwd>/.claude/learning/ (per-project)
 *   3. ~/.claude/kailash-learning/ (legacy fallback)
 *
 * @param {string} [cwd] - Project working directory
 * @returns {string} Absolute path to the learning directory
 */
function resolveLearningDir(cwd) {
  if (process.env.KAILASH_LEARNING_DIR) {
    return process.env.KAILASH_LEARNING_DIR;
  }
  if (cwd) {
    return path.join(cwd, ".claude", "learning");
  }
  return path.join(os.homedir(), ".claude", "kailash-learning");
}

/**
 * Ensure the learning directory and its subdirectories exist.
 *
 * @param {string} [cwd] - Project working directory
 * @returns {string} The resolved learning directory path
 */
function ensureLearningDir(cwd) {
  const learningDir = resolveLearningDir(cwd);

  const dirs = [
    learningDir,
    path.join(learningDir, "observations.archive"),
    path.join(learningDir, "instincts", "personal"),
    path.join(learningDir, "instincts", "inherited"),
    path.join(learningDir, "evolved", "skills"),
    path.join(learningDir, "evolved", "commands"),
    path.join(learningDir, "evolved", "agents"),
    path.join(learningDir, "checkpoints"),
  ];

  for (const dir of dirs) {
    try {
      fs.mkdirSync(dir, { recursive: true });
    } catch {}
  }

  // Create identity file if it doesn't exist
  const identityFile = path.join(learningDir, "identity.json");
  if (!fs.existsSync(identityFile)) {
    try {
      const identity = {
        system: "kailash-vibe-cc-setup",
        version: "2.0.0",
        created_at: new Date().toISOString(),
        learning_enabled: true,
        per_project: true,
        focus_areas: [
          "workflow-patterns",
          "error-fixes",
          "dataflow-patterns",
          "testing-patterns",
          "framework-selection",
        ],
      };
      fs.writeFileSync(identityFile, JSON.stringify(identity, null, 2));
    } catch {}
  }

  return learningDir;
}

/**
 * Append an observation to the per-project observations.jsonl file.
 *
 * @param {string} cwd - Project working directory
 * @param {string} type - Observation type (e.g. "workflow_pattern", "error_occurrence")
 * @param {Object} data - Observation data payload
 * @param {Object} [context] - Additional context (session_id, framework, etc.)
 */
function logObservation(cwd, type, data, context) {
  try {
    const learningDir = ensureLearningDir(cwd);
    const observationsFile = path.join(learningDir, "observations.jsonl");

    const observation = {
      id: `obs_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date().toISOString(),
      type,
      data,
      context: {
        session_id: "unknown",
        cwd: cwd || process.cwd(),
        framework: "unknown",
        ...context,
      },
    };

    fs.appendFileSync(observationsFile, JSON.stringify(observation) + "\n");
    return observation.id;
  } catch {
    return null;
  }
}

/**
 * Count observations in the current observations.jsonl file.
 *
 * @param {string} learningDir - Learning directory path
 * @returns {number} Number of observations
 */
function countObservations(learningDir) {
  try {
    const observationsFile = path.join(learningDir, "observations.jsonl");
    if (!fs.existsSync(observationsFile)) return 0;
    const content = fs.readFileSync(observationsFile, "utf8");
    return content
      .trim()
      .split("\n")
      .filter((l) => l).length;
  } catch {
    return 0;
  }
}

module.exports = {
  resolveLearningDir,
  ensureLearningDir,
  logObservation,
  countObservations,
};
