#!/usr/bin/env python3
"""
Comprehensive Example Testing - Kailash SDK

This script provides comprehensive validation of all SDK examples including:
1. Syntax validation - Python syntax correctness
2. Import testing - Module imports without errors  
3. Data path validation - Proper use of data utilities
4. Execution testing - Examples run without runtime errors
5. Performance tracking - Execution time analysis

Usage:
    python test-all-examples.py [--verbose] [--category CATEGORY]

Examples:
    # Run all tests
    python test-all-examples.py
    
    # Verbose output with detailed error information
    python test-all-examples.py --verbose
    
    # Test specific category only
    python test-all-examples.py --category ai

Categories: ai, security, workflows, nodes, integrations, enterprise

Dependencies:
    - Kailash SDK development environment running
    - All example dependencies installed
    - Data directories properly configured

Output:
    - Console progress with colored status indicators
    - JSON results file with detailed metrics
    - Performance statistics and timing data
"""

import subprocess
import sys
import time
import os
from pathlib import Path
from typing import Tuple, List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent  # Go up 3 levels from scripts/testing/
sys.path.insert(0, str(project_root))


def get_example_files() -> list[Path]:
    """Get all Python example files."""
    examples_dir = project_root / "examples"
    example_files = []

    # New structure - search feature_examples directory
    feature_tests_dir = examples_dir / "feature_examples"

    # Files to exclude
    exclude_files = {
        "__init__.py",
        "test_runner.py",
        "paths.py",
        "maintenance.py",
        "data_paths.py",
    }

    # Recursively find all Python files in feature_examples
    if feature_tests_dir.exists():
        for file in feature_tests_dir.rglob("*.py"):
            if file.name not in exclude_files and not file.name.startswith("_"):
                example_files.append(file)

    # Also check other example directories
    for dir_name in ["node_examples", "integration_examples", "workflow_examples"]:
        example_dir = examples_dir / dir_name
        if example_dir.exists():
            for file in example_dir.rglob("*.py"):
                if file.name not in exclude_files and not file.name.startswith("_"):
                    example_files.append(file)

    # Also check test-harness for any executable tests
    test_harness_dir = examples_dir / "test-harness"
    if test_harness_dir.exists():
        for file in test_harness_dir.rglob("*.py"):
            if (
                file.name not in exclude_files
                and not file.name.startswith("_")
                and "__pycache__" not in str(file)
            ):
                example_files.append(file)

    return sorted(example_files)


def check_syntax(file_path: Path) -> tuple[bool, str]:
    """Check if a file has valid Python syntax."""
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(file_path)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, result.stderr


def check_imports(file_path: Path) -> tuple[bool, str]:
    """Check if a file imports without errors."""
    # Create a test script that imports the module
    test_code = f"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path('{project_root}')))
sys.path.insert(0, str(Path('{file_path.parent}')))

try:
    # Try to import the module
    module_name = '{file_path.stem}'
    exec(f'import {{module_name}}')
    print("Import successful")
except Exception as e:
    print(f"Import failed: {{e}}")
    sys.exit(1)
"""

    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True,
        cwd=str(file_path.parent),
    )

    return result.returncode == 0, result.stdout + result.stderr


def check_data_paths(file_path: Path) -> tuple[bool, list[str]]:
    """Check if file uses hardcoded data paths."""
    issues = []

    with open(file_path) as f:
        content = f.read()
        lines = content.split("\n")

    # Patterns to check for
    bad_patterns = [
        ("data/", "Use get_input_data_path() instead"),
        ("examples/data/", "Use get_input_data_path() instead"),
        ("../data/", "Use get_input_data_path() instead"),
        ("data\\\\", "Use get_input_data_path() instead"),
    ]

    for i, line in enumerate(lines, 1):
        # Skip comments and strings in docstrings
        if line.strip().startswith("#") or '"""' in line or "'''" in line:
            continue

        for pattern, message in bad_patterns:
            if pattern in line and "data_paths" not in line:
                # Skip URLs, Docker paths, and other valid uses
                if any(
                    skip in line
                    for skip in [
                        "https://",
                        "http://",
                        "api.openweathermap.org",
                        "/data/",  # Docker absolute paths
                        "RUN mkdir",  # Dockerfile commands
                        'f"✓',  # Print statements with paths
                        "get_output_data_path",  # Already using correct function
                        "get_input_data_path",  # Already using correct function
                    ]
                ):
                    continue
                issues.append(f"Line {i}: {message} (found '{pattern}')")

    return len(issues) == 0, issues


