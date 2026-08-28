#!/usr/bin/env node
/**
 * docker-sprawl-guard.js — the structural detector for `docker-no-sprawl.md`.
 *
 * @hook-event: PostToolUse:Edit|Write — the subject is a compose file's CONTENT,
 *   which does not exist until the write lands. PreToolUse cannot see the
 *   post-edit text for an Edit (it holds the patch, not the result), so the
 *   project-name and volume checks are only decidable after the write.
 * @hook-event: PreToolUse:Bash — the subject is the `docker run` command itself,
 *   which exists only as the pending invocation. Once it has run the container
 *   and its anonymous volume already exist, so no later event can prevent it.
 *
 * SEVERITY — `halt-and-report` on both surfaces, never `block`, per
 * `hook-output-discipline.md` MUST-2.
 *
 *   The Bash surface is LEXICAL (a regex over a command string), and MUST-2
 *   caps a lexical signal at `halt-and-report`. That is the binding constraint
 *   there and there is no argument for teeth.
 *
 *   The compose surface IS structural — a top-level `name:` key is present or
 *   absent, which no surface rewrite evades — so by MUST-2's letter it MAY
 *   carry `block`. It deliberately does not, on MUST-2's own MUST NOT:
 *   "detectors that block work the agent has been instructed to perform".
 *   Blocking a PostToolUse write cannot un-write the file anyway (the edit has
 *   landed), so `block` there would buy an exit code and no protection while
 *   stranding a half-finished edit. The structural signal buys CONFIDENCE IN
 *   THE CLAIM — the report states the missing key as fact — not teeth.
 *
 * FAILS OPEN on every unknown (`cc-artifacts.md` Rule 7): unreadable payload,
 * missing lib, unparseable JSON, or the 5s budget. A docker-hygiene guard that
 * wedges the session is worse than the sprawl it reports.
 *
 * It NEVER shells out to `docker`. Every check is decidable from the compose
 * source or the pending command, so the hook costs no daemon round-trip and
 * behaves identically when the daemon is down.
 */

const path = require("path");

const BUDGET_MS = 5000;
let fallback = null;

function passthrough(note) {
  try {
    if (fallback) clearTimeout(fallback);
    const out = { continue: true };
    if (note) out.systemMessage = note;
    process.stdout.write(JSON.stringify(out) + "\n");
  } catch {
    /* fail open even here */
  }
  process.exit(0);
}

function readPayload() {
  try {
    const raw = require("fs").readFileSync(0, "utf8");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

async function main() {
  fallback = setTimeout(() => passthrough(null), BUDGET_MS);
  if (fallback.unref) fallback.unref();

  const payload = readPayload();
  if (!payload) return passthrough(null);

  let lib;
  try {
    lib = require("./lib/docker-sprawl.js");
  } catch {
    return passthrough(null); // missing lib => fail open, never assert
  }

  const event = payload.hook_event_name || "";
  const input = payload.tool_input || {};
  let findings = [];
  let surface = "";
  let ruleClause = "";

  if (event === "PreToolUse") {
    const cmd = input.command || "";
    findings = lib.inspectDockerRun(cmd);
    surface = "a bare `docker run`";
    ruleClause = "docker-no-sprawl/MUST-2";
  } else {
    const p = input.file_path || input.notebook_path || "";
    if (!lib.isComposeFile(p)) return passthrough(null);
    let text = input.content;
    if (typeof text !== "string") {
      try {
        text = require("fs").readFileSync(p, "utf8");
      } catch {
        return passthrough(null);
      }
    }
    findings = lib.inspectCompose(p, text);
    surface = `compose file ${path.relative(process.cwd(), p) || p}`;
    ruleClause = findings.some((f) => f.check.startsWith("group"))
      ? "docker-no-sprawl/MUST-1"
      : "docker-no-sprawl/MUST-3";
  }

  if (findings.length === 0) return passthrough(null);

  try {
    const { instructAndWait } = require("./lib/instruct-and-wait.js");
    const emitted = instructAndWait({
      hookEvent: event === "PreToolUse" ? "PreToolUse" : "PostToolUse",
      severity: "halt-and-report",
      rule_id: ruleClause,
      what_happened: `${findings.length} docker-sprawl finding(s) on ${surface}.`,
      why:
        "Ungrouped stacks and anonymous volumes are what produced this repo's " +
        "sprawl: 14 of 18 compose files pinned no project name, 18 of 21 " +
        "containers carried no compose label, and 456 orphaned volumes (25.8GB) " +
        "were reclaimed on the day the rule landed.",
      agent_must_report: [
        ...findings.slice(0, 5).map((f) => `[${f.check}] ${f.detail}`),
        `Canonical group for this repo: \`${lib.CANONICAL_GROUP}\`.`,
      ],
    });
    if (fallback) clearTimeout(fallback);
    // instructAndWait RETURNS {json, exitCode}; it does not write stdout.
    // Returning without emitting computes the finding and discards it.
    process.stdout.write(JSON.stringify(emitted.json) + "\n");
    process.exit(emitted.exitCode);
  } catch {
    return passthrough(
      findings.map((f) => `[${f.check}] ${f.detail}`).join("\n"),
    );
  }
}

main().catch(() => passthrough(null));
