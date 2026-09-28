const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');
const root = path.resolve(__dirname, '../../..');
const wrapper = path.join(root, '.claude/hooks/lib/codex-hook-runtime.js');
const outputModule = path.join(root, '.claude/hooks/lib/instruct-and-wait.js');
const manifest = JSON.parse(fs.readFileSync(path.join(root, '.codex/hooks.json')));

function output(runtime, hookEvent, severity) {
  const payload = { hookEvent, severity, what_happened: 'known finding', why: 'test policy', agent_must_report: ['report'], agent_must_wait: 'wait' };
  const result = spawnSync(process.execPath, ['-e', `const {instructAndWait}=require(process.argv[1]); process.stdout.write(JSON.stringify(instructAndWait(JSON.parse(process.argv[2]))));`, outputModule, JSON.stringify(payload)], { encoding: 'utf8', env: { ...process.env, COC_RUNTIME: runtime } });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test('Codex PreToolUse deny and context contain only supported output fields', () => {
  for (const severity of ['block', 'advisory', 'pre-action', 'halt-and-report']) {
    const result = output('codex', 'PreToolUse', severity);
    assert.equal(Object.hasOwn(result.json, 'continue'), false);
    assert.equal(result.exitCode, severity === 'block' ? 2 : 0);
    if (severity === 'block') assert.equal(result.json.hookSpecificOutput.permissionDecision, 'deny');
    else assert.match(result.json.hookSpecificOutput.additionalContext, /known finding/);
  }
});

test('Codex PermissionRequest uses its decision schema without unsupported context', () => {
  const denied = output('codex', 'PermissionRequest', 'block');
  assert.equal(denied.json.hookSpecificOutput.decision.behavior, 'deny');
  assert.match(denied.json.hookSpecificOutput.decision.message, /known finding/);
  const advisory = output('codex', 'PermissionRequest', 'advisory');
  assert.equal(Object.hasOwn(advisory.json, 'continue'), false);
  assert.equal(Object.hasOwn(advisory.json, 'hookSpecificOutput'), false);
  assert.match(advisory.json.systemMessage, /known finding/);
});

test('Codex PostToolUse blocking feedback does not claim to prevent the tool', () => {
  const result = output('codex', 'PostToolUse', 'block');
  assert.equal(result.json.decision, 'block');
  assert.match(result.json.reason, /ALREADY RAN/);
  assert.doesNotMatch(result.json.reason, /Tool call blocked/);
});

test('CC and Gemini legacy output remains unchanged', () => {
  for (const runtime of ['cc', 'gemini']) {
    const deny = output(runtime, 'PreToolUse', 'block');
    assert.equal(deny.json.continue, false);
    assert.equal(deny.json.hookSpecificOutput.permissionDecision, 'deny');
    assert.equal(deny.exitCode, 2);
    assert.equal(output(runtime, 'PreToolUse', 'advisory').json.continue, true);
  }
});

test('Codex lifecycle and post-tool context remains deliverable', () => {
  for (const event of ['Stop', 'PreCompact', 'SessionStart', 'UserPromptSubmit', 'PostToolUse']) {
    const result = output('codex', event, 'advisory');
    assert.equal(result.exitCode, 0);
    assert.match(result.json.systemMessage || result.json.hookSpecificOutput.additionalContext, /known finding/);
  }
});

test('registered shell events match Bash and reject an unrelated tool name', () => {
  for (const event of ['PreToolUse', 'PostToolUse']) {
    const matcher = new RegExp(manifest.hooks[event][0].matcher);
    assert.equal(matcher.test('Bash'), true);
    assert.equal(matcher.test('mcp__example__tool'), false);
  }
});

test('registered commands work from nested directories with spaces and preserve payloads', (t) => {
  const repo = fs.mkdtempSync(path.join(os.tmpdir(), 'codex hooks space '));
  t.after(() => fs.rmSync(repo, { recursive: true, force: true }));
  assert.equal(spawnSync('git', ['init', '-q', repo]).status, 0);
  const hooks = path.join(repo, '.claude/hooks');
  fs.mkdirSync(path.join(hooks, 'lib'), { recursive: true });
  fs.copyFileSync(wrapper, path.join(hooks, 'lib/codex-hook-runtime.js'));
  const nested = path.join(repo, 'nested folder');
  fs.mkdirSync(nested);
  for (const name of ['session-start', 'validate-bash-command', 'integration-hygiene']) {
    fs.writeFileSync(path.join(hooks, `${name}.js`), `const fs=require('node:fs'); console.log(JSON.stringify({runtime:process.env.COC_RUNTIME,root:process.env.CLAUDE_PROJECT_DIR,cwd:process.cwd(),input:fs.readFileSync(0,'utf8')}));`);
  }
  const input = JSON.stringify({ cwd: nested, hook_event_name: 'PreToolUse', tool_name: 'Bash' });
  for (const event of ['SessionStart', 'PreToolUse', 'PostToolUse']) {
    const command = manifest.hooks[event][0].hooks[0].command;
    const result = spawnSync('/bin/sh', ['-c', command], { cwd: nested, input, encoding: 'utf8', env: { ...process.env, CLAUDE_PROJECT_DIR: '/wrong/inherited/root' } });
    assert.equal(result.status, 0, result.stderr);
    const actual = JSON.parse(result.stdout);
    assert.equal(actual.runtime, 'codex');
    assert.equal(actual.root, fs.realpathSync(repo));
    assert.equal(actual.cwd, fs.realpathSync(repo));
    assert.equal(actual.input, input);
  }
});

test('wrapper preserves hook exit statuses and fails closed on unusable targets', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-hook-status-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const target = path.join(dir, 'hook.js');
  for (const code of [0, 1, 2]) {
    fs.writeFileSync(target, `process.stdout.write('out');process.stderr.write('err');process.exit(${code});`);
    const result = spawnSync(process.execPath, [wrapper, target], { encoding: 'utf8' });
    assert.equal(result.status, code);
    assert.equal(result.stdout, 'out');
    assert.equal(result.stderr, 'err');
  }
  for (const bad of [path.join(dir, 'missing.js'), dir]) {
    const result = spawnSync(process.execPath, [wrapper, bad], { encoding: 'utf8' });
    assert.equal(result.status, 2);
    assert.match(result.stderr, /codex-hook-runtime/);
  }
  fs.writeFileSync(target, "process.kill(process.pid, 'SIGTERM');");
  assert.equal(spawnSync(process.execPath, [wrapper, target]).status, 2);
});

test('actual Bash validator emits Codex-compatible output on the legacy allow path', () => {
  const result = spawnSync(process.execPath, [wrapper, '.claude/hooks/validate-bash-command.js'], {
    encoding: 'utf8', input: JSON.stringify({ hook_event_name: 'PreToolUse', tool_name: 'Bash', tool_input: { command: 'echo compatibility-probe' }, cwd: root }),
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(Object.hasOwn(JSON.parse(result.stdout), 'continue'), false);
});

test('actual Bash validator denies destructive input without executing it', () => {
  const result = spawnSync(process.execPath, [wrapper, '.claude/hooks/validate-bash-command.js'], {
    encoding: 'utf8', input: JSON.stringify({ hook_event_name: 'PreToolUse', tool_name: 'Bash', tool_input: { command: 'rm -rf /' }, cwd: root }),
  });
  assert.equal(result.status, 2, result.stderr);
  const denied = JSON.parse(result.stdout);
  assert.equal(Object.hasOwn(denied, 'continue'), false);
  assert.equal(denied.hookSpecificOutput.permissionDecision, 'deny');
  assert.match(result.stderr, /STOP/);
});
