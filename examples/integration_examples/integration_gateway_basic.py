"""Basic Multi-Workflow Gateway Example.

This example demonstrates a simple gateway setup with two workflows:
1. Data processing workflow
2. Reporting workflow

The gateway provides unified access to both workflows through a single API.
"""

from pathlib import Path

from kailash.api.gateway import WorkflowAPIGateway
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.transform import DataTransformer
from kailash.workflow import Workflow

# Setup paths
DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


def create_data_processing_workflow() -> Workflow:
    """Create a simple data processing workflow."""
    workflow = Workflow(
        workflow_id="data_processor_001",
        name="Data Processor",
        description="Process CSV data and calculate totals",
    )

    # Read CSV data - parameters will be provided at runtime
    reader = CSVReaderNode()
    workflow.add_node("read_data", reader)

    # Transform data - add a simple calculation
    transformer = DataTransformer(
        transform_fn=lambda df: df.assign(
            total_value=(
                df["quantity"] * df["price"]
                if "quantity" in df and "price" in df
                else 0
            )
        )
    )
    workflow.add_node("calculate_total", transformer)

    # Write results
    writer = CSVWriterNode()
    workflow.add_node("save_results", writer)

    # Connect nodes
    workflow.add_edge("read_data", "calculate_total")
    workflow.add_edge("calculate_total", "save_results")

    return workflow


def create_reporting_workflow() -> Workflow:
    """Create a simple reporting workflow."""
    workflow = Workflow(
        workflow_id="reporter_001",
        name="Reporter",
        description="Generate summary reports from CSV data",
    )

    # Read data - parameters will be provided at runtime
    reader = CSVReaderNode()
    workflow.add_node("load_data", reader)

    # Generate summary
    summarizer = DataTransformer(
        transform_fn=lambda df: {
            "total_rows": len(df),
            "columns": list(df.columns),
            "summary": df.describe().to_dict() if hasattr(df, "describe") else {},
        }
    )
    workflow.add_node("create_summary", summarizer)

    # Connect nodes
    workflow.add_edge("load_data", "create_summary")

    return workflow


def main():
    """Run the basic gateway example."""
    print("=== Basic Multi-Workflow Gateway Example ===\n")

    # Create gateway
    gateway = WorkflowAPIGateway(
        title="Basic Workflow Gateway",
        description="Simple gateway with data processing and reporting",
        version="1.0.0",
    )

    # Register workflows
    print("Registering workflows...")

    gateway.register_workflow(
        "process",
        create_data_processing_workflow(),
        description="Process CSV data and calculate totals",
        tags=["data", "processing"],
    )

    gateway.register_workflow(
        "report",
        create_reporting_workflow(),
        description="Generate reports from CSV data",
        tags=["reporting", "analytics"],
    )

    print("✓ Registered 2 workflows\n")

    # Display available endpoints
    print("Available Endpoints:")
    print("-" * 50)
    print("Gateway Info:    http://localhost:8000/")
    print("List Workflows:  http://localhost:8000/workflows")
    print("Health Check:    http://localhost:8000/health")
    print()

    for name in ["process", "report"]:
        print(f"{name.upper()} Workflow:")
        print(f"  Execute:       http://localhost:8000/{name}/execute")
        print(f"  Info:          http://localhost:8000/{name}/workflow/info")
        print(f"  Docs:          http://localhost:8000/{name}/docs")
        print()

    # Example usage
    print("Example API Calls:")
    print("-" * 50)
    print("# Process data")
    print("curl -X POST http://localhost:8000/process/execute \\")
    print('  -H "Content-Type: application/json" \\')
    print(f'  -d \'{{"read_data": {{"file_path": "{DATA_DIR}/sample_data.csv"}}, ')
    print(
        f'       "save_results": {{"file_path": "{OUTPUT_DIR}/processed_data.csv"}}}}\''
    )
    print()
    print("# Generate report")
    print("curl -X POST http://localhost:8000/report/execute \\")
    print('  -H "Content-Type: application/json" \\')
    print(
        f'  -d \'{{"load_data": {{"file_path": "{OUTPUT_DIR}/processed_data.csv"}}}}\''
    )

    return gateway


if __name__ == "__main__":
    gateway = main()

    print("\n\nStarting gateway server on http://localhost:8000")
    print("Press Ctrl+C to stop\n")

    # Note: In a real scenario, you would run:
    # gateway.run(host="0.0.0.0", port=8000)

    # For testing, we'll just show the setup is correct
    print(
        "Gateway setup complete! In production, run gateway.run() to start the server."
    )
