#!/usr/bin/env node
/**
 * Audit fixtures for `.claude/hooks/coc-telemetry-autocommit.js::evaluateGates`.
 *
 * Per `rules/cc-artifacts.md` Rule 9: every scope-restriction predicate
 * the hook relies on MUST have a committed test fixture. This script is
 * the mechanical regression lock — run it with `node` and it asserts
 * one case per predicate plus a positive (proceed) case.
 *
 * Run: `node .claude/audit-fixtures/coc-telemetry-autocommit/gates.test.js`
 * Exit 0 = all asserts pass; non-zero = regression.
 */

const path = require("path");
const assert = require("assert");

const HOOK_PATH = path.resolve(
  __dirname,
  "..",
  "..",
  "hooks",
  "coc-telemetry-autocommit.js",
);
const { evaluateGates, TELEMETRY_PATHS, LOCK_STALE_MS } = require(HOOK_PATH);

const FRESH_LOCK_AGE = 60 * 1000; // 1 min — well under LOCK_STALE_MS
const STALE_LOCK_AGE = LOCK_STALE_MS + 1000; // 1s past the threshold

// Build a "happy path" base; each fixture mutates exactly one predicate.
function baseInput() {
  return {
    syncManifestExists: true,
    lockfilePresent: false,
    lockfileAgeMs: 0,
    branch: "main",
    porcelainLines: [
      " M .claude/learning/observations.jsonl",
      " M .claude/learning/violations.jsonl",
    ],
    ghAuthOk: true,
  };
}

const cases = [
  {
    name: "positive — telemetry-only drift on main, all gates pass",
    input: baseInput(),
    expectProceed: true,
  },
  {
    name: "predicate 1 — sync-manifest absent (not loom)",
    input: { ...baseInput(), syncManifestExists: false },
    expectProceed: false,
    reasonContains: "not loom",
  },
  {
    name: "predicate 2 — lockfile present and fresh",
    input: {
      ...baseInput(),
      lockfilePresent: true,
      lockfileAgeMs: FRESH_LOCK_AGE,
    },
    expectProceed: false,
    reasonContains: "lockfile present",
  },
  {
    name: "predicate 2 — lockfile present but stale (treated as absent)",
    input: {
      ...baseInput(),
      lockfilePresent: true,
      lockfileAgeMs: STALE_LOCK_AGE,
    },
    expectProceed: true,
  },
  {
    name: "predicate 3 — on feature branch (not main)",
    input: { ...baseInput(), branch: "feat/some-work" },
    expectProceed: false,
    reasonContains: "not on main",
  },
  {
    name: "predicate 4 — no drift at all",
    input: { ...baseInput(), porcelainLines: [] },
    expectProceed: false,
    reasonContains: "no drift",
  },
  {
    name: "predicate 4 — mixed drift (telemetry + non-telemetry)",
    input: {
      ...baseInput(),
      porcelainLines: [
        " M .claude/learning/observations.jsonl",
        " M .claude/rules/foo.md",
      ],
    },
    expectProceed: false,
    reasonContains: "non-telemetry path",
  },
  {
    name: "predicate 4 — staged change shape (not bare modification)",
    input: {
      ...baseInput(),
      porcelainLines: ["M  .claude/learning/observations.jsonl"],
    },
    expectProceed: false,
    reasonContains: "non-telemetry change shape",
  },
  {
    name: "predicate 4 — untracked file (?? shape)",
    input: {
      ...baseInput(),
      porcelainLines: ["?? .claude/learning/observations.jsonl"],
    },
    expectProceed: false,
    reasonContains: "non-telemetry change shape",
  },
  {
    name: "predicate 4 — deleted telemetry (D shape) does not trigger autocommit",
    input: {
      ...baseInput(),
      porcelainLines: [" D .claude/learning/observations.jsonl"],
    },
    expectProceed: false,
    reasonContains: "non-telemetry change shape",
  },
  {
    name: "predicate 5 — gh CLI not authenticated",
    input: { ...baseInput(), ghAuthOk: false },
    expectProceed: false,
    reasonContains: "gh CLI not authenticated",
  },
  {
    name: "telemetry path allowlist enforced (random .claude/learning/* path rejected)",
    input: {
      ...baseInput(),
      porcelainLines: [" M .claude/learning/posture.json"],
    },
    expectProceed: false,
    reasonContains: "non-telemetry path",
  },
];

let failed = 0;
for (const c of cases) {
  try {
    const v = evaluateGates(c.input);
    assert.strictEqual(
      v.proceed,
      c.expectProceed,
      `${c.name}: expected proceed=${c.expectProceed}, got ${v.proceed} (reason: ${v.reason})`,
    );
    if (c.reasonContains) {
      assert.ok(
        v.reason.includes(c.reasonContains),
        `${c.name}: expected reason to include "${c.reasonContains}", got "${v.reason}"`,
      );
    }
    process.stdout.write(`PASS  ${c.name}\n`);
  } catch (e) {
    failed++;
    process.stdout.write(`FAIL  ${e.message}\n`);
  }
}

// Sanity: ensure telemetry allowlist is exactly the expected pair.
assert.deepStrictEqual(
  TELEMETRY_PATHS.slice().sort(),
  [
    ".claude/learning/observations.jsonl",
    ".claude/learning/violations.jsonl",
  ].sort(),
  "TELEMETRY_PATHS allowlist drifted",
);
process.stdout.write(`PASS  TELEMETRY_PATHS allowlist unchanged\n`);

process.stdout.write(
  `\n${cases.length + 1 - failed}/${cases.length + 1} passed; ${failed} failed\n`,
);
process.exit(failed === 0 ? 0 : 1);
