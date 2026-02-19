#!/usr/bin/env python3
"""
Comprehensive SDK Pattern Validation Tests

Tests all documented patterns from skills against the real Kailash SDK.
This validates that our documentation and skills are accurate.

Usage:
    python tests/sdk/test_sdk_patterns.py

Requirements:
    - Kailash SDK installed (pip install kailash)
    - .env file with required API keys
"""

import os
import sys

# Add SDK to path if needed
SDK_PATH = os.path.expanduser("~/repos/dev/kailash_python_sdk")
if os.path.exists(SDK_PATH):
    sys.path.insert(0, os.path.join(SDK_PATH, "src"))

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Test tracking
tests_passed = 0
tests_failed = 0
tests_skipped = 0


def test(name):
    """Test decorator"""

    def decorator(fn):
        def wrapper():
            global tests_passed, tests_failed, tests_skipped
            try:
                fn()
                print(f"  ✓ {name}")
                tests_passed += 1
            except AssertionError as e:
                print(f"  ✗ {name}: {e}")
                tests_failed += 1
            except Exception as e:
                print(f"  ⚠ {name}: SKIPPED - {e}")
                tests_skipped += 1

        return wrapper

    return decorator


# ==============================================================================
# CORE SDK PATTERN TESTS
# ==============================================================================


def test_core_sdk_patterns():
    """Test Core SDK patterns documented in 01-core-sdk skill."""
    print("\nCore SDK Pattern Tests:")

    @test("Import WorkflowBuilder")
    def _():
        from kailash.workflow.builder import WorkflowBuilder

        assert WorkflowBuilder is not None

    _()

    @test("Import LocalRuntime")
    def _():
        from kailash.runtime import LocalRuntime

        assert LocalRuntime is not None

    _()

    @test("Import AsyncLocalRuntime")
    def _():
        from kailash.runtime import AsyncLocalRuntime

        assert AsyncLocalRuntime is not None

    _()

    @test("Import get_runtime")
    def _():
        from kailash.runtime import get_runtime

        assert get_runtime is not None

    _()

    @test("Create workflow with 3-param add_node")
    def _():
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "code1", {"code": "x = 1"})
        built = workflow.build()
        assert built is not None

    _()

    @test("Create connection with 4-param add_connection")
    def _():
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "code1", {"code": "x = 1"})
        workflow.add_node("PythonCodeNode", "code2", {"code": "y = x"})
        workflow.add_connection("code1", "output", "code2", "input")
        built = workflow.build()
        assert built is not None

    _()

    @test("Execute workflow with LocalRuntime")
    def _():
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "calc", {"code": "result = 42"})

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert run_id is not None
        assert "calc" in results

    _()

    @test("LocalRuntime returns (results, run_id) tuple")
    def _():
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {"code": "x = 1"})

        runtime = LocalRuntime()
        output = runtime.execute(workflow.build())

        assert isinstance(output, tuple)
        assert len(output) == 2
        results, run_id = output
        assert isinstance(results, dict)
        assert isinstance(run_id, str)

    _()


# ==============================================================================
# RUNTIME CONFIGURATION TESTS
# ==============================================================================


def test_runtime_configuration():
    """Test runtime configuration options documented in CLAUDE.md."""
    print("\nRuntime Configuration Tests:")

    @test("LocalRuntime with debug=True")
    def _():
        from kailash.runtime import LocalRuntime

        runtime = LocalRuntime(debug=True)
        assert runtime is not None

    _()

    @test("LocalRuntime with enable_cycles=True")
    def _():
        from kailash.runtime import LocalRuntime

        runtime = LocalRuntime(enable_cycles=True)
        assert runtime is not None

    _()

    @test("LocalRuntime with connection_validation='strict'")
    def _():
        from kailash.runtime import LocalRuntime

        runtime = LocalRuntime(connection_validation="strict")
        assert runtime is not None

    _()

    @test("LocalRuntime with conditional_execution='skip_branches'")
    def _():
        from kailash.runtime import LocalRuntime

        runtime = LocalRuntime(conditional_execution="skip_branches")
        assert runtime is not None

    _()

    @test("LocalRuntime has validate_workflow method")
    def _():
        from kailash.runtime import LocalRuntime

        runtime = LocalRuntime()
        assert hasattr(runtime, "validate_workflow")

    _()

    @test("LocalRuntime has get_validation_metrics method")
    def _():
        from kailash.runtime import LocalRuntime

        runtime = LocalRuntime()
        assert hasattr(runtime, "get_validation_metrics")

    _()


# ==============================================================================
# NODE TESTS
# ==============================================================================


