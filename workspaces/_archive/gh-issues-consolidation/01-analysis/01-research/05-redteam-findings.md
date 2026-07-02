# Red Team Findings — Analysis Phase

## CRITICAL

### C1. #236 fix will break existing tests

`packages/kailash-pact/tests/unit/test_pact_engine.py:142-149` asserts `isinstance(gov, GovernanceEngine)`. At least 6 test call sites access `.governance` and assert on its type or call methods. The `_ReadOnlyGovernanceView` wrapper must proxy read-only properties (`org_name`, `compiled_org`, etc.) and tests must be updated.

**Resolution**: PR 1A must include test migration. ReadOnlyView must expose all read-only properties.

### C2. Hardcoded model string "claude-sonnet-4-6" in PactEngine

`packages/kailash-pact/src/pact/engine.py:411` — `model=self._model or "claude-sonnet-4-6"`. Violates `rules/env-models.md` (BLOCKED pattern). When #235 recreates supervisor per submit(), this fallback executes more frequently.

**Resolution**: Fix in PR 1A since it touches the same `_get_or_create_supervisor` code. Fallback should use `os.environ.get("DEFAULT_LLM_MODEL")`.

## HIGH

### H1. SSE streaming tests already exist in RED phase

`packages/kailash-nexus/tests/integration/test_sse_streaming.py` has comprehensive SSE tests (~600 lines) written in TDD RED phase. PR 3A should make these pass, not write new ones.

**Resolution**: Rescope PR 3A to "make existing RED tests pass + add /metrics endpoint."

### H2. #238 depends on #236 — accidental, not explicit

The dependency is currently satisfied because both are in sequential PRs, but if PR 1A is restructured, the hidden dependency breaks.

**Resolution**: Make dependency explicit in plan.

### H3. `datetime.utcnow()` in audit code — timezone-naive comparison bugs

Audit code uses deprecated `datetime.utcnow()` (audit_integration.py:41, audit_events.py:43,95, audit_trail_manager.py:118). Time-range queries with timezone-aware parameters will fail against naive timestamps.

**Resolution**: PR 4A must migrate existing `datetime.utcnow()` to `datetime.now(UTC)`.

### H4. `prometheus_client` is a new external dependency

Not in any pyproject.toml. Should be optional, not mandatory.

**Resolution**: Make it an optional extra (`pip install kailash-nexus[metrics]`) with lazy import guard.

### H5. #234 per-node governance spans two packages

GovernedSupervisor lives in kailash-kaizen, not kailash-pact. Cross-package coordination needed.

**Resolution**: PR 1B must list kaizen-agents as co-change with version compatibility and cross-package integration tests.

## MEDIUM

### M1. #244 assumes Fabric Engine implementation is complete

Fabric module exists (`packages/kailash-dataflow/src/dataflow/fabric/`) but operational status unknown. If `@db.product` decorator isn't functional, PR 4C is blocked.

**Resolution**: Verify Fabric Engine operational status before Session 3.

### M2. ProvenancedField likely underscoped

Must touch `@db.model` decorator, serialization, FieldMeta, database adapters, and query engine. Estimate of ~670 lines may be low.

**Resolution**: Consider splitting PR 4B into sub-PRs (type system + serialization, then query support).

### M3. Audit persistence has no migration strategy

Existing deployments need schema migrations to add audit_events table. No auto-creation behavior planned.

**Resolution**: Include auto-table-creation in `DataFlow.start()` when `audit=True`.

### M4. 3-session estimate assumes full parallelism

4 parallel PRs in Session 1 requires parallel agent execution. Sequential execution = 5-6 sessions.

**Resolution**: Frame as "3 sessions with parallel execution" or "5-6 sequential."

## NOTED

- N1. `reject_bridge()` confirmed missing — research accurate
- N2. Cross-SDK kailash-rs issues need filing for #234, #235, #236, #237, #233 (not just #231)
- N3. `set_vacancy_designation` correctly rejects filled roles — confirmed, test coverage missing
- N4. Developer flow examples accurate except hardcoded model (C2)
