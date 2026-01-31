#!/usr/bin/env node
/**
 * CI Validation Runner for Kailash Vibe CC Setup
 *
 * Runs all validation scripts and reports aggregate results.
 *
 * Usage:
 *   node scripts/ci/run-all.js           Run all validations
 *   node scripts/ci/run-all.js --json    Output JSON results
 *   node scripts/ci/run-all.js --strict  Fail on warnings
 */

const { spawn } = require('child_process');
const path = require('path');

const SCRIPTS = [
  { name: 'agents', script: 'validate-agents.js', description: 'Agent files' },
  { name: 'skills', script: 'validate-skills.js', description: 'Skill directories' },
  { name: 'hooks', script: 'validate-hooks.js', description: 'Hook scripts' },
  { name: 'rules', script: 'validate-rules.js', description: 'Rule files' },
  { name: 'commands', script: 'validate-commands.js', description: 'Command files' }
];

/**
 * Run a validation script
 */
function runValidation(scriptPath) {
  return new Promise((resolve) => {
    const child = spawn('node', [scriptPath], {
      stdio: ['inherit', 'pipe', 'pipe'],
      cwd: process.cwd()
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    child.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    child.on('close', (code) => {
      resolve({
        exitCode: code,
        stdout: stdout.trim(),
        stderr: stderr.trim()
      });
    });
  });
}

/**
 * Parse validation output for summary
 */
function parseSummary(output) {
  const summaryMatch = output.match(/Summary:\s*(\d+)\/(\d+)/);
  if (summaryMatch) {
    return {
      valid: parseInt(summaryMatch[1]),
      total: parseInt(summaryMatch[2])
    };
  }
  return null;
}

/**
 * Count warnings in output
 */
function countWarnings(output) {
  return (output.match(/WARN:/g) || []).length;
}

/**
 * Count errors in output
 */
function countErrors(output) {
  return (output.match(/ERROR:/g) || []).length;
}

/**
 * Main execution
 */
async function main() {
  const args = process.argv.slice(2);
  const jsonOutput = args.includes('--json');
  const strictMode = args.includes('--strict');

  if (!jsonOutput) {
    console.log('╔══════════════════════════════════════════════╗');
    console.log('║     Kailash Vibe CC Setup - CI Validation    ║');
    console.log('╚══════════════════════════════════════════════╝\n');
  }

  const results = {
    timestamp: new Date().toISOString(),
    validations: [],
    summary: {
      passed: 0,
      failed: 0,
      warnings: 0,
      errors: 0
    }
  };

  const scriptsDir = path.join(process.cwd(), 'scripts', 'ci');

  for (const script of SCRIPTS) {
    const scriptPath = path.join(scriptsDir, script.script);

    if (!jsonOutput) {
      console.log(`\n${'═'.repeat(50)}`);
      console.log(`${script.description.toUpperCase()}`);
      console.log('═'.repeat(50));
    }

    const result = await runValidation(scriptPath);

    const validation = {
      name: script.name,
      description: script.description,
      exitCode: result.exitCode,
      passed: result.exitCode === 0,
      summary: parseSummary(result.stdout),
      warnings: countWarnings(result.stdout),
      errors: countErrors(result.stdout)
    };

    if (!jsonOutput) {
      console.log(result.stdout);
    }

    results.validations.push(validation);

    if (validation.passed) {
      results.summary.passed++;
    } else {
      results.summary.failed++;
    }

    results.summary.warnings += validation.warnings;
    results.summary.errors += validation.errors;
  }

  // Calculate overall status
  let overallPassed = results.summary.failed === 0;
  if (strictMode && results.summary.warnings > 0) {
    overallPassed = false;
  }

  results.overallPassed = overallPassed;

  if (jsonOutput) {
    console.log(JSON.stringify(results, null, 2));
  } else {
    console.log('\n' + '═'.repeat(50));
    console.log('OVERALL SUMMARY');
    console.log('═'.repeat(50));

    results.validations.forEach(v => {
      const status = v.passed ? '✓' : '✗';
      const summaryStr = v.summary ? `${v.summary.valid}/${v.summary.total}` : 'N/A';
      console.log(`${status} ${v.description}: ${summaryStr}`);
    });

    console.log('\n' + '─'.repeat(50));
    console.log(`Validations: ${results.summary.passed}/${SCRIPTS.length} passed`);
    console.log(`Errors: ${results.summary.errors}`);
    console.log(`Warnings: ${results.summary.warnings}`);
    console.log('─'.repeat(50));

    if (overallPassed) {
      console.log('\n✓ ALL VALIDATIONS PASSED\n');
    } else {
      console.log('\n✗ VALIDATION FAILED\n');
    }
  }

  process.exit(overallPassed ? 0 : 1);
}

main().catch(error => {
  console.error('CI Runner Error:', error.message);
  process.exit(1);
});
