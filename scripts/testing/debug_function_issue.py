#!/usr/bin/env python3
"""Debug the function issue"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from kailash.nodes.code.python import PythonCodeNode


def test_simple():
    """Test the simplest case"""

    def my_function(data: str = "test") -> dict:
        return {"result": data.upper()}

    print(f"Function type: {type(my_function)}")
    print(f"Function callable: {callable(my_function)}")
    print(f"Function name: {my_function.__name__}")

    # This should work
    try:
        node = PythonCodeNode.from_function(my_function, name="test_node")
        print("✅ Node creation successful")

        result = node.execute(data="hello")
        print(f"✅ Execution result: {result}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_simple()
