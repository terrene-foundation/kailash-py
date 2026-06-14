# Cluster D — §4.5 Audit Envelope + §5 Rotation

Conformance-gap analysis for EATP-12 v1.0 Trust Vault Key-Binding, cluster D
(§4.5 audit envelope N12-AU-01..04a + §5 rotation N12-RT-01..06), verified
against the shipped `kailash-py` source as of this analysis. Read-only; no
source edited.

**Verification method:** every current-state claim below was produced by a
literal `grep`/`sed`/`ls` against the working tree (per `spec-accuracy.md`
MUST-1). Where a grep returned empty, that is stated explicitly as ABSENT.

**Bottom line:** the cluster is **PARTIAL**. The cryptographic + audit-chain
_substrate_ (canonical pre-image, closed event-type enum, `EXTERNAL_SIDE_EFFECT`

- subtype migration pattern, gradient-keyed dispatcher, PACT `AuditAnchor` with
  hash-chain `seal()`, `PostureStore` + `SUPERVISED`, `shamir.rotate_holders`)
  all exists and is directly reusable. But **every named-tier + receipt + vault-
  subtype + canonical-payload-schema + trust-anchored-time + generation-counter
  surface is net-new** — none of it ships today. The spec already discloses this
  honestly (F-SUBSTRATE-1/-2, Ruling 2) and sanctions a binding ADAPTER onto the
  shipped surface. The adapter is feasible and is the key architecture decision
  for this cluster; assessment in §2 below.

---

## Requirement table

