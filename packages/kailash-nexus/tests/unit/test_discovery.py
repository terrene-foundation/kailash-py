"""Unit tests for workflow auto-discovery functionality.

Tests the discovery module that automatically finds and registers
workflows in the current directory.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestWorkflowDiscovery:
    """Test workflow auto-discovery functionality."""

    def test_discover_workflows_patterns(self):
        """Test that discovery finds workflows matching patterns."""
        from nexus.discovery import WorkflowDiscovery

        # Create a temporary directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files matching patterns
            workflows_dir = Path(tmpdir) / "workflows"
            workflows_dir.mkdir()

            test_files = [
                workflows_dir / "test1.py",
                Path(tmpdir) / "test.workflow.py",
                Path(tmpdir) / "workflow_test2.py",
            ]

            for file in test_files:
                file.write_text(
                    """
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "agent", {"code": "result = 'hello'"})
"""
                )

            # Discover workflows
            discovery = WorkflowDiscovery(tmpdir)
            workflows = discovery.discover()

            # Should find all three workflows
            assert len(workflows) >= 3

    def test_load_workflow_from_file_success(self):
        """Test successful workflow loading from file."""
        from kailash.workflow import Workflow
        from nexus.discovery import WorkflowDiscovery

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a valid workflow file
            test_file = Path(tmpdir) / "test_workflow.py"
            test_file.write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "agent", {"code": "result = 'hello'"})
"""
            )

            discovery = WorkflowDiscovery(tmpdir)
            discovery._load_workflow_from_file(test_file)

            # Should have loaded the workflow
            assert len(discovery._discovered_workflows) == 1
            assert "test_workflow" in list(discovery._discovered_workflows.keys())[0]

    def test_load_workflow_error_handling(self):
        """Test handling of import errors."""
        from nexus.discovery import WorkflowDiscovery

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with syntax error
            bad_file = Path(tmpdir) / "bad_workflow.py"
            bad_file.write_text("invalid python syntax here!")

            with patch("nexus.discovery.logger") as mock_logger:
                discovery = WorkflowDiscovery(tmpdir)
                discovery._load_workflow_from_file(bad_file)

                # Should log warning and continue
                mock_logger.warning.assert_called()
                assert len(discovery._discovered_workflows) == 0

    def test_is_workflow_validation(self):
        """Test workflow object validation."""
        from kailash.workflow import Workflow
        from kailash.workflow.builder import WorkflowBuilder
        from nexus.discovery import WorkflowDiscovery

        discovery = WorkflowDiscovery()

        # Valid workflow
        workflow = Mock(spec=Workflow)
        assert discovery._is_workflow(workflow) is True

        # Valid WorkflowBuilder
        builder = Mock(spec=WorkflowBuilder)
        assert discovery._is_workflow(builder) is True

        # Valid factory function
        def workflow_factory():
            return Mock(spec=Workflow)

        assert discovery._is_workflow(workflow_factory) is True

        # Invalid object
        not_workflow = "not a workflow"
        assert discovery._is_workflow(not_workflow) is False

    def test_prepare_workflow(self):
        """Test workflow preparation."""
        from kailash.workflow import Workflow
        from kailash.workflow.builder import WorkflowBuilder
        from nexus.discovery import WorkflowDiscovery

        discovery = WorkflowDiscovery()

        # Already a workflow
        workflow = Mock(spec=Workflow)
        result = discovery._prepare_workflow(workflow)
        assert result is workflow

        # WorkflowBuilder
        builder = Mock(spec=WorkflowBuilder)
        built_workflow = Mock(spec=Workflow)
        builder.build.return_value = built_workflow
        result = discovery._prepare_workflow(builder)
        assert result is built_workflow
        builder.build.assert_called_once()

    def test_generate_workflow_name(self):
        """Test workflow name generation."""
        from nexus.discovery import WorkflowDiscovery

        discovery = WorkflowDiscovery()

        # Generic object name uses file name
        name = discovery._generate_workflow_name(Path("test.py"), "workflow")
        assert name == "test"

        # Specific object name combines with file
        name = discovery._generate_workflow_name(Path("api.py"), "UserWorkflow")
        assert name == "api.UserWorkflow"

        # Works with complex paths
        name = discovery._generate_workflow_name(Path("workflows/data.py"), "builder")
        assert name == "data"

    def test_exclude_files(self):
        """Test that excluded files are skipped."""
        from nexus.discovery import WorkflowDiscovery

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files that should be excluded
            excluded_files = [
                Path(tmpdir) / "__init__.py",
                Path(tmpdir) / "setup.py",
                Path(tmpdir) / "conftest.py",
            ]

            for file in excluded_files:
                file.write_text("# Should be ignored")

            # Create one valid file
            valid_file = Path(tmpdir) / "valid_workflow.py"
            valid_file.write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "agent", {"code": "result = 'hello'"})
"""
            )

            discovery = WorkflowDiscovery(tmpdir)
            workflows = discovery.discover()

            # Should only find the valid file
            assert len(workflows) == 1
            assert "valid_workflow" in list(workflows.keys())[0]

    def test_empty_directory_handling(self):
        """Test handling of empty directory."""
        from nexus.discovery import discover_workflows

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("nexus.discovery.logger") as mock_logger:
                workflows = discover_workflows(tmpdir)

                # Should return empty dict and log info
                assert workflows == {}
                # Should log discovery start and result
                assert mock_logger.info.call_count >= 2

    def test_factory_function_discovery(self):
        """Test discovery of workflow factory functions."""
        from nexus.discovery import WorkflowDiscovery

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with factory function
            factory_file = Path(tmpdir) / "factory_workflow.py"
            factory_file.write_text(
                """
from kailash.workflow.builder import WorkflowBuilder

def create_workflow():
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "agent", {"code": "result = 'hello'"})
    return builder

# Export the factory
workflow_factory = create_workflow
"""
            )

            discovery = WorkflowDiscovery(tmpdir)
            workflows = discovery.discover()

            # Should discover the factory (may find multiple objects)
            assert len(workflows) >= 1
            # At least one should be our factory
            assert any(
                "workflow_factory" in name or "create_workflow" in name
                for name in workflows.keys()
            )
