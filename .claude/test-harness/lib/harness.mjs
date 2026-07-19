#!/usr/bin/env node
/*
 * CLI Test Harness — shared library (v2, post-redteam).
 *
 * Runs a single test against one CLI, captures stdout/stderr/exit/runtime,
 * scores against expected evidence (regex or negative regex), records JSONL
 * result. Invoked by suites/*.mjs.
 *
 * Redteam fixes applied:
 *   - M9: replaced require("fs") in setupFn pattern with proper ESM import
 *   - M11: env isolation — spawnSync uses a scrubbed env with stub HOME per CLI
 *   - M1 / M2: replaced execSync(`cp -r "..." "..."`) + execSync(`rm -rf "..."`)
 *              with spawnSync(argv) and fs.rmSync(recursive)
 *   - L4: captures CLI versions at init, emits a header record
 *   - L1: increased stdout cap to 32k for JSONL completeness
 *   - L3: timeoutMs heuristic loosened to 500ms slack
 */

import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

export const DEFAULT_TIMEOUT_MS = 180_000;

// Per-CLI timeout overrides. Gemini's headless -p mode has a slow first-token
// latency relative to cc/codex exec — SF1 repeatedly SIGKILL'd at 60s before
// it produced any output. Raise Gemini's budget to 180s.
//
// CC: bumped from 60s → 120s on 2026-05-07 after Week-2 probe migration smoke
// surfaced two timeout flakes (CM6, SF5) on plan-mode multi-step deliberation
// prompts. Root cause: CC's `--output-format json` (chosen for plan-mode
// determinism, see CLI_COMMANDS.cc) is whole-message buffered — when the
// timeout fires, stdout is empty because the JSON envelope is only emitted
// at completion. The 60s ceiling was too tight on prompts where CC has to
// (a) read multi-doc loaded baseline, (b) plan a refusal/permit, (c) cite a
// rule. 12 of 14 cc-only smoke tests finished in ≤44s; 2 hit the 60s ceiling
// with empty stdout; 120s gives 2.7× headroom over the worst non-timeout
// observation while preserving a hard backstop for genuinely-hung CC.
export const CLI_TIMEOUT_MS = {
  cc: 120_000,
  codex: 60_000,
  gemini: 180_000,
};

// Gemini quota-exhaustion retry tunables. When Gemini's API layer returns
// "exhausted your capacity" / "quota will reset", the first invocation bails
// instantly; a short pause + single retry usually succeeds. If BOTH attempts
// hit quota, the result is recorded as `skipped_quota_exhausted` — a distinct
// state from fail/pass so the aggregator can surface it separately from real
// failures (see aggregate.mjs per-test matrix).
export const QUOTA_RETRY_DELAY_MS = 10_000;
const QUOTA_STDERR_RE = /exhausted your capacity|quota will reset/i;

const REPO_ROOT = path.resolve(
  path.dirname(new URL(import.meta.url).pathname),
  "..",
  "..",
  "..",
);

export const HARNESS_ROOT = path.join(REPO_ROOT, ".claude", "test-harness");
export const RESULTS_DIR = path.join(HARNESS_ROOT, "results");
export const FIXTURES_DIR = path.join(HARNESS_ROOT, "fixtures");
fs.mkdirSync(RESULTS_DIR, { recursive: true });

// Stub HOME dirs per CLI — isolates from user's ~/.codex / ~/.gemini / ~/.claude.
// Populated on-demand per test via prepareFixture; lives under /tmp so
// no state leaks across runs.
export function stubHomeFor(cli, fixtureDir) {
  const home = path.join(fixtureDir, "_harness_home");
  fs.mkdirSync(home, { recursive: true });
  return home;
}

export function cliVersion(cli) {
  try {
    if (cli === "cc") return execFileSync("claude", ["--version"], { encoding: "utf8" }).trim();
    if (cli === "codex") return execFileSync("codex", ["--version"], { encoding: "utf8" }).trim();
    if (cli === "gemini") return execFileSync("gemini", ["--version"], { encoding: "utf8" }).trim();
    return "unknown";
  } catch {
    return "probe-failed";
  }
}

