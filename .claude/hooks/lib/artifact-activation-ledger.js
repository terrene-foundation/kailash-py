"use strict";

/**
 * artifact-activation-ledger.js — loom#1209 (W1-b, activation-event producer, loom lane).
 *
 * The BEST-EFFORT LOCAL STAGING SINK for the ArtifactActivationEvent stream + the shared
 * emit helpers the producer hooks call. loom EMITS here; the kailash S-3 consumer DRAINS this
 * sink and persists into the DataFlow accountability store (`C-observability-eval.md` §2.5).
 *
 * THIS IS NOT THE STORE. It is a per-session append-only JSONL staging file — the loom side of
 * the producer/consumer seam, exactly analogous to how provenance-ledger.js is the degraded-
 * local half of the loom↔csq provenance seam. loom does NOT build the DataFlow store (the "no
 * coding" charter); it stages events for the engine to ingest.
 *
 * BEST-EFFORT / NEVER-THROWS. Every helper returns a result object and NEVER throws to the
 * caller's halting path — a capture failure degrades observability, it NEVER blocks the session
 * (`hook-output-discipline.md`: an observability hook must fail-open). This mirrors the
 * provenance-ledger contract.
 *
 * DISCLOSURE CONTAINMENT. The sink lives under `.claude/learning/artifact-activation/` — the
 * same per-clone, never-committed operator-correlatable state class as `.claude/learning/`
 * (F40) and the provenance ledger (F101-2). Gitignored; never committed.
 *
 * Origin: loom#1209.
 */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const {
  buildArtifactActivationEvent,
} = require("./artifact-activation-event.js");

/**
 * Per-session sink file. Injective session_id → filename mapping (sanitized token + 8-char
 * sha256 of the raw id), identical to the provenance ledger's fencing: two raw ids that
 * sanitize to the same token still land on distinct files; the charclass strips every path
 * separator so a crafted session_id cannot traverse out of the sink dir.
 */
function _sinkPath(repoDir, session) {
  const hasSession = typeof session === "string" && session.trim().length > 0;
  const safe = hasSession
    ? session.replace(/[^A-Za-z0-9._-]/g, "_")
    : "unknown-session";
  const suffix = hasSession
    ? crypto.createHash("sha256").update(session, "utf8").digest("hex").slice(0, 8)
    : "00000000";
  return path.join(
    repoDir,
    ".claude",
    "learning",
    "artifact-activation",
    `${safe}-${suffix}.jsonl`,
  );
}

/**
 * Emit ONE ArtifactActivationEvent to the local staging sink. Best-effort: returns a result
 * object; NEVER throws.
 *
 * @param {object} a
 * @param {string}  a.repoDir          MAIN-checkout repo dir (caller resolves it)
 * @param {string}  a.artifactType     one of ARTIFACT_TYPES (agent|skill|rule|hook)
 * @param {string}  a.artifactId       the artifact identity
 * @param {?string} a.agentId          dispatching/emitting agent, or null (main agent)
 * @param {string}  a.sessionId        session id
 * @param {string}  a.lifecycleMoment  CLI-neutral moment (session-start|pre-tool-use|…)
 * @param {string}  a.observationTier  observed|availability|self-reported
 * @param {string}  a.nowIso           ISO-8601 timestamp (caller supplies; testable)
 * @returns {{ ok: boolean, event?: object, sinkPath?: string, error?: string }}
 */
function emitArtifactActivation(a) {
  try {
    const repoDir = a.repoDir || process.cwd();
    const event = buildArtifactActivationEvent({
      artifactType: a.artifactType,
      artifactId: a.artifactId,
      agentId: a.agentId === undefined ? null : a.agentId,
      sessionId:
        typeof a.sessionId === "string" && a.sessionId.trim()
          ? a.sessionId
          : "unknown-session",
      timestamp: a.nowIso || new Date().toISOString(),
      lifecycleMoment: a.lifecycleMoment,
      observationTier: a.observationTier,
    });
    const sinkPath = _sinkPath(repoDir, event.session_id);
    fs.mkdirSync(path.dirname(sinkPath), { recursive: true });
    fs.appendFileSync(sinkPath, JSON.stringify(event) + "\n");
    return { ok: true, event, sinkPath };
  } catch (e) {
    return { ok: false, error: e && e.message ? e.message : String(e) };
  }
}

/**
 * Convenience: record a HOOK's own firing (self-report). The reliable, CLI-neutral way to make
 * hook-firing observable is for each hook to report itself at entry — a hook running is a
 * deterministic execution the hook itself can attest. Un-instrumented hooks stay silent (the G2
 * "self-reported" residual: coverage = the set of hooks that call this).
 *
 * @param {object} a  { repoDir, hookName, sessionId, agentId?, nowIso? }
 */
function recordHookFiring(a) {
  return emitArtifactActivation({
    repoDir: a.repoDir,
    artifactType: "hook",
    artifactId: a.hookName,
    agentId: a.agentId === undefined ? null : a.agentId,
    sessionId: a.sessionId,
    lifecycleMoment: a.lifecycleMoment || "pre-tool-use",
    observationTier: "self-reported",
    nowIso: a.nowIso,
  });
}

module.exports = {
  emitArtifactActivation,
  recordHookFiring,
  _sinkPath,
};
