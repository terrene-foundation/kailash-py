# ADR-002: Hook Scope Restriction to 4 Trust-Native Events

**Status**: Accepted
**Date**: 2026-03-14

## Context

Early designs included hooks for `PRE_TOOL_USE`, `POST_TOOL_USE`, and `SUBAGENT_SPAWN`. These are orchestration concerns, not trust protocol events.

## Decision

EATP hooks are limited to 4 events corresponding to the 4 EATP operations:

- `PRE_DELEGATION` / `POST_DELEGATION`
- `PRE_VERIFICATION` / `POST_VERIFICATION`

ESTABLISH and AUDIT are excluded (bootstrap and read-only respectively).

## Rationale

EATP defines 4 operations: ESTABLISH, DELEGATE, VERIFY, AUDIT. Hook interception points should mirror these. Tool use and subagent coordination are orchestration concerns that belong in kailash-kaizen, which has full context about agent execution.

## Consequences

- Orchestration hooks must be implemented in kailash-kaizen, not EATP.
- EATP hooks are simpler and more focused.
- Cross-SDK alignment is easier (fewer events to coordinate).