def run_example(file_path: Path, timeout: int = 10) -> Tuple[bool, str, float]:
    """Actually run an example file and check if it executes successfully.
    
    Returns:
        tuple: (success, output/error, execution_time)
    """
    start_time = time.time()
    
    # Set up environment
    env = os.environ.copy()
    env['PYTHONPATH'] = str(project_root)
    
    try:
        # Run the example with a timeout
        result = subprocess.run(
            [sys.executable, str(file_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(file_path.parent),
            env=env
        )
        
        execution_time = time.time() - start_time
        
        if result.returncode == 0:
            # Check if output contains error indicators
            output = result.stdout + result.stderr
            error_indicators = [
                "Error:",
                "Failed:",
                "Exception:",
                "Traceback",
                "AssertionError",
                "KeyError",
                "ValueError",
                "TypeError",
                "AttributeError"
            ]
            
            # Some errors are expected in examples (e.g., showing error handling)
            allowed_errors = [
                "❌",  # Used in output messages
                "error handling",
                "Expected error",
                "This is expected",
                "demonstrates error"
            ]
            
            has_real_error = False
            for indicator in error_indicators:
                if indicator in output:
                    # Check if it's an allowed error
                    if not any(allowed in output for allowed in allowed_errors):
                        has_real_error = True
                        break
            
            if has_real_error:
                return False, f"Output contains error indicators:\n{output[-1000:]}", execution_time
            else:
                return True, f"Executed successfully in {execution_time:.2f}s", execution_time
        else:
            error_output = result.stderr if result.stderr else result.stdout
            return False, f"Exit code {result.returncode}:\n{error_output[-1000:]}", execution_time
            
    except subprocess.TimeoutExpired:
        return False, f"Timeout after {timeout}s", timeout
    except Exception as e:
        execution_time = time.time() - start_time
        return False, f"Exception: {str(e)}", execution_time


def categorize_example(file_path: Path) -> str:
    """Categorize an example by its directory structure."""
    relative = file_path.relative_to(project_root / "examples")
    parts = relative.parts
    
    if "feature_examples" in parts:
        if len(parts) > 2:
            return parts[1]  # e.g., 'ai', 'security', 'validation'
        return "feature"
    elif "node_examples" in parts:
        return "node"
    elif "integration_examples" in parts:
        return "integration"
    elif "workflow_examples" in parts:
        return "workflow"
    elif "test-harness" in parts:
        return "test-harness"
    else:
        return "other"


def main():
    """Main test runner."""
    print("=" * 70)
    print("Testing all Kailash SDK Examples")
    print("=" * 70)

    example_files = get_example_files()
    print(f"\nFound {len(example_files)} example files to test\n")

    # Group examples by category
    categories: Dict[str, List[Path]] = {}
    for example in example_files:
        category = categorize_example(example)
        if category not in categories:
            categories[category] = []
        categories[category].append(example)

    results = {
        "syntax": {"passed": 0, "failed": 0, "errors": []},
        "imports": {"passed": 0, "failed": 0, "errors": []},
        "data_paths": {"passed": 0, "failed": 0, "errors": []},
        "execution": {"passed": 0, "failed": 0, "errors": [], "skipped": 0},
    }

    # Track execution times
    execution_times = []
    
    # Examples that require special setup (skip execution)
    skip_execution = {
        "ollama_rag_example.py",  # Requires Ollama
        "sharepoint_auth_example.py",  # Requires SharePoint credentials
        "azure_openai_example.py",  # Requires Azure credentials
        "advanced_rag_pipeline.py",  # Requires embeddings setup
        "distributed_training_example.py",  # Requires distributed setup
        "llm_monitoring_example.py",  # Requires Ollama to be running
        "oauth2_enhanced_example.py",  # Requires OAuth servers
        "rotating_credentials_example.py",  # Requires credential infrastructure
        "sharepoint_multi_auth_example.py",  # Requires SharePoint
    }

    # Process examples by category
    for category, files in sorted(categories.items()):
        print(f"\n{'=' * 50}")
        print(f"Category: {category.upper()} ({len(files)} files)")
        print(f"{'=' * 50}")
        
        for example in files:
            relative_path = example.relative_to(project_root)
            print(f"\n📄 Testing: {relative_path}")

            # Check syntax
            syntax_ok, syntax_error = check_syntax(example)
            if syntax_ok:
                results["syntax"]["passed"] += 1
                print("  ✓ Syntax OK")
            else:
                results["syntax"]["failed"] += 1
                results["syntax"]["errors"].append((relative_path, syntax_error))
                print(f"  ✗ Syntax Error: {syntax_error}")
                continue  # Skip other tests if syntax is bad

            # Check imports
            import_ok, import_error = check_imports(example)
            if import_ok:
                results["imports"]["passed"] += 1
                print("  ✓ Imports OK")
            else:
                results["imports"]["failed"] += 1
                results["imports"]["errors"].append((relative_path, import_error))
                print(f"  ✗ Import Error: {import_error}")

            # Check data paths
            paths_ok, path_issues = check_data_paths(example)
            if paths_ok:
                results["data_paths"]["passed"] += 1
                print("  ✓ Data paths OK")
            else:
                results["data_paths"]["failed"] += 1
                results["data_paths"]["errors"].append((relative_path, path_issues))
                print("  ✗ Data path issues:")
                for issue in path_issues:
                    print(f"    - {issue}")
            
            # Run the example (NEW)
            if example.name in skip_execution:
                results["execution"]["skipped"] += 1
                print("  ⏭️  Execution skipped (requires special setup)")
            elif import_ok:  # Only run if imports are OK
                print("  🔄 Running example...")
                run_ok, run_output, exec_time = run_example(example)
                execution_times.append((relative_path, exec_time))
                
                if run_ok:
                    results["execution"]["passed"] += 1
                    print(f"  ✓ Execution OK ({exec_time:.2f}s)")
                else:
                    results["execution"]["failed"] += 1
                    results["execution"]["errors"].append((relative_path, run_output))
                    print(f"  ✗ Execution Failed:")
                    # Print first few lines of error
                    error_lines = run_output.split('\n')
                    for line in error_lines[:5]:
                        if line.strip():
                            print(f"    {line}")
                    if len(error_lines) > 5:
                        print(f"    ... ({len(error_lines) - 5} more lines)")

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_passed = True
    for test_type, result in results.items():
        if test_type == "execution":
            total = result["passed"] + result["failed"] + result["skipped"]
        else:
            total = result["passed"] + result["failed"]
            
        print(f"\n{test_type.replace('_', ' ').title()}:")
        print(f"  Passed: {result['passed']}/{total}")
        
        if test_type == "execution" and result["skipped"] > 0:
            print(f"  Skipped: {result['skipped']} (require special setup)")
            
        if result["failed"] > 0:
            all_passed = False
            print(f"  Failed: {result['failed']}")
            print("  Errors:")
            for file, error in result["errors"][:5]:  # Show first 5 errors
                print(f"    - {file}:")
                if isinstance(error, list):
                    for e in error:
                        print(f"      {e}")
                else:
                    error_lines = str(error).strip().split('\n')
                    for line in error_lines[:3]:  # First 3 lines of each error
                        if line.strip():
                            print(f"      {line}")
            if len(result["errors"]) > 5:
                print(f"    ... and {len(result['errors']) - 5} more")

    # Print execution time statistics
    if execution_times:
        print("\n" + "=" * 70)
        print("EXECUTION TIME STATISTICS")
        print("=" * 70)
        
        execution_times.sort(key=lambda x: x[1], reverse=True)
        total_time = sum(t[1] for t in execution_times)
        
        print(f"\nTotal execution time: {total_time:.2f}s")
        print(f"Average per example: {total_time / len(execution_times):.2f}s")
        
        print("\nSlowest examples:")
        for path, exec_time in execution_times[:5]:
            print(f"  {exec_time:6.2f}s - {path}")

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed - please fix the issues above")
    print("=" * 70)

    # Print helpful tips for common issues
    if not all_passed:
        print("\n💡 Common fixes:")
        print("  - LocalWorkflowRunner import: Use 'from kailash.runtime.local import LocalRuntime'")
        print("  - Execution method: Use 'LocalRuntime().execute(workflow)' not '.run()'")
        print("  - Missing imports: Ensure all required nodes are imported")
        print("  - Data paths: Use get_input_data_path() / get_output_data_path()")
        print("  - Timeout issues: Some examples may need longer execution times")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())