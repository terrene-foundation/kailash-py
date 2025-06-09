#!/usr/bin/env python3
"""
REST API Integration Workflow
=============================

This script demonstrates REST API integration patterns with Kailash SDK:
1. Basic API calls with authentication
2. Rate limiting and retries
3. Data transformation and validation
4. Error handling and fallbacks

Key Features:
- Uses native REST client nodes
- Implements proper authentication
- Handles rate limiting
- Transforms API responses
"""

import os
import json
from typing import Dict, Any
from kailash import Workflow
from kailash.nodes.api import RESTClientNode, RateLimitedAPINode
from kailash.nodes.transform import DataTransformer, FilterNode
from kailash.nodes.data import CSVWriterNode
from kailash.runtime import LocalRuntime


def create_api_workflow() -> Workflow:
    """Create a REST API integration workflow."""
    workflow = Workflow(
        workflow_id="api_integration_001",
        name="rest_api_workflow",
        description="REST API integration with rate limiting"
    )
    
    # REST API client with rate limiting
    api_client = RateLimitedAPINode(
        id="api_client",
        base_url="https://api.example.com",
        timeout=30,
        requests_per_minute=60,
        max_retries=3
    )
    workflow.add_node("api_client", api_client)
    
    # Response transformer
    transformer = DataTransformer(
        id="response_transformer",
        transformations=[]  # Provided at runtime
    )
    workflow.add_node("response_transformer", transformer)
    workflow.connect("api_client", "response_transformer", mapping={"response": "data"})
    
    # Error filter
    error_filter = FilterNode(id="error_filter")
    workflow.add_node("error_filter", error_filter)
    workflow.connect("response_transformer", "error_filter", mapping={"result": "data"})
    
    # Save results
    writer = CSVWriterNode(
        id="result_writer",
        file_path="data/outputs/api_results.csv"
    )
    workflow.add_node("result_writer", writer)
    workflow.connect("error_filter", "result_writer", mapping={"filtered_data": "data"})
    
    return workflow


def create_simple_api_workflow() -> Workflow:
    """Create a simplified API workflow for testing."""
    workflow = Workflow(
        workflow_id="simple_api_001",
        name="simple_api_workflow",
        description="Simple API workflow without external calls"
    )
    
    # Mock API response
    mock_api = DataTransformer(
        id="mock_api",
        transformations=[
            """
# Simulate API response
api_response = {
    "status": "success",
    "data": [
        {
            "id": 1,
            "name": "Product A",
            "price": 29.99,
            "stock": 100,
            "category": "electronics"
        },
        {
            "id": 2,
            "name": "Product B",
            "price": 49.99,
            "stock": 50,
            "category": "electronics"
        },
        {
            "id": 3,
            "name": "Product C",
            "price": 19.99,
            "stock": 0,
            "category": "accessories"
        }
    ],
    "timestamp": "2024-01-15T10:30:00Z"
}
result = api_response
"""
        ]
    )
    workflow.add_node("mock_api", mock_api)
    
    # Debug transformer to see what mock_api returns
    debugger = DataTransformer(
        id="debugger",
        transformations=[
            """
import json
# Check if we have a 'result' key from DataTransformer
actual_data = result if 'result' in locals() else data
print(f"DEBUG: Type of actual_data: {type(actual_data)}")
if isinstance(actual_data, dict):
    print(f"DEBUG: Dict keys: {list(actual_data.keys())}")
    if 'data' in actual_data:
        print(f"DEBUG: Found 'data' key, type: {type(actual_data['data'])}")
        print(f"DEBUG: First product: {actual_data['data'][0] if actual_data['data'] else 'No products'}")
else:
    print(f"DEBUG: Not a dict, is {type(actual_data)}")
    
# Pass through the actual API response structure
result = actual_data
"""
        ]
    )
    workflow.add_node("debugger", debugger)
    # DataTransformer outputs "result", so map that to "data" for next node
    workflow.connect("mock_api", "debugger", mapping={"result": "data"})
    
    # Extract and transform data
    extractor = DataTransformer(
        id="data_extractor",
        transformations=[
            """
# Extract and enhance product data
# Debug: print data structure
print(f"DEBUG data type: {type(data)}")
print(f"DEBUG data content: {data}")

# data is the result dict from mock_api
products = data.get("data", []) if isinstance(data, dict) else data
enhanced = []

for product in products:
    enhanced.append({
        "id": product["id"],
        "name": product["name"],
        "price": product["price"],
        "stock": product["stock"],
        "category": product["category"],
        "in_stock": product["stock"] > 0,
        "price_tier": "high" if product["price"] > 40 else "mid" if product["price"] > 25 else "low"
    })

result = enhanced
"""
        ]
    )
    workflow.add_node("data_extractor", extractor)
    workflow.connect("debugger", "data_extractor", mapping={"result": "data"})
    
    # Filter in-stock items
    stock_filter = FilterNode(id="stock_filter")
    workflow.add_node("stock_filter", stock_filter)
    workflow.connect("data_extractor", "stock_filter", mapping={"result": "data"})
    
    # Calculate metrics
    metrics = DataTransformer(
        id="metrics_calculator",
        transformations=[
            """
# Calculate inventory metrics
total_value = 0
total_items = 0
categories = {}

for product in data:
    value = product["price"] * product["stock"]
    total_value += value
    total_items += product["stock"]
    
    cat = product["category"]
    if cat not in categories:
        categories[cat] = {"count": 0, "value": 0}
    categories[cat]["count"] += 1
    categories[cat]["value"] += value

result = [{
    "total_products": len(data),
    "total_inventory_value": round(total_value, 2),
    "total_items_in_stock": total_items,
    "avg_price": round(sum(p["price"] for p in data) / len(data), 2) if data else 0,
    "category_breakdown": str(categories)
}]
"""
        ]
    )
    workflow.add_node("metrics_calculator", metrics)
    workflow.connect("stock_filter", "metrics_calculator", mapping={"filtered_data": "data"})
    
    # Write metrics
    writer = CSVWriterNode(
        id="metrics_writer",
        file_path="data/outputs/inventory_metrics.csv"
    )
    workflow.add_node("metrics_writer", writer)
    workflow.connect("metrics_calculator", "metrics_writer", mapping={"result": "data"})
    
    return workflow


