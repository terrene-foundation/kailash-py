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

function parseOutput(result) {
  let parsed;
  assert.doesNotThrow(() => { parsed = JSON.parse(result.stdout); },
    `Invalid hook JSON (status ${result.status}); stderr: ${result.stderr}; stdout: ${result.stdout}`);
  return parsed;
}

test('invalid hook JSON diagnostics preserve stderr and exit status', () => {
  assert.throws(() => parseOutput({status:2,stdout:'',stderr:'deadline diagnostic'}),
    /status 2.*stderr: deadline diagnostic/);
});

function output(runtime, hookEvent, severity) {
  const payload = { hookEvent, severity, what_happened: 'known finding', why: 'test policy', agent_must_report: ['report'], agent_must_wait: 'wait' };
  const result = spawnSync(process.execPath, ['-e', `const {instructAndWait}=require(process.argv[1]); process.stdout.write(JSON.stringify(instructAndWait(JSON.parse(process.argv[2]))));`, outputModule, JSON.stringify(payload)], { encoding: 'utf8', env: { ...process.env, COC_RUNTIME: runtime } });
  assert.equal(result.status, 0, result.stderr);
  return parseOutput(result);
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
  for (const event of ['PreToolUse']) {
    const matcher = new RegExp(manifest.hooks[event][0].matcher);
    assert.equal(matcher.test('Bash'), true);
    assert.equal(matcher.test('mcp__example__tool'), false);
  }
  const postMatcher = new RegExp(manifest.hooks.PostToolUse[0].matcher);
  assert.equal(postMatcher.test('apply_patch'), true);
  assert.equal(postMatcher.test('Bash'), false);
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
    const actual = parseOutput(result);
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
  assert.equal(Object.hasOwn(parseOutput(result), 'continue'), false);
});

test('actual Bash validator denies destructive input without executing it', () => {
  const result = spawnSync(process.execPath, [wrapper, '.claude/hooks/validate-bash-command.js'], {
    encoding: 'utf8', input: JSON.stringify({ hook_event_name: 'PreToolUse', tool_name: 'Bash', tool_input: { command: 'rm -rf /' }, cwd: root }),
  });
  assert.equal(result.status, 2, result.stderr);
  const denied = parseOutput(result);
  assert.equal(Object.hasOwn(denied, 'continue'), false);
  assert.equal(denied.hookSpecificOutput.permissionDecision, 'deny');
  assert.match(result.stderr, /STOP/);
});

test('Codex validator fails closed on malformed or missing command input', () => {
  for (const input of ['{', 'null', '{}', JSON.stringify({tool_input:{command:{}}}), JSON.stringify({tool_input:{command:[]}})]) {
    const result = spawnSync(process.execPath, [wrapper, '.claude/hooks/validate-bash-command.js'], { encoding:'utf8', input });
    assert.equal(result.status, 2, `input ${input}: ${result.stderr}`);
    const denied = parseOutput(result);
    assert.equal(denied.hookSpecificOutput.permissionDecision, 'deny');
    assert.match(denied.hookSpecificOutput.permissionDecisionReason, /validation could not complete/);
  }
});

test('CC and Gemini malformed-input handling keeps the legacy non-blocking error', () => {
  for (const runtime of ['cc','gemini']) {
    const result = spawnSync(process.execPath, [path.join(root,'.claude/hooks/validate-bash-command.js')], {encoding:'utf8',input:'{',env:{...process.env,COC_RUNTIME:runtime}});
    assert.equal(result.status,1);
    assert.equal(parseOutput(result).continue,true);
  }
});

function runHygiene(repo, toolInput, cwd = repo) {
  return spawnSync(process.execPath, [path.join(root,'.claude/hooks/integration-hygiene.js')], {
    encoding:'utf8', env:{...process.env,COC_RUNTIME:'codex',CLAUDE_PROJECT_DIR:repo},
    input:JSON.stringify({hook_event_name:'PostToolUse',tool_name:'apply_patch',tool_input:toolInput,cwd}),
  });
}

