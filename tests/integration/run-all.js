#!/usr/bin/env node
/**
 * Integration Test Runner
 *
 * Runs all integration tests and reports aggregate results.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const TESTS_DIR = path.join(process.cwd(), 'tests', 'integration');

const TEST_FILES = [
  { name: 'Learning System', file: 'test-learning-system.js' },
  { name: 'Hooks System', file: 'test-hooks-system.js' }
];

/**
 * Run a test file
 */
function runTest(testPath) {
  return new Promise((resolve) => {
    const child = spawn('node', [testPath], {
      stdio: ['inherit', 'pipe', 'pipe'],
      cwd: process.cwd()
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (data) => {
      stdout += data.toString();
      process.stdout.write(data);
    });

    child.stderr.on('data', (data) => {
      stderr += data.toString();
      process.stderr.write(data);
    });

    child.on('close', (code) => {
      // Extract pass/fail counts from output
      const match = stdout.match(/(\d+) passed, (\d+) failed/);
      resolve({
        exitCode: code,
        passed: match ? parseInt(match[1]) : 0,
        failed: match ? parseInt(match[2]) : (code !== 0 ? 1 : 0)
      });
    });
  });
}

/**
 * Main execution
 */
async function main() {
  console.log('╔════════════════════════════════════════════════╗');
  console.log('║  Integration Test Suite                        ║');
  console.log('╚════════════════════════════════════════════════╝\n');

  const results = {
    tests: [],
    totalPassed: 0,
    totalFailed: 0
  };

  for (const test of TEST_FILES) {
    const testPath = path.join(TESTS_DIR, test.file);

    if (!fs.existsSync(testPath)) {
      console.log(`\n⚠ Skipping ${test.name}: file not found`);
      continue;
    }

    console.log(`\n${'━'.repeat(60)}`);
    console.log(`Running: ${test.name}`);
    console.log('━'.repeat(60));

    const result = await runTest(testPath);

    results.tests.push({
      name: test.name,
      passed: result.passed,
      failed: result.failed,
      success: result.exitCode === 0
    });

    results.totalPassed += result.passed;
    results.totalFailed += result.failed;
  }

  // Summary
  console.log('\n' + '═'.repeat(60));
  console.log('INTEGRATION TEST SUMMARY');
  console.log('═'.repeat(60));

  results.tests.forEach(test => {
    const status = test.success ? '✓' : '✗';
    console.log(`${status} ${test.name}: ${test.passed} passed, ${test.failed} failed`);
  });

  console.log('─'.repeat(60));
  console.log(`Total: ${results.totalPassed} passed, ${results.totalFailed} failed`);
  console.log('═'.repeat(60));

  if (results.totalFailed > 0) {
    console.log('\n✗ INTEGRATION TESTS FAILED\n');
    process.exit(1);
  } else {
    console.log('\n✓ ALL INTEGRATION TESTS PASSED\n');
    process.exit(0);
  }
}

main().catch(error => {
  console.error('Test runner error:', error.message);
  process.exit(1);
});
