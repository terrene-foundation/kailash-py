# GAP — execute_async wraps ProtectionViolation; P1 alone fails I5 on runtime path

**Date:** 2026-05-17
**Phase:** /analyze (red-team gate)

## Finding (CRITICAL, caught by reviewer red-team)

`src/kailash/nodes/base_async.py:271-280` `execute_async` has a broad
`except Exception: raise NodeExecutionError(...)`; it re-raises ONLY
`NodeValidationError` / `NodeExecutionError` as-is. `ProtectionViolation`
(plain `Exception` subclass, `protection.py:163-181`) is therefore
WRAPPED in `NodeExecutionError` on the workflow-runtime path.

The fix-design `02-fix-design.md:304-315` claimed `execute_async` "lets
others propagate ✅" — factually wrong. Consequence: P1 (override
`ProtectedNode.async_run`) alone does NOT satisfy spec invariant I5
("`ProtectionViolation` MUST propagate to the caller") on issue #1050
AC#3 (`runtime.execute(workflow.build())`) for plain
`LocalRuntime`/`AsyncLocalRuntime`. Express path is unaffected (calls
`node.async_run` directly, no `execute_async` wrap; bulk paths confirmed
non-swallowing).

## Why journal-worthy

This is the red-team gate doing its job: the single-agent specialist
design inherited an unverified propagation claim; independent review
re-read `base_async.py` and falsified it. Recording per the /analyze
gate (red-team findings recorded before /todos) and zero-tolerance Rule 1
(found it, own it — folded back into design, not deferred).

## Disposition

Design returned to dataflow-specialist for: corrected propagation
analysis; one chosen fix option (a: `ProtectionViolation(NodeExecutionError)`
/ b / c) with `except NodeExecutionError` blast-radius grep; new
invariant I9 (audit-record-on-block); re-shard (likely Shard 1 → 1a
exception-taxonomy + audit, 1b async_run override + gap-test restore).
Re-converge red-team before the /todos human gate.

## Other red-team verdicts (sound, recorded)

- P1 MRO correctness: SOUND — no alternate async write path bypasses
  `DataFlowNode.async_run`; `AsyncSQLProtectionWrapper` sync-dead.
- Express exception propagation: SOUND and stronger than design stated —
  bulk\_\* have no try/except, propagate via try/finally.
- `read()` not-found filter: SOUND — `ProtectionViolation` message has no
  not-found substring.
- spec-accuracy of `specs/dataflow-protection.md` §4: COMPLIANT —
  present-tense conformance fact, no Phase/gap-tracker framing.
