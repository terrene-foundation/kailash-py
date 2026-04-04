# COC Artifact Red Team Report — 2026-04-04

## Executive Summary

13 parallel red team agents audited the entire COC artifact surface (37 agents, 421 skills, 29 rules = ~112K lines) against the actual Kailash SDK source code in kailash-py.

| Severity | Count | Impact                                                              |
| -------- | ----- | ------------------------------------------------------------------- |
| CRITICAL | 62    | Would cause import errors, runtime crashes, or generate broken code |
| HIGH     | 103   | Incomplete, misleading, or wasting significant tokens               |
| MEDIUM   | ~75   | Could be improved                                                   |
| LOW      | ~40   | Minor optimizations                                                 |

### Seven Systemic Failure Patterns

| #   | Pattern                                                                                           | Scope                              | Est. Files Affected |
| --- | ------------------------------------------------------------------------------------------------- | ---------------------------------- | ------------------- |
| P1  | **Phantom APIs/Nodes** — Skills reference classes, methods, and nodes that don't exist in the SDK | All framework skills               | 50+                 |
| P2  | **Wrong Import Paths** — Pervasive across Kaizen, PACT, EATP, Core SDK                            | Kaizen, PACT, EATP, Core SDK       | 40+                 |
| P3  | **Hardcoded Model Names** — Systematic violation of env-models.md                                 | All framework skills               | 60+ occurrences     |
| P4  | **Hollow Stub Skills** — Auto-generated boilerplate with zero real content                        | Core SDK, Security, Arch Decisions | 15+ files           |
| P5  | **Stale/Contradictory Rules** — CLAUDE.md vs agents.md, rules referencing phantom functions       | Rules, CLAUDE.md                   | 8 rules             |
| P6  | **Broken Cross-References** — Dangling file paths to renamed/removed files                        | All categories                     | 30+ refs            |
| P7  | **Token Waste** — Duplicate rules, unscoped domain rules, stubs consuming context                 | Rules, Skills                      | ~3,400 lines/turn   |

---

## Findings by Agent Area

### 1. Nexus (9 CRITICAL, 10 HIGH)

**CRITICAL:**

- C1: SKILL.md Quick Start `Nexus([workflow])` and `nexus.run()` — NEITHER EXISTS. Correct: `Nexus()` + `app.register()` + `app.start()`
- C2: SKILL.md DataFlow integration `db.get_workflows()` — method doesn't exist
- C3: HTTPTransport constructor shows `host` parameter — doesn't exist
- C4: HandlerParam uses `type=str` — actual field is `param_type: str` taking string values
- C5: `registry.handlers` — private `_handlers`, no public attribute
- C6: `subscribe_filtered(event_filter=, handler=)` — actual signature is `subscribe_filtered(predicate)` returning Queue
- C7: `NexusFile.data` — private `_data`, public API is `file.read()`
- C8: Workflow registration uses `metadata=` in 10+ examples after documenting it doesn't exist
- C9: `BackgroundService.is_running` — actual method is `is_healthy`

**HIGH:**

- H3: `app.workflows` doesn't exist (private `_workflows`)
- H4: Troubleshooting references 6+ fabricated constructor params and methods
- H5: `session_manager.extend_timeout()`, `.exists()` don't exist
- H9: `auto_discovery` default documented as True, actual is False

### 2. Kaizen (8 CRITICAL, 8 HIGH)

**CRITICAL:**

- C1: `agent-reasoning.md` (GLOBAL RULE): `from kaizen.orchestration.pipeline import Pipeline` — path doesn't exist
- C2: `patterns.md` (GLOBAL RULE): `from kaizen.core import BaseAgent, Signature` — kaizen.core doesn't export these
- C3: `patterns.md`: `from kaizen.core.registry import AgentRegistry` — module doesn't exist
- C4: SKILL.md Blackboard: `agents=` should be `specialists=`, `discovery_mode=` should be `selection_mode=`
- C5: `kaizen-orchestration.md`: ENTIRE SKILL uses nonexistent `kailash_kaizen` package — every example crashes
- C6: Same skill teaches keyword-based routing — BLOCKED anti-pattern
- C7: `agent-reasoning.md`: `agent.solve()` is not a method on ReActAgent, `tools="all"` not valid
- C8: `kaizen-tool-calling.md`: `tools="all"` not a BaseAgent parameter (actual: `mcp_servers`)

