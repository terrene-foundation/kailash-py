#!/usr/bin/env node
/**
 * Commands Validation Script for CI
 *
 * Validates all command files meet quality standards:
 * - Has Purpose section
 * - Has Quick Reference table
 * - Has Usage Examples
 * - References related commands/skills
 */

const fs = require('fs');
const path = require('path');

const COMMANDS_DIR = path.join(process.cwd(), '.claude', 'commands');

/**
 * Validate single command file
 */
function validateCommand(filePath) {
  const errors = [];
  const warnings = [];
  const fileName = path.basename(filePath);

  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n');

    // Check for title (h1)
    if (!content.match(/^#\s+\//)) {
      warnings.push('Title should start with / (command name)');
    }

    // Check for Purpose section
    if (!content.includes('## Purpose')) {
      warnings.push('Missing Purpose section');
    }

    // Check for Quick Reference
    if (!content.includes('## Quick Reference') && !content.includes('| Command |')) {
      warnings.push('Missing Quick Reference table');
    }

    // Check for Usage Examples
    if (!content.includes('## Usage') && !content.includes('## Example')) {
      warnings.push('Missing Usage Examples section');
    }

    // Check for code blocks
    const codeBlockCount = (content.match(/```/g) || []).length / 2;
    if (codeBlockCount < 1) {
      warnings.push('No code examples');
    }

    // Check for Related Commands section
    if (!content.includes('## Related')) {
      warnings.push('Missing Related Commands section');
    }

    // Check for Skill Reference
    if (!content.includes('Skill Reference') && !content.includes('skill')) {
      warnings.push('No skill reference');
    }

    // Extract command name from title
    const titleMatch = content.match(/^#\s+\/(\w+)/);
    const commandName = titleMatch ? titleMatch[1] : fileName.replace('.md', '');

    return {
      file: fileName,
      command: commandName,
      codeBlocks: codeBlockCount,
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
 * Validate all commands
 */
function validateAllCommands() {
  const results = {
    total: 0,
    valid: 0,
    invalid: 0,
    commands: []
  };

  if (!fs.existsSync(COMMANDS_DIR)) {
    return { error: `Commands directory not found: ${COMMANDS_DIR}` };
  }

  const files = fs.readdirSync(COMMANDS_DIR).filter(f => f.endsWith('.md'));
  results.total = files.length;

  files.forEach(file => {
    const result = validateCommand(path.join(COMMANDS_DIR, file));
    results.commands.push(result);

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
  console.log('Validating commands...\n');

  const results = validateAllCommands();

  if (results.error) {
    console.error(`Error: ${results.error}`);
    process.exit(1);
  }

  // Output results
  results.commands.forEach(cmd => {
    const status = cmd.valid ? '✓' : '✗';
    console.log(`${status} /${cmd.command} (${cmd.file})`);

    cmd.errors.forEach(err => {
      console.log(`    ERROR: ${err}`);
    });
    cmd.warnings.forEach(warn => {
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

module.exports = { validateCommand, validateAllCommands };
