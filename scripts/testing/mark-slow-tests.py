#!/usr/bin/env python3
"""
Mark slow tests with appropriate pytest markers.
"""

import ast
from pathlib import Path


class SlowTestMarker(ast.NodeTransformer):
    """AST transformer to add @pytest.mark.slow to slow test methods."""

    def __init__(self, slow_methods):
        self.slow_methods = slow_methods
        self.imports_pytest = False

    def visit_Import(self, node):
        """Check if pytest is imported."""
        for alias in node.names:
            if alias.name == "pytest":
                self.imports_pytest = True
        return node

    def visit_ImportFrom(self, node):
        """Check if pytest is imported."""
        if node.module == "pytest":
            self.imports_pytest = True
        return node

    def visit_FunctionDef(self, node):
        """Add slow marker to identified slow test functions."""
        if node.name in self.slow_methods:
            # Check if already has slow marker
            has_slow_marker = any(
                isinstance(dec, ast.Attribute)
                and isinstance(dec.value, ast.Attribute)
                and dec.value.attr == "mark"
                and dec.attr == "slow"
                for dec in node.decorator_list
            )

            if not has_slow_marker:
                # Add @pytest.mark.slow decorator
                slow_marker = ast.Attribute(
                    value=ast.Attribute(
                        value=ast.Name(id="pytest", ctx=ast.Load()),
                        attr="mark",
                        ctx=ast.Load(),
                    ),
                    attr="slow",
                    ctx=ast.Load(),
                )
                node.decorator_list.insert(0, slow_marker)

        return node


def find_slow_tests():
    """Find tests that should be marked as slow."""
    slow_tests = {
        "tests/test_nodes/test_a2a.py": ["test_memory_relevance_calculation"],
        "tests/test_tracking/test_metrics_collector.py": [
            "test_sync_function_decorator",
            "test_async_function_decorator",
            "test_async_collection",
        ],
        "tests/integration/test_workflow_execution.py": [
            "test_workflow_state_persistence"
        ],
        "tests/test_runtime/test_local.py": ["test_parallel_execution"],
    }

    # Tests with file I/O
    io_tests = {
        "tests/test_nodes/test_data.py": [
            "test_csv_reader_execution",
            "test_csv_writer_execution",
            "test_json_reader_execution",
            "test_json_writer_execution",
        ],
        "tests/test_visualization/test_visualization_consolidated.py": [
            "test_workflow_visualization",
            "test_performance_visualization",
            "test_dashboard_visualization",
        ],
    }

    # Tests with external dependencies
    integration_tests = {
        "tests/test_nodes/test_mcp.py": ["test_mcp_client_node_execution"],
        "tests/test_nodes/test_embedding_generator.py": ["test_embedding_generation"],
        "tests/test_nodes/test_intelligent_orchestration.py": [
            "test_intelligent_agent_orchestrator"
        ],
    }

    # Merge all slow tests
    all_slow_tests = {}
    for tests_dict in [slow_tests, io_tests, integration_tests]:
        for file, methods in tests_dict.items():
            if file in all_slow_tests:
                all_slow_tests[file].extend(methods)
            else:
                all_slow_tests[file] = methods

    return all_slow_tests


def mark_file_slow_tests(filepath, slow_methods):
    """Mark slow tests in a single file."""
    try:
        with open(filepath) as f:
            source = f.read()

        tree = ast.parse(source)
        marker = SlowTestMarker(slow_methods)
        new_tree = marker.visit(tree)

        # Add import if needed
        if not marker.imports_pytest:
            import_node = ast.Import(names=[ast.alias(name="pytest", asname=None)])
            tree.body.insert(0, import_node)

        # Convert back to source
        import astor

        new_source = astor.to_source(new_tree)

        with open(filepath, "w") as f:
            f.write(new_source)

        print(f"✓ Marked {len(slow_methods)} slow tests in {filepath}")

    except Exception as e:
        print(f"✗ Error processing {filepath}: {e}")


def main():
    """Main function to mark all slow tests."""
    print("🏃 Marking slow tests...")

    slow_tests = find_slow_tests()

    for filepath, methods in slow_tests.items():
        full_path = Path(filepath)
        if full_path.exists():
            mark_file_slow_tests(full_path, methods)
        else:
            print(f"⚠️  File not found: {filepath}")

    print("\n✅ Slow test marking complete!")
    print("\nTo run tests excluding slow ones:")
    print("  pytest -m 'not slow'")
    print("\nTo run only slow tests:")
    print("  pytest -m slow")


if __name__ == "__main__":
    main()
