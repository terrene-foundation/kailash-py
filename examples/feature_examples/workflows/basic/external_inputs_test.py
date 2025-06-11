"""Example demonstrating how to pass external inputs to workflows.

This example shows different patterns for providing initial data to workflows:
1. Traditional source nodes that generate their own data
2. Processing nodes that receive external data via parameters
3. Hybrid approach with both patterns
"""

from pathlib import Path
from typing import Any

from examples.utils.paths import get_data_dir
from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.data import CSVReaderNode
from kailash.runtime import LocalRuntime


class DataProcessorNode(Node):
    """Simple node that processes input data."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data to process",
            ),
            "multiplier": NodeParameter(
                name="multiplier",
                type=float,
                required=False,
                default=2.0,
                description="Multiplier for numeric values",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        data = kwargs["data"]
        multiplier = kwargs.get("multiplier", 2.0)

        # Process the data
        processed = []
        for item in data:
            if isinstance(item, dict) and "value" in item:
                processed.append(
                    {**item, "processed_value": item["value"] * multiplier}
                )
            elif isinstance(item, (int, float)):
                processed.append({"original": item, "processed": item * multiplier})
            else:
                processed.append(item)

        return {"processed_data": processed}


def example_1_source_node_pattern():
    """Traditional pattern: Workflow starts with a source node."""
    print("\n=== Example 1: Source Node Pattern ===")

    # Create workflow
    workflow = Workflow("source_pattern", "Source Node Example")

    # Add source node that reads from file
    csv_reader = CSVReaderNode(
        file_path=str(get_data_dir() / "sample_data.csv"), headers=True
    )
    workflow.add_node("reader", csv_reader)

    # Add processor
    processor = DataProcessorNode()
    workflow.add_node("processor", processor, multiplier=3.0)

    # Connect nodes
    workflow.connect("reader", "processor", {"data": "data"})

    # Execute - no external parameters needed
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow)

    print(f"Results: {results}")
    print("Note: Data came from the CSV file, no external input needed")


def example_2_external_input_pattern():
    """Modern pattern: Workflow receives external data via parameters."""
    print("\n=== Example 2: External Input Pattern ===")

    # Create workflow
    workflow = Workflow("external_pattern", "External Input Example")

    # Add processor as first node
    processor = DataProcessorNode()
    workflow.add_node("processor", processor)

    # Prepare external data
    external_data = [
        {"id": 1, "value": 10},
        {"id": 2, "value": 20},
        {"id": 3, "value": 30},
    ]

    # Execute with external data
    runtime = LocalRuntime()
    results, run_id = runtime.execute(
        workflow, parameters={"processor": {"data": external_data, "multiplier": 5.0}}
    )

    print(f"External data: {external_data}")
    print(f"Results: {results}")
    print("Note: Data was passed directly to the processor node")


def example_3_hybrid_pattern():
    """Hybrid pattern: Source node with runtime parameter override."""
    print("\n=== Example 3: Hybrid Pattern ===")

    # Create workflow
    workflow = Workflow("hybrid_pattern", "Hybrid Example")

    # Add CSV reader with default file
    default_file = Path(__file__).parent / "data" / "default.csv"
    workflow.add_node("reader", CSVReaderNode(), file_path=str(default_file))

    # Add processor
    workflow.add_node("processor", DataProcessorNode())

    # Connect nodes
    workflow.connect("reader", "processor", {"data": "data"})

    # Execute with parameter override
    runtime = LocalRuntime()
    custom_file = Path(__file__).parent / "data" / "custom.csv"

    results, run_id = runtime.execute(
        workflow,
        parameters={
            "reader": {"file_path": str(custom_file)},  # Override default file
            "processor": {"multiplier": 10.0},  # Override processing parameter
        },
    )

    print(f"Default file: {default_file}")
    print(f"Custom file: {custom_file}")
    print(f"Results: {results}")
    print("Note: Both source node config and processor config were overridden")


def example_4_multi_entry_workflow():
    """Complex pattern: Multiple entry points in a workflow."""
    print("\n=== Example 4: Multi-Entry Workflow ===")

    # Create workflow
    workflow = Workflow("multi_entry", "Multi-Entry Example")

    # Add multiple processors that can receive external data
    processor1 = DataProcessorNode()
    processor2 = DataProcessorNode()
    merger = DataProcessorNode()  # Merges results

    workflow.add_node("processor1", processor1)
    workflow.add_node("processor2", processor2)
    workflow.add_node("merger", merger)

    # Connect processors to merger
    workflow.connect("processor1", "merger", {"processed_data": "data"})
    workflow.connect("processor2", "merger", {"processed_data": "data"})

    # Execute with data for multiple entry points
    runtime = LocalRuntime()
    results, run_id = runtime.execute(
        workflow,
        parameters={
            "processor1": {"data": [1, 2, 3], "multiplier": 2.0},
            "processor2": {"data": [4, 5, 6], "multiplier": 3.0},
            "merger": {"multiplier": 0.5},  # Final processing
        },
    )

    print(f"Results: {results}")
    print("Note: Multiple nodes received external inputs simultaneously")


def main():
    """Run all examples."""
    print("Kailash SDK - External Input Patterns")
    print("=" * 50)

    # Run examples
    example_1_source_node_pattern()
    example_2_external_input_pattern()
    example_3_hybrid_pattern()
    example_4_multi_entry_workflow()

    print("\n" + "=" * 50)
    print("Key Takeaways:")
    print("1. Workflows can start with source nodes OR processing nodes")
    print("2. Any node can receive data via runtime.execute() parameters")
    print("3. The parameters dict maps node IDs to their inputs")
    print("4. Parameters override both config and connected inputs")


if __name__ == "__main__":
    main()
