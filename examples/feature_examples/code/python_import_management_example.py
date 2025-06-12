"""Example demonstrating enhanced PythonCodeNode import management.

This example shows the improved import error handling, module validation,
and helpful suggestions when working with PythonCodeNode.
"""

import json
from kailash import setup_logging
from kailash.nodes.code import PythonCodeNode
from kailash.workflow import Workflow


def demonstrate_module_checking():
    """Demonstrate module availability checking."""
    print("\n=== Module Availability Checking ===")
    
    # List all allowed modules
    allowed_modules = PythonCodeNode.list_allowed_modules()
    print(f"Total allowed modules: {len(allowed_modules)}")
    print(f"Common modules: {allowed_modules[:10]}...")
    
    # Check various modules
    test_modules = [
        "pandas",      # Allowed and commonly installed
        "numpy",       # Allowed and commonly installed
        "requests",    # Not allowed - common mistake
        "subprocess",  # Not allowed - security risk
        "boto3",       # Not allowed - cloud operations
        "sklearn",     # Allowed for ML
        "fake_module", # Doesn't exist
    ]
    
    print("\n=== Module Status ===")
    for module in test_modules:
        info = PythonCodeNode.check_module_availability(module)
        status = "✓" if info["allowed"] and info["importable"] else "✗"
        print(f"{status} {module}: allowed={info['allowed']}, installed={info['installed']}")
        if info["suggestions"]:
            print(f"  Suggestions: {info['suggestions'][0]}")


def demonstrate_code_validation():
    """Demonstrate code validation with helpful feedback."""
    print("\n=== Code Validation ===")
    
    # Create a PythonCodeNode instance for validation
    node = PythonCodeNode(
        name="validator",
        code="# Dummy code for validation"
    )
    
    # Test various code snippets
    test_cases = [
        {
            "name": "Good code",
            "code": """
import pandas as pd
import numpy as np

# Process data
data = pd.DataFrame(input_data)
result = data.mean().to_dict()
"""
        },
        {
            "name": "Forbidden import",
            "code": """
import requests  # This will fail

response = requests.get('https://api.example.com')
result = response.json()
"""
        },
        {
            "name": "Dangerous operations",
            "code": """
import os

# Try to use eval (dangerous)
code = "print('hello')"
eval(code)

result = "done"
"""
        },
        {
            "name": "Syntax error",
            "code": """
import pandas as pd

# Missing closing parenthesis
df = pd.DataFrame(data
result = df
"""
        },
        {
            "name": "Common mistake - print without result",
            "code": """
import pandas as pd

df = pd.DataFrame(input_data)
print(df.head())  # This won't be captured
print(df.describe())
"""
        },
    ]
    
    for test in test_cases:
        print(f"\n--- {test['name']} ---")
        validation = node.validate_code(test['code'])
        
        print(f"Valid: {validation['valid']}")
        
        if validation['syntax_errors']:
            print("Syntax errors:")
            for err in validation['syntax_errors']:
                print(f"  Line {err['line']}: {err['message']}")
        
        if validation['safety_violations']:
            print("Safety violations:")
            for violation in validation['safety_violations']:
                print(f"  Line {violation['line']}: {violation['message']}")
        
        if validation['warnings']:
            print("Warnings:")
            for warning in validation['warnings']:
                print(f"  - {warning}")
        
        if validation['suggestions']:
            print("Suggestions:")
            for suggestion in validation['suggestions']:
                print(f"  → {suggestion}")


def demonstrate_import_error_handling():
    """Demonstrate enhanced import error messages."""
    print("\n=== Import Error Handling ===")
    
    # Test case 1: Trying to use requests
    print("\n1. Attempting to import 'requests':")
    try:
        node = PythonCodeNode(
            name="http_processor",
            code="""
import requests

url = "https://api.example.com/data"
response = requests.get(url)
result = response.json()
"""
        )
        result = node.run(url="test")
    except Exception as e:
        print(f"Error caught:\n{e}")
    
    # Test case 2: Database operations
    print("\n2. Attempting to import 'sqlite3':")
    try:
        node = PythonCodeNode(
            name="db_processor",
            code="""
import sqlite3

conn = sqlite3.connect('data.db')
cursor = conn.cursor()
cursor.execute("SELECT * FROM users")
result = cursor.fetchall()
"""
        )
        result = node.run()
    except Exception as e:
        print(f"Error caught:\n{e}")
    
    # Test case 3: Missing allowed module
    print("\n3. Attempting to import missing but allowed module:")
    try:
        node = PythonCodeNode(
            name="ml_processor",
            code="""
import pandas as pd
import some_rare_ml_lib  # This might not be installed

data = pd.DataFrame(input_data)
result = some_rare_ml_lib.process(data)
"""
        )
        result = node.run(input_data=[])
    except Exception as e:
        print(f"Error caught:\n{e}")


