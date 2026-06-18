# 0001 DECISION — #1338 tenant-scoped EventBus: helper-backed, not doc-only

Date: 2026-06-17
Issue: terrene-foundation/kailash-py #1338 (cross-SDK parity w/ kailash-rs #1352)
Branch: feat/issue-1338-tenant-scoped-eventbus

## Brief verification (ground truth, kailash 2.36.0 — issue probed 2.34.2)

The issue is a single MEDIUM parity gap, not ≥3 sub-issues. Verified every
factual claim against the live surface before building (parity-issue trap:
"framed from the Rust side, routinely probe the wrong namespace"):

- CLAIM: `kailash.events` exports `EventBus`, `InMemoryEventBackend`, `DomainEvent`.
  VERIFIED TRUE — `events.__all__` = EventBus, Subscription, DomainEvent,
  EventBackend, InMemoryEventBackend, RedisStreamsEventBackend, create_backend.
- CLAIM: no tenant-scoped pub/sub recipe exists.
  VERIFIED TRUE — zero `tenant` references in `src/kailash/events/*.py`.
- DISPATCH (design-load-bearing): both backends dispatch by EXACT event_type
  (InMemory `self._subscribers.get(event.event_type)`; Redis one stream key
  `kailash:events:<type>`). → topic-prefixing by tenant yields complete,
  backend-agnostic isolation with zero transport change.

## Decision

Ship a helper-backed wrapper `TenantScopedEventBus`, NOT doc-only.

Value-anchor (cross-SDK parity / EATP D6 — the issue is user-approved as the
queued workstream per prior session notes). AC permits "documented OR
helper-backed"; doc-only forces every app to re-roll tenant scoping and drift
on the isolation guarantee — the exact "we'll migrate later" debt
`framework-first` + `zero-tolerance` Rule 4 forbid (this IS the SDK).

## Design

- `f"{tenant_id}{separator}{event_type}"` prefixing over a SHARED EventBus.
- Isolation-integrity guard: tenant_id MUST NOT contain the separator
  (else `a:b`+`c` collides with `a`+`b:c`); separator + tenant_id non-empty.
- `subscribe_events` delivers the LOGICAL (un-prefixed) event_type via
  `dataclasses.replace`; un-prefix is by known-prefix-LENGTH (not split), so
  an event_type may itself contain the separator without breaking isolation.
- Ownership: self-constructed bus is owned + closed by `close()`; a shared
  bus is left open (caller owns lifecycle).

## Verification at implement-time

- 17/17 new Tier-2 tests pass; 34/34 events tests pass; collect-only exit 0.
- Runtime isolation proven (acme/globex cross-publish → zero cross-talk).
- Example `examples/eventbus_tenant_isolation.py` runs clean.
- pre-commit (black/isort/ruff/Tier-1) pass. pyright noise = stale-index
  false positive (not a CI gate here; mypy disabled).

## Redteam

R1: parallel reviewer + security-reviewer (tenant-isolation = security gate).
Receipts: 04-validate/R1-reviewer.md, 04-validate/R1-security.md.
