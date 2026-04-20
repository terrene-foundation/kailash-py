# PACT Absorbed Governance Capabilities

**Spec authority**: This is domain truth for the five first-class
governance-diagnostic capabilities absorbed into existing PACT classes.
When code and spec disagree, update the spec or fix the code — never leave
them divergent (per `rules/specs-authority.md`).

## Provenance

Issue #567 PR#7 of 7 — cross-SDK Diagnostic Protocol adoption. Mirror
SDK kailash-rs shipped PR#6 with the same absorb strategy.

**Rejected alternative**: The `/private/tmp/pcml-run26-template/shared/
mlfp06/diagnostics/governance.py::GovernanceDiagnostics` class (716 LOC)
was REJECTED per SYNTHESIS-proposal.md. It violated three PACT MUST
rules:

1. **Rule 8 (Thread Safety)** — bypassed `PactEngine._submit_lock`,
   racing audit-chain reads against in-flight submits.
2. **Rule 1 (Frozen GovernanceContext)** — exposed a non-frozen
   `GovernanceContext` dataclass to test code, creating a
   self-modification attack vector.
3. **Rule 4 (Fail-Closed)** — treated drill-probe exceptions as passes
   ("the probe errored, so the engine held the action"). Fail-OPEN.

## API Contract

### 1. `PactEngine.verify_audit_chain`

```python
async def verify_audit_chain(
    self,
    *,
    tenant_id: Optional[str] = None,
    start_sequence: int = 0,
    end_sequence: Optional[int] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> ChainVerificationResult:
    """Verify audit chain integrity within optional filters."""
```

**Returns**: `ChainVerificationResult(is_valid, verified_count,
first_break_reason, first_break_sequence, tenant_id, chain_id,
verified_at)`. Frozen dataclass.

**Invariants**:

- Acquires `self._submit_lock` before reading (PACT MUST Rule 8).
  Makes the verification atomic against a concurrent `submit()`'s
  audit append.
- Delegates integrity checking to the underlying
  `AuditChain.verify_chain_integrity()` which already uses
  `hmac.compare_digest` (constant-time comparison per
  `rules/trust-plane-security.md` MUST NOT Rule 1).
- Applies filters (tenant_id, sequence range, time range) AFTER the
  integrity walk, so tampering outside the filter window is still
  detected if it poisons prior hashes.
- Chain break → `is_valid=False` + `first_break_reason` +
  `first_break_sequence`. **NEVER raises on break** (PACT MUST Rule 4
  fail-closed). Only raises on impossible states (helper crashed).
- Breaks outside the filter window do NOT mark the window invalid —
  they are counted but not reported as the window's first break.

### 2. `PactEngine.envelope_snapshot`

```python
def envelope_snapshot(
    self,
    *,
    envelope_id: Optional[str] = None,
    role_address: Optional[str] = None,
    at_timestamp: Optional[datetime] = None,
    tenant_id: Optional[str] = None,
) -> EnvelopeSnapshot:
    """Return a frozen point-in-time envelope snapshot."""
```

**Returns**: `EnvelopeSnapshot(envelope_id, role_address, resolved_at,
clearance, constraints, tenant_id)`. Frozen dataclass.

**Invariants**:

- Exactly one of `envelope_id` or `role_address` MUST be provided;
  both or neither raises `ValueError`.
- The `role_address` path calls `GovernanceEngine.compute_envelope`
  which already acquires `self._lock` (PACT MUST Rule 8).
- The `envelope_id` path walks role nodes bounded by
  `MAX_TOTAL_NODES = 100_000` (PACT MUST Rule 7) and matches by
  `ConstraintEnvelopeConfig.id`.
- Unknown `envelope_id` or unresolvable `role_address` raises
  `LookupError`. AddressError / internal addressing failures are
  mapped to `LookupError` to prevent information leak.
- `at_timestamp` is reserved for future point-in-time rewind; today
  the returned `resolved_at` is always the actual resolution time.
- The returned snapshot carries only serialized `clearance` + `constraints`
  dicts — NEVER a live `GovernanceEngine` reference (PACT MUST Rule 1).

### 3. `PactEngine.iter_audit_anchors`

```python
def iter_audit_anchors(
    self,
    *,
    tenant_id: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = 10_000,
) -> Iterator[AuditAnchor]:
    """Yield persisted audit anchors within the requested filters."""
```

**Invariants**:

- Reuses the canonical `kailash.trust.pact.audit.AuditAnchor` type —
  no redefinition.
- Snapshots `chain.anchors` under a quick `list(...)` copy which
  serializes with the chain's internal append lock.
- `limit < 0` raises `ValueError`.
- `limit == 0` returns empty immediately.
- Tenant-ID filtering matches on anchor `metadata["tenant_id"]`.

### 4. `CostTracker.consumption_report`

```python
def consumption_report(
    self,
    *,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    envelope_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> ConsumptionReport:
    """Aggregate a frozen consumption report from self._history."""
```

