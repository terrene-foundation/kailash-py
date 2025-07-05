#!/usr/bin/env python3
"""
Financial Data Processor - Simple Working Example
================================================

This simplified version demonstrates the core pattern of using
existing nodes instead of PythonCodeNode for financial workflows.

This example focuses on demonstrating the pattern without
complex configuration.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
)

from kailash import Workflow
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import RESTClientNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.logic import SwitchNode
from kailash.nodes.transform import FilterNode
from kailash.runtime.local import LocalRuntime


def create_financial_processor_workflow() -> Workflow:
    """Create a simple financial processing workflow using best practices."""
    workflow = Workflow(
        workflow_id="financial_processor_simple",
        name="financial_processor_demo",
        description="Simple financial transaction processing - no PythonCodeNode",
    )

    # Read transaction data from CSV
    csv_reader = CSVReaderNode(file_path="/tmp/transactions.csv")
    workflow.add_node("transaction_reader", csv_reader)

    # Validate transactions using FilterNode
    valid_filter = FilterNode()
    workflow.add_node("valid_filter", valid_filter)
    workflow.connect("transaction_reader", "valid_filter", mapping={"data": "data"})

    # Route high-value transactions
    value_router = SwitchNode()
    workflow.add_node("value_router", value_router)
    workflow.connect(
        "valid_filter", "value_router", mapping={"filtered_data": "input_data"}
    )

    # Process high-value transactions with LLM
    fraud_detector = LLMAgentNode()
    workflow.add_node("fraud_detector", fraud_detector)
    workflow.connect(
        "value_router",
        "fraud_detector",
        condition="true_output",
        mapping={"true_output": "messages"},
    )

    # Send alerts via REST API
    alert_sender = RESTClientNode()
    workflow.add_node("alert_sender", alert_sender)
    workflow.connect("fraud_detector", "alert_sender", mapping={"response": "data"})

    # Write results to CSV
    result_writer = CSVWriterNode(file_path="/tmp/processed_transactions.csv")
    workflow.add_node("result_writer", result_writer)
    workflow.connect(
        "value_router",
        "result_writer",
        condition="false_output",
        mapping={"false_output": "data"},
    )

    return workflow


def main():
    """Execute the simple financial processor workflow."""
    print("Financial Data Processor - Simple Demo")
    print("=" * 50)
    print("Demonstrates using existing nodes instead of PythonCodeNode")
    print()

    # Create workflow
    workflow = create_financial_processor_workflow()

    # Set up runtime
    runtime = LocalRuntime()

    # Create sample data
    sample_data = """transaction_id,amount,currency,account_id,risk_score
TX001,50000,USD,ACC-12345,75
TX002,1500,USD,ACC-67890,20
TX003,25000,EUR,ACC-11111,65
TX004,750,GBP,ACC-22222,10
TX005,100000,USD,ACC-33333,85"""

    # Write sample data
    with open("/tmp/transactions.csv", "w") as f:
        f.write(sample_data)

    # Configure parameters
    parameters = {
        "transaction_reader": {"file_path": "/tmp/transactions.csv"},
        "valid_filter": {"field": "amount", "operator": ">", "value": 0},
        "value_router": {"condition_field": "amount", "operator": ">", "value": 10000},
        "fraud_detector": {
            "provider": "openai",
            "model": "gpt-3.5-turbo",
            "system_prompt": "Analyze transactions for fraud risk. Return JSON with risk assessment.",
            "api_key": os.getenv("OPENAI_API_KEY", "demo-key"),
        },
        "alert_sender": {
            "url": os.getenv("ALERT_API", "https://api.example.com") + "/alerts",
            "method": "POST",
            "headers": {"Authorization": f"Bearer {os.getenv('API_KEY', 'demo-key')}"},
        },
        "result_writer": {"file_path": "/tmp/processed_transactions.csv"},
    }

    try:
        # Execute workflow
        result, run_id = runtime.execute(workflow, parameters=parameters)

        print("✓ Workflow completed successfully!")
        print(f"  Run ID: {run_id}")
        print("  Processed transactions written to: /tmp/processed_transactions.csv")
        print()
        print("Key Pattern Demonstrated:")
        print("- CSVReaderNode for data input (not PythonCodeNode)")
        print("- FilterNode for validation (not PythonCodeNode)")
        print("- SwitchNode for routing (not PythonCodeNode)")
        print("- LLMAgentNode for ML processing (not PythonCodeNode)")
        print("- RESTClientNode for API calls (not PythonCodeNode)")
        print("- CSVWriterNode for output (not PythonCodeNode)")

    except Exception as e:
        print(f"✗ Error executing workflow: {str(e)}")
        print("\nNote: This is a demonstration of the pattern.")
        print("In production, ensure all API keys and endpoints are configured.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
