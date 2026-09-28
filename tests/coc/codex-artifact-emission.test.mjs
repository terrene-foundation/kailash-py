import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { test } from "node:test";
import { codexAgentConfig, emitCodexAgentPrompts, rebaseCodexAgentLinks } from "../../.claude/bin/emit-cli-artifacts.mjs";
import { composeArtifactBody, rewriteClaudePathsForCli } from "../../.claude/bin/lib/coc-manifest.mjs";

function parseToml(text) {
  return JSON.parse(execFileSync("python3", ["-c", "import json,sys,tomllib; print(json.dumps(tomllib.loads(sys.stdin.read())))"], { input: text, encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] }));
}

// Explicit expected values make the tests fail if the implementation rewrites
// source provenance, widens a role, drops filtering, or emits invalid TOML.
test("TOML parser negative control rejects malformed config", () => {
  assert.throws(() => parseToml('name = "unterminated'), /TOMLDecodeError/);
});

test("native schema preserves text and narrows read-only/no-shell roles", () => {
  const { content } = codexAgentConfig({ name: "security-reviewer", description: 'Review "quotes"', tools: "Read, Grep, Glob", model: "opus", hooks: "not portable" }, 'Text with \\ and """ and \'\'\'\nnew line', "quality/security-reviewer.md");
  const config = parseToml(content);
  assert.equal(config.name, "security-reviewer");
  assert.equal(config.description, 'Review "quotes"');
  assert.equal(config.sandbox_mode, "read-only");
  assert.equal(config.features.shell_tool, false);
  assert.equal(config.agents.enabled, false);
  assert.equal(config.web_search, "disabled");
  assert.match(config.developer_instructions, /Source tool inventory: Read, Grep, Glob/);
  assert.match(config.developer_instructions, /not an exact Claude tool allowlist/);
  assert.match(config.developer_instructions, /Text with \\ and """ and '''\nnew line/);
  assert.equal(config.model, undefined);
  assert.equal(config.hooks, undefined);
});

test("implementation roles inherit permission/model choices without widening", () => {
  const config = parseToml(codexAgentConfig({ name: "implementer", tools: "Read, Edit, Bash, Task" }, "Implement.", "implementation/implementer.md").content);
  for (const key of ["sandbox_mode", "approval_policy", "model", "model_reasoning_effort", "features", "agents"]) assert.equal(config[key], undefined, key);
});

test("invalid names and absent inventories fail closed", () => {
  assert.throws(() => codexAgentConfig({ name: "../escape", tools: "Read" }, "", "bad.md"), /Invalid Codex agent name/);
  assert.throws(() => codexAgentConfig({ name: "test" }, "", "bad.md"), /Missing specialist tool inventory/);
});

test("source paths survive quoted and fenced authoring examples", () => {
  const source = '> Source: `.claude/commands/name.md`\n```sh\ncat .claude/skills/command-authoring/SKILL.md\n```';
  for (const cli of ["codex", "gemini"]) {
    assert.equal(rewriteClaudePathsForCli(source, cli, { preserveSourcePaths: true }), source);
    assert.notEqual(rewriteClaudePathsForCli(source, cli), source);
    const emitted = composeArtifactBody("skills", "command-authoring/SKILL.md", cli, null).body;
    assert.match(emitted, /authoritative copy lives at `\.claude\/commands\/<name>\.md`/);
    assert.match(emitted, /\| CC\s*\| `\.claude\/commands\/<name>\.md`/);
  }
  assert.equal(rewriteClaudePathsForCli("Read .claude/commands/enroll.md", "gemini"), "Read .gemini/commands/enroll.toml");
});

test("native and compatibility outputs share tier/role/exclusion filters", () => {
  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "codex-emission-test-"));
  const base = { outDir, exclusions: { codex: [], gemini: [] }, tierFilter: ["agents/quality/**"], loomOnly: [], surfaceRoles: {}, targetRole: "build", lang: null, verbose: false };
  try {
    const all = emitCodexAgentPrompts(base);
    assert.equal(all.nativeAgents, 3);
    assert.equal(all.codex, 3);
    const agentDir = path.join(outDir, "codex", "agents");
    for (const name of fs.readdirSync(agentDir)) {
      const config = parseToml(fs.readFileSync(path.join(agentDir, name), "utf8"));
      assert.equal(config.name, path.basename(name, ".toml"));
      assert.equal(config.sandbox_mode, "read-only");
      assert.ok(config.developer_instructions.length > 100);
    }
    const prompt = fs.readFileSync(path.join(outDir, "codex/prompts/specialist-reviewer.md"), "utf8");
    assert.match(prompt, /Native named-agent delegation/);
    assert.doesNotMatch(prompt, /interactive Codex only|spawning is unreliable/);
    // Each filter must independently reject a known-present specialist.
    for (const override of [
      { exclusions: { codex: ["agents/quality/**"] } },
      { tierFilter: ["agents/not-present/**"] },
      { loomOnly: ["agents/quality/**"] },
      { surfaceRoles: Object.fromEntries(["reviewer", "security-reviewer", "gold-standards-validator"].map(n => [`agents/quality/${n}.md`, ["source"]])) },
    ]) {
      const result = emitCodexAgentPrompts({ ...base, ...override });
      assert.equal(result.codex, 0);
      assert.equal(result.nativeAgents, 0);
    }
    assert.equal(fs.existsSync(path.join(agentDir, "codex-architect.toml")), false);
  } finally {
    fs.rmSync(outDir, { recursive: true });
  }
});


test("flattened agent Markdown links retain source targets and fragments", () => {
  const source = '[skill](../../skills/05-kailash-mcp/SKILL.md#setup) [web](https://example.com/a) [anchor](#setup) [root](/docs/a.md) [near](peer.md)';
  const expected = '[skill](../../.claude/skills/05-kailash-mcp/SKILL.md#setup) [web](https://example.com/a) [anchor](#setup) [root](/docs/a.md) [near](../../.claude/agents/frameworks/peer.md)';
  assert.equal(rebaseCodexAgentLinks(source, 'frameworks/mcp-specialist.md'), expected);
  assert.notEqual(source, expected); // An identity transform must fail the oracle.
  const nested = rebaseCodexAgentLinks('[skill](../../../skills/05-kailash-mcp/SKILL.md)', 'frameworks/nested/mcp.md');
  assert.equal(nested, '[skill](../../.claude/skills/05-kailash-mcp/SKILL.md)');
});

test("specialist source dependencies survive CLI surface exclusion", () => {
  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "codex-dependencies-"));
  try {
    emitCodexAgentPrompts({ outDir, exclusions: { codex: ['skills/30-claude-code-patterns/**'] }, tierFilter: ['agents/quality/**'], loomOnly: [], surfaceRoles: {}, targetRole: 'build', lang: null, verbose: false });
    const native = parseToml(fs.readFileSync(path.join(outDir, 'codex/agents/reviewer.toml'), 'utf8'));
    const prompt = fs.readFileSync(path.join(outDir, 'codex/prompts/specialist-reviewer.md'), 'utf8');
    for (const text of [native.developer_instructions, prompt]) {
      assert.match(text, /`\.claude\/skills\/30-claude-code-patterns\/completion-criterion-evidence\.md`/);
      assert.doesNotMatch(text, /\.codex\/skills\/30-claude-code-patterns/);
    }
    assert.equal(fs.existsSync(path.join(outDir, 'codex/skills/30-claude-code-patterns')), false);
  } finally { fs.rmSync(outDir, { recursive: true }); }
});

test("all generated specialists resolve concrete source dependencies and Markdown links", () => {
  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-all-dependencies-'));
  const repo = path.resolve(import.meta.dirname, '../..');
  function unresolved(text, outputDir) {
    const missing = [];
    for (const match of text.matchAll(/\.claude\/[A-Za-z0-9_.\/-]+\.md/g)) {
      if (!fs.existsSync(path.join(repo, match[0]))) missing.push(match[0]);
    }
    const prose = text.replace(/^```[^\n]*\n[\s\S]*?^```[^\n]*$/gm, '');
    for (const [, target] of prose.matchAll(/\]\(([^\s)]+)\)/g)) {
      if (/^(?:[a-z][a-z0-9+.-]*:|[\/#<])/i.test(target)) continue;
      const file = target.split(/[?#]/)[0];
      if (!fs.existsSync(path.resolve(repo, outputDir, file))) missing.push(target);
    }
    return missing;
  }
  // Same instrument fires for an absent dependency and accepts a known one.
  assert.deepEqual(unresolved('[missing](../../skills/does-not-exist.md)', '.codex/prompts'), ['../../skills/does-not-exist.md']);
  assert.deepEqual(unresolved('[exists](../../.claude/skills/05-kailash-mcp/SKILL.md)', '.codex/prompts'), []);
  try {
    const result = emitCodexAgentPrompts({ outDir, exclusions: { codex: [] }, tierFilter: null, loomOnly: [], surfaceRoles: {}, targetRole: 'build', lang: null, verbose: false });
    assert.ok(result.nativeAgents > 0);
    for (const file of fs.readdirSync(path.join(outDir, 'codex/agents'))) {
      const native = parseToml(fs.readFileSync(path.join(outDir, 'codex/agents', file), 'utf8'));
      assert.deepEqual(unresolved(native.developer_instructions, '.codex/agents'), [], file);
    }
    for (const file of fs.readdirSync(path.join(outDir, 'codex/prompts'))) {
      assert.deepEqual(unresolved(fs.readFileSync(path.join(outDir, 'codex/prompts', file), 'utf8'), '.codex/prompts'), [], file);
    }
  } finally { fs.rmSync(outDir, { recursive: true }); }
});