// Env isolation is calibrated per-CLI:
//   - HOME stays the REAL user home because all three CLIs read OAuth /
//     API-key state from ~/.{claude,codex,gemini}/ and cannot auth without it.
//   - CC: CLAUDE_CONFIG_DIR can be overridden → we point it at a stubHome
//     so the USER's rules/skills/agents do not leak into the test.
//   - Codex: CODEX_HOME can be overridden → same trick.
//   - Gemini: has no documented home-override env var (as of 0.38.x), so
//     the user's ~/.gemini/ IS read. We document this as a known
//     measurement caveat (M10b below) — tests that would be contaminated
//     by a user's own .gemini/agents or commands should use fixture-side
//     `.gemini/` files that take precedence (project-local scope wins
//     over user-global in Gemini's hierarchy loader).
export const CLI_COMMANDS = {
  cc: (fixtureDir, prompt, stubHome) => ({
    cmd: "claude",
    // --output-format json puts the assistant response in .result, which is
    // reliable across plan-mode exit recap variations. Empirically the
    // default text output is non-deterministic on conversational prompts
    // in plan mode: sometimes CC emits a full recap, sometimes only a
    // "no plan needed" meta-summary, dropping the actual answer. The JSON
    // envelope captures the assistant's final response unconditionally.
    // runCli post-processes by extracting .result for downstream scoring;
    // the raw envelope stays in the .log file for debugging.
    args: ["--permission-mode", "plan", "--output-format", "json", "-p", prompt],
    cwd: fixtureDir,
    env: {
      ...process.env,
      CLAUDE_PROJECT_DIR: fixtureDir,
      TERM: "dumb",
      // NOTE: CLAUDE_CONFIG_DIR intentionally NOT overridden. CC reads
      // OAuth credentials from ~/.claude/.credentials.json; stubbing the
      // config dir breaks auth. Residual: user's global .claude/
      // (custom rules/skills/agents) contaminates tests. Fixture-local
      // .claude/ takes precedence where it matters.
    },
  }),
  codex: (fixtureDir, prompt, stubHome) => ({
    cmd: "codex",
    args: [
      "exec",
      "--sandbox",
      "read-only",
      "--skip-git-repo-check",
      "--color",
      "never",
      prompt,
    ],
    cwd: fixtureDir,
    env: {
      ...process.env,
      TERM: "dumb",
      // NOTE: CODEX_HOME intentionally NOT overridden. Codex reads auth
      // from ~/.codex/; overriding the home dir breaks auth. Residual:
      // user's ~/.codex/AGENTS.md contaminates the baseline set. This
      // shows up as a per-CLI user-scoped marker in results — filter
      // via the AGENTS.md marker token specific to our fixture.
    },
  }),
  gemini: (fixtureDir, prompt, stubHome) => ({
    cmd: "gemini",
    args: ["--approval-mode", "plan", "-p", prompt],
    cwd: fixtureDir,
    env: {
      ...process.env,
      // NOTE: Gemini has no documented home override; ~/.gemini/ reads
      // from real HOME. Tests that could be contaminated by user's
      // global .gemini/ should use fixture-local `.gemini/` which takes
      // precedence per Gemini's project>user hierarchy.
      TERM: "dumb",
    },
  }),
};

