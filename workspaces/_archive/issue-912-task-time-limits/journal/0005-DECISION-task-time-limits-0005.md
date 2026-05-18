---
type: DECISION
title: Shard 1 RC1 corrected from hard-remove to additive-scope `**kwargs`
date: 2026-05-09
session: 2026-05-09 PM
---

# Decision: Shard 1 RC1 corrected — additive scope, not hard-remove

## Context

The `/todos` plan (written 2026-05-09 AM) baked RC1 as "BROAD sweep across all `BaseRuntime` subclasses — drop `**kwargs`". Two parallel deep-dive verification agents (agent-1 + agent-2) flagged in the prior session that hard-removal of `**kwargs` from a public `execute(...)` signature in a minor version is BLOCKED by `zero-tolerance.md` Rule 6a — the rule mandates a `DeprecationWarning` shim covering at least one minor cycle plus a CHANGELOG migration entry before public-API removal. The agent-1 STOP correctness was acknowledged by the user; the user paused the shard at session-notes line 17 awaiting an explicit re-issue.

## Decision

Re-issue Shard 1 with **additive** scope:

- Add `*, soft_time_limit: float | None = None, time_limit: float | None = None` to every `BaseRuntime.execute(...)` subclass alongside the existing `**kwargs` (no removal).
- Pin tests assert PRESENCE of the new typed kwargs (not absence of `**kwargs`).
- `SoftTimeLimitExceeded` and `HardTimeLimitExceeded` subclass `RuntimeException` (sibling of `ResourceLimitExceededError`), NOT `WorkflowExecutionError`.
- Hard-removal of `**kwargs` is deferred to a separate next-major proposal that ships the Rule-6a-mandated deprecation shim + CHANGELOG migration entry.

User approved the corrected scope at session start 2026-05-09 PM in response to the orchestrator's recommendation question.

## Rationale

`zero-tolerance.md` Rule 6a is explicit: "Public-API removal MUST land with a `DeprecationWarning` shim covering at least one minor cycle, plus a CHANGELOG migration section explicitly documenting the 1.x → next-1.x callsite change. Removal-without-shim is BLOCKED." The signature `def execute(self, workflow, **kwargs)` is the public producer surface that downstream consumers (kailash-dataflow, kailash-nexus, third-party callers) depend on for forward-compat. Removing it in this shard would TypeError every existing callsite on first import after `pip upgrade`.

The additive scope delivers the user's `gh issue view 912` value (per-task soft/hard time limits) without the breaking-change risk. The silent-drop offender at `distributed.py:502-544` remains for one more minor cycle; the deprecation-cycle proposal removes it cleanly with a migration path.

## Implications

- LOC estimate drops from ~180 to ~130 (no `**kwargs` removal mechanical work).
- One fewer invariant to enforce (was 8, now 7) — invariant 2 inverts from "no `**kwargs` survives" to "`**kwargs` REMAINS PRESENT".
- Test assertions invert: pin PRESENCE of typed kwargs, drop assertions about `**kwargs` absence.
- Shard 1 still owns the signature surface for #911 (`queue=` kwarg) ordering — slot is `*, soft_time_limit, time_limit, [queue,] **kwargs`.
- Cross-SDK alignment with kailash-rs is unchanged — kailash-rs has no equivalent variadic kwargs surface (Rust enforces typed signatures structurally), so the "additive" framing IS the natural Rust shape; only Python carried the `**kwargs` artifact.

## Hard-Remove Deferral — Value Anchor

**Anchor:** `zero-tolerance.md` Rule 3c clean intent (typed signatures, no silent-drop) — keeps Rule 3c discipline visible without breaking minor-version contract. Filed as "next-major proposal" pending a `release/v3.0.0`-class change window.

## Re-pickup Re-validation

Per `value-prioritization.md` MUST Rule 3, this DECISION is the value-anchor for Shard 1 re-pickup. Re-validation at next session start: confirm `gh issue view 912` brief still names per-task soft/hard time limits as the active value; if yes, resume with this corrected scope.
