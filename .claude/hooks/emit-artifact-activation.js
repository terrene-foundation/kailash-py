#!/usr/bin/env node
/**
 * emit-artifact-activation.js — loom#1209 (W1-b, the S-3 activation-event PRODUCER, loom lane).
 *
 * PRODUCER of the ArtifactActivationEvent stream at the **pre-tool-use** lifecycle moment
 * (CLI-neutral; CC PreToolUse ≈ Gemini `@hooks.tool_use` ≈ Codex `pre-tool`). It inspects the
 * about-to-run tool call and, when that call IS an artifact activation, emits an event naming
 * the artifact TYPE + identity to the local staging sink (artifact-activation-ledger.js) for
 * the kailash S-3 consumer to drain (`C-observability-eval.md` §2.5).
 *
 * WHAT THIS MOMENT OBSERVES (the G2 finding, in code — see the investigation doc for the full
 * per-type evidence):
 *   - AGENT (subagent dispatch)  → OBSERVED. A delegation tool call names the dispatched agent
 *                                  in `tool_input.subagent_type`. High-confidence discrete signal.
 *   - SKILL (skill consultation) → PARTIAL. A Skill TOOL call names the skill in
 *                                  `tool_input.{skill|name|command}`. This captures skills the
 *                                  agent invokes VIA the skill tool; it does NOT capture a skill
 *                                  whose guidance is consulted SEMANTICALLY from its already-loaded
 *                                  description (no discrete tool call). The Skill-tool call is the
 *                                  recommended fallback signal; the semantic residual is documented.
 *   - RULE / HOOK                → NOT at this moment. Rule application is semantic (no tool call);
 *                                  hook firing is self-reported. Both are handled by the session-
 *                                  start producer + the recordHookFiring self-report helper.
 *
 * Severity: NEVER blocks. `{continue:true}` on every path. This is an observability emitter, not
 * a guard (`hook-output-discipline.md`: fail-open). It emits at pre-tool-use so the record is
 * DETERMINISTIC (the model cannot route around it), exactly like provenance-capture-tool.js.
 *
 * NO F101-2 DEPENDENCY. This producer writes ONLY to the artifact-activation staging sink via
 * artifact-activation-ledger.js. It does NOT touch the provenance ledger, the csq seam, or the
 * F101-2 durable leg (loom#411). The live activation surface ships independent of the durable
 * leg — the acceptance criterion "functions with NO F101-2 dependency".
 *
 * Test env overrides: COC_TEST_FINGERPRINT / COC_TEST_PERSON_ID (identity short-circuit, unused
 * here — activation events carry agent_id, not signing identity — but accepted for parity).
 *
 * Origin: loom#1209.
 */

"use strict";

const TIMEOUT_MS = 5000;
let fallback = null;

const path = require("path");
const PROJECT_DIR = process.env.CLAUDE_PROJECT_DIR || process.cwd();

const { readStdinBounded } = require("./lib/read-stdin-bounded.js");

// Cross-CLI delegation tool vocabulary — a subagent dispatch. CC names it `Agent`
// (current harness) or `Task` (vanilla alias); accept both (same legacy-tolerant pattern as
// provenance-capture-tool.js::DELEGATION_TOOLS). Gemini `@agent` / Codex inline-cat injection
// fire different lifecycle surfaces (no tool call here) — deferred, documented in the G2 finding.
const DELEGATION_TOOLS = new Set(["Task", "Agent"]);
// The skill-invocation tool. CC exposes skill invocations as the `Skill` tool (evidenced by the
// PreToolUse(Skill) matcher registered on analyze-completeness-guard.js).
const SKILL_TOOLS = new Set(["Skill"]);

function passthrough() {
  if (fallback) clearTimeout(fallback);
  try {
    process.stdout.write(JSON.stringify({ continue: true }) + "\n");
  } catch {}
  process.exit(0);
}

function resolveMainCheckoutSafely(repoDir) {
  try {
    const { resolveMainCheckout } = require(
      path.join(__dirname, "lib", "state-resolver.js"),
    );
    return resolveMainCheckout(repoDir);
  } catch {
    return repoDir;
  }
}

