"""Unit tests for BaseRuntime state management.

Tests run ID generation, metadata tracking, workflow caching, and
enterprise feature helpers.
"""

import time

import pytest
from kailash.runtime.base import BaseRuntime
from kailash.workflow import Workflow

from tests.unit.runtime.helpers_runtime import (
    create_minimal_workflow,
    create_valid_workflow,
)


class ConcreteRuntime(BaseRuntime):
    """Concrete implementation for testing abstract base."""

    def execute(self, workflow: Workflow, **kwargs):
        """Minimal execute implementation."""
        return {}, "test-run-id"


class TestRunIDGeneration:
    """Test run ID generation and uniqueness."""

    def test_generate_run_id_format(self):
        """Test run ID is valid UUID format."""
        runtime = ConcreteRuntime()
        run_id = runtime._generate_run_id()

        # Should be a string
        assert isinstance(run_id, str)
        # Should be non-empty
        assert len(run_id) > 0
        # Should be UUID format (contains hyphens)
        assert "-" in run_id

    def test_generate_run_id_uniqueness(self):
        """Test that generated run IDs are unique."""
        runtime = ConcreteRuntime()

        # Generate multiple run IDs
        run_ids = [runtime._generate_run_id() for _ in range(100)]

        # All should be unique
        assert len(run_ids) == len(set(run_ids))

    def test_generate_run_id_multiple_runtimes(self):
        """Test run IDs are unique across runtime instances."""
        runtime1 = ConcreteRuntime()
        runtime2 = ConcreteRuntime()

        run_id1 = runtime1._generate_run_id()
        run_id2 = runtime2._generate_run_id()

        # Should be different
        assert run_id1 != run_id2


class TestExecutionMetadata:
    """Test execution metadata initialization and management."""

    def test_initialize_execution_metadata_structure(self):
        """Test metadata initialization creates correct structure."""
        runtime = ConcreteRuntime()
        workflow = create_valid_workflow()
        run_id = runtime._generate_run_id()

        metadata = runtime._initialize_execution_metadata(workflow, run_id)

        # Check all expected fields
        assert metadata["run_id"] == run_id
        assert "workflow_id" in metadata
        assert metadata["start_time"] is None  # Set by runtime during execution
        assert metadata["end_time"] is None  # Set by runtime after execution
        assert metadata["status"] == "initializing"
        assert "node_count" in metadata
        assert metadata["node_count"] > 0
        assert isinstance(metadata["executed_nodes"], list)
        assert len(metadata["executed_nodes"]) == 0
        assert isinstance(metadata["skipped_nodes"], list)
        assert len(metadata["skipped_nodes"]) == 0

    def test_initialize_execution_metadata_with_workflow_id(self):
        """Test metadata includes workflow ID when available."""
        runtime = ConcreteRuntime()
        workflow = Workflow(workflow_id="test-workflow-123", name="Test")
        run_id = runtime._generate_run_id()

        metadata = runtime._initialize_execution_metadata(workflow, run_id)

        assert metadata["workflow_id"] == "test-workflow-123"

    def test_initialize_execution_metadata_without_workflow_id(self):
        """Test metadata handles missing workflow ID."""
        runtime = ConcreteRuntime()
        # Workflow without explicit workflow_id
        workflow = create_valid_workflow()
        run_id = runtime._generate_run_id()

        metadata = runtime._initialize_execution_metadata(workflow, run_id)

        # Should still have workflow_id key (may be None)
        assert "workflow_id" in metadata

    def test_update_execution_metadata(self):
        """Test updating execution metadata."""
        runtime = ConcreteRuntime()
        workflow = create_valid_workflow()
        run_id = runtime._generate_run_id()

        # Initialize metadata
        metadata = runtime._initialize_execution_metadata(workflow, run_id)
        runtime._execution_metadata[run_id] = metadata

        # Update metadata
        updates = {
            "status": "running",
            "start_time": time.time(),
            "executed_nodes": ["node1", "node2"],
        }
        runtime._update_execution_metadata(run_id, updates)

        # Verify updates
        updated_metadata = runtime._execution_metadata[run_id]
        assert updated_metadata["status"] == "running"
        assert updated_metadata["start_time"] is not None
        assert len(updated_metadata["executed_nodes"]) == 2

    def test_update_execution_metadata_nonexistent_run(self):
        """Test updating metadata for nonexistent run ID."""
        runtime = ConcreteRuntime()

        # Try to update non-existent run (should log warning but not crash)
        runtime._update_execution_metadata("nonexistent-run-id", {"status": "running"})

        # Should not create entry
        assert "nonexistent-run-id" not in runtime._execution_metadata

    def test_get_execution_metadata(self):
        """Test retrieving execution metadata."""
        runtime = ConcreteRuntime()
        workflow = create_valid_workflow()
        run_id = runtime._generate_run_id()

        # Initialize and store metadata
        metadata = runtime._initialize_execution_metadata(workflow, run_id)
        runtime._execution_metadata[run_id] = metadata

        # Retrieve metadata
        retrieved = runtime._get_execution_metadata(run_id)

        assert retrieved is not None
        assert retrieved == metadata
        assert retrieved["run_id"] == run_id

    def test_get_execution_metadata_nonexistent(self):
        """Test retrieving metadata for nonexistent run."""
        runtime = ConcreteRuntime()

        metadata = runtime._get_execution_metadata("nonexistent-run-id")

        assert metadata is None


