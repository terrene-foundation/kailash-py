#!/usr/bin/env node
/*
 * Aggregate JSONL results from all three suites × all three CLIs into a
 * single parity report suitable for pasting into session notes.
 *
 * Usage:  node .claude/test-harness/lib/aggregate.mjs
 *
 * Reads .claude/test-harness/results/*.jsonl, produces:
 *   - per-CLI per-suite pass/fail tallies
 *   - per-test matrix (rows = tests, columns = CLIs)
 *   - latency stats (p50/p90) per CLI
 *   - highlighted failures with short-form evidence
 *
 * Probe companion merge (per rules/probe-driven-verification.md MUST-1):
 *   Suite results may contain rows with state === "needs_probe" — assertion
 *   bodies that defer to an LLM-judge verdict supplied by the orchestrator
 *   (commands/test-harness-probe.md). Verdicts land in
 *   <basename>.probes.jsonl alongside the suite output. This aggregator
 *   reads both files: if a probe verdict matches a needs_probe row's
 *   probe criterion (keyed by suite/test/cli/label), the verdict is
 *   spliced in and the row's state is recomputed (pass / fail /
 *   still-needs-probe). Companions are NOT enumerated as suite rows —
 *   they are companion verdicts, not independent test runs.
 */

import fs from "node:fs";
import path from "node:path";

const RESULTS_DIR = path.resolve(
  path.dirname(new URL(import.meta.url).pathname),
  "..",
  "results",
);

// Filename guard. Probe companions are recognised by ending in
// `.probes.jsonl` so the main loop can skip them while a separate read
// pass collects their verdicts. Any future companion convention (e.g.
// `.coverage.jsonl`) MUST extend this guard explicitly — never let the
// main loop pick up rows whose schema differs from the suite-row schema.
function isProbeCompanion(filename) {
  return filename.endsWith(".probes.jsonl");
}

function readAll() {
  const files = fs.readdirSync(RESULTS_DIR).filter((f) => f.endsWith(".jsonl"));
  const rows = [];
  const headers = [];
  const probeRows = [];
  for (const f of files) {
    const lines = fs.readFileSync(path.join(RESULTS_DIR, f), "utf8").split("\n").filter(Boolean);
    const probeFile = isProbeCompanion(f);
    for (const line of lines) {
      let rec;
      try {
        rec = JSON.parse(line);
      } catch {
        continue;
      }
      if (probeFile) {
        probeRows.push(rec);
        continue;
      }
      if (rec._header) {
        headers.push({ file: f, ...rec });
      } else {
        rows.push(rec);
      }
    }
  }
  return { rows, headers, probeRows };
}

// Build a lookup table keyed by `${suite}/${test}/${cli}/${label}`. The
// suite-side criterion's `label` field is the join key; the orchestrator
// preserves it verbatim from the suite criterion when writing the
// companion (commands/test-harness-probe.md Step 6). When duplicate keys
// appear (re-scored probe), latest by judged_at wins — orchestrator
// runs are append-only and the latest verdict reflects the latest
// dispatch.
function buildProbeMap(probeRows) {
  const map = new Map();
  for (const p of probeRows) {
    if (!p || !p.suite || !p.test || !p.cli || !p.label) continue;
    const key = `${p.suite}/${p.test}/${p.cli}/${p.label}`;
    const prior = map.get(key);
    if (!prior) {
      map.set(key, p);
      continue;
    }
    const priorAt = Date.parse(prior.judged_at || "") || 0;
    const thisAt = Date.parse(p.judged_at || "") || 0;
    if (thisAt >= priorAt) map.set(key, p);
  }
  return map;
}

