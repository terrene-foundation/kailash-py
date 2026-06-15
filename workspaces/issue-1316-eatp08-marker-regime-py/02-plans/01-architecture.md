# Architecture plan — #1316 EATP-08 marker-regime tail (D2c + V6/V7 + §7.1 logging)

Phase-01 output. Decomposition under the autonomous execution model
(`rules/autonomous-execution.md` — sessions, not days; value-anchored shards per
`rules/value-prioritization.md` Rule 2). Value anchor: EATP-08 §4 backward-compat
conformance + cross-SDK parity, the only open actionable py-side item (HIGH, spec-anchored;
user-approved this session).

## Brief corrections (THE GATE before /todos — `rules/agents.md` MUST)

Four parallel deep-dive agents re-derived every brief claim from source. Material
corrections:

1. **Cross-SDK direction inverted — in our favor.** Brief framed parity as a cross-repo
   blocker (rs-canonical). FALSE: kailash-py is the **canonical author**; kailash-rs vendors
   this file (`eatp08-alg-id-canonical.json:7`). V6/V7 byte-pins are derived here
   deterministically. **No cross-repo dependency blocks any shard.**
2. **Compatible-Legacy logging is NOT greenfield.** Brief implied §7.1 logging was unbuilt.
   FALSE: two `logger.info` acceptance lines already ship (`algorithm_id.py:488-498`,
   `:611-621`). Shard 4 shrinks to a level/consolidation decision.
3. **`monotonic-upgrade-violation` is unimplemented** (only a forward-reference docstring,
   `algorithm_id.py:197-198`). V6 sub-case (i) is a NEW ENFORCER, not a vector. Split into
   its own shard with cross-file reach into the record-consumer layer. **This is the one
   genuine scope increase and the one open spec question** (see § Open question).
4. **D2c trusted-verifier-key config must be built** (no existing config; pattern =
   `MultiSigPolicy.signer_public_keys`, `multi_sig.py:170`). Crypto primitives are ready
   (`crypto.py:170`/`:225`).
5. **D2c blast radius is mechanical for callers** — 0 production constructions of
   `D2dWitness`; the 5 wire-decode consumers only forward `witness=`. Behavioral change is
   contained in 2 functions. Invariant count confirmed ~5.

## Design decision (recommended — confirm marker field shape against spec at /todos)

