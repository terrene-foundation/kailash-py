# PACT Changelog

## [0.9.0] - 2026-04-20

### Added

- **Absorbed governance capabilities (#567 PR#7 of 7)** — REJECTS the MLFP
  `GovernanceDiagnostics` parallel facade (716 LOC) and ABSORBS four
  capabilities as first-class methods on existing PACT classes:
  - `PactEngine.verify_audit_chain(...) -> ChainVerificationResult` —
    verifies audit chain integrity within tenant / sequence / time
    filters. Acquires `self._submit_lock` before reading. NEVER raises
    on chain break (fail-closed per PACT MUST Rule 4); returns
    `is_valid=False` with `first_break_reason` + `first_break_sequence`.
  - `PactEngine.envelope_snapshot(...) -> EnvelopeSnapshot` — returns a
    frozen point-in-time envelope snapshot by either `envelope_id` or
    `role_address`. Acquires the engine's thread lock via
    `GovernanceEngine.compute_envelope`.
  - `PactEngine.iter_audit_anchors(...) -> Iterator[AuditAnchor]` —
    yields persisted audit anchors filtered by tenant / time / limit.
    Reuses the canonical `kailash.trust.pact.audit.AuditAnchor` (no
    redefinition).
  - `CostTracker.consumption_report(...) -> ConsumptionReport` —
    aggregates `CostTracker._history` with filters, returning totals in
    microdollars (USD × 1_000_000) for integer-math financial safety.
    Acquires `self._lock` during aggregation.
  - `pact.governance.testing.run_negative_drills(engine, drills, *,
stop_at_first_failure=False)` — test-only batch runner for negative
    governance probes. Fail-CLOSED: a drill passes ONLY when it raises
    `GovernanceHeldError`. A drill that returns normally or raises any
    other exception counts as FAILED.

- **Frozen result dataclasses** in `pact.governance.results`:
  `ChainVerificationResult`, `EnvelopeSnapshot`, `ConsumptionReport`,
  `NegativeDrillResult`. All `frozen=True` per PACT MUST Rule 1. Also
  re-exported at the package top-level (`from pact import
ChainVerificationResult`).

### Security

- All new engine / tracker methods acquire `self._submit_lock` (async)
  or `self._lock` (thread) before reading shared state — no bypasses.
- No new raw SQL; all persistence reads go through existing PACT
  surfaces.
- Rejects MLFP's 3 MUST violations: no chain-race (PR#7 holds the
  submit lock); no non-frozen GovernanceContext exposure (results are
  frozen dataclasses, engine handle stays private); no fail-open drills
  (runner treats exceptions as failures, not passes).

## [0.6.0] - 2026-04-02

### Fixed

- **API error sanitization** (P-H6): All mutation endpoints now hide internal exception details
- **Envelope adapter error handling** (P-H7): PactError vs generic Exception handled separately with sanitized messages
- **NaN/Inf on operational rate limits** (P-H8/P-H9): `max_actions_per_day` and `max_actions_per_hour` validated via `math.isfinite()`
- **AuditChain integrity on deserialization** (P-H10): `from_dict()` verifies hash chain after reconstruction
- **grant_clearance D/T/R resolution** (#215): Endpoint resolves D/T/R addresses via `engine.get_node()` before granting
- **get_node non-head role resolution** (#216): Endpoint supports suffix-based address resolution

### Security

- R2 red team converged: 0 CRITICAL, 0 HIGH findings
- 1,257 tests passing, 0 regressions

## [0.5.0] - 2026-03-30

### Added

- **PactEngine facade**: Dual Plane bridge with progressive disclosure (v0.4.0 → v0.5.0)
- **Bridge LCA Approval** (#168): `create_bridge()` requires lowest common ancestor approval with 24h expiry
- **Vacancy Enforcement** (#169): `verify_action()` checks vacancy status before envelope checks
- **Dimension-Scoped Delegation** (#170): `DelegationRecord.dimension_scope` for delegations scoped to specific constraint dimensions
- **CostModel** (#66): Per-model cost rates wired to GovernedSupervisor and `/cost` handler
- **External HELD mechanism** (#61): `GovernanceHeldError` catch, `resolve_hold()`, `asyncio.Event` gate
- **ConstraintEnvelopeConfig** (#59): Pydantic-based configuration replacing raw dataclass
- **DataClassification → ConfidentialityLevel** (#60): CARE terminology alignment across 12+ files
- **22 governance modules** (#63): Moved to `src/kailash/trust/pact/` (api/cli/mcp stay in kailash-pact)
- **/compact and /plan handlers** (#65): Sync message pruning and GovernedSupervisor display

### Fixed

- **internal_only Enforcement** (#179): Only explicitly external actions blocked for internal-only agents
- **Session file permissions** (#68): 0o600/0o700 with atomic writes via `os.open`

### Security

- Red team converged: all HIGH/MEDIUM findings fixed (thread safety, NaN validation, bounded collections, TOCTOU, fuzzy match)
- 189 new tests, 3,243 total passing