// Splice probe verdicts into needs_probe rows AND recompute row state.
// The merge is non-destructive — the original row is shallow-cloned, and
// each criterion is replaced rather than mutated, so a caller passing
// the same `rows` array to a second invocation sees idempotent results.
//
// Recomputed state semantics:
//   - any criterion still missing a verdict (probe map lookup miss)
//     → state stays "needs_probe", score.pass stays null
//   - all criteria resolved AND all pass → state = "pass"
//   - all criteria resolved AND ≥1 fails → state = "fail",
//     score.pass = false, criterion's pass stamped from probe verdict
//
// A probe verdict with `valid: false` (schema-validation failure) is
// treated as a hard fail and surfaces the validator's `reason` in
// failedCriteria — per probe-driven-verification.md MUST-2 a schema
// violation IS the verdict, not a retry signal.
function mergeProbeVerdicts(rows, probeMap) {
  const merged = [];
  for (const r of rows) {
    if (r.state !== "needs_probe" || !r.score || !Array.isArray(r.score.criteria)) {
      merged.push(r);
      continue;
    }
    const newCriteria = [];
    let stillNeedsProbe = false;
    let allPass = true;
    for (const c of r.score.criteria) {
      if (c.kind !== "probe" || c.needs_probe !== true) {
        newCriteria.push(c);
        if (c.pass === false) allPass = false;
        continue;
      }
      const key = `${r.suite}/${r.test}/${r.cli}/${c.label}`;
      const verdict = probeMap.get(key);
      if (!verdict) {
        newCriteria.push(c);
        stillNeedsProbe = true;
        continue;
      }
      const probePass = Boolean(verdict.valid) && Boolean(verdict.pass);
      const probeReason = !verdict.valid
        ? sanitizeForReport(verdict.reason || "schema validation failed")
        : verdict.pass
          ? null
          : extractFailedFields(verdict);
      newCriteria.push({
        ...c,
        pass: probePass,
        needs_probe: false,
        probe_pass: probePass,
        probe_valid: Boolean(verdict.valid),
        probe_reason: probeReason,
        evidence_quote: sanitizeForReport(verdict.evidence_quote || ""),
      });
      if (!probePass) allPass = false;
    }
    let newState;
    let newScorePass;
    if (stillNeedsProbe) {
      newState = "needs_probe";
      newScorePass = null;
    } else {
      newState = allPass ? "pass" : "fail";
      newScorePass = allPass;
    }
    merged.push({
      ...r,
      state: newState,
      score: { ...r.score, pass: newScorePass, criteria: newCriteria, needs_probe: stillNeedsProbe },
    });
  }
  return merged;
}

