#!/usr/bin/env python3
"""
Export Workflow Example

This example demonstrates how to export workflows for Kailash integration
using the actual SDK implementation.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.utils.export import ExportConfig, WorkflowExporter, export_workflow
from kailash.workflow.graph import Workflow


def create_sample_workflow():
    """Create a sample workflow for export demonstration."""

    workflow = Workflow(
        workflow_id="customer_analysis_pipeline",
        name="customer_analysis_pipeline",
        description="Analyze customer data and generate insights",
    )

    # Add metadata
    workflow.metadata["tags"] = {"customer", "analytics", "ml"}
    workflow.metadata["version"] = "1.0.0"
    workflow.metadata["author"] = "John Doe"

    # Create nodes
    csv_reader = CSVReaderNode(file_path="../data/customers.csv", headers=True)

    # Create transformer using PythonCodeNode
    def transform_data(data: list) -> Dict[str, Any]:
        """Transform customer data."""
        # Simulate data transformation
        transformed = []
        for record in data:
            new_record = record.copy()
            if isinstance(record.get("age"), (int, float)):
                new_record["age_group"] = "Senior" if record["age"] >= 60 else "Adult"
            if isinstance(record.get("income"), (int, float)):
                new_record["income_level"] = (
                    "High" if record["income"] > 100000 else "Medium"
                )
            transformed.append(new_record)
        return {"data": transformed}

    from kailash.nodes.base import NodeParameter

    input_schema = {"data": NodeParameter(name="data", type=list, required=True)}
    output_schema = {"data": NodeParameter(name="data", type=list, required=True)}

    transformer = PythonCodeNode.from_function(
        transform_data,
        name="process_data",
        input_schema=input_schema,
        output_schema=output_schema,
    )

    # Create classifier using PythonCodeNode
    def classify_customers(data: list) -> Dict[str, Any]:
        """Classify customers into segments."""
        # Simulate classification
        segments = []
        for record in data:
            segment = "Premium" if record.get("income_level") == "High" else "Standard"
            record["segment"] = segment
            segments.append(record)
        return {"data": segments}

    classifier = PythonCodeNode.from_function(
        classify_customers,
        name="segment_customers",
        input_schema=input_schema,
        output_schema=output_schema,
    )

    csv_writer = CSVWriterNode(file_path="../data/export_results.csv")

    # Add nodes to workflow with configuration
    workflow.add_node(
        node_id="reader",
        node_or_type=csv_reader,
        config={"file_path": "../data/customers.csv"},
    )
    workflow.add_node(node_id="transformer", node_or_type=transformer)
    workflow.add_node(node_id="classifier", node_or_type=classifier)
    workflow.add_node(
        node_id="writer",
        node_or_type=csv_writer,
        config={"file_path": "../data/customer_segments.csv"},
    )

    # Connect nodes
    workflow.connect("reader", "transformer", {"data": "data"})
    workflow.connect("transformer", "classifier", {"data": "data"})
    workflow.connect("classifier", "writer", {"data": "data"})

    return workflow


def demonstrate_basic_export():
    """Demonstrate basic workflow export."""

    print("\n=== Basic Workflow Export ===")

    workflow = create_sample_workflow()

    # Basic export to YAML
    yaml_content = export_workflow(workflow, format="yaml")

    # Save to file
    output_path = "../data/exports/basic_workflow.yaml"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(yaml_content)

    print(f"✓ Workflow exported to: {output_path}")

    # Show export content
    print("\nExport preview:")
    print(yaml_content[:500] + "..." if len(yaml_content) > 500 else yaml_content)


def demonstrate_export_with_config():
    """Demonstrate export with custom configuration."""

    print("\n=== Export with Configuration ===")

    workflow = create_sample_workflow()

    # Configure export
    config = ExportConfig(
        version="1.0",
        namespace="production",
        include_metadata=True,
        include_resources=True,
        validate_output=True,
    )

    exporter = WorkflowExporter(config)

    # Export to JSON
    json_content = exporter.to_json(workflow)

    # Save to file
    output_path = "../data/exports/workflow_with_config.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(json_content)

    print(f"✓ Workflow with config exported to: {output_path}")

    # Load and display some data
    data = json.loads(json_content)
    print("\nMetadata included:")
    for key in data.get("metadata", {}).keys():
        print(f"  - {key}")


def demonstrate_manifest_export():
    """Demonstrate Kubernetes manifest export."""

    print("\n=== Kubernetes Manifest Export ===")

    workflow = create_sample_workflow()

    # Configure for Kubernetes
    config = ExportConfig(namespace="analytics", container_registry="your-registry.io")

    exporter = WorkflowExporter(config)

    # Export as manifest
    manifest_content = exporter.to_manifest(workflow)

    # Save to file
    output_path = "../data/exports/workflow_manifest.yaml"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(manifest_content)

    print(f"✓ Kubernetes manifest exported to: {output_path}")

    # Show manifest preview
    print("\nManifest preview:")
    print(
        manifest_content[:500] + "..."
        if len(manifest_content) > 500
        else manifest_content
    )


def demonstrate_custom_node_mapping():
    """Demonstrate custom node to container mapping."""

    print("\n=== Custom Node Mapping ===")

    workflow = create_sample_workflow()

    # Create exporter with custom mappings
    exporter = WorkflowExporter()

    # Register custom node mappings
    exporter.register_custom_mapping(
        node_type="PythonCodeNode",
        container_image="custom/python-executor:latest",
        command=["python", "-m", "executor"],
        args=["--config", "/config/node.yaml"],
        resources={"cpu": "500m", "memory": "1Gi"},
    )

    # Export with custom mappings
    yaml_content = exporter.to_yaml(workflow)

    # Save to file
    output_path = "../data/exports/workflow_custom_mapping.yaml"
    with open(output_path, "w") as f:
        f.write(yaml_content)

    print(f"✓ Workflow with custom mappings exported to: {output_path}")


def demonstrate_template_export():
    """Demonstrate export using templates."""

    print("\n=== Template-based Export ===")

    workflow = create_sample_workflow()
    exporter = WorkflowExporter()

    # Export using different templates
    template_types = ["minimal", "standard", "kubernetes", "docker"]

    for template_name in template_types:
        try:
            exports = exporter.export_with_templates(
                workflow,
                template_name=template_name,
                output_dir=f"../data/exports/{template_name}",
            )

            print(f"✓ {template_name.title()} template export completed:")
            for file_path in exports.keys():
                print(f"  - {file_path}")

        except Exception as e:
            print(f"✗ Failed to export with {template_name} template: {e}")


def demonstrate_partial_export():
    """Demonstrate exporting only part of a workflow."""

    print("\n=== Partial Export ===")

    workflow = create_sample_workflow()

    # Configure partial export (only export specific nodes)
    config = ExportConfig(
        partial_export={"reader", "transformer", "writer"}  # Skip classifier
    )

    exporter = WorkflowExporter(config)

    # Export partial workflow
    yaml_content = exporter.to_yaml(workflow)

    # Save to file
    output_path = "../data/exports/partial_workflow.yaml"
    with open(output_path, "w") as f:
        f.write(yaml_content)

    print(f"✓ Partial workflow exported to: {output_path}")

    # Show which nodes were exported
    data = yaml.safe_load(yaml_content)
    print("\nExported nodes:")
    for node_id in data.get("nodes", {}).keys():
        print(f"  - {node_id}")


def demonstrate_export_validation():
    """Demonstrate export with validation."""

    print("\n=== Export with Validation ===")

    # Create a workflow with some issues
    workflow = Workflow(workflow_id="test_workflow", name="test_workflow")

    # Add an incomplete node
    csv_reader = CSVReaderNode(file_path="../data/test.csv", headers=True)
    workflow.add_node(node_id="reader", node_or_type=csv_reader)
    # Note: No configuration provided for reader

    # Try to export with validation
    config = ExportConfig(validate_output=True)
    exporter = WorkflowExporter(config)

    try:
        yaml_content = exporter.to_yaml(workflow)
        print("✓ Validation passed")
    except Exception as e:
        print(f"✗ Validation failed: {e}")

    # Export without validation
    config = ExportConfig(validate_output=False)
    exporter = WorkflowExporter(config)

    yaml_content = exporter.to_yaml(workflow)
    output_path = "../data/exports/unvalidated_workflow.yaml"
    with open(output_path, "w") as f:
        f.write(yaml_content)

    print(f"✓ Unvalidated workflow exported to: {output_path}")


def demonstrate_workflow_execution_and_export():
    """Demonstrate executing a workflow and then exporting it."""

    print("\n=== Execute and Export ===")

    workflow = create_sample_workflow()

    # Create sample data
    sample_data = [
        {"customer_id": 1, "name": "John Doe", "age": 45, "income": 85000},
        {"customer_id": 2, "name": "Jane Smith", "age": 65, "income": 120000},
        {"customer_id": 3, "name": "Bob Johnson", "age": 35, "income": 65000},
    ]

    # Write sample data
    Path("../data").mkdir(exist_ok=True)
    with open("../data/customers.csv", "w") as f:
        f.write("customer_id,name,age,income\n")
        for record in sample_data:
            f.write(
                f"{record['customer_id']},{record['name']},{record['age']},{record['income']}\n"
            )

    # Execute workflow
    runner = LocalRuntime(debug=True)
    results, run_id = runner.execute(workflow)

    print(f"✓ Workflow executed successfully (run_id: {run_id})")

    # Export the executed workflow
    exporter = WorkflowExporter()

    # Add execution metadata
    workflow.metadata.last_run_id = run_id
    workflow.metadata.last_run_time = datetime.now().isoformat()

    # Export with execution info
    yaml_content = exporter.to_yaml(workflow)

    output_path = "../data/exports/executed_workflow.yaml"
    with open(output_path, "w") as f:
        f.write(yaml_content)

    print(f"✓ Executed workflow exported to: {output_path}")


def main():
    """Main entry point for export examples."""

    print("=== Kailash Export Workflow Examples ===\n")

    # Create necessary directories
    for dir_path in [
        "../data/exports",
        "../data/exports/minimal",
        "../data/exports/standard",
        "../data/exports/kubernetes",
        "../data/exports/docker",
    ]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    examples = [
        ("Basic Export", demonstrate_basic_export),
        ("Export with Configuration", demonstrate_export_with_config),
        ("Kubernetes Manifest Export", demonstrate_manifest_export),
        ("Custom Node Mapping", demonstrate_custom_node_mapping),
        ("Template-based Export", demonstrate_template_export),
        ("Partial Export", demonstrate_partial_export),
        ("Export with Validation", demonstrate_export_validation),
        ("Execute and Export", demonstrate_workflow_execution_and_export),
    ]

    for name, example_func in examples:
        print(f"\n{'='*50}")
        print(f"Running: {name}")
        print("=" * 50)

        try:
            example_func()
        except Exception as e:
            print(f"Example failed: {e}")
            import traceback

            traceback.print_exc()

    print("\n=== All export examples completed ===")
    print("\nExported files created in the '../data/exports' directory")

    return 0


if __name__ == "__main__":
    sys.exit(main())
