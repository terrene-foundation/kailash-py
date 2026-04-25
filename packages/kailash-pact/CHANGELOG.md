# PACT Changelog

## [0.11.0] — 2026-04-25 — PACT N4/N5 conformance runner (#605)

Cross-SDK parity with `kailash-rs#317`. Minor bump — new public surface; closes Envoy Phase 02 BET-6 gate (cross-SDK contract parity for Python is now falsifiable).

### Added

- **`pact.conformance` subpackage** (#605 shards A–D) — full PACT N4/N5 conformance vector runner. Public surface:
  - `ConformanceVector`, `ExpectedVerdict` dataclasses (vector schema)
  - `load_vectors(vector_dir)` — JSON fixture loader with schema validation
  - `parse_vector(json_obj)` — strict parser; rejects unrecognised contracts at parse-time with `ConformanceVectorError`
  - `ConformanceRunner` — drives a `GovernanceEngine` through every vector; produces `RunnerReport` with per-vector PASSED / FAILED / UNSUPPORTED outcome + canonical-JSON byte-equality diff
  - `render_failure_report(report)` — human-readable diff renderer
- **`pact-conformance-runner` CLI** (shard C) — entry point: `pact-conformance-runner <vector_dir> [--json] [--verbose]`. Exit code 0 if all PASSED, 1 if any FAILED (UNSUPPORTED counts as PASSED). Stdout is JSON with `--json`, human-readable otherwise; stderr for progress.
- **Vendored N4/N5 vectors** (shard D.1) at `tests/fixtures/conformance/{n4,n5}/*.json` — 5 N4 + 2 N5 vectors, byte-identical copies from `kailash-rs` commit `95916caa66d698d2d7c2755a4b5f3e61019af74e` (snapshot 2026-04-25). Refresh procedure documented in `tests/fixtures/conformance/README.md`.
- **65 tests pass** — 26 vector loader + 19 runner Tier 1 cases + 16 CLI Tier 1 + 4 Tier 2 integration (real `GovernanceEngine` + real `PactEngine` against vendored vectors).
- **Specs**: `specs/pact-enforcement.md` § 21 — public surface contract, vendored-vector refresh procedure, BET-6 status.

### BET-6 Phase 02

Python runner validates byte-for-byte against all 7 real Rust conformance vectors. Cross-SDK governance-semantics parity is now falsifiable. Phase 02 BLOCKER cleared.

### Cross-SDK API gaps surfaced

Two known divergences from the cross-SDK contract (documented in PR #624 body for reviewer triage):

1. `kailash.trust.pact.GovernanceVerdict.level: str` uses legacy snake_case; canonical contract is `zone: GradientZone` enum (PascalCase JSON values like `"AutoApproved"`). Runner owns the cross-SDK shape internally.
2. `kailash.trust.posture.TrustPosture` enum values use legacy semantic labels; canonical Rust values are snake_case variant names. Runner uses internal `PactPostureLevel` enum.

### Related

- Cross-SDK: `esperie/kailash-rs#317`
- Issues: closes #605 (all 4 shards landed across PRs #622 + #624)

## [0.10.0] - 2026-04-23

### Added

- **PACT × kailash-ml governance methods (W32.c)** — new `pact.ml`
  module shipping the three governance methods required by the
  kailash-ml 1.0.0 engine surface per `specs/pact-ml-integration.md`:
  - `check_trial_admission(engine, *, tenant_id, actor_id, trial_config,
budget_microdollars, latency_budget_ms, fairness_constraints=None,
...) -> AdmissionDecision` — pre-trial admission gate for
    `AutoMLEngine.run()` / `HyperparameterSearch.search()` / every
    agent-driven tuning sweep. Validates budget / latency against the
    governance envelope, fails CLOSED on probe exception per PACT
    MUST Rule 4, and emits an audit row with a `sha256:<8hex>` payload
    fingerprint (cross-SDK contract per
    `rules/event-payload-classification.md` MUST Rule 2).
  - `check_engine_method_clearance(engine, *, tenant_id, actor_id,
engine_name, method_name, clearance_required, held_dimensions=None,
...) -> ClearanceDecision` — per-method D/T/R clearance gate called
    at every `MLEngine` mutation entry point (`fit` / `predict` /
    `promote` / `delete` / `archive` / `rollback`).
  - `check_cross_tenant_op(engine, *, actor_id, src_tenant_id,
dst_tenant_id, operation, clearance_required, ...) ->
CrossTenantDecision` — v1.0 always-denied contract per spec
    IT-4 / Decision 12. Full bilateral clearance evaluation lands in
    v1.1. The v1.0 always-denied path is a REAL implementation (frozen
    decision, audit row, typed errors for invalid inputs) -- removing
    it would remove the audit trail and fail-open.
- **Frozen decision dataclasses** in `pact.ml`:
  `AdmissionDecision`, `ClearanceDecision`, `CrossTenantDecision`
  (all `frozen=True` per PACT MUST Rule 1).
- **Typed error hierarchy** for programmer-error inputs:
  `GovernanceAdmissionError`, `GovernanceClearanceError`,
  `GovernanceCrossTenantError`. Denials are DATA, not exceptions.
- **`ClearanceRequirement` decorator** and `MLGovernanceContext`
  frozen dataclass — the `ml_context` kwarg plumbed through every
  MLEngine mutation method. Per `rules/security.md` § Multi-Site
  Kwarg Plumbing, the kwarg is security-relevant; silently defaulting
  it would defeat governance, so the decorator raises `PactError` when
  it is missing.
- **Audit row schema** (`specs/pact-ml-integration.md` §5):
  `decision_id`, `method`, `tenant_id` (indexed per
  `rules/tenant-isolation.md` §5), `actor_id`, `admitted_or_cleared`,
  `binding_constraint`, `reason`, `decided_at`, `payload_fingerprint`,
  `audit_correlation_id` (links PACT rows 1:1 with kailash-ml
  `_kml_audit` rows).

### Cross-SDK Parity

- The `sha256:<8hex>` payload fingerprint format is identical to
  kailash-rs `crates/kailash-pact/src/engines/governance.rs` (spec §7).
  Forensic correlation across polyglot deployments relies on this
  stable shape.

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
