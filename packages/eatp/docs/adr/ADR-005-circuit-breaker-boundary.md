# ADR-005: Circuit Breaker Boundary

**Status**: Accepted
**Date**: 2026-03-15

## Context

The EATP spec addendum identifies the circuit breaker as an enforcement/orchestration concern (D2 decision) that canonically belongs in `kailash-kaizen`. However, shipping it in a separate package would force all users to install kaizen just to get posture circuit breaking, even for simple single-SDK deployments.

## Decision

The circuit breaker primitive (`PostureCircuitBreaker`, `CircuitBreakerRegistry`) is retained in the EATP SDK for `pip install eatp` ergonomics. The canonical orchestration layer for multi-agent circuit breaker coordination is `kailash-kaizen`.

The EATP module provides the **primitive**: per-agent failure tracking, weighted threshold evaluation, three-state circuit (CLOSED/OPEN/HALF_OPEN), and posture downgrade on open.

Kaizen provides the **orchestration**: fleet-wide circuit breaker policies, cross-agent failure correlation, and recovery coordination.

## Rationale

- **Single-package ergonomics**: Users should get posture protection with `pip install eatp` alone, without needing kaizen for basic use cases.
- **Clear boundary**: EATP owns the primitive (per-agent state machine), kaizen owns the orchestration (fleet coordination). Neither duplicates the other.
- **Bounded collections**: All per-agent tracking dicts in the circuit breaker use `maxlen=10000` with oldest-10% trimming to prevent unbounded memory growth (EATP convention).
- **Monotonic escalation safety**: `_close_circuit` does NOT auto-restore postures. It only logs a suggestion. Restoring posture is an explicit human or kaizen-orchestrator action, preserving the monotonic escalation invariant (AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED, never downgrade).

## Consequences

- `eatp.circuit_breaker` module is part of the EATP public API and will follow EATP semver.
- Kaizen's circuit breaker orchestration wraps EATP's primitive rather than reimplementing it.
- Users who only need basic per-agent circuit breaking do not need kaizen.
- The module docstring documents this boundary for future contributors.
