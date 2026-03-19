#!/usr/bin/env python3
"""
Simple DataFlow Validation

This script performs basic validation tests to identify what's working
and what's broken in the current DataFlow implementation.

It's designed to work even when core functionality is partially broken.
"""

import sys
import traceback
from datetime import datetime


def test_basic_import():
    """Test that DataFlow can be imported"""
    try:
        from dataflow import DataFlow

        print("✅ DataFlow import: SUCCESS")
        return True
    except Exception as e:
        print(f"❌ DataFlow import: FAILED - {e}")
        return False


def test_instantiation():
    """Test basic DataFlow instantiation"""
    try:
        from dataflow import DataFlow

        # Test default instantiation
        db = DataFlow()
        print("✅ DataFlow() instantiation: SUCCESS")

        # Test memory instantiation
        try:
            db_memory = DataFlow(":memory:")
            print("✅ DataFlow(':memory:') instantiation: SUCCESS")
        except Exception as e:
            print(f"⚠️  DataFlow(':memory:') instantiation: FAILED - {e}")

        return True
    except Exception as e:
        print(f"❌ DataFlow instantiation: FAILED - {e}")
        traceback.print_exc()
        return False


def test_model_decorator():
    """Test model decorator registration"""
    try:
        from dataflow import DataFlow

        db = DataFlow()

        @db.model
        class TestModel:
            name: str
            value: int

        print("✅ @db.model decorator: SUCCESS")

        # Try to inspect registered models
        try:
            models = getattr(db, "_models", None)
            if models:
                print(f"   Models registered: {len(models)}")
                print(f"   Model types: {[type(m) for m in models]}")
            else:
                print("   No _models attribute found")
        except Exception as e:
            print(f"   Model inspection failed: {e}")

        return True
    except Exception as e:
        print(f"❌ @db.model decorator: FAILED - {e}")
        traceback.print_exc()
        return False


def test_workflow_builder():
    """Test basic workflow building"""
    try:
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        print("✅ WorkflowBuilder import/instantiation: SUCCESS")

        # Try adding a simple node
        try:
            workflow.add_node("PassthroughNode", "test_node", {"value": "test"})
            print("✅ Basic node addition: SUCCESS")
        except Exception as e:
            print(f"⚠️  Basic node addition: FAILED - {e}")

        # Try building workflow
        try:
            built = workflow.build()
            print("✅ Workflow build: SUCCESS")
        except Exception as e:
            print(f"⚠️  Workflow build: FAILED - {e}")

        return True
    except Exception as e:
        print(f"❌ WorkflowBuilder: FAILED - {e}")
        traceback.print_exc()
        return False


def test_runtime():
    """Test basic runtime functionality"""
    try:
        from kailash.runtime.local import LocalRuntime

        runtime = LocalRuntime()
        print("✅ LocalRuntime instantiation: SUCCESS")
        return True
    except Exception as e:
        print(f"❌ LocalRuntime: FAILED - {e}")
        traceback.print_exc()
        return False


def test_generated_nodes():
    """Test if DataFlow generates nodes correctly"""
    try:
        from dataflow import DataFlow

        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow()

        @db.model
        class SimpleModel:
            name: str

        workflow = WorkflowBuilder()

        # Try to reference generated nodes
        node_types = [
            "SimpleModelCreateNode",
            "SimpleModelReadNode",
            "SimpleModelListNode",
        ]

        for node_type in node_types:
            try:
                workflow.add_node(
                    node_type, f"test_{node_type.lower()}", {"name": "test"}
                )
                print(f"✅ {node_type}: SUCCESS")
            except Exception as e:
                print(f"⚠️  {node_type}: FAILED - {e}")

        return True
    except Exception as e:
        print(f"❌ Generated nodes test: FAILED - {e}")
        traceback.print_exc()
        return False


def test_database_adapters():
    """Test which database adapters are available"""
    try:
        from dataflow.adapters.factory import AdapterFactory

        factory = AdapterFactory()
        print("✅ AdapterFactory import: SUCCESS")

        # Test different database types
        db_types = ["sqlite", "postgresql", "mysql"]

        for db_type in db_types:
            try:
                adapter = factory.get_adapter(f"{db_type}://test")
                print(f"✅ {db_type} adapter: AVAILABLE")
            except Exception as e:
                print(f"⚠️  {db_type} adapter: FAILED - {e}")

        return True
    except Exception as e:
        print(f"❌ Database adapters test: FAILED - {e}")
        traceback.print_exc()
        return False


def main():
    """Run all simple validation tests"""
    print("=" * 60)
    print("DataFlow Simple Validation")
    print("=" * 60)
    print(f"Started at: {datetime.now().isoformat()}")
    print()

    tests = [
        ("Basic Import", test_basic_import),
        ("Instantiation", test_instantiation),
        ("Model Decorator", test_model_decorator),
        ("WorkflowBuilder", test_workflow_builder),
        ("Runtime", test_runtime),
        ("Generated Nodes", test_generated_nodes),
        ("Database Adapters", test_database_adapters),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🔍 Testing: {test_name}")
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name}: CRASHED - {e}")
        print()

    print("=" * 60)
    print("SIMPLE VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Tests passed: {passed}/{total}")
    print(f"Success rate: {passed / total * 100:.1f}%")

    if passed == total:
        print("\n🎉 ALL BASIC COMPONENTS WORKING")
        print("DataFlow basic infrastructure is functional.")
    elif passed >= total * 0.7:
        print("\n⚠️  MOST COMPONENTS WORKING")
        print("Some issues detected but core infrastructure intact.")
    else:
        print("\n🚨 SIGNIFICANT ISSUES DETECTED")
        print("Multiple components are broken - investigation needed.")

    return passed >= total * 0.7


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
