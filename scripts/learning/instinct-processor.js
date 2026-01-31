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

const fs = require('fs');
const path = require('path');
const os = require('os');

// Learning directory structure - supports env var override for testing
const LEARNING_DIR = process.env.KAILASH_LEARNING_DIR || path.join(os.homedir(), '.claude', 'kailash-learning');
const OBSERVATIONS_FILE = path.join(LEARNING_DIR, 'observations.jsonl');
const INSTINCTS_DIR = path.join(LEARNING_DIR, 'instincts', 'personal');

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
      version: '1.0',
      active: true
    }
  };
}

/**
 * Load all observations
 */
function loadObservations() {
  const observations = [];

  if (fs.existsSync(OBSERVATIONS_FILE)) {
    const content = fs.readFileSync(OBSERVATIONS_FILE, 'utf8');
    const lines = content.trim().split('\n').filter(l => l);
    lines.forEach(line => {
      try {
        observations.push(JSON.parse(line));
      } catch (e) { }
    });
  }

  // Also load from archives
  const archiveDir = path.join(LEARNING_DIR, 'observations.archive');
  if (fs.existsSync(archiveDir)) {
    const archives = fs.readdirSync(archiveDir);
    archives.forEach(archive => {
      const content = fs.readFileSync(path.join(archiveDir, archive), 'utf8');
      const lines = content.trim().split('\n').filter(l => l);
      lines.forEach(line => {
        try {
          observations.push(JSON.parse(line));
        } catch (e) { }
      });
    });
  }

  return observations;
}

/**
 * Analyze observations for workflow patterns
 */
function analyzeWorkflowPatterns(observations) {
  const patterns = {};

  observations
    .filter(o => o.type === 'workflow_pattern' || o.type === 'node_usage')
    .forEach(obs => {
      const key = JSON.stringify(obs.data);
      if (!patterns[key]) {
        patterns[key] = { data: obs.data, count: 0, contexts: [] };
      }
      patterns[key].count++;
      patterns[key].contexts.push(obs.context);
    });

  return Object.values(patterns)
    .filter(p => p.count >= 3) // Minimum 3 occurrences
    .map(p => ({
      type: 'workflow_pattern',
      pattern: p.data,
      occurrences: p.count,
      confidence: Math.min(0.9, 0.3 + (p.count * 0.1))
    }));
}

/**
 * Analyze observations for error-fix pairs
 */
function analyzeErrorFixPatterns(observations) {
  const errors = observations.filter(o => o.type === 'error_occurrence');
  const fixes = observations.filter(o => o.type === 'error_fix');
  const pairs = [];

  // Match errors with subsequent fixes
  errors.forEach(error => {
    const errorTime = new Date(error.timestamp).getTime();
    const matchingFix = fixes.find(fix => {
      const fixTime = new Date(fix.timestamp).getTime();
      return fixTime > errorTime &&
        fixTime - errorTime < 300000 && // Within 5 minutes
        fix.context.session_id === error.context.session_id;
    });

    if (matchingFix) {
      const key = `${error.data.error_type}:${matchingFix.data.fix_type}`;
      const existing = pairs.find(p => p.key === key);
      if (existing) {
        existing.count++;
      } else {
        pairs.push({
          key,
          error: error.data,
          fix: matchingFix.data,
          count: 1
        });
      }
    }
  });

  return pairs
    .filter(p => p.count >= 2)
    .map(p => ({
      type: 'error_fix',
      pattern: { error: p.error, fix: p.fix },
      occurrences: p.count,
      confidence: Math.min(0.9, 0.4 + (p.count * 0.15))
    }));
}

/**
 * Analyze observations for framework selection patterns
 */
function analyzeFrameworkPatterns(observations) {
  const selections = {};

  observations
    .filter(o => o.type === 'framework_selection')
    .forEach(obs => {
      const key = `${obs.data.project_type}:${obs.data.framework}`;
      if (!selections[key]) {
        selections[key] = {
          project_type: obs.data.project_type,
          framework: obs.data.framework,
          count: 0
        };
      }
      selections[key].count++;
    });

  return Object.values(selections)
    .filter(s => s.count >= 2)
    .map(s => ({
      type: 'framework_selection',
      pattern: { project_type: s.project_type, framework: s.framework },
      occurrences: s.count,
      confidence: Math.min(0.9, 0.4 + (s.count * 0.1))
    }));
}

