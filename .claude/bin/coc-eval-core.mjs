#!/usr/bin/env node
/**
 * coc-eval-core — reusable STRUCTURAL COC eval-harness engine.
 *
 * Factors the ~130-line test-runner pattern that the fork's KBV + Torque
 * eval-harnesses duplicate into ONE core. A COC "readiness scanner"
 * (e.g. `canon-sync-readiness-check.mjs`) runs CHECKS[] against a fixture
 * repo and encodes its verdict in its process EXIT CODE (0 = clean,
 * 1 = a critical check failed). This engine exercises such a scanner against
 * a set of audit-fixture repos and asserts each fixture produces its EXPECTED
 * disposition (exit code, and optionally grade + passed).
 *
 * This is the STRUCTURAL layer (Contract C2): offline, deterministic, NO LLM.
 * The semantic efficacy layer (LLM-judge probes, Contract C3) is separate.
 *
 * Fixture-existence guard is a HARD error: a fixture named in `expected` but
 * MISSING on disk is a coverage gap, NEVER a silent pass (zero-tolerance.md
 * Rule 2 — no fake pass). A missing scanner is likewise a HARD error (the
 * caller — coc-eval-all.mjs — skips probe-only entries whose scanner is null
 * BEFORE reaching this engine).
 *
 * Public API:
 *   runEvalHarness({ scanner, fixturesDir, expected }) -> { passed, fixtures[], summary }
 *
 *   scanner      absolute or repo-relative path to a `*-readiness-check.mjs`
 *   fixturesDir  directory holding one sub-dir per fixture case
 *   expected     { "<case-name>": { exit: 0|1, grade?: "...", passed?: bool,
 *                                   critical_failures?: ["<check-id>", ...] } }
 *                critical_failures pins the specific failing CRITICAL check-ids a
 *                violation fixture MUST exercise (binds the fixture to its
 *                detection class — a content swap keeping the same exit+grade but
 *                a different failing check no longer matches).
 *
 * Dependencies: Node.js built-ins only (child_process, fs, path). Zero deps.
 */

import { execFileSync } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { isAbsolute, join, resolve } from "node:path";

// Per-scanner wall-clock budget (ms). Env-overridable — read PER CALL, not at
// module load — so the `scanner-timeout` regression test can drive a sleeping
// stub past the budget without a 30s wait.
function scannerTimeoutMs() {
  return Number(process.env.COC_EVAL_SCANNER_TIMEOUT_MS) || 30000;
}

/** Parse JSON, returning { raw } on failure rather than throwing. */
function safeParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

/**
 * Extract a scanner's {grade, passed, score} verdict from its parsed JSON,
 * generically across scanner output shapes:
 *   - top-level:      { passed, grade, score, ... }   (torque-style)
 *   - single wrapper: { canon_sync_readiness: { grade, passed, score, ... } }
 *                     { kbv_readiness: { grade, score, ... } }
 * Returns { grade, passed, score } with null for any field not present.
 */
function extractVerdict(parsed) {
  const pick = (obj) =>
    obj && typeof obj === "object"
      ? {
          grade: obj.grade ?? null,
          passed: typeof obj.passed === "boolean" ? obj.passed : null,
          score: obj.score ?? null,
        }
      : { grade: null, passed: null, score: null };

  if (!parsed || typeof parsed !== "object") {
    return { grade: null, passed: null, score: null };
  }
  // Top-level verdict fields take precedence.
  if (parsed.grade !== undefined || typeof parsed.passed === "boolean") {
    return pick(parsed);
  }
  // Otherwise look one level deep for the first object carrying a grade/score.
  for (const value of Object.values(parsed)) {
    if (value && typeof value === "object" && (value.grade !== undefined || value.score !== undefined)) {
      return pick(value);
    }
  }
  return { grade: null, passed: null, score: null };
}

/**
 * Extract the scanner's per-check results array, generically across output
 * shapes: top-level `{ checks: [...] }` OR a single wrapper
 * `{ canon_sync_readiness: { checks: [...] } }`. Each check is
 * `{ id, critical, passed, ... }`. Returns [] when none is present.
 */
function extractChecks(parsed) {
  if (!parsed || typeof parsed !== "object") return [];
  if (Array.isArray(parsed.checks)) return parsed.checks;
  for (const value of Object.values(parsed)) {
    if (value && typeof value === "object" && Array.isArray(value.checks)) return value.checks;
  }
  return [];
}

function isDir(p) {
  try {
    return statSync(p).isDirectory();
  } catch {
    return false;
  }
}

/**
 * Run a structural scanner against every fixture named in `expected` and
 * assert each fixture produces its expected disposition.
 *
 * @returns {{ passed: boolean, fixtures: object[], summary: object }}
 * @throws  Error on a missing scanner or a missing fixture (HARD errors —
 *          a coverage gap is never a silent pass).
 */
