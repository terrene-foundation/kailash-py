"""Basic example showing how to connect CSV node to Python node."""

from pathlib import Path
from typing import Any, Dict

import pandas as pd

from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data import CSVReader

# Setup paths
sample_directory = Path("../data")

# Method 1: Using pre-built CSVReader node
csv_reader_node = CSVReader(
    file_path=sample_directory / "customer_value.csv", headers=True, delimiter=","
)

# Execute CSV reader
csv_result = csv_reader_node.execute()
print(f"Loaded {len(csv_result['data'])} records from CSV")

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


def custom_filter(data: list, column_name: str, threshold: float) -> Dict[str, Any]:
    """Filter data based on threshold."""
    df = pd.DataFrame(data)

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
filter_result = filter_node.execute(
    data=csv_result["data"], column_name="Total Claim Amount", threshold=1000.0
)

print(f"Filtered to {len(filter_result['filtered_data'])} records")


# Method 4: Chain multiple operations
def summarize_by_group(data: list, group_col: str, value_col: str) -> Dict[str, Any]:
    """Summarize data by group."""
    df = pd.DataFrame(data)
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
summary_result = summary_node.execute(
    data=filter_result["filtered_data"],
    group_col="Customer",
    value_col="Total Claim Amount",
)

print("\nSummary by customer:")
for customer, total in summary_result["summary"].items():
    print(f"  {customer}: ${total:,.2f}")
print(f"Total: ${summary_result['total']:,.2f}")


# Method 5: Direct execution without schemas (simpler but less validated)
def simple_stats(data: list, column: str) -> Dict[str, Any]:
    """Calculate simple statistics."""
    df = pd.DataFrame(data)
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
stats_result = stats_node.execute(data=csv_result["data"], column="Total Claim Amount")

print("\nStatistics for all data:")
print(f"  Mean: ${stats_result['mean']:,.2f}")
print(f"  Max: ${stats_result['max']:,.2f}")
print(f"  Min: ${stats_result['min']:,.2f}")
print(f"  Count: {stats_result['count']}")

# Create sample data if needed
if __name__ == "__main__":
    sample_dir = Path("../data")
    sample_dir.mkdir(parents=True, exist_ok=True)

    if not (sample_dir / "customer_value.csv").exists():
        # Create sample data
        data = pd.DataFrame(
            {
                "Customer": ["Alice", "Bob", "Charlie", "David", "Eve"] * 2,
                "Total Claim Amount": [1500, 800, 2500, 600, 1200] * 2,
                "Status": ["Active", "Active", "Inactive", "Active", "Active"] * 2,
            }
        )
        data.to_csv(sample_dir / "customer_value.csv", index=False)
        print("Created sample data\n")