**HIGH:**

- H1: 30+ hardcoded model names across ALL Kaizen skills
- H3: Stale `kaizen-orchestration.md` should be removed entirely

### 3. Core SDK (6 CRITICAL, 11 HIGH)

**CRITICAL:**

- C1: `custom-node-guide.md` ENTIRELY FICTIONAL — `register_callback()` doesn't exist anywhere
- C2: `connect()` with 4 positional args triggers runtime error
- C3: SwitchNode ports `"true"/"false"` — actual: `"true_output"/"false_output"`
- C4: ENTIRE `kailash.nodes.ai` module doesn't exist — LLMAgentNode, IterativeLLMAgentNode are phantom
- C5: `ExcelReaderNode` doesn't exist
- C6: `AsyncLocalRuntime.execute_workflow_async()` return value documented inconsistently (tuple vs single)

**HIGH:**

- H2: ~15 phantom nodes in nodes-quick-index.md (WhileNode, ConditionalRouterNode, AggregationNode, MCPToolNode, etc.)
- H3-H7: 6 of 21 core-sdk skills are HOLLOW STUBS (async-workflow-patterns, error-handling-patterns, pythoncode-best-practices, mcp-integration-guide, cycle-workflows-basics [says NOT IMPLEMENTED but IS], switchnode-patterns)
- H8: cycle-workflows-basics says "PLANNED - NOT IMPLEMENTED" but cycles ARE implemented
- H9: kailash-quick-tips cheatsheet is a hollow stub

### 4. DataFlow (5 CRITICAL, 6 HIGH)

**CRITICAL:**

- C1: SKILL.md node names `{Model}_Create` — actual: `{Model}CreateNode`
- C2: `connection_string` parameter — actual: `database_url`
- C3: `db.get_workflows()` doesn't exist
- C4: Result access `results["create_user"]["result"]` — wrong key
- C5: Agent says `existing_schema_mode` and `enable_model_persistence` "REMOVED" — they still exist

### 5. PACT (5 CRITICAL, 9 HIGH)

**CRITICAL:**

- C1: ALL skills use `pact.governance.X` sub-module imports — sub-modules DON'T EXIST (actual: `kailash.trust.pact.X`)
- C2: `Address.parse("Engineering-CTO-Backend-...")` — expects `D1-R1-T1-R3` notation
- C3: `load_org_yaml` returns `LoadedOrg`, not `OrgDefinition` — passed wrong to engine
- C5: pact-governance.md RULE shows `Address(org="acme", dept="engineering")` — actual constructor takes `segments` tuple only

**HIGH:**

- H4: GovernanceContext has `from_dict()` contradicting stated security invariant
- H6: PactEngine, WorkResult, WorkSubmission, CostTracker, EventBus undocumented

### 6. Rules Consistency (5 CRITICAL, 6 HIGH)

**CRITICAL:**

- C1: CLAUDE.md Directive 5 says reviews "NO exceptions" vs agents.md says "RECOMMENDED" + "users may skip"
- C2: testing.md references non-existent e2e-god-mode.md Rule 6
- C3: trust-plane-security.md references `safe_open` function — DOESN'T EXIST
- C4: pact-governance.md references `GovernanceViolationError` — DOESN'T EXIST
- C5: pact-governance.md scope misses primary PACT source location

**HIGH:**

- H1: 8 rules duplicated between loom/ and kailash-py/ (~1,225 lines wasted/turn)
- H2: 7 domain-specific rules lack `paths:` frontmatter (~1,103 lines wasted/turn)
- H3: connection-pool.md references non-existent `pool-safety` skill
- H4: No rules for kailash-ml, kailash-align, kaizen-agents, kailash-nexus, kailash-ml-protocols

