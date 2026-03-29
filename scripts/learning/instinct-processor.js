#!/usr/bin/env node
/**
 * Instinct Processor for Kailash Continuous Learning System
 *
 * Processes observations to detect patterns and create instincts.
 * Part of Phase 4: Continuous Learning implementation.
 *
 * Usage:
 *   node instinct-processor.js --analyze
 *   node instinct-processor.js --generate
 *   node instinct-processor.js --list
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
    observationsFile: path.join(dir, "observations.jsonl"),
    instinctsDir: path.join(dir, "instincts", "personal"),
    archiveDir: path.join(dir, "observations.archive"),
  };
}

/**
 * Instinct schema
 */
function createInstinct(pattern, confidence, source) {
  return {
    id: `instinct_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    pattern: pattern,
    confidence: confidence, // 0.3 - 0.9
    source: source,
    usage_count: 0,
    success_count: 0,
    metadata: {
      version: "1.0",
      active: true,
    },
  };
}

/**
 * Load all observations
 * @param {string} [learningDir] - Override learning directory
 */
function loadObservations(learningDir) {
  const p = resolvePaths(learningDir);
  const observations = [];

  if (fs.existsSync(p.observationsFile)) {
    const content = fs.readFileSync(p.observationsFile, "utf8");
    const lines = content
      .trim()
      .split("\n")
      .filter((l) => l);
    lines.forEach((line) => {
      try {
        observations.push(JSON.parse(line));
      } catch (e) {}
    });
  }

  // Also load from archives
  if (fs.existsSync(p.archiveDir)) {
    const archives = fs.readdirSync(p.archiveDir);
    archives.forEach((archive) => {
      const content = fs.readFileSync(path.join(p.archiveDir, archive), "utf8");
      const lines = content
        .trim()
        .split("\n")
        .filter((l) => l);
      lines.forEach((line) => {
        try {
          observations.push(JSON.parse(line));
        } catch (e) {}
      });
    });
  }

  return observations;
}

/**
 * Analyze observations for workflow patterns.
 * Keys on sorted node_types array for stable identity across sessions.
 */
function analyzeWorkflowPatterns(observations) {
  const patterns = {};

  observations
    .filter((o) => o.type === "workflow_pattern" || o.type === "node_usage")
    .forEach((obs) => {
      // Stable key: sorted node types (not full data blob)
      const nodeTypes = obs.data.node_types || [];
      const sortedTypes = [...nodeTypes].sort();
      const key =
        sortedTypes.length > 0
          ? sortedTypes.join("+")
          : obs.data.pattern_type || "unknown";
      const file = obs.data.file || "unknown";

      if (!patterns[key]) {
        patterns[key] = {
          node_types: sortedTypes,
          files: new Set(),
          has_cycles: false,
          runtimes: new Set(),
          count: 0,
        };
      }
      patterns[key].count++;
      patterns[key].files.add(file);
      if (obs.data.has_cycles) patterns[key].has_cycles = true;
      if (obs.data.runtime) patterns[key].runtimes.add(obs.data.runtime);
    });

  return Object.values(patterns)
    .filter((p) => p.count >= 3)
    .map((p) => ({
      type: "workflow_pattern",
      pattern: {
        node_types: p.node_types,
        has_cycles: p.has_cycles,
        runtimes: [...p.runtimes],
        files: [...p.files].slice(0, 5),
      },
      occurrences: p.count,
      unique_files: p.files.size,
      confidence: calculateConfidence(p.count, p.files.size),
    }));
}

/**
 * Analyze observations for error-fix pairs
 */
function analyzeErrorFixPatterns(observations) {
  const errors = observations.filter((o) => o.type === "error_occurrence");
  const fixes = observations.filter((o) => o.type === "error_fix");
  const pairs = [];

  // Match errors with subsequent fixes
  errors.forEach((error) => {
    const errorTime = new Date(error.timestamp).getTime();
    const matchingFix = fixes.find((fix) => {
      const fixTime = new Date(fix.timestamp).getTime();
      return (
        fixTime > errorTime &&
        fixTime - errorTime < 300000 && // Within 5 minutes
        fix.context.session_id === error.context.session_id
      );
    });

    if (matchingFix) {
      const key = `${error.data.error_type}:${matchingFix.data.fix_type}`;
      const existing = pairs.find((p) => p.key === key);
      if (existing) {
        existing.count++;
      } else {
        pairs.push({
          key,
          error: error.data,
          fix: matchingFix.data,
          count: 1,
        });
      }
    }
  });

  return pairs
    .filter((p) => p.count >= 2)
    .map((p) => ({
      type: "error_fix",
      pattern: { error: p.error, fix: p.fix },
      occurrences: p.count,
      confidence: Math.min(0.9, 0.4 + p.count * 0.15),
    }));
}

/**
 * Analyze observations for framework selection patterns
 */
function analyzeFrameworkPatterns(observations) {
  const selections = {};

  observations
    .filter((o) => o.type === "framework_selection")
    .forEach((obs) => {
      const framework = obs.data.framework || "unknown";
      const projectType = obs.data.project_type || "general";
      const key = `${projectType}:${framework}`;

      if (!selections[key]) {
        selections[key] = {
          project_type: projectType,
          framework,
          files: new Set(),
          count: 0,
        };
      }
      selections[key].count++;
      if (obs.data.file) selections[key].files.add(obs.data.file);
    });

  return Object.values(selections)
    .filter((s) => s.count >= 2)
    .map((s) => ({
      type: "framework_selection",
      pattern: {
        project_type: s.project_type,
        framework: s.framework,
        files: [...s.files].slice(0, 5),
      },
      occurrences: s.count,
      unique_files: s.files.size,
      confidence: calculateConfidence(s.count, s.files.size),
    }));
}

/**
 * Analyze observations for DataFlow model patterns
 */
function analyzeDataFlowPatterns(observations) {
  const models = {};

  observations
    .filter((o) => o.type === "dataflow_model")
    .forEach((obs) => {
      const names =
        obs.data.model_names || [obs.data.model_name].filter(Boolean);
      for (const name of names) {
        if (!models[name]) {
          models[name] = { model_name: name, files: new Set(), count: 0 };
        }
        models[name].count++;
        if (obs.data.file) models[name].files.add(obs.data.file);
      }
    });

  return Object.values(models)
    .filter((m) => m.count >= 2)
    .map((m) => ({
      type: "dataflow_model",
      pattern: {
        model_name: m.model_name,
        files: [...m.files].slice(0, 5),
      },
      occurrences: m.count,
      unique_files: m.files.size,
      confidence: calculateConfidence(m.count, m.files.size),
    }));
}

/**
 * Calculate confidence based on observation count and file diversity.
 * More diverse file usage = higher confidence (not just repetition in one file).
 */
function calculateConfidence(observationCount, uniqueFileCount) {
  // Base: 0.3 for meeting minimum threshold
  // +0.05 per observation (up to +0.3)
  // +0.1 per unique file (up to +0.3)
  // Cap at 0.9
  const obsBonus = Math.min(0.3, observationCount * 0.05);
  const fileBonus = Math.min(0.3, (uniqueFileCount || 1) * 0.1);
  return Math.min(0.9, 0.3 + obsBonus + fileBonus);
}

/**
 * Generate instincts from analyzed patterns
 */
function generateInstincts(patterns) {
  return patterns.map((pattern) =>
    createInstinct(pattern.pattern, pattern.confidence, {
      type: pattern.type,
      occurrences: pattern.occurrences,
      unique_files: pattern.unique_files || 0,
      generated_at: new Date().toISOString(),
    }),
  );
}

/**
 * Save instincts to file
 * @param {Array} instincts - Instincts to save
 * @param {string} category - Category name
 * @param {string} [learningDir] - Override learning directory
 */
function saveInstincts(instincts, category, learningDir) {
  const p = resolvePaths(learningDir);
  if (!fs.existsSync(p.instinctsDir)) {
    fs.mkdirSync(p.instinctsDir, { recursive: true });
  }

  const filePath = path.join(p.instinctsDir, `${category}.json`);
  let existing = [];

  if (fs.existsSync(filePath)) {
    existing = JSON.parse(fs.readFileSync(filePath, "utf8"));
  }

  // Merge new instincts, updating existing ones
  instincts.forEach((newInstinct) => {
    const existingIndex = existing.findIndex(
      (e) => JSON.stringify(e.pattern) === JSON.stringify(newInstinct.pattern),
    );

    if (existingIndex >= 0) {
      // Update existing instinct — take latest analysis values, don't inflate
      existing[existingIndex].confidence = newInstinct.confidence;
      existing[existingIndex].updated_at = new Date().toISOString();
      existing[existingIndex].source.occurrences = Math.max(
        existing[existingIndex].source.occurrences,
        newInstinct.source.occurrences,
      );
      existing[existingIndex].source.unique_files =
        newInstinct.source.unique_files || 0;
    } else {
      // Add new instinct
      existing.push(newInstinct);
    }
  });

  fs.writeFileSync(filePath, JSON.stringify(existing, null, 2));
  return existing.length;
}

/**
 * List all instincts
 * @param {string} [learningDir] - Override learning directory
 */
function listInstincts(learningDir) {
  const p = resolvePaths(learningDir);
  const result = {};

  if (fs.existsSync(p.instinctsDir)) {
    const files = fs.readdirSync(p.instinctsDir);
    files.forEach((file) => {
      if (file.endsWith(".json")) {
        const category = file.replace(".json", "");
        const content = JSON.parse(
          fs.readFileSync(path.join(p.instinctsDir, file), "utf8"),
        );
        result[category] = {
          count: content.length,
          instincts: content.map((i) => ({
            id: i.id,
            confidence: i.confidence,
            pattern_summary: JSON.stringify(i.pattern).substring(0, 50) + "...",
          })),
        };
      }
    });
  }

  return result;
}

/**
 * Main execution
 */
function main() {
  const args = process.argv.slice(2);
  const command = args[0] || "--help";

  switch (command) {
    case "--analyze":
      console.log("Analyzing observations...");
      const observations = loadObservations();
      console.log(`Loaded ${observations.length} observations`);

      const workflowPatterns = analyzeWorkflowPatterns(observations);
      const errorFixPatterns = analyzeErrorFixPatterns(observations);
      const frameworkPatterns = analyzeFrameworkPatterns(observations);

      console.log(`Found ${workflowPatterns.length} workflow patterns`);
      console.log(`Found ${errorFixPatterns.length} error-fix patterns`);
      console.log(`Found ${frameworkPatterns.length} framework patterns`);

      console.log(
        JSON.stringify(
          {
            workflow_patterns: workflowPatterns,
            error_fix_patterns: errorFixPatterns,
            framework_patterns: frameworkPatterns,
          },
          null,
          2,
        ),
      );
      break;

    case "--generate":
      console.log("Generating instincts...");
      const obs = loadObservations();

      const wp = analyzeWorkflowPatterns(obs);
      const efp = analyzeErrorFixPatterns(obs);
      const fp = analyzeFrameworkPatterns(obs);

      if (wp.length > 0) {
        const wpInstincts = generateInstincts(wp);
        const wpCount = saveInstincts(wpInstincts, "workflow-patterns");
        console.log(`Saved ${wpCount} workflow pattern instincts`);
      }

      if (efp.length > 0) {
        const efpInstincts = generateInstincts(efp);
        const efpCount = saveInstincts(efpInstincts, "error-fixes");
        console.log(`Saved ${efpCount} error-fix instincts`);
      }

      if (fp.length > 0) {
        const fpInstincts = generateInstincts(fp);
        const fpCount = saveInstincts(fpInstincts, "framework-selection");
        console.log(`Saved ${fpCount} framework selection instincts`);
      }

      console.log("Instinct generation complete");
      break;

    case "--list":
      const instincts = listInstincts();
      console.log(JSON.stringify(instincts, null, 2));
      break;

    case "--help":
    default:
      console.log(`
Instinct Processor for Kailash Continuous Learning

Usage:
  node instinct-processor.js --analyze   Analyze observations for patterns
  node instinct-processor.js --generate  Generate instincts from patterns
  node instinct-processor.js --list      List all instincts
  node instinct-processor.js --help      Show this help
`);
      break;
  }
}

if (require.main === module) {
  main();
}

module.exports = {
  loadObservations,
  analyzeWorkflowPatterns,
  analyzeErrorFixPatterns,
  analyzeFrameworkPatterns,
  analyzeDataFlowPatterns,
  generateInstincts,
  saveInstincts,
  listInstincts,
  createInstinct,
  calculateConfidence,
};
