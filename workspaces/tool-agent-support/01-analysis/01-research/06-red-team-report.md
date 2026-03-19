# Red Team Report -- Tool Agent Support

**Date**: 2026-03-18
**Scope**: All analysis, plans, and user flows
**Method**: Cross-document analysis, source code verification, rule compliance audit
**Findings**: 20 (2 CRITICAL, 6 HIGH, 10 MEDIUM, 2 LOW)

---

## Critical Findings

### RT-06: deploy_agent MCP Tool -- Path Traversal via manifest_path_or_content

**Severity**: CRITICAL
**Category**: security

`deploy_agent(manifest_path_or_content: str)` accepts either a file path or inline TOML. An MCP client can pass `"../../../../etc/passwd"` as the path. No path validation is specified.

**Resolution**: MCP tool accepts content-only (inline TOML string). Path mode is Python API-only where the caller is trusted. If path mode is needed in MCP, confine to project directory, reject `..` components, require `.toml` extension, resolve symlinks with `os.path.realpath()`.

### RT-07: introspect_agent -- Arbitrary Code Execution via importlib

**Severity**: CRITICAL
**Category**: security

`introspect_agent(module, class_name)` uses `importlib.import_module()` which executes module-level code. If exposed via MCP, any client can trigger arbitrary module loading.

**Resolution**: Do NOT expose `introspect_agent` via MCP. MCP tool `validate_agent_code` works with pre-built manifests (TOML content), not live module imports. Module introspection is CLI-only or Python API-only.

---

## High Findings

### RT-01: deploy() Sync/Async Contract Contradiction

**Severity**: HIGH

Brief says sync, requirements say async, user flow calls sync.

**Resolution**: Provide `deploy()` (sync, urllib.request) and `deploy_async()` (async). Document which to use when.

### RT-02: MCP Catalog Server Package Location -- Three-Way Disagreement

**Severity**: HIGH

Requirements: Core SDK. Plan: Kaizen. Risk analysis: Nexus.

**Resolution**: Place in `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/` (plan's location). Kaizen owns the agent registry. Update all documents.

### RT-04: P4 Aggregation -- MongoDB Support Missing from Plan

**Severity**: HIGH

Brief requires PostgreSQL + SQLite + MongoDB. Plan only covers PostgreSQL + SQLite.

**Resolution**: Add `query/mongo_builder.py` to P4 scope. Or explicitly descope MongoDB with stakeholder approval (document as ADR-6).

### RT-08: P5 PostureStore -- SQLite File Permissions and Locking

**Severity**: HIGH

SQLitePostureStore stores trust-critical state but plan doesn't mention symlink protection or trust-plane locking patterns.

**Resolution**: Use `validate_id()` for path validation, check for symlinks before opening, set 0o600 on DB/WAL/SHM files. Follow trust-plane-security.md patterns.

### RT-11: P3 Composite Validation -- Missing Maximum Depth/Size Limits

**Severity**: HIGH

No DAG size limits. 100K-node composition = denial of service.

**Resolution**: Add `max_agents=1000` parameter to `validate_dag`. Reject oversized compositions before traversal.

### RT-18: Test Strategy Mentions "Mock HTTP" for P1 Deploy -- Violates No-Mocking Rule

**Severity**: HIGH

Tier 2 deploy tests cannot use mock HTTP per project rules.

**Resolution**: Use a local HTTP test server (real infrastructure, running locally) that implements the CARE Platform API contract.

---

## Medium Findings

### RT-03: Budget Module Location Disagreement

Requirements: `kaizen.governance.budget`. Plan: `kaizen.core.autonomy.budget`.

**Resolution**: Use `kaizen.core.autonomy.budget` (plan's location, consistent with existing autonomy modules).

### RT-05: User Flow 3 Thin on Error Paths

Analytics flow has no error paths for invalid field names, SQL injection, or cross-backend examples.

**Resolution**: Add error paths to Flow 3.

### RT-09: Missing Error Hierarchy for New Modules

P3, P4, P6 have no defined error classes. EATP rules require TrustError hierarchy.

**Resolution**: Define error classes per module in implementation plan.

### RT-10: No BudgetStore Persistence Layer

BudgetTracker is in-memory only. No cross-process budget enforcement.

**Resolution**: Add `BudgetStore` protocol and `SQLiteBudgetStore` in Wave 1 or early Wave 2.

### RT-12: No manifest_version Field

Risk analysis recommended it, but neither requirements nor plan includes it.

**Resolution**: Add `manifest_version: str = "1.0"` to AgentManifest. Reject unknown versions.

### RT-13: COC Expert's 15-Tool Recommendation Reduced to 8 with No Fast-Follow Plan

Plan says "expand to ~15" but provides no timeline or tracking.

**Resolution**: Add 3 critical tools to Wave 3: `validate_composition`, `cost_estimate`, `introspect_agent` (CLI-only per RT-07).

### RT-14: No Import Cycle Analysis

5 new modules across 2 packages with cross-package imports. No cycle analysis.

**Resolution**: Draw import dependency graph before implementation. Verify `kaizen -> eatp` direction only.

### RT-15: AppManifest.budget Uses float, Not Decimal

Budget field is float in manifest but Decimal in BudgetTracker. Type mismatch at integration point.

**Resolution**: Accept float from TOML, convert to Decimal via `Decimal(str(raw_float))`.

### RT-16: No Rollback/Cleanup for Failed Deployments

No `undeploy_agent` or `deploy_rollback` tool. No removal mechanism.

**Resolution**: Add `catalog_deregister(agent_name)` to P2 tool set (tool #9).

### RT-17: PostureStateMachine Default Posture Mismatch

Current default: SHARED_PLANNING. CARE spec says tool agents start at SUPERVISED.

**Resolution**: Make default configurable, set SUPERVISED for tool agent contexts.

---

## Low Findings

### RT-19: Analysis References Aegis Architecture Journal

Independence rules say no proprietary references. Analysis grounds in Aegis decisions.

**Resolution**: Analysis was user-directed to reference Aegis journal. Ensure implementation code references CARE/CO specs, not Aegis.

### RT-20: Catalog Pre-Seeding Strategy Has No Implementation Details

"Pre-seed 14 agents" but no specifics on which agents or how.

**Resolution**: List specific agents from `kaizen.agents.specialized`. Auto-seed on server startup.

---

## Summary

| Severity | Count | Top Action                                                                    |
| -------- | ----- | ----------------------------------------------------------------------------- |
| CRITICAL | 2     | Resolve security vectors (RT-06, RT-07) before Wave 3                         |
| HIGH     | 6     | Resolve package location (RT-02), add MongoDB ADR (RT-04), DAG limits (RT-11) |
| MEDIUM   | 10    | Fix before each wave starts                                                   |
| LOW      | 2     | Track, non-blocking                                                           |

### Top 3 Pre-Implementation Actions

1. **Security**: MCP tool `deploy_agent` accepts inline TOML only (not file paths). `introspect_agent` is not exposed via MCP. (RT-06, RT-07)
2. **Alignment**: Resolve package locations and update all documents to match. (RT-02, RT-03)
3. **Scope**: Add MongoDB to P4 or create ADR-6 descoping it. (RT-04)
