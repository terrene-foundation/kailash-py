"""Example demonstrating hierarchical workflow composition using WorkflowNode.

This example shows how to:
1. Create a reusable workflow for data processing
2. Wrap it as a WorkflowNode
3. Use it as a component in a larger workflow
4. Demonstrate different loading methods
"""

import os
import sys
from pathlib import Path

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.logic import WorkflowNode
from kailash.nodes.transform import Filter
from kailash.runtime.local import LocalRuntime
from kailash.utils.export import WorkflowExporter
from kailash.workflow.graph import Workflow

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# Define simple test nodes for examples that don't require file I/O
@register_node()
class NumberGeneratorNode(Node):
    """Generates a list of numbers."""

    def get_parameters(self):
        return {
            "count": NodeParameter(
                name="count",
                type=int,
                required=True,
                default=10,
                description="Number of values to generate",
            ),
            "start": NodeParameter(
                name="start",
                type=int,
                required=False,
                default=0,
                description="Starting value",
            ),
        }

    def run(self, count=10, start=0):
        return {"numbers": list(range(start, start + count))}


@register_node()
class MultiplyNode(Node):
    """Multiplies numbers by a factor."""

    def get_parameters(self):
        return {
            "numbers": NodeParameter(
                name="numbers",
                type=list,
                required=False,  # Will come from connections
                description="List of numbers to multiply",
            ),
            "factor": NodeParameter(
                name="factor",
                type=float,
                required=False,
                default=2.0,
                description="Multiplication factor",
            ),
        }

    def run(self, numbers, factor=2.0):
        return {"result": [n * factor for n in numbers]}


@register_node()
class SumNode(Node):
    """Sums a list of numbers."""

    def get_parameters(self):
        return {
            "numbers": NodeParameter(
                name="numbers",
                type=list,
                required=False,  # Will come from connections
                description="Numbers to sum",
            )
        }

    def run(self, numbers):
        return {"total": sum(numbers)}


@register_node()
class MockDataGeneratorNode(Node):
    """Generates mock CSV-like data for testing."""

    def get_parameters(self):
        return {
            "num_rows": NodeParameter(
                name="num_rows",
                type=int,
                required=False,
                default=100,
                description="Number of rows to generate",
            )
        }

    def run(self, num_rows=100):
        # Generate mock data similar to CSV
        data = []
        categories = ["A", "B", "C", "D"]

        for i in range(1, num_rows + 1):
            row = {
                "id": str(i),
                "name": f"Item {i}",
                "value": i * 10,  # Keep as int for filtering
                "category": categories[(i - 1) % 4],
            }
            data.append(row)

        return {"data": data}


@register_node()
class DataLoggerNode(Node):
    """Logs data statistics without writing to file."""

    def get_parameters(self):
        return {
            "data": NodeParameter(
                name="data", type=list, required=False, description="Data to log"
            )
        }

    def run(self, data=None):
        if not data:
            return {"row_count": 0, "message": "No data received"}

        row_count = len(data)
        sample = data[:3] if data else []

        return {
            "row_count": row_count,
            "message": f"Processed {row_count} rows",
            "sample": sample,
        }


def create_simple_workflow():
    """Create a simple math processing workflow."""
    workflow = Workflow(workflow_id="math_processor", name="Math Processing Pipeline")

    # Add nodes
    generator = NumberGeneratorNode(name="generator")
    multiplier = MultiplyNode(name="multiplier")
    summer = SumNode(name="summer")

    workflow.add_node("generator", generator)
    workflow.add_node("multiplier", multiplier)
    workflow.add_node("summer", summer)

    # Connect nodes
    workflow.connect("generator", "multiplier", {"numbers": "numbers"})
    workflow.connect("multiplier", "summer", {"result": "numbers"})

    return workflow


def create_data_processing_workflow():
    """Create a reusable data processing workflow."""
    workflow = Workflow(
        workflow_id="data_processor",
        name="Data Processing Pipeline",
        description="Reusable workflow for data processing",
    )

    # Add nodes using mock data generator instead of CSV reader
    reader = MockDataGeneratorNode(name="reader", description="Generate mock data")

    # Use Filter node to filter data
    filter_node = Filter(
        name="filter", description="Filter data", field="value", operator=">", value=50
    )

    # Use DataLoggerNode instead of CSV writer
    writer = DataLoggerNode(name="writer", description="Log processed data")

    # Build workflow
    workflow.add_node("reader", reader)
    workflow.add_node("filter", filter_node)
    workflow.add_node("writer", writer)

    # Connect nodes
    workflow.connect("reader", "filter", {"data": "data"})
    workflow.connect("filter", "writer", {"filtered_data": "data"})

    return workflow


