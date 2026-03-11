#!/usr/bin/env python3
"""
Core Functionality Validation Script

This script validates that DataFlow's essential functionality remains intact.
It serves as the first line of defense against regressions that could break
basic operations.

CRITICAL: This script must ALWAYS pass. Any failure indicates a regression
that requires immediate attention.
"""

import sys
import time
import traceback
from datetime import datetime
from typing import Optional


def test_dataflow_instantiation():
    """Test that DataFlow can be instantiated without configuration"""
    print("Testing DataFlow instantiation...")

    try:
        from dataflow import DataFlow

        # Test default instantiation
        db = DataFlow()
        assert db is not None, "DataFlow() returned None"

        # Test memory database instantiation
        db_memory = DataFlow(":memory:")
        assert db_memory is not None, "DataFlow(':memory:') returned None"

        print("✅ DataFlow instantiation: PASS")
        return True

    except Exception as e:
        print(f"❌ DataFlow instantiation: FAIL - {e}")
        traceback.print_exc()
        return False


def test_model_decorator():
    """Test that @db.model decorator works correctly"""
    print("Testing @db.model decorator...")

    try:
        from dataflow import DataFlow

        db = DataFlow(":memory:")

        # Define a test model
        @db.model
        class TestUser:
            name: str
            email: str
            age: int = 25
            active: bool = True

        # Verify model was registered
        assert hasattr(db, "_models"), "DataFlow should have _models attribute"
        model_names = [model.__name__ for model in getattr(db, "_models", [])]
        assert "TestUser" in model_names, f"TestUser not found in models: {model_names}"

        print("✅ @db.model decorator: PASS")
        return True

    except Exception as e:
        print(f"❌ @db.model decorator: FAIL - {e}")
        traceback.print_exc()
        return False


def test_node_generation():
    """Test that CRUD nodes are generated automatically"""
    print("Testing automatic node generation...")

    try:
        from dataflow import DataFlow

        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(":memory:")

        @db.model
        class Product:
            name: str
            price: float
            in_stock: bool = True

        # Test that we can reference generated nodes
        workflow = WorkflowBuilder()

        # These should not raise exceptions if nodes exist
        workflow.add_node(
            "ProductCreateNode",
            "create_product",
            {"name": "Test Product", "price": 19.99},
        )

        workflow.add_node(
            "ProductListNode", "list_products", {"filter": {"in_stock": True}}
        )

        workflow.add_node("ProductReadNode", "read_product", {"conditions": {"id": 1}})

        # Build workflow - this validates node existence
        built_workflow = workflow.build()
        assert built_workflow is not None, "Workflow build failed"

        print("✅ Automatic node generation: PASS")
        return True

    except Exception as e:
        print(f"❌ Automatic node generation: FAIL - {e}")
        traceback.print_exc()
        return False


def test_basic_workflow_execution():
    """Test that basic workflows can execute successfully"""
    print("Testing basic workflow execution...")

    try:
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(":memory:")

        @db.model
        class BlogPost:
            title: str
            content: str
            published: bool = False

        # Create and execute a simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BlogPostCreateNode",
            "create_post",
            {"title": "Test Post", "content": "This is a test post for validation"},
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Validate results
        assert results is not None, "Results should not be None"
        assert "create_post" in results, "create_post not in results"
        assert "output" in results["create_post"], "output not in create_post results"

        post = results["create_post"]["output"]
        assert post["title"] == "Test Post", f"Title mismatch: {post['title']}"
        assert "id" in post, "Post should have an ID"

        print("✅ Basic workflow execution: PASS")
        return True

    except Exception as e:
        print(f"❌ Basic workflow execution: FAIL - {e}")
        traceback.print_exc()
        return False


