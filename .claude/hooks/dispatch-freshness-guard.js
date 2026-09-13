#!/usr/bin/env node
/**
 * dispatch-freshness-guard.js — surfaces a STALE BASE at the one moment it is still cheap to fix.
 *
 * @hook-event: PreToolUse:Task|Agent (guard) — dispatch is the ONLY correct event. The base every
 *   lane will share is chosen here, once, before the first lane exists; by the time any agent
 *   could look, N agents are already running and the decision is spent. A per-agent check cannot
 *   work because the agent is the wrong OBSERVER, not because it is inattentive: every lane in the
 *   measured incident read its own tree correctly and saw nothing wrong. The matcher is exactly
 *   the delegation-tool set — a `*` matcher would pay a node spawn plus a git probe on every
 *   Read/Bash/Grep to reach an immediate passthrough.
 *
 * NEVER BLOCKS. Advisory is not a weaker choice here, it is the CORRECT one: an old tip commit is
 * genuinely ambiguous — a quiet trunk over a holiday and a tree nobody has fetched produce the
 * identical reading, and only the operator can tell them apart. Blocking every dispatch on an
 * ambiguity is a false-positive machine, and a guard that makes the common case painful gets
 * disabled. What makes advisory SUFFICIENT (where it would not be for an end-of-turn check) is
 * timing: this fires BEFORE the decision it exists to change. `{continue:true}` and exit 0 on
 * every path, including the timeout fallback.
 *
 * NO NETWORK. The predicate reads a remote-tracking ref's tip date and never fetches. A network
 * call in a dispatch-time hook can hang every dispatch. Reading the local ref UNDER-reports and
 * never over-reports — the safe direction for an advisory.
 *
 * THREE STATES, NEVER TWO. Fires / silent / UNDETERMINED. An unanswerable probe is reported as
 * unanswerable, never folded into "proceed" — the two are byte-identical in a passthrough, which
 * is exactly how a guard stops guarding without anyone noticing.
 *
 * CLONE-SAFE, hence committed. Pure local git state: no roster, no signing key, no enrollment, no
 * network. A fresh fork with no `origin/dev` ref is SILENT, not degraded. This is why it belongs
 * in committed settings.json, unlike the six coordination-ENFORCEMENT hooks that must stay in a
 * gitignored settings.local.json because they brick a keyless forker.
 *
 * WRITES NOTHING. No sink, no ledger, no retained prompt text.
 */

"use strict";

// Bounded under the registered timeout so this hook's OWN fallback fires first and emits a
// well-formed passthrough rather than letting the harness kill it mid-write.
const TIMEOUT_MS = 4000;
let fallback = null;

const path = require("node:path");
const PROJECT_DIR = process.env.CLAUDE_PROJECT_DIR || process.cwd();

const { readStdinBounded } = require("./lib/read-stdin-bounded.js");

function passthrough(context) {
  if (fallback) clearTimeout(fallback);
  try {
    const out = { continue: true };
    if (context) {
      out.hookSpecificOutput = {
        hookEventName: "PreToolUse",
        additionalContext: context,
      };
    }
    process.stdout.write(JSON.stringify(out) + "\n");
  } catch {}
  process.exit(0);
}

fallback = setTimeout(() => passthrough(null), TIMEOUT_MS);
if (typeof fallback.unref === "function") fallback.unref();

async function main() {
  let payload;
  try {
    payload = await readStdinBounded();
  } catch {
    return passthrough(null); // Unreadable payload is an UNKNOWN about the CALL, not about git.
  }

  const p = payload && typeof payload === "object" ? payload : {};
  const tool = p.tool_name || p.tool || "";

  let lib;
  try {
    lib = require(path.join(__dirname, "lib", "dispatch-freshness.js"));
  } catch {
    return passthrough(null);
  }

  // The dispatch-tool gate lives in the lib so the mutation suite can remove it and observe a
  // non-dispatch call start firing.
  if (!lib.DELEGATION_TOOLS.includes(tool)) return passthrough(null);

  let result;
  try {
    result = lib.evaluateDispatchFreshness({
      toolName: tool,
      cwd: PROJECT_DIR,
    });
  } catch {
    return passthrough(null);
  }

  if (result.state === lib.SILENT) return passthrough(null);
  return passthrough(lib.renderAdvisory(result));
}

main().catch(() => passthrough(null));
