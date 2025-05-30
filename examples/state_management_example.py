"""
Simple State Management Example

This example demonstrates the immutable state management features
in the Kailash SDK without complex external dependencies.
"""

import logging

# Ensure module is in path
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).parent.parent))

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow
from kailash.workflow.state import StateManager, WorkflowStateWrapper

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StateAccumulatorNode(Node):
    """A node that accumulates values in the workflow state."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "value": NodeParameter(
                name="value", type=Any, required=True, description="Value to accumulate"
            ),
            "key": NodeParameter(
                name="key",
                type=str,
                required=True,
                description="State key to accumulate values under",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        value = kwargs.get("value")
        key = kwargs.get("key")

        # In a real workflow, this would interact with the state manager
        # For now, we'll just return the value to be accumulated
        logger.info(f"Accumulating value '{value}' under key '{key}'")

        return {"accumulated_value": value, "state_key": key, "status": "accumulated"}


class StateProcessorNode(Node):
    """A node that processes accumulated state values."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "state_values": NodeParameter(
                name="state_values",
                type=list,
                required=True,
                description="List of accumulated state values",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="sum",
                description="Operation to perform (sum, count, max, min)",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        state_values = kwargs.get("state_values", [])
        operation = kwargs.get("operation", "sum")

        result = None

        if operation == "sum":
            result = sum(state_values)
        elif operation == "count":
            result = len(state_values)
        elif operation == "max":
            result = max(state_values) if state_values else None
        elif operation == "min":
            result = min(state_values) if state_values else None
        else:
            result = state_values

        logger.info(
            f"Processed {len(state_values)} values with operation '{operation}': {result}"
        )

        return {
            "result": result,
            "operation": operation,
            "value_count": len(state_values),
        }


def demonstrate_state_management():
    """Demonstrate state management concepts using the StateManager and WorkflowStateWrapper."""

    logger.info("=== State Management Demonstration ===")

    # Create a state manager
    state_manager = StateManager()

    # Create initial state
    initial_state = {
        "messages": [],
        "values": [],
        "metadata": {"workflow_id": "state_demo", "version": "1.0"},
    }

    # Wrap the state for immutable updates
    state_wrapper = WorkflowStateWrapper(initial_state)

    # Demonstrate immutable updates
    logger.info("\n1. Adding messages to state (immutable)")
    new_state = state_wrapper.update_path("messages", ["Hello", "World"])
    logger.info(f"Original state messages: {state_wrapper.state.get('messages')}")
    logger.info(f"New state messages: {new_state.state.get('messages')}")

    # Demonstrate nested updates
    logger.info("\n2. Updating nested metadata")
    new_state = new_state.update_path("metadata.updated_at", "2025-05-29")
    logger.info(f"Updated metadata: {new_state.state.get('metadata')}")

    # Demonstrate batch updates
    logger.info("\n3. Batch updates")
    batch_updates = {
        "values": [1, 2, 3, 4, 5],
        "metadata.status": "processing",
        "metadata.node_count": 3,
    }
    new_state = new_state.batch_update(batch_updates)
    logger.info(f"After batch update: {new_state.state}")

    # Demonstrate merging state
    logger.info("\n4. Merging additional state")
    additional_state = {"results": {"sum": 15, "count": 5}}
    new_state = new_state.merge(additional_state)
    logger.info(f"After merge: {new_state.state}")

    return new_state


def demonstrate_stateful_workflow():
    """Demonstrate a workflow that uses state management."""

    logger.info("\n=== Stateful Workflow Demonstration ===")

    # Create workflow
    workflow = Workflow(
        workflow_id="stateful_workflow_demo", name="Stateful Workflow Demo"
    )

    # Create nodes
    accumulator1 = StateAccumulatorNode(name="accumulator_1")
    accumulator2 = StateAccumulatorNode(name="accumulator_2")
    accumulator3 = StateAccumulatorNode(name="accumulator_3")
    processor = StateProcessorNode(name="state_processor")

    # Add nodes to workflow
    workflow.add_node("acc1", accumulator1, config={"value": 10, "key": "values"})
    workflow.add_node("acc2", accumulator2, config={"value": 20, "key": "values"})
    workflow.add_node("acc3", accumulator3, config={"value": 30, "key": "values"})
    workflow.add_node(
        "processor",
        processor,
        config={
            "state_values": [
                10,
                20,
                30,
            ],  # In real workflow, this would come from state
            "operation": "sum",
        },
    )

    # Connect nodes (accumulate in parallel, then process)
    # Note: In a real stateful workflow, state would be passed between nodes
    # This is a simplified demonstration

    # Execute workflow
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow)

    logger.info(f"\nWorkflow completed with run_id: {run_id}")
    logger.info(f"Results: {results}")

    return workflow, results


def main():
    """Main function to run all demonstrations."""

    logger.info("=== Kailash SDK State Management Examples ===\n")

    # Demonstrate basic state management
    final_state = demonstrate_state_management()

    # Demonstrate stateful workflow
    workflow, results = demonstrate_stateful_workflow()

    # Summary
    logger.info("\n=== Summary ===")
    logger.info("State management features demonstrated:")
    logger.info("1. Immutable state updates with WorkflowStateWrapper")
    logger.info("2. Path-based updates for nested state")
    logger.info("3. Batch updates for multiple state changes")
    logger.info("4. State merging for combining results")
    logger.info("5. Stateful workflow execution (simplified)")

    logger.info("\nNote: Full stateful workflow execution with state passing between")
    logger.info("nodes would require integration with the runtime's state management.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
