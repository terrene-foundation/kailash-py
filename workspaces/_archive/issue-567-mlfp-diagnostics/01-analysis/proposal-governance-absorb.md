# Issue #567 — GovernanceDiagnostics Absorption Proposal

**Verdict**: REJECT MLFP `GovernanceDiagnostics` (716 LOC parallel facade). Absorb its capabilities into the existing PACT surface as described below. File as kailash-py#567-A (GovernanceEngine surface extension) + cross-SDK sibling ticket in `esperie/kailash-rs` (chain-fingerprint reconciliation + BP-051).

**Author**: pact-specialist
**Grounded against**: `src/kailash/trust/pact/engine.py` (3212 LOC), `src/kailash/trust/pact/audit.py` (585 LOC), `src/kailash/trust/pact/context.py` (222 LOC), `packages/kailash-pact/src/pact/costs.py::CostTracker` (128 LOC), `packages/kailash-pact/src/pact/governance/testing.py` (123 LOC — already exists).

---

## 1. Capability-By-Capability Disposition

| MLFP capability                       | Disposition     | Destination                                                                                              |
| ------------------------------------- | --------------- | -------------------------------------------------------------------------------------------------------- |
| Chain verification                    | **(A) Absorb**  | `GovernanceEngine.verify_audit_chain()` — new method                                                     |
| Budget consumption                    | **(D) Exists**  | Extend existing `pact.costs.CostTracker` with `consumption_report()` helper                              |
| Envelope snapshot                     | **(A) Absorb**  | `GovernanceEngine.envelope_snapshot()` — new method returning frozen dataclass                           |
| Negative drills                       | **(B) Testing** | `pact.governance.testing.run_negative_drills()` — add to existing testing namespace, marked experimental |
| Read-only audit walker (anchors iter) | **(A) Absorb**  | `GovernanceEngine.iter_audit_anchors(...)` — bounded, tenant-scoped reader                               |

