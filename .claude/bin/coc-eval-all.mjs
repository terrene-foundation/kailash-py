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
 * Usage:
 *   node .claude/bin/coc-eval-all.mjs [--json] [--manifest <path>]
 *
 * Exit 0: every structural entry's fixtures matched expectations.
 * Exit 1: any structural fixture mismatched, or a genuine coverage-gap error.
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
let manifestPath = join(REPO_ROOT, ".claude", "test-harness", "eval-manifest.json");
const mi = args.indexOf("--manifest");
if (mi !== -1 && args[mi + 1]) {
  manifestPath = isAbsolute(args[mi + 1]) ? args[mi + 1] : resolve(process.cwd(), args[mi + 1]);
}

if (args.includes("--help") || args.includes("-h")) {
  console.log(`coc-eval-all — CI structural gate over the COC eval-manifest.

Usage:
  node .claude/bin/coc-eval-all.mjs [--json] [--manifest <path>]

Exit 0: every structural entry passed. Exit 1: any structural failure or coverage gap.`);
  process.exit(0);
}

// An ABSENT manifest is BENIGN — treat it as 0 entries → exit 0. This lets the
// harness ENGINE ship to a BUILD repo that has not yet declared its own
// eval-manifest (or receives the engine before its manifest), and lets loom's
// own empty steady-state pass, WITHOUT loom shipping its (empty) manifest to
// clobber a BUILD repo's populated one — the manifest is NOT distributed
// (test-harness/eval-manifest.json stays under the harness-wide exclude). A
// PRESENT-but-corrupt manifest is still a HARD error (a coverage gap is never a
// silent pass — zero-tolerance.md Rule 2), and a PRESENT manifest's integrity is
// still hard-checked below.
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
// An absent manifest has nothing to check — SKIP the gate (0 entries, exit 0);
// integrity.ok stays true so the entries loop + coverage floor below are no-ops.
const integrity = manifestPresent
  ? checkManifestIntegrity({ manifestPath, repoRoot: REPO_ROOT })
  : { ok: true, errors: [], skipped: true };
report.push({
  id: "manifest-integrity",
  type: "gate",
  status: integrity.skipped ? "SKIP" : integrity.ok ? "PASS" : "ERROR",
  reason: integrity.skipped
    ? `no eval-manifest at ${manifestPath} — 0 entries, nothing to check`
    : integrity.ok
      ? "manifest ↔ probes ↔ on-disk artifacts consistent"
      : integrity.errors.join("; "),
  errors: integrity.errors,
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
      } else if (r.status === "SKIP") {
        console.log(`  [SKIP]  ${r.id} — ${r.reason}`);
      } else {
        console.log(`  [ERROR] ${r.id} — manifest integrity FAILED:`);
        for (const e of r.errors ?? []) console.log(`            - ${e}`);
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
  console.log(
    `Result: ${anyFail ? "FAILURES DETECTED" : "ALL STRUCTURAL PASS"} ` +
      `(${passCount}/${structural.length} structural entries; ` +
      `${report.filter((r) => r.status === "SKIP").length} skipped)`,
  );
}

process.exit(anyFail ? 1 : 0);
