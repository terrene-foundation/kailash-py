"""
Template: Simple API Integration
Purpose: Make basic API calls in a workflow
Use Case: Fetching data from external APIs

This template shows how to use HTTP nodes for API integration.
"""

from kailash.workflow.graph import Workflow
from kailash.nodes.api.http import HTTPRequestNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.writers import JSONWriterNode
from typing import Dict, Any
import os

# Configuration
API_URL = "https://api.example.com/data"  # Replace with your API
OUTPUT_FILE = "outputs/api_response.json"
API_KEY = os.getenv("API_KEY", "your-api-key")


def process_response(response: Dict) -> Dict[str, Any]:
    """Process the API response"""
    # Extract data from response
    if response.get("status_code") == 200:
        data = response.get("json", response.get("data", {}))

        # Process the data as needed
        processed = {
            "success": True,
            "record_count": len(data) if isinstance(data, list) else 1,
            "data": data,
            "timestamp": response.get("headers", {}).get("date", "unknown"),
        }
    else:
        processed = {
            "success": False,
            "error": f"API returned status {response.get('status_code')}",
            "data": [],
        }

    return processed


def main():
    """Create and run API integration workflow"""
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    # Create workflow
    workflow = Workflow()

    # HTTP request node
    api_call = HTTPRequestNode(
        url=API_URL,
        method="GET",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    workflow.add_node("api_call", api_call)

    # Process response
    processor = PythonCodeNode.from_function(
        func=process_response, name="response_processor"
    )
    workflow.add_node("processor", processor)

    # Write output
    writer = JSONWriterNode(file_path=OUTPUT_FILE)
    workflow.add_node("writer", writer)

    # Connect nodes
    workflow.connect("api_call", "processor", {"response": "response"})
    workflow.connect("processor", "writer", {"data": "data"})

    # Run workflow
    try:
        results, run_id = workflow.run()
        print(f"API workflow completed! Run ID: {run_id}")
        print(f"Results saved to: {OUTPUT_FILE}")

        # Check if successful
        if "processor" in results:
            success = results["processor"].get("success", False)
            if success:
                count = results["processor"].get("record_count", 0)
                print(f"Successfully fetched {count} records")
            else:
                error = results["processor"].get("error", "Unknown error")
                print(f"API call failed: {error}")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
