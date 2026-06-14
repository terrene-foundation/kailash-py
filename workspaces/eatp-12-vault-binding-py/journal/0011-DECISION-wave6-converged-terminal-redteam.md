---
type: DECISION
slug: wave6-converged-terminal-redteam
created: 2026-06-15T00:35:00Z
relates_to: 0010-DECISION-wave5-converged-inter-wave-gate
---

# Wave 6 (W6-X1-EMBED + T2 + S1) converged; terminal holistic redteam receipt

Branch `feat/eatp-12-vault-binding`. Wave 6 — the TERMINAL wave — landed across four
commits atop the Wave-5 `1b67dccdc` receipt. The EATP-12 v1.0 vault key-binding is
now feature-complete on the branch; **183 vault tests pass / 1 skipped** (verified
`pytest -k eatp12_vault --collect-only | grep -c ::` = 183); ruff clean.

## Commits

- **`4520e42c7`** — W6-X1-EMBED: wired the Complete-level X1 gates
  (`verify_governance_approval` / `verify_ceremony_witness`) into the hot path,
  closing the Wave-5 LOW-1 wiring gap (journal/0010 G3). `restore_vault_key` accepts
  an optional `GovernanceApproval` verified fail-closed after resolution and BEFORE
  the FT-02 gate sequence (so it lifts the CL-04 cooling-off suspension AND embeds
  into the signed restore anchor's `event_payload["approval"]`); `back_up_vault_key`
  symmetric for `CeremonyWitness` → `event_payload["witness"]`. `evaluate_clearance`
  CL-04 cooling-off lifts ONLY on a verified approval (`approval_verified`).
  `operation` ("restore" | "restore-forced-stale" | "backup") binds the pre-image
  (no cross-op replay); `requester_delegate_id` bound too (security MED-1, no
  cross-delegate replay). Conformant byte-unchanged (§12.4/§12.11 pins hold).
  V8 Tier-2 suite (10 → 13 tests). Gate reviewers: reviewer APPROVE,
  security-reviewer APPROVE (MED-1 fixed in-shard).
- **`695780cd9`** — W6-S1: spec truth-update. `specs/trust-crypto.md` §30 +
  `specs/security-data.md` §10.X both described `back_up_vault_key` as a
  NotImplementedError "stub awaiting mint ISS-37" (false since Waves 1-6). Replaced
  with the shipped contract; every cited symbol grep-resolves; split-state scan clean
  (only the permitted past-tense §30 change-log entry). The `security-data.md` drift
  was caught by the `specs-authority.md` Rule 5b full-sibling re-derivation sweep.
- **`98d044028`** — W6-T2 HIGH-7: release-blocking quickstart roundtrip regression
  (`tests/regression/test_eatp12_vault_quickstart.py`): the canonical backup→restore
  ceremony + explicit V1 KEK byte-equality (`reconstruct(generate(kek)) == kek`) +
  commitment-chain match + foreign-shard `unknown-shard` guard.
- **`3f153328c`** — terminal-redteam dispositions (HIGH-1 + PP-01 + MED-1, below).

## Terminal holistic redteam (agents.md § Holistic Post-Multi-Wave Redteam)

### Round 1 — 3 parallel reviewers across ALL 6 waves (the union, not the latest shard)

Durable receipts (agent task IDs per `verify-resource-existence.md` MUST-4):

- **reviewer** (task `abe2252e15e13447a`): APPROVE_WITH_FIXES. All 6 mechanical sweeps
  green (183 pass / collect-0 / ruff clean / zero orphans across 14 public symbols /
  no stubs / spec-accuracy clean). Cross-shard gate-order, fail-closed, consume-and-del,
  audit-completeness, and Conformant byte-pin all PASS. **MED-1**: `vault/__init__.py`
  module docstring still called the binding a "scaffold/stub NOT YET STABLE".
- **security-reviewer** (task `aa52545606fc4d776`): APPROVE_WITH_FIXES. Cryptographic
  core clean (constant-time compares, anti-replay binding, generation/rollback defense,
  authz isolation, audit integrity, no secrets in logs — all 9 threat surfaces + 11
  passed checks). **HIGH-1**: `restore_vault_key`'s X1 approval block (W6-X1-EMBED) runs
  after resolution but BEFORE the zeroizing try/finally — three denial exit paths left
  the resolved KEK un-zeroized until GC (N12-IN-05 residency, attacker-reachable).
- **closure-parity** (task `aa2dcdeb3df9cfce8`): GAPS-FOUND (1). 53/54 conformance IDs
  VERIFIED; V1-V8 all test-backed; W6-X1-EMBED carry-in CLOSED. **GAP**: N12-PP-01
  `invalid-passphrase` printability (spec §4.4.1) was an orphaned control —
  `INVALID_PASSPHRASE` declared, zero raise sites, zero tests.

### Dispositions (all fixed same-session per autonomous-execution Rule 4 — commit `3f153328c`)

- **HIGH-1**: `resolved.zeroize()` added at each of the three pre-try X1 exits
  (companion-args-missing, forged-approval-denial, mandatory-force-stale-missing). The
  4th R1-named path (non-ResolvedKek type-guard) is correctly a NO-OP — `resolved` is
  not a ResolvedKek there (no secret, no zeroize method). + 3 regression tests asserting
  `master_secret == b""` after the denial via a retaining `_SpyResolver` (Protocol
  adapter, no mock).
- **PP-01**: `require_printable_passphrase` entry gate (ASCII 32-126, empty valid) wired
  into both `back_up_vault_key` + `restore_vault_key` BEFORE the wrapper, surfacing
  `invalid-passphrase` deterministically. + 3 regression tests. 54/54 IDs now VERIFIED.
- **MED-1**: `vault/__init__.py` docstring corrected to the shipped EATP-12 contract.

### Round 2 — convergence confirmation

- **security-reviewer R2** (task `a6fc26fe5325f1524`): **CONVERGED**. All R1 security
  findings closed; the full resolution→try span re-traced (lines 873→1043), all three
  realized exit paths zeroize, the type-guard no-op confirmed correct; PP-01 gate sound
  with no bypass (the only `generate(`/`reconstruct(` call sites are gated at function
  entry); no new fail-open/double-free/secret-leak (zeroize idempotent). **Accepted LOW
  residual**: the `_find_distribution_anchor` dict-extraction span is not defensively
  zeroize-wrapped — NOT a realized gap (raises only under type-system-forbidden inputs);
  a defense-in-depth note for IF that extraction ever grows a narrowing raise.

## Convergence verdict

**Wave 6 CONVERGED.** The EATP-12 v1.0 vault key-binding is feature-complete, fail-closed,
audited, zeroized on every realized exit, and Conformant-byte-stable on the branch.
Terminal holistic redteam: R1 surfaced 3 cross-cutting findings the per-wave G1 gates
missed (the exact value of the holistic round), all fixed + regression-tested; R2 CONVERGED.

## Remaining before release (NOT in this session's scope)

- **XSDK-1/2/3 cross-SDK parity gate** — reconcile V6 (commitment + KCV + audit canonical
  pre-image), the non-ASCII sentinel (HIGH-3), and the HIGH-4 hash domains
  (`principal_set_root` / `shard_commitment`) byte-for-byte with kailash-rs (#1316), plus
  the rotation-denial no-anchor stance. **Requires a separate user-authorized cross-repo
  grant** (`repo-scope-discipline.md` § User-Authorized Exception) — NOT actionable from
  kailash-py without it. Neither SDK releases vault binding before this confirms.
- The approval/witness pre-image now binds `requester_delegate_id` (MED-1) — this is a
  NET-NEW byte surface the XSDK-3 reconciliation MUST include in the cross-SDK matrix.
