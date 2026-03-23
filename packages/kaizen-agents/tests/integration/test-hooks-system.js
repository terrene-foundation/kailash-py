#!/usr/bin/env node
/**
 * Integration Tests for Hooks System
 *
 * Tests the hook scripts with simulated JSON input/output.
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const HOOKS_DIR = path.join(process.cwd(), 'scripts', 'hooks');

let testsPassed = 0;
let testsFailed = 0;

/**
 * Run a hook script with JSON input
 */
function runHook(hookPath, input) {
  return new Promise((resolve, reject) => {
    const child = spawn('node', [hookPath], {
      stdio: ['pipe', 'pipe', 'pipe']
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

    child.stdin.write(JSON.stringify(input));
    child.stdin.end();
  });
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
 * Test Suite: validate-bash-command.js
 */
async function testValidateBashCommand() {
  console.log('\nvalidate-bash-command.js Tests:');

  const hookPath = path.join(HOOKS_DIR, 'validate-bash-command.js');

  await test('allows safe ls command', async () => {
    const result = await runHook(hookPath, {
      tool_name: 'Bash',
      tool_input: { command: 'ls -la' }
    });

    // Exit 0 means continue
    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
  })();

  await test('allows git status command', async () => {
    const result = await runHook(hookPath, {
      tool_name: 'Bash',
      tool_input: { command: 'git status' }
    });

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
  })();

  await test('allows npm test command', async () => {
    const result = await runHook(hookPath, {
      tool_name: 'Bash',
      tool_input: { command: 'npm test' }
    });

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
  })();

  await test('returns JSON output', async () => {
    const result = await runHook(hookPath, {
      tool_name: 'Bash',
      tool_input: { command: 'echo hello' }
    });

    // Should be valid JSON
    const output = JSON.parse(result.stdout);
    assert(typeof output === 'object', 'Expected JSON object output');
  })();
}

/**
 * Test Suite: validate-workflow.js
 */
async function testValidateWorkflow() {
  console.log('\nvalidate-workflow.js Tests:');

  const hookPath = path.join(HOOKS_DIR, 'validate-workflow.js');

  await test('validates correct workflow pattern', async () => {
    const result = await runHook(hookPath, {
      tool_name: 'Write',
      tool_input: {
        file_path: '/test/workflow.py',
        content: 'runtime.execute(workflow.build())'
      }
    });

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
  })();

  await test('detects anti-pattern in code', async () => {
    const result = await runHook(hookPath, {
      tool_name: 'Write',
      tool_input: {
        file_path: '/test/workflow.py',
        content: 'workflow.execute(runtime)'
      }
    });

    // Should still exit 0 (warning only) but include warning in output
    const output = JSON.parse(result.stdout);
    // Check for warning message if present
    if (output.message) {
      assert(
        output.message.includes('warning') || output.message.includes('pattern'),
        'Expected warning about pattern'
      );
    }
  })();

  await test('ignores non-Python files', async () => {
    const result = await runHook(hookPath, {
      tool_name: 'Write',
      tool_input: {
        file_path: '/test/readme.md',
        content: 'Some markdown content'
      }
    });

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
  })();
}

/**
 * Test Suite: auto-format.js
 */
async function testAutoFormat() {
  console.log('\nauto-format.js Tests:');

  const hookPath = path.join(HOOKS_DIR, 'auto-format.js');

  await test('processes Python file', async () => {
    const result = await runHook(hookPath, {
      tool_name: 'Write',
      tool_input: {
        file_path: '/test/script.py',
        content: 'def foo():pass'
      }
    });

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
  })();

  await test('processes JavaScript file', async () => {
    const result = await runHook(hookPath, {
      tool_name: 'Write',
      tool_input: {
        file_path: '/test/script.js',
        content: 'function foo(){return 1}'
      }
    });

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
  })();

  await test('returns JSON output', async () => {
    const result = await runHook(hookPath, {
      tool_name: 'Write',
      tool_input: {
        file_path: '/test/script.py',
        content: 'x=1'
      }
    });

    const output = JSON.parse(result.stdout);
    assert(typeof output === 'object', 'Expected JSON object output');
  })();
}

/**
 * Test Suite: session-start.js
 */
async function testSessionStart() {
  console.log('\nsession-start.js Tests:');

  const hookPath = path.join(HOOKS_DIR, 'session-start.js');

  await test('executes without error', async () => {
    const result = await runHook(hookPath, {
      session_id: 'test-session-123',
      timestamp: new Date().toISOString()
    });

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
  })();

  await test('returns JSON output', async () => {
    const result = await runHook(hookPath, {
      session_id: 'test-session-456'
    });

    const output = JSON.parse(result.stdout);
    assert(typeof output === 'object', 'Expected JSON object output');
  })();
}

/**
 * Test Suite: session-end.js
 */
async function testSessionEnd() {
  console.log('\nsession-end.js Tests:');

  const hookPath = path.join(HOOKS_DIR, 'session-end.js');

  await test('executes without error', async () => {
    const result = await runHook(hookPath, {
      session_id: 'test-session-123',
      timestamp: new Date().toISOString()
    });

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
  })();

  await test('returns JSON output', async () => {
    const result = await runHook(hookPath, {
      session_id: 'test-session-789'
    });

    const output = JSON.parse(result.stdout);
    assert(typeof output === 'object', 'Expected JSON object output');
  })();
}

/**
 * Test Suite: pre-compact.js
 */
async function testPreCompact() {
  console.log('\npre-compact.js Tests:');

  const hookPath = path.join(HOOKS_DIR, 'pre-compact.js');

  await test('executes without error', async () => {
    const result = await runHook(hookPath, {
      session_id: 'test-session-123',
      context_usage: 0.85
    });

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
  })();

  await test('returns JSON output', async () => {
    const result = await runHook(hookPath, {
      session_id: 'compact-test'
    });

    const output = JSON.parse(result.stdout);
    assert(typeof output === 'object', 'Expected JSON object output');
  })();
}

/**
 * Test Suite: stop.js
 */
async function testStop() {
  console.log('\nstop.js Tests:');

  const hookPath = path.join(HOOKS_DIR, 'stop.js');

  await test('executes without error', async () => {
    const result = await runHook(hookPath, {
      session_id: 'test-session-123',
      reason: 'user_request'
    });

    assert(result.exitCode === 0, `Expected exit 0, got ${result.exitCode}`);
  })();

  await test('returns JSON output', async () => {
    const result = await runHook(hookPath, {
      session_id: 'stop-test'
    });

    const output = JSON.parse(result.stdout);
    assert(typeof output === 'object', 'Expected JSON object output');
  })();
}

/**
 * Main execution
 */
async function main() {
  console.log('╔════════════════════════════════════════════════╗');
  console.log('║  Hooks System Integration Tests                ║');
  console.log('╚════════════════════════════════════════════════╝');

  try {
    await testValidateBashCommand();
    await testValidateWorkflow();
    await testAutoFormat();
    await testSessionStart();
    await testSessionEnd();
    await testPreCompact();
    await testStop();

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