// Per-CLI response extractors. Each takes the raw stdout bytes and returns
// the assistant's response text for scoring. `cc` uses --output-format json,
// so we extract:
//   1. .result (the assistant's final user-facing message)
//   2. .permission_denials[*].tool_input.{content, command, prompt} — text
//      that CC composed into a tool call but had blocked. In plan mode, CC
//      often expresses its full answer as Write(plan.md, content="..."); the
//      Write is denied, the .result becomes only a meta-summary, and the
//      actual answer lives in tool_input.content. Capturing it preserves
//      the assistant's intent for scoring without losing the response.
// On JSON parse failure we fall back to the raw bytes. codex and gemini
// emit their assistant response as plain text — identity extraction. The
// raw envelope is preserved on the returned object as `stdoutRaw` for the
// .log file.
const RESPONSE_EXTRACTORS = {
  cc: (raw) => {
    if (!raw) return "";
    try {
      const obj = JSON.parse(raw);
      const parts = [];
      if (obj && typeof obj.result === "string") parts.push(obj.result);
      if (obj && Array.isArray(obj.permission_denials)) {
        for (const d of obj.permission_denials) {
          const input = (d && d.tool_input) || {};
          for (const key of ["content", "command", "prompt", "description"]) {
            if (typeof input[key] === "string") parts.push(input[key]);
          }
        }
      }
      const text = parts.filter(Boolean).join("\n\n");
      if (text) return text;
    } catch {}
    return raw;
  },
  codex: (raw) => raw || "",
  gemini: (raw) => raw || "",
};

export function runCli(cli, fixtureDir, prompt, { timeoutMs } = {}) {
  // Per-CLI override lookup; explicit caller value wins if provided.
  const effectiveTimeout =
    timeoutMs !== undefined ? timeoutMs : (CLI_TIMEOUT_MS[cli] ?? DEFAULT_TIMEOUT_MS);
  const stubHome = stubHomeFor(cli, fixtureDir);
  const spec = CLI_COMMANDS[cli](fixtureDir, prompt, stubHome);
  const start = Date.now();
  const res = spawnSync(spec.cmd, spec.args, {
    cwd: spec.cwd,
    env: spec.env,
    encoding: "utf8",
    timeout: effectiveTimeout,
    maxBuffer: 10 * 1024 * 1024,
  });
  const runtimeMs = Date.now() - start;
  const rawStdout = res.stdout || "";
  const extract = RESPONSE_EXTRACTORS[cli] || ((s) => s);
  const stdout = extract(rawStdout);
  return {
    cli,
    cmd: `${spec.cmd} ${spec.args.map((a) => (a.includes(" ") ? `"${a.replace(/"/g, '\\"')}"` : a)).join(" ")}`,
    cwd: spec.cwd,
    stubHome,
    exitCode: res.status,
    signal: res.signal,
    stdout,
    stdoutRaw: rawStdout,
    stderr: res.stderr || "",
    runtimeMs,
    timedOut: res.signal === "SIGTERM" || runtimeMs >= effectiveTimeout - 500,
    effectiveTimeoutMs: effectiveTimeout,
  };
}

// Gemini-specific wrapper: invoke runCli, detect quota-exhaustion on stderr,
// pause + retry once. If the retry also hits quota, return a result object
// tagged `quotaExhausted: true` — runTest will record `skipped_quota_exhausted`
// instead of a fail. This is deliberately Gemini-only; cc/codex do not emit
// this stderr shape, so the detection is a no-op for them.
export function runCliWithQuotaRetry(cli, fixtureDir, prompt, opts = {}) {
  const first = runCli(cli, fixtureDir, prompt, opts);
  if (cli !== "gemini" || !QUOTA_STDERR_RE.test(first.stderr || "")) {
    return first;
  }
  // Deterministic busy-wait so the retry delay doesn't require making runTest
  // async on the hot path; QUOTA_RETRY_DELAY_MS is small enough (10s) that
  // blocking the harness process is acceptable for this diagnostic path.
  const deadline = Date.now() + QUOTA_RETRY_DELAY_MS;
  while (Date.now() < deadline) {
    // Intentional busy-wait; the alternative would require async propagation.
  }
  const second = runCli(cli, fixtureDir, prompt, opts);
  if (QUOTA_STDERR_RE.test(second.stderr || "")) {
    return { ...second, quotaExhausted: true, firstAttemptStderr: first.stderr };
  }
  return second;
}

// ────────────────────────────────────────────────────────────────
// Assertions
// ────────────────────────────────────────────────────────────────

export function expectMatch(output, pattern) {
  const re = typeof pattern === "string" ? new RegExp(pattern) : pattern;
  return re.test(output);
}

