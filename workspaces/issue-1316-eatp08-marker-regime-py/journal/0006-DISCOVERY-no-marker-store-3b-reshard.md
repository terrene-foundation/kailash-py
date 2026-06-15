---
type: DISCOVERY
date: 2026-06-15
author: agent
project: issue-1316-eatp08-marker-regime-py
topic: No marker store exists — D2c is signed-not-remembered; Shard 3B (write-path) re-sharded out of scope, 3A delivers monotonic enforcement
phase: implement
tags: [eatp-08, shard-3a, shard-3b, m3, monotonic, re-shard, chokepoint]
relates_to: 0003-DECISION-todos-scope-and-redteam-revisions
---

# 0006 — DISCOVERY: no marker store; 3B re-shard (M3 chokepoint pin)

The /todos red-team M3 trap mandated pinning the Shard 3B write chokepoint BEFORE
writing code, and STOP+re-shard if the write spans >1 module / no single
chokepoint exists. Fresh-session chokepoint analysis (read-only grep) resolves it.

## Findings (evidence)

1. **One read chokepoint, not five.** Every EATP-08 alg-id consumer routes its
   decode through the single `decode_wire_alg_id()` function. Production call
   sites (`grep "decode_wire_alg_id("`): `signing/timestamping.py:168,282`,
   `signing/crl.py:189`, `messaging/envelope.py:307`, `pact/envelopes.py:1384`
   — **4 modules / 5 sites**, all calling the one chokepoint. So Shard 3A's
   read-check centralizes in `decode_wire_alg_id` (one place); the 5 consumer
   `from_dict` methods just forward the signal, exactly as they already forward
   `verifier_keys`.

2. **vault/backup is a FALSE consumer.** The session-notes listed `vault/backup`
   as the 5th wire-decode consumer. `vault/registry_ops.py`/`dispatch.py` use
   `alg_id` as a SLIP-0039 _deployment_ algorithm id riding `event_payload.alg_id`
   — a different concept entirely, NOT the EATP-08 top-level `alg_id` / `D2dWitness`
   surface. It does not call `decode_wire_alg_id` and is out of #1316's blast radius.

3. **No marker store exists.** There is no `MarkerStore` / `first_v2_seen` /
   per-chain v2-emission persistence anywhere in `src/` or `packages/`
   (`grep -i "marker_store|first_v2_seen|witness_store"` → only unrelated kaizen
   memory hits). The D2c design is deliberately **signed-not-remembered**: the
   `witness` + `verifier_keys` are CALLER-SUPPLIED kwargs to each `from_dict`
   (confirmed `crl.py:160-189`), never resolved from a persistent store. §4.3
   already declares the marker transport "implementation-defined".

## Disposition (scope decision — surfaced, not silently dropped)

**Shard 3B as planned ("record first-v2 emission into the marker store") is NOT
implementable within #1316 and SHOULD NOT be built.** Writing a persistent
first-v2 store is a new subsystem (state, file-locking per
`trust-plane-security.md`, concurrency, retention) — far beyond the
marker-regime-tail scope, and §4.3 explicitly leaves marker transport to the
verifier integration.

**What #1316 needs is the monotonic READ enforcement (Shard 3A):** the §4.2 /
§4.5.3 / §5.1-step-3 check at the decode chokepoint, consuming a verifier-supplied
prior-v2 signal. Shard 3A delivers:

- `first_v2_seen: Optional[datetime]` signed field on `D2dWitness` (the §4.3.1
  "boundary MAY live in the signed marker" — conditionally inside the signed core,
  backward-compatible: markers without it keep signing `{principal, first_seen}`).
- `prior_registry_form_seen: bool` param on `decode_wire_alg_id` + `from_dict`
  (the Shard-2 V6(i) xfail contract), threaded through the 5 consumer `from_dict`
  sites. Signal = explicit bool OR a resolved marker carrying `first_v2_seen`.
- Read-check: an absent-alg-id OR pre-registry-form record from a prior-v2 chain
  → `monotonic-upgrade-violation`, taking precedence over D2a/D2d acceptance and
  over `missing-alg-id-post-adoption` (§5.1 step 3 / §4.5.3).

**V6(i) acceptance is met by 3A's read-check alone** — the conformance vector
supplies a prior-v2 signal and asserts the rejection; no write path is required
for the vector to pass. The WRITE side (who SETS the signal in production) is
verifier-integration, documented as out-of-#1316 in `specs/trust-crypto.md`.

Net: the 4-shard Wave-2 tail collapses to **3A (monotonic read) + Shard 5 (e2e
regression)**; Shard 3B is closed as "no store to write to — verifier-integration
concern, out of scope" with the rationale pinned in the spec.

## For Discussion

1. **Counterfactual:** if a future verifier DID maintain a persistent first-v2
   store, would the `prior_registry_form_seen` bool + signed `first_v2_seen` marker
   contract still be the right seam — i.e., is the read-check API stable under a
   later store landing, or would it want to resolve the marker internally?
2. **Data-referenced:** §4.5.3 says "once a registry-form record appears in the
   chain, the pre-registry form is rejected with monotonic-upgrade-violation." With
   no store, the verifier must supply `prior_registry_form_seen` truthfully — does
   leaving that to the integrator weaken the anti-downgrade guarantee V6 depends on,
   versus a (deferred) store that the SDK owns?
3. Is closing 3B as out-of-scope (vs filing a follow-up issue for an SDK-owned
   first-v2 store) the right disposition for the cross-SDK parity bar, given
   kailash-rs ISS-33 vendors the same vectors?