/**
 * Normalize a Skill invocation's name → the skill identity. Mirrors
 * analyze-completeness-guard.js::skillNameOf: strip leading `/`, lowercase, first token.
 * `/todos foo` → `todos`.
 */
function skillNameOf(toolInput) {
  const ti = toolInput || {};
  const raw = ti.skill || ti.name || ti.command || "";
  return String(raw).trim().replace(/^\//, "").toLowerCase().split(/[\s/]+/)[0];
}

/**
 * Classify a tool call into an artifact activation, or null (not an artifact activation).
 * Pure function of (tool name, tool_input) — no IO, fully testable.
 *
 * @returns {{ artifactType, artifactId, observationTier } | null}
 */
function classifyActivation(tool, toolInput) {
  const ti = toolInput && typeof toolInput === "object" ? toolInput : {};

  if (DELEGATION_TOOLS.has(tool)) {
    // AGENT activation — OBSERVED. The dispatched agent identity is tool_input.subagent_type.
    const id =
      typeof ti.subagent_type === "string" && ti.subagent_type
        ? ti.subagent_type
        : null;
    if (!id) return null; // a delegation with no named subagent carries no artifact identity
    return { artifactType: "agent", artifactId: id, observationTier: "observed" };
  }

  if (SKILL_TOOLS.has(tool)) {
    // SKILL activation — PARTIAL. Names the skill invoked via the skill tool. (Semantic
    // consultation of an already-loaded skill is NOT observable here — the G2 residual.)
    const id = skillNameOf(ti);
    if (!id) return null;
    return { artifactType: "skill", artifactId: id, observationTier: "observed" };
  }

  // Any other tool (Read/Write/Bash/Grep/…) is NOT an artifact activation — it is a plain tool
  // call, covered by the separate provenance stream. No artifact-activation event.
  return null;
}

async function main() {
  fallback = setTimeout(() => {
    try {
      process.stdout.write(JSON.stringify({ continue: true }) + "\n");
    } catch {}
    process.exit(1);
  }, TIMEOUT_MS);
  try {
    const payload = await readStdinBounded();
    const tool = payload.tool_name || payload.tool || "";
    const classified = classifyActivation(tool, payload.tool_input);
    if (!classified) {
      passthrough();
      return;
    }

    // Attribute the EMITTING agent: CC populates top-level `agent_id` ONLY when the call
    // originates inside a subagent (empirically confirmed — provenance-capture-tool.js §#448).
    // For a main-agent call it is absent → null. This is the DISPATCHING agent, distinct from
    // the dispatched artifact_id.
    const agentId =
      typeof payload.agent_id === "string" && payload.agent_id
        ? payload.agent_id
        : null;
    const session = payload.session_id || "unknown-session";
    const mainCheckout = resolveMainCheckoutSafely(PROJECT_DIR);

    try {
      const { emitArtifactActivation } = require(
        path.join(__dirname, "lib", "artifact-activation-ledger.js"),
      );
      const r = emitArtifactActivation({
        repoDir: mainCheckout,
        artifactType: classified.artifactType,
        artifactId: classified.artifactId,
        agentId,
        sessionId: session,
        lifecycleMoment: "pre-tool-use",
        observationTier: classified.observationTier,
        nowIso: new Date().toISOString(),
      });
      // Observability: a dropped activation event leaves a stderr breadcrumb, never blocks
      // (stderr does not touch the {continue:true} stdout payload).
      if (r && r.ok === false) {
        try {
          process.stderr.write(
            `artifact-activation.emit.dropped type=${classified.artifactType} reason=${String(
              r.error,
            ).slice(0, 120)}\n`,
          );
        } catch {}
      }
    } catch {
      // Best-effort: emit failure degrades observability, never blocks the tool.
    }

    passthrough();
  } catch {
    passthrough();
  }
}

// Run main() ONLY when invoked as a hook — NOT when required for testing classifyActivation().
if (require.main === module) {
  main();
}

module.exports = { classifyActivation, skillNameOf, DELEGATION_TOOLS, SKILL_TOOLS };