**(a) Verifier-key signed marker — SPEC-BLESSED** (§4.3 explicitly lists "per-verifier
signing keys" as a conformant transport; see `01-analysis/02-spec-locked-facts.md`).
`D2dWitness` grows `first_seen`, `marker_sig`, and an expiry bound; the marker signs
`serialize_for_signing({principal, first_seen})` (NOT `chain_head_date` — corrected per
§4.3.1: `chain_head_date` is the record's CLAIMED value, corroborated AGAINST the signed
`first_seen`, not part of the signed bytes). Verification resolves a configured trusted key
INSIDE the gate. Self-contained, no external infra, full cross-SDK byte parity, not a
one-way door (a transparency log / Foundation witness service can later become the marker
_source_ without changing this verification contract). Options (b)/(c) require external
infrastructure whose existence is unverified — out of scope until a live existence check
confirms an endpoint.

## Shard decomposition (4 shards, ~2 sessions)

### Shard 1 — D2c signed-marker + verifier + §4.3.2 detection (load-bearing crypto)

- `D2dWitness` (`algorithm_id.py:168`) grows `first_seen`, `marker_sig`, expiry/TTL.
- Add trusted-verifier-key config (mirror `signer_public_keys`); resolve inside the gate.
- Extend `assert_d2d_witness_pre_adoption` (`:223`) from 2 → 5 checks (missing · sig-verify ·
  first_seen-corroboration · expiry · monotonic-boundary), all fail-closed →
  `implicit-v1-witness-failure`.
- **Invariants: 5. Call-graph: ≤3 hops (key resolved in-gate). Live pytest loop → feedback
  multiplier.** Tier-2 wiring test through a real `from_dict` consumer (orphan-detection).
- Deps: none. **~1 session.**

### Shard 2 — V6 (ii)+(iii) + V7 vectors + schema `level` field

- Add `level` field to the vector schema; author V6 sub-cases (ii) `missing-alg-id-post-adoption`
  - (iii) `implicit-v1-witness-failure` and V7 Complete-level local-marker-tamper (depends on
    Shard 1's signed marker). Byte-pins derived here.
- Decode-regime tests hand-written, `exc.value.code` assertions (existing style).
- Deps: Shard 1 (V7 + the (iii) marker path). **Small; live test loop.**

### Shard 3 — monotonic-upgrade enforcer (NEW load-bearing logic — SCOPED, spec-locked)

Spec resolves the boundary (§4.1.3 / §4.2 / §4.5.3): the monotonic dimension is "has this
principal-chain previously emitted a registry-form record?" The spec lets that boundary live
in the SAME signed marker (`first_v2_seen`, §4.3.1). So this shard is three pieces, NOT a
separate subsystem:

- **(a) `first_v2_seen` field** on Shard 1's signed marker (inside the signed bytes per
  §4.3.1).
- **(b) write path** — record-consumer layer records first-registry-form emission for a
  principal-chain (the cross-file piece; the verify/record path, e.g. `pact/envelopes.py`
  consumer surface).
- **(c) read check** in resolver dispatch §5.1 step 3 (`algorithm_id.py` /
  `decode_wire_alg_id`): absent-alg-id OR pre-registry-form from a chain with a prior
  registry-form record → `monotonic-upgrade-violation`. Then author the V6 (i) vector.
- Note §4.1.3 also requires the D2a "trust store contains no prior-v2" check, currently
  unenforced — same `first_v2_seen` substrate covers it.
- Deps: Shard 1 (shares the marker store). **~1 session.** Cross-file reach into the
  record-consumer write path is the real surface here.

### Shard 4 — Compatible-Legacy logging §7.1 (observability; small)

- Decide INFO→WARN (degraded-path → WARN per `observability.md` Rule 3); consolidate the two
  existing acceptance logs (`:488`/`:611`) into one helper; guard `principal`/chain-head id
  at DEBUG-or-hashed (Rule 8). Add a migration-tracking counter.
- Deps: touches the same gate as Shard 1 — sequence AFTER Shard 1 to avoid churn. **Small.**

## Open question — RESOLVED (spec read, user-authorized 2026-06-15, journal 0002)

The `monotonic-upgrade-violation` enforcer is now fully scoped against EATP-08 v1.1
§4.1.3/§4.2/§4.3.1/§4.5.3 (`01-analysis/02-spec-locked-facts.md`). All four shards are
spec-locked. The spec authority is the EXTERNAL finalized doc at
`~/repos/terrene/mint/workspaces/envoy-parity/03-drafts/finalized/eatp-08-v1.1.md` (the
v1.1.1 erratum = the already-shipped bare-literal reject); no competing `specs/` is created
in this repo — the EATP-08 doc is the domain truth, mirrored in 02-spec-locked-facts.

**Residual to confirm at /todos** (small): which of the full §5.3 error-code set is already
raised vs new — `pre-registry-form-after-sunset` (2030 D2d sunset) and `alg-id-strip-detected`
may be absent today; confirm by grep before locking Shard 2/3 vector coverage.

## Cross-SDK + repo-scope boundary

Full V6/V7 authoring + byte-pins land here (py is canonical author). The rs vendor-pull is a
downstream `esperie-enterprise/kailash-rs` session — NOT performed from this repo
(`rules/repo-scope-discipline.md`).

## Gate

This plan stops at the `/analyze → /todos` boundary. `/todos` is the human-approval gate
(`rules/autonomous-execution.md` § Structural Gates). Recommended /todos sequence:
**Shard 1 → Shard 4 → Shard 2 → Shard 3** (3 last, pending the spec answer).
