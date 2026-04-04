# Nexus + Governance Research — Issues #233, #231

## Issue #233: Prometheus /metrics + SSE HTTP Streaming

### Current State

**EventBus** (`packages/kailash-nexus/src/nexus/events.py`, lines 65-274):

- Complete in-process delivery via janus.Queue (thread-safe bridge)
- `publish()` — thread-safe, non-blocking
- `subscribe()` — returns asyncio.Queue
- `subscribe_filtered()` — predicate-based filtering
- `_dispatch_loop()` — async fan-out (lines 233-263)
- `get_history()` — bounded deque, capacity=256 (lines 176-204)
- **No HTTP/SSE endpoint exists**

**Performance Metrics** (`packages/kailash-nexus/src/nexus/core.py`, lines 544-549):

- Internal deques: workflow_registration_time, cross_channel_sync_time, failure_recovery_time, session_sync_latency
- `get_performance_metrics()` method (line 2580) returns raw deques
- **No prometheus_client integration**
- **No /metrics endpoint**

### Endpoint Registration Pattern

`packages/kailash-nexus/src/nexus/transports/http.py`, lines 220-228:

```python
def register_endpoint(self, path, methods, func, **kwargs):
    if self._gateway is not None:
        self._register_endpoint_internal(path, methods, func, **kwargs)
    else:
        self._endpoint_queue.append((path, methods, func, kwargs))
```

Both new endpoints follow this existing pattern.

### Implementation Plan

**Feature 1: /metrics** (complexity: LOW)

- Add `prometheus_client` dependency
- Create Gauge/Counter/Histogram metrics from existing internal deques
- Register `/metrics` endpoint returning `generate_latest()` in OpenMetrics format
- Wire into Nexus startup

**Feature 2: /events/stream SSE** (complexity: MEDIUM)

- Create `/events/stream` endpoint with `Content-Type: text/event-stream`
- Accept optional `?event_type=` query param for filtering
- Use `subscribe_filtered()` internally
- Stream as `data: {json}\n\n` format
- Handle client disconnect gracefully (cancel subscription)
- Match kailash-rs `sse_url()` method interface

---

## Issue #231: Governance Vacancy Check + Cross-SDK Alignment

### Current State: Bridge Approval

**Location**: `src/kailash/trust/pact/engine.py`

**approve_bridge()** (lines 1141-1249):

- Validates approver is LCA or compliance role (lines 1194-1213)
- Creates BridgeApproval with 24-hour TTL (lines 1217-1224)
- **BUG: No vacancy check on approver role**

```python
# Current code (lines 1195-1200) — only checks role authority, not vacancy
lca_str = str(lca)
is_lca = approver_address == lca_str
is_compliance = (
    self._compliance_role is not None
    and approver_address == self._compliance_role
)
```

**reject_bridge()** — **MISSING ENTIRELY**. No method exists.

### set_vacancy_designation() — Already Correct

`engine.py`, lines 1708-1712:

```python
if not node.is_vacant:
    raise PactError(
        f"Role at '{vacant_role}' is not vacant",
        details={"vacant_role": vacant_role, "is_vacant": False},
    )
```

Already rejects non-vacant roles. Needs test coverage though.

### Required Changes

| Change                                | Location             | Complexity                       |
| ------------------------------------- | -------------------- | -------------------------------- |
| Add vacancy check to approve_bridge() | engine.py ~line 1227 | Low (3-5 lines)                  |
| Add reject_bridge() method            | engine.py ~line 1250 | Low (~30 lines, mirrors approve) |
| Vacancy check in reject_bridge()      | Same                 | Low                              |
| Tests for all above                   | test_bridge_lca.py   | Medium                           |

### Cross-SDK Semantic Alignment

| Item                                     | Python Status                                              | Action                         |
| ---------------------------------------- | ---------------------------------------------------------- | ------------------------------ |
| DimensionName serialization (snake_case) | `"financial"`, `"data_access"` — snake_case                | Verify matches kailash-rs      |
| BridgeApprovalStatus default             | No status enum exists — BridgeApproval has no status field | Add enum if kailash-rs has one |
| VacancyDesignation expiry boundary       | `now < expires_at` (strictly less than)                    | Verify same in kailash-rs      |
| LCA algorithm equivalence                | Uses accountability_chain, walks deepest to shallowest     | Verify same in kailash-rs      |
| is_ancestor_of reflexivity               | IS reflexive (`self.is_ancestor_of(self)` → True)          | Verify same in kailash-rs      |
| D/T/R grammar enforcement                | `_validate_grammar()` — D/T must be followed by R          | Verify same in kailash-rs      |

### Test Gaps

- Missing: approve_bridge() with vacant approver (should fail)
- Missing: reject_bridge() method and semantics
- Missing: set_vacancy_designation() on filled roles (behavior correct, no test)
