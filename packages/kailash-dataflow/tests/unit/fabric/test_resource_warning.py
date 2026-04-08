# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Phase 6.4 — ResourceWarning on every async fabric resource class.

Per ``rules/patterns.md`` § Async Resource Cleanup, every async resource
class MUST implement ``__del__`` with a ResourceWarning so leaked
instances are visible during testing instead of silently dropping live
asyncio tasks, Redis clients, and source adapters.

These tests assert the four classes documented in todos/active/
07-phase-6-async-migration.md TODO-6.4:

- ``FabricRuntime`` — orchestrator that holds the shared Redis client,
  asyncio tasks, and source adapters
- ``PipelineExecutor`` — holds the cache backend reference and
  in-flight pipeline state
- ``ConnectionManager`` — wraps the database adapter pool
- ``DataFlow`` — already covered by tests/unit/core (regression net)

Each test calls ``__del__()`` directly with ``warnings.catch_warnings``
so the assertion is deterministic regardless of garbage-collection
timing.
"""
from __future__ import annotations

import warnings
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# FabricRuntime
# ---------------------------------------------------------------------------


class TestFabricRuntimeResourceWarning:
    """FabricRuntime.__del__ must warn when ``_started=True`` at GC time."""

    def _make_runtime(self, started: bool):
        from dataflow.fabric.runtime import FabricRuntime

        runtime = FabricRuntime.__new__(FabricRuntime)
        runtime._started = started
        runtime._instance_name = "test-instance"
        return runtime

    def test_warns_when_started(self):
        """A FabricRuntime that is GC'd while started leaks live tasks."""
        runtime = self._make_runtime(started=True)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            runtime.__del__()

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert len(resource) == 1
            message = str(resource[0].message)
            assert "Unclosed FabricRuntime" in message
            assert "test-instance" in message
            assert "runtime.stop()" in message

    def test_silent_when_stopped(self):
        """A stopped FabricRuntime must NOT warn — clean shutdown happened."""
        runtime = self._make_runtime(started=False)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            runtime.__del__()

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert resource == []

    def test_silent_when_init_failed(self):
        """If __init__ raised before setting ``_started``, __del__ is silent.

        ``getattr(..., False)`` defaults to "not started" so the
        finalizer doesn't crash on a half-constructed instance.
        """
        from dataflow.fabric.runtime import FabricRuntime

        runtime = FabricRuntime.__new__(FabricRuntime)
        # Intentionally do NOT set _started — simulate __init__ failure.

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            runtime.__del__()

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert resource == []


# ---------------------------------------------------------------------------
# PipelineExecutor
# ---------------------------------------------------------------------------


class TestPipelineExecutorResourceWarning:
    """PipelineExecutor.__del__ must warn when ``_closed=False`` at GC time."""

    def _make_executor(self, closed: bool):
        from dataflow.fabric.pipeline import PipelineExecutor

        executor = PipelineExecutor.__new__(PipelineExecutor)
        executor._closed = closed
        executor._instance_name = "test-pipeline"
        return executor

    def test_warns_when_open(self):
        """A PipelineExecutor that is GC'd while open leaks state."""
        executor = self._make_executor(closed=False)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            executor.__del__()

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert len(resource) == 1
            message = str(resource[0].message)
            assert "Unclosed PipelineExecutor" in message
            assert "test-pipeline" in message
            assert "executor.close()" in message

    def test_silent_when_closed(self):
        """A closed PipelineExecutor must NOT warn."""
        executor = self._make_executor(closed=True)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            executor.__del__()

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert resource == []

    def test_silent_when_init_failed(self):
        """A half-constructed PipelineExecutor (no ``_closed``) is silent."""
        from dataflow.fabric.pipeline import PipelineExecutor

        executor = PipelineExecutor.__new__(PipelineExecutor)
        # Do not set _closed — simulate __init__ failure.

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            executor.__del__()

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert resource == []

    @pytest.mark.asyncio
    async def test_close_drains_and_marks_closed(self):
        """``close()`` MUST drain in-flight work and flip the flag."""
        from dataflow.fabric.pipeline import PipelineExecutor

        executor = PipelineExecutor.__new__(PipelineExecutor)
        executor._closed = False
        executor._instance_name = "drain-test"
        executor._max_concurrent = 0  # Drain is a no-op when nothing was acquired.

        await executor.close()
        assert executor._closed is True

        # No warning after close().
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            executor.__del__()
            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert resource == []


# ---------------------------------------------------------------------------
# ConnectionManager
# ---------------------------------------------------------------------------


class TestConnectionManagerResourceWarning:
    """ConnectionManager.__del__ must warn when the pool is still initialized."""

    def _make_manager(self, initialized: bool):
        from dataflow.utils.connection import ConnectionManager

        manager = ConnectionManager.__new__(ConnectionManager)
        manager._initialized = initialized
        manager._adapter = MagicMock() if initialized else None
        return manager

    def test_warns_when_initialized(self):
        """An initialized ConnectionManager that is GC'd leaks DB connections."""
        manager = self._make_manager(initialized=True)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            manager.__del__()

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert len(resource) == 1
            message = str(resource[0].message)
            assert "Unclosed ConnectionManager" in message
            assert "close_all_connections" in message

    def test_silent_when_not_initialized(self):
        """A never-initialized ConnectionManager must NOT warn."""
        manager = self._make_manager(initialized=False)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            manager.__del__()

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert resource == []

    def test_silent_when_init_failed(self):
        """A half-constructed ConnectionManager (no ``_initialized``) is silent."""
        from dataflow.utils.connection import ConnectionManager

        manager = ConnectionManager.__new__(ConnectionManager)
        # Do not set _initialized — simulate __init__ failure.

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            manager.__del__()

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert resource == []
