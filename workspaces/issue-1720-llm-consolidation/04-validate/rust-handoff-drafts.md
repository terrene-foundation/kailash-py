# Rust SDK cross-SDK handoff drafts (#1779 + #1727) — FOR REVIEW BEFORE FILING

Scrubbed to the SDK-API surface per `upstream-issue-hygiene.md` (no consumer names,
internal paths, workspace ids, or finding tags). The Rust SDK is referenced by role.
Target repo resolves via the operator's `loom-links.local.json` (`build.rs` key) —
NOT hardcoded. **Not yet filed** — awaiting the journaled grant + operator go-ahead
(operator authorized "both" via the session decision; bodies shown here first).

---

## Draft A — #1727 cross-SDK defect (concrete fix)

**Title:** `fix(kaizen): openai chat four-axis shaper must emit max_completion_tokens for GPT-5 / o-series`

**Labels:** `cross-sdk`

### Affected API

The four-axis kaizen OpenAI chat payload builder (the request-shaping layer that
serializes a completion request for `POST /v1/chat/completions`).

### Summary

The four-axis `openai_chat` shaper emits `max_tokens` unconditionally. OpenAI's
GPT-5 family and the o-series reasoning models reject `max_tokens` with a hard
HTTP 400 (`'max_tokens' is not supported with this model; use
'max_completion_tokens'`) and require `max_completion_tokens`. OpenAI-compatible
third-party providers that share this wire still use `max_tokens`.

### Minimal repro (target behaviour)

A completion request with `model = "gpt-5*"` (or `o1*` / `o3*` / `o4*`) and a
token limit set must serialize the limit under `max_completion_tokens`, not
`max_tokens`; every other model id keeps `max_tokens`.

### Expected vs actual

- **Expected:** the token-limit field name is selected by model family — GPT-5 /
  o-series → `max_completion_tokens`; all other ids → `max_tokens`.
- **Actual:** `max_tokens` is emitted for every model → HTTP 400 on GPT-5/o-series.

### Severity

MEDIUM — a live provider 400 on the GPT-5/o-series path; deterministic.

### Acceptance criteria

- [ ] Model-family field selection (prefixes `gpt-5` / `o1` / `o3` / `o4` →
      `max_completion_tokens`; otherwise `max_tokens`; unknown ids keep
      `max_tokens`).
- [ ] A regression vector asserting the emitted payload key per model family.

### Cross-SDK alignment

Cross-SDK alignment: this is the Rust equivalent of the Python fix already shipped
(the Python four-axis shaper selects the field by model family; verified live
against a GPT-5-class model).

---

## Draft B — #1779 cross-SDK parity verification (posture semantics)

**Title:** `chore(kaizen): verify governance_required posture semantics align cross-SDK (EATP D6)`

**Labels:** `cross-sdk`

### Affected API

The LLM-client / agent construction surface + the `governance_required` posture.

### Summary

The Python SDK has implemented a `governance_required` posture for direct LLM
egress as a PROCESS/ENV posture: resolution is programmatic override →
`KAILASH_GOVERNANCE_REQUIRED` env (truthy `1|true|yes|on`) → default OFF; a bare
un-governed client/agent that would make real egress is refused fail-closed with
a typed error naming both remedies, unless constructed with `ungoverned=True`;
mock/deterministic paths are exempt. This is the Python mirror of the Rust SDK's
per-deployment `governance_required` posture.

Because the Rust posture is per-deployment and the Python posture is process/env,
this is a request to CONFIRM the two are D6-semantically aligned (matching
observable behaviour), or to document the intentional shape difference.

### Expected vs actual

- **Expected (D6 parity):** both SDKs refuse a bare un-governed real-egress
  construction under an active posture with an explicit per-call/`ungoverned`
  opt-out and a mock exemption; resolution precedence is documented on both.
- **Actual:** verify the Rust per-deployment posture exposes an equivalent
  opt-out + fail-closed refusal + mock exemption; note any intentional
  per-deployment-vs-process/env divergence.

### Severity

LOW–MEDIUM — cross-SDK semantic-parity verification (D6); not a runtime defect.

### Acceptance criteria

- [ ] Confirm (or add) an explicit per-call opt-out equivalent to
      `ungoverned=True` on the Rust posture path.
- [ ] Confirm the fail-closed refusal + mock/deterministic exemption match.
- [ ] Document the per-deployment (Rust) vs process/env (Python) resolution
      shape as an intentional, D6-permitted idiomatic difference (or align).
