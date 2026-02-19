#!/usr/bin/env node
/**
 * Integration Tests for Continuous Learning System
 *
 * Tests the full learning pipeline:
 * - Observation capture
 * - Pattern detection
 * - Instinct generation
 * - Evolution process
 * - Checkpoint management
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const SCRIPTS_DIR = path.join(process.cwd(), 'scripts', 'learning');
const TEST_LEARNING_DIR = path.join(os.tmpdir(), 'kailash-learning-test');

let testsPassed = 0;
let testsFailed = 0;

/**
 * Run a script with input and capture output
 */
function runScript(scriptPath, args = [], stdin = null) {
  return new Promise((resolve, reject) => {
    const child = spawn('node', [scriptPath, ...args], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        // Override learning dir for tests
        KAILASH_LEARNING_DIR: TEST_LEARNING_DIR
      }
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

    child.on('error', reject);

    if (stdin) {
      child.stdin.write(stdin);
    }
    child.stdin.end();
  });
}

/**
 * Clean up test directory
 */
function cleanup() {
  if (fs.existsSync(TEST_LEARNING_DIR)) {
    fs.rmSync(TEST_LEARNING_DIR, { recursive: true });
  }
}

/**
 * Test helper
 */
function test(name, fn) {
  return async () => {
    try {
      await fn();
      console.log(`  ✓ ${name}`);
      testsPassed++;
    } catch (error) {
      console.log(`  ✗ ${name}`);
      console.log(`    Error: ${error.message}`);
      testsFailed++;
    }
  };
}

/**
 * Assert helper
 */
function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

/**
 * Test Suite: Observation Logger
 */
async function testObservationLogger() {
  console.log('\nObservation Logger Tests:');

  await test('logs observation from stdin', async () => {
    const input = JSON.stringify({
      type: 'test_observation',
      data: { test: 'value' },
      context: { session_id: 'test123' }
    });

    const result = await runScript(
      path.join(SCRIPTS_DIR, 'observation-logger.js'),
      [],
      input
    );

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);

    const output = JSON.parse(result.stdout);
    assert(output.success === true, 'Expected success=true');
    assert(output.observation_id.startsWith('obs_'), 'Expected observation ID');
  })();

  await test('provides stats', async () => {
    const input = JSON.stringify({
      type: 'workflow_pattern',
      data: { nodes: ['A', 'B'] }
    });

    const result = await runScript(
      path.join(SCRIPTS_DIR, 'observation-logger.js'),
      [],
      input
    );

    const output = JSON.parse(result.stdout);
    assert(output.stats !== undefined, 'Expected stats in output');
    assert(typeof output.stats.total_observations === 'number', 'Expected observation count');
  })();
}

/**
 * Test Suite: Instinct Processor
 */
async function testInstinctProcessor() {
  console.log('\nInstinct Processor Tests:');

  await test('analyze returns pattern structure', async () => {
    const result = await runScript(
      path.join(SCRIPTS_DIR, 'instinct-processor.js'),
      ['--analyze']
    );

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
    assert(result.stdout.includes('workflow_patterns'), 'Expected workflow_patterns key');
  })();

  await test('list returns empty object when no instincts', async () => {
    const result = await runScript(
      path.join(SCRIPTS_DIR, 'instinct-processor.js'),
      ['--list']
    );

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
    // Should be valid JSON
    JSON.parse(result.stdout);
  })();

  await test('generate completes without error', async () => {
    const result = await runScript(
      path.join(SCRIPTS_DIR, 'instinct-processor.js'),
      ['--generate']
    );

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
    assert(result.stdout.includes('complete'), 'Expected completion message');
  })();
}

/**
 * Test Suite: Instinct Evolver
 */
async function testInstinctEvolver() {
  console.log('\nInstinct Evolver Tests:');

  await test('candidates returns structured output', async () => {
    const result = await runScript(
      path.join(SCRIPTS_DIR, 'instinct-evolver.js'),
      ['--candidates']
    );

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);

    const output = JSON.parse(result.stdout);
    assert(output.skill !== undefined, 'Expected skill candidates');
    assert(output.command !== undefined, 'Expected command candidates');
    assert(output.agent !== undefined, 'Expected agent candidates');
  })();

  await test('auto-evolve completes without error', async () => {
    const result = await runScript(
      path.join(SCRIPTS_DIR, 'instinct-evolver.js'),
      ['--auto']
    );

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);

    const output = JSON.parse(result.stdout);
    assert(Array.isArray(output.evolved), 'Expected evolved array');
    assert(Array.isArray(output.skipped), 'Expected skipped array');
  })();

  await test('evolve-skill with invalid ID returns error', async () => {
    const result = await runScript(
      path.join(SCRIPTS_DIR, 'instinct-evolver.js'),
      ['--evolve-skill', 'nonexistent_id']
    );

    const output = JSON.parse(result.stdout);
    assert(output.success === false, 'Expected success=false for invalid ID');
    assert(output.error !== undefined, 'Expected error message');
  })();
}

