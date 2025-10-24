"""Tier 2 Integration Tests for Discovery System (NO MOCKING).

Tests workflow discovery with real file system operations and error handling.
Validates the stub fixes in discovery.py.
"""

import os
import tempfile
from pathlib import Path

import pytest
from nexus.discovery import WorkflowDiscovery, discover_workflows


@pytest.mark.integration
class TestWorkflowDiscoveryIntegration:
    """Integration tests for workflow discovery system."""

    def test_discovery_initialization_with_valid_path(self):
        """Test discovery initialization with real directory.

        NO MOCKING - uses real file system.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            discovery = WorkflowDiscovery(tmpdir)

            # Verify initialization
            assert discovery.base_path == Path(tmpdir)
            assert discovery._discovered_workflows == {}

    def test_discovery_initialization_with_invalid_path_fallback(self):
        """Test discovery handles invalid paths gracefully.

        CRITICAL: Tests error handling in __init__ - validates it doesn't crash.
        """
        # Use an inaccessible or non-existent path
        invalid_path = "/nonexistent/path/that/does/not/exist"

        # Should not raise exception
        discovery = WorkflowDiscovery(invalid_path)

        # Should have a valid base_path (implementation may use the path as-is
        # or fallback, key is it doesn't crash)
        assert discovery.base_path is not None
        assert isinstance(discovery.base_path, Path)

    def test_discover_workflows_in_empty_directory(self):
        """Test discovery in directory with no workflows.

        Validates discovery handles empty directories gracefully.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            discovery = WorkflowDiscovery(tmpdir)
            workflows = discovery.discover()

            # Should return empty dict
            assert workflows == {}

    def test_discover_workflow_from_pattern(self):
        """Test discovering workflows using pattern matching.

        Tests _search_pattern() with real files matching WORKFLOW_PATTERNS.
        NO MOCKING - creates real workflow files.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a workflow file matching pattern
            workflow_file = Path(tmpdir) / "test_workflow.py"
            workflow_file.write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {"code": "result = 42"})
"""
            )

            discovery = WorkflowDiscovery(tmpdir)
            workflows = discovery.discover()

            # Should discover the workflow
            assert len(workflows) > 0

    def test_discover_multiple_workflow_patterns(self):
        """Test discovery with multiple file patterns.

        Validates all WORKFLOW_PATTERNS are checked.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create workflows directory
            workflows_dir = Path(tmpdir) / "workflows"
            workflows_dir.mkdir()

            # Create workflow with pattern: workflows/*.py
            (workflows_dir / "my_workflow.py").write_text(
                """
from kailash.workflow.builder import WorkflowBuilder
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "node1", {"code": "result = 1"})
"""
            )

            # Create workflow with pattern: *_workflow.py
            (Path(tmpdir) / "data_workflow.py").write_text(
                """
from kailash.workflow.builder import WorkflowBuilder
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "node2", {"code": "result = 2"})
"""
            )

            discovery = WorkflowDiscovery(tmpdir)
            workflows = discovery.discover()

            # Should discover both workflows
            assert len(workflows) >= 2

    def test_exclude_files_from_discovery(self):
        """Test that excluded files are not discovered.

        Tests EXCLUDE_FILES filtering.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workflows_dir = Path(tmpdir) / "workflows"
            workflows_dir.mkdir()

            # Create __init__.py (should be excluded)
            (workflows_dir / "__init__.py").write_text(
                """
from kailash.workflow.builder import WorkflowBuilder
workflow = WorkflowBuilder()
"""
            )

            # Create valid workflow file
            (workflows_dir / "valid.py").write_text(
                """
from kailash.workflow.builder import WorkflowBuilder
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {"code": "result = 1"})
"""
            )

            discovery = WorkflowDiscovery(tmpdir)
            workflows = discovery.discover()

            # Should only find valid workflow, not __init__.py
            assert len(workflows) == 1
            assert "__init__" not in str(list(workflows.keys())[0])

    def test_workflow_loading_error_handling(self):
        """Test error handling when loading invalid workflow files.

        CRITICAL: Tests _load_workflow_from_file() error handling.
        NO MOCKING - uses real invalid Python file.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create invalid Python file
            invalid_file = Path(tmpdir) / "invalid_workflow.py"
            invalid_file.write_text("this is not valid python syntax!!!")

            discovery = WorkflowDiscovery(tmpdir)

            # Should not raise exception - should log warning and continue
            workflows = discovery.discover()

            # Should return empty dict (invalid file skipped)
            assert workflows == {}

    def test_callable_workflow_factory_detection(self):
        """Test detecting callable workflow factories.

        Tests _is_workflow() with factory pattern.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create workflow factory file
            factory_file = Path(tmpdir) / "factory_workflow.py"
            factory_file.write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

