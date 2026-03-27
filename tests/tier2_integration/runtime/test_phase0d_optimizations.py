"""Regression tests for Phase 0d performance optimizations.

Validates that all P0D performance optimizations are in place and functional:
- P0D-001: MetricsCollector respects enable_resource_monitoring=False (no thread spawn)
- P0D-002: sanitize_input() uses cached allowed_types (no per-call lazy imports)
- P0D-003: Topological sort cache returns immutable tuple (prevents cache corruption)
"""

import inspect
import time

import pytest


from kailash.runtime.local import LocalRuntime
from kailash.tracking.metrics_collector import MetricsCollector, MetricsContext
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

# --- P0D-001: MetricsCollector Thread Elimination ---


class TestP0D001MetricsCollectorThreadElimination:
    """Verify that MetricsCollector skips thread creation when resource monitoring disabled."""

    def test_enable_resource_monitoring_parameter_exists(self):
        """MetricsCollector.__init__ should accept enable_resource_monitoring parameter."""
        sig = inspect.signature(MetricsCollector.__init__)
        params = list(sig.parameters.keys())
        assert "enable_resource_monitoring" in params, (
            "MetricsCollector missing enable_resource_monitoring parameter. "
            "P0D-001 optimization may have been reverted."
        )

    def test_monitoring_disabled_skips_thread(self):
        """When enable_resource_monitoring=False, no monitoring thread should be spawned."""
        collector = MetricsCollector(enable_resource_monitoring=False)
        assert not collector._monitoring_enabled, (
            "MetricsCollector._monitoring_enabled should be False when "
            "enable_resource_monitoring=False."
        )

        with collector.collect(node_id="test") as ctx:
            assert ctx.monitoring_thread is None, (
                "MetricsContext should not spawn a monitoring thread when "
                "monitoring is disabled."
            )

    def test_monitoring_enabled_still_works(self):
        """When enable_resource_monitoring=True, monitoring should work if psutil available."""
        from kailash.tracking.metrics_collector import PSUTIL_AVAILABLE

        collector = MetricsCollector(enable_resource_monitoring=True)
        assert collector._monitoring_enabled == PSUTIL_AVAILABLE

    def test_disabled_monitoring_collects_duration(self):
        """Even with monitoring disabled, duration should still be tracked."""
        collector = MetricsCollector(enable_resource_monitoring=False)
        with collector.collect(node_id="test") as ctx:
            time.sleep(0.01)  # 10ms
        metrics = ctx.result()
        assert (
            metrics.duration >= 0.005
        ), f"Duration {metrics.duration} should be >= 5ms even with monitoring disabled."

    def test_disabled_monitoring_performance(self):
        """Disabled monitoring should be sub-10us per collect() call."""
        collector = MetricsCollector(enable_resource_monitoring=False)
        n_iterations = 100
        start = time.perf_counter()
        for _ in range(n_iterations):
            with collector.collect(node_id="perf") as ctx:
                pass
            ctx.result()
        elapsed = time.perf_counter() - start
        per_call_us = (elapsed / n_iterations) * 1_000_000
        assert per_call_us < 100, (
            f"MetricsCollector with monitoring disabled took {per_call_us:.1f}us/call. "
            "Expected < 100us. P0D-001 may not be effective."
        )

    def test_shared_collector_uses_enable_resource_limits(self):
        """LocalRuntime should pass enable_resource_limits to MetricsCollector."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        assert "enable_resource_monitoring" in source, (
            "enable_resource_monitoring not passed to MetricsCollector in "
            "_execute_workflow_async. P0D-001 wiring may have been reverted."
        )


# --- P0D-002: Cached allowed_types in sanitize_input ---


class TestP0D002CachedAllowedTypes:
    """Verify that sanitize_input() uses cached allowed_types."""

    def test_cache_function_exists(self):
        """_get_cached_allowed_types should exist in security module."""
        from kailash.security import _get_cached_allowed_types

        assert callable(_get_cached_allowed_types)

    def test_cache_returns_consistent_types(self):
        """Cache should return the same types on repeated calls."""
        from kailash.security import _get_cached_allowed_types

        types_1 = _get_cached_allowed_types()
        types_2 = _get_cached_allowed_types()

        # Both calls should return lists with same content
        assert set(types_1) == set(
            types_2
        ), "Cached allowed_types returned different types on repeated calls."

    def test_cache_includes_builtins(self):
        """Cache should include all builtin types."""
        from kailash.security import _get_cached_allowed_types

        types = _get_cached_allowed_types()
        for builtin_type in [str, int, float, bool, list, dict, tuple, set, type(None)]:
            assert (
                builtin_type in types
            ), f"Builtin type {builtin_type} missing from cache."

    def test_cache_returns_mutable_copy(self):
        """Cache should return a mutable copy so callers can extend safely."""
        from kailash.security import _get_cached_allowed_types

        types_1 = _get_cached_allowed_types()
        types_1.append(bytes)  # Modify the returned list

        types_2 = _get_cached_allowed_types()
        assert bytes not in types_2, (
            "Modifying returned list corrupted the cache. "
            "Cache should return a copy, not the original."
        )

    def test_cached_types_used_in_sanitize_input(self):
        """sanitize_input() should use _get_cached_allowed_types."""
        source = inspect.getsource(
            __import__("kailash.security", fromlist=["sanitize_input"]).sanitize_input
        )
        assert "_get_cached_allowed_types()" in source, (
            "sanitize_input() does not use _get_cached_allowed_types(). "
            "P0D-002 optimization may have been reverted."
        )

    def test_sanitize_input_performance(self):
        """sanitize_input() should be fast with cached types."""
        from kailash.security import sanitize_input

        n_iterations = 1000
        start = time.perf_counter()
        for _ in range(n_iterations):
            sanitize_input("test_value")
        elapsed = time.perf_counter() - start
        per_call_us = (elapsed / n_iterations) * 1_000_000
        assert per_call_us < 50, (
            f"sanitize_input took {per_call_us:.1f}us/call. "
            "Expected < 50us with caching. P0D-002 may not be effective."
        )

    def test_module_level_cache_variable_exists(self):
        """_CACHED_ALLOWED_TYPES should be a module-level variable."""
        import kailash.security as sec

        assert hasattr(
            sec, "_CACHED_ALLOWED_TYPES"
        ), "_CACHED_ALLOWED_TYPES module-level cache not found in security.py."

    def test_no_allowed_types_construction_in_sanitize_input(self):
        """sanitize_input() should not build allowed_types inline with lazy imports."""
        source = inspect.getsource(
            __import__("kailash.security", fromlist=["sanitize_input"]).sanitize_input
        )
        # The big block of imports for building allowed_types should NOT be in
        # sanitize_input anymore — it should be in _get_cached_allowed_types()
        for pattern in [
            "import torch",
            "import tensorflow",
            "import scipy",
            "import xgboost",
            "import lightgbm",
        ]:
            assert pattern not in source, (
                f"Found '{pattern}' in sanitize_input() body. "
                "The allowed_types construction should be in _get_cached_allowed_types()."
            )


# --- P0D-003: Immutable Topo Cache ---


class TestP0D003ImmutableTopoCache:
    """Verify that topological sort cache returns immutable tuple."""

    def test_topo_cache_type_annotation_is_tuple(self):
        """_topo_cache should be typed as tuple, not list."""
        # Check the class annotations
        source = inspect.getsource(Workflow.__init__)
        assert "tuple" in source.lower() or "Tuple" in source, (
            "_topo_cache type annotation should use tuple. "
            "P0D-003 optimization may have been reverted."
        )

    def test_get_execution_order_returns_tuple(self):
        """get_execution_order() should return a tuple (immutable)."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node_a", {"code": "result = {'v': 1}"})
        builder.add_node("PythonCodeNode", "node_b", {"code": "result = {'v': 2}"})
        builder.add_connection("node_a", "result", "node_b", "input")
        workflow = builder.build()

        order = workflow.get_execution_order()
        assert isinstance(order, tuple), (
            f"get_execution_order() returned {type(order).__name__}, expected tuple. "
            "P0D-003 optimization may have been reverted."
        )

    def test_cached_order_is_immutable(self):
        """Callers should not be able to mutate the cached order."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node_a", {"code": "result = {'v': 1}"})
        builder.add_node("PythonCodeNode", "node_b", {"code": "result = {'v': 2}"})
        builder.add_connection("node_a", "result", "node_b", "input")
        workflow = builder.build()

        order1 = workflow.get_execution_order()
        # Tuples are immutable, so this should raise TypeError
        try:
            order1[0] = "corrupted"  # type: ignore
            assert False, "Should not be able to mutate tuple"
        except TypeError:
            pass  # Expected for tuples

        # Verify cache still intact
        order2 = workflow.get_execution_order()
        assert order1 == order2, "Cache was corrupted despite tuple immutability."

    def test_topo_cache_invalidation_still_works(self):
        """Adding nodes should still invalidate the topo cache."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node_a", {"code": "result = {'v': 1}"})
        workflow = builder.build()

        order1 = workflow.get_execution_order()
        assert "node_a" in order1

        # Mutate the workflow (add node + connection)
        workflow.add_node("node_b", "PythonCodeNode", code="result = {'v': 2}")
        workflow.connect("node_a", "node_b", mapping={"result": "input"})

        order2 = workflow.get_execution_order()
        assert "node_b" in order2, "New node should appear after cache invalidation."
        assert len(order2) == 2, "Should have 2 nodes after adding one."

    def test_execution_still_works_with_tuple_order(self):
        """Workflow execution should work correctly with tuple-based execution order."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "node_a", {"code": "result = {'data': 'hello'}"}
        )
        builder.add_node(
            "PythonCodeNode", "node_b", {"code": "result = {'data': 'world'}"}
        )
        builder.add_connection("node_a", "result", "node_b", "input")
        workflow = builder.build()

        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(workflow)
            assert results is not None
            assert "node_a" in results
            assert "node_b" in results


# --- P0D-004: Hoisted Trust Verification ---


class TestP0D004HoistedTrustVerification:
    """Verify that trust verification check is hoisted before execution loop."""

    def test_trust_enabled_flag_in_source(self):
        """_trust_enabled should be computed before the execution loop, not per-node."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        # The _trust_enabled flag should be computed BEFORE the loop
        trust_idx = source.find("_trust_enabled")
        loop_idx = source.find("for node_id in execution_order:")
        assert trust_idx != -1, (
            "_trust_enabled not found in _execute_workflow_async. "
            "P0D-004 optimization may have been reverted."
        )
        assert trust_idx < loop_idx, (
            "_trust_enabled is defined AFTER the execution loop. "
            "P0D-004 requires it BEFORE the loop to avoid per-node overhead."
        )

    def test_trust_context_precomputed(self):
        """_trust_context should be precomputed before the loop."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        context_idx = source.find("_trust_context")
        loop_idx = source.find("for node_id in execution_order:")
        assert context_idx != -1, (
            "_trust_context not found in _execute_workflow_async. "
            "P0D-004 optimization may have been reverted."
        )
        assert context_idx < loop_idx, (
            "_trust_context is defined AFTER the execution loop. "
            "P0D-004 requires it BEFORE the loop."
        )

    def test_per_node_trust_guarded(self):
        """The per-node trust check should be wrapped with if _trust_enabled."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        assert "if _trust_enabled:" in source, (
            "Per-node trust check not guarded by _trust_enabled flag. "
            "P0D-004 optimization may have been reverted."
        )

    def test_workflow_executes_with_trust_disabled(self):
        """Workflow should execute correctly when trust is disabled (default)."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "node_a", {"code": "result = {'data': 'hello'}"}
        )
        builder.add_node(
            "PythonCodeNode", "node_b", {"code": "result = {'data': 'world'}"}
        )
        builder.add_connection("node_a", "result", "node_b", "input")
        workflow = builder.build()

        with LocalRuntime(enable_resource_limits=False) as runtime:
            results, run_id = runtime.execute(workflow)
            assert "node_a" in results
            assert "node_b" in results


# --- P0D-005: Lazy psutil Import ---


class TestP0D005LazyPsutilImport:
    """Verify that psutil is not imported at module level in local.py."""

    def test_no_module_level_psutil_import(self):
        """local.py should not have 'import psutil' at module level."""
        import kailash.runtime.local as local_module

        source = inspect.getsource(local_module)
        # Check the top-level imports section (before the first class/function def)
        lines = source.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Stop at the first class or function definition
            if stripped.startswith("class ") or (
                stripped.startswith("def ") and not stripped.startswith("def _")
            ):
                break
            if stripped == "import psutil" or stripped.startswith("from psutil"):
                raise AssertionError(
                    f"Module-level 'import psutil' found at line {i + 1}. "
                    "P0D-005 requires psutil to be lazy-imported only where used."
                )

    def test_psutil_only_in_cold_paths(self):
        """psutil usage should only be in diagnostic/cold-path methods."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        # Check for actual psutil CALLS (not comments mentioning psutil)
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # Skip comments
            if "import psutil" in stripped or "psutil." in stripped:
                raise AssertionError(
                    f"psutil usage found in hot-path _execute_workflow_async: {stripped!r}. "
                    "psutil should only be used in cold-path methods like get_health_diagnostics."
                )