// Sanitize a string for inclusion in the failures section of the
// markdown report. The report renders inside a list whose entries
// later get pasted into PR descriptions / session notes — control
// characters or markdown control chars in adversarial probe payloads
// (schema names, validation reasons, rubric field names) would break
// the table layout or inject markdown when the report is pasted.
// Replace `\r`, `\n`, `|`, and backtick with a space; cap at 200 chars.
// Schema names and rubric field names in lib/probe-schemas.mjs are all
// snake_case identifiers, so this sanitizer is a no-op for legitimate
// values; it only activates when an adversarial subagent injects
// control-shaped tokens through a schema-permissive answer field.
function sanitizeForReport(s) {
  if (s === null || s === undefined) return "";
  const str = String(s).replace(/[\r\n|`]/g, " ");
  return str.length > 200 ? str.slice(0, 197) + "..." : str;
}

// For a probe verdict with valid:true but pass:false, surface the
// rubric fields that flipped false. The probe schema's scoringRule is
// AND across boolean fields (see lib/probe-schemas.mjs); listing the
// false fields tells the reader which dimension regressed without
// re-loading the full answer payload. evidence_quote and answer fields
// of unknown shape are excluded — only declared booleans count as
// "rubric fields". All string composition routes through
// sanitizeForReport() so adversarial probe payloads cannot break the
// report's markdown layout when pasted (security-reviewer LOW-1).
function extractFailedFields(verdict) {
  if (!verdict || !verdict.answer || typeof verdict.answer !== "object") {
    return verdict && verdict.reason
      ? sanitizeForReport(verdict.reason)
      : "probe failed (no answer)";
  }
  const failed = [];
  for (const [k, v] of Object.entries(verdict.answer)) {
    if (typeof v === "boolean" && v === false) failed.push(sanitizeForReport(k));
  }
  if (!failed.length) {
    return verdict.reason
      ? sanitizeForReport(verdict.reason)
      : "probe failed (no false fields)";
  }
  return `probe ${sanitizeForReport(verdict.schema)}: ${failed.join(", ")} = false`;
}

function percentile(sorted, p) {
  if (sorted.length === 0) return 0;
  const idx = Math.min(sorted.length - 1, Math.floor(sorted.length * p));
  return sorted[idx];
}

function main() {
  const { rows: rawRows, headers, probeRows } = readAll();
  const probeMap = buildProbeMap(probeRows);
  const rows = mergeProbeVerdicts(rawRows, probeMap);
  const byCliSuite = {};
  const byTest = {};
  const latencies = {};

  for (const r of rows) {
    const key = `${r.cli}/${r.suite}`;
    if (!byCliSuite[key]) byCliSuite[key] = { pass: 0, fail: 0, skipped: 0, needsProbe: 0 };
    // Skipped (quota-exhausted) and needs_probe runs are recorded separately
    // from pass/fail. needs_probe means the assertion requires an LLM-judge
    // verdict from the orchestrator (commands/test-harness-probe.md); the
    // verdict lands in a companion <basename>.probes.jsonl file. After
    // mergeProbeVerdicts, needs_probe survives ONLY if the companion was
    // missing or did not cover this row's criterion — counting it as fail
    // would misrepresent the CLI's behavior.
    const skipped = r.state === "skipped_quota_exhausted";
    const needsProbe = r.state === "needs_probe";
    if (skipped) byCliSuite[key].skipped = (byCliSuite[key].skipped || 0) + 1;
    else if (needsProbe) byCliSuite[key].needsProbe = (byCliSuite[key].needsProbe || 0) + 1;
    else if (r.score && r.score.pass) byCliSuite[key].pass++;
    else byCliSuite[key].fail++;

    if (!byTest[r.test]) byTest[r.test] = {};
    byTest[r.test][r.cli] = {
      pass: r.score ? r.score.pass : false,
      skipped,
      needsProbe,
      state: r.state || (r.score && r.score.pass ? "pass" : "fail"),
      runtimeMs: r.runtimeMs,
      failedCriteria: ((r.score && r.score.criteria) || [])
        .filter((c) => c.pass === false)
        .map((c) => c.probe_reason || c.label),
    };

    if (!latencies[r.cli]) latencies[r.cli] = [];
    latencies[r.cli].push(r.runtimeMs);
  }

  // Summary
  console.log("# CLI Parity Report (empirical)\n");
  console.log(`Generated: ${new Date().toISOString()}`);
  if (headers.length) {
    const v = headers[0].versions || {};
    console.log(`\nCLI versions:`);
    console.log(`  cc     = ${v.cc || "?"}`);
    console.log(`  codex  = ${v.codex || "?"}`);
    console.log(`  gemini = ${v.gemini || "?"}`);
    console.log(`  node   = ${v.node || "?"}`);
    console.log(`  os     = ${v.os || "?"}`);
  }

  // Overall pass rate. Skipped (quota-exhausted) cells are appended as
  // "+Nskip" so a Gemini run hit by a 3-test quota window does not read
  // as 3/5 failed when really it ran 2/2 and the API layer dropped 3.
  console.log("\n## Overall pass rate per CLI × suite\n");
  console.log("Legend: `+N∅` skipped (quota), `+N⚙` needs-probe (orchestrator pending).");
  console.log("");
  console.log("| CLI | Capability | Compliance | Safety | Total |");
  console.log("|-----|------------|------------|--------|-------|");
  const clis = ["cc", "codex", "gemini"];
  const suites = ["capability", "compliance", "safety"];
  for (const cli of clis) {
    const cells = [];
    let total = { pass: 0, fail: 0, skipped: 0, needsProbe: 0 };
    for (const s of suites) {
      const v = byCliSuite[`${cli}/${s}`] || { pass: 0, fail: 0, skipped: 0, needsProbe: 0 };
      const denom = v.pass + v.fail;
      const annotations = [];
      if (v.skipped) annotations.push(`+${v.skipped}∅`);
      if (v.needsProbe) annotations.push(`+${v.needsProbe}⚙`);
      const cell = annotations.length
        ? `${v.pass}/${denom} ${annotations.join(" ")}`
        : `${v.pass}/${denom}`;
      cells.push(cell);
      total.pass += v.pass;
      total.fail += v.fail;
      total.skipped += v.skipped || 0;
      total.needsProbe += v.needsProbe || 0;
    }
    const totalDenom = total.pass + total.fail;
    const totalAnn = [];
    if (total.skipped) totalAnn.push(`+${total.skipped}∅`);
    if (total.needsProbe) totalAnn.push(`+${total.needsProbe}⚙`);
    const totalCell = totalAnn.length
      ? `${total.pass}/${totalDenom} ${totalAnn.join(" ")}`
      : `${total.pass}/${totalDenom}`;
    cells.push(totalCell);
    console.log(`| ${cli.padEnd(6)} | ${cells.join(" | ")} |`);
  }

  // Per-test matrix
  console.log("\n## Per-test matrix (✓ pass, ✗ fail, ∅ skipped-quota, ⚙ needs-probe, — not run)\n");
  console.log("| Test | CC | Codex | Gemini |");
  console.log("|------|----|----|--------|");
  const tests = Object.keys(byTest).sort();
  for (const t of tests) {
    const cells = clis.map((c) => {
      const x = byTest[t][c];
      if (!x) return "—";
      if (x.skipped || x.state === "skipped_quota_exhausted") return "∅";
      if (x.needsProbe || x.state === "needs_probe") return "⚙";
      return x.pass ? "✓" : "✗";
    });
    console.log(`| ${t} | ${cells.join(" | ")} |`);
  }

  // Latency stats
  console.log("\n## Latency (per-test runtime, ms)\n");
  console.log("| CLI | p50 | p90 | max | n |");
  console.log("|-----|-----|-----|-----|---|");
  for (const cli of clis) {
    const arr = (latencies[cli] || []).slice().sort((a, b) => a - b);
    console.log(
      `| ${cli.padEnd(6)} | ${percentile(arr, 0.5) || 0} | ${percentile(arr, 0.9) || 0} | ${arr[arr.length - 1] || 0} | ${arr.length} |`,
    );
  }

  // Failures + skipped-quota callouts. Skipped cells are reported distinctly
  // so they are not mistaken for real failures; a real regression hunt filters
  // them out, but the counts remain visible in the per-CLI totals above.
  console.log("\n## Failures (per test, per CLI)\n");
  for (const t of tests) {
    for (const cli of clis) {
      const x = byTest[t][cli];
      if (!x) continue;
      if (x.skipped || x.state === "skipped_quota_exhausted") {
        console.log(`- **${t}** / ${cli}: ∅ skipped (quota exhausted after retry)`);
        continue;
      }
      if (x.needsProbe || x.state === "needs_probe") {
        console.log(
          `- **${t}** / ${cli}: ⚙ needs-probe (run \`/test-harness-probe\` to score)`,
        );
        continue;
      }
      if (x.pass === false) {
        console.log(
          `- **${t}** / ${cli}: ${x.failedCriteria.join("; ") || "(no criteria labeled)"}`,
        );
      }
    }
  }

  console.log("\n## Raw data");
  console.log(`- JSONL: ${RESULTS_DIR}/*.jsonl (${rows.length} test records)`);
  console.log(`- Probe verdicts: ${RESULTS_DIR}/*.probes.jsonl (${probeRows.length} verdicts merged)`);
  console.log(`- Per-test logs: ${RESULTS_DIR}/<cli>-<suite>-<test>.log`);
}

// Exported for the smoke test in tests/aggregate-merge.test.mjs. Pure
// functions only — no fs / no process side effects, so the test can
// drive them with synthetic fixtures.
export {
  buildProbeMap,
  mergeProbeVerdicts,
  extractFailedFields,
  isProbeCompanion,
  sanitizeForReport,
};

// Only run main() when invoked directly (not when imported as a module).
const isDirectInvocation =
  import.meta.url === `file://${process.argv[1]}` ||
  import.meta.url.endsWith(process.argv[1] || "");
if (isDirectInvocation) main();
