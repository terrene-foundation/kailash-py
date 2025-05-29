#!/usr/bin/env python3
"""
Test script to verify all updated examples can run without errors.
"""

import sys
import subprocess
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_example(example_file: str, timeout: int = 60):
    """Test if an example can run without errors."""
    logger.info(f"Testing {example_file}...")
    
    try:
        # Run the example with Python
        result = subprocess.run(
            [sys.executable, example_file],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        # Check the result
        if result.returncode == 0:
            logger.info(f"✓ {example_file} - executed successfully")
            return True
        else:
            logger.error(f"✗ {example_file} - execution failed")
            logger.error(f"Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.warning(f"✗ {example_file} - execution timeout (> {timeout}s)")
        return False
    except Exception as e:
        logger.error(f"✗ {example_file} - error: {e}")
        return False

def update_python_code_nodes_import(example_file: str):
    """Update the imports in example files to use fixed PythonCodeNode."""
    try:
        with open(example_file, 'r') as f:
            content = f.read()
            
        # Replace PythonCodeNode import with the fixed version
        updated_content = content.replace(
            "from kailash.nodes.code.python import PythonCodeNode", 
            "from kailash.nodes.code.python import PythonCodeNode"
        )
        updated_content = updated_content.replace(
            "from kailash.nodes.code.python import PythonCodeNode", 
            "from kailash.nodes.code.python import PythonCodeNode"
        )
        
        if content != updated_content:
            with open(example_file, 'w') as f:
                f.write(updated_content)
                
            logger.info(f"Updated imports in {example_file}")
            
    except Exception as e:
        logger.error(f"Failed to update imports in {example_file}: {e}")

def main():
    """Run tests for all updated examples."""
    logger.info("Testing updated Kailash SDK examples...\n")
    
    # Change to examples directory
    examples_dir = Path(__file__).parent
    import os
    os.chdir(examples_dir)
    
    # List of examples to test
    examples = [
        "simplified_workflow_example.py",  # Our new simplified example
    ]
    
    # First update imports in all Python files
    python_files = list(Path('.').glob('*.py'))
    for py_file in python_files:
        if "python" not in str(py_file):  # Skip files without python code nodes
            update_python_code_nodes_import(str(py_file))
    
    # Test each example
    failed_examples = []
    
    for example in examples:
        if not test_example(example):
            failed_examples.append(example)
    
    # Report results
    if failed_examples:
        logger.error(f"\nFailed examples: {failed_examples}")
        return 1
    else:
        logger.info("\n=== All examples passed! ===")
        return 0

if __name__ == "__main__":
    sys.exit(main())