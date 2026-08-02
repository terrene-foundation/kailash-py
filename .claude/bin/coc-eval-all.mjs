#!/usr/bin/env node
/**
 * coc-eval-all — CI entry-point for the STRUCTURAL COC eval-harness (C2).
 *
 * Iterates `.claude/test-harness/eval-manifest.json`, runs the reusable
 * `runEvalHarness` engine on every STRUCTURAL entry (scanner !== null), and
 * exits non-zero on ANY fixture failure. Offline, deterministic — this is the
 * hard structural gate CI runs on every PR (the semantic LLM-judge probe layer
 * is Contract C3, run separately by /test-harness-probe).
 *
 * Probe-only entries (scanner === null) are SKIPPED here with an explicit note
 * — their efficacy is checked by the probe layer, not this structural runner.
 *
 * A missing scanner OR a missing fixture inside a structural entry is a HARD
 * error — a coverage gap is NEVER a silent pass (zero-tolerance.md Rule 2). A
 * declared-but-missing scanner is caught FAIL-CLOSED by manifest-integrity
 * check (a) BEFORE the entries loop runs (integrity failure ⇒ exit 1); the
 * belt-and-suspenders guard in the loop below is an ERROR too, never a SKIP.
 * (The prior "not integrated yet ⇒ skip" branch was dead — integrity already
 * hard-fails a missing scanner — and contradicted the fail-closed contract.)
 *
 * Coverage floor: every `type:tool` entry MUST produce a structural run;
 * defense-in-depth atop manifest-integrity check (d) so a tool whose coverage
 * silently vanished (e.g. downgraded to scanner:null) cannot exit 0.
 *
 * DECLARED-EMPTY vs UNCONFIGURED (loom#1368 part 2). A zero-entry run verifies
 * NOTHING, so it may never print `ALL STRUCTURAL PASS`:
 *   - manifest ABSENT / unparseable / present-but-empty-with-no-declaration
 *     → UNCONFIGURED → exit 1. Silence can no longer read as coverage.
 *   - manifest present, zero entries, carrying an explicit
 *     `_declared_empty: { reason, graduation }` → exit 0, under a loud
 *     NO-STRUCTURAL-COVERAGE banner quoting the declaration (loom's own C2 §3.2
 *     steady state: the eval ENGINE adopted with no local structural scanners).
 *   - a stale `_declared_empty` alongside real entries → exit 1 (integrity (k)).
 * `--json` carries the same signal as `summary.coverage_asserted`.
 *
 * `--require-coverage` turns `coverage_asserted` into an exit code for repos that
 * HAVE structural coverage (R1 HIGH-2 — otherwise nothing machine-reads the field).
 *
 * Usage:
 *   node .claude/bin/coc-eval-all.mjs [--json] [--manifest <path>] [--require-coverage]
 *
 * Exit 0: every structural entry's fixtures matched expectations (or a declared
 *         zero-coverage run — see above; check `coverage_asserted`, not the exit).
 * Exit 1: any structural fixture mismatched, a genuine coverage-gap error, or an
 *         unconfigured/undeclared-empty manifest.
 *
 * Dependencies: Node.js built-ins + coc-eval-core.mjs. Zero external deps.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { runEvalHarness } from "./coc-eval-core.mjs";
import { checkManifestIntegrity } from "./coc-manifest-integrity.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
// Repo root = two levels up from .claude/bin/.
const REPO_ROOT = resolve(__dirname, "..", "..");

const args = process.argv.slice(2);
const jsonMode = args.includes("--json");
// --require-coverage (loom#1368 R1 HIGH-2): turn `coverage_asserted` into an
// EXIT CODE. Without it the field is reported but nothing reads it, so a run
// that verified zero artifacts and a run that verified all of them produce the
// same CI outcome. A repo that HAS structural coverage passes this flag to make
// losing it a hard failure; loom's own CI cannot (its steady state is the
// declared-empty manifest), so at loom the equivalent guarantee comes from
// integrity check (k)'s bidirectional declaration<->coverage equivalence.
const requireCoverage = args.includes("--require-coverage");
let manifestPath = join(REPO_ROOT, ".claude", "test-harness", "eval-manifest.json");
const mi = args.indexOf("--manifest");
if (mi !== -1 && args[mi + 1]) {
  manifestPath = isAbsolute(args[mi + 1]) ? args[mi + 1] : resolve(process.cwd(), args[mi + 1]);
}

if (args.includes("--help") || args.includes("-h")) {
  console.log(`coc-eval-all — CI structural gate over the COC eval-manifest.

Usage:
  node .claude/bin/coc-eval-all.mjs [--json] [--manifest <path>] [--require-coverage]

  --require-coverage   exit non-zero when the run asserted ZERO structural
                       coverage, even if the manifest declares that state.

Exit 0: every structural entry passed. Exit 1: any structural failure or coverage gap.`);
  process.exit(0);
}

// An ABSENT manifest is an UNCONFIGURED harness — HARD FAIL (loom#1368 part 2).
//
// This bin previously treated an absent manifest as "0 entries → exit 0", so a
// repo that received the eval ENGINE without ever declaring a manifest reported
// `ALL STRUCTURAL PASS` on every PR. coc-artifact-eval-coverage.md calls this
// exit-0 a hard gate with `block` severity, so that green vouched for nothing —
// a gate structurally unable to fail. A repo adopting the engine now MUST say
// what it expects: real entries, or an explicit `_declared_empty` declaration
// (one object) stating that zero IS the intended steady state. Both are cheap;
// silence is the one thing that can no longer read as coverage.
//
// A PRESENT-but-corrupt manifest was, and remains, a HARD error.
const manifestPresent = existsSync(manifestPath);
let manifest = {};
if (manifestPresent) {
  try {
    manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  } catch (e) {
    console.error(`ERROR: cannot parse eval-manifest at ${manifestPath}: ${e.message}`);
    process.exit(1);
  }
}

// Resolve manifest-relative paths against the repo root, and run each scanner
// from the repo root so scanner-internal repo-relative lookups (e.g. the K1
// tool at tools/canon-sync.mjs) resolve correctly.
const originalCwd = process.cwd();
process.chdir(REPO_ROOT);

const rel = (p) => (p == null ? null : isAbsolute(p) ? p : resolve(REPO_ROOT, p));

const entries = Object.entries(manifest).filter(([id]) => !id.startsWith("_"));
const report = [];
let anyFail = false;

// ---------------------------------------------------------------------------
// manifest-integrity FIRST — the F1-class tripwire. HARD-FAIL (exit 1) when a
// declared scanner/fixtures/probes path does not resolve, a probe row cites a
// phantom artifact_id, or an on-disk COC artifact has no manifest entry. A
// declared-but-missing scanner is a FAIL here, never a downstream SKIP.
// ---------------------------------------------------------------------------
// An ABSENT manifest is UNCONFIGURED, not clean — it fails closed here rather
// than SKIPping to a vacuous exit 0 (loom#1368 part 2).
const absentManifestError = `no eval-manifest at ${manifestPath} — the eval harness is UNCONFIGURED, which is a FAILURE, not a pass. This run verified ZERO artifacts and cannot vouch for anything. Declare a manifest: register real entries, OR — if zero structural entries IS the intended steady state for this repo — declare it explicitly with a top-level {"_declared_empty": {"reason": "...", "graduation": "..."}}`;
const integrity = manifestPresent
  ? checkManifestIntegrity({ manifestPath, repoRoot: REPO_ROOT })
  : { ok: false, errors: [absentManifestError], absent: true };
report.push({
  id: "manifest-integrity",
  type: "gate",
  status: integrity.ok ? "PASS" : "ERROR",
  reason: integrity.ok ? "manifest ↔ probes ↔ on-disk artifacts consistent" : integrity.errors.join("; "),
  errors: integrity.errors,
  // Declared-but-unregistered coverage (e.g. `_deferred_probes`). Legal, but a
  // GAP — surfaced into the CI log so it is never invisibly clean.
  notes: integrity.notes ?? [],
  // UNDECLARED coverage gaps (loom#1393): a gate that asserted NOTHING in this
  // repo because its class routes the pin sets to a manifest declaration this
  // repo has not made. Non-fatal by design (a hard fail would regress a
  // never-surveyed consumer — security.md § Secure-Default), so it MUST be loud
  // in the CI log or it is the vacuous pass all over again.
  warnings: integrity.warnings ?? [],
});
if (!integrity.ok) {
  anyFail = true;
}

// Only iterate the structural entries when manifest-integrity is clean — a
// broken manifest is a hard gate; running scanners over it would report noise.
for (const [id, spec] of integrity.ok ? entries : []) {
  if (!spec || typeof spec !== "object") continue;

  // Probe-only entry: no structural scanner — skip with a note.
  if (spec.scanner == null) {
    report.push({
      id,
      type: spec.type ?? "unknown",
      status: "SKIP",
      reason: "probe-only entry (scanner: null) — semantic efficacy checked by /test-harness-probe",
      probes: spec.probes ?? null,
    });
    continue;
  }

  const scannerPath = rel(spec.scanner);
  // Belt-and-suspenders: manifest-integrity check (a) already hard-fails a
  // declared-but-missing scanner before this loop runs. If one still reaches
  // here it is an ERROR (fail-closed), never a silent skip.
  if (!existsSync(scannerPath)) {
    anyFail = true;
    report.push({
      id,
      type: spec.type ?? "unknown",
      status: "ERROR",
      reason: `scanner does not resolve on disk: ${spec.scanner}`,
    });
    continue;
  }

  let result;
  try {
    result = runEvalHarness({
      scanner: scannerPath,
      fixturesDir: rel(spec.fixturesDir),
      expected: spec.expected,
    });
  } catch (e) {
    // A genuine coverage gap (missing fixture, malformed expected) is a HARD fail.
    anyFail = true;
    report.push({ id, type: spec.type ?? "unknown", status: "ERROR", reason: e.message });
    continue;
  }

  if (!result.passed) anyFail = true;
  report.push({
    id,
    type: spec.type ?? "unknown",
    status: result.passed ? "PASS" : "FAIL",
    summary: result.summary,
    fixtures: result.fixtures.map((f) => ({
      name: f.name,
      expected_exit: f.expected_exit,
      actual_exit: f.actual_exit,
      grade: f.actual_grade,
      score: f.score,
      verdict: f.verdict,
      mismatches: f.mismatches,
    })),
  });
}

process.chdir(originalCwd);

// ---------------------------------------------------------------------------
// Coverage floor (F1 defense-in-depth atop manifest-integrity check (d)):
// every type:tool entry MUST have produced a structural PASS/FAIL row. A tool
// that reached here without one means its structural coverage silently vanished
// — fail-closed. Only meaningful when the entries loop actually ran (integrity
// clean); a broken manifest already set anyFail.
// ---------------------------------------------------------------------------
if (integrity.ok) {
  const ranStructuralIds = new Set(
    report.filter((r) => r.status === "PASS" || r.status === "FAIL").map((r) => r.id),
  );
  for (const [id, spec] of entries) {
    if (spec && typeof spec === "object" && spec.type === "tool" && !ranStructuralIds.has(id)) {
      anyFail = true;
      report.push({
        id,
        type: "tool",
        status: "ERROR",
        reason: "type:tool entry produced no structural run — coverage floor breached (F1 defense)",
      });
    }
  }
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

const structural = report.filter((r) => (r.status === "PASS" || r.status === "FAIL") && r.type !== "gate");
const passCount = structural.filter((r) => r.status === "PASS").length;

// A run that executed ZERO structural entries asserts NO coverage, whatever its
// exit code (loom#1368 part 2). This covers BOTH the declared-empty manifest and
// the all-probe-only manifest (every entry `scanner:null` — also 0 scanners run,
// and equally misreported as "ALL STRUCTURAL PASS" before this change). The exit
// code says "nothing is broken"; `coverage_asserted` says whether anything was
// actually checked. Consumers citing this gate MUST read the second one.
const coverageAsserted = structural.length > 0;
// Under --require-coverage a zero-coverage run is a FAILURE even when every
// declaration is in order — the caller has stated this repo must verify
// something. Applied before the output block so text/JSON/exit all agree.
if (requireCoverage && !coverageAsserted && !anyFail) {
  anyFail = true;
  report.push({
    id: "coverage-floor",
    type: "gate",
    status: "ERROR",
    reason:
      "--require-coverage was passed but this run asserted ZERO structural coverage. Nothing was verified. Either register a structural entry, or drop --require-coverage if zero coverage is genuinely intended here (and declare it via _declared_empty).",
    errors: [],
    notes: [],
  });
}
const declaredEmpty = manifestPresent && manifest && typeof manifest._declared_empty === "object" && manifest._declared_empty !== null && !Array.isArray(manifest._declared_empty) ? manifest._declared_empty : null;

if (jsonMode) {
  console.log(
    JSON.stringify(
      {
        harness: "coc-eval-all",
        passed: !anyFail,
        entries: report,
        summary: {
          total_entries: entries.length,
          structural_run: structural.length,
          structural_pass: passCount,
          structural_fail: structural.length - passCount,
          skipped: report.filter((r) => r.status === "SKIP").length,
          errored: report.filter((r) => r.status === "ERROR").length,
          coverage_asserted: coverageAsserted,
          declared_empty: declaredEmpty !== null,
          declared_empty_reason: declaredEmpty ? declaredEmpty.reason : null,
        },
      },
      null,
      2,
    ),
  );
} else {
  console.log("COC Structural Eval Harness (coc-eval-all)");
  console.log("=".repeat(58));
  for (const r of report) {
    if (r.type === "gate") {
      if (r.status === "PASS") {
        console.log(`  [PASS]  ${r.id} — ${r.reason}`);
        for (const n of r.notes ?? []) console.log(`          NOTE: ${n}`);
        for (const w of r.warnings ?? []) console.log(`       !! WARN: ${w}`);
      } else {
        // A gate row is PASS or ERROR only. The former SKIP branch (absent
        // manifest) is gone — an unconfigured harness is a failure, not a skip.
        // Errors are itemised when the gate carries them (manifest-integrity);
        // otherwise the reason line IS the finding (coverage-floor).
        const errs = r.errors ?? [];
        if (errs.length > 0) {
          console.log(`  [ERROR] ${r.id} — FAILED:`);
          for (const e of errs) console.log(`            - ${e}`);
        } else {
          console.log(`  [ERROR] ${r.id} — ${r.reason}`);
        }
        for (const w of r.warnings ?? []) console.log(`       !! WARN: ${w}`);
      }
    } else if (r.status === "PASS" || r.status === "FAIL") {
      const s = r.summary;
      console.log(`  [${r.status}]  ${r.id} (${r.type}) — ${s.pass}/${s.total_fixtures} fixtures`);
      for (const f of r.fixtures) {
        const mark = f.verdict === "PASS" ? "ok" : "XX";
        console.log(`         ${mark} ${f.name}: exit ${f.actual_exit} (want ${f.expected_exit}), grade=${f.grade}`);
        for (const m of f.mismatches) console.log(`            mismatch: ${m}`);
      }
    } else if (r.status === "SKIP") {
      console.log(`  [SKIP]  ${r.id} (${r.type}) — ${r.reason}`);
    } else if (r.status === "ERROR") {
      console.log(`  [ERROR] ${r.id} (${r.type}) — ${r.reason}`);
    }
  }
  console.log("=".repeat(58));
  // The NO-COVERAGE banner. `ALL STRUCTURAL PASS (0/0 structural entries)` was
  // the string that made a vacuous run read as a verified one in every CI log;
  // a zero-entry run never prints it again.
  if (!anyFail && !coverageAsserted) {
    console.log("  !!  NO STRUCTURAL COVERAGE — THIS RUN IS NOT EVIDENCE  !!");
    console.log("  This run verified ZERO artifacts. Exit 0 means 'nothing declared is");
    console.log("  broken', NOT 'the artifacts are verified'. Do not cite it as coverage.");
    if (declaredEmpty) {
      console.log(`  Declared reason: ${declaredEmpty.reason}`);
      console.log(`  Graduation:      ${declaredEmpty.graduation}`);
    } else {
      console.log("  Every manifest entry is probe-only (scanner: null) — no structural");
      console.log("  scanner ran. Semantic efficacy is checked by /test-harness-probe.");
    }
    console.log("=".repeat(58));
  }
  const verdict = anyFail
    ? "FAILURES DETECTED"
    : coverageAsserted
      ? "ALL STRUCTURAL PASS"
      : "NO STRUCTURAL COVERAGE (exit 0 by declaration — NOT a pass over any artifact)";
  console.log(
    `Result: ${verdict} ` +
      `(${passCount}/${structural.length} structural entries; ` +
      `${report.filter((r) => r.status === "SKIP").length} skipped)`,
  );
}

process.exit(anyFail ? 1 : 0);
