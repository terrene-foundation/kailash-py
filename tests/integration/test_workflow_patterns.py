"""Integration tests for various workflow patterns."""

import json
import tempfile
from pathlib import Path

import pytest
from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data import (
    CSVReaderNode,
    CSVWriterNode,
    JSONReaderNode,
    JSONWriterNode,
)
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.runtime.local import LocalRuntime


class TestWorkflowPatterns:
    """Test various workflow patterns work correctly."""

    def test_simple_etl_workflow(self, tmp_path):
        """Test a simple ETL workflow: Read -> Transform -> Write."""
        # Create test data
        input_file = tmp_path / "input.csv"
        with open(input_file, "w") as f:
            f.write("name,value\n")
            f.write("Alice,100\n")
            f.write("Bob,200\n")
            f.write("Charlie,150\n")

        output_file = tmp_path / "output.csv"

        # Build workflow
        workflow = Workflow("etl-test", "ETL Test")

        # Add nodes
        reader = CSVReaderNode(file_path=str(input_file))

        def transform_data(data):
            """Add 10% to each value."""
            for record in data:
                if "value" in record:
                    record["value"] = float(record["value"]) * 1.1
            return data

        transformer = PythonCodeNode.from_function(
            func=transform_data,
            name="transformer",
            input_schema={"data": NodeParameter(name="data", type=list, required=True)},
        )

        writer = CSVWriterNode(file_path=str(output_file))

        workflow.add_node("reader", reader)
        workflow.add_node("transformer", transformer)
        workflow.add_node("writer", writer)

        # Connect nodes
        workflow.connect("reader", "transformer", mapping={"data": "data"})
        workflow.connect("transformer", "writer", mapping={"result": "data"})

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        # Verify
        assert output_file.exists()
        assert results["writer"]["rows_written"] == 3

        # Check transformed data
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 4  # Header + 3 rows
            # Values should be increased by 10%
            assert "110" in lines[1]  # Alice's value
            assert "220" in lines[2]  # Bob's value
            assert "165" in lines[3]  # Charlie's value

    def test_conditional_workflow(self, tmp_path):
        """Test workflow with conditional routing."""
        # Create test data
        input_file = tmp_path / "customers.json"
        with open(input_file, "w") as f:
            json.dump(
                [
                    {"name": "Alice", "value": 500, "status": "active"},
                    {"name": "Bob", "value": 100, "status": "inactive"},
                    {"name": "Charlie", "value": 300, "status": "active"},
                ],
                f,
            )

        high_value_file = tmp_path / "high_value.json"
        low_value_file = tmp_path / "low_value.json"

        # Build workflow
        workflow = Workflow("conditional-test", "Conditional Test")

        # Add nodes
        reader = JSONReaderNode(file_path=str(input_file))

        def evaluate_customer(data):
            """Evaluate customer and determine routing."""
            high_value = []
            low_value = []

            for customer in data:
                if (
                    customer.get("status") == "active"
                    and customer.get("value", 0) >= 300
                ):
                    high_value.append(customer)
                else:
                    low_value.append(customer)

            return {
                "high_value": high_value,
                "low_value": low_value,
                "high_count": len(high_value),
                "low_count": len(low_value),
            }

        evaluator = PythonCodeNode.from_function(
            func=evaluate_customer,
            name="evaluator",
            input_schema={"data": NodeParameter(name="data", type=list, required=True)},
        )

        # Process high value customers
        def process_high_value(customers):
            """Add premium benefits."""
            for customer in customers:
                customer["tier"] = "premium"
                customer["discount"] = 0.2
            return customers

        high_processor = PythonCodeNode.from_function(
            func=process_high_value,
            name="high_processor",
            input_schema={
                "customers": NodeParameter(name="customers", type=list, required=True)
            },
        )

        # Process low value customers
        def process_low_value(customers):
            """Add standard benefits."""
            for customer in customers:
                customer["tier"] = "standard"
                customer["discount"] = 0.05
            return customers

        low_processor = PythonCodeNode.from_function(
            func=process_low_value,
            name="low_processor",
            input_schema={
                "customers": NodeParameter(name="customers", type=list, required=True)
            },
        )

        high_writer = JSONWriterNode(file_path=str(high_value_file))
        low_writer = JSONWriterNode(file_path=str(low_value_file))

        # Add nodes to workflow
        workflow.add_node("reader", reader)
        workflow.add_node("evaluator", evaluator)
        workflow.add_node("high_processor", high_processor)
        workflow.add_node("low_processor", low_processor)
        workflow.add_node("high_writer", high_writer)
        workflow.add_node("low_writer", low_writer)

        # Connect nodes
        workflow.connect("reader", "evaluator", mapping={"data": "data"})
        workflow.connect(
            "evaluator", "high_processor", mapping={"result.high_value": "customers"}
        )
        workflow.connect(
            "evaluator", "low_processor", mapping={"result.low_value": "customers"}
        )
        workflow.connect("high_processor", "high_writer", mapping={"result": "data"})
        workflow.connect("low_processor", "low_writer", mapping={"result": "data"})

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        # Verify
        assert high_value_file.exists()
        assert low_value_file.exists()

        # Check high value customers
        with open(high_value_file) as f:
            high_value_data = json.load(f)
            assert len(high_value_data) == 2  # Alice and Charlie
            assert all(c["tier"] == "premium" for c in high_value_data)
            assert all(c["discount"] == 0.2 for c in high_value_data)

        # Check low value customers
        with open(low_value_file) as f:
            low_value_data = json.load(f)
            assert len(low_value_data) == 1  # Bob
            assert all(c["tier"] == "standard" for c in low_value_data)
            assert all(c["discount"] == 0.05 for c in low_value_data)

    def test_parallel_processing_workflow(self, tmp_path):
        """Test workflow with parallel branches."""
        # Create test data
        input_file = tmp_path / "data.json"
        with open(input_file, "w") as f:
            json.dump({"values": [1, 2, 3, 4, 5], "multiplier": 2}, f)

        output_file = tmp_path / "results.json"

        # Build workflow
        workflow = Workflow("parallel-test", "Parallel Test")

        # Add nodes
        reader = JSONReaderNode(file_path=str(input_file))

        # Branch 1: Calculate sum
        def calculate_sum(values):
            """Calculate sum of values."""
            return {"sum": sum(values)}

        sum_calculator = PythonCodeNode.from_function(
            func=calculate_sum,
            name="sum_calculator",
            input_schema={
                "values": NodeParameter(name="values", type=list, required=True)
            },
        )

        # Branch 2: Calculate product
        def calculate_product(values, multiplier):
            """Multiply each value."""
            return {"products": [v * multiplier for v in values]}

        product_calculator = PythonCodeNode.from_function(
            func=calculate_product,
            name="product_calculator",
            input_schema={
                "values": NodeParameter(name="values", type=list, required=True),
                "multiplier": NodeParameter(name="multiplier", type=int, required=True),
            },
        )

        # Branch 3: Calculate statistics
        def calculate_stats(values):
            """Calculate statistics."""
            return {
                "mean": sum(values) / len(values) if values else 0,
                "max": max(values) if values else 0,
                "min": min(values) if values else 0,
                "count": len(values),
            }

        stats_calculator = PythonCodeNode.from_function(
            func=calculate_stats,
            name="stats_calculator",
            input_schema={
                "values": NodeParameter(name="values", type=list, required=True)
            },
        )

        # Merge results
        def merge_results(sum_result, product_result, stats_result):
            """Merge all results."""
            return {
                "sum": sum_result["sum"],
                "products": product_result["products"],
                "statistics": stats_result,
            }

        merger = PythonCodeNode.from_function(
            func=merge_results,
            name="merger",
            input_schema={
                "sum_result": NodeParameter(
                    name="sum_result", type=dict, required=True
                ),
                "product_result": NodeParameter(
                    name="product_result", type=dict, required=True
                ),
                "stats_result": NodeParameter(
                    name="stats_result", type=dict, required=True
                ),
            },
        )

        writer = JSONWriterNode(file_path=str(output_file))

        # Add nodes to workflow
        workflow.add_node("reader", reader)
        workflow.add_node("sum_calculator", sum_calculator)
        workflow.add_node("product_calculator", product_calculator)
        workflow.add_node("stats_calculator", stats_calculator)
        workflow.add_node("merger", merger)
        workflow.add_node("writer", writer)

        # Connect nodes - parallel branches
        workflow.connect("reader", "sum_calculator", mapping={"data.values": "values"})
        workflow.connect(
            "reader",
            "product_calculator",
            mapping={"data.values": "values", "data.multiplier": "multiplier"},
        )
        workflow.connect(
            "reader", "stats_calculator", mapping={"data.values": "values"}
        )

        # Connect to merger
        workflow.connect("sum_calculator", "merger", mapping={"result": "sum_result"})
        workflow.connect(
            "product_calculator", "merger", mapping={"result": "product_result"}
        )
        workflow.connect(
            "stats_calculator", "merger", mapping={"result": "stats_result"}
        )

        # Connect to writer
        workflow.connect("merger", "writer", mapping={"result": "data"})

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        # Verify
        assert output_file.exists()

        with open(output_file) as f:
            result_data = json.load(f)
            assert result_data["sum"] == 15  # 1+2+3+4+5
            assert result_data["products"] == [2, 4, 6, 8, 10]  # Each * 2
            assert result_data["statistics"]["mean"] == 3.0
            assert result_data["statistics"]["max"] == 5
            assert result_data["statistics"]["min"] == 1
            assert result_data["statistics"]["count"] == 5
