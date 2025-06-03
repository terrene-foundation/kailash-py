#!/usr/bin/env python3
"""Example demonstrating Mermaid diagram visualization for workflows.

This example shows how to generate Mermaid diagrams that can be embedded
in markdown documentation for better workflow visualization.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import (
    CSVReaderNode,
    CSVWriterNode,
    JSONReaderNode,
    JSONWriterNode,
)
from kailash.nodes.transform import DataTransformer
from kailash.workflow import MermaidVisualizer, Workflow
from kailash.workflow.builder import WorkflowBuilder


def create_simple_workflow() -> Workflow:
    """Create a simple ETL workflow."""
    workflow = Workflow(
        workflow_id="simple_etl",
        name="Simple ETL Pipeline",
        description="A basic Extract-Transform-Load workflow",
    )

    # Create node instances
    reader = CSVReaderNode(file_path="../data/input.csv", headers=True)
    transformer = DataTransformer(transformations=["lambda x: x"])
    writer = CSVWriterNode(file_path="../outputs/output.csv")

    # Add nodes to workflow
    workflow.add_node(node_id="reader", node_or_type=reader)
    workflow.add_node(node_id="transformer", node_or_type=transformer)
    workflow.add_node(node_id="writer", node_or_type=writer)

    # Connect nodes
    workflow.connect("reader", "transformer", {"data": "data"})
    workflow.connect("transformer", "writer", {"transformed_data": "data"})

    return workflow


def create_complex_workflow() -> Workflow:
    """Create a complex workflow with conditional logic and multiple paths."""
    builder = WorkflowBuilder()

    # Input nodes (using config for builder pattern)
    csv_reader = builder.add_node(
        "CSVReaderNode",
        "customer_reader",
        {"file_path": "../data/customers.csv", "headers": True},
    )
    json_reader = builder.add_node(
        "JSONReaderNode",
        "transaction_reader",
        {"file_path": "../data/transactions.json"},
    )

    # Processing nodes
    validator = builder.add_node(
        "PythonCodeNode",
        "data_validator",
        {
            "name": "DataValidator",
            "code": "def execute(input_data, transactions):\n    return {'validated_data': input_data}",
        },
    )

    # Conditional routing
    switch = builder.add_node(
        "SwitchNode",
        "quality_router",
        {"field": "quality", "cases": ["high", "low", "error"]},
    )

    # Different processing paths
    high_quality = builder.add_node(
        "DataTransformer", "premium_processor", {"transformations": ["lambda x: x"]}
    )
    low_quality = builder.add_node(
        "Filter", "basic_filter", {"field": "value", "operator": ">", "value": 100}
    )
    error_handler = builder.add_node(
        "PythonCodeNode",
        "error_handler",
        {
            "name": "ErrorHandler",
            "code": "def execute(data):\n    return {'handled_errors': data}",
        },
    )

    # More transformations
    aggregator = builder.add_node(
        "DataTransformer", "data_aggregator", {"transformations": ["lambda x: x"]}
    )
    normalizer = builder.add_node(
        "DataTransformer", "data_normalizer", {"transformations": ["lambda x: x"]}
    )

    # Merge results
    merger = builder.add_node("MergeNode", "result_merger", {})

    # Output
    json_writer = builder.add_node(
        "JSONWriterNode", "final_output", {"file_path": "../outputs/output.json"}
    )

    # Connect the workflow
    builder.add_connection(csv_reader, "data", validator, "input_data")
    builder.add_connection(json_reader, "data", validator, "transactions")

    builder.add_connection(validator, "validated_data", switch, "input")

    # SwitchNode outputs to different paths
    builder.add_connection(switch, "case_high", high_quality, "data")
    builder.add_connection(switch, "case_low", low_quality, "data")
    builder.add_connection(switch, "case_error", error_handler, "data")

    # Additional processing for high quality data
    builder.add_connection(high_quality, "transformed_data", aggregator, "data")
    builder.add_connection(aggregator, "transformed_data", normalizer, "data")

    # MergeNode all paths
    builder.add_connection(normalizer, "transformed_data", merger, "input1")
    builder.add_connection(low_quality, "filtered_data", merger, "input2")
    builder.add_connection(error_handler, "handled_errors", merger, "input3")

    # Final output
    builder.add_connection(merger, "merged_data", json_writer, "data")

    workflow = builder.build(
        workflow_id="complex_pipeline",
        name="Complex Data Processing Pipeline",
        description="A sophisticated workflow with conditional routing and API integration",
    )

    return workflow


def demonstrate_mermaid_visualization():
    """Demonstrate various Mermaid visualization features."""
    print("Mermaid Workflow Visualization Examples")
    print("=" * 50)
    print()

    # Example 1: Simple workflow
    print("1. Simple ETL Workflow")
    print("-" * 30)
    simple_workflow = create_simple_workflow()
    print(simple_workflow.to_mermaid())
    print()

    # Save as markdown
    simple_workflow.save_mermaid_markdown(
        "../outputs/simple_workflow_mermaid.md",
        title="Simple ETL Pipeline Visualization",
    )
    print("Saved to: ../outputs/simple_workflow_mermaid.md")
    print()

    # Example 2: Complex workflow with different direction
    print("2. Complex Workflow (Left to Right)")
    print("-" * 30)
    complex_workflow = create_complex_workflow()
    print(complex_workflow.to_mermaid(direction="LR"))
    print()

    # Save complex workflow
    complex_workflow.save_mermaid_markdown(
        "../outputs/complex_workflow_mermaid.md",
        title="Complex Processing Pipeline",
    )
    print("Saved to: ../outputs/complex_workflow_mermaid.md")
    print()

    # Example 3: Custom visualization
    print("3. Custom Mermaid Visualization")
    print("-" * 30)

    # Create custom visualizer with different styles
    custom_styles = {
        "reader": "fill:#2196F3,stroke:#0D47A1,stroke-width:3px,color:#fff",
        "writer": "fill:#4CAF50,stroke:#1B5E20,stroke-width:3px,color:#fff",
        "transform": "fill:#FF9800,stroke:#E65100,stroke-width:3px,color:#fff",
        "logic": "fill:#E91E63,stroke:#880E4F,stroke-width:3px,color:#fff",
    }

    visualizer = MermaidVisualizer(
        simple_workflow, direction="TB", node_styles=custom_styles
    )

    # Generate just the diagram
    mermaid_code = visualizer.generate()
    print(mermaid_code)
    print()

    # Example 4: Generate full markdown documentation
    print("4. Full Markdown Documentation")
    print("-" * 30)
    markdown_content = complex_workflow.to_mermaid_markdown(
        title="Data Processing Pipeline Documentation"
    )
    print(markdown_content[:500] + "...")  # Show first 500 chars
    print()

    # Example 5: Programmatic workflow creation with immediate visualization
    print("5. Real-time Workflow Visualization")
    print("-" * 30)

    # Create a workflow for API integration
    api_workflow = Workflow(
        workflow_id="api_integration",
        name="API Integration Flow",
        description="Demonstrates API data fetching and processing",
    )

    # Create node instances
    fetch_data = JSONReaderNode(file_path="../data/transactions.json")
    process_data = PythonCodeNode(
        name="ProcessData", code="def execute(data):\n    return {'processed': data}"
    )
    transform_data = DataTransformer(transformations=["lambda x: {'final': x}"])
    save_results = JSONWriterNode(file_path="../outputs/api_results.json")

    # Add nodes to workflow
    api_workflow.add_node(node_id="fetch_data", node_or_type=fetch_data)
    api_workflow.add_node(node_id="process_data", node_or_type=process_data)
    api_workflow.add_node(node_id="transform_data", node_or_type=transform_data)
    api_workflow.add_node(node_id="save_results", node_or_type=save_results)

    # Connect the nodes
    api_workflow.connect("fetch_data", "process_data", {"data": "data"})
    api_workflow.connect("process_data", "transform_data", {"processed": "data"})
    api_workflow.connect("transform_data", "save_results", {"transformed_data": "data"})

    # Generate and display
    print(api_workflow.to_mermaid(direction="LR"))
    print()

    # Save API workflow
    api_workflow.save_mermaid_markdown(
        "../outputs/api_workflow_mermaid.md",
        title="API Integration Workflow",
    )
    print("Saved to: ../outputs/api_workflow_mermaid.md")
    print()

    print("All examples completed!")
    print("\nYou can copy the Mermaid code into any markdown file or")
    print("documentation that supports Mermaid rendering (GitHub, GitLab, etc.)")


if __name__ == "__main__":
    # Ensure output directory exists
    os.makedirs("../outputs", exist_ok=True)

    # Run the demonstration
    demonstrate_mermaid_visualization()
