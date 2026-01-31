#!/usr/bin/env node
/**
 * Rules Validation Script for CI
 *
 * Validates all rule files meet quality standards:
 * - Scope clearly defined
 * - MUST rules are enforceable
 * - MUST NOT rules are detectable
 * - No contradictions between rules
 */

const fs = require('fs');
const path = require('path');

const RULES_DIR = path.join(process.cwd(), '.claude', 'rules');

/**
 * Validate single rule file
 */
function validateRule(filePath) {
  const errors = [];
  const warnings = [];
  const fileName = path.basename(filePath);

  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n');

    // Check for scope definition
    if (!content.includes('## Scope') && !content.includes('## Applies')) {
      warnings.push('Missing Scope/Applies section');
    }

    // Check for MUST rules
    const mustCount = (content.match(/\bMUST\b/g) || []).length;
    const mustNotCount = (content.match(/MUST NOT/g) || []).length;

    if (mustCount === 0 && mustNotCount === 0) {
      warnings.push('No MUST or MUST NOT rules defined');
    }

    // Check for enforcement mechanism
    if (!content.includes('## Enforcement') && !content.includes('## Validation') &&
        !content.includes('hook') && !content.includes('validate')) {
      warnings.push('No enforcement mechanism specified');
    }

    // Check for examples
    if (!content.includes('```') && !content.includes('Example')) {
      warnings.push('No examples provided');
    }

    // Check for checkmarks (good/bad examples)
    // Accept various marker styles: ✓/✗, ✅/❌, Good:/Bad:, Correct:/Incorrect:
    const hasGoodBadMarkers =
      content.includes('✓') || content.includes('✗') ||
      content.includes('✅') || content.includes('❌') ||
      content.includes('Good:') || content.includes('Bad:') ||
      content.includes('Correct') || content.includes('Incorrect');

    if (!hasGoodBadMarkers) {
      warnings.push('No good/bad example markers');
    }

    // Extract rule statements
    const ruleStatements = [];
    lines.forEach(line => {
      if (line.includes('MUST') || line.includes('SHALL') || line.includes('REQUIRED')) {
        ruleStatements.push(line.trim());
      }
    });

    return {
      file: fileName,
      mustRules: mustCount,
      mustNotRules: mustNotCount,
      totalRuleStatements: ruleStatements.length,
      errors,
      warnings,
      valid: errors.length === 0
    };
  } catch (error) {
    return {
      file: fileName,
      errors: [`Read error: ${error.message}`],
      warnings: [],
      valid: false
    };
  }
}

/**
 * Check for contradictions between rules
 */
function checkContradictions(rules) {
  const contradictions = [];

  // Extract all MUST and MUST NOT statements
  const mustStatements = [];
  const mustNotStatements = [];

  rules.forEach(rule => {
    try {
      const content = fs.readFileSync(path.join(RULES_DIR, rule.file), 'utf8');
      const lines = content.split('\n');

      lines.forEach(line => {
        if (line.includes('MUST NOT')) {
          mustNotStatements.push({ file: rule.file, statement: line.trim() });
        } else if (line.includes('MUST')) {
          mustStatements.push({ file: rule.file, statement: line.trim() });
        }
      });
    } catch (e) { }
  });

  // Contradiction check (same term in MUST and MUST NOT)
  // Filter out common words that don't indicate true contradictions
  const excludedTerms = [
    'must', 'shall', 'always', 'never', 'should', 'before', 'after',
    'required', 'commit', 'review', 'code', 'file', 'test', 'security',
    'rule', 'check', 'validation', 'enforced', 'violation'
  ];

  mustStatements.forEach(must => {
    mustNotStatements.forEach(mustNot => {
      // Extract key terms (5+ chars to filter common words)
      const mustTerms = must.statement.toLowerCase().match(/\b\w{5,}\b/g) || [];
      const mustNotTerms = mustNot.statement.toLowerCase().match(/\b\w{5,}\b/g) || [];

      const overlap = mustTerms.filter(t =>
        mustNotTerms.includes(t) && !excludedTerms.includes(t)
      );

      // Require at least 3 overlapping specific terms to flag as potential contradiction
      if (overlap.length >= 3 && must.file !== mustNot.file) {
        contradictions.push({
          file1: must.file,
          statement1: must.statement.substring(0, 80),
          file2: mustNot.file,
          statement2: mustNot.statement.substring(0, 80),
          overlappingTerms: overlap
        });
      }
    });
  });

  return contradictions;
}

/**
 * Validate all rules
 */
function validateAllRules() {
  const results = {
    total: 0,
    valid: 0,
    invalid: 0,
    rules: [],
    contradictions: []
  };

  if (!fs.existsSync(RULES_DIR)) {
    return { error: `Rules directory not found: ${RULES_DIR}` };
  }

  const files = fs.readdirSync(RULES_DIR).filter(f => f.endsWith('.md'));
  results.total = files.length;

  files.forEach(file => {
    const result = validateRule(path.join(RULES_DIR, file));
    results.rules.push(result);

    if (result.valid) {
      results.valid++;
    } else {
      results.invalid++;
    }
  });

  // Check for contradictions
  results.contradictions = checkContradictions(results.rules);

  return results;
}

/**
 * Main execution
 */
function main() {
  console.log('Validating rules...\n');

  const results = validateAllRules();

  if (results.error) {
    console.error(`Error: ${results.error}`);
    process.exit(1);
  }

  // Output results
  results.rules.forEach(rule => {
    const status = rule.valid ? '✓' : '✗';
    console.log(`${status} ${rule.file} (${rule.mustRules} MUST, ${rule.mustNotRules} MUST NOT)`);

    rule.errors.forEach(err => {
      console.log(`    ERROR: ${err}`);
    });
    rule.warnings.forEach(warn => {
      console.log(`    WARN: ${warn}`);
    });
  });

  // Output contradictions
  if (results.contradictions.length > 0) {
    console.log('\nPotential Contradictions:');
    results.contradictions.forEach(c => {
      console.log(`  ${c.file1} vs ${c.file2}`);
      console.log(`    Terms: ${c.overlappingTerms.join(', ')}`);
    });
  }

  console.log(`\nSummary: ${results.valid}/${results.total} valid`);
  if (results.contradictions.length > 0) {
    console.log(`Contradictions: ${results.contradictions.length} potential`);
  }

  // Exit with error if any invalid
  process.exit(results.invalid > 0 ? 1 : 0);
}

if (require.main === module) {
  main();
}

module.exports = { validateRule, validateAllRules, checkContradictions };
