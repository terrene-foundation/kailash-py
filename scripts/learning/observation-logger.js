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
 *   Appends observation to ~/.claude/kailash-learning/observations.jsonl
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

// Learning directory structure - supports env var override for testing
const LEARNING_DIR = process.env.KAILASH_LEARNING_DIR || path.join(os.homedir(), '.claude', 'kailash-learning');
const OBSERVATIONS_FILE = path.join(LEARNING_DIR, 'observations.jsonl');
const ARCHIVE_DIR = path.join(LEARNING_DIR, 'observations.archive');
const IDENTITY_FILE = path.join(LEARNING_DIR, 'identity.json');

// Maximum observations before archiving
const MAX_OBSERVATIONS = 1000;

/**
 * Initialize learning directory structure
 */
function initializeLearningDir() {
  const dirs = [
    LEARNING_DIR,
    ARCHIVE_DIR,
    path.join(LEARNING_DIR, 'instincts', 'personal'),
    path.join(LEARNING_DIR, 'instincts', 'inherited'),
    path.join(LEARNING_DIR, 'evolved', 'skills'),
    path.join(LEARNING_DIR, 'evolved', 'commands'),
    path.join(LEARNING_DIR, 'evolved', 'agents')
  ];

  dirs.forEach(dir => {
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  });

  // Create identity file if not exists
  if (!fs.existsSync(IDENTITY_FILE)) {
    const identity = {
      system: 'kailash-vibe-cc-setup',
      version: '1.0.0',
      created_at: new Date().toISOString(),
      learning_enabled: true,
      focus_areas: [
        'workflow-patterns',
        'error-fixes',
        'dataflow-patterns',
        'testing-patterns',
        'framework-selection'
      ]
    };
    fs.writeFileSync(IDENTITY_FILE, JSON.stringify(identity, null, 2));
  }
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
      session_id: context.session_id || 'unknown',
      cwd: context.cwd || process.cwd(),
      framework: context.framework || 'unknown',
      ...context
    },
    metadata: {
      version: '1.0',
      source: 'hook'
    }
  };
}

/**
 * Log an observation to the JSONL file
 */
function logObservation(observation) {
  initializeLearningDir();

  const line = JSON.stringify(observation) + '\n';
  fs.appendFileSync(OBSERVATIONS_FILE, line);

  // Check if archiving needed
  checkAndArchive();

  return observation.id;
}

/**
 * Check observation count and archive if needed
 */
function checkAndArchive() {
  if (!fs.existsSync(OBSERVATIONS_FILE)) return;

  const content = fs.readFileSync(OBSERVATIONS_FILE, 'utf8');
  const lines = content.trim().split('\n').filter(l => l);

  if (lines.length >= MAX_OBSERVATIONS) {
    // Archive current file
    const archiveName = `observations_${Date.now()}.jsonl`;
    const archivePath = path.join(ARCHIVE_DIR, archiveName);
    fs.renameSync(OBSERVATIONS_FILE, archivePath);

    // Create new empty observations file
    fs.writeFileSync(OBSERVATIONS_FILE, '');
  }
}

/**
 * Get observation statistics
 */
function getStats() {
  initializeLearningDir();

  let totalObservations = 0;
  let typeBreakdown = {};

  // Count current observations
  if (fs.existsSync(OBSERVATIONS_FILE)) {
    const content = fs.readFileSync(OBSERVATIONS_FILE, 'utf8');
    const lines = content.trim().split('\n').filter(l => l);
    totalObservations += lines.length;

    lines.forEach(line => {
      try {
        const obs = JSON.parse(line);
        typeBreakdown[obs.type] = (typeBreakdown[obs.type] || 0) + 1;
      } catch (e) { }
    });
  }

  // Count archived observations
  if (fs.existsSync(ARCHIVE_DIR)) {
    const archives = fs.readdirSync(ARCHIVE_DIR);
    archives.forEach(archive => {
      const content = fs.readFileSync(path.join(ARCHIVE_DIR, archive), 'utf8');
      const lines = content.trim().split('\n').filter(l => l);
      totalObservations += lines.length;
    });
  }

  return {
    total_observations: totalObservations,
    current_file: fs.existsSync(OBSERVATIONS_FILE)
      ? fs.readFileSync(OBSERVATIONS_FILE, 'utf8').trim().split('\n').filter(l => l).length
      : 0,
    archives: fs.existsSync(ARCHIVE_DIR) ? fs.readdirSync(ARCHIVE_DIR).length : 0,
    type_breakdown: typeBreakdown
  };
}

// Observation types for Kailash-specific patterns
const OBSERVATION_TYPES = {
  TOOL_USE: 'tool_use',
  WORKFLOW_PATTERN: 'workflow_pattern',
  ERROR_OCCURRENCE: 'error_occurrence',
  ERROR_FIX: 'error_fix',
  FRAMEWORK_SELECTION: 'framework_selection',
  NODE_USAGE: 'node_usage',
  CONNECTION_PATTERN: 'connection_pattern',
  TEST_PATTERN: 'test_pattern',
  DATAFLOW_MODEL: 'dataflow_model',
  SESSION_SUMMARY: 'session_summary'
};

// Main execution
if (require.main === module) {
  const args = process.argv.slice(2);

  // Handle --stats flag
  if (args.includes('--stats')) {
    initializeLearningDir();
    console.log(JSON.stringify(getStats(), null, 2));
    process.exit(0);
  }

  // Handle --help flag
  if (args.includes('--help')) {
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
  let input = '';

  process.stdin.on('data', chunk => {
    input += chunk;
  });

  process.stdin.on('end', () => {
    try {
      const data = JSON.parse(input);
      const type = data.type || OBSERVATION_TYPES.TOOL_USE;
      const observation = createObservation(type, data.data || data, data.context || {});
      const id = logObservation(observation);

      // Output result
      console.log(JSON.stringify({
        success: true,
        observation_id: id,
        stats: getStats()
      }));

      process.exit(0);
    } catch (error) {
      console.error(JSON.stringify({
        success: false,
        error: error.message
      }));
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
  OBSERVATION_TYPES,
  LEARNING_DIR,
  OBSERVATIONS_FILE
};