def test_crud_operations():
    """Test that all CRUD operations work correctly"""
    print("Testing CRUD operations...")

    try:
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow(":memory:")

        @db.model
        class Task:
            title: str
            completed: bool = False
            priority: int = 1

        runtime = LocalRuntime()

        # CREATE
        create_workflow = WorkflowBuilder()
        create_workflow.add_node(
            "TaskCreateNode", "create_task", {"title": "Validation Task", "priority": 2}
        )

        create_results, _ = runtime.execute(create_workflow.build())
        task_id = create_results["create_task"]["output"]["id"]
        assert isinstance(task_id, int), f"Task ID should be int, got {type(task_id)}"

        # READ
        read_workflow = WorkflowBuilder()
        read_workflow.add_node(
            "TaskReadNode", "read_task", {"conditions": {"id": task_id}}
        )

        read_results, _ = runtime.execute(read_workflow.build())
        task = read_results["read_task"]["output"]
        assert task["title"] == "Validation Task", f"Title mismatch: {task['title']}"
        assert task["priority"] == 2, f"Priority mismatch: {task['priority']}"

        # UPDATE
        update_workflow = WorkflowBuilder()
        update_workflow.add_node(
            "TaskUpdateNode",
            "update_task",
            {
                "conditions": {"id": task_id},
                "updates": {"completed": True, "priority": 3},
            },
        )

        update_results, _ = runtime.execute(update_workflow.build())
        updated_task = update_results["update_task"]["output"]
        assert updated_task["completed"] is True, "Task should be completed"
        assert (
            updated_task["priority"] == 3
        ), f"Priority should be 3, got {updated_task['priority']}"

        # LIST
        list_workflow = WorkflowBuilder()
        list_workflow.add_node(
            "TaskListNode", "list_tasks", {"filter": {"completed": True}}
        )

        list_results, _ = runtime.execute(list_workflow.build())
        tasks = list_results["list_tasks"]["output"]
        assert len(tasks) >= 1, "Should find at least one completed task"
        assert any(t["id"] == task_id for t in tasks), "Our task should be in the list"

        # DELETE
        delete_workflow = WorkflowBuilder()
        delete_workflow.add_node(
            "TaskDeleteNode", "delete_task", {"conditions": {"id": task_id}}
        )

        delete_results, _ = runtime.execute(delete_workflow.build())
        deleted_task = delete_results["delete_task"]["output"]
        assert deleted_task["id"] == task_id, "Deleted task ID should match"

        print("✅ CRUD operations: PASS")
        return True

    except Exception as e:
        print(f"❌ CRUD operations: FAIL - {e}")
        traceback.print_exc()
        return False


def test_performance_baseline():
    """Test that core operations meet performance expectations"""
    print("Testing performance baseline...")

    try:
        from dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Test instantiation performance
        start_time = time.time()
        db = DataFlow(":memory:")
        instantiation_time = (time.time() - start_time) * 1000  # ms

        assert (
            instantiation_time < 100
        ), f"Instantiation took {instantiation_time:.2f}ms (should be <100ms)"

        # Test model registration performance
        start_time = time.time()

        @db.model
        class PerformanceTest:
            name: str
            value: int

        registration_time = (time.time() - start_time) * 1000  # ms

        assert (
            registration_time < 50
        ), f"Model registration took {registration_time:.2f}ms (should be <50ms)"

        # Test workflow execution performance
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PerformanceTestCreateNode",
            "create_item",
            {"name": "Performance Test Item", "value": 42},
        )

        runtime = LocalRuntime()
        start_time = time.time()
        results, _ = runtime.execute(workflow.build())
        execution_time = (time.time() - start_time) * 1000  # ms

        assert (
            execution_time < 200
        ), f"Workflow execution took {execution_time:.2f}ms (should be <200ms)"

        print("✅ Performance baseline: PASS")
        print(f"   Instantiation: {instantiation_time:.2f}ms")
        print(f"   Registration: {registration_time:.2f}ms")
        print(f"   Execution: {execution_time:.2f}ms")
        return True

    except Exception as e:
        print(f"❌ Performance baseline: FAIL - {e}")
        traceback.print_exc()
        return False


def main():
    """Run all core functionality validation tests"""
    print("=" * 60)
    print("DataFlow Core Functionality Validation")
    print("=" * 60)
    print(f"Started at: {datetime.now().isoformat()}")
    print()

    tests = [
        test_dataflow_instantiation,
        test_model_decorator,
        test_node_generation,
        test_basic_workflow_execution,
        test_crud_operations,
        test_performance_baseline,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test.__name__}: CRASH - {e}")
            failed += 1
        print()

    print("=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Tests passed: {passed}")
    print(f"Tests failed: {failed}")
    print(f"Success rate: {passed/(passed+failed)*100:.1f}%")

    if failed == 0:
        print("\n🎉 ALL CORE FUNCTIONALITY TESTS PASSED")
        print("DataFlow basic operations are working correctly.")
        return True
    else:
        print(f"\n🚨 {failed} CORE FUNCTIONALITY TESTS FAILED")
        print("CRITICAL: DataFlow core functionality is broken!")
        print("Immediate action required - stop all development.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
