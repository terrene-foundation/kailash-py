# DISCOVERY — DataFlow is a façade: seven "manager" classes were Python dicts

**Date**: 2026-04-08
**Phase**: 01-analyze + 03-implement

## What we found

Eight parallel specialist audits converged on the same anti-pattern: DataFlow ships seven "manager" classes exposed as public API (`db.transactions`, `db.connection`, `db.tenants`, etc.) that are Python dicts returning canned responses. Every one is instantiated in `DataFlow.__init__`, documented as production infrastructure, and backed by a trivial function.

**The façades**:
1. `TransactionManager` (`features/transactions.py`) — yielded in-memory dicts with `status="committed"`. Zero BEGIN/COMMIT/ROLLBACK. `model_registry.py` wrapped every registration in this and called it "transactional".
2. `ConnectionManager` (`utils/connection.py`) — `health_check()` always returned `database_reachable=True` regardless of state.
3. `MultiTenantManager` (`features/multi_tenant.py`) — hardcoded `created_at = "2024-01-01T00:00:00Z"` for every tenant.
4. `TenantSecurityManager.encrypt_tenant_data` (`core/multi_tenancy.py:925-949`) — returned `f"encrypted_{encryption_key}_{data}"` with a hardcoded `"tenant_specific_key"` constant. Users who trusted "enterprise encryption" stored plaintext with a fixed prefix.
5. `CacheIntegration` (dead parallel init path at `core/engine.py:941-1005`, 886 LOC) — zero consumers.
6. `FabricScheduler` — 257 LOC of cron scaffolding never instantiated.
7. `FabricServingLayer` — 512 LOC of endpoints never registered with Nexus.

## Root cause

Context amnesia at review time. The `TODO-11` reference at `fabric/pipeline.py:11` and the honest comment `# Cache operations (in-memory; Redis is a future extension)` at `pipeline.py:227` coexist 90 lines below a class docstring claiming production Redis caching. The author KNEW they were landing a stub, documented it honestly in the comment, and also wrote the class docstring as if the stub were implemented. Reviewers accepted it.

## What we fixed

- `TransactionManager` rewritten: real `BEGIN ISOLATION LEVEL X` / `COMMIT` / `ROLLBACK` with `ContextVar`-based async-safe connection tracking, savepoint nesting for nested `with` blocks.
- `ConnectionManager` rewritten: real `SELECT 1` health check via adapter, adapter-delegated pool stats, async `test_connection`.
- `encrypt_tenant_data` replaced with real `cryptography.fernet.Fernet` backed by env-var keys (`DATAFLOW_TENANT_KEY_<ID>` or `DATAFLOW_TENANT_ENCRYPTION_KEY`).
- 4 regression tests verify the Fernet fix (no `encrypted_` prefix, round-trip decryption, missing-key raises, per-tenant key priority).

## Guardrails needed

A new rule `rules/facade-manager-detection.md` should require: any class named `*Manager` exposed as `db.X` MUST have a Tier 2 integration test that verifies real side effects (not just API return value). This would have caught every one of these stubs at review time.

## Related

- `workspaces/dataflow-perfection/01-analysis/02-subsystem-audits/01-core-and-config.md`
- `workspaces/dataflow-perfection/01-analysis/02-subsystem-audits/05-tenancy-and-security.md`
- Commit `53dab715`, `cfec932c`
