"""Regression: #713 (S5) — DataFlow subsystems follow parent runtime swap.

After S4 made `DataFlow.runtime` a lazy `@property`, four subsystems
(ModelRegistry, AutoMigrationSystem, MigrationHistoryManager via
SchemaStateManager, GatewayIntegration) previously snapshotted `self.runtime`
at __init__ and held a stale reference after the parent's runtime swapped.

S5 converts each subsystem's `runtime` to a lazy `@property` that returns
`self._dataflow.runtime` (or the legacy explicit-runtime override). This test
verifies the swap-following behavior end-to-end against real PostgreSQL.

Pre-fix failure mode: module-import-time `db = DataFlow(...)` binds
LocalRuntime; subsystems snapshot it; later `await db.create_tables_async()`
inside an event loop crashes with
`AttributeError: 'LocalRuntime' object has no attribute 'execute_workflow_async'`
because subsystems still hold the LocalRuntime even after the parent's
property switched to AsyncLocalRuntime.

This regression MUST NOT be deleted per `rules/orphan-detection.md` Rule 4.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime

POSTGRES_URL = os.environ.get(
    "DATAFLOW_TEST_POSTGRES_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


@pytest.mark.regression
@pytest.mark.integration
def test_model_registry_follows_runtime_swap():
    """ModelRegistry.runtime tracks parent DataFlow.runtime swaps."""
    from dataflow import DataFlow

    db = DataFlow(POSTGRES_URL)
    try:
        # In sync context, parent resolves to LocalRuntime
        assert isinstance(db.runtime, LocalRuntime)
        # Subsystem follows parent
        assert isinstance(db._model_registry.runtime, LocalRuntime)

        # Setter override on parent → subsystem follows
        async_rt = AsyncLocalRuntime()
        db.runtime = async_rt
        assert db._model_registry.runtime is async_rt

        # Clear override → resumes lazy detection (LocalRuntime in sync ctx)
        db.runtime = None
        assert isinstance(db._model_registry.runtime, LocalRuntime)
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
def test_auto_migration_system_follows_runtime_swap():
    """AutoMigrationSystem.runtime tracks parent DataFlow.runtime swaps."""
    from dataflow import DataFlow

    db = DataFlow(POSTGRES_URL, auto_migrate=True)
    try:
        # In sync context, parent resolves to LocalRuntime
        if db._migration_system is None:
            pytest.skip("migration system not initialized for this config")
        assert isinstance(db._migration_system.runtime, LocalRuntime)

        # Swap parent → subsystem follows
        async_rt = AsyncLocalRuntime()
        db.runtime = async_rt
        assert db._migration_system.runtime is async_rt
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
def test_schema_state_manager_follows_runtime_swap():
    """SchemaStateManager (MigrationHistoryManager) follows parent swaps."""
    from dataflow import DataFlow

    db = DataFlow(POSTGRES_URL)
    try:
        # The schema state manager initializes lazily on the postgres path.
        # If the lazy path didn't construct it for this config, skip.
        if db._schema_state_manager is None:
            pytest.skip("schema state manager not initialized for this config")

        assert isinstance(db._schema_state_manager.runtime, LocalRuntime)

        async_rt = AsyncLocalRuntime()
        db.runtime = async_rt
        assert db._schema_state_manager.runtime is async_rt
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
def test_module_level_dataflow_then_async_ddl_succeeds_via_subsystems():
    """downstream-consumer shape: module-level DataFlow + async DDL no longer crashes.

    Pre-fix the framework crashed at create_tables_async because subsystems
    captured LocalRuntime. Post-S4 + S5: parent property is lazy AND
    subsystems read it lazily, so the same call works.
    """
    from dataflow import DataFlow

    db = DataFlow(POSTGRES_URL)

    @db.model
    class _S5RegressionItem:  # noqa: N801 — test fixture
        id: int
        name: str

    async def _run() -> None:
        # Inside the event loop, parent.runtime resolves AsyncLocalRuntime
        assert isinstance(db.runtime, AsyncLocalRuntime)
        # And the subsystems agree
        assert isinstance(db._model_registry.runtime, AsyncLocalRuntime)
        # The actual call that crashed pre-fix
        await db.create_tables_async()

    try:
        asyncio.run(_run())
    finally:
        # Cleanup the test table
        async def _cleanup() -> None:
            try:
                from kailash.workflow.builder import WorkflowBuilder

                wf = WorkflowBuilder()
                wf.add_node(
                    "AsyncSQLDatabaseNode",
                    "drop",
                    {
                        "connection_string": POSTGRES_URL,
                        "query": 'DROP TABLE IF EXISTS "_s5regressionitem"',
                        "fetch_mode": "none",
                    },
                )
                runtime = AsyncLocalRuntime()
                await runtime.execute_workflow_async(wf.build(), inputs={})
            except Exception:
                pass

        asyncio.run(_cleanup())
        db.close()


@pytest.mark.regression
def test_subsystem_explicit_runtime_override_pins():
    """Explicit runtime= argument to ModelRegistry pins its runtime.

    The subsystem's @property returns self._explicit_runtime when set, falling
    through to self._dataflow.runtime only when the override is None. This
    test verifies the explicit-override path still works for callers that
    intentionally pin a runtime.
    """
    from dataflow import DataFlow
    from dataflow.core.model_registry import ModelRegistry

    db = DataFlow(POSTGRES_URL)
    try:
        # Construct an explicitly-pinned ModelRegistry (legacy escape hatch)
        pinned_runtime = AsyncLocalRuntime()
        registry = ModelRegistry(db, runtime=pinned_runtime)

        # Even after parent swaps, this registry is pinned
        db.runtime = LocalRuntime()
        assert registry.runtime is pinned_runtime
    finally:
        db.close()


@pytest.mark.regression
def test_subsystem_runtime_assignment_setter_compat():
    """Legacy callers that wrote subsystem.runtime = X still work.

    S5 preserves backwards compat for code that mutates
    ``model_registry.runtime`` directly — the @property has a setter that
    stores the value as the explicit override.
    """
    from dataflow import DataFlow

    db = DataFlow(POSTGRES_URL)
    try:
        original = db._model_registry.runtime
        # Direct assignment on the subsystem
        new_runtime = AsyncLocalRuntime()
        db._model_registry.runtime = new_runtime
        assert db._model_registry.runtime is new_runtime
        # Clearing the override resumes parent-follow
        db._model_registry.runtime = None
        assert isinstance(db._model_registry.runtime, type(original))
    finally:
        db.close()


@pytest.mark.regression
def test_subsystem_audit_grep_no_orphan_runtime_captures():
    """Mechanical sweep: subsystem files MUST NOT capture self.runtime in __init__.

    Per S5 + rules/orphan-detection.md, every subsystem with a runtime
    surface MUST read via lazy @property (returning self._dataflow.runtime).
    Plain attribute capture in __init__ is BLOCKED — that is the failure mode
    this shard fixed.
    """
    import re
    from pathlib import Path

    repo_root = Path(__file__).parent.parent.parent
    subsystems = [
        repo_root / "packages/kailash-dataflow/src/dataflow/core/model_registry.py",
        repo_root
        / "packages/kailash-dataflow/src/dataflow/migrations/auto_migration_system.py",
        repo_root
        / "packages/kailash-dataflow/src/dataflow/migrations/schema_state_manager.py",
        repo_root / "packages/kailash-dataflow/src/dataflow/gateway_integration.py",
    ]

    # Pattern: `self.runtime = <expr>` or `self._runtime = <expr>` inside __init__.
    # Acceptable: setter assignments (under @runtime.setter) and explicit-override
    # initialization (`self._explicit_runtime = runtime`).
    bad_pattern = re.compile(
        r"^\s*self\.(runtime|_runtime)\s*=\s*[^#\n]+", re.MULTILINE
    )

    for subsystem in subsystems:
        if not subsystem.exists():
            continue
        text = subsystem.read_text()

        # Find all matches and exclude legitimate ones:
        # - inside @<...>.setter blocks
        # - assignments to self._explicit_runtime (the new pattern)
        for match in bad_pattern.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            line = text[line_start:line_end]

            if "_explicit_runtime" in line:
                continue  # the new pattern
            # Look back ~10 lines for an @<...>.setter decorator
            preceding = text[max(0, match.start() - 500) : match.start()]
            if ".setter" in preceding.split("\n")[-15:][-1:][0] or any(
                ".setter" in pl for pl in preceding.split("\n")[-15:]
            ):
                continue

            pytest.fail(
                f"Orphan runtime capture detected in {subsystem.name}:\n"
                f"  {line.strip()}\n"
                f"This violates S5 — subsystems MUST read runtime via "
                f"lazy @property delegating to self._dataflow.runtime. "
                f"See rules/orphan-detection.md and "
                f"workspaces/issues-712-714/01-analysis/01-architecture.md."
            )
