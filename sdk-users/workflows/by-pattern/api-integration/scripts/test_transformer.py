#!/usr/bin/env python3
"""Test DataTransformer behavior"""

from kailash import Workflow
from kailash.nodes.transform import DataTransformer
from kailash.runtime.local import LocalRuntime


def test_transformer():
    workflow = Workflow(workflow_id="test_001", name="test_transformer")

    # Simple transformer
    transformer = DataTransformer(
        id="test",
        transformations=[
            """
print(f"Type of data: {type(data)}")
print(f"Data content: {data}")
result = {"message": "Hello", "value": 42}
"""
        ],
    )
    workflow.add_node("test", transformer)

    runtime = LocalRuntime()
    result, run_id = runtime.execute(
        workflow, parameters={"test": {"data": ["item1", "item2"]}}
    )

    print(f"\nFinal result: {result}")


if __name__ == "__main__":
    test_transformer()
