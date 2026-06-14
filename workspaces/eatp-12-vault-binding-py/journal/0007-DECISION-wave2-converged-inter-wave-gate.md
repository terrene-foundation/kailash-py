---
type: DECISION
slug: wave2-converged-inter-wave-gate
created: 2026-06-14T12:30:00Z
---

# Wave 2 (Audit substrate + Input) — converged; inter-wave gate G1–G4 receipt

Branch `feat/eatp-12-vault-binding` @ `3cf239dc0` (Wave-2 commit; +4801/-91 across
12 files). Wave 2 shards D1/D2/I1 implemented; **84 vault tests pass**;
`pytest --collect-only` exit 0 (18,328 collected); ruff clean; no deprecations.
All 8 §12.4–12.11 anchor byte-pins reproduce the spec hexes EXACTLY through the
production `content_signing_bytes`.

Each load-bearing shard ran as a **fresh agent context** (per-session capacity
budget — one shard's ~5–10 invariants each), driven as a sequential pipeline
because the dependency chain is real (D1 → D2 → I1, not parallelizable):

- **D1** (`dispatch.py`): named-tier `AuditDispatcher` (recovery/safety) layered
  on the delegate `AuditChainEngine` (one engine per tier → independent per-tier
  chain + real `content_signing_bytes` pre-image + real Ed25519 sign/verify);
  `DispatchReceipt`; `require_receipt_or_abort` fail-closed helper (N12-AU-02/02a/02b).
- **D2** (`anchors.py`): 10 per-subtype `vault_*` `event_payload` builders + the
  `vault_`-namespace subtype validator + the two-state `timestamp`/`time_attested`
  grammar + `side_channel_hardened` default-false (N12-AU-01/01a/03/04/04a, CRY-SC record).
- **I1** (`backup.py` + `input_gates.py`): handle-based `back_up_vault_key` /
  `restore_vault_key` + the `VaultKeyResolver` trusted-module boundary; entry gates
  (not-a-kek, ritual floor, secret-length, escape-hatch-off, CSPRNG); consume-and-`del`
  no-plaintext on every exit path (N12-IN-01..05, TH-01, CRY-PIN family). The #606
  `NotImplementedError` stub retired + its deferral tests rewritten same-commit
  (orphan-detection Rule 4a).

## G1 — redteam to convergence (the `/implement` MUST gate)

Two parallel gate reviewers (durable receipts per `verify-resource-existence.md`
MUST-4 — the agent task IDs are the external receipt). The FIRST dispatch of both
died on a transient server rate-limit (API error, not a verdict); per
`evidence-first-claims.md` MUST-3 an errored gate is zero evidence, so both were
re-dispatched and ran clean:

- **reviewer** (task `a02e7e72796c76130`): **APPROVE.** All 8 mechanical sweeps
  pass — collect-only exit 0; 83→84 vault tests green with `-W error::DeprecationWarning`;
  ruff clean; `__all__`/import parity (orphan-detection Rule 6) — 0 orphaned, 0
  un-exported; `AuditDispatcher` (`*Dispatcher` manager-shape) has a real-construction
  Tier-2 wiring test (no mocks); no-stub sweep clean; the 8 §12.4–12.11 byte-pins
  reproduce **through the real `content_signing_bytes`** (not merely a self-consistent
  spec). 2 LOW advisory (see deferred).
- **security-reviewer** (task `af357d21f183d4279`): **APPROVE-WITH-FIXES.** All 9
  KEK threat surfaces VERIFIED — no-plaintext egress (consume-and-`del` in `finally`
  on every exit path + `resolver.zeroize()`); no-secret-in-envelope (denial OMITS
  vault_id/gen/commitments via `_forbid_absent`, not null-filled); constant-time
  (`hmac.compare_digest` via C1); fail-closed everywhere; CSPRNG-only public surface;
  byte-pin/cross-SDK integrity; escape-hatch off-by-default + fail-closed-when-enabled.

### Findings + dispositions

- **HIGH-1 (fixed in-shard, autonomous-execution Rule 4):** `restore_vault_key`
  built a non-§12.8-conformant `vault_key_restore` anchor — it recorded the
  **presenting k-subset** (`shard_commitments=[]`, `shard_count=len(shards)`)
  instead of the **current-generation DISTRIBUTION** (n=5 holders + the 5
  `shard_commitments`, copied from the establishing distribution anchor) the spec
  mandates. **The byte-pin regression only exercised the DIRECT D2 builder, so the
  binding-path divergence was invisible** — the code-reviewer's byte-pin check
  passed; only the security-reviewer's trace of the actual I1 binding path caught
  it. Fix: threaded caller-supplied `shard_commitments` + `re_established_handle_ref`
  params (mirroring how `holders`/`expected_commitment` already flow as the Wave-2
  interim that C2a's registry replaces), set `shard_count = len(shard_commitments)`,
  and added an end-to-end I1-path §12.8 `event_payload` byte-pin regression
  (`test_restore_binding_path_reproduces_spec_12_8_event_payload`). The full
  signed-hex is signer-id-dependent (fixture `delegate:vault-signer-00` vs the
  test's random Ed25519 `delegate_id`), so the signer-independent `event_payload`
  is the binding-path target; the full-hex pin stays in the direct-builder test.
- **MED-1 (fixed in-shard):** the AU-02b failing-dispatch test asserted
  `... or isinstance(exc.value, Exception)` — a tautology (always True). Replaced
  with a falsifiable structural check: `isinstance(exc.value, AuditChainSignatureError)`
  (the wrong-key-verifier dispatch failure that propagates), keeping the
  `sequence_length(RECOVERY) == 0` fail-closed check.

## G2 — learning captured (this entry)

The load-bearing institutional lesson: **a byte-pin that exercises only the
direct builder does NOT prove the binding path reproduces the spec.** The §12.8
divergence passed every direct-builder test for the entire shard; it was reachable
only by driving the real `restore_vault_key` end-to-end and reading the dispatched
`event_payload`. Generalize: every cross-SDK byte-pin owned by a builder MUST also
have an end-to-end test through the public binding path that emits it. This is the
`facade-manager-detection.md` shape applied to byte-pins — the builder is the
"manager", the byte-pin-through-the-builder is the Tier-1 unit, and the
binding-path byte-pin is the wiring test that proves the framework actually
produces the contract bytes. Folded into the Wave-3/Wave-6 redteam sweep below.

Second lesson (process): running BOTH gate reviewers earned its keep — the
code-reviewer APPROVED unconditionally and MISSED HIGH-1; the security-reviewer's
adversarial path-trace caught it. The two gates are not redundant.

## G3 — later-wave todos amended (carry-ins for Wave 3+)

1. **W3-C2a (registry) — replace the caller-supplied restore interim.** I1's
   `restore_vault_key` currently takes `expected_commitment`, `holders`, and
   `shard_commitments` as caller-supplied inputs (the Wave-2 interim). C2a's
   per-(handle, generation) commitment registry + N12-CB-03 `shard_commitments`
   source MUST replace these: restore looks up the registered commitment + the
   establishing distribution anchor's `holders`/`shard_commitments` rather than
   trusting caller args. The §12.8 binding-path byte-pin test MUST be updated to
   drive the registry path once C2a lands (it currently passes the distribution
   explicitly).
2. **W3-C2a carry-in (unchanged from journal/0006):** wire the registry-layer
   `key-identity-mismatch` (N12-CB-02(d)) comparison + the `map_wrapper_exception`
   fail-closed caller (LOW-1) before ANY restore path ships — `KEY_IDENTITY_MISMATCH`
   - the recorded `key_id` are orphaned controls until then.
3. **W3-C3 (stale-guard) — wire the deferred restore gates.** I1's restore drives
   `first_failing(RESTORE_GATE_ORDER, check)` where `check` returns `None` for the
   gates C2a/C3 own (shard-count/parameter/mixed backstopped by the wrapper raising;
   foreign-shard backstopped by commitment-auth; ordinal-generation safe ONLY for
   the single-generation Wave-2 surface). C3 MUST wire `foreign-shard` (CB-03) +
   `ordinal-generation` (SG) into the SAME `check`; the security-reviewer VERIFIED
   no Wave-2 silent path returns a KEK without commitment-auth, but the
   `ordinal-generation` `None` is NOT safe once the rotation chain exists (R1) — C3
   owns closing it.
4. **Re-established-handle minting (#630).** `re_established_handle_ref` is
   caller-supplied in Wave 2 (the resolver/re-establishment hierarchy is the #630
   gap). When #630's KEK re-establishment lands, the binding mints the opaque
   re-established handle internally rather than taking it as an arg.

### Deferred LOW findings (next-iteration, non-blocking — both reviewers)

- **sec-LOW-1:** strengthen `_assert_no_plaintext` to also assert the passphrase +
  a per-shard mnemonic word are absent (currently master-secret only — the
  highest-value target IS covered).
- **sec-LOW-2:** `vault.backup.start`/`vault.restore.start` log `key_id` at INFO —
  operator-facing id, not a secret/schema name, but consider DEBUG (log aggregators
  have wide read access; `security.md` § "never expose internal IDs" posture).
- **reviewer-LOW-1:** `require_receipt_or_abort` / `DispatchReceipt.__post_init__`
  reuse `N12FT01Code.UNKNOWN_TIER` for receipt/ordering-invariant violations
  (functionally a typed loud failure; semantically imprecise for post-incident grep).
- **reviewer-LOW-2:** `build_holder_rotation_anchor` nests the `{old:{k,n},new:{k,n}}`
  ritual under a field named `"k"` — NOT among the 8 §12.4–12.11 byte-pinned subtypes,
  so no cross-SDK contract is violated yet; **R1 (Wave 5) MUST confirm the field name
  against the §4.5.1 `vault_holder_rotation` row before it byte-pins this subtype.**

### Holistic-redteam carry-in (Wave 6 terminal gate)

Add to the post-Wave-6 holistic redteam (`agents.md` § Holistic Post-Multi-Wave
Redteam): **every cross-SDK byte-pin MUST have an end-to-end binding-path test, not
only a direct-builder test** (the HIGH-1 lesson). Sweep all subtypes for this.

## G4 — re-rank

No change: waves are dependency-ordered. **Wave 3 (Crypto registry + stale —
C2a/C2b/C3)** remains the next eligible wave (it consumes the Wave-2 audit chain

- anchor schema this wave landed). Value-anchor unchanged (EATP-12 spec §4.4/§6).

**Wave 2 is converged.** Next: G5 launch Wave 3 (or human context-switch call).