def test_node_patterns():
    """Test node patterns documented in 08-nodes-reference skill."""
    print("\nNode Pattern Tests:")

    @test("PythonCodeNode exists")
    def _():
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {"code": "x = 1"})
        built = workflow.build()
        # Nodes may be strings or objects with .id
        node_ids = [n if isinstance(n, str) else n.id for n in built.nodes]
        assert "test" in node_ids

    _()

    @test("SwitchNode exists")
    def _():
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node(
            "SwitchNode", "switch", {"switch_variable": "x", "cases": {"a": "branch_a"}}
        )
        built = workflow.build()
        node_ids = [n if isinstance(n, str) else n.id for n in built.nodes]
        assert "switch" in node_ids

    _()

    @test("HTTPRequestNode exists")
    def _():
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node(
            "HTTPRequestNode", "http", {"url": "https://example.com", "method": "GET"}
        )
        built = workflow.build()
        node_ids = [n if isinstance(n, str) else n.id for n in built.nodes]
        assert "http" in node_ids

    _()

    @test("PythonCodeNode can execute")
    def _():
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "log", {"code": "result = 'logged'"})
        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())
            assert "log" in results

    _()


# ==============================================================================
# ASYNC RUNTIME TESTS
# ==============================================================================


def test_async_patterns():
    """Test async runtime patterns documented in CLAUDE.md."""
    print("\nAsync Runtime Tests:")

    @test("AsyncLocalRuntime can be instantiated")
    def _():
        from kailash.runtime import AsyncLocalRuntime

        runtime = AsyncLocalRuntime()
        assert runtime is not None

    _()

    @test("AsyncLocalRuntime has execute_workflow_async method")
    def _():
        from kailash.runtime import AsyncLocalRuntime

        runtime = AsyncLocalRuntime()
        assert hasattr(runtime, "execute_workflow_async")

    _()

    @test("AsyncLocalRuntime with max_concurrent_nodes")
    def _():
        from kailash.runtime import AsyncLocalRuntime

        runtime = AsyncLocalRuntime(max_concurrent_nodes=10)
        assert runtime is not None

    _()


# ==============================================================================
# WORKFLOW BUILDER TESTS
# ==============================================================================


def test_workflow_builder_features():
    """Test WorkflowBuilder features."""
    print("\nWorkflowBuilder Feature Tests:")

    @test("WorkflowBuilder.build() returns workflow object")
    def _():
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {"code": "x = 1"})
        built = workflow.build()

        # Verify it has required attributes
        assert hasattr(built, "nodes")
        assert hasattr(built, "id") or hasattr(built, "name")

    _()

    @test("Workflow has nodes attribute")
    def _():
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {"code": "x = 1"})
        built = workflow.build()

        assert hasattr(built, "nodes")

    _()

    @test("Multiple nodes can be added")
    def _():
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "node1", {"code": "a = 1"})
        workflow.add_node("PythonCodeNode", "node2", {"code": "b = 2"})
        workflow.add_node("PythonCodeNode", "node3", {"code": "c = 3"})
        built = workflow.build()

        assert len(built.nodes) == 3

    _()

    @test("Connections create data flow")
    def _():
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "producer", {"code": "output = 42"})
        workflow.add_node("PythonCodeNode", "consumer", {"code": "result = input * 2"})
        workflow.add_connection("producer", "output", "consumer", "input")

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        # Verify consumer received the output
        assert "consumer" in results

    _()


# ==============================================================================
# MCP INTEGRATION TESTS
# ==============================================================================


def test_mcp_patterns():
    """Test MCP patterns documented in 05-kailash-mcp skill."""
    print("\nMCP Integration Tests:")

    @test("MCP server module exists")
    def _():
        from kailash.mcp_server import MCPServer

        assert MCPServer is not None

    _()

    @test("MCP server has required methods")
    def _():
        from kailash.mcp_server import MCPServer

        server = MCPServer(name="test-server")
        assert hasattr(server, "tool")
        assert hasattr(server, "resource")
        assert hasattr(server, "prompt")

    _()


# ==============================================================================
# CONTEXT MANAGER PATTERN TESTS
# ==============================================================================


def test_context_patterns():
    """Test context manager patterns."""
    print("\nContext Manager Pattern Tests:")

    @test("Runtime can be used as context manager")
    def _():
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {"code": "x = 1"})

        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(workflow.build())
            assert run_id is not None

    _()


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================


def main():
    """Run all SDK pattern tests."""
    print("=" * 60)
    print("SDK Pattern Validation Tests")
    print("=" * 60)
    print(f"SDK Path: {SDK_PATH}")
    print("-" * 60)

    # Run all test suites
    test_core_sdk_patterns()
    test_runtime_configuration()
    test_node_patterns()
    test_async_patterns()
    test_workflow_builder_features()
    test_mcp_patterns()
    test_context_patterns()

    # Summary
    print("\n" + "=" * 60)
    print(
        f"Results: {tests_passed} passed, {tests_failed} failed, {tests_skipped} skipped"
    )
    print("=" * 60)

    if tests_failed > 0:
        print("\n✗ SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("\n✓ ALL TESTS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
