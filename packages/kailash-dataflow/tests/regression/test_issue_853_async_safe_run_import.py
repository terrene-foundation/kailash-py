"""Regression test for issue #853 — schema_state_manager NameError.

`SchemaStateManager._record_migration_with_thread_pool` (and the sibling
workflow-execution path) call `async_safe_run(...)` to bridge sync→async
when recording a migration-history audit row. The module never imported
`async_safe_run`, so applying numbered migrations against PostgreSQL raised
`NameError: name 'async_safe_run' is not defined` on the audit-trail insert
(the DDL itself applied successfully — only the history-table write failed).

Root cause: missing `from dataflow.core.async_utils import async_safe_run`
in `dataflow/migrations/schema_state_manager.py`. The helper is defined at
`dataflow/core/async_utils.py`.

This is the kailash-py equivalent of HANA #90
(https://github.com/Integrum-Global/hana/issues/90) — cross-SDK alignment
per rules/cross-sdk-inspection.md.

The bug is, definitionally, "the name is not bound in this module's
namespace." The regression pin asserts the name IS bound AND that every
call site referencing it resolves against the module globals. Without the
import line both assertions fail; with it both pass. No external infra is
needed — the NameError is a pure import-resolution defect, not a runtime
data-path defect.
"""

import ast
import inspect
from pathlib import Path

import pytest

from dataflow.migrations import schema_state_manager


@pytest.mark.regression
def test_async_safe_run_is_bound_in_module_namespace():
    """The missing-import root cause: `async_safe_run` MUST resolve in the
    schema_state_manager module namespace. Fails with AttributeError if the
    import is removed (the exact #853 failure)."""
    assert hasattr(schema_state_manager, "async_safe_run"), (
        "schema_state_manager.async_safe_run is unbound — issue #853 regression: "
        "the `from dataflow.core.async_utils import async_safe_run` import was "
        "removed, reintroducing the migration-tracking NameError."
    )
    assert callable(schema_state_manager.async_safe_run)


@pytest.mark.regression
def test_async_safe_run_resolves_to_canonical_helper():
    """The bound symbol MUST be the canonical helper from
    dataflow.core.async_utils, not a shadow/local rebinding."""
    from dataflow.core.async_utils import async_safe_run as canonical

    assert schema_state_manager.async_safe_run is canonical


@pytest.mark.regression
def test_every_async_safe_run_call_site_is_backed_by_the_import():
    """AST guard: every `async_safe_run(...)` call in the module source MUST
    have `async_safe_run` resolvable in module globals. Guards against a
    future refactor that removes the import while leaving call sites — the
    exact shape of the #853 regression."""
    source_path = Path(inspect.getfile(schema_state_manager))
    tree = ast.parse(source_path.read_text())

    call_site_lines = [
        node.func.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "async_safe_run"
    ]

    assert call_site_lines, (
        "expected ≥1 async_safe_run(...) call site in schema_state_manager.py "
        "(test is stale if the call sites were intentionally removed)"
    )
    # The name referenced by every call site must resolve in module globals.
    assert "async_safe_run" in vars(schema_state_manager), (
        f"async_safe_run called at lines {call_site_lines} but unbound in "
        f"module globals — issue #853 regression."
    )
