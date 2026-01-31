#!/usr/bin/env node
/**
 * Skills Validation Script for CI
 *
 * Validates all skill directories meet quality standards:
 * - Has SKILL.md entry point
 * - Quick Patterns: 3-5 copy-paste ready
 * - Critical Gotchas: formatted with checkmarks
 * - References sdk-users for details
 * - Total lines: 50-250
 */

const fs = require('fs');
const path = require('path');

const SKILLS_DIR = path.join(process.cwd(), '.claude', 'skills');

const MIN_LINES = 50;
const MAX_LINES = 250;

/**
 * Validate single skill directory
 */
function validateSkill(skillPath) {
  const errors = [];
  const warnings = [];
  const skillName = path.basename(skillPath);

  try {
    const skillMdPath = path.join(skillPath, 'SKILL.md');

    // Check for SKILL.md
    if (!fs.existsSync(skillMdPath)) {
      errors.push('Missing SKILL.md entry point');
      return {
        skill: skillName,
        errors,
        warnings,
        valid: false
      };
    }

    const content = fs.readFileSync(skillMdPath, 'utf8');
    const lines = content.split('\n');
    const lineCount = lines.length;

    // Check line count
    if (lineCount < MIN_LINES) {
      warnings.push(`Line count ${lineCount} below recommended ${MIN_LINES}`);
    }
    if (lineCount > MAX_LINES) {
      warnings.push(`Line count ${lineCount} exceeds recommended ${MAX_LINES}`);
    }

    // Check for Quick Patterns section (accept various pattern-related headings)
    const hasPatternSection =
      content.includes('## Quick') ||
      content.includes('## Pattern') ||
      content.includes('Patterns') ||
      content.includes('## Integration') ||
      content.includes('## Key Decision') ||
      content.includes('## Tier') ||
      content.includes('## Strategy') ||
      content.includes('## Validation');

    if (!hasPatternSection) {
      warnings.push('Missing Quick Patterns section');
    }

    // Check for code blocks (copy-paste ready patterns)
    const codeBlockCount = (content.match(/```/g) || []).length / 2;
    if (codeBlockCount < 3) {
      warnings.push(`Only ${codeBlockCount} code blocks (recommend 3-5)`);
    }

    // Check for gotchas/warnings
    if (!content.includes('Gotcha') && !content.includes('Warning') &&
        !content.includes('CRITICAL') && !content.includes('NEVER')) {
      warnings.push('No gotchas or warnings documented');
    }

    // Check for documentation reference (multiple valid patterns)
    const hasDocReference =
      content.includes('sdk-users/') ||
      content.includes('Full Documentation') ||
      content.includes('See also') ||
      content.includes('Reference:') ||
      content.includes('Documentation:') ||
      content.includes('For more details') ||
      content.includes('Related Skills') ||
      content.includes('CLAUDE.md');

    if (!hasDocReference) {
      warnings.push('No documentation reference found (sdk-users/, Full Documentation, Related Skills, etc.)');
    }

    // Check for checkmarks/cross marks formatting (only warn if gotchas section exists)
    const hasGotchasSection = content.includes('Gotcha') || content.includes('Warning') ||
                              content.includes('CRITICAL') || content.includes('NEVER');
    if (hasGotchasSection && !content.includes('✓') && !content.includes('✗') &&
        !content.includes('✅') && !content.includes('❌')) {
      warnings.push('Gotchas section exists but no formatted checkmarks');
    }

    return {
      skill: skillName,
      lineCount,
      codeBlocks: codeBlockCount,
      errors,
      warnings,
      valid: errors.length === 0
    };
  } catch (error) {
    return {
      skill: skillName,
      errors: [`Read error: ${error.message}`],
      warnings: [],
      valid: false
    };
  }
}

/**
 * Validate all skills
 */
function validateAllSkills() {
  const results = {
    total: 0,
    valid: 0,
    invalid: 0,
    skills: []
  };

  if (!fs.existsSync(SKILLS_DIR)) {
    return { error: `Skills directory not found: ${SKILLS_DIR}` };
  }

  const dirs = fs.readdirSync(SKILLS_DIR).filter(f => {
    const fullPath = path.join(SKILLS_DIR, f);
    return fs.statSync(fullPath).isDirectory();
  });

  results.total = dirs.length;

  dirs.forEach(dir => {
    const result = validateSkill(path.join(SKILLS_DIR, dir));
    results.skills.push(result);

    if (result.valid) {
      results.valid++;
    } else {
      results.invalid++;
    }
  });

  return results;
}

/**
 * Main execution
 */
function main() {
  console.log('Validating skills...\n');

  const results = validateAllSkills();

  if (results.error) {
    console.error(`Error: ${results.error}`);
    process.exit(1);
  }

  // Output results
  results.skills.forEach(skill => {
    const status = skill.valid ? '✓' : '✗';
    const lineInfo = skill.lineCount ? ` (${skill.lineCount} lines, ${skill.codeBlocks} blocks)` : '';
    console.log(`${status} ${skill.skill}${lineInfo}`);

    skill.errors.forEach(err => {
      console.log(`    ERROR: ${err}`);
    });

    skill.warnings.forEach(warn => {
      console.log(`    WARN: ${warn}`);
    });
  });

  console.log(`\nSummary: ${results.valid}/${results.total} valid`);

  // Exit with error if any invalid
  process.exit(results.invalid > 0 ? 1 : 0);
}

if (require.main === module) {
  main();
}

module.exports = { validateSkill, validateAllSkills };
