# R1 Reviewer Verdict — Issue #1338 Tenant-Scoped EventBus (Python)

Branch: `feat/issue-1338-tenant-scoped-eventbus`
Reviewed: 2026-06-17
Scope: tenant.py + events/__init__.py + kailash/__init__.py + integration test + example

## VERDICT: APPROVE

No CRIT / HIGH / MED findings. Two LOW (non-blocking, optional). Implementation is
correct, well-documented, fully tested, and consistent with the EventBus surface.

---

## Mechanical Sweeps (all PASS)

| # | Sweep | Result |
|---|-------|--------|
| 1 | `pytest tests/integration/events/ -q` | **34 passed in 2.07s** (17 tenant + 17 base) |
| 2 | `pytest --collect-only -q tests/integration/events/` | **exit 0**, 34 collected |
| 3 | `'TenantScopedEventBus' in kailash.__all__` AND `in kailash.events.__all__` | **True True** |
| 4 | `from kailash import ... as a; from kailash.events import ... as b; assert a is b` | **SAME OBJECT OK** |
| 5 | Public-method direct-test coverage | **PASS** (see matrix below) |
| 6 | `python examples/eventbus_tenant_isolation.py` | **exit 0**, isolation demonstrated |

Per-variant direct-test matrix (testing.md "one direct test per variant"):
- `publish` — test_isolation_publish_fans_out_within_tenant_only, test_subscribe_returns_subscription_payload_is_original
- `subscribe` — test_subscribe_returns_subscription_payload_is_original, test_custom_separator_isolates
- `subscribe_events` — test_subscribe_events_delivers_logical_event_type, test_subscribe_events_isolated_across_tenants, test_event_type_containing_separator_roundtrips
- `close` — test_owns_bus_when_self_constructed, test_does_not_own_shared_bus
- `tenant_id` / `separator` / `bus` / `owns_bus` properties — test_properties_expose_config, test_owns_bus_when_self_constructed, test_does_not_own_shared_bus
- validation guards (empty tenant_id / separator-in-id / empty separator / empty event_type ×2) — 5 dedicated tests

Note on the pyright stale-index false positive: confirmed not investigated as a real
finding per instruction; mypy is disabled in .pre-commit-config.yaml and pyright is
not a CI gate. Runtime import + 34 passing tests are ground truth.

---

## LLM-Judgment Review

### Dispatch assumption — CONFIRMED
Read bus.py + backends.py. Both backends dispatch by EXACT event_type:
- `InMemoryEventBackend.publish` (backends.py:150-153): `self._subscribers.get(event.event_type)` — exact dict-key lookup.
- `RedisStreamsEventBackend` (backends.py:217-218): `_stream_key` = `f"kailash:events:{event_type}"`, one stream per type, consumer reads its own stream key.
Prefixing `{tenant_id}{sep}{event_type}` therefore yields STRUCTURAL isolation on both
backends with zero transport change. The module docstring's claim is accurate.

### API-shape consistency with EventBus — PASS
- `publish(event_type, payload, *, correlation_id=None, actor=None) -> None` mirrors
  EventBus.publish exactly (param names, order, keyword-only split, async-ness).
- `subscribe(event_type, handler) -> Subscription` — sync, matches EventBus.subscribe.
- `subscribe_events(event_type, handler) -> Subscription` — sync, matches.
- `close()` async, matches.
- Async-ness pairing (patterns.md "paired public surface consistent async-ness"):
  publish async / subscribe sync / close async — IDENTICAL to the wrapped EventBus.
  No mixed-async-ness drift.

### Un-prefix logic in subscribe_events — CORRECT
`_logical` (tenant.py:146-149) strips by `len(self._prefix)` slice, NOT by `.split()`.
This correctly preserves event types that themselves contain the separator
(`"ns:order:created"` round-trips intact — verified by
test_event_type_containing_separator_roundtrips). `replace(event, event_type=...)` uses
`dataclasses.replace` on the non-frozen `@dataclass DomainEvent`; the replace re-runs
`__post_init__` validation (logical type is non-empty, so the guard passes). Handler
receives the LOGICAL un-prefixed type + original payload + intact correlation_id/actor/
timestamp — verified by test_subscribe_events_delivers_logical_event_type.

### Ownership / close semantics — CORRECT
- `owns_bus=True` only when no bus passed (wrapper constructs its own) — closes it.
- `owns_bus=False` when a shared bus is passed — `close()` is a no-op on the shared bus.
- Verified by test_owns_bus_when_self_constructed + test_does_not_own_shared_bus (the
  latter asserts the shared bus survives a wrapper.close() and stays usable). This is the
  correct facade lifecycle — the caller owns the shared transport.

### Validation guards — CORRECT and security-relevant
- Empty/non-str tenant_id rejected; empty/non-str separator rejected.
- separator-in-tenant_id rejected (tenant.py:96-101): closes the cross-tenant-collision
  vector where a crafted id like `"acme:evil"` with sep `":"` could address another
  tenant's topics. This is the right structural guard, with a clear error message, and is
  tested for both default and custom separators.
- Empty event_type rejected on both publish and subscribe via `_scoped`.

### Zero-tolerance — PASS
No stubs, no TODO/FIXME, no silent fallbacks, no bare except. `_logical`'s non-prefix
branch is marked `# pragma: no cover - defensive` (correct — it is structurally
unreachable since the bus only delivers prefixed types to the wrapped subscriber).

### Docstring accuracy vs code — PASS
Module + class + method docstrings match behavior. The Redis-backend paragraph correctly
notes prefixing is the only isolation mechanism for a shared broker. The doctest-style
Example uses real API shapes.

### Observability note (informational, not a finding)
The wrapper adds no log lines of its own; it delegates to EventBus which logs publish/
subscribe at DEBUG with backend + correlation_id. For a thin prefixing facade this is
acceptable — no new integration boundary is crossed (it calls the same in-process bus).

---

## LOW Findings (optional, non-blocking)

**LOW-1 — Constructor kwargs (`backend` / `redis_url` / `max_subscribers`) are silently
inert when a `bus` is passed.** When `bus is not None`, the `backend`, `redis_url`, and
`max_subscribers` args are accepted but ignored (only the owned-bus branch consumes them).
This is the documented and intended behavior (they configure the auto-constructed bus
only), and the shared-bus case is the common path, so it is not a zero-tolerance Rule 3c
violation in spirit. Optional hardening: raise `ValueError` if a caller passes both a
`bus` AND any of these three kwargs, so a mis-wired call (`TenantScopedEventBus("acme",
shared_bus, backend="redis")` expecting redis) fails loudly instead of silently using the
shared bus's backend. Low priority — current behavior is internally consistent and
documented.

**LOW-2 — Example file location.** `examples/eventbus_tenant_isolation.py` sits at the
top-level `examples/` dir. Confirm this matches the repo's example-placement convention
(some SDK examples live under feature-scoped subdirs). Cosmetic; the file runs clean.

---

## Cross-SDK Parity Note (informational)
This is the Python side of kailash-rs #1352. Per cross-sdk-inspection.md Rule 3 (matching
semantics), the API shape (`publish`/`subscribe`/`subscribe_events`, tenant-prefix
isolation, logical-type delivery) should mirror the Rust wrapper's semantics. No
byte-level fingerprint contract applies here (no hashing helper), so Rule 4 byte-vector
pinning is N/A. Recommend a one-line confirmation at /codify that the Rust wrapper's
public method names + un-prefix-on-delivery behavior match this surface.