| Normative ID   | Requirement (1-line)                                                                                                                                                                                                                                                            | Current state                                                                                                                                                                                                                                            | Evidence (file:line)                                                                                                                                                                        | Net-new work                                                                                                                                                                                                                                         |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **N12-AU-01**  | Outcome anchor on gated invocation; distinct denial anchor on clearance reject; two explicit schemas; denial-flood → `vault_denial_summary`; outcome→`recovery`, denial/summary→`safety`                                                                                        | **ABSENT** (no vault-binding layer; no recovery/safety tiers; no denial/summary subtypes)                                                                                                                                                                | `trust/pact/audit.py:475` dispatcher keys on `VerificationLevel` only; recovery/safety grep EMPTY                                                                                           | Binding emit-path that classifies outcome vs denial + flood coalescer; the two payload schemas; tier routing via adapter                                                                                                                             |
| **N12-AU-01a** | Anchor is a well-formed EATP Audit Anchor (Element 5): `transaction_id`, `lineage_hash`, `outcome`, `log_ref`, in-tier `previous_anchor_hash`; chains within dispatch tier                                                                                                      | **PARTIAL** — shipped `AuditAnchor` chains (`previous_hash`+`content_hash`) but carries `anchor_id/sequence/agent_id/action/verification_level/envelope_id/result/metadata/timestamp`, NOT `transaction_id`/`lineage_hash`/`outcome`/`log_ref`           | `trust/pact/audit.py:134` (`AuditAnchor.__slots__`), `:195` `compute_hash`, `:225` `seal`                                                                                                   | Map EATP Audit-Anchor Element-5 fields onto/into the anchor (adapter shapes a delegate-side `AuditChainEntry` or carries them in `event_payload`); bind `lineage_hash` over `vault_id`+`kek_generation` (outcome) / principal+opaque-handle (denial) |
| **N12-AU-02**  | Dispatcher-mediated via `AuditDispatcher.dispatch(anchor, tier=...)` (N9-D-01); direct store-write non-conforming; signed under current `alg_id` carried as `event_payload.alg_id`; recovery-tier; Complete needs witness                                                       | **ABSENT** named-tier dispatcher / `tier=` param / `alg_id` slot. Shipped `dispatch(anchor, level)` keys on gradient. Pre-image `content_signing_bytes(event_type,event_payload,signer_delegate_id)` has NO top-level `alg_id` slot (confirms F-AUDIT-8) | `trust/pact/audit.py:520` `def dispatch(self, anchor, level)`; `delegate/audit.py:79` `content_signing_bytes(...)`, `:362` `signer_delegate_id`                                             | Binding adapter mapping recovery-tier enrollment + `DispatchReceipt` onto gradient `dispatch`; `alg_id` rides `event_payload` pinned-first                                                                                                           |
| **N12-AU-02a** | Recovery-tier dispatch-acceptance interlock — sealed tier MUST still accept `dispatch()` of vault anchors (seal blocks rotate/compact, not append); `safety` extended (bounded-degradation, retryable)                                                                          | **ABSENT** (no sealed recovery tier; no seal/rotate/compact semantics on shipped dispatcher; `seal()` here is per-anchor content-hash, NOT tier-seal)                                                                                                    | `trust/pact/audit.py:225` `AuditAnchor.seal` (per-anchor hash, not tier); no tier `rotate`/`compact`                                                                                        | Adapter-level invariant that the recovery/safety tier accepts vault appends despite seal; depends on EATP-09 §3.4 semantics the substrate lacks                                                                                                      |
| **N12-AU-02b** | Audit is precondition for KEK going active (fail-closed ordering); no active handle / shards until `DispatchReceipt` returned; audit-outage = retryable, not brick                                                                                                              | **ABSENT** — `dispatch` returns `None` (no receipt); no vault backup/restore surface to order against                                                                                                                                                    | `trust/pact/audit.py:520-595` (`dispatch` returns `None`); `trust/vault/backup.py` (3 KB; no dispatch-gated restore)                                                                        | Receipt-returning adapter + fail-closed ordering in the (net-new) `back_up_vault_key`/`restore_vault_key` binding                                                                                                                                    |
| **N12-AU-03**  | Map vault events onto closed `DelegateEventType` via `EXTERNAL_SIDE_EFFECT` + `event_payload["subtype"]`; reserve disjoint `vault_` prefix; binding (not engine) validates subtype                                                                                              | **PRESENT (substrate) / ABSENT (vault use)** — closed 5-variant M4 enum + `EXTERNAL_SIDE_EFFECT` + documented subtype migration pattern all exist; engine validates `event_type` only, NOT subtype (matches spec)                                        | `delegate/audit.py:207` `DelegateEventType`, `:222` subtype migration map, `:249` `EXTERNAL_SIDE_EFFECT`, `:888` `emit_event` validates `event_type not in _AUDIT_VISIBLE_EVENT_TYPES` only | Binding-side subtype validator over the closed `vault_*` set (10 subtypes); reserve `vault_` disjoint from shipped `{dispatch_invocation,cascade_emission,lifecycle_transition,posture_ratchet,sovereign_handover}` (all present at `:228-236`)      |
| **N12-AU-04**  | Pinned per-subtype canonical `event_payload` schema (10 subtypes) + golden fixture; shared encodings; two-state `timestamp`+`time_attested`                                                                                                                                     | **ABSENT** — no vault payload schemas; canonical encoder `canonical_json_dumps` (RFC 8785/JCS) EXISTS and is reusable                                                                                                                                    | `delegate/audit.py:57` `from kailash.trust._json import canonical_json_dumps`, `:130` used in `content_signing_bytes`                                                                       | All 10 per-subtype schemas as binding code + Appendix B golden-fixture parity test; reuse `canonical_json_dumps` for byte-identical pre-image                                                                                                        |
| **N12-AU-04a** | Trust-anchored timestamps for forced-stale (SG-03) + denylist (SG-05) anchors; `time_attested:false`+`"unverified"` sentinel when unavailable                                                                                                                                   | **ABSENT** — no trust-anchored clock anywhere in `src/kailash/` (broad grep EMPTY)                                                                                                                                                                       | grep `trust_anchored_time\|trusted_time_source\|time_attested\|TrustedTimeSource\|attested_timestamp` over `src/kailash/` → 0 hits                                                          | Net-new trusted-time source binding (EATP-10 §14) + two-state grammar; this is also TEMP-2/TEMP-3 surface                                                                                                                                            |
| **N12-RT-01**  | Holder rotation calls shipped `shamir.rotate_holders(old_shards,new_ritual,*,passphrase=...)`; binding composes, never reimplements; requires `vault:rotate`; new ritual ≥ N12-TH-01 floor                                                                                      | **PRESENT (wrapper) / ABSENT (binding)** — `rotate_holders` exists with exactly the spec'd signature; composes `reconstruct`→`generate`; `del secret` best-effort                                                                                        | `trust/vault/shamir.py:464` `def rotate_holders(old_shards, new_ritual, *, passphrase=b"")`, `:510` `del secret`                                                                            | Binding wrapper adding the `vault:rotate` clearance gate + floor check + audit emit; wrapper itself is reuse-as-is                                                                                                                                   |
| **N12-RT-02**  | Amicable holder rotation writes `vault_holder_rotation` anchor to `recovery` tier (dispatcher-mediated, fail-closed); records old/new `{k,n}`, departing holder, new distribution, `vault_id`, unchanged `kek_generation`, new `shard_commitments`, `for_cause=false`           | **ABSENT** — no vault anchor subtype, no recovery tier, no `vault_id`/`kek_generation`/`shard_commitments` registry                                                                                                                                      | (depends on AU-02/03/04 net-new surfaces above)                                                                                                                                             | Binding audit emit for `vault_holder_rotation` per AU-04 row                                                                                                                                                                                         |
| **N12-RT-03**  | Old-ritual shards no longer reconstruct active set; rejected via `shard_commitments` (N12-CB-03) → `unknown-shard`/`revoked-holder`/`mixed-shard-set`; forced-stale is the sole sanctioned exception                                                                            | **ABSENT** — no `shard_commitments` registry; wrapper emits fresh SLIP-0039 generation (the upstream mechanism the outcome rests on is a library property)                                                                                               | `trust/vault/shamir.py` (wrapper re-shards; no commitments registry)                                                                                                                        | `shard_commitments` foreign-shard gate (cluster C surface) + the forced-stale carve-out wiring                                                                                                                                                       |
| **N12-RT-04**  | Mode A only (single-group full re-shard `group_threshold=1`); Mode B deferred; MUST NOT claim Mode B conformance                                                                                                                                                                | **PRESENT** — wrapper is hard-wired single-group `group_threshold=1, groups=[(m,n)]`                                                                                                                                                                     | `trust/vault/shamir.py:286` `group_threshold=1` (in `generate`, composed by `rotate_holders`); module deliberately single-group                                                             | None — wrapper already enforces; binding just MUST NOT over-claim                                                                                                                                                                                    |
| **N12-RT-05**  | Any KEK-materializing restore triggers D6 by reference (SUPERVISED across 5 dims + 7-day cooling-off via PostureStore); no re-wrap carve-out                                                                                                                                    | **PARTIAL** — `PostureStore` Protocol + `SQLitePostureStore` concrete + `TrustPosture.SUPERVISED` + `emergency_downgrade` all exist; the D6 _trigger wiring from a vault restore_ is ABSENT (no restore surface)                                         | `trust/posture/postures.py:426` `PostureStore` Protocol, `:38` `SUPERVISED`, `:620` `emergency_downgrade`; `trust/posture/posture_store.py:221` `SQLitePostureStore`, `:341` `set_posture`  | Binding restore path drives the D6 write through `PostureStore`; cooling-off needs the (net-new) trust-anchored clock (AU-04a/CL-04)                                                                                                                 |
| **N12-RT-06**  | KEK-rotation advances `kek_generation` g→g+1; emits `vault_kek_rotation` to `recovery` tier with full re-shard distribution + `for_cause`; current generation derivable from signed dispatcher chain, NOT a mutable counter; generation is REQUIRED net-new key-manager surface | **ABSENT** — shipped `KeyMetadata` carries `rotated_from`/`is_revoked`/`is_hardware_backed`, **NO `kek_generation` integer, NO key-class** (confirms F-SUBSTRATE-1)                                                                                      | `trust/key_manager.py:94` `class KeyMetadata` (`:114` `is_hardware_backed`, `:116` `is_revoked`, `:118` `rotated_from`); no `generation`/`key_class` field                                  | `kek_generation` integer + KEK-class metadata extension (kailash-py#630) + `vault_kek_rotation` audit emit + generation-from-chain derivation                                                                                                        |

---

## EATP-09 named-tier dispatcher gap + ADAPTER feasibility assessment

This is the load-bearing architecture decision for cluster D.

### What the shipped `TieredAuditDispatcher` provides

`trust/pact/audit.py:475` ships a `TieredAuditDispatcher` whose `dispatch(anchor,
level)` (`:520`) routes a sealed `AuditAnchor` to one of THREE persistence tiers
keyed on `VerificationLevel` (the PACT verification gradient), NOT EATP-09 named
tiers:

- `HELD`/`BLOCKED` → Tier 3 (synchronous durable + ephemeral) — `:531`
- `FLAGGED` → Tier 2 (session-buffered + ephemeral) — `:567`
- else (`AUTO_APPROVED`) → Tier 1 (ephemeral only)

`dispatch` returns **`None`** (no receipt). The anchor itself (`AuditAnchor`,
`:134`) is a tamper-evident hash-chain record: `seal()` (`:225`) computes a
SHA-256 `content_hash` over a canonical pre-image including `previous_hash`
(`:195` `compute_hash`), so cross-anchor chaining IS present. But the anchor
carries PACT fields (`agent_id`, `action`, `verification_level`, `envelope_id`,
`result`), NOT the EATP Audit-Anchor Element-5 fields (`transaction_id`,
`lineage_hash`, `outcome`, `log_ref`) that N12-AU-01a requires.

### What is missing for recovery/safety named tiers + DispatchReceipt

Verified ABSENT (grep over `src/kailash/trust/` + `src/kailash/delegate/`
returned ZERO hits for `DispatchReceipt`, `"recovery"`/`recovery_tier`,
`"safety"`/`safety_tier`, `class AuditDispatcher`):

1. **No named tiers.** The spec's `recovery` (indefinitely sealed) and `safety`
   (sealed-at-rotation) tiers do not exist; only the 3 gradient tiers do.
2. **No `tier=` parameter.** `dispatch(anchor, level)` — no tier kwarg.
3. **No `DispatchReceipt`.** Return is `None`; N12-AU-02b's fail-closed ordering
   ("no active handle until a receipt is returned") has nothing to receive.
4. **No seal/rotate/compaction tier semantics.** The dispatcher's `seal()` is the
   per-anchor content-hash, not the EATP-09 §3.4 indefinite-seal / rotation-seal
   that AU-02a's interlock guards against. There is no `rotate()`/`compact()` and
   no "further restricts" escape to defend against.
5. **No global anchor.** N9-T-02's cross-tier ordering anchor is absent.

The spec already discloses all of this truthfully: **F-SUBSTRATE-2** (§9.6 line 631) names `AuditDispatcher.dispatch(anchor, tier="recovery")` as a surface the
shipped py lacks ("the only shipped `dispatch()` keys on `VerificationLevel`...
no `tier` parameter, no `recovery` tier, no `seal`, no global anchor"), and
N12-AU-02 explicitly permits "an adapter mapping recovery-tier enrollment +
`DispatchReceipt` onto the shipped gradient-keyed `dispatch(anchor, level)`"
(tracked `kailash-py#630`).

### How hard is the binding adapter?

**Feasibility: tractable, but it is a real adapter — not a thin shim — because
the receipt + fail-closed ordering + EATP-Audit-Anchor shape are all net-new.**
Three layers:

1. **Shape adapter (low effort).** Wrap construction so a vault anchor carries
   the EATP Audit-Anchor Element-5 fields. The cleaner path is to use the
   _delegate-side_ `AuditChainEngine.emit_event` (`delegate/audit.py:825`) with
   `EXTERNAL_SIDE_EFFECT` + `event_payload["subtype"]="vault_*"`, NOT the
   PACT `TieredAuditDispatcher` — because the delegate engine already produces
   the canonical signed pre-image (`content_signing_bytes`, `:79`) the spec's
   N12-AU-03 pre-image is defined over, and already hash-chains entries. The
   PACT dispatcher's tier routing is then a _parallel_ concern. **Open question
   #1 below.**

2. **Tier + receipt adapter (medium effort).** Introduce a binding-owned
   `AuditDispatcher` facade exposing `dispatch(anchor, tier="recovery"|"safety")`
   → `DispatchReceipt`. Internally it (a) emits the chained entry, (b) maps
   `recovery`/`safety` onto a durable tier (gradient `HELD`/`BLOCKED` give
   synchronous-durable semantics — `:531` — which is the right durability class
   for recovery/safety), and (c) returns a populated `DispatchReceipt` so
   N12-AU-02b's fail-closed ordering can gate the KEK going active. The `seal`
   /indefinite-seal semantics (AU-02a) must be _modeled_ by the adapter since the
   substrate has none — the interlock ("accept append despite seal") is satisfied
   trivially because there is no seal to violate, but the adapter MUST document
   that it is providing append-only-not-append-prohibited semantics itself.

3. **Per-tier hash-chain (medium effort).** N12-AU-01a chains within tier
   (`previous_anchor_hash` per recovery/safety). The substrate chains globally
   per `AuditChain`/`AuditChainEngine`; the adapter must maintain a per-tier
   `previous_anchor_hash` so the denial-summary's "chains after the last stored
   safety anchor" guarantee holds. This is the most invariant-heavy part.

**Verdict:** the adapter is feasible and is the correct disposition (the spec
sanctions it). It is NOT a one-liner: it owns the receipt, the fail-closed
ordering hook, the per-tier chain, and the EATP-Audit-Anchor shape. Estimate it
as its OWN shard (load-bearing, ~5 invariants: tier routing, receipt contract,
per-tier chain, fail-closed ordering, append-despite-seal) per the capacity
budget — do not fold it into the emit-path shard.

---

## Reusable substrate (cite REAL file:line)

These ship today and are directly reusable; the binding composes them.

- **Canonical signed pre-image** — `delegate/audit.py:79`
  `content_signing_bytes(event_type, event_payload, signer_delegate_id)`, using
  `canonical_json_dumps` (RFC 8785/JCS) at `:130`. This IS the N12-AU-03
  pre-image; reuse directly for the V6 byte-identical golden fixture.
- **Closed event-type enum + subtype migration pattern** — `delegate/audit.py:207`
  `DelegateEventType` (5 variants), `:249` `EXTERNAL_SIDE_EFFECT`, `:222-236` the
  documented `event_payload["subtype"]` migration map reserving
  `{dispatch_invocation, cascade_emission, lifecycle_transition, posture_ratchet,
sovereign_handover}`. The `vault_` prefix is disjoint from all five.
- **Engine validates event_type only, not subtype** — `delegate/audit.py:888`
  (`if event_type not in _AUDIT_VISIBLE_EVENT_TYPES: raise
AuditChainEmissionError`). `EXTERNAL_SIDE_EFFECT` IS in `_AUDIT_VISIBLE_EVENT_TYPES`
  (`:309-311`), so vault events are retained by the C3 classifier (resolves
  F-AUDIT-7). Confirms the binding (not engine) MUST validate subtype.
- **AuditChainEngine.emit_event + per-entry signed bytes** — `delegate/audit.py:825`
  `emit_event`, `:466` `AuditChainEntry.to_content_signing_bytes`, `:362`
  `signer_delegate_id` (UUID).
- **PACT AuditAnchor hash-chain + seal** — `trust/pact/audit.py:134` `AuditAnchor`,
  `:195` `compute_hash` (SHA-256 over canonical content incl. `previous_hash`),
  `:225` `seal`, `:235`+ `verify_integrity`.
- **Gradient dispatcher (durability tiers)** — `trust/pact/audit.py:475`
  `TieredAuditDispatcher`, `:520` `dispatch`, `:531` synchronous-durable for
  HELD/BLOCKED, `:595` `flush_session`.
- **PostureStore + SUPERVISED + emergency downgrade (D6 substrate)** —
  `trust/posture/postures.py:426` `PostureStore` Protocol, `:38` `SUPERVISED`,
  `:620` `emergency_downgrade`; concrete `trust/posture/posture_store.py:221`
  `SQLitePostureStore`, `:341` `set_posture`, `:369` `record_transition`.
- **shamir.rotate_holders (RT-01)** — `trust/vault/shamir.py:464`
  `rotate_holders(old_shards, new_ritual, *, passphrase=b"")`, composes
  `reconstruct`→`generate`, `:510` best-effort `del secret`. Single-group
  `group_threshold=1` (`:286` in `generate`) satisfies RT-04 Mode A.

## Net-new surfaces (must be built)

Confirmed ABSENT against the working tree:

1. **`vault_*` subtypes (10)** — `vault_key_backup`, `vault_key_restore`,
   `vault_key_restore_forced_stale`, `vault_key_restore_raw`, `vault_kek_rotation`,
   `vault_kek_recommit`, `vault_kek_retire`, `vault_holder_rotation`,
   `vault_key_backup_denied`/`vault_key_restore_denied`, `vault_denial_summary`.
   Plus the binding-side subtype validator over this closed set.
2. **Per-subtype canonical `event_payload` schemas (N12-AU-04)** — the shared
   encodings + per-row required/forbidden field sets + the two-state
   `timestamp`+`time_attested` grammar; plus the Appendix B golden-fixture parity
   test.
3. **Denial-flood summary** — `vault_denial_summary` dispatch-time coalescer
   preserving distinct principals (in-line cap M + `principal_set_root` Merkle
   digest), `O(M)`-bounded, chaining after the last `safety` anchor.
4. **recovery/safety tier routing + `DispatchReceipt`** — the adapter (§2 above).
5. **D6 trigger wiring (RT-05)** — the (net-new) `restore_vault_key` path driving
   `PostureStore` to SUPERVISED across 5 dims + 7-day cooling-off start.
6. **`kek_generation` integer + KEK-class metadata (RT-06/SG-01)** — extend
   `KeyMetadata` (`trust/key_manager.py:94`, which today has NO generation field);
   tracked kailash-py#630.
7. **Trust-anchored clock (AU-04a / TEMP-2 / TEMP-3 / CL-04)** — a trusted-time
   source per EATP-10 §14 with the `time_attested` two-state grammar; ZERO
   trust-anchored-time surface exists in `src/kailash/` today.
8. **The vault binding surface itself** — `back_up_vault_key` / `restore_vault_key`
   / holder-rotation / KEK-rotation entry points (`trust/vault/backup.py` is 3 KB
   today and carries no dispatch-gated restore).

## Key risks / pitfalls (cite §9 findings)

- **F-AUDIT-8 (high, §9.6:629) — `alg_id` has no pre-image slot.** The substrate
  pre-image is `{event_type, event_payload, signer_delegate_id}` (verified
  `delegate/audit.py:79`); there is no top-level `alg_id`. The binding MUST carry
  `alg_id` as a fixed `event_payload.alg_id` pinned first (N12-AU-02). Do NOT try
  to add a top-level `alg_id` to the substrate pre-image — it would break the
  cross-SDK byte-identical contract.
- **F-AUDIT-9 (high, §9.6:643) — denial vs outcome payloads are DIFFERENT schemas.**
  A denial anchor has NO resolved `vault_id`/`kek_generation`/commitments (those
  values don't exist before handle/shard resolution). Do not null-fill —
  explicitly OMIT, or the canonical pre-image is non-deterministic. Denial
  `lineage_hash` binds principal + opaque `target_handle_ref` instead.
- **F-AUDIT-10 (high, §9.6:644) — denial flood into the sealed recovery tier is a
  seal-flood DoS.** Denials + summary route to `safety` (not `recovery`); denials
  MUST NOT be dropped (the earlier F-BND-8 rate-limit-drop knob is struck). The
  summary is DISPATCH-TIME aggregation (one record in place of N), NOT post-hoc
  EATP-09 §4.1 compaction — getting this distinction wrong re-opens F-BND-8.
- **F-AUDIT-3 (high, §9.3:591) — unauthorized probing must be audited.** Outcome
  anchors are scoped to "passes the clearance gate"; rejections get distinct
  denial anchors. A binding that only audits successes leaves the probing trail
  invisible.
- **F-BND-3 (high, §9.5:613) — no D6 re-wrap carve-out.** ANY KEK-materializing
  restore triggers D6 (N12-RT-05). The first-draft "re-wrap only dodges D6"
  carve-out is removed; do not re-introduce it as an optimization.
- **F-TEMP-2 / F-TEMP-3 (medium, §9.6:641-642) — local clock is forgeable.** The
  cooling-off window (CL-04) and the forced-stale/denylist anchor timestamps
  (AU-04a) MUST bind to the EATP-10 §14 trust-anchored clock, fail-closed
  `"unverified"` when unavailable. The substrate has ZERO trust-anchored time
  today — this is genuinely greenfield and is itself an existence-check risk:
  EATP-10 §14 must actually ship a usable surface, else AU-04a/CL-04 degrade to
  `time_attested:false` permanently.
- **F-SUBSTRATE-1 / F-SUBSTRATE-2 (high, Ruling 2, §9.6:630-631) — net-new
  surfaces, not weakened requirements.** The `kek_generation` counter and the
  named-tier dispatcher are REQUIRED net-new; the spec's disposition is truthful
  re-wording + adapter, NOT requirement reversal. The binding MUST NOT silently
  treat "substrate lacks it" as "requirement optional."

## Open questions for architecture

1. **Which substrate carries the vault anchor — delegate `AuditChainEngine` or
   PACT `TieredAuditDispatcher`?** The delegate engine produces the exact
   N12-AU-03 signed pre-image (`content_signing_bytes`) and chains entries; the
   PACT dispatcher provides durability-tier routing but a PACT-shaped anchor.
   Recommendation to validate in cluster integration: emit via the **delegate
   engine** (correct pre-image + chain + subtype pattern) and have the
   binding-owned `AuditDispatcher` adapter own tier routing + receipt separately.
   This avoids reshaping the PACT `AuditAnchor` to carry `lineage_hash`/`log_ref`.
2. **Does the per-tier `previous_anchor_hash` (N12-AU-01a) require a persisted
   per-tier chain head, or can it be derived from the durable store at dispatch
   time?** The denial-summary's "chains after the last stored safety anchor"
   guarantee needs a reliable per-tier tail; the substrate chains globally.
3. **What is the `DispatchReceipt` contract** (fields, durability guarantee)?
   N12-AU-02b gates the KEK going active on it — it must prove durable enrollment,
   not just in-memory append. Define before the backup/restore shard.
4. **Does EATP-10 §14 actually expose a usable trust-anchored time source in any
   shipped SDK,** or is it net-new everywhere? If net-new, AU-04a/CL-04 carry a
   permanent-degradation risk until it lands; confirm via existence-check before
   committing to the attested path as the default.
5. **Is the `kek_generation` + KEK-class `KeyMetadata` extension in scope for THIS
   binding or deferred to kailash-py#630 first?** RT-06/SG-01 depend on it; the
   stale-generation guard (cluster, §6) is unbuildable without it. Sequencing
   decision: #630 likely blocks the rotation + stale-guard shards.
