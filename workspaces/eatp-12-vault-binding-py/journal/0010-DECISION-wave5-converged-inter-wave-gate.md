---
type: DECISION
slug: wave5-converged-inter-wave-gate
created: 2026-06-14T19:30:00Z
relates_to: 0009-DECISION-wave4-converged-inter-wave-gate
---

# Wave 5 (Rotation R1 + Complete-level X1) — converged; inter-wave gate G1–G4 receipt

Branch `feat/eatp-12-vault-binding`. R1 commit `369518157`, X1 commit `82f1bfcf1`
(both atop the Wave-4 `2156c71b5` receipt). **177 vault tests pass** (157 Wave-4 +
8 R1 + 12 X1); collect-only exit 0; ruff + mypy clean.

- **R1** (`rotation.py`): `rotate_vault_holders` (amicable — N12-RT-01/02/03/04,
  generation UNCHANGED, writes `vault_holder_rotation` for_cause=False) +
  `revoke_holder_for_cause` (N12-SH-04/RT-06 — for-cause generation-advance g→g+1,
  writes `vault_kek_rotation` for_cause=true + new distribution, registers the
  new-gen commitment). Composes `shamir.rotate_holders` + `check_revocation_k_floor`
  (no reimpl). **Makes C3's stale-guard LIVE** — R1 writes the `vault_kek_rotation`
  anchors `current_generation_from_chain` reads (RT-06). `RotationReceipt` added to
  `types.py` with for-cause/amicable generation invariants enforced in `__post_init__`.
- **X1** (`complete.py`): the Complete-level cryptographic core gated behind
  `ConformanceLevel` (Conformant pre-image byte-unchanged) — `verify_governance_approval`
  (CL-03: vault:approve + tenant/domain scope + dual-axis no-self-approval + signed-token
  - fail-closed), `verify_ceremony_witness` (CL-05: vault:witness + distinct-from-requester-
    AND-approver + signed-token), per-holder wrapping (SH-02: HMAC wrap; revoked→`revoked-holder`,
    tamper→`corrupted-shard`). Signature primitive injected as a `verify_token` callable
    (real Ed25519Verifier in Tier-2 — no mock, no embedded key).

## G1 — redteam to convergence (the `/implement` MUST gate) — BOTH APPROVE

Durable receipts (agent task IDs per `verify-resource-existence.md` MUST-4):

- **reviewer** (task `ab46e5fed040b4a51`): **APPROVE**, zero CRIT/HIGH/MED. All 5
  mechanical sweeps green (177 pass / collect-0 / ruff+mypy clean / no orphans / R1
  composes `rotate_holders`+`check_revocation_k_floor` not reimpl). For-cause gen-advance
  chain-sourced (RT-06); register-after-dispatch (AU-02b); secret hygiene zeroize-in-finally
  both paths; dual-axis self-approval prohibition; trust-boundary invariant SOUND.
- **security-reviewer** (task `a1839120620d12abc`): **APPROVE**, zero CRIT/HIGH. All 9
  threat surfaces verified clean against the actual code (KEK zeroization every exit path;
  chain-sourced generation = no rollback; dual-axis self-approval/self-witness prohibition;
  fully-bound domain-separated pre-images = no cross-op/cross-vault/cross-gen replay; uniform
  fail-closed; `hmac.compare_digest` for wrap MAC; domain-separated HMAC with correct
  revoked/tamper precedence; k-floor composed before re-shard; mismatched-old_shards
  disposition correct/bounded).

### Findings + dispositions (all LOW — forward-tracking, none blocking)

- **LOW-1 (security-reviewer — X1 wiring gap → Wave-6 T2 carry-in, G3 below):** the X1
  gates (`verify_governance_approval`/`verify_ceremony_witness`/wrap) have NO production
  hot-path caller yet — `back_up_vault_key`/`restore_vault_key` reference only the
  `approver_configured` pass-through seam, never the X1 verifiers. So CL-03(c)'s "approval
  token bound into the signed `event_payload` (covered by `content_signing_bytes`)" guarantee
  is **not yet realized** — the gates verify-then-return-the-payload, but no anchor embeds it.
  This is the anchor-embedding wiring consciously deferred from X1 (commit message + module
  docstring `complete.py` §"the V8/Wave-6 anchor-embedding consumes it") for per-session
  capacity reasons. **NOT a defect** (the gates are correct + fail-closed); it is a forward-
  wiring obligation. **Tracked as a Wave-6 T2 carry-in (G3) with a value-anchor.**
- **LOW-2 (both — docstring wording; FIXED):** `HolderRevocationRegistry.is_revoked`
  docstring said "fail-closed" but is fail-open on the revocation check (the integrity MAC
  check immediately after is the fail-closed backstop). Wording tightened to state the
  composed behavior accurately. Composed behavior was always safe.