def demonstrate_code_length_warning():
    """Demonstrate code length warning feature."""
    print("\n=== Code Length Warning ===")
    
    # Example 1: Short code (no warning)
    print("\n1. Short code (5 lines) - No warning:")
    short_code = """
import pandas as pd

df = pd.DataFrame(data)
result = df.mean().to_dict()
"""
    
    node1 = PythonCodeNode(
        name="short_processor",
        code=short_code,
        max_code_lines=10  # Default threshold
    )
    print("✓ Node created without warnings")
    
    # Example 2: Long code (triggers warning)
    print("\n2. Long code (15+ lines) - Will trigger warning:")
    long_code = """
import pandas as pd
import numpy as np
from datetime import datetime

# This is a long code block that should be refactored
df = pd.DataFrame(data)

# Add multiple calculated columns
df['timestamp'] = datetime.now()
df['value_squared'] = df['value'] ** 2
df['value_cubed'] = df['value'] ** 3
df['value_sqrt'] = np.sqrt(df['value'])
df['value_log'] = np.log(df['value'] + 1)

# Calculate statistics
mean_val = df['value'].mean()
std_val = df['value'].std()
min_val = df['value'].min()
max_val = df['value'].max()

# Create result
result = {
    'processed_data': df.to_dict('records'),
    'statistics': {
        'mean': mean_val,
        'std': std_val,
        'min': min_val,
        'max': max_val
    }
}
"""
    
    print("Creating node with long code...")
    node2 = PythonCodeNode(
        name="long_processor",
        code=long_code,
        max_code_lines=10
    )
    print("⚠️ Warning should have been logged above")
    
    # Example 3: Custom threshold
    print("\n3. Custom threshold (set to 20 lines):")
    node3 = PythonCodeNode(
        name="custom_threshold",
        code=long_code,
        max_code_lines=20  # Higher threshold
    )
    print("✓ No warning with higher threshold")
    
    # Example 4: Disable warning
    print("\n4. Disable warning (set to 0):")
    node4 = PythonCodeNode(
        name="no_warning",
        code=long_code,
        max_code_lines=0  # Disable warning
    )
    print("✓ Warning disabled")


def demonstrate_best_practices():
    """Demonstrate best practices for PythonCodeNode."""
    print("\n=== Best Practices ===")
    
    # Good example - using allowed modules properly
    print("\n1. Good Example - Short, focused code:")
    good_code = """
import pandas as pd
import numpy as np

# Process input data
df = pd.DataFrame(data)
stats = df.describe().to_dict()
result = {'data': df.to_dict('records'), 'stats': stats}
"""
    
    node = PythonCodeNode(
        name="data_processor",
        code=good_code
    )
    
    validation = node.validate_code(good_code)
    print(f"Code is valid: {validation['valid']}")
    print(f"Imports used: {validation['imports']}")
    
    # Better approach for long code
    print("\n2. Better Approach for Long Code - Use Functions:")
    print("""
Instead of long code strings, use from_function():

def process_data(data):
    '''Process data with multiple steps.'''
    df = pd.DataFrame(data)
    
    # Add calculated columns
    df['value_squared'] = df['value'] ** 2
    df['value_log'] = np.log(df['value'] + 1)
    
    # Calculate statistics
    stats = {
        'mean': df['value'].mean(),
        'std': df['value'].std(),
        'count': len(df)
    }
    
    return {'data': df.to_dict('records'), 'stats': stats}

# Create node from function
node = PythonCodeNode.from_function(
    func=process_data,
    name="data_processor"
)
""")
    
    # Alternative approach - using specialized nodes
    print("\n3. Best Alternative - Using Specialized Nodes:")
    print("""
Instead of:
    import requests
    response = requests.get(url)
    
Use:
    workflow.add_node("http_client", HTTPRequestNode())
    
Instead of:
    import sqlite3
    conn = sqlite3.connect('db.sqlite')
    
Use:
    workflow.add_node("database", SQLDatabaseNode(
        connection_string="sqlite:///db.sqlite"
    ))
""")


def create_workflow_with_validation():
    """Create a workflow that validates code before execution."""
    print("\n=== Workflow with Code Validation ===")
    
    workflow = Workflow(name="validated_python_workflow")
    
    # Add a PythonCodeNode with validation
    code = """
import json
import pandas as pd

# This is valid code
df = pd.DataFrame(input_data)
summary = df.describe().to_dict()

result = {
    'summary': summary,
    'row_count': len(df)
}
"""
    
    # Create and validate node
    node = PythonCodeNode(
        name="analyzer",
        code=code
    )
    
    validation = node.validate_code(code)
    if validation['valid']:
        workflow.add_node("analyzer", node)
        print("✓ Code validated and node added to workflow")
    else:
        print("✗ Code validation failed:")
        for suggestion in validation['suggestions']:
            print(f"  - {suggestion}")
    
    return workflow


def main():
    """Run all demonstrations."""
    setup_logging()
    
    print("PythonCodeNode Import Management Demonstration")
    print("=" * 50)
    
    # Run demonstrations
    demonstrate_module_checking()
    demonstrate_code_validation()
    demonstrate_import_error_handling()
    demonstrate_code_length_warning()
    demonstrate_best_practices()
    create_workflow_with_validation()
    
    print("\n=== Summary ===")
    print("Key improvements in PythonCodeNode import management:")
    print("✓ Clear error messages with specific suggestions")
    print("✓ Module availability checking before execution")
    print("✓ Code validation with syntax and safety checks")
    print("✓ Warning for long code blocks (configurable threshold)")
    print("✓ Helpful alternatives for common use cases")
    print("✓ Better developer experience with actionable feedback")


if __name__ == "__main__":
    main()