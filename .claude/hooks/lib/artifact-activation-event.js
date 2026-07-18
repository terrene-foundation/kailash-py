"use strict";

/**
 * artifact-activation-event.js — loom#1209 (W1-b, the S-3 activation-event PRODUCER, loom lane).
 *
 * FORMAT AUTHORITY for the **ArtifactActivationEvent** stream — the SECOND activation stream
 * of the RAG-plugin observability plane (`C-observability-eval.md` §2.5; `B-rag-technique-
 * accountability.md` §3.4). This stream records WHICH loom artifacts (agents / skills / rules /
 * hooks) fired in a session, so a human can later read the per-agent activation heatmap and
 * spot which distilled knowledge the agents actually used.
 *
 * PRODUCER / CONSUMER SPLIT (loom "no coding" charter):
 *   - loom (THIS module + the emit hooks) is the PRODUCER. It DEFINES the event FORMAT and
 *     EMITS events to a best-effort local staging sink. loom does NOT build the store.
 *   - kailash S-3 (a separate BUILD repo, cross-referenced) is the CONSUMER. It persists the
 *     events into the local DataFlow accountability store and renders the heatmap.
 *
 * ┌─────────────────────────────────────────────────────────────────────────────────────────┐
 * │ PENDING S-3 RATIFICATION — `activation_schema_version: 0`.                                 │
 * │ This envelope is a loom-side PROPOSAL. It is NOT an agreed cross-repo contract. Version 0 │
 * │ signals "proposed / not yet frozen": the kailash S-3 consumer models have NOT ratified    │
 * │ this field shape. When S-3 confirms the field set, bump to `1` in a COORDINATED cycle     │
 * │ (loom emitter + kailash consumer conformance together). Until then, no caller may treat   │
 * │ this shape as frozen. See §"S-3 ratification" in the emit-contract proposal doc.          │
 * └─────────────────────────────────────────────────────────────────────────────────────────┘
 *
 * DISTINCT FROM THE FROZEN provenance-event.js (F120 / csq seam, schema_version 1). That schema
 * is a SIGNED, hash-chained governance record csq anchors; it is BYTE-FROZEN and MUST NOT be
 * widened here. The ArtifactActivationEvent is a SEPARATE, lean, UNSIGNED observability event
 * consumed by DataFlow — it deliberately does NOT carry the signing chain (`prev_link`) or the
 * csq operator-signing identity. Two streams, two purposes: provenance = "who authorized this
 * mutation, tamper-evidently"; artifact-activation = "which artifact fired, for the heatmap".
 * Keeping them separate is what lets the live producer ship with NO dependency on the F101-2
 * durable leg (loom#411) — the acceptance criterion "functions with NO F101-2 dependency".
 *
 * CLI-NEUTRAL (`rules/cross-cli-artifact-hygiene.md` MUST-4). The event names the lifecycle
 * MOMENT conceptually (`session-start` / `pre-tool-use` / `post-tool-use` / `session-end`),
 * never one CLI's PascalCase event identifier. The producer binds to whichever runtime event
 * the host CLI fires at that moment; the contract is the neutral moment, not the CC name.
 *
 * Origin: loom#1209 (workspaces/loom-rag-plugin-2026-07-18/06-handoff/issues/loom/
 * 02-in-session-distillation-hooks.md).
 */

// Version 0 = PROPOSED / pending S-3 ratification (see the fenced block above). A frozen,
// S-3-ratified contract is version >= 1, bumped in a coordinated cross-repo cycle.
const ACTIVATION_SCHEMA_VERSION = 0;
const PENDING_S3_RATIFICATION = true;

/**
 * Closed artifact-type taxonomy (`C-observability-eval.md` §2.5). The four in-session artifact
 * classes whose activation the observability plane renders. A free-form type would defeat the
 * per-type heatmap bucketing, so this set is closed — adding a type is a schema change.
 */
const ARTIFACT_TYPES = Object.freeze(["agent", "skill", "rule", "hook"]);

/**
 * CLI-neutral lifecycle moments. NEVER a CC PascalCase event name (`PreToolUse`) — the neutral
 * moment is the contract; the per-CLI event is the implementation (`cross-cli-artifact-hygiene.md`
 * MUST-4). CC pre-tool-use ≈ Gemini `@hooks.tool_use` ≈ Codex `pre-tool`; the event records the
 * MOMENT, so a Gemini/Codex producer emits the identical shape.
 */