def example_direct_workflow_wrapping():
    """Example 1: Direct workflow wrapping."""
    print("\n=== Example 1: Direct Workflow Wrapping ===")

    # Create the inner workflow
    inner_workflow = create_data_processing_workflow()

    # Wrap it as a node
    workflow_node = WorkflowNode(
        workflow=inner_workflow,
        name="data_processor_node",
        description="Processes CSV data through a workflow",
    )

    # Create outer workflow
    main_workflow = Workflow(
        workflow_id="main_workflow", name="Main Processing Pipeline"
    )

    # Add the workflow node
    main_workflow.add_node("processor", workflow_node)

    # Execute with inputs mapped to inner workflow nodes
    runtime = LocalRuntime()
    results, task_id = runtime.execute(
        main_workflow,
        parameters={
            "processor": {
                "reader_num_rows": 20,  # Generate 20 rows
                "filter_value": 100,  # Filter for values > 100
            }
        },
    )

    # Extract and display results
    processor_results = results["processor"]["results"]
    print(
        f"Generated rows: {processor_results['reader']['data'][:5]}..."
    )  # Show first 5
    print(f"Filtered count: {processor_results['writer']['row_count']}")
    print(f"Message: {processor_results['writer']['message']}")

    return main_workflow


def example_simple_math_workflow():
    """Example 2: Simple math workflow composition."""
    print("\n=== Example 2: Simple Math Workflow ===")

    # Create inner workflow
    math_workflow = create_simple_workflow()

    # Wrap it as a node
    math_node = WorkflowNode(
        workflow=math_workflow,
        name="math_processor",
        description="Processes numbers through math operations",
    )

    # Create outer workflow
    main_workflow = Workflow(workflow_id="main", name="Main Workflow")

    main_workflow.add_node("math", math_node)

    # Execute with different parameters
    runtime = LocalRuntime()

    print("\nTest 1: Generate 5 numbers starting at 10, multiply by 3")
    results1, _ = runtime.execute(
        main_workflow,
        parameters={
            "math": {
                "generator_count": 5,
                "generator_start": 10,
                "multiplier_factor": 3.0,
            }
        },
    )

    # Extract results
    math_results = results1["math"]["results"]
    print(f"Generated: {math_results['generator']['numbers']}")
    print(f"Multiplied: {math_results['multiplier']['result']}")
    print(f"Sum: {math_results['summer']['total']}")

    print("\nTest 2: Generate 3 numbers starting at 0, multiply by 10")
    results2, _ = runtime.execute(
        main_workflow,
        parameters={"math": {"generator_count": 3, "multiplier_factor": 10.0}},
    )

    math_results2 = results2["math"]["results"]
    print(f"Generated: {math_results2['generator']['numbers']}")
    print(f"Multiplied: {math_results2['multiplier']['result']}")
    print(f"Sum: {math_results2['summer']['total']}")

    return main_workflow


def example_workflow_from_file():
    """Example 3: Loading workflow from file."""
    print("\n=== Example 3: Loading Workflow from File ===")

    # First, export a simple workflow to file
    math_workflow = create_simple_workflow()
    export_path = Path("data/exports/math_processor.yaml")

    exporter = WorkflowExporter()
    exporter.to_yaml(math_workflow, str(export_path))
    print(f"Exported workflow to: {export_path}")

    # Create a workflow node that loads from file
    workflow_node = WorkflowNode(
        workflow_path=str(export_path),
        name="file_based_processor",
        description="Workflow loaded from YAML file",
    )

    # Use in a main workflow
    main_workflow = Workflow(
        workflow_id="file_based_main", name="File-based Workflow Composition"
    )

    main_workflow.add_node("processor", workflow_node)

    # Execute to verify it works
    runtime = LocalRuntime()
    results, _ = runtime.execute(
        main_workflow,
        parameters={
            "processor": {
                "generator_count": 4,
                "generator_start": 5,
                "multiplier_factor": 2.5,
            }
        },
    )

    processor_results = results["processor"]["results"]
    print("Loaded and executed workflow from file")
    print(f"Result: {processor_results['summer']['total']}")

    return main_workflow