**Returns**: `ConsumptionReport(total_microdollars, entries,
per_envelope, per_agent, since, until)`. Frozen dataclass.
`total_usd` property converts µ$ → USD.

**Invariants**:

- Acquires `self._lock` (PACT MUST Rule 8) during aggregation so the
  report is consistent against concurrent `record()` calls.
- Totals are in **microdollars** (USD × 1_000_000) for integer-math
  safety. Float-USD summation accumulates precision error over
  thousands of entries; integer µ$ does not.
- Rounding: per-entry amount converted via `round(value * 1_000_000)`
  after filtering so residual per-entry error stays within 1 µ$.
- Empty filter passes everything; empty history returns zero totals.
- Entries that failed `math.isfinite()` are silently skipped (defense-
  in-depth — `CostTracker.record` already rejects them).

### 5. `pact.governance.testing.run_negative_drills`

```python
def run_negative_drills(
    engine: PactEngine,
    drills: Sequence[Union[NegativeDrill, Tuple[str, Callable], Callable]],
    *,
    stop_at_first_failure: bool = False,
) -> list[NegativeDrillResult]:
    """Fail-CLOSED batch runner for negative governance probes."""
```

**Returns**: ordered `list[NegativeDrillResult]`, one per executed drill.

**Invariants — FAIL-CLOSED**:

- A drill that raises `GovernanceHeldError` → `passed=True` (engine
  correctly held the action).
- A drill that **returns normally** → `passed=False` (the engine
  should have refused but did not).
- A drill that raises **any OTHER exception type** → `passed=False`
  with `exception_type` set (the probe did not complete its check).
  **Exceptions from drills DO NOT mean "pass"** — this is the
  single biggest misuse pattern for negative probes and MLFP's
  rejected implementation got it wrong.
- Both `kailash.trust.pact.agent.GovernanceHeldError` and
  `pact.engine.GovernanceHeldError` are accepted as the pass-type.
- `stop_at_first_failure=True` short-circuits on the first non-passed
  drill.

**Scope**: This module is intended for use in test suites only —
production code MUST NOT import from `pact.governance.testing`.

## Security Threats + Mitigations

| Threat                                                       | Mitigation                                                                                                                  |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Audit-chain read races a submit's audit append               | `verify_audit_chain` acquires `self._submit_lock` (async) making check-remaining→execute→record-cost atomic (#292 pattern). |
| Snapshot carries mutable engine reference, enabling widening | `EnvelopeSnapshot` is `frozen=True`; carries only serialized dicts; live `GovernanceEngine` never leaks.                    |
| Drill probe errors silently count as passes                  | `run_negative_drills` treats every exception that is NOT `GovernanceHeldError` as a FAILURE.                                |
| Float-USD summation drift in long consumption reports        | `ConsumptionReport.total_microdollars` is integer-math microdollars; `total_usd` converts for display.                      |
| Identifier-based envelope_id path unbounded                  | `envelope_snapshot(envelope_id=...)` walks role nodes bounded by `MAX_TOTAL_NODES = 100_000` (PACT MUST Rule 7).            |
| Chain-break verification raises and masks the break details  | `ChainVerificationResult` carries `first_break_reason` + `first_break_sequence` on failure; never raises (fail-closed).     |

## Frozen Result Dataclasses

All result types live in `pact.governance.results`:

- `ChainVerificationResult`
- `EnvelopeSnapshot`
- `ConsumptionReport`
- `NegativeDrillResult`
- `AuditAnchor` (re-exported from `kailash.trust.pact.audit`; NOT
  re-defined)

All are `@dataclass(frozen=True)` per PACT MUST Rule 1. Re-exported at
package top-level (`from pact import ChainVerificationResult`) so
consumer code imports once.

## Cross-SDK Parity

Per EATP D6 (independent implementation, matching semantics):

- Rust SDK (kailash-rs) ships the same absorb strategy in PR#6 of
  the equivalent issue — five first-class methods on `PactEngine` /
  `CostTracker`, not a parallel `GovernanceDiagnostics` facade.
- The hash prefix and µ$ shape are stable across SDKs so the forensic
  correlation contract in `rules/event-payload-classification.md`
  Rule 2 holds across polyglot deployments.
- Convention names may differ (Python snake_case vs Rust snake_case)
  but semantics MUST match. A kailash-rs `CostTracker::consumption_report`
  returning the same `total_microdollars` on the same input is the
  cross-SDK test.

## Related Specs

- `specs/pact-addressing.md` — D/T/R addressing grammar, organization
  compilation, `GovernanceEngine`.
- `specs/pact-envelopes.md` — Operating envelopes (5 dimensions),
  clearance, 5-step access enforcement.
- `specs/pact-enforcement.md` — Audit chain, budget, events, work
  tracking, MCP governance, stores.
- `specs/ml-diagnostics.md` — DLDiagnostics adapter (sibling Diagnostic
  Protocol adopter, shares the frozen-result-dataclass pattern).
