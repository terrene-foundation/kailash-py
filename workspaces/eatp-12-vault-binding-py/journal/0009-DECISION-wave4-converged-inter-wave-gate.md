---
type: DECISION
slug: wave4-converged-inter-wave-gate
created: 2026-06-14T17:00:00Z
---

# Wave 4 (Authz — clearance + holder registry) — converged; inter-wave gate G1–G4 receipt

Branch `feat/eatp-12-vault-binding` @ `2e6ff74cc` (Wave-4 commit). Shards B1/B2 implemented;
**157 vault tests pass**; collect-only exit 0; ruff clean.

- **B1** (`clearance.py`): `evaluate_clearance` — CL-01/02 (vault:backup/restore on the bound
  CapabilitySet, independent gates); **CL-02a** binding-OWNED tenant/domain scoping (vault
  tenant/domain from the resolver, fail-closed order tenant→domain→token, `domain_covers` with
  a `/` boundary); **CL-04** cooling-off suspension reading C3's RT-05 PostureStore receipt via
  the trust-anchored clock. `ResolvedKek` extended with `vault_tenant`/`vault_domain` (all ~13
  construction sites updated, orphan-detection Rule 4).
- **B2** (`holder_registry.py`): SH-01 deployment-controlled `HolderRegistry` (unregistered-holder
  before sharding — closes the exfil channel); SH-03 `check_revocation_k_floor` (rotation-required,
  no silent drop below k).

## G1 — redteam to convergence (the `/implement` MUST gate) — BOTH APPROVE-WITH-FIXES

Durable receipts (agent task IDs per `verify-resource-existence.md` MUST-4):

- **security-reviewer** (task `a99645265db33e2b9`): **APPROVE-WITH-FIXES**, zero CRIT/HIGH. All 8
  authz surfaces VERIFIED (CL-02a `+ "/"` boundary closes the naive-prefix attack; CL-04 reader
  fail-closed; SH-01 before-sharding; no plaintext regression).
- **reviewer** (task `a5ae843370b8d0627`): **APPROVE-WITH-FIXES**, zero CRIT/HIGH/MED beyond the
  one shared MED; all mechanical sweeps green.

### Findings + dispositions

- **MED (CL-04 writer clock — code-reviewer; FIXED in-shard):** `restore_vault_key` threaded
  `trust_anchored_now` to the cooling-off READ but not the WRITE — `trigger_d6_posture_downgrade`
  omitted it, so the window START recorded wall-clock while the reader compared trust-anchored
  (a clock-source asymmetry an attacker skewing host time at restore-1 could exploit). Fixed:
  pass `now=trust_anchored_now` to the trigger + an **end-to-end producer-clock regression**
  (`test_cooling_off_start_recorded_from_trust_anchored_clock_end_to_end`) driving the START write
  through the real restore→D6 path (the prior CL-04 tests seeded via a direct trigger call).
- **MED-1 (CL-04 reader history-order — security-reviewer; FIXED in-shard):** `read_cooling_off_start`
  returned the first history match, trusting `get_history` newest-first; an oldest-first store would
  compute the window from a twice-recovered principal's FIRST restore → under-suspension. Fixed: select
  the LATEST start by parsed timestamp across ALL matching transitions (independent of store order);
  fail-closed (raise) on any unparseable receipt.
- **MED-2 (check_revocation_k_floor orphan — security-reviewer; DISPOSITION):** the SH-03 guard has
  no production call site (the for-cause revocation that calls it is R1/Wave-5). It IS pinned by a
  direct Tier-1/2 contract test (the reviewer's option-b), so not a silent orphan. **R1-consumer
  obligation (G3 carry-in below) records that R1 MUST call `check_revocation_k_floor` — do NOT
  re-implement a parallel k-floor check.**

### Deferred LOW findings (next-iteration / Wave-6 polish — gate-APPROVED as-is)

1. sec-LOW-1 / reviewer-LOW-3 — `domain_covers` authorizes a broader bound domain over a narrower
   vault sub-domain in the same tenant; by-design per §4.2a(b) (tenant is the hard wall, checked first).
2. sec-LOW-2 / LOW-2 — principal id in the cooling-off error `.details`; confirm not PII in deployment.
3. (Wave-3 carryover, journal/0008) sec-LOW-2 enum-source `"recovery"` in stale_guard; reviewer-LOW-2
   `CommitmentRegistry.mark_retired` public method.

## G2 — learning captured (this entry)

Lesson: **a producer/reader clock-source asymmetry is invisible to a test that seeds the producer
directly.** The CL-04 tests all injected the cooling-off start via a direct `trigger_d6` call, so the
writer's wall-clock default was never exercised — only the end-to-end restore→D6→second-op chain
surfaces it. Generalize (Wave-6 holistic-redteam carry-in, alongside the journal/0007 byte-pin lesson):
**every injected-clock / injected-dependency invariant needs an end-to-end test through the real
producer path, not only a direct-seed test.** Same shape as the Wave-2 HIGH-1 byte-pin-only-direct-builder
lesson.

## G3 — later-wave todos amended (carry-ins for Wave 5)

1. **W5-R1 (rotation) CONSUMES two Wave-3/4 seams:** (a) B2's `check_revocation_k_floor` disposition —
   for a for-cause revocation R1 MUST call this guard (do NOT re-implement) then perform the
   generation-advancing `vault_kek_rotation` (for_cause=true) per SH-04; (b) C3's `ordinal-generation`
   gate reads the current generation from the audited rotation chain (`current_generation_from_chain`
   scans `vault_kek_rotation` anchors) — R1 is what WRITES those anchors (RT-06), so C3's stale-guard
   becomes live the moment R1 lands. R1 also writes the `vault_holder_rotation` anchor (amicable, RT-02)
   - reuses the B1 clearance gate (vault:rotate) + the N12-TH-01 floor.
2. **W5-X1 (Complete-level)** — CL-03 governance-approver HELD (B1's `evaluate_clearance` documents the
   `approver_configured` seam — wire the HELD path here), CL-05 witness, SH-02 per-holder wrapping.
3. **Wave-2 caller-supplied restore interim** still has the `expected_commitment`/`holders`/
   `shard_commitments` backward-compat fallbacks (C2a/B-paths now source from registry/anchor); removable later.

## G4 — re-rank

No change: **Wave 5 (Rotation R1 + Complete-level X1)** is the next eligible wave (R1 closes the
for-cause-revocation loop B2 surfaced + makes C3's stale-guard live). Value-anchor unchanged
(EATP-12 spec §5/§4.2/§4.3). Wave 6 (conformance proof T2 + spec truth-update S1) is terminal.

**Wave 4 is converged.** Next: G5 launch Wave 5 (or human context-switch call).