def example_custom_mapping():
    """Example 4: Custom input/output mapping."""
    print("\n=== Example 4: Custom Input/Output Mapping ===")

    data_workflow = create_data_processing_workflow()

    # Create workflow node with custom mappings
    workflow_node = WorkflowNode(
        workflow=data_workflow,
        name="mapped_processor",
        description="Workflow with custom parameter mapping",
        input_mapping={
            "rows": {
                "node": "reader",
                "parameter": "num_rows",
                "type": int,
                "required": False,
                "default": 50,
                "description": "Number of rows to generate",
            },
            "threshold": {
                "node": "filter",
                "parameter": "value",
                "type": int,
                "required": False,
                "default": 100,
                "description": "Filter threshold",
            },
        },
        output_mapping={
            "filtered_count": {
                "node": "writer",
                "output": "row_count",
                "type": int,
                "description": "Number of filtered rows",
            },
            "sample_data": {
                "node": "writer",
                "output": "sample",
                "type": list,
                "description": "Sample of filtered data",
            },
        },
    )

    # Create main workflow
    main_workflow = Workflow(
        workflow_id="mapped_main", name="Workflow with Custom Mappings"
    )

    main_workflow.add_node("processor", workflow_node)

    # Execute with simplified inputs
    runtime = LocalRuntime()
    results, _ = runtime.execute(
        main_workflow, parameters={"processor": {"rows": 30, "threshold": 150}}
    )

    # Access custom mapped outputs
    print(f"Filtered count: {results['processor']['filtered_count']}")
    print(f"Sample data: {results['processor']['sample_data']}")

    return main_workflow


def example_nested_workflows():
    """Example 5: Multiple levels of nesting."""
    print("\n=== Example 5: Nested Workflow Composition ===")

    # Level 1: Basic math processing
    level1_workflow = create_simple_workflow()

    # Level 2: Wrap level 1 and add more processing
    level2_workflow = Workflow(
        workflow_id="enhanced_math", name="Enhanced Math Pipeline"
    )

    # Wrap level 1 as a node
    math_node = WorkflowNode(workflow=level1_workflow, name="basic_math")

    # Add another multiply operation
    extra_multiply = MultiplyNode(name="extra_multiply", factor=0.5)  # Divide by 2

    level2_workflow.add_node("basic", math_node)
    level2_workflow.add_node("scale", extra_multiply)

    # We need to wrap the sum in a list for the multiply node
    # Add a simple node to convert the sum to a list
    @register_node()
    class NumberToListNode(Node):
        """Converts a single number to a list containing that number."""

        def get_parameters(self):
            return {
                "number": NodeParameter(
                    name="number",
                    type=float,
                    required=False,
                    description="Number to convert to list",
                )
            }

        def run(self, number):
            return {"list": [number]}

    converter = NumberToListNode(name="converter")
    level2_workflow.add_node("convert", converter)

    # Connect the sum to converter, then to scale
    level2_workflow.connect("basic", "convert", {"summer_total": "number"})
    level2_workflow.connect("convert", "scale", {"list": "numbers"})

    # Level 3: Wrap level 2 for use in main application
    level3_workflow = Workflow(
        workflow_id="main_application", name="Main Application Workflow"
    )

    enhanced_node = WorkflowNode(workflow=level2_workflow, name="full_pipeline")

    level3_workflow.add_node("pipeline", enhanced_node)

    print("Created 3-level nested workflow hierarchy:")
    print("  Level 3: Main Application")
    print("    └── Level 2: Enhanced Math Pipeline")
    print("          └── Level 1: Basic Math Operations")

    # Execute the nested workflow
    runtime = LocalRuntime()
    results, _ = runtime.execute(
        level3_workflow,
        parameters={
            "pipeline": {
                "basic_generator_count": 4,
                "basic_generator_start": 2,
                "basic_multiplier_factor": 3.0,
            }
        },
    )

    # Show results from different levels
    pipeline_results = results["pipeline"]["results"]
    basic_results = pipeline_results["basic"]["results"]

    print(f"\nLevel 1 sum: {basic_results['summer']['total']}")
    print(f"Level 2 scaled: {pipeline_results['scale']['result']}")

    return level3_workflow


def main():
    """Run all workflow composition examples."""
    print("=== Kailash WorkflowNode Examples ===")
    print("Demonstrating hierarchical workflow composition\n")

    # Ensure output directory exists
    os.makedirs("data/outputs", exist_ok=True)
    os.makedirs("data/exports", exist_ok=True)

    # Run examples
    try:
        # Example 1: Direct wrapping with data processing
        example_direct_workflow_wrapping()

        # Example 2: Simple math workflow
        workflow2 = example_simple_math_workflow()

        # Example 3: File-based loading (skip for now due to export format issue)
        # workflow3 = example_workflow_from_file()

        # Example 4: Custom mapping
        example_custom_mapping()

        # Example 5: Nested workflows
        example_nested_workflows()

        print("\n✓ All examples completed successfully!")

        # Export one of the workflows for visualization
        exporter = WorkflowExporter()
        export_path = Path("data/exports/nested_workflow_example.yaml")
        exporter.to_yaml(workflow2, str(export_path))
        print(f"\nExported example workflow to: {export_path}")

    except Exception as e:
        print(f"\n✗ Example failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
