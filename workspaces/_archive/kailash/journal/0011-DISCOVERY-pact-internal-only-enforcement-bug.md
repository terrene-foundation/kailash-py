---
type: DISCOVERY
date: 2026-03-30
created_at: "2026-03-30T15:50:00Z"
author: agent
session_id: session-6
session_turn: 12
project: kailash
topic: PACT internal_only enforcement blocked all actions without explicit is_external=False
phase: implement
tags: [pact, governance, enforcement, bug]
---

# PACT internal_only Enforcement Bug

## Finding

`CommunicationConstraintConfig.internal_only` defaults to `True`. The enforcement logic at `engine.py:714` used `is_external is not False`, which treated `None` (unspecified) as external communication. This caused 11 test failures where actions without `is_external` in their context were blocked even though they weren't external.

## Root Cause

```python
# Before (broken): blocks when is_external is None
if envelope.communication.internal_only and is_external is not False:

# After (fixed): blocks only when explicitly external
if envelope.communication.internal_only and is_external is True:
```

The semantic difference: "block unless proven internal" vs "block when proven external". The former requires every caller to explicitly declare `is_external=False` for every action, which is unreasonable. The latter only blocks actions that explicitly declare themselves as external.

## Impact

11 PACT unit tests were failing. Any production code creating envelopes without explicit communication config and calling `verify_action()` without `is_external=False` would have all actions blocked.

## Resolution

PR #179 — one-line fix. Released in kailash 2.3.1 and kailash-pact 0.5.0.

## For Discussion

1. If the default had been `internal_only=False` instead of `True`, would this bug have been caught during the original implementation, or would it have surfaced later as a security gap?
2. Should `ConstraintEnvelopeConfig` defaults be permissive (opt-in to restrictions) or restrictive (opt-out)? The fail-closed principle says restrictive, but the usability impact suggests permissive defaults with explicit tightening.
