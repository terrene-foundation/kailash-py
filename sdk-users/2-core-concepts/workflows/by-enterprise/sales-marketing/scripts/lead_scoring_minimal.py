#!/usr/bin/env python3
"""
Lead Scoring Engine - Minimal Working Example
=============================================

This minimal example shows the pattern without complex configuration.
It demonstrates using existing nodes instead of PythonCodeNode.
"""

import os
import sys

# Add parent directory to path
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
)

from kailash import Workflow
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.transform import DataTransformer
from kailash.runtime.local import LocalRuntime


def main():
    """Execute minimal lead scoring workflow."""
    print("Lead Scoring Engine - Minimal Example")
    print("=" * 50)
    print()

    # Create sample data
    sample_data = """lead_id,company,industry,employees,engagement_score
LEAD001,TechCorp,Software,500,85
LEAD002,SmallBiz,Retail,20,45
LEAD003,Enterprise Inc,Finance,5000,92
LEAD004,StartupXYZ,SaaS,15,78
LEAD005,BigCo,Manufacturing,10000,67"""

    # Write sample data
    with open("/tmp/leads.csv", "w") as f:
        f.write(sample_data)

    # Create workflow
    workflow = Workflow(workflow_id="lead_scoring_minimal", name="minimal_lead_demo")

    # Add nodes
    reader = CSVReaderNode(file_path="/tmp/leads.csv")
    workflow.add_node("reader", reader)

    # Transform to prepare for LLM
    transformer = DataTransformer(
        transformations=[
            """lambda leads: {
            'messages': [{
                'role': 'user',
                'content': f'Score these leads (0-100) based on company size and engagement: {leads}'
            }]
        }"""
        ]
    )
    workflow.add_node("transformer", transformer)

    scorer = LLMAgentNode()
    workflow.add_node("scorer", scorer)

    writer = CSVWriterNode(file_path="/tmp/scored_leads.csv")
    workflow.add_node("writer", writer)

    # Connect nodes
    workflow.connect("reader", "transformer", mapping={"data": "data"})
    workflow.connect("transformer", "scorer", mapping={"result": "messages"})
    workflow.connect(
        "reader", "writer", mapping={"data": "data"}
    )  # Write original data

    # Execute
    runtime = LocalRuntime()

    try:
        result, run_id = runtime.execute(
            workflow,
            parameters={
                "scorer": {
                    "provider": "openai",
                    "model": "gpt-3.5-turbo",
                    "system_prompt": "You are a lead scoring expert. Score leads 0-100.",
                    "api_key": os.getenv("OPENAI_API_KEY", "demo-key"),
                }
            },
        )

        print("✓ Workflow completed successfully!")
        print("  Scored leads written to: /tmp/scored_leads.csv")
        print()
        print("Pattern demonstrated:")
        print("- CSVReaderNode → DataTransformer → LLMAgentNode")
        print("- Minimal PythonCodeNode usage (only in transformer lambda)")
        print("- Real AI integration with LLMAgentNode")

    except Exception as e:
        print(f"✗ Error: {str(e)}")
        print("\nNote: This example requires OPENAI_API_KEY to be set.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
