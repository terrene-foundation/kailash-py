# Proposal — Extend cross-SDK conformance vectors from byte-shape to BEHAVIORAL surfaces

**Status:** DRAFT (2026-07-19) — for methodology-lane routing (loom Gate-1). Authored during the #1720-followup session after verifying the Rust SDK (`@4b357dec`) is at parity/ahead on the security surfaces; the divergence that _did_ occur (kailash-py behind on webhook fail-closed / OIDC nonce+PKCE / Gemini guard) was invisible to the existing vectors.

## Problem (root cause)

"Independent implementations, matching semantics" (EATP D6) is enforced by human memory + reactive per-issue mirroring, not a mechanical gate. Existing cross-SDK vectors pin **static byte-shapes** (`cross_sdk_llm_deployment_presets.rs` + `test-vectors/llm-deployment-presets.json`; `cross_sdk_agent_result`, `cross_sdk_trace_event`; the `kailash-coc-conformer` crate) — preset names, wire kinds, fingerprints. They do **not** pin **behavioral contracts** (request→payload transforms, verdict decisions, guard conditions). So behavioral divergence is caught only reactively as a bug.

## Key insight — the pattern already exists in THIS repo (promote, don't build)

`tests/trust/pact/conformance/vectors/circuit_breaker.json` + `test_bh5_circuit_breaker_conformance.py` already pin **observable state-machine verdicts** (not bytes), including a **fail-closed case via `expect_error`**, with an **exact-set orphan guard**. This is a proven, shipping in-repo behavioral-vector pattern. The proposal is to **promote it from the PACT/trust family to the LLM/auth surfaces** — lower-risk than a net-new suite.

## 1. Behavioral-vector schema

Generalize `circuit_breaker.json`'s `{config, events → expected}` to `{surface, input, expect}`:

```json
{
  "surface": "gemini.build_request_payload",
  "input": {
    "tools": [{ "name": "get_weather" }],
    "response_format": {
      "type": "json_schema",
      "json_schema": { "name": "r", "schema": { "type": "object" } }
    }
  },
  "expect": {
    "payload.tools": "present",
    "payload.generationConfig.responseMimeType": "absent",
    "payload.generationConfig.responseSchema": "absent",
    "signal": "suppression_warn"
  }
}
```

Seed vectors (3 surfaces): **Gemini tools+response_format mutual-exclusion** (above); **webhook signature verdict** (`{payload, secret_state} → accept|reject|error`, incl. the no-secret **fail-closed** case via `expect_error`); **OIDC PKCE/nonce** (`verifier → S256 challenge`; nonce match→accept / mismatch→`expect_error`).

## 2. Runner contract (reuse existing mechanism)

- **Python:** a pytest walk modeled on the shipping BH5 runner — drives the REAL surface (`google_generate_content.build_request_payload`, `WebhookTransport.verify_signature`, `SSOAuthenticationNode` PKCE/nonce), deterministic oracle, exact-set orphan guard.
- **Rust:** via the existing `cross_sdk_*` test pattern + shared walk logic in `kailash-coc-conformer`.
- No net-new suite; the vector JSON is the single source of truth.

## 3. Single-source-of-truth + CI gate

Vendor the canonical vectors (`cross-sdk-inspection.md` Rule 4a) + pin an integrity manifest (Rule 4c `*.sha256`). A fix updates the vector once; the un-fixed SDK's CI goes red until it complies. **Canonical-home is a loom/methodology Gate-1 routing decision** — lean: seed vendored-from-one-BUILD-repo, flag loom-canonical for scaling. (For ratification, not decided here.)

## 4. Anti-rot discipline (teeth)

"New shared behavioral surface ⇒ new vector" MUST (analogous to Rule 4/4a), enforced by two structural teeth: the **exact-set orphan guard** (BH5 pattern) + a **`/redteam` coverage lens**. Land the rule + guard in the SAME change as the seed vectors — vectors without the anti-rot rule rot.

## 5. Scope boundaries

**In:** shared behavioral surfaces (wire-payload shaping, auth verdicts, signature verdicts). **Out:** SDK-internal impl / serialization order, non-shared surfaces, timing, semantic judgments. **Migration:** seed with the 3 surfaces; backfill opportunistically.

## 6. Trade-offs

**Pros:** promotes a proven in-repo pattern (low risk); aligned with D6 (enforces "matching semantics" without coupling code); retires the reactive-mirroring failure class; extends proven infra rather than building.
**Cons (honest):** coverage is the ceiling — an un-vectored shared surface still diverges silently (mitigated by the anti-rot rule + coverage lens); discipline dependency (vectors rot without the rule); upfront cost of the behavioral-runner harness in both SDKs.

## Grounding

`tests/trust/pact/conformance/vectors/circuit_breaker.json` + `test_bh5_circuit_breaker_conformance.py`; Rust `crates/kailash-kaizen/tests/cross_sdk_llm_deployment_presets.rs` + `test-vectors/llm-deployment-presets.json` + `crates/kailash-coc-conformer`; `rules/cross-sdk-inspection.md` Rule 4/4a/4c. Rust-side claims are from this session's read-only recon (`@4b357dec`), not re-verified here.
