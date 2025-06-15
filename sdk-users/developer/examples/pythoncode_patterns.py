"""
PythonCodeNode Advanced Patterns

This example demonstrates critical patterns and common pitfalls when using PythonCodeNode.
Most importantly: input variables are EXCLUDED from outputs!
"""

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.runtime import LocalRuntime


def create_pythoncode_workflow():
    """Demonstrates correct PythonCodeNode patterns."""
    workflow = Workflow(
        workflow_id="pythoncode_patterns", name="PythonCodeNode Pattern Examples"
    )

    # Pattern 1: Correct Variable Mapping
    # ===================================

    # Stage 1: Generate some data
    generator = PythonCodeNode(
        name="generator",  # Always include name!
        code="""
result = {
    'files': ['a.csv', 'b.json', 'c.txt'],
    'metadata': {'count': 3, 'source': 'test'}
}
""",
    )
    workflow.add_node("generator", generator)

    # Stage 2: Process data (CORRECT - different variable name)
    processor = PythonCodeNode(
        name="processor",
        code="""
# CORRECT: 'input_data' is different from output 'result'
files = input_data.get('files', [])
metadata = input_data.get('metadata', {})

# Process the data
csv_files = [f for f in files if f.endswith('.csv')]
json_files = [f for f in files if f.endswith('.json')]

# 'result' is a NEW variable, will be in outputs
result = {
    'csv_count': len(csv_files),
    'json_count': len(json_files),
    'total_count': metadata.get('count', 0)
}
""",
    )
    workflow.add_node("processor", processor)

    # CORRECT: Map 'result' to 'input_data' (different names)
    workflow.connect("generator", "processor", mapping={"result": "input_data"})

    # Pattern 2: DataFrame Serialization
    # ==================================

    data_processor = PythonCodeNode(
        name="data_processor",
        code="""
import pandas as pd
import numpy as np

# Create sample data
data = {
    'id': [1, 2, 3],
    'value': [10.5, 20.3, 30.1],
    'category': ['A', 'B', 'A']
}

# Create DataFrame
df = pd.DataFrame(data)

# WRONG: This would fail with serialization error
# result = {'dataframe': df}

# CORRECT: Convert to serializable format
result = {
    'data': df.to_dict('records'),
    'columns': df.columns.tolist(),
    'shape': list(df.shape),
    'summary': {
        'mean_value': float(df['value'].mean()),  # Convert numpy types
        'categories': df['category'].unique().tolist()
    }
}

# Also handle numpy arrays
arr = np.array([1, 2, 3, 4, 5])
result['array_data'] = arr.tolist()  # Convert to list
result['array_stats'] = {
    'mean': float(arr.mean()),
    'std': float(arr.std())
}
""",
    )
    workflow.add_node("data_processor", data_processor)

    # Pattern 3: Error Handling
    # ========================

    safe_processor = PythonCodeNode(
        name="safe_processor",
        code="""
# Always handle potential missing inputs
try:
    # Check if input exists
    if 'input_value' not in locals():
        result = {'error': 'No input provided', 'status': 'failed'}
    else:
        # Validate input type
        if not isinstance(input_value, (int, float)):
            result = {'error': 'Input must be numeric', 'status': 'failed'}
        else:
            # Safe processing
            result = {
                'doubled': input_value * 2,
                'squared': input_value ** 2,
                'status': 'success'
            }
except Exception as e:
    result = {
        'error': str(e),
        'status': 'error',
        'traceback': str(e.__class__.__name__)
    }
""",
    )
    workflow.add_node("safe_processor", safe_processor)

    # Pattern 4: Multi-Stage Pipeline
    # ===============================

    # Stage 1
    stage1 = PythonCodeNode(
        name="stage1", code="result = {'stage': 1, 'data': [1, 2, 3]}"
    )
    workflow.add_node("stage1", stage1)

    # Stage 2 - Process stage 1 output
    stage2 = PythonCodeNode(
        name="stage2",
        code="""
# Using descriptive variable name from stage1
stage_num = stage1_output.get('stage', 0)
data = stage1_output.get('data', [])

# Process
result = {
    'stage': stage_num + 1,
    'data': [x * 2 for x in data],
    'sum': sum(data)
}
""",
    )
    workflow.add_node("stage2", stage2)

    # Stage 3 - Aggregate results
    stage3 = PythonCodeNode(
        name="stage3",
        code="""
# Different variable names for each stage
s1_data = stage1_data.get('data', [])
s2_data = stage2_data.get('data', [])
s2_sum = stage2_data.get('sum', 0)

result = {
    'stage': 3,
    'original': s1_data,
    'processed': s2_data,
    'total': s2_sum,
    'report': f'Processed {len(s1_data)} items, sum: {s2_sum}'
}
""",
    )
    workflow.add_node("stage3", stage3)

    # Connect with unique variable names
    workflow.connect("stage1", "stage2", mapping={"result": "stage1_output"})
    workflow.connect("stage1", "stage3", mapping={"result": "stage1_data"})
    workflow.connect("stage2", "stage3", mapping={"result": "stage2_data"})

    return workflow


def demonstrate_common_mistakes():
    """Shows what NOT to do with PythonCodeNode."""

    # MISTAKE 1: Same variable name mapping
    # =====================================
    print("MISTAKE 1: Same variable name in mapping")

    bad_workflow = Workflow("bad_example", "Common Mistakes")

    node1 = PythonCodeNode(name="node1", code="result = {'value': 42}")
    bad_workflow.add_node("node1", node1)

    node2 = PythonCodeNode(
        name="node2",
        code="""
# This will FAIL because 'result' is an input variable
value = result.get('value')
result = {'doubled': value * 2}  # Won't be in output!
""",
    )
    bad_workflow.add_node("node2", node2)

    # WRONG: Mapping to same variable name
    bad_workflow.connect("node1", "node2", mapping={"result": "result"})

    # This will fail with "Required output 'result' not provided"

    # MISTAKE 2: Forgetting name parameter
    # ====================================
    print("\nMISTAKE 2: Missing name parameter")

    try:
        # This will raise TypeError
        _ = PythonCodeNode(code="result = {}")
    except TypeError as e:
        print(f"Error: {e}")

    # MISTAKE 3: Non-serializable outputs
    # ===================================
    print("\nMISTAKE 3: Non-serializable data")

    _ = PythonCodeNode(
        name="bad_serialization",
        code="""
import pandas as pd
import numpy as np

# These will fail during serialization
df = pd.DataFrame({'a': [1, 2, 3]})
arr = np.array([1, 2, 3])

result = {
    'dataframe': df,      # Not JSON serializable!
    'array': arr,         # Not JSON serializable!
    'set': {1, 2, 3},    # Not JSON serializable!
}
""",
    )


def main():
    """Run the examples."""
    print("PythonCodeNode Pattern Examples")
    print("=" * 50)

    # Create and run the correct workflow
    workflow = create_pythoncode_workflow()
    runtime = LocalRuntime()

    # Run with sample parameters
    parameters = {"safe_processor": {"input_value": 10}}

    print("\nRunning workflow with correct patterns...")
    result = runtime.execute(workflow, parameters=parameters)

    # Extract outputs from tuple result
    outputs, error = result if isinstance(result, tuple) else (result, None)

    print("\nResults:")
    for node_id, node_result in outputs.items():
        print(f"\n{node_id}:")
        print(f"  {node_result}")

    if error:
        print(f"\nErrors: {error}")
    else:
        print("\n✅ All patterns executed successfully!")

    # Show common mistakes (commented out to avoid errors)
    # demonstrate_common_mistakes()


if __name__ == "__main__":
    main()