- **rotation-denial audit gap (both — documented, XSDK-3):** a rotation gate-failure raises
  typed + WARN-logs but writes NO denial anchor, because the §4.5 **closed** denial-subtype
  set (`{vault_key_backup_denied, vault_key_restore_denied}`, N12-AU-03) has no
  `vault_*_rotation_denied` member; minting one would break the V6 golden-fixture byte-pin.
  Both reviewers: the conservative no-mint choice is **correct**; reconcile at the cross-SDK
  gate (XSDK-3, kailash-rs #1316) — confirm rs takes the same no-denial-anchor stance so the
  two SDKs don't diverge. Already disclosed in `rotation.py` §"Rotation-denial audit gap".

## G2 — learning captured (this entry)

Lesson 1 (**library-contract surfacing via the real-infra test**): `shamir.reconstruct`
requires EXACTLY `threshold` mnemonics, not `n` — the first R1 test (passing all `n` shards)
surfaced `MnemonicError: Expected 3 ... but 5 were provided`. The Tier-2 real-SLIP-0039 path
(not a mock) is what surfaced the exact-`k` contract; a mocked re-shard would have hidden it.
Generalizes the journal/0006 + journal/0009 carry-in: **every composed-wrapper invariant needs
an end-to-end test through the real wrapper, not a direct-seed/mock.** Docstrings on both R1
surfaces corrected to "EXACTLY `threshold`".

Lesson 2 (**capacity-honest shard boundary**): X1's anchor-embedding (binding the gate's
returned payload into the signed `event_payload`) was deferred mid-shard, in-session, for
per-session attention-budget reasons (R1-full + X1-core already landed). The security-reviewer
independently flagged the resulting orphan (LOW-1) — confirming the deferral was real and
must be **tracked**, not forgotten (the deferral-as-forgetting failure mode). G3 records it
with a value-anchor.

## G3 — later-wave todos amended (carry-ins for Wave 6)

1. **W6-X1-EMBED (NEW Wave-6 carry-in, from LOW-1) — wire the X1 gates into the hot path.**
   Value-anchor: realizes the CL-03(c)/CL-05 "token bound into the signed `event_payload`,
   covered by `content_signing_bytes`" guarantee the EATP-12 v1.0 spec §4.2 success criterion
   requires (primary anchor: spec §4.2 N12-CL-03(c) — user-approved Published normative spec).
   Scope: `restore_vault_key` accepts an optional `GovernanceApproval` + approver clearance +
   `verify_token` → runs `verify_governance_approval` → embeds the returned payload into the
   restore anchor's `event_payload["approval"]` (the existing `build_restore_*_anchor` adds an
   optional `approval` sub-object); `back_up_vault_key` symmetric for `CeremonyWitness` →
   `event_payload["witness"]` (the existing `build_backup_anchor` already has the optional
   `witness` scaffold). Conformant path (no approval/witness) byte-unchanged. Mandatory ONLY
   for the CL-03 high-risk restore paths (raw-bytes IN-03, forced-stale SG-03, cooling-off
   CL-04). Add a V8 Tier-2 end-to-end test: a forged/missing approval on a forced-stale restore
   is rejected `missing-clearance` AND a valid approval lands in the dispatched anchor's
   `event_payload` (covered by `content_signing_bytes`). This is the natural V8 (Complete-level)
   conformance-vector home in the W6-T2 suite.
2. **W6-S1** spec truth-update MUST describe R1 (`rotate_vault_holders`/`revoke_holder_for_cause`)
   - X1 (`complete.py` gates) as shipped, citing the landed symbols (`spec-accuracy.md` Rule 1).
3. **XSDK-3** cross-SDK gate: reconcile the rotation-denial no-anchor stance + the Complete-level
   approval/witness `event_payload` fields byte-for-byte with kailash-rs (#1316). (Carried from
   the rotation-denial disposition + the X1 Complete-field byte surface.)

## G4 — re-rank

No change to the forest order: **Wave 6 (conformance proof T2 + spec truth-update S1)** is the
terminal wave, now carrying the W6-X1-EMBED wiring + V8 end-to-end (above). Value-anchor
unchanged (EATP-12 spec §7 V1–V8 release-blocking conformance + §4.2 CL-03(c)). The post-Wave-6
holistic redteam + cross-SDK parity gate (XSDK-1/2/3) remain terminal; neither SDK releases
vault binding before the cross-SDK byte-parity reconciliation confirms.

**Wave 5 is converged.** Next: G5 launch Wave 6 (T2 conformance suite incl. V8 + W6-X1-EMBED;
S1 spec) — recommended for a fresh orchestrator session (terminal conformance + holistic
redteam + cross-SDK gate is a large value-coherent wave); or human context-switch call.