export function runEvalHarness({ scanner, fixturesDir, expected }) {
  if (!scanner) {
    throw new Error("runEvalHarness: `scanner` is required (probe-only entries must be filtered by the caller)");
  }
  if (!fixturesDir) {
    throw new Error("runEvalHarness: `fixturesDir` is required for a structural scanner entry");
  }
  if (!expected || typeof expected !== "object" || Object.keys(expected).length === 0) {
    throw new Error("runEvalHarness: `expected` must be a non-empty { case: {exit,...} } map");
  }

  const scannerPath = isAbsolute(scanner) ? scanner : resolve(process.cwd(), scanner);
  if (!existsSync(scannerPath)) {
    throw new Error(`runEvalHarness: scanner not found at ${scannerPath} (structural coverage gap — not a pass)`);
  }

  const fixturesRoot = isAbsolute(fixturesDir) ? fixturesDir : resolve(process.cwd(), fixturesDir);
  if (!isDir(fixturesRoot)) {
    throw new Error(`runEvalHarness: fixtures directory not found at ${fixturesRoot} (coverage gap — not a pass)`);
  }

  // Fixture-existence guard: EVERY expected case MUST exist on disk. A missing
  // fixture is a silent-coverage-gap, HARD error — never a silent pass.
  const caseNames = Object.keys(expected).sort();
  const missing = caseNames.filter((name) => !isDir(join(fixturesRoot, name)));
  if (missing.length > 0) {
    throw new Error(
      `runEvalHarness: expected fixture(s) missing under ${fixturesRoot}: ${missing.join(", ")} ` +
        `(a missing fixture is a coverage gap, NEVER a silent pass)`,
    );
  }

  const fixtures = [];
  let allPassed = true;

  for (const name of caseNames) {
    const want = expected[name];
    const fixturePath = join(fixturesRoot, name);
    const row = {
      name,
      fixture_path: fixturePath,
      expected_exit: want.exit,
      actual_exit: null,
      expected_grade: want.grade ?? null,
      actual_grade: null,
      expected_passed: typeof want.passed === "boolean" ? want.passed : null,
      actual_passed: null,
      expected_critical_failures: Array.isArray(want.critical_failures) ? want.critical_failures : null,
      actual_failed_critical: null,
      score: null,
      mismatches: [],
      verdict: null,
      scanner_output: null,
    };

    let stdout = "";
    let unclean = false;
    let uncleanReason = null;
    try {
      stdout = execFileSync(process.execPath, [scannerPath, "--root", fixturePath, "--json"], {
        encoding: "utf8",
        timeout: scannerTimeoutMs(),
        stdio: ["pipe", "pipe", "pipe"],
      });
      row.actual_exit = 0;
    } catch (err) {
      // A signal-kill / timeout / maxBuffer overflow leaves err.status NON-numeric
      // (null) and sets err.killed / err.signal. That is NOT the scanner's intended
      // exit-code signal — it is a runner-level abort. Collapsing it to `1` (or any
      // number) and comparing to want.exit would FALSE-PASS an exit-1 fixture whose
      // scanner was actually killed (the F3 false-pass). Treat it as a HARD fail and
      // NEVER compare to want.exit.
      if (err.killed || err.signal || typeof err.status !== "number") {
        unclean = true;
        uncleanReason = err.signal || err.code || (err.killed ? "killed (timeout/maxBuffer)" : "non-numeric exit status");
        row.actual_exit = null;
      } else {
        // A clean non-zero numeric exit IS the scanner's intended signal.
        row.actual_exit = err.status;
      }
      stdout = typeof err.stdout === "string" ? err.stdout : "";
    }

    const parsed = safeParse(stdout);
    row.scanner_output = parsed;
    const verdict = extractVerdict(parsed);
    row.actual_grade = verdict.grade;
    row.actual_passed = verdict.passed;
    row.score = verdict.score;

    // 1. Exit code — the authoritative structural signal (always compared).
    if (unclean) {
      // Never a pass: an unclean abort is not a comparable exit code.
      row.mismatches.push(`scanner did not exit cleanly: ${uncleanReason}`);
    } else if (row.actual_exit !== want.exit) {
      row.mismatches.push(`exit: expected ${want.exit}, got ${row.actual_exit}`);
    }
    // 2. Grade — compared ONLY when the expected case pins one.
    if (want.grade !== undefined && want.grade !== null && row.actual_grade !== want.grade) {
      row.mismatches.push(`grade: expected ${want.grade}, got ${row.actual_grade}`);
    }
    // 3. passed — compared ONLY when the expected case pins one.
    if (typeof want.passed === "boolean" && row.actual_passed !== want.passed) {
      row.mismatches.push(`passed: expected ${want.passed}, got ${row.actual_passed}`);
    }
    // 4. critical_failures — compared ONLY when the expected case pins a list of
    // critical check-ids that MUST be present-and-failed. This binds a fixture to
    // the specific detection CLASS it exercises (its named failing critical check),
    // so a fixture-content swap that keeps the same exit + grade but flips to a
    // DIFFERENT failing check no longer matches the pin. Skipped on an unclean
    // abort (the fixture already FAILs on the exit-code mismatch).
    if (!unclean && Array.isArray(want.critical_failures) && want.critical_failures.length > 0) {
      const checks = extractChecks(parsed);
      const failedCritical = new Set(
        checks.filter((c) => c && c.critical === true && c.passed === false).map((c) => c.id),
      );
      row.actual_failed_critical = [...failedCritical];
      for (const id of want.critical_failures) {
        if (!failedCritical.has(id)) {
          row.mismatches.push(
            `critical_failures: expected failing critical check '${id}' not among actual failed-critical checks [${[...failedCritical].join(", ")}] (fixture no longer exercises its pinned detection class)`,
          );
        }
      }
    }

    row.verdict = row.mismatches.length === 0 ? "PASS" : "FAIL";
    if (row.verdict === "FAIL") allPassed = false;
    fixtures.push(row);
  }

  const summary = {
    total_fixtures: fixtures.length,
    pass: fixtures.filter((f) => f.verdict === "PASS").length,
    fail: fixtures.filter((f) => f.verdict === "FAIL").length,
  };

  return { passed: allPassed, fixtures, summary };
}
