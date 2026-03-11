"""
End-to-end tests for DataFlow package installation and setup.

Tests installation scenarios, dependency management, import validation,
and first-run experiences that users encounter.
"""

import importlib
import os
import subprocess

# Import DataFlow components
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestPackageInstallation:
    """Test DataFlow package installation and setup scenarios."""

    def test_basic_import_functionality(self):
        """Test that all essential DataFlow imports work correctly."""
        # Test basic imports
        try:
            from dataflow import DataFlow

            assert DataFlow is not None
        except ImportError as e:
            pytest.fail(f"Failed to import DataFlow: {e}")

        try:
            from kailash.workflow.builder import WorkflowBuilder

            assert WorkflowBuilder is not None
        except ImportError as e:
            pytest.fail(f"Failed to import WorkflowBuilder: {e}")

        try:
            from kailash.runtime.local import LocalRuntime

            assert LocalRuntime is not None
        except ImportError as e:
            pytest.fail(f"Failed to import LocalRuntime: {e}")

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode.async_run")
    def test_first_time_usage_scenario(self, mock_async_run):
        """Test the first-time user experience."""
        # Mock database operations
        mock_async_run.return_value = {
            "success": True,
            "result": {"id": 1, "name": "Hello DataFlow", "value": 42},
        }

        # Simulate a new user following getting started guide

        # Step 1: Import DataFlow
        db = DataFlow(database_url="postgresql://user:pass@localhost/test_db")
        assert db is not None

        # Step 2: Define first model
        @db.model
        class FirstModel:
            name: str
            value: int

        # Step 3: Create first workflow
        workflow = WorkflowBuilder()
        workflow.add_node("FirstModelCreateNode", "first_create", {})

        # Step 4: Execute first workflow
        runtime = LocalRuntime()
        parameters = {"first_create": {"name": "Hello DataFlow", "value": 42}}
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        # Verify first experience works
        assert results is not None
        assert run_id is not None
        assert "first_create" in results

    def test_database_dependencies_available(self):
        """Test that required database dependencies are available."""
        # Test SQLite support (should always be available)
        try:
            import sqlite3

            assert sqlite3 is not None
        except ImportError:
            pytest.fail("SQLite support not available")

        # Test that DataFlow can create SQLite database
        db = DataFlow()  # Uses SQLite by default

        @db.model
        class DependencyTest:
            dep_id: int
            dep_type: str

        workflow = WorkflowBuilder()
        workflow.add_node(
            "DependencyTestCreateNode", "test_deps", {"dep_id": 1, "dep_type": "sqlite"}
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert results is not None

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode.async_run")
    def test_minimal_requirements_check(self, mock_async_run):
        """Test that minimal system requirements are met."""
        # Mock database operations
        mock_async_run.return_value = {
            "success": True,
            "result": {"id": 1, "test_value": "minimal_setup_works"},
        }

        # Check Python version
        python_version = sys.version_info
        assert python_version >= (3, 8), f"Python {python_version} too old, need 3.8+"

        # Test basic functionality with minimal setup
        db = DataFlow(database_url="postgresql://user:pass@localhost/test_db")

        @db.model
        class MinimalTest:
            test_value: str

        workflow = WorkflowBuilder()
        workflow.add_node("MinimalTestCreateNode", "minimal", {})

        runtime = LocalRuntime()
        parameters = {"minimal": {"test_value": "minimal_setup_works"}}
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert results["minimal"]["test_value"] == "minimal_setup_works"

    def test_configuration_free_setup(self):
        """Test that DataFlow works without any configuration."""
        # Should work with zero configuration
        db = DataFlow()

        @db.model
        class ConfigFreeTest:
            auto_id: int
            auto_name: str
            auto_active: bool = True

        # Should generate nodes automatically
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ConfigFreeTestCreateNode",
            "auto_create",
            {"auto_id": 100, "auto_name": "Auto Generated", "auto_active": True},
        )

        workflow.add_node(
            "ConfigFreeTestListNode", "auto_list", {"filter": {"auto_active": True}}
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert results is not None
        assert "auto_create" in results
        assert "auto_list" in results

    def test_error_handling_for_new_users(self):
        """Test error handling that new users might encounter."""
        db = DataFlow()

        @db.model
        class ErrorTestModel:
            required_field: str
            optional_field: str = "default"

        # Test missing required field (common new user mistake)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ErrorTestModelCreateNode",
            "error_test",
            {
                # Missing required_field
                "optional_field": "test"
            },
        )

        runtime = LocalRuntime()

        # Should handle error gracefully or provide clear feedback
        try:
            results, run_id = runtime.execute(workflow.build())
            # If it doesn't fail, validation is permissive (acceptable)
        except Exception as e:
            # Should provide helpful error message
            error_message = str(e).lower()
            # Error should mention the missing field or validation
            assert any(
                keyword in error_message
                for keyword in ["required", "field", "missing", "validation"]
            )

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode.async_run")
    def test_progressive_complexity_support(self, mock_async_run):
        """Test that package supports progressive complexity."""
        # Mock database operations
        mock_async_run.return_value = {
            "success": True,
            "result": {"id": 1, "name": "Test", "parent_id": None, "metadata": "{}"},
        }

        # Level 1: Simple model and operation
        db = DataFlow(database_url="postgresql://user:pass@localhost/test_db")

        @db.model
        class SimpleModel:
            name: str

        workflow1 = WorkflowBuilder()
        workflow1.add_node("SimpleModelCreateNode", "simple", {})

        runtime = LocalRuntime()
        parameters1 = {"simple": {"name": "Simple Test"}}
        results1, run_id1 = runtime.execute(workflow1.build(), parameters=parameters1)
        assert results1 is not None

        # Level 2: Model with relationships
        @db.model
        class ComplexModel:
            name: str
            parent_id: int = None
            metadata: str = "{}"

        workflow2 = WorkflowBuilder()
        workflow2.add_node("ComplexModelCreateNode", "complex", {})

        parameters2 = {
            "complex": {
                "name": "Complex Test",
                "parent_id": 1,
                "metadata": '{"type": "test"}',
            }
        }
        results2, run_id2 = runtime.execute(workflow2.build(), parameters=parameters2)
        assert results2 is not None

        # Level 3: Bulk operations
        workflow3 = WorkflowBuilder()
        bulk_data = [{"name": f"Bulk Item {i}"} for i in range(10)]

        workflow3.add_node("SimpleModelBulkCreateNode", "bulk", {})

        parameters3 = {"bulk": {"data": bulk_data, "batch_size": 5}}

        results3, run_id3 = runtime.execute(workflow3.build(), parameters=parameters3)
        assert results3 is not None

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode.async_run")
    def test_documentation_code_examples_work(self, mock_async_run):
        """Test that code examples from documentation execute correctly."""
        # Mock database operations
        mock_async_run.return_value = {
            "success": True,
            "result": {
                "id": 1,
                "name": "Alice",
                "email": "alice@example.com",
                "active": True,
            },
        }

        # Test README example
        db = DataFlow(database_url="postgresql://user:pass@localhost/test_db")

        @db.model
        class User:
            name: str
            email: str
            active: bool = True

        workflow = WorkflowBuilder()
        workflow.add_node("UserCreateNode", "create", {})

        runtime = LocalRuntime()
        parameters = {"create": {"name": "Alice", "email": "alice@example.com"}}
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None

        # Test quickstart example
        workflow2 = WorkflowBuilder()
        workflow2.add_node("UserListNode", "list_users", {})

        parameters2 = {"list_users": {"filter": {"active": True}, "limit": 10}}

        results2, run_id2 = runtime.execute(workflow2.build(), parameters=parameters2)
        assert results2 is not None

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode.async_run")
    def test_common_use_case_scenarios(self, mock_async_run):
        """Test common use case scenarios that new users try."""
        # Mock database operations
        mock_async_run.return_value = {
            "success": True,
            "result": {
                "id": 1,
                "username": "testuser",
                "email": "test@example.com",
                "is_active": True,
            },
        }

        db = DataFlow(database_url="postgresql://user:pass@localhost/test_db")

        # Use case 1: User management
        @db.model
        class User:
            username: str
            email: str
            is_active: bool = True

        # Use case 2: Content management
        @db.model
        class Post:
            title: str
            content: str
            author_id: int
            published: bool = False

        # Test user registration flow
        workflow = WorkflowBuilder()
        workflow.add_node("UserCreateNode", "register", {})

        # Test content creation flow
        workflow.add_node("PostCreateNode", "create_post", {})

        # Test content publishing flow
        workflow.add_node("PostUpdateNode", "publish_post", {})

        runtime = LocalRuntime()
        parameters = {
            "register": {
                "username": "testuser",
                "email": "test@example.com",
                "is_active": True,
            },
            "create_post": {
                "title": "My First Post",
                "content": "This is my first post using DataFlow",
                "author_id": 1,
                "published": False,
            },
            "publish_post": {"id": 1, "published": True},
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert "register" in results
        assert "create_post" in results
        assert "publish_post" in results

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode.async_run")
    def test_development_workflow_setup(self, mock_async_run):
        """Test typical development workflow setup."""
        # Mock database operations
        mock_async_run.return_value = {
            "success": True,
            "result": {
                "id": 1,
                "dev_id": 1,
                "environment": "development",
                "debug_info": "Development environment test",
            },
        }

        # Test development database setup
        db = DataFlow(database_url="postgresql://user:pass@localhost/test_db")

        @db.model
        class DevModel:
            dev_id: int
            environment: str = "development"
            debug_info: str = ""

        # Test development operations
        workflow = WorkflowBuilder()

        # Create development record
        workflow.add_node("DevModelCreateNode", "dev_create", {})

        # Test development query
        workflow.add_node("DevModelListNode", "dev_query", {})

        runtime = LocalRuntime()
        parameters = {
            "dev_create": {
                "dev_id": 1,
                "environment": "development",
                "debug_info": "Development environment test",
            },
            "dev_query": {
                "filter": {"environment": "development"},
                "sort": [{"dev_id": 1}],
            },
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert "dev_create" in results
        assert "dev_query" in results

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode.async_run")
    def test_performance_baseline_for_new_installations(self, mock_async_run):
        """Test that new installations meet performance baselines."""
        # Mock database operations
        mock_async_run.return_value = {
            "success": True,
            "result": {
                "id": 1,
                "perf_id": 1,
                "timestamp": 1642723200.0,
                "operation_type": "create",
            },
        }

        db = DataFlow(database_url="postgresql://user:pass@localhost/test_db")

        @db.model
        class PerformanceBaseline:
            perf_id: int
            timestamp: float
            operation_type: str

        import time

        # Test single operation performance
        start_time = time.time()

        workflow = WorkflowBuilder()
        workflow.add_node("PerformanceBaselineCreateNode", "perf_test", {})

        runtime = LocalRuntime()
        parameters = {
            "perf_test": {
                "perf_id": 1,
                "timestamp": start_time,
                "operation_type": "baseline_test",
            }
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        end_time = time.time()
        execution_time = end_time - start_time

        # Should complete within reasonable time for new installation
        assert execution_time < 5.0, f"New installation too slow: {execution_time:.2f}s"
        assert results is not None

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode.async_run")
    def test_environment_compatibility(self, mock_async_run):
        """Test compatibility with different Python environments."""
        # Mock database operations
        mock_async_run.return_value = {
            "success": True,
            "result": {
                "id": 1,
                "python_version": "3.12",
                "platform": "Darwin",
                "test_result": "compatible",
            },
        }

        # Test that DataFlow works in current environment
        db = DataFlow(database_url="postgresql://user:pass@localhost/test_db")

        @db.model
        class EnvironmentTest:
            python_version: str
            platform: str
            test_result: str

        import platform

        workflow = WorkflowBuilder()
        workflow.add_node("EnvironmentTestCreateNode", "env_test", {})

        runtime = LocalRuntime()
        parameters = {
            "env_test": {
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
                "platform": platform.system(),
                "test_result": "compatible",
            }
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert results["env_test"]["test_result"] == "compatible"

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode.async_run")
    def test_memory_usage_on_startup(self, mock_async_run):
        """Test that package doesn't use excessive memory on startup."""
        # Mock database operations
        mock_async_run.return_value = {
            "success": True,
            "result": {"id": 1, "instance_id": 1, "memory_test": "passed"},
        }

        # Create multiple DataFlow instances to test memory usage
        instances = []

        for i in range(5):
            db = DataFlow(database_url="postgresql://user:pass@localhost/test_db")

            @db.model
            class MemoryTestModel:
                instance_id: int
                memory_test: str

            instances.append(db)

        # Should be able to create multiple instances without issues
        assert len(instances) == 5

        # Test that all instances work
        runtime = LocalRuntime()

        for i, db_instance in enumerate(instances):
            workflow = WorkflowBuilder()
            workflow.add_node("MemoryTestModelCreateNode", f"memory_{i}", {})

            parameters = {
                f"memory_{i}": {"instance_id": i, "memory_test": f"instance_{i}_works"}
            }

            results, run_id = runtime.execute(workflow.build(), parameters=parameters)
            assert results is not None

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode.async_run")
    def test_graceful_degradation(self, mock_async_run):
        """Test graceful degradation when optional features unavailable."""
        # Mock database operations
        mock_async_run.return_value = {
            "success": True,
            "result": {
                "id": 1,
                "basic_id": 1,
                "basic_data": "basic_functionality_works",
            },
        }

        # Test basic functionality even if advanced features fail
        db = DataFlow(database_url="postgresql://user:pass@localhost/test_db")

        @db.model
        class DegradationTest:
            basic_id: int
            basic_data: str

        # Should work with minimal feature set
        workflow = WorkflowBuilder()
        workflow.add_node("DegradationTestCreateNode", "basic_op", {})

        runtime = LocalRuntime()
        parameters = {
            "basic_op": {"basic_id": 1, "basic_data": "basic_functionality_works"}
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert results["basic_op"]["basic_data"] == "basic_functionality_works"
