# -*- coding: utf-8 -*-
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from kailash.nodes.base import Node, NodeMetadata, NodeParameter
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReader

sample_directory = Path("tests/sample_data")

# CSV Node (pre-created)
csv_reader_node = CSVReader(
    metadata=NodeMetadata(
        id="csv_node_1",
        name="customer_value_csv_read_node",
        description="Read customer value data from csv",
        version="1.0",
        author="Esperie",
        tags={"csv", "data"},
    ),
    file_path=sample_directory / "customer_value.csv",
    headers=True,
    delimiter=",",
)

result_from_reusable_csv_node = csv_reader_node.execute()

# Custom CSV Node creation


class CustomCSVNode(Node):
    # Input parameters (for automatic validation)
    def get_parameters(self) -> Dict[str, NodeParameter]:
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
    def get_output_schema(self) -> Dict[str, NodeParameter]:
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
    ) -> Dict[str, Any]:

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
    file_path=sample_directory / "customer_value.csv",
    headers=True,
    delimiter=",",
)

result_from_custom_csv_node = csv_reader_node.execute()

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
    df = pd.DataFrame(data)
    return {"filtered_data": df[df[column_name] > threshold].to_dict(orient="records")}


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

    def get_parameters(self) -> Dict[str, NodeParameter]:
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

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "filtered_data": NodeParameter(
                name="filtered_data",
                type=list,
                required=True,
                description="Filtered data records",
            )
        }

    def run(self, data: list, column_name: str, threshold: float) -> Dict[str, Any]:
        """Filter data based on threshold and return filtered data."""
        df = pd.DataFrame(data)
        filtered_df = df[df[column_name] > threshold]

        return {"filtered_data": filtered_df.to_dict(orient="records")}


filter_node = FilterNode(
    metadata=NodeMetadata(
        id="filter_node_1",
        name="filter_total_claims_node",
        description="Filter total claims above a threshold",
        version="1.0",
        author="Esperie",
        tags={"csv", "data"},
    ),
    data=result_from_custom_csv_node["data"],
    column_name="Total Claim Amount",
    threshold=1000.0,
)

filter_node.execute()
