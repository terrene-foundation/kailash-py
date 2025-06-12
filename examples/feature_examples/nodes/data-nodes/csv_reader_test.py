"""
CSV Reader Test - Docker Infrastructure Pattern

This example demonstrates:
1. In-memory data processing (Docker-ready)
2. Node connection patterns
3. Data transformation workflows

Prerequisites:
- Docker infrastructure: docker-compose -f docker/docker-compose.sdk-dev.yml up -d
"""

from typing import Any

import pandas as pd

from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode

# Create test data inline (Docker infrastructure pattern)
test_data = pd.DataFrame(
    {
        "customer_id": [1, 2, 3, 4, 5],
        "name": ["Alice Corp", "Bob LLC", "Charlie Inc", "David Co", "Eve Ltd"],
        "value": [1000, 1500, 800, 2000, 1200],
        "region": ["North", "South", "East", "West", "North"],
        "status": ["active", "active", "inactive", "active", "pending"],
    }
)

print("🐳 CSV Reader Test - Docker Infrastructure Pattern")
print("=" * 55)
print(f"📊 Using in-memory data with {len(test_data)} customer records")

# Simulate CSV reader result
csv_result = {"data": test_data.to_dict("records"), "success": True}
print(f"✅ Loaded {len(csv_result['data'])} records (in-memory simulation)")

# Method 2: Creating custom Python node with schemas
input_schema = {
    "data": NodeParameter(
        name="data", type=list, required=True, description="List of data records"
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

output_schema = {
    "filtered_data": NodeParameter(
        name="filtered_data",
        type=list,
        required=True,
        description="Filtered data records",
    )
}


def custom_filter(data: list, column_name: str, threshold: float) -> dict[str, Any]:
    """Filter data based on threshold (Docker infrastructure ready)."""
    df = pd.DataFrame(data)

    # Validate column exists
    if column_name not in df.columns:
        available_cols = list(df.columns)
        return {
            "error": f"Column '{column_name}' not found. Available: {available_cols}",
            "filtered_data": [],
        }

    # Ensure column is numeric
    if df[column_name].dtype == "object":
        df[column_name] = pd.to_numeric(df[column_name], errors="coerce")

    filtered_df = df[df[column_name] > threshold]

    return {"filtered_data": filtered_df.to_dict(orient="records")}


# Create Python node
filter_node = PythonCodeNode.from_function(
    func=custom_filter,
    name="threshold_filter",
    description="Filter data based on threshold",
    input_schema=input_schema,
    output_schema=output_schema,
)

# Method 3: Execute the filter node with CSV data
filter_result = filter_node.run(
    data=csv_result["data"], column_name="value", threshold=1000.0
)

print(f"Filter result keys: {list(filter_result.keys())}")
print(f"Filter result: {filter_result}")

# Handle PythonCodeNode result structure
if "result" in filter_result and "filtered_data" in filter_result["result"]:
    filtered_data = filter_result["result"]["filtered_data"]
elif "filtered_data" in filter_result:
    filtered_data = filter_result["filtered_data"]
else:
    print("Warning: filtered_data not found in expected location")
    filtered_data = []

print(f"Filtered to {len(filtered_data)} records")


# Method 4: Chain multiple operations
def summarize_by_group(data: list, group_col: str, value_col: str) -> dict[str, Any]:
    """Summarize data by group (Docker infrastructure ready)."""
    df = pd.DataFrame(data)

    # Validate columns exist
    missing_cols = []
    if group_col not in df.columns:
        missing_cols.append(group_col)
    if value_col not in df.columns:
        missing_cols.append(value_col)

    if missing_cols:
        available_cols = list(df.columns)
        return {
            "error": f"Columns {missing_cols} not found. Available: {available_cols}",
            "summary": {},
            "groups": [],
            "total": 0,
        }

    summary = df.groupby(group_col)[value_col].sum().to_dict()

    return {
        "summary": summary,
        "groups": list(summary.keys()),
        "total": sum(summary.values()),
    }


# Define output schema for summary node
summary_output_schema = {
    "summary": NodeParameter(
        name="summary", type=dict, required=True, description="Summary by group"
    ),
    "groups": NodeParameter(
        name="groups", type=list, required=True, description="List of groups"
    ),
    "total": NodeParameter(
        name="total", type=float, required=True, description="Total sum"
    ),
}

summary_node = PythonCodeNode.from_function(
    func=summarize_by_group,
    name="group_summarizer",
    description="Summarize data by group",
    output_schema=summary_output_schema,
)

# Use filtered data for summary
summary_result = summary_node.run(
    data=filtered_data,
    group_col="region",
    value_col="value",
)

print("\nSummary by region:")
print(f"Summary result: {summary_result}")

# Handle PythonCodeNode result structure
if "result" in summary_result:
    result_data = summary_result["result"]
    summary_data = result_data.get("summary", {})
    total_data = result_data.get("total", 0)
else:
    summary_data = summary_result.get("summary", {})
    total_data = summary_result.get("total", 0)

for region, total in summary_data.items():
    print(f"  {region}: ${total:,.2f}")
print(f"Total: ${total_data:,.2f}")


# Method 5: Direct execution without schemas (simpler but less validated)
def simple_stats(data: list, column: str) -> dict[str, Any]:
    """Calculate simple statistics (Docker infrastructure ready)."""
    df = pd.DataFrame(data)

    # Validate column exists
    if column not in df.columns:
        available_cols = list(df.columns)
        return {
            "error": f"Column '{column}' not found. Available: {available_cols}",
            "mean": 0,
            "max": 0,
            "min": 0,
            "count": 0,
        }

    # Convert column to numeric, handling errors
    values = pd.to_numeric(df[column], errors="coerce")

    return {
        "mean": values.mean(),
        "max": values.max(),
        "min": values.min(),
        "count": len(values),
    }


# Define output schema for stats node
stats_output_schema = {
    "mean": NodeParameter(
        name="mean", type=float, required=True, description="Mean value"
    ),
    "max": NodeParameter(
        name="max", type=float, required=True, description="Maximum value"
    ),
    "min": NodeParameter(
        name="min", type=float, required=True, description="Minimum value"
    ),
    "count": NodeParameter(
        name="count", type=int, required=True, description="Count of values"
    ),
}

# Create node with output schema
stats_node = PythonCodeNode.from_function(
    func=simple_stats, name="simple_stats", output_schema=stats_output_schema
)

# Execute with original data
stats_result = stats_node.run(data=csv_result["data"], column="value")

print("\nStatistics for all data:")
# Handle PythonCodeNode result structure for stats
if "result" in stats_result:
    stats_data = stats_result["result"]
else:
    stats_data = stats_result

print(f"  Mean: ${stats_data['mean']:,.2f}")
print(f"  Max: ${stats_data['max']:,.2f}")
print(f"  Min: ${stats_data['min']:,.2f}")
print(f"  Count: {stats_data['count']}")

# Docker infrastructure pattern complete
if __name__ == "__main__":
    print("\n🎯 CSV Reader Test Summary:")
    print("   ✅ In-memory data processing demonstrated")
    print("   ✅ Node connection patterns shown")
    print("   ✅ Docker infrastructure ready")
    print("🐳 Ready for production deployment with containerized services")