def run_api_workflow():
    """Run the API workflow with rate limiting."""
    workflow = create_api_workflow()
    runtime = LocalRuntime()
    
    parameters = {
        "api_client": {
            "endpoint": "/v1/products",
            "method": "GET",
            "headers": {
                "Authorization": "Bearer YOUR_API_KEY",
                "Accept": "application/json"
            },
            "params": {
                "limit": 100,
                "offset": 0
            }
        },
        "response_transformer": {
            "transformations": [
                """
# Transform API response
if isinstance(data, dict) and "items" in data:
    result = data["items"]
elif isinstance(data, list):
    result = data
else:
    result = []
"""
            ]
        },
        "error_filter": {
            "field": "status",
            "operator": "!=",
            "value": "error"
        }
    }
    
    try:
        print("Running API workflow...")
        result, run_id = runtime.execute(workflow, parameters=parameters)
        print("API integration complete!")
        return result
    except Exception as e:
        print(f"API workflow failed: {str(e)}")
        raise


def run_simple_api():
    """Run simplified API workflow."""
    workflow = create_simple_api_workflow()
    runtime = LocalRuntime()
    
    parameters = {
        "mock_api": {
            "data": []  # Empty data to ensure 'data' variable exists
        },
        "debugger": {},
        "data_extractor": {},
        "stock_filter": {
            "field": "in_stock",
            "operator": "==",
            "value": True
        },
        "metrics_calculator": {}
    }
    
    try:
        print("Running simple API workflow...")
        result, run_id = runtime.execute(workflow, parameters=parameters)
        print("Workflow complete!")
        print(f"Metrics written to: data/outputs/inventory_metrics.csv")
        return result
    except Exception as e:
        print(f"Workflow failed: {str(e)}")
        raise


def main():
    """Main entry point."""
    import sys
    
    # Create output directory
    os.makedirs("data/outputs", exist_ok=True)
    
    if len(sys.argv) > 1 and sys.argv[1] == "real":
        # Run with real API (requires API key)
        print("Note: Real API workflow requires valid API credentials")
        run_api_workflow()
    else:
        # Run simple version
        run_simple_api()


if __name__ == "__main__":
    main()