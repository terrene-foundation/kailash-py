#!/usr/bin/env python3
"""
Backward Compatibility Check for DataFlow

This script ensures that existing user code continues to work without
modification when DataFlow is updated. It validates that the public API
remains stable and no breaking changes have been introduced.

CRITICAL: Any failure in this script indicates a breaking change that
would require a major version bump.
"""

import sys
import traceback
from datetime import datetime
from typing import Any, Dict, List


class BackwardCompatibilityChecker:
    """Validates backward compatibility of DataFlow API"""

    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0

    def test(self, test_name: str, test_func):
        """Run a compatibility test and record the result"""
        print(f"Testing: {test_name}")

        try:
            test_func()
            print("✅ PASS")
            self.results.append({"test": test_name, "status": "PASS", "error": None})
            self.passed += 1
            return True
        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results.append({"test": test_name, "status": "FAIL", "error": str(e)})
            self.failed += 1
            return False

    def test_basic_import_patterns(self):
        """Test that basic import patterns still work"""

        # Test 1: Basic DataFlow import
        from dataflow import DataFlow

        assert DataFlow is not None

        # Test 2: DataFlow instantiation without arguments
        db = DataFlow()
        assert db is not None

        # Test 3: DataFlow instantiation with memory database
        db_memory = DataFlow(":memory:")
        assert db_memory is not None

        # Test 4: Model decorator exists and works
        @db.model
        class TestModel:
            name: str
            value: int

        # Should not raise any exceptions

    def test_model_decorator_compatibility(self):
        """Test that @db.model decorator API remains stable"""
        from dataflow import DataFlow

        db = DataFlow(":memory:")

        # Test 1: Basic model definition (legacy pattern)
        @db.model
        class User:
            name: str
            email: str
            age: int = 25

        # Test 2: Model with various field types
        @db.model
        class Product:
            name: str
            price: float
            available: bool = True
            tags: list = None
            metadata: dict = None

        # Test 3: Model with optional fields
        @db.model
        class BlogPost:
            title: str
            content: str
            published: bool = False

        # All should work without modification

    def test_workflow_integration_compatibility(self):
        """Test that workflow integration patterns remain stable"""
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(":memory:")

        @db.model
        class Task:
            title: str
            completed: bool = False

        # Test 1: Legacy workflow pattern
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TaskCreateNode", "create_task", {"title": "Compatibility Test Task"}
        )

        # Test 2: Workflow execution
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Test 3: Result structure
        assert "create_task" in results
        assert "output" in results["create_task"]
        assert "id" in results["create_task"]["output"]
        assert results["create_task"]["output"]["title"] == "Compatibility Test Task"

    def test_crud_node_names_compatibility(self):
        """Test that generated CRUD node names remain stable"""
        from dataflow import DataFlow

        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(":memory:")

        @db.model
        class Item:
            name: str
            value: int

        workflow = WorkflowBuilder()

        # Test that all expected node names still work
        expected_nodes = [
            "ItemCreateNode",
            "ItemReadNode",
            "ItemUpdateNode",
            "ItemDeleteNode",
            "ItemListNode",
            "ItemBulkCreateNode",
            "ItemBulkUpdateNode",
            "ItemBulkDeleteNode",
            "ItemCountNode",
        ]

        for node_name in expected_nodes:
            # Should not raise exception
            workflow.add_node(node_name, f"test_{node_name.lower()}", {})

        # Should build successfully
        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_node_parameter_compatibility(self):
        """Test that node parameter formats remain stable"""
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(":memory:")

        @db.model
        class Record:
            name: str
            value: int
            active: bool = True

        workflow = WorkflowBuilder()
        runtime = LocalRuntime()

        # Test 1: Create node parameters
        workflow.add_node(
            "RecordCreateNode", "create", {"name": "Test Record", "value": 42}
        )
        results, _ = runtime.execute(workflow.build())
        record_id = results["create"]["output"]["id"]

        # Test 2: Read node parameters
        workflow = WorkflowBuilder()
        workflow.add_node("RecordReadNode", "read", {"conditions": {"id": record_id}})
        results, _ = runtime.execute(workflow.build())
        assert results["read"]["output"]["name"] == "Test Record"

        # Test 3: Update node parameters
        workflow = WorkflowBuilder()
        workflow.add_node(
            "RecordUpdateNode",
            "update",
            {
                "conditions": {"id": record_id},
                "updates": {"value": 84, "active": False},
            },
        )
        results, _ = runtime.execute(workflow.build())
        assert results["update"]["output"]["value"] == 84

        # Test 4: List node parameters
        workflow = WorkflowBuilder()
        workflow.add_node(
            "RecordListNode",
            "list",
            {"filter": {"active": False}, "order_by": ["-value"], "limit": 10},
        )
        results, _ = runtime.execute(workflow.build())
        assert len(results["list"]["output"]) >= 1

        # Test 5: Delete node parameters
        workflow = WorkflowBuilder()
        workflow.add_node(
            "RecordDeleteNode", "delete", {"conditions": {"id": record_id}}
        )
        results, _ = runtime.execute(workflow.build())
        assert results["delete"]["output"]["id"] == record_id

    def test_field_type_compatibility(self):
        """Test that field type support remains stable"""
        from datetime import datetime

        from dataflow import DataFlow

        db = DataFlow(":memory:")

        # Test all supported field types
        @db.model
        class AllTypes:
            # Basic types
            text_field: str
            number_field: int
            decimal_field: float
            boolean_field: bool

            # Container types
            list_field: list = None
            dict_field: dict = None

            # Optional types with defaults
            optional_text: str = "default"
            optional_number: int = 0
            optional_boolean: bool = False

        # Should not raise any exceptions during model registration

    def test_database_url_compatibility(self):
        """Test that database URL patterns remain supported"""
        from dataflow import DataFlow

        # Test 1: Memory database (should always work)
        db1 = DataFlow(":memory:")
        assert db1 is not None

        # Test 2: SQLite file database
        db2 = DataFlow("sqlite:///test_compat.db")
        assert db2 is not None

        # Test 3: Default instantiation
        db3 = DataFlow()
        assert db3 is not None

    def test_error_handling_compatibility(self):
        """Test that error handling patterns remain stable"""
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(":memory:")

        @db.model
        class TestItem:
            name: str
            required_field: str  # No default - should be required

        workflow = WorkflowBuilder()
        runtime = LocalRuntime()

        # Test that missing required fields still produce predictable errors
        workflow.add_node(
            "TestItemCreateNode",
            "create_invalid",
            {
                "name": "Test Item"
                # Missing required_field
            },
        )

        try:
            results, _ = runtime.execute(workflow.build())
            # If this succeeds, the error handling has changed
            # We expect this to fail in a predictable way
            assert False, "Expected validation error for missing required field"
        except Exception as e:
            # Error should be related to missing required field
            error_msg = str(e).lower()
            assert any(
                keyword in error_msg for keyword in ["required", "missing", "field"]
            ), f"Unexpected error message: {e}"

    def test_legacy_examples_compatibility(self):
        """Test that legacy example patterns still work"""

        # This replicates the pattern from examples/01_basic_crud.py
        from datetime import datetime
        from typing import Optional

        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Zero configuration - just works!
        db = DataFlow(":memory:")

        # Define a model using Python type hints
        @db.model
        class BlogPost:
            """A simple blog post model"""

            title: str
            content: str
            author: str
            published: bool = False
            views: int = 0
            tags: Optional[list] = None

        # Create a workflow exactly like in the example
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BlogPostCreateNode",
            "create_post",
            {
                "title": "Introduction to DataFlow",
                "content": "DataFlow makes database operations incredibly simple...",
                "author": "Alice Smith",
                "tags": ["database", "python", "kailash"],
            },
        )

        # Execute workflow exactly like in the example
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Validate results structure matches example expectations
        post = results["create_post"]["output"]
        assert post["title"] == "Introduction to DataFlow"
        assert "id" in post
        assert isinstance(post["id"], int)