const LIFECYCLE_MOMENTS = Object.freeze([
  "session-start",
  "pre-tool-use",
  "post-tool-use",
  "session-end",
]);

/**
 * HOW the activation was observed at the hook layer — the honest observability tier per event
 * (the G2 finding, surfaced IN-BAND so the consumer never over-trusts a weak signal):
 *   - "observed"       : a discrete runtime signal names the artifact firing (a delegation tool
 *                        call for an agent; a Skill tool call for a skill). High confidence.
 *   - "availability"   : the artifact was LOADED / made active this session, but per-application
 *                        "firing" is a semantic act the hook layer does not see (rules). The event
 *                        attests availability at session grain, NOT that the agent applied it.
 *   - "self-reported"  : the artifact reported its OWN firing (a hook calling the emitter). Reliable
 *                        for instrumented artifacts; silent for un-instrumented ones.
 */
const OBSERVATION_TIERS = Object.freeze([
  "observed",
  "availability",
  "self-reported",
]);

// Credential-shaped key names forbidden anywhere in the event (defense-in-depth; the same hygiene
// the provenance schema enforces — an activation event is a durable observability record and must
// not carry secrets). Matches exact credential names + the _secret/_token/… suffix family.
const CREDENTIAL_KEY_RE =
  /^(api_?key|model_?key|access_?key|signing_?key|private_?key|secret|token|password|passwd|credential)$|_(secret|token|password|passwd|credential|key)$/i;
const PROTO_POLLUTION_KEYS = Object.freeze([
  "__proto__",
  "constructor",
  "prototype",
]);

const ISO_8601_RE =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/;

// Top-level event keys in canonical declaration order. Closed shape so a future S-3 conformance
// vector can byte-check it.
const EVENT_KEYS = Object.freeze([
  "activation_schema_version",
  "event_type",
  "artifact_type",
  "artifact_id",
  "agent_id",
  "session_id",
  "timestamp",
  "lifecycle_moment",
  "observation_tier",
  "producer",
]);

function _isNonEmptyString(v) {
  return typeof v === "string" && v.length > 0;
}
function _isPlainObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function _scanForbiddenKeys(value, pathStr, errors) {
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++)
      _scanForbiddenKeys(value[i], `${pathStr}[${i}]`, errors);
    return;
  }
  if (value === null || typeof value !== "object") return;
  for (const k of Object.keys(value)) {
    if (PROTO_POLLUTION_KEYS.includes(k))
      errors.push(`${pathStr}.${k}: prototype-pollution key forbidden`);
    if (CREDENTIAL_KEY_RE.test(k))
      errors.push(
        `${pathStr}.${k}: credential-shaped key forbidden — an activation event is a durable ` +
          `observability record and MUST NOT carry secrets (security.md "no secrets in logs")`,
      );
    _scanForbiddenKeys(value[k], `${pathStr}.${k}`, errors);
  }
}

/**
 * Validate an ArtifactActivationEvent against the PROPOSED (v0) contract.
 * @returns {{ ok: boolean, errors: string[] }}
 */
function validateArtifactActivationEvent(evt) {
  const errors = [];
  if (!_isPlainObject(evt))
    return { ok: false, errors: ["event MUST be a plain object"] };

  if (evt.activation_schema_version !== ACTIVATION_SCHEMA_VERSION)
    errors.push(
      `activation_schema_version MUST be ${ACTIVATION_SCHEMA_VERSION} (proposed/pending-S3) ` +
        `(got ${JSON.stringify(evt.activation_schema_version)})`,
    );
  if (evt.event_type !== "ArtifactActivationEvent")
    errors.push(
      `event_type MUST be "ArtifactActivationEvent" (got ${JSON.stringify(evt.event_type)})`,
    );
  if (!ARTIFACT_TYPES.includes(evt.artifact_type))
    errors.push(
      `artifact_type MUST be one of ${JSON.stringify(ARTIFACT_TYPES)} (got ${JSON.stringify(evt.artifact_type)})`,
    );
  if (!_isNonEmptyString(evt.artifact_id))
    errors.push("artifact_id MUST be a non-empty string (the artifact identity)");
  // agent_id: the dispatching/emitting agent. null = the main agent (no subagent attribution),
  // which is a legitimate, common case — a top-level artifact activation.
  if (evt.agent_id !== null && !_isNonEmptyString(evt.agent_id))
    errors.push("agent_id MUST be a non-empty string or null (null = main agent)");
  if (!_isNonEmptyString(evt.session_id))
    errors.push("session_id MUST be a non-empty string");
  if (!_isNonEmptyString(evt.timestamp) || !ISO_8601_RE.test(evt.timestamp))
    errors.push("timestamp MUST be an ISO-8601 string");
  if (!LIFECYCLE_MOMENTS.includes(evt.lifecycle_moment))
    errors.push(
      `lifecycle_moment MUST be one of ${JSON.stringify(LIFECYCLE_MOMENTS)} ` +
        `(CLI-neutral moment, never a CC event name) (got ${JSON.stringify(evt.lifecycle_moment)})`,
    );
  if (!OBSERVATION_TIERS.includes(evt.observation_tier))
    errors.push(
      `observation_tier MUST be one of ${JSON.stringify(OBSERVATION_TIERS)} (got ${JSON.stringify(evt.observation_tier)})`,
    );
  if (evt.producer !== "loom")
    errors.push(`producer MUST be "loom" (got ${JSON.stringify(evt.producer)})`);

  _scanForbiddenKeys(evt, "event", errors);

  for (const k of Object.keys(evt))
    if (!EVENT_KEYS.includes(k))
      errors.push(`unexpected top-level key '${k}' (closed event shape)`);

  return { ok: errors.length === 0, errors };
}