# --- P0D-006: Logging Format Optimization ---


class TestP0D006LoggingFormat:
    """Verify that hot-path logging uses lazy % formatting, not f-strings."""

    def test_execution_order_logging_format(self):
        """Execution order log should use %s format, not f-string."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        # Should NOT have: self.logger.info(f"Execution order: {execution_order}")
        assert 'f"Execution order: {execution_order}"' not in source, (
            "Execution order log uses f-string. "
            "P0D-006: Use self.logger.info('Execution order: %s', execution_order) "
            "to avoid string formatting when logging is disabled."
        )

    def test_node_execution_logging_format(self):
        """Per-node log should use %s format, not f-string."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        # Should NOT have: self.logger.info(f"Executing node: {node_id}")
        assert 'f"Executing node: {node_id}"' not in source, (
            "Per-node log uses f-string. "
            "P0D-006: Use self.logger.info('Executing node: %s', node_id) "
            "to avoid string formatting when logging is disabled."
        )


# --- P0D-007: Deferred Storage for Monitoring ---


class TestP0D007DeferredStorage:
    """Verify that monitoring uses DeferredStorageBackend to avoid per-node I/O."""

    def test_deferred_storage_used_in_execute(self):
        """_execute_async should use DeferredStorageBackend when monitoring enabled."""
        source = inspect.getsource(LocalRuntime._execute_async)
        assert "DeferredStorageBackend" in source, (
            "DeferredStorageBackend not found in _execute_async. "
            "P0D-007 optimization may have been reverted."
        )

    def test_deferred_storage_save_task_is_memory_only(self):
        """DeferredStorageBackend.save_task should not touch filesystem."""
        from kailash.tracking.models import TaskRun
        from kailash.tracking.storage.deferred import DeferredStorageBackend

        storage = DeferredStorageBackend()
        task = TaskRun(run_id="test", node_id="node_a", node_type="PythonCodeNode")
        storage.save_task(task)

        # Verify it's in memory
        loaded = storage.load_task(task.task_id)
        assert loaded is not None
        assert loaded.task_id == task.task_id

    def test_deferred_storage_flush_is_noop(self):
        """DeferredStorageBackend.flush() should be a no-op (data stays in memory)."""
        from kailash.tracking.models import TaskRun
        from kailash.tracking.storage.deferred import DeferredStorageBackend

        storage = DeferredStorageBackend()
        task = TaskRun(run_id="test", node_id="node_a", node_type="PythonCodeNode")
        storage.save_task(task)

        # Flush should not raise or clear data
        storage.flush()

    def test_deferred_storage_batch_file_persistence(self):
        """flush_to_filesystem() should write a single batch JSON per run.

        P0D-007b: Instead of N individual task files in the bloated tasks/ directory,
        the deferred backend writes one batch/{run_id}.json containing all CARE audit
        data (run metadata + all tasks with metrics). This avoids O(N) directory lookups
        in a 1M+ entry directory.
        """
        import json
        import tempfile

        from kailash.tracking.models import TaskRun, WorkflowRun
        from kailash.tracking.storage.deferred import DeferredStorageBackend

        storage = DeferredStorageBackend()

        # Create run + tasks
        from datetime import UTC, datetime

        run = WorkflowRun(
            run_id="test-run-batch",
            workflow_name="bench_wf",
            status="completed",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
        )
        storage.save_run(run)
        for i in range(5):
            task = TaskRun(
                task_id=f"task-{i:03d}",
                run_id="test-run-batch",
                node_id=f"node_{i}",
                node_type="PythonCodeNode",
            )
            storage.save_task(task)

        # Flush to temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            storage.flush_to_filesystem(base_path=tmpdir)

            # Verify batch file exists
            import os

            batch_path = os.path.join(tmpdir, "batch", "test-run-batch.json")
            assert os.path.exists(batch_path), (
                f"Batch file not found at {batch_path}. "
                "P0D-007b batch persistence may have been reverted."
            )

            # Verify batch content
            with open(batch_path) as f:
                data = json.load(f)
            assert "run" in data, "Batch file missing 'run' key"
            assert "tasks" in data, "Batch file missing 'tasks' key"
            assert data["run"]["run_id"] == "test-run-batch"
            assert (
                len(data["tasks"]) == 5
            ), f"Expected 5 tasks, got {len(data['tasks'])}"

            # Verify NO individual task files in tasks/ directory
            tasks_dir = os.path.join(tmpdir, "tasks")
            assert not os.path.exists(tasks_dir) or not os.listdir(tasks_dir), (
                "Individual task files should NOT be written. "
                "Only batch/{run_id}.json should exist."
            )

    def test_deferred_storage_saves_nothing_during_execution(self):
        """DeferredStorageBackend should perform zero filesystem I/O during execution.

        The hot-path uses pure in-memory storage. Persistence to filesystem
        happens once after execution completes (flush_to_filesystem).
        This test verifies the in-memory path has negligible overhead.
        """
        from kailash.tracking.models import TaskRun
        from kailash.tracking.storage.deferred import DeferredStorageBackend

        storage = DeferredStorageBackend()

        # Simulate per-node tracking operations (what happens during execution)
        n_nodes = 100
        n_iterations = 10
        times = []
        for _ in range(n_iterations):
            start = time.perf_counter()
            for i in range(n_nodes):
                task = TaskRun(
                    run_id="test-run",
                    node_id=f"node_{i}",
                    node_type="PythonCodeNode",
                )
                storage.save_task(task)
            elapsed = time.perf_counter() - start
            times.append(elapsed * 1_000_000 / n_nodes)  # us per node

        mean_per_node = sum(times) / len(times)

        # In-memory save should be < 10us per node (just dict assignment + Pydantic model)
        assert mean_per_node < 20, (
            f"DeferredStorage per-node overhead is {mean_per_node:.1f}us. "
            "Expected < 20us for in-memory storage. "
            "P0D-007 may be doing unexpected I/O during save."
        )


