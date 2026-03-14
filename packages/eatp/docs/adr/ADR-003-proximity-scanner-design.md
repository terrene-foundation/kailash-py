# ADR-003: Standalone Proximity Scanner (Opt-In)

**Status**: Accepted
**Date**: 2026-03-14

## Context

Constraint proximity scanning detects when agents approach their limits. The question was whether to embed this in `StrictEnforcer` or keep it standalone.

## Decision

`ProximityScanner` is a standalone, opt-in component. It is not integrated into `StrictEnforcer` by default.

## Rationale

- **Backward compatible**: `StrictEnforcer()` with no arguments behaves identically to pre-proximity versions.
- **Composable**: Callers can use `ProximityScanner` with any enforcer or independently.
- **No surprise escalations**: Existing codebases won't suddenly get FLAGGED verdicts.

## Consequences

- Callers must explicitly create and attach a `ProximityScanner` to get proximity-based escalation.
- Proximity thresholds are configurable via `ProximityConfig` (defaults: flag=0.80, hold=0.95).
