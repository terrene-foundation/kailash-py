# Red Team Consolidated: Analysis Phase

**Date**: 2026-03-23
**Red Team Agents**: deep-analyst, requirements-analyst, coc-expert
**Scope**: Ground truth audit (doc 17), deconfliction (doc 18), revised plan (doc 02-revised), user flows (doc 02-flows)

---

## Convergent Findings (flagged by 2+ agents)

### CC1: Ground Truth Audit Got Protocols Wrong [CRITICAL]

**Flagged by**: All three agents independently.

The audit claimed protocols are "type stubs only." Reality:

- `delegation.py`: 399 lines, fully implemented
- `clarification.py`: 341 lines, fully implemented
- `escalation.py`: 390 lines, fully implemented

All three have real LLM-driven composition and response parsing. What IS missing is the **message transport layer** — no MessageRouter.route() calls, no MessageChannel consumption, no correlation tracking.

**Correction needed**:

- Fix doc 17 section on protocols
- Rescope P1-01 from "implement protocols" to "wire protocol implementations to SDK MessageRouter"

### CC2: SDK Type Migration Is Not a Simple Import Swap [CRITICAL]

**Flagged by**: deep-analyst (RT-01, RT-06, RT-07), requirements-analyst (H1, H2, M2)

Three specific type mismatches:

1. **ConstraintEnvelope does not exist in SDK** — SDK uses PACT typed dataclasses (e.g., `financial.max_spend_usd`), not raw dicts (`financial["limit"]`)
2. **GradientZone casing mismatch** — local uses lowercase (`"auto_approved"`), SDK uses UPPERCASE (`"AUTO_APPROVED"`)
3. **PlanModification factory methods** may not exist in SDK

The plan's P0-01 ("delete types.py, create thin adapter") understates the scope. This is a structural translation, not an import swap.

**Correction needed**:

- P0-01 must start with a compatibility matrix before any code changes
- Estimate 65 test rewrites (test_types.py) + ~50 test modifications across other files

### CC3: PlanMonitor Executes Nodes Sequentially [CRITICAL]

**Flagged by**: requirements-analyst (C3)

The `for node_id in ready_nodes:` loop executes independent nodes one at a time. The user flows assume parallel execution. This must be addressed in P0-02.

**Correction needed**: P0-02 must include asyncio.gather() or bounded semaphore for parallel node execution.

### CC4: NaN Vulnerabilities in monitor.py [HIGH → must fix now per zero-tolerance]

**Flagged by**: requirements-analyst (M3, M4)

Two NaN attack vectors:

1. `_check_budget()` — NaN cost passes through to AUTO_APPROVED
2. Cost accumulation — `NaN + anything = NaN` permanently poisons total_cost

Per `rules/trust-plane-security.md` Rule 3 and `rules/zero-tolerance.md` Rule 1: pre-existing defect, must fix.

**Correction needed**: Fix in monitor.py before any other work.

---

## Non-Convergent but Valid Findings

### NC1: CLI Architectural Invariant Conflicts with Plan [HIGH]

**Flagged by**: deep-analyst (RT-05), requirements-analyst (H4)

`loop.py` line 14-16: "kz core loop MUST NOT use Kaizen Pipeline primitives."
Plan P0-05: "Wire CLI through PlanMonitor for multi-agent work."

Needs ADR to resolve.

### NC2: Plan Does Not Map to PACT SDK Types [HIGH]

**Flagged by**: requirements-analyst (H3)

Phase 2 (governance) describes requirements conceptually but doesn't reference the existing PACT SDK classes: `GovernanceEngine`, `PactGovernedAgent`, `GovernanceEnvelopeAdapter`, `AuditChain`, `GradientEngine`.

Needs a PACT SDK integration map before Phase 2 begins.

### NC3: Cross-Repo Deconfliction Has No Enforcement Mechanism [HIGH]

**Flagged by**: coc-expert (H1)

The doc defines ownership boundaries on paper. No hook, CI check, or session-start validation enforces them across repos.

### NC4: Session Notes Propagate "M2 Complete" Claim [MEDIUM]

**Flagged by**: coc-expert (M4)

Session notes say "M2: Complete orchestration layer (370 tests)." This carries forward to future sessions via session-start hook. Needs correction.

### NC5: PlanExecutor State Machine Ownership Undefined [HIGH]

**Flagged by**: deep-analyst (RT-02)

Plan says "do NOT call SDK PlanExecutor" but "use SDK Plan types." SDK PlanExecutor mutates `plan.state` directly. If we own execution but use SDK Plan types, who owns state transitions? Split-brain risk.

### NC6: No Verification of "Three Hard Truths" Against Actual SDK [HIGH]

**Flagged by**: coc-expert (H4)

The Hard Truths come from kailash-py's red team. Were they verified against the actual kailash-py v2.1.0 source in this session? Given this audit got protocols wrong, trusting cross-repo findings without verification is risky.

### NC7: Session Estimate Should Be 10-12, Not 6-8 [MEDIUM]

**Flagged by**: deep-analyst (session estimate section), requirements-analyst (M6)

Phase 2 alone needs 3-4 sessions (governance is 8 sub-tasks from empty). Type migration is a rewrite, not a swap.

### NC8: 5 P0 Authority Matrix Features Missing from Plan [HIGH]

**Flagged by**: deep-analyst

Streaming, file exclusion (.kzignore), MCP client, effort levels, and project context verification are P0 in the authority feature matrix but absent from the revised plan.

### NC9: No Rollback Strategy for Phase 0 [LOW]

**Flagged by**: coc-expert (L1)

If SDK wiring breaks the test suite in unfixable ways, there's no documented recovery path.

---

## Corrections Required Before /todos

1. **Fix doc 17** — correct protocol claims, add evidence (line counts)
2. **Fix revised plan** — rescope P1-01, add compatibility matrix to P0-01, add parallel execution to P0-02, add P0 authority matrix features
3. **Verify Three Hard Truths** — inspect kailash-py v2.1.0 PlanExecutor, HELD, and Signatures directly
4. **Fix NaN vulnerabilities** — monitor.py, immediately
5. **Run pytest** — verify the 690 test claim
6. **Update session notes** — M2 is NOT complete against SDK
7. **Revise session estimate** — 10-12 sessions
8. **Create ADR for CLI invariant** — resolve P0-05 conflict

---

## Disposition

| ID  | Severity | Action                                     | Owner                         |
| --- | -------- | ------------------------------------------ | ----------------------------- |
| CC1 | CRITICAL | Correct doc 17, rescope P1-01              | This session                  |
| CC2 | CRITICAL | Add compatibility matrix to P0-01          | This session                  |
| CC3 | CRITICAL | Add parallel execution to P0-02            | This session                  |
| CC4 | HIGH     | Fix NaN in monitor.py                      | This session (zero-tolerance) |
| NC1 | HIGH     | Create ADR for CLI invariant               | This session                  |
| NC2 | HIGH     | PACT SDK integration map for Phase 2       | Phase 2 start                 |
| NC3 | HIGH     | Cross-repo enforcement mechanism           | Deferred (future session)     |
| NC4 | MEDIUM   | Update session notes                       | This session                  |
| NC5 | HIGH     | Define state transition ownership in P0-02 | This session                  |
| NC6 | HIGH     | Verify Hard Truths against actual SDK      | This session                  |
| NC7 | MEDIUM   | Revise to 10-12 sessions                   | This session                  |
| NC8 | HIGH     | Add missing P0 features to plan            | This session                  |
| NC9 | LOW      | Document rollback strategy                 | This session                  |