class TestWorkflowCaching:
    """Test workflow caching functionality."""

    def test_cache_workflow(self):
        """Test caching a workflow."""
        runtime = ConcreteRuntime()
        workflow = create_valid_workflow()
        workflow_id = "test-workflow-123"

        # Cache workflow
        runtime._cache_workflow(workflow_id, workflow)

        # Verify cached
        assert workflow_id in runtime._workflow_cache
        assert runtime._workflow_cache[workflow_id] is workflow

    def test_get_cached_workflow_exists(self):
        """Test retrieving cached workflow."""
        runtime = ConcreteRuntime()
        workflow = create_valid_workflow()
        workflow_id = "test-workflow-123"

        # Cache workflow
        runtime._cache_workflow(workflow_id, workflow)

        # Retrieve cached workflow
        cached = runtime._get_cached_workflow(workflow_id)

        assert cached is not None
        assert cached is workflow

    def test_get_cached_workflow_not_exists(self):
        """Test retrieving non-cached workflow."""
        runtime = ConcreteRuntime()

        cached = runtime._get_cached_workflow("nonexistent-workflow")

        assert cached is None

    def test_cache_multiple_workflows(self):
        """Test caching multiple workflows."""
        runtime = ConcreteRuntime()

        workflows = {
            "workflow1": create_valid_workflow(),
            "workflow2": create_minimal_workflow(),
            "workflow3": create_valid_workflow(),
        }

        # Cache all workflows
        for wf_id, wf in workflows.items():
            runtime._cache_workflow(wf_id, wf)

        # Verify all cached
        assert len(runtime._workflow_cache) == 3
        for wf_id, wf in workflows.items():
            cached = runtime._get_cached_workflow(wf_id)
            assert cached is wf

    def test_cache_workflow_overwrites_existing(self):
        """Test caching overwrites existing workflow."""
        runtime = ConcreteRuntime()
        workflow_id = "test-workflow"

        workflow1 = create_valid_workflow()
        workflow2 = create_minimal_workflow()

        # Cache first workflow
        runtime._cache_workflow(workflow_id, workflow1)
        assert runtime._get_cached_workflow(workflow_id) is workflow1

        # Cache second workflow with same ID
        runtime._cache_workflow(workflow_id, workflow2)
        assert runtime._get_cached_workflow(workflow_id) is workflow2
        assert runtime._get_cached_workflow(workflow_id) is not workflow1

    def test_clear_cache(self):
        """Test clearing workflow cache and execution metadata."""
        runtime = ConcreteRuntime()

        # Add workflows to cache
        runtime._cache_workflow("workflow1", create_valid_workflow())
        runtime._cache_workflow("workflow2", create_minimal_workflow())

        # Add execution metadata
        run_id = runtime._generate_run_id()
        workflow = create_valid_workflow()
        metadata = runtime._initialize_execution_metadata(workflow, run_id)
        runtime._execution_metadata[run_id] = metadata

        # Verify data exists
        assert len(runtime._workflow_cache) == 2
        assert len(runtime._execution_metadata) == 1

        # Clear cache
        runtime._clear_cache()

        # Verify cleared
        assert len(runtime._workflow_cache) == 0
        assert len(runtime._execution_metadata) == 0

    def test_clear_cache_empty(self):
        """Test clearing empty cache doesn't error."""
        runtime = ConcreteRuntime()

        # Clear empty cache (should not error)
        runtime._clear_cache()

        assert len(runtime._workflow_cache) == 0
        assert len(runtime._execution_metadata) == 0

    def test_cache_workflow_debug_logging(self):
        """Test workflow caching logs in debug mode."""
        runtime = ConcreteRuntime(debug=True)
        workflow = create_valid_workflow()
        workflow_id = "test-workflow"

        # Cache workflow (debug logging should occur)
        runtime._cache_workflow(workflow_id, workflow)

        # Verify cached (logging is tested via manual inspection/coverage)
        assert workflow_id in runtime._workflow_cache


