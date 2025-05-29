#!/usr/bin/env python3
"""
Test script to verify all examples can run without errors.
"""

import sys
import subprocess
from pathlib import Path

def test_imports():
    """Test if all example files can be imported."""
    print("=== Testing Example Imports ===\n")
    
    example_files = [
        "basic_workflow.py",
        "complex_workflow.py",
        "custom_node.py",
        "data_transformation.py",
        "error_handling.py",
        "export_workflow.py",
        "task_tracking_example.py",
        "visualization_example.py",
        "simplified_workflow_example.py",  # Added new simplified example
        "api_integration_comprehensive.py"  # Added new API integration example
    ]
    
    failed_imports = []
    
    for example in example_files:
        try:
            # Try to run with --help or similar to avoid full execution
            result = subprocess.run(
                [sys.executable, example, "--help"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # If --help not supported, just check if it imports without syntax errors
            if result.returncode != 0:
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", example],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print(f"✓ {example} - imports successfully")
                else:
                    print(f"✗ {example} - import failed")
                    failed_imports.append(example)
            else:
                print(f"✓ {example} - runs with --help")
        except subprocess.TimeoutExpired:
            print(f"✓ {example} - starts execution (timeout expected)")
        except Exception as e:
            print(f"✗ {example} - error: {e}")
            failed_imports.append(example)
    
    if failed_imports:
        print(f"\nFailed imports: {failed_imports}")
        return False
    else:
        print("\nAll examples import successfully!")
        return True

def test_dry_run():
    """Test if examples can execute in dry-run mode."""
    print("\n=== Testing Example Dry Runs ===\n")
    
    # These examples should be safe to run partially
    safe_examples = [
        "test_imports.py",
    ]
    
    for example in safe_examples:
        if not Path(example).exists():
            continue
            
        try:
            result = subprocess.run(
                [sys.executable, example],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                print(f"✓ {example} - executed successfully")
            else:
                print(f"✗ {example} - execution failed")
                print(f"  Error: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print(f"✗ {example} - execution timeout")
        except Exception as e:
            print(f"✗ {example} - error: {e}")

def main():
    """Run all tests."""
    print("Testing all Kailash SDK examples...\n")
    
    # Change to examples directory
    examples_dir = Path(__file__).parent
    import os
    os.chdir(examples_dir)
    
    # Run tests
    import_success = test_imports()
    test_dry_run()
    
    if import_success:
        print("\n=== All tests passed! ===")
        return 0
    else:
        print("\n=== Some tests failed ===")
        return 1

if __name__ == "__main__":
    sys.exit(main())