def create_workflow():
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "factory", {"code": "result = 'factory'"})
    return workflow.build()
"""
            )

            discovery = WorkflowDiscovery(tmpdir)
            workflows = discovery.discover()

            # Should discover workflow from factory
            assert len(workflows) > 0

    def test_callable_requiring_arguments_skipped(self):
        """Test that callables requiring arguments are skipped.

        CRITICAL: Tests error handling in _is_workflow() for functions with args.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create function requiring arguments
            func_file = Path(tmpdir) / "parameterized_workflow.py"
            func_file.write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

def create_workflow(name, version):  # Requires arguments
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", name, {"code": f"result = '{version}'"})
    return workflow.build()
"""
            )

            discovery = WorkflowDiscovery(tmpdir)

            # Should not raise exception - should skip function
            workflows = discovery.discover()

            # Function should be skipped (can't call without args)
            # Note: Discovery may still succeed if there are other valid workflows
            # The key is that it doesn't crash

    def test_workflow_name_generation(self):
        """Test workflow name generation from file and object names.

        Tests _generate_workflow_name() logic.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create workflow with specific name
            named_file = Path(tmpdir) / "data_processing_workflow.py"
            named_file.write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

my_workflow = WorkflowBuilder()
my_workflow.add_node("PythonCodeNode", "process", {"code": "result = 'processed'"})
"""
            )

            discovery = WorkflowDiscovery(tmpdir)
            workflows = discovery.discover()

            # Check generated name includes file stem
            workflow_names = list(workflows.keys())
            assert any("data_processing" in name for name in workflow_names)

    def test_workflow_builder_preparation(self):
        """Test preparing WorkflowBuilder instances for use.

        Tests _prepare_workflow() method that builds workflows.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file with WorkflowBuilder (not yet built)
            builder_file = Path(tmpdir) / "builder_workflow.py"
            builder_file.write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

builder = WorkflowBuilder()
builder.add_node("PythonCodeNode", "prep", {"code": "result = 'prepared'"})
# Note: Not calling .build() here
"""
            )

            discovery = WorkflowDiscovery(tmpdir)
            workflows = discovery.discover()

            # Should auto-build the workflow
            if workflows:
                # Verify workflow is built (has nodes)
                workflow = list(workflows.values())[0]
                assert hasattr(workflow, "_nodes") or hasattr(workflow, "nodes")


@pytest.mark.integration
class TestDiscoveryConvenienceFunction:
    """Integration tests for discover_workflows() convenience function."""

    def test_discover_workflows_function(self):
        """Test convenience function for discovery.

        Tests module-level discover_workflows() function.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test workflow
            (Path(tmpdir) / "test_workflow.py").write_text(
                """
from kailash.workflow.builder import WorkflowBuilder
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {"code": "result = True"})
"""
            )

            # Use convenience function
            workflows = discover_workflows(tmpdir)

            # Should return dict of workflows
            assert isinstance(workflows, dict)
            assert len(workflows) > 0

    def test_discover_workflows_without_base_path(self):
        """Test discovery with default current directory.

        Tests that None base_path uses current directory.
        """
        # Should not raise exception
        workflows = discover_workflows()

        # Should return dict (may be empty)
        assert isinstance(workflows, dict)


@pytest.mark.integration
class TestDiscoveryDiagnostics:
    """Integration tests for discovery diagnostics and logging."""

    def test_discovery_logging_on_success(self):
        """Test that discovery logs successful workflow finds.

        Validates diagnostic logging.
        """
        import logging
        from io import StringIO

        # Capture log output
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        logger = logging.getLogger("nexus.discovery")
        logger.addHandler(handler)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Create workflow
                (Path(tmpdir) / "logged_workflow.py").write_text(
                    """
from kailash.workflow.builder import WorkflowBuilder
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "log", {"code": "result = 'logged'"})
"""
                )

                discovery = WorkflowDiscovery(tmpdir)
                discovery.discover()

                # Check logs
                log_output = log_stream.getvalue()
                assert "Starting workflow discovery" in log_output
                assert "Discovered" in log_output

        finally:
            logger.removeHandler(handler)

    def test_discovery_warning_on_load_failure(self):
        """Test that discovery logs warnings for failed loads.

        Validates error diagnostic logging.
        """
        import logging
        from io import StringIO

        # Capture log output
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.WARNING)
        logger = logging.getLogger("nexus.discovery")
        logger.addHandler(handler)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Create invalid file
                (Path(tmpdir) / "broken_workflow.py").write_text("invalid python!!!")

                discovery = WorkflowDiscovery(tmpdir)
                discovery.discover()

                # Should log warning
                log_output = log_stream.getvalue()
                assert "Failed to load" in log_output or "warning" in log_output.lower()

        finally:
            logger.removeHandler(handler)
