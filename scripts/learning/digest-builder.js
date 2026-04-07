#!/usr/bin/env node
/**
 * Digest Builder for Learning System
 *
 * Replaces the instinct-processor + instinct-evolver pipeline.
 * Reads observations.jsonl and produces learning-digest.json — a structured
 * summary consumed by /codify where the LLM does semantic analysis.
 *
 * This script does PURE AGGREGATION — no confidence scores, no pattern
 * matching, no frequency counting. The LLM in /codify does the thinking.
 *
 * Usage:
 *   node digest-builder.js                    Build digest from observations
 *   node digest-builder.js --stats            Show observation statistics
 *   node digest-builder.js --help             Show help
 */

const fs = require("fs");
const path = require("path");
const { resolveLearningDir } = require("../hooks/lib/learning-utils");

/**
 * Load all observations from JSONL file.
 * @param {string} learningDir
 * @returns {Array} Parsed observations
 */
function loadObservations(learningDir) {
  const observationsFile = path.join(learningDir, "observations.jsonl");
  if (!fs.existsSync(observationsFile)) return [];

  const content = fs.readFileSync(observationsFile, "utf8");
  return content
    .trim()
    .split("\n")
    .filter((l) => l)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

/**
 * Build the learning digest from observations.
 * Pure aggregation — groups observations by type for /codify consumption.
 *
 * @param {string} cwd - Project working directory
 * @param {string} [learningDir] - Override learning directory
 * @returns {Object} The digest object
 */
function buildDigest(cwd, learningDir) {
  const dir = learningDir || resolveLearningDir(cwd);
  const observations = loadObservations(dir);

  if (observations.length === 0) {
    return null;
  }

  // Determine the time period covered
  const timestamps = observations
    .map((o) => o.timestamp)
    .filter(Boolean)
    .sort();
  const period = {
    from: timestamps[0] || null,
    to: timestamps[timestamps.length - 1] || null,
    observation_count: observations.length,
  };

  // --- User corrections (most valuable signal) ---
  const corrections = observations
    .filter((o) => o.type === "user_correction")
    .map((o) => ({
      message: o.data?.message || "",
      session: o.context?.session_id || "unknown",
      timestamp: o.timestamp,
    }));

  // --- Rule violations (recurring = rule needs strengthening) ---
  const violationMap = {};
  observations
    .filter((o) => o.type === "rule_violation")
    .forEach((o) => {
      const rule = o.data?.rule || "unknown";
      if (!violationMap[rule]) {
        violationMap[rule] = { rule, count: 0, files: new Set(), messages: [] };
      }
      violationMap[rule].count++;
      if (o.data?.file) violationMap[rule].files.add(o.data.file);
      if (o.data?.message && violationMap[rule].messages.length < 3) {
        violationMap[rule].messages.push(o.data.message);
      }
    });
  const errorPatterns = Object.values(violationMap).map((v) => ({
    rule: v.rule,
    count: v.count,
    files: [...v.files].slice(0, 5),
    sample_messages: v.messages,
  }));

  // --- Session accomplishments ---
  const accomplishments = observations
    .filter((o) => o.type === "session_accomplishment")
    .map((o) => ({
      workspace: o.data?.workspace || null,
      accomplishments: o.data?.accomplishments || "",
      timestamp: o.timestamp,
    }));

  // --- Decision references (from journals) ---
  const decisions = observations
    .filter((o) => o.type === "decision_reference")
    .map((o) => ({
      type: o.data?.type || "unknown",
      topic: o.data?.topic || "unknown",
      file: o.data?.file || null,
      timestamp: o.timestamp,
    }));

  // --- Active frameworks (what's being used) ---
  const frameworkCounts = {};
  observations
    .filter((o) => o.type === "framework_selection")
    .forEach((o) => {
      const fw = o.data?.framework;
      if (fw) frameworkCounts[fw] = (frameworkCounts[fw] || 0) + 1;
    });

  // --- Workflow patterns (structural, for context) ---
  const workflowPatterns = observations
    .filter((o) => o.type === "workflow_pattern")
    .reduce((acc, o) => {
      const nodeTypes = o.data?.node_types || [];
      if (nodeTypes.length > 0) {
        const key = [...nodeTypes].sort().join("+");
        if (!acc[key]) acc[key] = { node_types: nodeTypes, count: 0 };
        acc[key].count++;
      }
      return acc;
    }, {});

  const digest = {
    version: "2.0",
    built_at: new Date().toISOString(),
    period,
    corrections,
    error_patterns: errorPatterns,
    accomplishments,
    decisions,
    active_frameworks: frameworkCounts,
    workflow_patterns: Object.values(workflowPatterns),
  };

  // Write digest to file
  const digestPath = path.join(dir, "learning-digest.json");
  fs.writeFileSync(digestPath, JSON.stringify(digest, null, 2));

  return digest;
}

/**
 * Get observation statistics.
 * @param {string} [learningDir]
 * @returns {Object} Stats breakdown
 */
function getStats(learningDir) {
  const dir = learningDir || resolveLearningDir();
  const observations = loadObservations(dir);

  const typeBreakdown = {};
  for (const obs of observations) {
    typeBreakdown[obs.type] = (typeBreakdown[obs.type] || 0) + 1;
  }

  // Check for existing digest
  const digestPath = path.join(dir, "learning-digest.json");
  let digestAge = null;
  if (fs.existsSync(digestPath)) {
    try {
      const digest = JSON.parse(fs.readFileSync(digestPath, "utf8"));
      digestAge = digest.built_at || null;
    } catch {}
  }

  return {
    total_observations: observations.length,
    type_breakdown: typeBreakdown,
    last_digest: digestAge,
    archive_count: countArchives(dir),
  };
}

function countArchives(learningDir) {
  const archiveDir = path.join(learningDir, "observations.archive");
  if (!fs.existsSync(archiveDir)) return 0;
  try {
    return fs.readdirSync(archiveDir).filter((f) => f.endsWith(".jsonl"))
      .length;
  } catch {
    return 0;
  }
}

// --- Main execution ---
if (require.main === module) {
  const args = process.argv.slice(2);

  if (args.includes("--help")) {
    console.log(`
Digest Builder for Learning System

Reads observations.jsonl and produces learning-digest.json for /codify.

Usage:
  node digest-builder.js          Build digest from observations
  node digest-builder.js --stats  Show observation statistics
  node digest-builder.js --help   Show this help
`);
    process.exit(0);
  }

  if (args.includes("--stats")) {
    console.log(JSON.stringify(getStats(), null, 2));
    process.exit(0);
  }

  // Default: build digest
  const cwd = process.cwd();
  const digest = buildDigest(cwd);
  if (digest) {
    console.log(
      JSON.stringify(
        {
          success: true,
          period: digest.period,
          corrections: digest.corrections.length,
          error_patterns: digest.error_patterns.length,
          accomplishments: digest.accomplishments.length,
          decisions: digest.decisions.length,
        },
        null,
        2,
      ),
    );
  } else {
    console.log(JSON.stringify({ success: false, reason: "no observations" }));
  }
  process.exit(0);
}

module.exports = {
  buildDigest,
  loadObservations,
  getStats,
};