/**
 * Build a canonical ArtifactActivationEvent. Throws on invalid input (fail-loud — a malformed
 * event must never reach the sink). Time-source-agnostic (caller supplies `timestamp`) so it
 * stays deterministic + testable.
 *
 * @param {object} a
 * @param {string}  a.artifactType     one of ARTIFACT_TYPES
 * @param {string}  a.artifactId       the artifact identity (agent name / skill name / rule id / hook name)
 * @param {?string} a.agentId          dispatching/emitting agent, or null for the main agent
 * @param {string}  a.sessionId        session id
 * @param {string}  a.timestamp        ISO-8601
 * @param {string}  a.lifecycleMoment  one of LIFECYCLE_MOMENTS (CLI-neutral)
 * @param {string}  a.observationTier  one of OBSERVATION_TIERS
 * @returns {Readonly<object>}
 */
function buildArtifactActivationEvent(a) {
  if (!_isPlainObject(a))
    throw new TypeError("buildArtifactActivationEvent: args MUST be a plain object");
  const evt = {
    activation_schema_version: ACTIVATION_SCHEMA_VERSION,
    event_type: "ArtifactActivationEvent",
    artifact_type: a.artifactType,
    artifact_id: a.artifactId,
    agent_id: a.agentId === undefined ? null : a.agentId,
    session_id: a.sessionId,
    timestamp: a.timestamp,
    lifecycle_moment: a.lifecycleMoment,
    observation_tier: a.observationTier,
    producer: "loom",
  };
  const { ok, errors } = validateArtifactActivationEvent(evt);
  if (!ok)
    throw new Error(
      `buildArtifactActivationEvent: invalid event:\n  - ${errors.join("\n  - ")}`,
    );
  return Object.freeze(evt);
}

/**
 * The self-describing contract descriptor — what a consumer (kailash S-3) reads to learn the
 * PROPOSED field shape + ratification status WITHOUT importing loom code. This is the machine-
 * readable half of the emit-contract proposal.
 */
function contractDescriptor() {
  return Object.freeze({
    event_type: "ArtifactActivationEvent",
    activation_schema_version: ACTIVATION_SCHEMA_VERSION,
    pending_s3_ratification: PENDING_S3_RATIFICATION,
    producer: "loom",
    consumer: "kailash S-3 (DataFlow accountability store)",
    core_fields: ["artifact_type", "artifact_id", "agent_id", "session_id", "timestamp"],
    envelope_fields: [
      "activation_schema_version",
      "event_type",
      "lifecycle_moment",
      "observation_tier",
      "producer",
    ],
    artifact_types: ARTIFACT_TYPES.slice(),
    lifecycle_moments: LIFECYCLE_MOMENTS.slice(),
    observation_tiers: OBSERVATION_TIERS.slice(),
  });
}

module.exports = {
  ACTIVATION_SCHEMA_VERSION,
  PENDING_S3_RATIFICATION,
  ARTIFACT_TYPES,
  LIFECYCLE_MOMENTS,
  OBSERVATION_TIERS,
  EVENT_KEYS,
  validateArtifactActivationEvent,
  buildArtifactActivationEvent,
  contractDescriptor,
};