/**
 * Generate instincts from analyzed patterns
 */
function generateInstincts(patterns) {
  const instincts = [];

  patterns.forEach(pattern => {
    const instinct = createInstinct(
      pattern.pattern,
      pattern.confidence,
      {
        type: pattern.type,
        occurrences: pattern.occurrences,
        generated_at: new Date().toISOString()
      }
    );
    instincts.push(instinct);
  });

  return instincts;
}

/**
 * Save instincts to file
 */
function saveInstincts(instincts, category) {
  if (!fs.existsSync(INSTINCTS_DIR)) {
    fs.mkdirSync(INSTINCTS_DIR, { recursive: true });
  }

  const filePath = path.join(INSTINCTS_DIR, `${category}.json`);
  let existing = [];

  if (fs.existsSync(filePath)) {
    existing = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  }

  // Merge new instincts, updating existing ones
  instincts.forEach(newInstinct => {
    const existingIndex = existing.findIndex(e =>
      JSON.stringify(e.pattern) === JSON.stringify(newInstinct.pattern)
    );

    if (existingIndex >= 0) {
      // Update existing instinct
      existing[existingIndex].confidence = Math.max(
        existing[existingIndex].confidence,
        newInstinct.confidence
      );
      existing[existingIndex].updated_at = new Date().toISOString();
      existing[existingIndex].source.occurrences += newInstinct.source.occurrences;
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
 */
function listInstincts() {
  const result = {};

  if (fs.existsSync(INSTINCTS_DIR)) {
    const files = fs.readdirSync(INSTINCTS_DIR);
    files.forEach(file => {
      if (file.endsWith('.json')) {
        const category = file.replace('.json', '');
        const content = JSON.parse(fs.readFileSync(path.join(INSTINCTS_DIR, file), 'utf8'));
        result[category] = {
          count: content.length,
          instincts: content.map(i => ({
            id: i.id,
            confidence: i.confidence,
            pattern_summary: JSON.stringify(i.pattern).substring(0, 50) + '...'
          }))
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
  const command = args[0] || '--help';

  switch (command) {
    case '--analyze':
      console.log('Analyzing observations...');
      const observations = loadObservations();
      console.log(`Loaded ${observations.length} observations`);

      const workflowPatterns = analyzeWorkflowPatterns(observations);
      const errorFixPatterns = analyzeErrorFixPatterns(observations);
      const frameworkPatterns = analyzeFrameworkPatterns(observations);

      console.log(`Found ${workflowPatterns.length} workflow patterns`);
      console.log(`Found ${errorFixPatterns.length} error-fix patterns`);
      console.log(`Found ${frameworkPatterns.length} framework patterns`);

      console.log(JSON.stringify({
        workflow_patterns: workflowPatterns,
        error_fix_patterns: errorFixPatterns,
        framework_patterns: frameworkPatterns
      }, null, 2));
      break;

    case '--generate':
      console.log('Generating instincts...');
      const obs = loadObservations();

      const wp = analyzeWorkflowPatterns(obs);
      const efp = analyzeErrorFixPatterns(obs);
      const fp = analyzeFrameworkPatterns(obs);

      if (wp.length > 0) {
        const wpInstincts = generateInstincts(wp);
        const wpCount = saveInstincts(wpInstincts, 'workflow-patterns');
        console.log(`Saved ${wpCount} workflow pattern instincts`);
      }

      if (efp.length > 0) {
        const efpInstincts = generateInstincts(efp);
        const efpCount = saveInstincts(efpInstincts, 'error-fixes');
        console.log(`Saved ${efpCount} error-fix instincts`);
      }

      if (fp.length > 0) {
        const fpInstincts = generateInstincts(fp);
        const fpCount = saveInstincts(fpInstincts, 'framework-selection');
        console.log(`Saved ${fpCount} framework selection instincts`);
      }

      console.log('Instinct generation complete');
      break;

    case '--list':
      const instincts = listInstincts();
      console.log(JSON.stringify(instincts, null, 2));
      break;

    case '--help':
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
  generateInstincts,
  saveInstincts,
  listInstincts,
  createInstinct
};
