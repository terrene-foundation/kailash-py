# Consolidated Resolution Plan: Issues #59-68

**Date**: 2026-03-24
**Scope**: All 9 open GitHub issues across kaizen-agents, kailash-pact, kailash core
**Execution model**: Autonomous (10x multiplier, parallel agent deployment)

## Issue Map

| Issue | Package             | Type         | Complexity  | Est. Effort                   | Dependencies           |
| ----- | ------------------- | ------------ | ----------- | ----------------------------- | ---------------------- |
| #68   | kaizen-agents       | security bug | Trivial     | 15 min                        | None                   |
| #67   | kaizen-agents       | bug          | Trivial     | 0 min (auto-resolves via #60) | Soft: #60              |
| #60   | kaizen-agents       | alignment    | Moderate    | 1-2 hours                     | None                   |
| #59   | kaizen-agents       | alignment    | Significant | 2-3 hours                     | Soft: #60              |
| #61   | kaizen-agents       | feature      | Moderate    | 2-3 hours                     | None                   |
| #66   | kaizen-agents       | feature      | Moderate    | 1-2 hours                     | None                   |
| #63   | kailash-pact + core | refactor     | Major       | 3-4 hours                     | #59, #60 inform design |
| #64   | kailash-pact        | feature      | Major       | 3-4 hours                     | #63, #61               |
| #65   | kaizen-agents       | stub removal | Moderate    | 2-3 hours                     | #61 for /plan          |

## Critical Discovery: Simplification Opportunities

The deep analyst estimated 28-38 hours. These can be compressed to ~15-18 hours through:

1. **#67 is a no-op after #60** — when DataClassification → ConfidentialityLevel, "restricted" maps correctly by definition

2. **#63 is mechanical** — 33 file moves + bulk import rewrite (`pact.governance.X` → `kailash.trust.pact.X`) + re-export shim. No logic changes. A disciplined agent with bash + sed can do this in 2-3 hours, not 6-10

3. **#59 uses adapter pattern** — instead of rewriting 20+ access patterns, create `ConstraintEnvelope` as a thin adapter over `ConstraintEnvelopeConfig`. Kaizen-agents code keeps dict-style access, adapter delegates to Pydantic model

4. **#64 is MVP only** — v0.4.0 PactEngine is the facade + GovernanceEngine ownership + lazy GovernedSupervisor. Work lifecycle protocols are interfaces with implementations, not stubs (satisfy no-stubs rule)

5. **#65 /compact is standalone** — LLM context summarization, no dependencies. /plan wires to existing GovernedSupervisor.run()

## Execution Plan: 5 Waves (revised after red-team)

### Wave 1: Quick Fixes + Independent Features (parallel, ~2 hours)

Three parallel streams, zero dependencies between them:

| Stream | Issue            | Work                                                                        | Files                                                                 |
| ------ | ---------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| A      | **#68**          | Add `os.chmod(path, 0o600)` after file writes, `mode=0o700` on dir creation | `delegate/session.py`                                                 |
| B      | **#66**          | CostModel class + wire UsageTracker → BudgetTracker                         | `governance/cost_model.py` (new), `supervisor.py`, `delegate/loop.py` |
| C      | **#65 /compact** | LLM-driven context summarization in AgentLoop                               | `delegate/builtins.py`, `delegate/loop.py`                            |

**Exit criteria**: All tests pass, security review for #68

### Wave 2: Type Alignment (sequential, ~3 hours)

Must be sequential because #59 benefits from #60 being done.

| Order | Issue   | Work                                                                                                                                                                                                                              | Files                                                                               |
| ----- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| 1     | **#60** | Replace `DataClassification` (IntEnum C0-C4) with `ConfidentialityLevel` (str Enum) from `kailash.trust`. Map: C0_PUBLIC→PUBLIC, C1_INTERNAL→RESTRICTED, C2_CONFIDENTIAL→CONFIDENTIAL, C3_SECRET→SECRET, C4_TOP_SECRET→TOP_SECRET | `governance/clearance.py`, `supervisor.py`, `governance/__init__.py`, ~8 test files |
| 2     | **#67** | Verify auto-resolved by #60. If not, one-line fix                                                                                                                                                                                 | `supervisor.py`                                                                     |
| 3     | **#59** | Create adapter: `ConstraintEnvelope` wraps `ConstraintEnvelopeConfig` with dict-style access for backward compat. Progressively replace direct construction sites                                                                 | `types.py`, `supervisor.py`, ~10 files                                              |

**Decision needed**: Is `C1_INTERNAL → RESTRICTED` acceptable? (Deep analyst flagged semantic gap)

**Decision needed**: Adapter pattern vs big-bang for #59?

### Wave 3: HELD Mechanism + Governance Migration (parallel, ~5 hours)

Two parallel streams:

| Stream | Issue   | Work                                                                                                                                                                                                                 | Files                                                  |
| ------ | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| A      | **#61** | Add `GovernanceHeldError` catch → node HELD state, `resolve_hold(node_id, approved)` method, `asyncio.Event` for pause/resume, timeout handling                                                                      | `supervisor.py`                                        |
| B      | **#63** | Move 33 files from `packages/kailash-pact/src/pact/governance/` → `src/kailash/trust/pact/`. Bulk rewrite imports. Add re-export shim in `pact/governance/__init__.py`. Add `pydantic>=2.6` to `kailash[pact]` extra | 33 source files, 40 test files, 2 pyproject.toml files |

**#63 mechanical steps**:

1. `mkdir -p src/kailash/trust/pact/`
2. `cp -r packages/kailash-pact/src/pact/governance/* src/kailash/trust/pact/`
3. Bulk rewrite: `from pact.governance.X` → `from kailash.trust.pact.X` in all moved files
4. Bulk rewrite: `from pact.governance` → `from kailash.trust.pact` in all moved files
5. Rewrite `pact/governance/__init__.py` as re-export shim from `kailash.trust.pact`
6. Update `kailash` pyproject.toml: add `pact = ["pydantic>=2.6"]` extra
7. Update `kailash-pact` pyproject.toml: version → 0.4.0, dep → `kailash[pact]>=2.1.0`
8. Update all test imports
9. Update kaizen-agents imports (`pact.governance.addressing` → `kailash.trust.pact.addressing`)
10. Run full test suite

**Risk mitigation for #63**: Keep re-export shim as backward compat for one release cycle. No deprecation warnings in v0.4.0 — add in v0.5.0.

### Wave 4: PactEngine + /plan (sequential, ~4 hours)

| Order | Issue         | Work                                                                                                                                                                                                        | Files                                                                                         |
| ----- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| 1     | **#64**       | Build PactEngine facade: YAML org loading, GovernanceEngine ownership, lazy GovernedSupervisor creation, submit() API, progressive disclosure (Layer 1/2/3), work submission types, cost tracker, event bus | `packages/kailash-pact/src/pact/engine.py` (new), `engine_config.py` (new), `work/` (new dir) |
| 2     | **#65 /plan** | Wire to GovernedSupervisor.run() for plan decomposition, display plan DAG in terminal                                                                                                                       | `delegate/builtins.py`                                                                        |

**PactEngine v0.4.0 scope** (per framework-advisor):

- PactEngine class with Layer 1/2/3 progressive disclosure
- GovernanceEngine integration (always present)
- GovernedSupervisor integration (lazy, requires kaizen-agents)
- WorkSubmission + WorkResult types (concrete, not stubs)
- Simple cost tracker (wraps BudgetTracker)
- Simple event bus (in-memory pub/sub)

**Defer to v0.5.0**: Approval queue, DataFlow integration, MCP integration, persistent events

## Dependency Graph (Validated)

```
Wave 1 (parallel, no deps)         Wave 2 (sequential)
┌──────┐ ┌──────┐ ┌───────────┐    ┌──────┐ → ┌──────┐ → ┌──────┐
│ #68  │ │ #66  │ │ #65/comp  │    │ #60  │   │ #67  │   │ #59  │
└──────┘ └──────┘ └───────────┘    └──────┘   └──────┘   └──────┘
                                                              │
Wave 3 (parallel, after Wave 2)    Wave 4 (sequential, after Wave 3)
┌──────┐   ┌──────┐                ┌──────┐ → ┌───────────┐
│ #61  │   │ #63  │───────────────→│ #64  │   │ #65/plan  │
└──────┘   └──────┘                └──────┘   └───────────┘
```

## Feasibility: Single Session

**With 4 waves, ~14 hours total with parallelization.**

Under the autonomous execution model (10x multiplier for mature COC):

- Waves 1+2 can overlap (Wave 1 streams are independent of Wave 2)
- Wave 3 streams are independent of each other
- Wave 4 is the only strict sequential segment

**Compressed timeline**: ~8-10 hours of focused autonomous execution across parallel agent streams. This is achievable in a single extended session but aggressive. The mechanical nature of #63 (bulk file moves) is the key enabler.

**Recommendation**: Execute all 4 waves. If time pressure forces a cut, defer #64 (PactEngine) and #65 /plan to next session — they are the terminal nodes. Waves 1-3 (#68, #67, #60, #59, #61, #63, #65/compact, #66) are achievable in one session with certainty.

## Decision Points for User

1. **C1_INTERNAL → RESTRICTED mapping (#60)**: Accept or add new ConfidentialityLevel?
2. **Adapter vs big-bang (#59)**: Adapter (safer, keeps dict access) or full Pydantic migration?
3. **PactEngine scope (#64)**: Full v0.4.0 or defer to next session?
4. **Backward compat window (#63)**: Re-export shim duration? (Recommend: one release, no warnings in v0.4.0)
5. **/plan depth (#65)**: Full multi-agent decomposition or simple "show plan DAG"?
