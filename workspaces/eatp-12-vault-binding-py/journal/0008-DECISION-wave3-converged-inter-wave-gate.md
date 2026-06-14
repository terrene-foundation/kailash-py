---
type: DECISION
slug: wave3-converged-inter-wave-gate
created: 2026-06-14T15:00:00Z
---

# Wave 3 (Crypto registry + stale-guard) — converged; inter-wave gate G1–G4 receipt

Branch `feat/eatp-12-vault-binding` @ `4b5562490` (Wave-3 commit). Shards C2a/C2b/C3
implemented; **111 vault tests pass**; `collect-only` exit 0 (18,355); ruff clean; no
deprecations. The §12.2/12.3 byte-pins are unchanged (eatp-v1 path untouched by the
eatp-v1.1 registry addition).

Each load-bearing shard ran as a fresh agent context. Dependency chain: C2a (registry
foundation) → {C2b (recommit/retire write paths, disjoint), C3 (stale-guard, extends
C2a's restore)}; run sequentially because C3 extends the same restore_vault_key region
C2a just authored.

- **C2a** (`registry.py`): per-(vault_id, kek_generation) commitment registry keyed by
  alg; 3-way discrimination (commitment-alg-mismatch / kek-commitment-mismatch /
  key-identity-mismatch); recompute-under-RECORDED-alg + CAPTURED-gen (no downgrade);
  CB-03 foreign-shard BEFORE reconstruction (lazy `_reconstruct_guarded`) from the
  recovery-tier distribution anchor; `map_wrapper_exception` None→deny. **The key-identity
  control is now WIRED (journal/0006 carry-in CLOSED — no longer orphaned).** The
  `map_wrapper_exception` fail-closed caller carry-in (journal/0006 LOW-1) is also CLOSED.
- **C2b** (`registry_ops.py`): `recommit_vault_kek` (additive — old alg stays verifiable,
  V6(e)) + `retire_vault_kek_alg` (→ retired-commitment-alg, distinct vault:retire-alg
  cap, recoverability guard refuses to strand the corpus); FT-03 write-path gate orders.
- **C3** (`stale_guard.py`): FT-02 step-8 ordinal-generation gate (default stale refusal —
  no silent rollback; current gen from the audited rotation chain); force_stale step-8-only
  (steps 6/7 still enforced; vault:restore-stale cap; dual-emit recovery+safety);
  compromised-generation denylist (revoked-generation, NOT force_stale-overridable);
  RT-05 D6 trigger (SUPERVISED downgrade + 7-day cooling-off on EVERY materializing restore).

## G1 — redteam to convergence (the `/implement` MUST gate) — BOTH APPROVE

Durable receipts (the agent task IDs are the external receipt per `verify-resource-existence.md`
MUST-4):

- **security-reviewer** (task `a6468633858bbca34`): **APPROVE** — zero CRIT/HIGH. All 11 KEK
  threat surfaces VERIFIED with quoted code lines: 3-way discrimination sound (recompute uses
  recorded-alg + captured-gen, never current/latest — no downgrade); foreign-shard genuinely
  before reconstruction (lazy reconstruct fired only inside commitment-auth); key-identity
  fires (not orphaned); map_wrapper_exception None→`CORRUPTED_SHARD` deny; recommit additive +
  retire recoverability guard enforced (no path silently deletes a live commitment); force_stale
  step-8-only (commitment mismatch still fails under it); default stale refusal (no silent
  rollback); denylist non-overridable by force_stale; RT-05 fires on every materializing restore
  (single fall-through trigger, no carve-out); no plaintext egress (`del secret`+`zeroize()` every
  path, AU-02b mutation-after-dispatch); eatp-v1.1 addition preserves byte-pins.
- **reviewer** (task `a2920480d9c71e859`): **APPROVE** — zero CRIT/HIGH/MED. 8 mechanical sweeps
  clean (collect-only exit 0; 111 green `-W error::DeprecationWarning`; ruff clean; **all** parity
  41 symbols; no-stub sweep clean — the 3 `pragma: no cover` are genuinely-unreachable fail-closed
  guards, not seams; PostureStore via shipped API, no raw SQL). Confirmed eatp-v1.1 correctly scoped
  (recommit structurally needs ≥2 resolvable algs; eatp-v1 stays default; spec's "pin until PQC"
  honored — eatp-v1.1 is opt-in migration target).

### Deferred LOW findings (next-iteration / Wave-6 polish — non-blocking, gate-APPROVED as-is)

1. **sec-LOW-1** — `verify_commitment` `hmac.compare_digest` length-invariant is enforced upstream by
   the alg-keyed lookup (recomputed + expected always same hash family); no change needed (note only).
2. **sec-LOW-2** — `stale_guard.py:~126` `current_generation_from_chain` uses the literal `"recovery"`
   vs `AuditTier.RECOVERY.value`; cosmetic single-source drift risk — source from the enum.
3. **sec-LOW-3** — the backup denial anchor's `target_handle_ref` embeds `vault_id:key_id`; by-design
   (the denial must identify its target) and key_id is not-secret; no action.
4. **reviewer-LOW-1** — `registry_ops.py:~446` retire gate-2 (`kek_generation != key_handle.kek_generation`)
   is a tautology (`# pragma: no cover`), documented as an FT-03-order-preserving placeholder; strengthen
   if a future surface adds a second generation source.
5. **reviewer-LOW-2** — `registry_ops.py:~573` `_mark_entry_retired` reaches `CommitmentRegistry._store`
   (no public mutate method); add a `CommitmentRegistry.mark_retired(...)` public method to close the
   cross-module private reach. Encapsulation seam, fail-closed, immutability honored.

## G2 — learning captured (this entry)

Load-bearing lesson: **the security-reviewer's adversarial path-trace remains the decisive gate on
crypto** — Wave 2's HIGH-1 was caught only by it; Wave 3 it independently VERIFIED all 11 surfaces
with quoted lines while the code-reviewer's mechanical sweeps confirmed structure. Both gates on every
CRITICAL crypto wave is the right discipline. Second: the FT-02/FT-03 first-failing gate-order
skeletons (Wave-1 FT shard) paid off — C2a/C2b/C3 each wired their gates into the SAME closed order, so
two SDKs return the same first code (the F-XSDK-13 determinism guarantee) without re-deriving the order.

## G3 — later-wave todos amended (carry-ins for Wave 4)

1. **W4-B1 (clearance + CL-04 cooling-off) CONSUMES C3's RT-05 trigger.** C3 fires the D6 posture
   downgrade (SUPERVISED) + records the 7-day cooling-off start (via PostureStore `record_transition`
   metadata) on every materializing restore. B1's CL-04 gate MUST read that cooling-off receipt and
   suspend the principal's `vault:*` tokens during the window (a 2nd op needs HELD or missing-clearance).
   The trigger is fired; B1 enforces. B1 also owns CL-01/02/02a (capability-on-bound-role + tenant→domain→token
   fail-closed) — these run BEFORE the crypto gates (FT-02 step 1 clearance, currently a presence check
   in I1; B1 deepens it to the full CapabilitySet/RoleScope evaluation).
2. **W4-B2 (holder registry SH-01/03)** — holder-registry membership (unregistered-holder) + k-floor-no-
   silent-drop on revocation; independent of the crypto core.
3. **Wave-2 caller-supplied restore interim — PARTIALLY closed.** C2a now sources commitment + foreign-shard
   from the registry/distribution-anchor; `expected_commitment`/`holders`/`shard_commitments` remain as
   documented backward-compat fallbacks. A future shard MAY remove them once all callers use the registry path.
4. **Deferred LOWs 2 + 5 above** are the cheapest Wave-6-polish candidates (1-line enum-source + a public
   `mark_retired` method).

## G4 — re-rank

No change: waves are dependency-ordered. **Wave 4 (Authz — B1 clearance + CL-04 cooling-off, B2 holder
registry)** is the next eligible wave; CL-04 consumes the RT-05 trigger this wave landed. Value-anchor
unchanged (EATP-12 spec §4.2/§4.3).

**Wave 3 is converged.** Next: G5 launch Wave 4 (or human context-switch call).
