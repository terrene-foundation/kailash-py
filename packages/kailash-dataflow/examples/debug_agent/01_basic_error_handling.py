"""Example 1: Basic Error Handling with Debug Agent

This example demonstrates simple try/catch integration with the Debug Agent
for immediate error diagnosis during development.

Usage:
    python examples/debug_agent/01_basic_error_handling.py
"""

import asyncio

from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def main():
    """Basic error handling example."""
    print("=" * 80)
    print("Example 1: Basic Error Handling")
    print("=" * 80)
    print()

    # Initialize DataFlow
    db = DataFlow(":memory:")

    @db.model
    class User:
        id: str
        name: str
        email: str

    # Initialize Debug Agent
    kb = KnowledgeBase(
        "src/dataflow/debug/patterns.yaml", "src/dataflow/debug/solutions.yaml"
    )
    inspector = Inspector(db)
    agent = DebugAgent(kb, inspector)

    # Initialize database
    asyncio.run(db.initialize())

    # Create workflow with intentional error (missing 'id' parameter)
    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserCreateNode",
        "create",
        {
            "name": "Alice",
            "email": "alice@example.com",
            # Missing required 'id' parameter - will cause error
        },
    )

    # Execute workflow with error handling
    runtime = LocalRuntime()
    try:
        print("Executing workflow...")
        results, run_id = runtime.execute(workflow.build())
        print("✓ Workflow executed successfully")
        print(f"  Run ID: {run_id}")
        print(f"  Results: {results}")
    except Exception as e:
        print("✗ Workflow execution failed")
        print(f"  Error: {e}")
        print()

        # Debug the error automatically
        print("Debugging error with Debug Agent...")
        report = agent.debug(e, max_solutions=5, min_relevance=0.3)

        # Display rich CLI output
        print()
        print(report.to_cli_format())

        # You can also access report data programmatically
        print()
        print("Programmatic Access:")
        print(f"  Category: {report.error_category.category}")
        print(f"  Confidence: {report.error_category.confidence * 100:.0f}%")
        print(f"  Root Cause: {report.analysis_result.root_cause}")
        print(f"  Solutions Found: {len(report.suggested_solutions)}")
        print(f"  Execution Time: {report.execution_time:.1f}ms")

        if report.suggested_solutions:
            print()
            print("Top Solution:")
            top_solution = report.suggested_solutions[0]
            print(f"  Title: {top_solution.title}")
            print(f"  Relevance: {top_solution.relevance_score * 100:.0f}%")
            print(f"  Difficulty: {top_solution.difficulty}")
            print(f"  Estimated Time: {top_solution.estimated_time} min")


if __name__ == "__main__":
    main()
