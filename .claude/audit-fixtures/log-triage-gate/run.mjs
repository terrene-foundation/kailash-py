#!/usr/bin/env node
// Audit fixture for log-triage-gate.js EXCLUDED_FILES predicate
// (observability.md Rule 5a — audit-log files excluded by filename).
//
// Contract: the session-end WARN+ scanner MUST NOT flag a structured
// append-only AUDIT log (whose payload verbatim-quotes commit subjects that
// may contain "WARNING"/"ERROR"), but MUST still flag a genuine runtime *.log.
//
// This drives the REAL hook end-to-end (spawns it with a Stop payload and
// asserts on the emitted systemMessage) so it locks the ACTUAL find
// expression + the EXCLUDED_FILES predicate's placement within the
// `\( -type d ... -prune \) -o -type f ...` branch — not a reconstruction.
//
// Run: node .claude/audit-fixtures/log-triage-gate/run.mjs   (exit 0 = pass)
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HOOK = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "hooks",
  "log-triage-gate.js",
);

const dir = mkdtempSync(join(tmpdir(), "log-triage-fixture-"));
// (a) an AUDIT log whose content contains a WARN+ token — MUST NOT flag
writeFileSync(
  join(dir, ".journal-skipped.log"),
  '2026-07-02T15:36:20Z <journal-skip>commit=abc reason=fix-routine subject="fix(fabric): remove exc_info from ChangeDetector poll-loop WARNING log"</journal-skip>\n',
);
// (b) a genuine runtime log with a WARN line — MUST flag
writeFileSync(
  join(dir, "runtime.log"),
  "2026-07-02T15:36:20Z WARN pool exhausted, degrading\n",
);

const res = spawnSync("node", [HOOK], {
  input: JSON.stringify({ cwd: dir }),
  encoding: "utf8",
  timeout: 10000,
});

let systemMessage = "";
try {
  systemMessage = JSON.parse(res.stdout || "{}").systemMessage || "";
} catch {
  console.error("FAIL: hook did not emit valid JSON:", res.stdout, res.stderr);
  process.exit(1);
}

const flaggedAudit = systemMessage.includes(".journal-skipped.log");
const flaggedRuntime = systemMessage.includes("runtime.log");

let ok = true;
if (flaggedAudit) {
  console.error("FAIL: .journal-skipped.log was flagged (must be excluded)");
  ok = false;
}
if (!flaggedRuntime) {
  console.error(
    "FAIL: runtime.log was NOT flagged (real WARN must still surface)",
  );
  ok = false;
}
if (ok)
  console.log(
    "PASS: real hook excludes .journal-skipped.log; runtime WARN still surfaced",
  );
process.exit(ok ? 0 : 1);
