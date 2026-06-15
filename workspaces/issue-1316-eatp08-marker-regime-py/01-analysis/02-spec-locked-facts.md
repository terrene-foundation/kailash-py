# 02 — Spec-locked normative facts (EATP-08 v1.1, §4.3/§4.5/§5/§6)

Source (user-authorized cross-repo read, journal 0002):
`~/repos/terrene/mint/workspaces/envoy-parity/03-drafts/finalized/eatp-08-v1.1.md`.
Verbatim normative pins below resolve the Shard-3 open question and correct Shard 1's
marker payload.

## §4.3.1 Witnessed-marker contents (normative) — Shard 1 field shape

REQUIRED signed core (`:195-205`):

```json
{
  "principal": "<principal_chain_id>",
  "first_seen": "<RFC-3339-Z first-contact/adoption boundary>",
  "marker_sig": "<signature over the marker by witness or verifier key>"
}
```

- `marker_sig` binds `principal` + `first_seen` ("the values D2a/D2b/D2d compare against").
- **CORRECTION to brief/shard-1 design**: the signed payload is `{principal, first_seen}`,
  NOT `{principal, first_seen, chain_head_date}`. `chain_head_date` is the record's CLAIMED
  head timestamp that gets corroborated AGAINST the witnessed `first_seen` — it is not signed
  into the marker.
- A marker MAY carry additional fields — explicitly `first_v2_seen` (flag-and-timestamp for
  the monotonic-upgrade boundary) and `witness_id` — but **any field a verifier relies on for
  a D2 decision MUST be inside the signed bytes** (`:205`).

## §4.3 Transport (normative split) — design (a) is spec-blessed

`:191`: transport is implementation-defined — "a Trillian-style transparency log, an
in-Foundation witness service, **or per-verifier signing keys**". Contents (§4.3.1) +
detection (§4.3.2) are normative; transport is not. → The recommended **verifier-key signed
marker** IS a first-class conformant transport, not a compromise.

## §4.3.2 Detection rule (normative) — Shard 1 detection branch

`:207-209`: emit `implicit-v1-witness-failure` when ANY of:

1. the marker is missing;
2. `marker_sig` fails verification OR the marker is expired;
3. the record's claimed pre-adoption head date is not corroborated by a signed pre-adoption
   `first_seen` (witnessed `first_seen` does not precede adoption, OR no pre-adoption witness
   entry exists for the head's hash).

## §4.1.3 / §4.2 / §4.5.3 — the monotonic dimension (Shard 3)

- §4.1.3 (`:177`): D2a acceptance ALSO requires "the verifier's trust store contains no v2
  record from this principal-chain." **This trust-store-no-prior-v2 check is a SEPARATE state
  dimension from the temporal witness, and is unenforced today** (the gate only does temporal
  - missing).
- §4.2 (`:185`): reject any record without `alg_id` from a principal-chain that has
  previously emitted a v2 record → `monotonic-upgrade-violation`.
- §4.5.3 (`:229`): once a registry-form `eatp-v1`(or later) record appears in the chain, the
  pre-registry form is rejected with `monotonic-upgrade-violation`.
- The boundary MAY live in the SAME signed marker (`first_v2_seen`, §4.3.1). So Shard 3 =
  (a) a `first_v2_seen` field on Shard 1's marker store + (b) the WRITE path that records
  first-v2 emission (record-consumer layer) + (c) the READ check in resolver dispatch §5.1
  step 3.

## §5.1 Resolver dispatch (the wiring point)

`:245-249` step 3: "If `alg_id` is absent, apply D2a/D2b/D2c. If acceptance is permitted
under D2a, dispatch `eatp-v1`; otherwise reject with `missing-alg-id-post-adoption` or
`monotonic-upgrade-violation`. If a pre-registry explicit form is present, apply D2d."

## §5.3 Error codes (full set — some unimplemented today)

Confirmed normative codes (`:259-268`): `unsupported-algorithm`, `alg-id-shape-mismatch`,
`missing-alg-id-post-adoption`, `monotonic-upgrade-violation`, `implicit-v1-witness-failure`,
`pre-registry-form-after-sunset` (D2d 2030 sunset), `chain-ref-canonical-form-mismatch`,
`alg-id-strip-detected` (signature matches no registered algorithm). The last three may be
absent today — confirm at /todos which are already raised vs new.

## §6 Vectors + levels (Shard 2 schema `level` field)

`:272`: V1–V7 required at **Conformant**; **V7 at Complete only**. V9 (D2d accept) present.
V8 is an amendment-procedure obligation, NOT a runtime vector (exclude from executable set).
V6 three sub-cases pinned `:302-306` (prior-v2 → `monotonic-upgrade-violation`; fresh
post-adoption → `missing-alg-id-post-adoption`; fresh attacker-pre-adoption-date →
`implicit-v1-witness-failure`, fixture REQUIRED). V7 `:308-311` local-marker-tamper →
`implicit-v1-witness-failure`.

## Net architectural insight

The D2c signed-marker store is the unifying substrate for THREE D2 decisions: D2a
(`first_seen`/adoption witness), D2b+D2d-monotonic (`first_v2_seen`), and the §4.3.2
detection. Shard 1 builds the store + witness side; Shard 3 adds the `first_v2_seen`
dimension + the record-consumer write path + the resolver read. This couples Shard 3 to
Shard 1 (shared store) but removes the "separate cross-layer subsystem" risk — it is one
store with two state fields.