### 7. Frontend (5 CRITICAL, 6 HIGH)

**CRITICAL:**

- C1: Broken skill paths in react-specialist and flutter-specialist agents (`../../.claude/skills/` — extra .claude/)
- C2: Dangling `enterprise-ai-hub-uiux-design.md` guide reference
- C3: Three dangling cross-references in interactive-widgets overview
- C4: Fabricated `streaming=True` and `/stream` endpoint
- C5: Hardcoded `"gpt-4"` in both quick-start skills

**HIGH:**

- H1: `frontend-developer` almost entirely duplicates `react-specialist` — merge candidate
- H2: Skills use `WorkflowAPI` (primitive) instead of Nexus (engine) — violates framework-first

### 8. Standards (4 CRITICAL, 6 HIGH)

**CRITICAL:**

- C1: 4 of 5 TrustPosture enum values WRONG (FULL_AUTONOMY→DELEGATED, ASSISTED→CONTINUOUS_INSIGHT, HUMAN_DECIDES→SHARED_PLANNING, BLOCKED→PSEUDO_AGENT)
- C2: Import path `kailash.trust.postures` — actual: `kailash.trust.posture`
- C3: care-expert says "CARE is an Execution Plane tool" — inverts the meaning
- C4: EATP skills internally inconsistent on posture names

**HIGH:**

- H2: Stale counts everywhere (claims 30 agents/9 rules, actual 37/29)
- H3: coc-expert claims "Seven-phase workflow" — CLAUDE.md shows 5, CO reference shows 6

### 9. MCP (3 CRITICAL, 13 HIGH)

**CRITICAL:**

- C1: `@server.tool()` call pattern wrong
- C2: `@server.resource()` usage wrong
- C3: `JWTAuth` parameter name wrong

**HIGH:**

- H7: `mcp-integration-guide.md` is a STUB referenced by 4 skills
- H8: IterativeLLMAgentNode requires kailash-kaizen but skills don't mention it
- Systematic hardcoded model names across ALL MCP skills

### 10. Infrastructure (3 CRITICAL, 8 HIGH)

**CRITICAL:**

- C1: MySQL `blob_type()` returns `LONGBLOB`, skill says `BLOB`
- C2: `upsert()` signature omits 4th parameter `update_columns`
- C3: **ACTUAL SDK BUG** — `store_result()` doesn't update `expires_at`, so idempotency TTL is 5min not 1hr

### 11. ML/Align (1 CRITICAL, 5 HIGH)

**CRITICAL:**

- C1: Align agent falsely claims ALL configs are `frozen=True` — AlignmentConfig is mutable

**HIGH:**

- H1: CLAUDE.md says "9 engines" — actual count is 13
- H2: ML claims chi2/jensen_shannon drift methods — don't exist in code
- H3: `RegistryCapacityError` doesn't exist

### 12. Quality Agents (4 CRITICAL, 8 HIGH)

**CRITICAL:**

- C1: 3-way contradiction on review mandate strength (security-reviewer, CLAUDE.md, agents.md)
- C2: 18-security-patterns SKILL.md references 8 NONEXISTENT files
- C3: gold-standards-validator uses `LS` — not a valid Claude Code tool
- C4: value-auditor references 2 nonexistent agents

**HIGH:**

- H1: intermediate-reviewer doesn't check for agent-reasoning violations (despite being named as enforcer)
- H2: intermediate-reviewer doesn't check for no-stubs violations
- H6: e2e-runner ignores all 5 e2e-god-mode rules
- H7: testing SKILL.md uses wrong directory names

### 13. Analysis/Planning (4 CRITICAL, 7 HIGH)

**CRITICAL:**

- C1: `APICallNode` phantom — referenced in 20+ files, actual: `HTTPRequestNode`
- C2: `DatabaseExecuteNode` phantom — referenced in 20+ files, actual: `SQLDatabaseNode`
- C3: `DataValidationNode` phantom
- C4: Three architecture decision skills are empty stubs

