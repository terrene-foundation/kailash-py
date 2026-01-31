#!/usr/bin/env node
/**
 * Agent Validation Script for CI
 *
 * Validates all agent files meet quality standards:
 * - Frontmatter has required fields
 * - Description under 120 chars with "Use when" trigger
 * - Total lines: 100-300
 * - Has Related Agents section
 * - Has Full Documentation section
 */

const fs = require('fs');
const path = require('path');

const AGENTS_DIR = path.join(process.cwd(), '.claude', 'agents');

const REQUIRED_FRONTMATTER = ['name', 'description'];
const RECOMMENDED_FRONTMATTER = ['tools', 'model'];
const MIN_LINES = 100;
const MAX_LINES = 300;
const MAX_DESCRIPTION_LENGTH = 120;

/**
 * Parse frontmatter from markdown
 */
function parseFrontmatter(content) {
  const match = content.match(/^---\n([\s\S]*?)\n---/);
  if (!match) return null;

  const frontmatter = {};
  const lines = match[1].split('\n');

  lines.forEach(line => {
    const colonIndex = line.indexOf(':');
    if (colonIndex > 0) {
      const key = line.substring(0, colonIndex).trim();
      const value = line.substring(colonIndex + 1).trim();
      frontmatter[key] = value;
    }
  });

  return frontmatter;
}

/**
 * Validate single agent file
 */
function validateAgent(filePath) {
  const errors = [];
  const warnings = [];
  const fileName = path.basename(filePath);

  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n');
    const lineCount = lines.length;

    // Check line count
    if (lineCount < MIN_LINES) {
      errors.push(`Line count ${lineCount} below minimum ${MIN_LINES}`);
    }
    if (lineCount > MAX_LINES) {
      warnings.push(`Line count ${lineCount} exceeds recommended ${MAX_LINES}`);
    }

    // Parse and validate frontmatter
    const frontmatter = parseFrontmatter(content);
    if (!frontmatter) {
      errors.push('Missing frontmatter (---...---)');
    } else {
      // Check required fields
      REQUIRED_FRONTMATTER.forEach(field => {
        if (!frontmatter[field]) {
          errors.push(`Missing required frontmatter: ${field}`);
        }
      });

      // Check recommended fields
      RECOMMENDED_FRONTMATTER.forEach(field => {
        if (!frontmatter[field]) {
          warnings.push(`Missing recommended frontmatter: ${field}`);
        }
      });

      // Check description length
      if (frontmatter.description && frontmatter.description.length > MAX_DESCRIPTION_LENGTH) {
        warnings.push(`Description exceeds ${MAX_DESCRIPTION_LENGTH} chars (${frontmatter.description.length})`);
      }

      // Check for "Use when" trigger
      if (frontmatter.description && !frontmatter.description.toLowerCase().includes('use')) {
        warnings.push('Description should contain usage trigger (e.g., "Use when...")');
      }
    }

    // Check for Related Agents section
    if (!content.includes('## Related') && !content.includes('## Hand')) {
      warnings.push('Missing Related Agents or Handoff section');
    }

    // Check for Full Documentation section
    if (!content.includes('## Full Documentation') && !content.includes('## SDK Reference')) {
      warnings.push('Missing Full Documentation section');
    }

    // Check for SDK reference
    if (!content.includes('sdk-users/')) {
      warnings.push('No SDK documentation reference found');
    }

    return {
      file: fileName,
      lineCount,
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
 * Validate all agents
 */
function validateAllAgents() {
  const results = {
    total: 0,
    valid: 0,
    invalid: 0,
    agents: []
  };

  if (!fs.existsSync(AGENTS_DIR)) {
    return { error: `Agents directory not found: ${AGENTS_DIR}` };
  }

  // Exclude files starting with underscore (documentation)
  const files = fs.readdirSync(AGENTS_DIR).filter(f => f.endsWith('.md') && !f.startsWith('_'));
  results.total = files.length;

  files.forEach(file => {
    const result = validateAgent(path.join(AGENTS_DIR, file));
    results.agents.push(result);

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
  console.log('Validating agents...\n');

  const results = validateAllAgents();

  if (results.error) {
    console.error(`Error: ${results.error}`);
    process.exit(1);
  }

  // Output results
  results.agents.forEach(agent => {
    const status = agent.valid ? '✓' : '✗';
    console.log(`${status} ${agent.file} (${agent.lineCount} lines)`);

    agent.errors.forEach(err => {
      console.log(`    ERROR: ${err}`);
    });

    agent.warnings.forEach(warn => {
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

module.exports = { validateAgent, validateAllAgents };