test('Codex hygiene scans actual patch targets including nested paths and moves', (t) => {
  const repo=fs.mkdtempSync(path.join(os.tmpdir(),'codex-hygiene-'));
  t.after(()=>fs.rmSync(repo,{recursive:true,force:true}));
  const cwd=path.join(repo,'src'); fs.mkdirSync(cwd);
  fs.writeFileSync(path.join(cwd,'bad.py'),'try:\n    operation()\nexcept: pass\n');
  fs.writeFileSync(path.join(cwd,'moved.js'),'const FAKE_USERS = [];\n');
  fs.writeFileSync(path.join(cwd,'clean.py'),'answer = 42\n');
  const patch='*** Begin Patch\n*** Update File: bad.py\n@@\n+except: pass\n*** Update File: old.js\n*** Move to: moved.js\n@@\n+const FAKE_USERS = [];\n*** End Patch';
  const flagged=runHygiene(repo,{command:patch},cwd);
  assert.equal(flagged.status,0,flagged.stderr);
  const context=parseOutput(flagged).hookSpecificOutput?.additionalContext || '';
  assert.match(context,/silent Python exception swallow/);
  assert.match(context,/mock\/fake\/dummy constant/);
  const clean=runHygiene(repo,{command:'*** Begin Patch\n*** Update File: clean.py\n@@\n+answer = 42\n*** End Patch'},cwd);
  assert.equal(clean.status,0,clean.stderr);
  assert.equal(parseOutput(clean).hookSpecificOutput,undefined);
});

test('Codex hygiene refuses outside-root and symlink targets and reports bounded skips', (t) => {
  const repo=fs.mkdtempSync(path.join(os.tmpdir(),'codex-hygiene-root-'));
  const external=fs.mkdtempSync(path.join(os.tmpdir(),'codex-hygiene-external-'));
  t.after(()=>{fs.rmSync(repo,{recursive:true,force:true});fs.rmSync(external,{recursive:true,force:true});});
  fs.writeFileSync(path.join(external,'secret.py'),'except: pass');
  fs.symlinkSync(external,path.join(repo,'linked'));
  for(const target of [path.join(external,'secret.py'),'linked/secret.py']) {
    const result=runHygiene(repo,{command:`*** Begin Patch\n*** Update File: ${target}\n@@\n+x\n*** End Patch`});
    const context=parseOutput(result).hookSpecificOutput?.additionalContext || '';
    assert.match(context,/outside.*root/i);
    assert.doesNotMatch(context,/silent Python/);
  }
  fs.writeFileSync(path.join(repo,'large.py'),'x'.repeat(1024*1024+1));
  const result=runHygiene(repo,{command:'*** Begin Patch\n*** Update File: large.py\n@@\n+x\n*** End Patch'});
  assert.match(parseOutput(result).hookSpecificOutput.additionalContext,/size limit/);
});

test('validator adapter denies unexpected exit and synchronous timeout', (t) => {
  const repo=fs.mkdtempSync(path.join(os.tmpdir(),'codex-validator-deadline-'));
  t.after(()=>fs.rmSync(repo,{recursive:true,force:true}));
  const lib=path.join(repo,'.claude/hooks/lib'); fs.mkdirSync(lib,{recursive:true});
  const adapter=path.join(lib,'codex-hook-runtime.js'); fs.copyFileSync(wrapper,adapter);
  const target=path.join(repo,'.claude/hooks/validate-bash-command.js');
  fs.writeFileSync(target,'process.exit(1);');
  const failed=spawnSync(process.execPath,[adapter,'./.claude/hooks/validate-bash-command.js'],{encoding:'utf8'});
  assert.equal(failed.status,2);
  assert.match(failed.stderr,/validation could not complete/);
  fs.writeFileSync(target,'Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,Infinity);');
  const hung=spawnSync(process.execPath,[adapter,'./.claude/hooks/validate-bash-command.js'],{encoding:'utf8',timeout:8000});
  assert.equal(hung.status,2,hung.stderr);
  assert.match(hung.stderr,/codex-hook-runtime/);
  assert.equal(hung.error,undefined);
});

test('Codex validator input timeout denies rather than allowing unchecked input', async () => {
  const {spawn}=require('node:child_process');
  const child=spawn(process.execPath,[path.join(root,'.claude/hooks/validate-bash-command.js')],{env:{...process.env,COC_RUNTIME:'codex'},stdio:['pipe','pipe','pipe']});
  let stdout=''; let stderr='';
  child.stdout.on('data',chunk=>stdout+=chunk); child.stderr.on('data',chunk=>stderr+=chunk);
  const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});
  assert.equal(code,2,stderr);
  assert.equal(parseOutput({stdout,stderr,status:code}).hookSpecificOutput.permissionDecision,'deny');
  assert.match(stderr,/timed out/);
});