export function score(output, criteria) {
  // Probe criteria (kind: "probe") are NOT scored here — they require an
  // LLM-judge verdict that only the CC-session orchestrator can dispatch
  // (subagents). Per rules/probe-driven-verification.md MUST-1 regex-on-
  // semantic is BLOCKED, so we explicitly defer rather than falling back
  // to a regex proxy. The row is marked needs_probe; the orchestrator
  // (`commands/test-harness-probe.md`) reads it later, dispatches one
  // subagent per probe criterion, validates the answer against the
  // schema in `lib/probe-schemas.mjs`, and writes a `<basename>.probes.jsonl`
  // companion file with the scored verdicts.
  const results = [];
  let allPass = true;
  let needsProbe = false;
  for (const c of criteria) {
    if (c.kind === "probe") {
      results.push({
        label: c.label,
        kind: "probe",
        probe_schema: c.schema,
        pass: null,
        needs_probe: true,
      });
      needsProbe = true;
      continue;
    }
    const matched = expectMatch(output, c.pattern);
    const pass = c.kind === "contains" ? matched : !matched;
    if (!pass) allPass = false;
    results.push({
      label: c.label,
      kind: c.kind,
      pattern: c.pattern.toString(),
      pass,
    });
  }
  return {
    pass: needsProbe ? null : allPass,
    criteria: results,
    needs_probe: needsProbe,
  };
}

// ────────────────────────────────────────────────────────────────
// JSONL result writer
// ────────────────────────────────────────────────────────────────
let jsonlPath = null;
export function setResultsFile(filename) {
  jsonlPath = path.join(RESULTS_DIR, filename);
  fs.writeFileSync(jsonlPath, "");
}

export function writeHeader(header) {
  if (!jsonlPath) throw new Error("setResultsFile() required");
  fs.appendFileSync(jsonlPath, JSON.stringify({ _header: true, ...header }) + "\n");
}

export function recordResult(record) {
  if (!jsonlPath) throw new Error("setResultsFile() required");
  fs.appendFileSync(jsonlPath, JSON.stringify(record) + "\n");

  // Companion .log with full (untruncated) output for post-hoc inspection.
  const logName = `${record.cli}-${record.suite}-${record.test}.log`.replace(
    /[^a-zA-Z0-9._-]/g,
    "_",
  );
  const logPath = path.join(RESULTS_DIR, logName);
  fs.writeFileSync(
    logPath,
    `### CLI: ${record.cli} (${record.cliVersion || "?"})\n` +
    `### TEST: ${record.suite} / ${record.test}\n` +
    `### CMD: ${record.cmd || "n/a"}\n` +
    `### CWD: ${record.cwd || "n/a"}\n` +
    `### STUB_HOME: ${record.stubHome || "n/a"}\n` +
    `### EXIT: ${record.exitCode} (signal=${record.signal}) runtime=${record.runtimeMs}ms timedOut=${record.timedOut}\n\n` +
    `---- STDOUT ----\n${record.stdout_full || record.stdout || ""}\n\n` +
    `---- STDERR ----\n${record.stderr_full || record.stderr || ""}\n\n` +
    `---- SCORE ----\n${JSON.stringify(record.score, null, 2)}\n`,
  );
}

// ────────────────────────────────────────────────────────────────
// Fixture management — argv-safe (M1/M2 fix)
// ────────────────────────────────────────────────────────────────
const FIXTURE_NAME_RE = /^[a-zA-Z0-9._-]+$/;

export function prepareFixture(fixtureName, setupFn) {
  if (!FIXTURE_NAME_RE.test(fixtureName)) {
    throw new Error(`invalid fixture name: ${fixtureName}`);
  }
  const src = path.join(FIXTURES_DIR, fixtureName);
  if (!fs.existsSync(src)) {
    throw new Error(`fixture not found: ${src}`);
  }
  const stamp = Date.now() + "-" + Math.random().toString(36).slice(2, 8);
  const dst = path.join(os.tmpdir(), `coc-harness-${fixtureName}-${stamp}`);
  // cp -r via spawnSync argv (no shell)
  const cp = spawnSync("cp", ["-r", src, dst], { encoding: "utf8" });
  if (cp.status !== 0) throw new Error(`cp failed: ${cp.stderr}`);

  // setupFn runs BEFORE git commit so its files get tracked.
  if (setupFn) setupFn(dst, fs, path);

  // git init + commit via spawnSync
  spawnSync("git", ["init", "-q"], { cwd: dst });
  spawnSync("git", ["add", "-A"], { cwd: dst });
  spawnSync(
    "git",
    ["-c", "user.email=h@t", "-c", "user.name=h", "commit", "-q", "-m", "init"],
    { cwd: dst },
  );
  return dst;
}