class TestEnterpriseFeatureHelpers:
    """Test enterprise feature helper methods."""

    def test_check_workflow_access_with_security_and_user(self):
        """Test workflow access check with security enabled."""
        user_context = {"user_id": "test_user", "role": "admin"}
        runtime = ConcreteRuntime(enable_security=True, user_context=user_context)
        workflow = create_valid_workflow()

        # Should not raise (placeholder implementation)
        runtime._check_workflow_access(workflow)

    def test_check_workflow_access_security_disabled(self):
        """Test workflow access check when security disabled."""
        runtime = ConcreteRuntime(enable_security=False)
        workflow = create_valid_workflow()

        # Should not raise
        runtime._check_workflow_access(workflow)

    def test_check_workflow_access_no_user_context(self):
        """Test workflow access check without user context."""
        runtime = ConcreteRuntime(enable_security=True, user_context=None)
        workflow = create_valid_workflow()

        # Should not raise (no user to check)
        runtime._check_workflow_access(workflow)


class TestRuntimeIDGeneration:
    """Test runtime ID generation and uniqueness."""

    def test_runtime_id_format(self):
        """Test runtime ID has expected format."""
        runtime = ConcreteRuntime()

        assert runtime._runtime_id is not None
        assert isinstance(runtime._runtime_id, str)
        assert "runtime_" in runtime._runtime_id

    def test_runtime_id_uniqueness(self):
        """Test runtime IDs are unique per instance."""
        runtime1 = ConcreteRuntime()
        runtime2 = ConcreteRuntime()

        assert runtime1._runtime_id != runtime2._runtime_id

    def test_runtime_id_includes_timestamp(self):
        """Test runtime ID includes timestamp component."""
        runtime = ConcreteRuntime()

        # ID format: runtime_{object_id}_{timestamp}
        parts = runtime._runtime_id.split("_")
        assert len(parts) >= 3
        assert parts[0] == "runtime"

        # Last part should be numeric timestamp
        timestamp_part = parts[-1]
        assert timestamp_part.isdigit()


class TestStateManagementIntegration:
    """Test integration of state management features."""

    def test_full_execution_metadata_lifecycle(self):
        """Test complete metadata lifecycle."""
        runtime = ConcreteRuntime()
        workflow = create_valid_workflow()

        # 1. Generate run ID
        run_id = runtime._generate_run_id()
        assert run_id is not None

        # 2. Initialize metadata
        metadata = runtime._initialize_execution_metadata(workflow, run_id)
        assert metadata["status"] == "initializing"
        runtime._execution_metadata[run_id] = metadata

        # 3. Update to running
        runtime._update_execution_metadata(
            run_id, {"status": "running", "start_time": time.time()}
        )
        assert runtime._execution_metadata[run_id]["status"] == "running"

        # 4. Update progress
        runtime._update_execution_metadata(
            run_id, {"executed_nodes": ["node1", "node2"]}
        )
        assert len(runtime._execution_metadata[run_id]["executed_nodes"]) == 2

        # 5. Complete execution
        runtime._update_execution_metadata(
            run_id, {"status": "completed", "end_time": time.time()}
        )
        assert runtime._execution_metadata[run_id]["status"] == "completed"

        # 6. Retrieve final metadata
        final_metadata = runtime._get_execution_metadata(run_id)
        assert final_metadata["status"] == "completed"
        assert final_metadata["start_time"] is not None
        assert final_metadata["end_time"] is not None

    def test_multiple_concurrent_executions(self):
        """Test tracking multiple concurrent executions."""
        runtime = ConcreteRuntime()
        workflow = create_valid_workflow()

        # Create multiple execution contexts
        run_ids = [runtime._generate_run_id() for _ in range(5)]

        # Initialize metadata for all
        for run_id in run_ids:
            metadata = runtime._initialize_execution_metadata(workflow, run_id)
            runtime._execution_metadata[run_id] = metadata

        # All should be tracked separately
        assert len(runtime._execution_metadata) == 5

        # Update each independently
        for i, run_id in enumerate(run_ids):
            runtime._update_execution_metadata(run_id, {"executed_nodes": [f"node{i}"]})

        # Verify independence
        for i, run_id in enumerate(run_ids):
            metadata = runtime._get_execution_metadata(run_id)
            assert metadata["executed_nodes"] == [f"node{i}"]

    def test_cache_and_metadata_independence(self):
        """Test workflow cache and execution metadata are independent."""
        runtime = ConcreteRuntime()
        workflow = create_valid_workflow()

        # Cache workflow
        runtime._cache_workflow("workflow1", workflow)
        assert len(runtime._workflow_cache) == 1
        assert len(runtime._execution_metadata) == 0

        # Add execution metadata
        run_id = runtime._generate_run_id()
        metadata = runtime._initialize_execution_metadata(workflow, run_id)
        runtime._execution_metadata[run_id] = metadata
        assert len(runtime._workflow_cache) == 1
        assert len(runtime._execution_metadata) == 1

        # Clear cache clears both
        runtime._clear_cache()
        assert len(runtime._workflow_cache) == 0
        assert len(runtime._execution_metadata) == 0
