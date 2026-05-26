# DECISION — Option (a) re-base; red-team converged; load-bearing claims re-verified

**Date:** 2026-05-17
**Phase:** /analyze (red-team convergence)

## Decision

Fix #1050 via **Option (a)**: `class ProtectionViolation(NodeExecutionError)`

- P1 (`ProtectedNode.async_run` override, delete dead sync `run()`).
  Rejected (b) (discards typed exception, weakens tests) and (c) (does not
  cover Express path; needs P1 anyway).

## Red-team convergence (durable receipt)

- Round 1 (reviewer, agentId ad539333b16ec5d98): found CRITICAL —
  `base_async.py:277` wraps `ProtectionViolation` in `NodeExecutionError`
  on the workflow-runtime path; design's propagation ✅ was false. Plus
  HIGH (shard plan inherits it), HIGH (I9 missing), MEDIUM (Shard 1 over
  budget). Recorded journal 0002.
- Design revised (dataflow-specialist af3cd907a5d5d5cb9): Option (a) +
  I9 added + re-shard 1a/1b/2/3.
- Round 2 (general-purpose abe959fd13941b468): independently re-verified
  the two load-bearing claims Option (a) rests on —
  - CLAIM 1 (blast radius) TRUE: 9 production `except NodeExecutionError`
    sites; all class (i) re-raise or class (ii) off-CRUD-path; ZERO
    class (iii) swallow. `security_access_control.py:147` swallows but is
    an RBAC read node unreachable from a protected write. No
    `except ProtectionViolation`-after-`except NodeExecutionError`
    ordering hazard. All `pytest.raises(ProtectionViolation)` /
    `isinstance` sites still match via subclass.
  - CLAIM 2 (I9 existing behavior) TRUE: `_handle_violation`
    (`protection.py:418`) calls `auditor.log_violation` (appends event
    `:204` + `logger.warning` `:205`) BEFORE `raise` `:421`. Zero new
    code. I9 documents shipped behavior → spec-accuracy compliant.

**Convergence verdict:** CRITICAL resolved; revised design's load-bearing
claims independently TRUE; no new gaps. Receipts: this entry + journal
0001 (root cause) + 0002 (the CRITICAL). Per
`verify-resource-existence.md` MUST-4 (convergence claims cite durable
receipts) — agent IDs recorded above.

## Spec impact

`specs/dataflow-protection.md` §3 extended I1–I8 → I1–I9 (audit-on-block,
documents existing `_handle_violation` behavior — no gap flagged,
spec-accuracy compliant). §4 remains present-tense conformance fact.

## Why journal-worthy

The /analyze gate's purpose realized: single-agent design carried a false
propagation claim; two independent review rounds falsified then
re-verified. The fix is now a 5-LOC taxonomy change + the wiring, with
the public-API blast radius audited clean before any code is written.