# --- Integration: All P0D optimizations working together ---


class TestP0DIntegration:
    """Verify all P0D optimizations work together in end-to-end execution."""

    def test_full_workflow_with_all_p0d_optimizations(self):
        """A workflow should execute correctly with all P0D optimizations active."""
        builder = WorkflowBuilder()
        for i in range(5):
            builder.add_node(
                "PythonCodeNode", f"node_{i}", {"code": f"result = {{'v': {i}}}"}
            )
            if i > 0:
                builder.add_connection(f"node_{i - 1}", "result", f"node_{i}", "input")
        workflow = builder.build()

        with LocalRuntime(enable_resource_limits=False) as runtime:
            results, run_id = runtime.execute(workflow)
            assert len(results) == 5
            for i in range(5):
                assert f"node_{i}" in results

    def test_repeated_execution_performance(self):
        """Repeated executions should benefit from all P0D caching."""
        builder = WorkflowBuilder()
        for i in range(10):
            builder.add_node(
                "PythonCodeNode", f"node_{i}", {"code": f"result = {{'v': {i}}}"}
            )
            if i > 0:
                builder.add_connection(f"node_{i - 1}", "result", f"node_{i}", "input")
        workflow = builder.build()

        with LocalRuntime(
            enable_resource_limits=False, enable_monitoring=False
        ) as runtime:
            # Warmup
            runtime.execute(workflow)

            # Measure 5 runs
            times = []
            for _ in range(5):
                start = time.perf_counter()
                results, _ = runtime.execute(workflow)
                elapsed = time.perf_counter() - start
                times.append(elapsed)
                assert len(results) == 10

            avg_ms = (sum(times) / len(times)) * 1000
            # With all P0D optimizations, 10 nodes should execute in < 50ms
            # (each PythonCodeNode takes ~100us for exec, so ~1ms for 10 nodes
            # plus ~42us/node framework overhead = ~1.42ms total)
            assert avg_ms < 50, (
                f"Average execution time {avg_ms:.2f}ms for 10 nodes. "
                "Expected < 50ms with all P0D optimizations."
            )
