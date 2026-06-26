# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures + helpers for regression tests.

Hosts the ``sqlite_file_url`` fixture + ``RecordingExecutor`` stub +
``pass_through_plan`` factory used by the per-manager trust-wiring tests:

- ``test_trust_executor_wiring.py``
- ``test_audit_store_wiring.py``
- ``test_trust_manager_wiring.py``

These three files were split out of the former monolithic
``test_phase_5_11_trust_wiring.py`` per
rules/facade-manager-detection.md MUST Rule 2 (issue #499 Finding 8).

Helpers live in conftest (not a sibling module) because
``packages/kailash-dataflow/tests/regression/`` is not a Python package
(no ``__init__.py``), so relative imports from sibling test modules are
not available. Pytest auto-imports conftest and makes its names
importable by test files via the ``conftest`` attribute on the session,
but the canonical pattern for sharing helpers across pytest test modules
is a fixture + module-scoped pytest-importable globals.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import os
import tempfile
import uuid
from typing import Any, Dict, List, Optional

import pytest

from dataflow.trust.query_wrapper import QueryAccessResult

# --- F-TEST-HYGIENE: autouse resource-close fixture (zero-tolerance Rule 1) ---
#
# Many infra-free regression tests construct framework resource objects
# (``DataFlow``, ``PipelineExecutor``, ``ModelRegistry``, ``Nexus``) without
# closing them, so each class's ``__del__`` fires
# ``ResourceWarning: Unclosed <Class>`` when the instance is garbage collected.
# The warnings are CORRECT SDK behaviour — the "you forgot to close" contract
# per rules/patterns.md § "Async Resource Cleanup" — so the fix belongs in the
# tests, not the SDK. This fixture closes any such resource a test left open,
# at that test's teardown, so the closed-flag is set before GC runs.
#
# BLAST RADIUS (why the design is shaped this way): an un-closed instance is
# freed at function-return (frame pop), firing ``__del__`` BEFORE any teardown
# fixture runs — a teardown-only ``gc`` scan is too late to suppress the
# warning. To *prevent* it, the fixture holds a STRONG reference from
# construction (via one-time ``__init__`` wrappers), keeping the instance alive
# until teardown-close. That strong reference would DEFEAT tests that rely on
# GC firing ``__del__`` in-body (``del df; gc.collect()``) or on GC reaping
# pool-registry entries. Such lifecycle-semantics tests carry
# ``@pytest.mark.dataflow_lifecycle`` and OPT OUT of tracking entirely — the
# fixture holds no reference to their instances (including resources those
# tests construct internally, e.g. an engine-created ModelRegistry), so their
# GC-based assertions are unaffected.
#
# ``ModelRegistry`` instances are created INTERNALLY by the engine (no
# test-visible handle), so the ``__init__`` wrapper is the only mechanism that
# can reach them. ``PipelineExecutor.close()`` is async (drains then flips the
# flag) — driven via ``asyncio.run`` at the sync teardown (no loop is running
# there); an idle test executor has nothing to drain, so a fresh loop is safe.
# Every close is best-effort (try/except): the worst case is a warning persists
# (visible), never a test failure.

_tracked_resource_instances: List[Any] = []
_resource_tracking_enabled = False
_resource_init_installed = False


def _make_tracking_init(orig_init: Any) -> Any:
    @functools.wraps(orig_init)
    def _tracking_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        if _resource_tracking_enabled:
            _tracked_resource_instances.append(self)

    return _tracking_init


def _install_resource_init_trackers() -> None:
    """Wrap each tracked resource class's ``__init__`` once. Imports are lazy +
    defensive so a missing optional package never breaks conftest collection
    for the whole regression suite. The four classes are unrelated (no
    subclassing among them), so wrapping each independently cannot
    double-register; ``ProtectedDataFlow`` registers once via the wrapped
    ``DataFlow.__init__`` its ``super().__init__`` reaches."""
    global _resource_init_installed
    if _resource_init_installed:
        return
    _resource_init_installed = True

    for _import in (
        lambda: __import__("dataflow", fromlist=["DataFlow"]).DataFlow,
        lambda: __import__(
            "dataflow.fabric.pipeline", fromlist=["PipelineExecutor"]
        ).PipelineExecutor,
        lambda: __import__(
            "dataflow.core.model_registry", fromlist=["ModelRegistry"]
        ).ModelRegistry,
        lambda: __import__(
            "dataflow.cache.async_redis_adapter", fromlist=["AsyncRedisCacheAdapter"]
        ).AsyncRedisCacheAdapter,
        lambda: __import__("nexus", fromlist=["Nexus"]).Nexus,
    ):
        try:
            cls = _import()
        except Exception:
            continue
        cls.__init__ = _make_tracking_init(cls.__init__)


@pytest.fixture(autouse=True)
def _auto_close_resource_instances(request):
    """Close framework resources a regression test forgot to close.

    Opt out with ``@pytest.mark.dataflow_lifecycle`` for tests that assert
    ``__del__`` / ``close`` / GC semantics and need their instances to be
    garbage-collectable in-body.
    """
    global _resource_tracking_enabled
    if request.node.get_closest_marker("dataflow_lifecycle") is not None:
        # GC-sensitive test: hold no references; let __del__/GC behave natively.
        yield
        return
    _install_resource_init_trackers()
    _resource_tracking_enabled = True
    start = len(_tracked_resource_instances)
    try:
        yield
    finally:
        _resource_tracking_enabled = False
        for inst in _tracked_resource_instances[start:]:
            try:
                if getattr(inst, "_closed", False) is True:
                    continue
                # Resolve the first available close method. DataFlow exposes
                # both sync ``close`` and async ``close_async`` — ``close`` wins
                # (cheaper, no loop). AsyncRedisCacheAdapter exposes only
                # ``close_async``; FabricRuntime-style resources expose ``stop``.
                close = None
                for _name in ("close", "close_async", "stop"):
                    cand = getattr(inst, _name, None)
                    if callable(cand):
                        close = cand
                        break
                if close is None:
                    continue
                if inspect.iscoroutinefunction(close):
                    asyncio.run(close())
                else:
                    close()
            except Exception:
                # Best-effort teardown cleanup: a close() failure here MUST NOT
                # mask the test's own result. Acceptable per zero-tolerance
                # Rule 3 (cleanup path, failure expected/benign).
                pass
        del _tracked_resource_instances[start:]


@pytest.fixture
def recording_executor():
    """Factory fixture — returns the RecordingExecutor class.

    Fixture form lets sibling test files access the stub without needing
    to import it (conftest.py is auto-discovered by pytest but its names
    are not directly importable from sibling test files without package
    infrastructure).
    """
    return RecordingExecutor


@pytest.fixture
def plan_factory():
    """Factory fixture — returns the ``pass_through_plan`` helper."""
    return pass_through_plan


@pytest.fixture
def sqlite_file_url():
    """Yield a file-backed SQLite URL scoped to a single test.

    ``sqlite:///:memory:`` cannot be used because DataFlow's migration lock
    table is created lazily on a separate connection and ``:memory:``
    databases are not shared across connections.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"tf_{uuid.uuid4().hex}.db")
        yield f"sqlite:///{path}"


def pass_through_plan(
    *,
    additional_filters: Optional[Dict[str, Any]] = None,
    row_limit: Optional[int] = None,
    pii: Optional[List[str]] = None,
    allowed: bool = True,
    denied_reason: Optional[str] = None,
) -> QueryAccessResult:
    return QueryAccessResult(
        allowed=allowed,
        filtered_columns=[],
        additional_filters=additional_filters or {},
        row_limit=row_limit,
        denied_reason=denied_reason,
        applied_constraints=[],
        pii_columns_filtered=pii or [],
        sensitive_columns_flagged=[],
    )


class RecordingExecutor:
    """Observer executor that mimics the TrustAwareQueryExecutor surface.

    Every Express CRUD method calls one of these methods. The recorder lets
    tests assert exactly which model/operation/plan was seen.
    """

    def __init__(
        self,
        *,
        read_plan: Optional[QueryAccessResult] = None,
        write_plan: Optional[QueryAccessResult] = None,
        deny_writes: bool = False,
    ) -> None:
        self.read_plan = read_plan or pass_through_plan()
        self.write_plan = write_plan or pass_through_plan()
        self.deny_writes = deny_writes
        self.read_checks: List[Dict[str, Any]] = []
        self.write_checks: List[Dict[str, Any]] = []
        self.successes: List[Dict[str, Any]] = []
        self.failures: List[Dict[str, Any]] = []

    async def check_read_access(
        self,
        *,
        model_name: str,
        filter: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        trust_context: Any = None,
    ) -> QueryAccessResult:
        self.read_checks.append(
            {"model": model_name, "filter": filter, "agent_id": agent_id}
        )
        return self.read_plan

    async def check_write_access(
        self,
        *,
        model_name: str,
        operation: str,
        agent_id: Optional[str] = None,
        trust_context: Any = None,
    ) -> QueryAccessResult:
        self.write_checks.append(
            {"model": model_name, "operation": operation, "agent_id": agent_id}
        )
        if self.deny_writes:
            raise PermissionError(f"{operation} denied by test stub")
        return self.write_plan

    def apply_result_filter(self, data: Any, plan: QueryAccessResult) -> Any:
        if not plan.pii_columns_filtered:
            return data
        if isinstance(data, list):
            return [
                (
                    {k: v for k, v in row.items() if k not in plan.pii_columns_filtered}
                    if isinstance(row, dict)
                    else row
                )
                for row in data
            ]
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in plan.pii_columns_filtered}
        return data

    async def record_query_success(
        self,
        *,
        model_name: str,
        operation: str,
        plan: QueryAccessResult,
        agent_id: Optional[str] = None,
        trust_context: Any = None,
        rows_affected: int = 0,
        query_params: Any = None,
    ) -> Optional[str]:
        self.successes.append(
            {
                "model": model_name,
                "operation": operation,
                "agent_id": agent_id,
                "rows_affected": rows_affected,
            }
        )
        return "success-event-id"

    async def record_query_failure(
        self,
        *,
        model_name: str,
        operation: str,
        plan: Optional[QueryAccessResult],
        agent_id: Optional[str] = None,
        trust_context: Any = None,
        error: Optional[str] = None,
        query_params: Any = None,
    ) -> None:
        self.failures.append(
            {
                "model": model_name,
                "operation": operation,
                "agent_id": agent_id,
                "error": error,
            }
        )