export function cleanupFixtures(olderThanHours = 24) {
  const cutoff = Date.now() - olderThanHours * 3600 * 1000;
  const base = os.tmpdir();
  for (const d of fs.readdirSync(base)) {
    if (!/^coc-harness-[a-zA-Z0-9._-]+$/.test(d)) continue;
    const full = path.join(base, d);
    try {
      const st = fs.statSync(full);
      if (st.mtimeMs < cutoff) fs.rmSync(full, { recursive: true, force: true });
    } catch {}
  }
}

// ────────────────────────────────────────────────────────────────
// Uniform test runner
// ────────────────────────────────────────────────────────────────

// Precomputed at first call; avoids re-probing versions per test.
let _versions = null;
function getVersions() {
  if (_versions) return _versions;
  _versions = {
    cc: cliVersion("cc"),
    codex: cliVersion("codex"),
    gemini: cliVersion("gemini"),
    node: process.version,
    platform: `${process.platform} ${process.arch}`,
    os: `${os.type()} ${os.release()}`,
  };
  return _versions;
}

export async function runTest(suite, testName, cli, fixtureDir, prompt, criteria, opts = {}) {
  const versions = getVersions();
  const t0 = Date.now();
  let result;
  try {
    result = runCliWithQuotaRetry(cli, fixtureDir, prompt, opts);
  } catch (e) {
    result = {
      cli, cmd: "?", cwd: fixtureDir, stubHome: "?", exitCode: -1, signal: null,
      stdout: "", stdoutRaw: "", stderr: String(e), runtimeMs: Date.now() - t0, timedOut: false,
    };
  }
  const output = result.stdout + "\n" + result.stderr;
  const scoreResult = score(output, criteria);
  // A quota-exhausted run is NOT scored against the criteria — it is a
  // measurement failure of the API layer, not a CLI behavior failure. Mark
  // the record with an explicit `state` field that aggregate.mjs reads to
  // render ∅ in the matrix.
  const state = result.quotaExhausted
    ? "skipped_quota_exhausted"
    : scoreResult.needs_probe
      ? "needs_probe"
      : scoreResult.pass
        ? "pass"
        : "fail";
  const record = {
    suite,
    test: testName,
    cli,
    cliVersion: versions[cli],
    cmd: result.cmd,
    cwd: result.cwd,
    stubHome: result.stubHome,
    exitCode: result.exitCode,
    signal: result.signal,
    runtimeMs: result.runtimeMs,
    timedOut: result.timedOut,
    state,
    quotaExhausted: result.quotaExhausted || false,
    score: result.quotaExhausted
      ? { pass: false, criteria: [], skipped: true, reason: "quota_exhausted" }
      : scoreResult,
    stdout: result.stdout.slice(0, 32000),
    stderr: result.stderr.slice(0, 8000),
    // .log writer uses *_full fields for full debug context. For CC, stdoutRaw
    // is the JSON envelope (contains cost, model, session_id) — useful for
    // diagnosing CLI-side issues separately from the assistant response.
    stdout_full: result.stdoutRaw || result.stdout,
    stderr_full: result.stderr,
  };
  recordResult(record);
  // Strip _full fields from returned record (used only by log writer).
  const returned = { ...record };
  delete returned.stdout_full;
  delete returned.stderr_full;
  return returned;
}

export function suiteHeader(suiteName) {
  writeHeader({
    suite: suiteName,
    started_at: new Date().toISOString(),
    versions: getVersions(),
  });
}
