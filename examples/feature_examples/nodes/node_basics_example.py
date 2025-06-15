#!/usr/bin/env python3
"""
Node Basics Test - Docker Infrastructure Pattern

This example demonstrates:
1. Node creation and configuration patterns
2. In-memory data processing (Docker-ready)
3. Custom node development
4. Production-ready data handling

Prerequisites:
- Docker infrastructure running: docker-compose -f docker/docker-compose.sdk-dev.yml up -d
"""

from typing import Any

import pandas as pd

from kailash.nodes.base import Node, NodeMetadata, NodeParameter
from kailash.nodes.code import PythonCodeNode

# Create test fixture data inline (Docker infrastructure pattern)
test_customers = pd.DataFrame(
    {
        "id": [1, 2, 3, 4, 5],
        "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "age": [30, 25, 35, 28, 32],
        "city": ["New York", "San Francisco", "Chicago", "Boston", "Seattle"],
        "status": ["active", "active", "inactive", "active", "active"],
    }
)

print("🐳 Node Basics Test - Docker Infrastructure Pattern")
print("=" * 60)
print(f"📊 Using in-memory data with {len(test_customers)} customer records")
print(f"   Data shape: {test_customers.shape}")
print(f"   Columns: {list(test_customers.columns)}")

# Demonstrate node creation with in-memory data
print("\n📝 Node Creation Patterns:")

# Custom CSV Node creation


class CustomCSVNode(Node):
    # Input parameters (for automatic validation)
    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to the CSV file",
            ),
            "headers": NodeParameter(
                name="headers",
                type=bool,
                required=True,
                default=True,
                description="Whether the CSV file has headers",
            ),
            "delimiter": NodeParameter(
                name="delimiter",
                type=str,
                required=True,
                default=",",
                description="Delimiter used in the CSV file",
            ),
        }

    # Output parameters (for automatic validation)
    def get_output_schema(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Dictionary containing the CSV data",
            )
        }

    # Code to run when the node is executed
    def run(
        self, file_path: str, headers: bool = True, delimiter: str = ","
    ) -> dict[str, Any]:

        # Read the CSV file
        data = pd.read_csv(
            file_path, header=0 if headers else None, delimiter=delimiter
        )

        return {"data": data.to_dict(orient="records")}


csv_reader_node = CustomCSVNode(
    metadata=NodeMetadata(
        id="csv_node_1",
        name="customer_value_csv_read_node",
        description="Read customer value data from csv",
        version="1.0",
        author="Esperie",
        tags={"csv", "data"},
    ),
    # Note: In production, use Docker PostgreSQL/MongoDB
    # For testing, we'll use in-memory data simulation
)

# Simulate CSV reader result with our test data
result_from_custom_csv_node = {
    "data": test_customers.to_dict("records"),
    "success": True,
}
print(f"✅ Custom node simulation: {len(result_from_custom_csv_node['data'])} records")

# Python Node
input_schema = {
    "data": NodeParameter(
        name="data",
        type=list,  # Not pd.DataFrame
        required=True,
        description="List of data records",
    ),
    "column_name": NodeParameter(
        name="column_name",
        type=str,
        required=True,
        description="Column name to filter on",
    ),
    "threshold": NodeParameter(
        name="threshold",
        type=float,  # Not str - needs to be numeric for comparison
        required=True,
        description="Threshold value for filtering",
    ),
}

output_schema = {
    "filtered_data": NodeParameter(
        name="filtered_data",
        type=list,
        required=True,
        description="Filtered data records",
    )
}


def custom_filter(data: list, column_name: str, threshold: float) -> dict[str, Any]:
    """Filter data by column threshold (Docker infrastructure ready)."""
    df = pd.DataFrame(data)

    # Ensure column exists
    if column_name not in df.columns:
        available_cols = list(df.columns)
        return {
            "error": f"Column '{column_name}' not found. Available: {available_cols}",
            "filtered_data": [],
        }

    filtered_df = df[df[column_name] > threshold]
    return {"filtered_data": filtered_df.to_dict(orient="records")}


node = PythonCodeNode.from_function(
    func=custom_filter,
    name="threshold_filter",
    description="Filter data based on threshold",
    input_schema=input_schema,
    output_schema=output_schema,
)

node.execute(
    data=result_from_custom_csv_node["data"],
    column_name="Total Claim Amount",
    threshold=1000.0,
)  # Automatic type conversion if possible

node.execute_code(
    inputs={
        "data": result_from_custom_csv_node["data"],
        "column_name": "Total Claim Amount",
        "threshold": 1000.0,
    }
)


# We can also create a CustomNode with the python function under in run
class FilterNode(Node):
    """Node to filter data based on a threshold."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="List of data records",
            ),
            "column_name": NodeParameter(
                name="column_name",
                type=str,
                required=True,
                description="Column name to filter on",
            ),
            "threshold": NodeParameter(
                name="threshold",
                type=float,
                required=True,
                description="Threshold value for filtering",
            ),
        }

    def get_output_schema(self) -> dict[str, NodeParameter]:
        return {
            "filtered_data": NodeParameter(
                name="filtered_data",
                type=list,
                required=True,
                description="Filtered data records",
            )
        }

    def run(self, data: list, column_name: str, threshold: float) -> dict[str, Any]:
        """Filter data based on threshold and return filtered data."""
        df = pd.DataFrame(data)
        filtered_df = df[df[column_name] > threshold]

        return {"filtered_data": filtered_df.to_dict(orient="records")}


# Example: Create and run filter node with test data
filter_node = FilterNode(
    metadata=NodeMetadata(
        id="filter_node_1",
        name="filter_age_node",
        description="Filter customers by age threshold",
        version="1.0",
        author="Esperie",
        tags={"filter", "data"},
    ),
)

# Run with test data (Docker infrastructure pattern)
filter_result = filter_node.execute(
    data=result_from_custom_csv_node["data"], column_name="age", threshold=30.0
)

print(
    f"\n🔍 Filter Results: Found {len(filter_result.get('filtered_data', []))} customers over 30"
)
print("✅ Node basics test completed successfully with Docker infrastructure pattern!")
print("🐳 Ready for production deployment with containerized services")