**Why reject MLFP as-is**: its audit walker bypasses `GovernanceEngine._lock` (violates `rules/pact-governance.md` MUST #8 thread safety), constructs a non-frozen `GovernanceContext` for "drill" probes (violates MUST #1), and its negative-drill harness executes `check_access()` with a `diagnostic=True` flag that short-circuits fail-closed semantics (violates MUST #4). Those three violations are load-bearing — fixing them is the redesign.

---

## 2. `GovernanceEngine.verify_audit_chain()` — Exact Signature

```python
@dataclass(frozen=True)
class ChainVerificationResult:
    chain_id: str
    anchors_checked: int
    is_valid: bool
    first_break_sequence: int | None       # None if valid
    first_break_reason: str | None         # "content_hash_mismatch" | "prev_hash_mismatch" | "sequence_gap" | "genesis_not_null"
    genesis_hash: str                      # canonical "0"*64 sentinel (see §7)
    verified_at: datetime                  # UTC
    tenant_id: str | None                  # if audit store is tenant-partitioned

    def to_dict(self) -> dict[str, Any]: ...

def verify_audit_chain(
    self,
    *,
    tenant_id: str | None = None,
    start_sequence: int = 0,
    end_sequence: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> ChainVerificationResult:
    """Walk the audit chain, re-compute SHA-256s, verify prev_hash linkage.

    Read-only. Acquires self._lock shared window (engine has only one
    lock; MUST Rule 8). Returns a ChainVerificationResult dataclass —
    NEVER raises on chain break (a break is data, not an error). Raises
    TypedPactError only on missing store / tenant-missing / invalid range.
    Fail-closed per MUST #4: any exception inside the walker flips
    is_valid=False and records first_break_reason="walker_exception".
    """
```

- **Tenant isolation** (`rules/tenant-isolation.md` §5): if the underlying audit store persists `tenant_id`, the walker filters to that tenant; `None` means cross-tenant (admin only — enforced by existing `GovernanceEngine` permission checks).
- **Range discipline**: `start/end_sequence` and `since/until` are mutually composable; empty window returns `anchors_checked=0, is_valid=True`.
- **No dispatcher bypass**: when `TieredAuditDispatcher` is configured, verify iterates `ephemeral` chain AND the durable store, comparing anchors by `anchor_id`. Divergence surfaces as `first_break_reason="tier_divergence"`.

---

## 3. Budget Consumption — Canonical API

PACT's existing `pact.costs.CostTracker` already tracks USD cost (NOT microdollars — see §8). MLFP's budget-consumption telemetry is a **query view** over the existing tracker:

```python
@dataclass(frozen=True)
class ConsumptionReport:
    total_usd: float
    budget_usd: float | None
    utilization: float | None             # spent / budget, None if unbounded
    remaining_usd: float | None
    entries: int
    by_envelope_id: dict[str, float]       # envelope_id → usd
    by_agent_id: dict[str, float]          # agent_id → usd
    window_start: datetime | None
    window_end: datetime | None

def consumption_report(
    self,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    envelope_id: str | None = None,
    agent_id: str | None = None,
) -> ConsumptionReport: ...
```

- Add to `CostTracker` (128 LOC → ~180 LOC). Thread-safe (reuses existing `self._lock`).
- Requires extending `CostTracker._history` entries with `envelope_id` and `agent_id` (currently only `amount`, `description`, `timestamp`, `cumulative`). Backfill: new fields default to `None` for pre-existing history — older entries show up with `by_envelope_id[None]` / `by_agent_id[None]` buckets.
- **Microdollar question**: MLFP tracks USD-float like PACT. Kaizen `CostTracker` (separate surface in kailash-kaizen 2.5+) uses microdollar integers. PACT's governance budget and Kaizen's LLM cost are distinct concerns — they don't merge. Issue #567's wider AgentDiagnostics cost-routing (§1.5 of failure-points.md) is a separate workstream that MUST route LLM costs through kaizen's microdollar tracker; PACT governance budgets remain USD-float.

---

## 4. Envelope Snapshot

PACT's `GovernanceContext` exposes a snapshot of the **effective** envelope for a role at context-creation time. MLFP's "envelope snapshot" is the same concept but at-any-timestamp and by-envelope-id. Design:

```python
@dataclass(frozen=True)
class EnvelopeSnapshot:
    envelope_id: str
    kind: str                              # "role" | "task" | "effective"
    role_address: str | None
    task_id: str | None
    envelope_fields: ConstraintEnvelopeConfig  # already frozen via pydantic model_config
    parent_envelope_id: str | None
    snapshot_at: datetime
    tenant_id: str | None

def envelope_snapshot(
    self,
    *,
    envelope_id: str | None = None,
    role_address: str | None = None,
    at_timestamp: datetime | None = None,  # None = current state
    tenant_id: str | None = None,
) -> EnvelopeSnapshot: ...
```

- Exactly one of `envelope_id` or `role_address` required (typed error otherwise).
- `at_timestamp` requires envelope-history retention; Phase 1 accepts `None` only (current state). Phase 2 adds history (separate issue).
- Thread-safe via `self._lock`. Fail-closed: missing envelope raises `PactError` (not an access-control path — safe to raise).

---

## 5. Negative Drills — Disposition: `pact.governance.testing`

**Decision**: absorb into `pact.governance.testing` (already exists, already houses `MockGovernedAgent`), NOT into production surface, NOT rejected outright.

```python
# packages/kailash-pact/src/pact/governance/testing.py (add to existing file)

@dataclass(frozen=True)
class NegativeDrillResult:
    drill_id: str
    role_address: str
    attempted_action: str
    expected: Literal["BLOCKED", "HELD"]
    observed: str                          # AUTO_APPROVED | FLAGGED | HELD | BLOCKED
    passed: bool

def run_negative_drills(
    engine: GovernanceEngine,
    drills: list[NegativeDrill],
    *,
    stop_at_first_failure: bool = False,
) -> list[NegativeDrillResult]:
    """Execute drill scripts that MUST be denied; assert real denial.

    This is TEST HARNESS code. Production code paths MUST NOT import it.
    Runs every drill through the SAME `engine.verify_action` / `check_access`
    entry points a real agent would — never short-circuits fail-closed.
    """
```

- Lives in the testing namespace so production `import pact` never surfaces it.
- Production safety: uses `engine.verify_action()` directly (no `diagnostic=True` shortcut), so MUST #4 fail-closed is preserved. A drill that the engine "passes" (returns AUTO_APPROVED for a forbidden action) is a real governance bug and surfaces as `passed=False`.
- The existing `MockGovernedAgent` already proves this pattern works.

---

## 6. TraceEvent ↔ AuditEntry Reconciliation

Separate concerns, keep separate types, enforce **shared fingerprint contract**:

- `AuditAnchor` (kailash.trust.pact.audit): governance-layer append-only chain record. Owner: PACT. Carries SHA-256 `content_hash` + `previous_hash`.
- `TraceEvent` (Kaizen observability, landing in PR #5 of #567 sequence): agent-execution observability record. Owner: Kaizen. Does NOT need a chain — emit through `kaizen.observability.TracingManager`.
- **Bridge**: when an agent run produces a governance event (tool denied, envelope tightened), emit BOTH: a `TraceEvent` (for the agent's timeline) AND an `AuditAnchor` (for PACT's chain), correlated by the same `correlation_id`. Neither wraps the other.

Per `rules/event-payload-classification.md` MUST Rule 2, any shared identifiers (agent_id, role_address) that are classified MUST be hashed with the canonical 8-hex-prefix SHA-256 fingerprint so Python and Rust observers can correlate.

---

## 7. Canonical SHA-256 Chain Format (Cross-SDK)

**Blocker for cross-SDK**: four existing chain implementations drift (kailash-core `audit_log`, kailash-enterprise `audit/sqlite`, kailash-pact `audit`, eatp `ledger` per `kailash-rs-parity.md` §5). The one-true spec BOTH SDKs MUST adopt:

```
# Genesis sentinel
GENESIS_PREV_HASH = "0" * 64           # 64 hex chars, lowercase
# (chosen over "" / NULL: gives every anchor a non-empty previous_hash
#  field, simplifies range iteration, matches kailash-py's current
#  _GENESIS_HASH constant in trust/audit_store.py)

# Canonical input string (UTF-8, no trailing newline)
#   SHA-256 input = "{anchor_id}:{sequence}:{previous_hash}:{agent_id}:
#                    {action}:{verification_level}:{envelope_id}:
#                    {result}:{timestamp_iso8601_utc}[:{metadata_json_sorted_keys}]"
#
# Where:
#   previous_hash        — GENESIS_PREV_HASH for sequence 0, else the
#                          prior anchor's content_hash hex
#   envelope_id          — empty string "" when None (never the literal "None")
#   timestamp_iso8601_utc — datetime.now(UTC).isoformat(), RFC 3339,
#                           MUST include "+00:00" suffix (no "Z")
#   metadata_json        — json.dumps(metadata, sort_keys=True,
#                          default=str, ensure_ascii=True,
#                          separators=(",", ":"))  # no whitespace
#                          appended ONLY if metadata is non-empty
#
# content_hash = hashlib.sha256(input.encode("utf-8")).hexdigest()
# prev_hash stored on the NEXT anchor equals this value verbatim

# Chain verification = for every anchor N≥1,
#   assert anchor[N].previous_hash == anchor[N-1].content_hash
# Using hmac.compare_digest() (constant-time), per rules/trust-plane-security.md MUST #1.
```

**kailash-py today**: `AuditAnchor.compute_hash()` (audit.py:179) matches this contract EXCEPT it writes `"genesis"` instead of `"0"*64` for the sequence-0 sentinel. Fix is a one-line change + a Tier 2 round-trip test per `rules/orphan-detection.md` §2a (crypto-pair round-trip through facade).

**kailash-rs today**: four drifted implementations. BP-051 prerequisite is a reconciliation PR that aligns all four on the above.

---

## 8. One-Line API Signatures

```python
# New on GovernanceEngine (all thread-safe, all fail-closed):
engine.verify_audit_chain(*, tenant_id=None, start_sequence=0, end_sequence=None, since=None, until=None) -> ChainVerificationResult
engine.envelope_snapshot(*, envelope_id=None, role_address=None, at_timestamp=None, tenant_id=None) -> EnvelopeSnapshot
engine.iter_audit_anchors(*, tenant_id=None, since=None, until=None, limit=10_000) -> Iterator[AuditAnchor]

# Extension to existing pact.costs.CostTracker:
tracker.consumption_report(*, since=None, until=None, envelope_id=None, agent_id=None) -> ConsumptionReport

# Test-only (pact.governance.testing):
run_negative_drills(engine, drills, *, stop_at_first_failure=False) -> list[NegativeDrillResult]
```

All three engine methods acquire `self._lock` (MUST #8). All dataclasses are `frozen=True` (MUST #1). `ChainVerificationResult.is_valid=False` on ANY walker error (MUST #4). Genesis sentinel + canonical input string per §7 — cross-SDK identical.

---

## 9. Closing Disposition

- Close #567 GovernanceDiagnostics item with link to new ticket **#567-A** (this proposal).
- File cross-SDK sibling issue in `esperie/kailash-rs` titled "Cross-SDK audit fingerprint canonicalisation" — MUST land BEFORE BP-051.
- Existing 716 LOC of MLFP GovernanceDiagnostics: DO NOT upstream. Point MLFP contributors at this proposal.