**HIGH:**

- H1: deep-analyst has NO awareness of Kailash frameworks (only governance/constitutional)
- H2: framework-advisor omits ML, Align, and PACT frameworks entirely
- H4: requirements-analyst uses "human-days" — violates autonomous-execution rule
- H7: `ConditionalNode` used in ~30 workflow patterns — actual: `SwitchNode`

---

## Token Efficiency Analysis

### Current Waste (estimated per-turn loading)

| Source                                  | Lines Wasted | Cause                                    |
| --------------------------------------- | ------------ | ---------------------------------------- |
| 8 duplicate rules (loom/ + kailash-py/) | ~1,225       | Both versions load without path scoping  |
| 7 unscoped domain rules                 | ~1,103       | Missing `paths:` frontmatter             |
| Hollow stub skills (loaded on demand)   | ~500+        | Auto-generated boilerplate, zero content |
| Duplicate learned-instincts.md entries  | ~50          | Auto-generation not deduplicating        |
| **Total per-turn waste**                | **~2,878**   |                                          |

### Recommended Efficiency Fixes (no performance loss)

1. **Add `paths:` frontmatter to 7 domain rules** → saves ~1,103 lines/turn
2. **Scope loom/ parent rules to exclude kailash-py child paths** → saves ~1,225 lines/turn
3. **Delete or rewrite 15+ hollow stub skills** → saves ~500+ lines on-demand
4. **Deduplicate learned-instincts.md** → saves ~50 lines/turn
5. **Merge `frontend-developer` into `react-specialist`** → removes 1 redundant agent
6. **Remove `kaizen-orchestration.md`** → removes 1 entirely stale skill

---

## Priority Fix Order

### Tier 1: Immediate (blocks correct code generation)

1. Fix SKILL.md files for all 5 framework specialists (Nexus, DataFlow, Kaizen, MCP, PACT) — these are loaded first and have the highest error density
2. Fix `agent-reasoning.md` and `patterns.md` import paths (Kaizen) — global rules loaded every session
3. Fix `pact-governance.md` Address API and GovernanceViolationError — global rule loaded every session
4. Fix `trust-plane-security.md` phantom `safe_open` reference
5. Delete `custom-node-guide.md` (entirely fictional) and `kaizen-orchestration.md` (entirely stale)
6. Fix TrustPosture enum names in EATP skills

### Tier 2: High Impact (prevents misleading guidance)

7. Remove/rewrite 15+ hollow stub skills
8. Fix phantom node references: LLMAgentNode, APICallNode, DatabaseExecuteNode, ConditionalNode (~50+ files)
9. Replace all hardcoded model names with env var patterns (~60+ occurrences)
10. Resolve CLAUDE.md vs agents.md review mandate contradiction
11. Add `paths:` frontmatter to 7 domain rules
12. Fix all PACT import paths from `pact.governance.X` to correct paths

### Tier 3: Token Efficiency (no performance loss)

13. Scope loom/ parent rules to exclude kailash-py
14. Delete hollow stubs that can't be immediately rewritten
15. Deduplicate learned-instincts.md
16. Merge frontend-developer into react-specialist
17. Update stale counts (agents: 37, rules: 29, engines: 13, etc.)

---

## SDK Bug Found

**Infrastructure: `store_result()` doesn't update `expires_at`** (CRITICAL-3 in infrastructure audit)

In `src/kailash/infrastructure/idempotency_store.py`, `store_result()` only updates `response_data`, `status_code`, and `headers` — it does NOT update `expires_at`. This means cached results retain the 5-minute claim TTL instead of the configured 1-hour TTL. Users relying on hour-long idempotency windows will find cached results disappearing after 5 minutes.

This is an actual SDK bug, not just a documentation error.

---

_Generated by 13 parallel red team agents auditing against actual SDK source code._
_Total agent execution: ~55 minutes wall clock across 13 parallel agents._
