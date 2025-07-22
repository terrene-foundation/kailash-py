#!/usr/bin/env python3
"""
Financial Data Processor - Minimal Working Example
=================================================

This minimal example shows the pattern without complex configuration.
It demonstrates using existing nodes instead of PythonCodeNode.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
)

# Auto-detect SDK development environment
if os.getenv("SDK_DEV_MODE") == "true":
    env_file = Path(__file__).parent.parent.parent.parent / ".env.sdk-dev"
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file)
        print("✓ Using SDK development environment")

from kailash import Workflow
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.transform import FilterNode
from kailash.runtime.local import LocalRuntime


def main():
    """Execute minimal financial processor workflow."""
    print("Financial Data Processor - Minimal Example")
    print("=" * 50)
    print()

    # Create sample data
    sample_data = """transaction_id,amount,currency,status
TX001,50000,USD,pending
TX002,1500,USD,approved
TX003,25000,EUR,pending
TX004,750,GBP,approved
TX005,100000,USD,pending"""

    # Write sample data
    with open("/tmp/transactions.csv", "w") as f:
        f.write(sample_data)

    # Create workflow
    workflow = Workflow(workflow_id="financial_minimal", name="minimal_demo")

    # Add nodes
    reader = CSVReaderNode(file_path="/tmp/transactions.csv")
    workflow.add_node("reader", reader)

    filter_node = FilterNode()
    workflow.add_node("filter", filter_node)

    writer = CSVWriterNode(file_path="/tmp/high_value.csv")
    workflow.add_node("writer", writer)

    # Connect nodes
    workflow.connect("reader", "filter", mapping={"data": "data"})
    workflow.connect("filter", "writer", mapping={"filtered_data": "data"})

    # Execute
    runtime = LocalRuntime()

    try:
        result, run_id = runtime.execute(
            workflow,
            parameters={"filter": {"field": "amount", "operator": ">", "value": 10000}},
        )

        print("✓ Workflow completed successfully!")
        print("  High-value transactions written to: /tmp/high_value.csv")
        print()
        print("Pattern demonstrated:")
        print("- CSVReaderNode → FilterNode → CSVWriterNode")
        print("- No PythonCodeNode needed!")

        # Show results
        with open("/tmp/high_value.csv") as f:
            print("\nHigh-value transactions:")
            print(f.read())

    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
