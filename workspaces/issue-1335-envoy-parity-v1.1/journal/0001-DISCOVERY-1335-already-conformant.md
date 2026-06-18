# 0001 — DISCOVERY: #1335 envoy-parity v1.1 errata — kailash-py already conformant

**Date:** 2026-06-16
**Phase:** /analyze (brief-claim verification gate per `rules/agents.md` § Parallel Brief-Claim Verification)
**Verdict:** #1335 is a **CLOSE-WITH-EVIDENCE**, not an implementation task. Every acceptance criterion is already met in kailash-py by existing code carrying explicit v1.1 annotations, with passing test coverage.

## Why this matters (brief framing was cross-SDK)

The #1335 brief was authored from the Foundation/Rust v1.0→v1.1 perspective (it is "the kailash-py ISS-34 cross-file" tracking issue). Its B1 field-rename table and B2 wire-swap describe the **Rust/Foundation typed envelope schema**. kailash-py uses a **different envelope representation** and was **already brought to v1.1** in prior trust/vault work — so the brief overstates kailash-py scope ~5×. This is the exact decay-of-author-mental-model failure mode the parallel-verification gate exists to catch.

(Method note: 4 parallel verification agents were launched but killed by a transient server-side API rate-limit before reporting — zero evidence per `rules/evidence-first-claims.md` MUST-3. Verification was redone inline. Every claim below cites file:line + a passing test.)

## Per-cluster verdicts (evidence-cited)

### B1 — 9 field renames/reshapes → **N/A for kailash-py**

- kailash-py's PACT constraint-envelope wire shape is **generic**: `active_constraints[]` of `{id, constraint_type, value, source, priority}` (stringly-typed `value`, e.g. `"max_api_calls:1000"`). Reference: `tests/trust/fixtures/wire_format/constraint-envelope.fixture.json`.
- None of the v1.0 typed names exist in the envelope path: `max_cumulative_amount`, `operation_scope`, `rate_limit_per_hour`, `deadline_iso8601`, `content_classification_ceiling`, `operating_hours`, `pii_handling` — grep across `src/kailash/trust/` returns no envelope-emit sites.
- The trust-plane `TemporalConstraint` (`src/kailash/trust/envelope.py:302-311`) **already uses v1.1 names**: `valid_until`, `max_duration_seconds`. The lone v1.0-style field `cooldown_minutes` (envelope.py:307) lives in the trust-plane's internal dataclass, which carries **no** PACT-05/`schema_version`/`constraint-envelope` marker — it is not the PACT-05 wire schema. Not a wire-conformance gap.

### B2 — classification wire-semantic swap → **N/A / already-correct**

- Canonical ordinal map is correct and name-honest: `src/kailash/trust/pact/config.py:42-47` — `PUBLIC:0, RESTRICTED:1, CONFIDENTIAL:2, SECRET:3, TOP_SECRET:4`.
- Engine comparisons use the canonical ordinal, never a wire token's apparent rank: `src/kailash/trust/pact/access.py:421` (`_CLEARANCE_ORDER[ConfidentialityLevel.SECRET]`).
- kailash-py's confidentiality vocabulary has **no `internal` wire token** (it uses named enum members), so the Rust-side `internal↔C3` swap concern does not map onto kailash-py.

### EATP-10/12 — over-supply reject (`too-many-shards`, no trim) → **DONE**

- Error code exists: `src/kailash/trust/vault/errors.py:62` (`TOO_MANY_SHARDS = "too-many-shards"`).
- Restore enforces exactly-k at the FT-02 `shard-count` gate: `src/kailash/trust/vault/backup.py:1196-1199` — `len(shards) < k → INSUFFICIENT_SHARDS`, `len(shards) > k → TOO_MANY_SHARDS`. Comment at backup.py:1185: _"py pins the N12-FT-02 REJECT branch (too-many-shards): an over-supply is REJECTED, the trim branch is not chosen."_ No trim path is wired.
- Test: `tests/integration/test_eatp12_vault_backup_restore_wiring.py:633 test_restore_too_many_shards_rejected_too_many_shards` asserts `exc.value.code is N12FT01Code.TOO_MANY_SHARDS` for k+1 over-supply. **PASSING.**

### EATP-09a — recovery-tier dispatch under indefinite seal → **DONE (already-correct)**

- `src/kailash/trust/vault/dispatch.py:27-33` (N12-AU-02a): _"the `recovery` tier is conceptually 'sealed indefinitely'… but BOTH MUST still ACCEPT `dispatch()`… NEVER fails due to a seal. A deployment MUST NOT exercise an EATP-09 §3.4 'further restricts'."_ Exactly the v1.1 not-brickable requirement.

### EATP-09b — `wrong-tier` retired in favour of `unknown-tier` → **DONE**

- `src/kailash/trust/vault/errors.py:82` (`UNKNOWN_TIER = "unknown-tier" # EATP-09 N9-D-02`); errors.py:49 explicitly: _"so the vocabulary does not fork across SDKs."_ No `wrong-tier` token anywhere; no `info` tier defined.

## Test confirmation (closure evidence — behaviour is LIVE, not just code-present)

`pytest tests/integration/test_eatp12_vault_backup_restore_wiring.py tests/integration/test_eatp12_vault_dispatch_wiring.py tests/regression/test_eatp12_vault_canonical_vectors.py` → **35 passed in 1.21s** (2026-06-16).

## Disposition

- **Recommend closing #1335** against the existing code (cite the file:line + passing tests above) — there is no shippable kailash-py change. Closure is the user's call (it's a cross-SDK tracking issue; the rs side may still be open).
- The acceptance checkboxes map cleanly: B1 → N/A (different envelope repr); B2 → already name-honest; over-supply → backup.py:1196-1199 + passing test; `recovery` dispatch + `wrong-tier`→`unknown-tier` → dispatch.py/errors.py as cited.
- **Re-sequences the parity queue:** #1335 drops out as implementation work → the real first implementation shard is **#1339** (DistributedLock/Lease, HIGH, true new feature).