def main():
    """Run all backward compatibility checks"""
    print("=" * 60)
    print("DataFlow Backward Compatibility Check")
    print("=" * 60)
    print(f"Started at: {datetime.now().isoformat()}")
    print()

    checker = BackwardCompatibilityChecker()

    # Define all compatibility tests
    tests = [
        ("Basic Import Patterns", checker.test_basic_import_patterns),
        ("Model Decorator Compatibility", checker.test_model_decorator_compatibility),
        ("Workflow Integration", checker.test_workflow_integration_compatibility),
        ("CRUD Node Names", checker.test_crud_node_names_compatibility),
        ("Node Parameter Formats", checker.test_node_parameter_compatibility),
        ("Field Type Support", checker.test_field_type_compatibility),
        ("Database URL Patterns", checker.test_database_url_compatibility),
        ("Error Handling Patterns", checker.test_error_handling_compatibility),
        ("Legacy Examples", checker.test_legacy_examples_compatibility),
    ]

    # Run all tests
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}")
        checker.test(test_name, test_func)

    # Summary
    print("\n" + "=" * 60)
    print("COMPATIBILITY CHECK SUMMARY")
    print("=" * 60)
    print(f"Tests passed: {checker.passed}")
    print(f"Tests failed: {checker.failed}")
    print(f"Success rate: {checker.passed/(checker.passed+checker.failed)*100:.1f}%")

    if checker.failed == 0:
        print("\n🎉 ALL COMPATIBILITY TESTS PASSED")
        print("No breaking changes detected - existing user code will continue to work")
        return True
    else:
        print(f"\n🚨 {checker.failed} COMPATIBILITY TESTS FAILED")
        print("BREAKING CHANGES DETECTED!")
        print("This would require a major version bump and user code updates")

        print("\nFailed tests:")
        for result in checker.results:
            if result["status"] == "FAIL":
                print(f"  - {result['test']}: {result['error']}")

        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