test('Codex hygiene reports patch size/count limits and supports direct Write payloads', (t) => {
  const repo=fs.mkdtempSync(path.join(os.tmpdir(),'codex-hygiene-limits-'));
  t.after(()=>fs.rmSync(repo,{recursive:true,force:true}));
  for (const command of ['x'.repeat(1024*1024+1),'*** Begin Patch\n'+Array.from({length:101},(_,i)=>`*** Add File: ${i}.py\n+x`).join('\n')+'\n*** End Patch']) {
    const result=runHygiene(repo,{command});
    assert.equal(result.status,0,result.stderr);
    assert.match(parseOutput(result).hookSpecificOutput.additionalContext,/limit/);
  }
  fs.writeFileSync(path.join(repo,'write.py'),'except: pass');
  const result=spawnSync(process.execPath,[path.join(root,'.claude/hooks/integration-hygiene.js')],{
    encoding:'utf8',env:{...process.env,COC_RUNTIME:'codex',CLAUDE_PROJECT_DIR:repo},
    input:JSON.stringify({hook_event_name:'PostToolUse',tool_name:'Write',tool_input:{file_path:'write.py'},cwd:repo}),
  });
  assert.match(parseOutput(result).hookSpecificOutput.additionalContext,/silent Python exception swallow/);
});

test('native budget includes shell startup before bounded validation', (t) => {
  const repo=fs.mkdtempSync(path.join(os.tmpdir(),'codex-startup-budget-'));
  t.after(()=>fs.rmSync(repo,{recursive:true,force:true}));
  assert.equal(spawnSync('git',['init','-q',repo]).status,0);
  const lib=path.join(repo,'.claude/hooks/lib');fs.mkdirSync(lib,{recursive:true});
  fs.copyFileSync(wrapper,path.join(lib,'codex-hook-runtime.js'));
  fs.writeFileSync(path.join(repo,'.claude/hooks/validate-bash-command.js'),
    "Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,2500);process.stdout.write('validated');");
  const native=manifest.hooks.PreToolUse[0].hooks[0];
  // A four-second startup plus a valid 2.5-second child exceeds the old native
  // five-second window, while each stage individually fits its own budget.
  const result=spawnSync('/bin/sh',['-c',`sleep 4\nexec ${native.command}`],{
    cwd:repo,input:'{}',encoding:'utf8',timeout:native.timeout*1000,
  });
  assert.equal(result.status,0,result.stderr);
  assert.equal(result.error,undefined);
  assert.equal(result.stdout,'validated');
});

test('SessionStart and hygiene have real deadlines even during synchronous work', async (t) => {
  const {spawn}=require('node:child_process');
  const repo=fs.mkdtempSync(path.join(os.tmpdir(),'codex-lifecycle-deadline-'));
  t.after(()=>fs.rmSync(repo,{recursive:true,force:true}));
  const lib=path.join(repo,'.claude/hooks/lib');fs.mkdirSync(lib,{recursive:true});
  const adapter=path.join(lib,'codex-hook-runtime.js');fs.copyFileSync(wrapper,adapter);
  await Promise.all([['session-start.js',20000,'SessionStart'],['integration-hygiene.js',10000,'PostToolUse']].map(async ([name,budget,event])=>{
    fs.writeFileSync(path.join(repo,'.claude/hooks',name), 'process.exit(1);');
    const warning=spawnSync(process.execPath,[adapter,`./.claude/hooks/${name}`],{encoding:'utf8'});
    assert.equal(warning.status,1,`${event}: warning status changed`);
    fs.writeFileSync(path.join(repo,'.claude/hooks',name),
      "process.on('SIGTERM',()=>{});Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,22000);process.stdout.write('completed past deadline');");
    const outerMs=manifest.hooks[event][0].hooks[0].timeout*1000;
    assert.ok(outerMs>=budget+10000,`${event}: no startup allowance`);
    const child=spawn(process.execPath,[adapter,`./.claude/hooks/${name}`],{stdio:['ignore','pipe','pipe']});
    let stdout='';let stderr='';
    child.stdout.on('data',chunk=>stdout+=chunk);child.stderr.on('data',chunk=>stderr+=chunk);
    const started=Date.now();
    const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});
    assert.equal(code,2,`${event}: ${stdout} ${stderr}`);
    assert.match(stderr,/ETIMEDOUT|timed out/);
    assert.equal(stdout,'');
    assert.ok(Date.now()-started>=budget-500,`${event}: terminated before intended child budget`);
  }));
});
