"""Example 2: Production Logging with Debug Agent

This example demonstrates integration with Python's logging module for
structured error logging in production applications.

Usage:
    python examples/debug_agent/02_production_logging.py
"""

import asyncio
import logging
import sys

from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("debug_agent.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def execute_workflow_with_logging(db, agent, workflow_data):
    """Execute workflow with structured error logging."""
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", workflow_data)

    runtime = LocalRuntime()
    try:
        logger.info(
            "Executing workflow",
            extra={"operation": "CREATE", "node_type": "UserCreateNode"},
        )

        results, run_id = runtime.execute(workflow.build())

        logger.info(
            "Workflow executed successfully",
            extra={"run_id": run_id, "result_count": len(results)},
        )

        return results
    except Exception as e:
        # Debug error automatically
        report = agent.debug(e, max_solutions=3, min_relevance=0.5)

        # Log structured error data
        logger.error(
            "Workflow execution failed",
            extra={
                "error_type": report.captured_error.error_type,
                "error_message": report.captured_error.message,
                "category": report.error_category.category,
                "pattern_id": report.error_category.pattern_id,
                "confidence": f"{report.error_category.confidence * 100:.0f}%",
                "root_cause": report.analysis_result.root_cause,
                "affected_nodes": report.analysis_result.affected_nodes,
                "affected_models": report.analysis_result.affected_models,
                "solutions_count": len(report.suggested_solutions),
                "execution_time_ms": report.execution_time,
            },
        )

        # Log full JSON report for external systems
        logger.debug("Full debug report", extra={"report_json": report.to_json()})

        # Log top solution
        if report.suggested_solutions:
            top_solution = report.suggested_solutions[0]
            logger.info(
                "Top suggested solution",
                extra={
                    "solution_id": top_solution.solution_id,
                    "title": top_solution.title,
                    "category": top_solution.category,
                    "relevance": f"{top_solution.relevance_score * 100:.0f}%",
                    "difficulty": top_solution.difficulty,
                    "estimated_time_min": top_solution.estimated_time,
                },
            )

        # Re-raise for upstream handling
        raise


def main():
    """Production logging example."""
    print("=" * 80)
    print("Example 2: Production Logging")
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

    # Test Case 1: Missing 'id' parameter
    print("Test Case 1: Missing 'id' parameter")
    print("-" * 80)
    try:
        execute_workflow_with_logging(
            db,
            agent,
            {
                "name": "Alice",
                "email": "alice@example.com",
                # Missing 'id'
            },
        )
    except Exception:
        print("✓ Error logged successfully")
    print()

    # Test Case 2: Type mismatch
    print("Test Case 2: Valid workflow")
    print("-" * 80)
    try:
        execute_workflow_with_logging(
            db, agent, {"id": "user-123", "name": "Bob", "email": "bob@example.com"}
        )
    except Exception:
        print("✗ Unexpected error")
    print()

    print("Logs written to: debug_agent.log")


if __name__ == "__main__":
    main()