/**
 * Test Suite: Checkpoint Manager
 */
async function testCheckpointManager() {
  console.log('\nCheckpoint Manager Tests:');

  await test('save creates checkpoint', async () => {
    const result = await runScript(
      path.join(SCRIPTS_DIR, 'checkpoint-manager.js'),
      ['--save', '--name', 'test-checkpoint']
    );

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);

    const output = JSON.parse(result.stdout);
    assert(output.success === true, 'Expected success=true');
    assert(output.checkpoint_id.startsWith('checkpoint_'), 'Expected checkpoint ID');
  })();

  await test('list returns checkpoints', async () => {
    const result = await runScript(
      path.join(SCRIPTS_DIR, 'checkpoint-manager.js'),
      ['--list']
    );

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);

    const output = JSON.parse(result.stdout);
    assert(Array.isArray(output), 'Expected array of checkpoints');
  })();

  await test('diff with invalid ID returns error', async () => {
    const result = await runScript(
      path.join(SCRIPTS_DIR, 'checkpoint-manager.js'),
      ['--diff', 'nonexistent_id']
    );

    const output = JSON.parse(result.stdout);
    assert(output.success === false, 'Expected success=false for invalid ID');
  })();
}

/**
 * Test Suite: Full Pipeline
 */
async function testFullPipeline() {
  console.log('\nFull Pipeline Tests:');

  await test('observation → analyze → generate pipeline', async () => {
    // Step 1: Log multiple observations to create patterns
    for (let i = 0; i < 5; i++) {
      const input = JSON.stringify({
        type: 'workflow_pattern',
        data: { nodes: ['PythonCodeNode', 'PythonCodeNode'], pattern: 'transform' },
        context: { session_id: 'pipeline-test' }
      });

      await runScript(
        path.join(SCRIPTS_DIR, 'observation-logger.js'),
        [],
        input
      );
    }

    // Step 2: Analyze patterns
    const analyzeResult = await runScript(
      path.join(SCRIPTS_DIR, 'instinct-processor.js'),
      ['--analyze']
    );

    assert(analyzeResult.exitCode === 0, 'Analyze should succeed');

    // Step 3: Generate instincts
    const generateResult = await runScript(
      path.join(SCRIPTS_DIR, 'instinct-processor.js'),
      ['--generate']
    );

    assert(generateResult.exitCode === 0, 'Generate should succeed');
  })();

  await test('checkpoint before and after operations', async () => {
    // Create checkpoint
    const beforeResult = await runScript(
      path.join(SCRIPTS_DIR, 'checkpoint-manager.js'),
      ['--save', '--name', 'before-test']
    );

    const beforeOutput = JSON.parse(beforeResult.stdout);
    assert(beforeOutput.success === true, 'Before checkpoint should succeed');

    // Log some observations
    const input = JSON.stringify({
      type: 'test_observation',
      data: { test: 'pipeline' }
    });

    await runScript(
      path.join(SCRIPTS_DIR, 'observation-logger.js'),
      [],
      input
    );

    // Create another checkpoint
    const afterResult = await runScript(
      path.join(SCRIPTS_DIR, 'checkpoint-manager.js'),
      ['--save', '--name', 'after-test']
    );

    const afterOutput = JSON.parse(afterResult.stdout);
    assert(afterOutput.success === true, 'After checkpoint should succeed');

    // Compare checkpoints
    const diffResult = await runScript(
      path.join(SCRIPTS_DIR, 'checkpoint-manager.js'),
      ['--diff', beforeOutput.checkpoint_id]
    );

    const diffOutput = JSON.parse(diffResult.stdout);
    assert(diffOutput.success === true, 'Diff should succeed');
  })();
}

/**
 * Main execution
 */
async function main() {
  console.log('╔════════════════════════════════════════════════╗');
  console.log('║  Learning System Integration Tests             ║');
  console.log('╚════════════════════════════════════════════════╝');

  try {
    await testObservationLogger();
    await testInstinctProcessor();
    await testInstinctEvolver();
    await testCheckpointManager();
    await testFullPipeline();

    console.log('\n' + '═'.repeat(50));
    console.log(`Results: ${testsPassed} passed, ${testsFailed} failed`);
    console.log('═'.repeat(50));

    if (testsFailed > 0) {
      console.log('\n✗ SOME TESTS FAILED\n');
      process.exit(1);
    } else {
      console.log('\n✓ ALL TESTS PASSED\n');
      process.exit(0);
    }
  } catch (error) {
    console.error('\nTest runner error:', error.message);
    process.exit(1);
  }
}

main();
