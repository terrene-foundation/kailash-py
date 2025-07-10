#!/usr/bin/env python3
"""Analyze E2E test failures systematically."""

import json
import subprocess
import sys
from pathlib import Path

# List of E2E test files to analyze
test_files = [
    "test_production_workflows_e2e.py",
    "test_mcp_advanced_patterns_e2e.py",
    "test_durable_gateway_real_world.py",
    "test_realworld_data_pipelines.py",
    "test_async_workflow_builder_e2e_real_world.py",
    "test_workflow_builder_real_world_e2e.py",
    "test_async_sql_transactions_e2e.py",
    "test_pythoncode_production_scenarios.py",
    "test_production_data_pipeline_e2e.py",
    "test_production_database_scenarios.py",
    "test_async_testing_demanding_real_world.py",
    "test_ai_powered_etl_e2e.py",
]

results = {}

for test_file in test_files:
    test_path = f"tests/e2e/{test_file}"
    if not Path(test_path).exists():
        continue

    print(f"\n{'='*60}")
    print(f"Testing: {test_file}")
    print("=" * 60)

    # Run pytest and capture output
    cmd = ["pytest", test_path, "-x", "--tb=short", "-v", "--no-header"]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Parse results
    output = result.stdout + result.stderr

    # Look for specific error patterns
    error_info = {
        "status": "PASSED" if result.returncode == 0 else "FAILED",
        "errors": [],
    }

    if "ImportError" in output:
        error_info["errors"].append("ImportError")
    if "TypeError" in output:
        error_info["errors"].append("TypeError")
    if "KeyError" in output:
        error_info["errors"].append("KeyError")
    if "RuntimeError" in output:
        error_info["errors"].append("RuntimeError")
    if "IndentationError" in output:
        error_info["errors"].append("IndentationError")
    if "Docker not available" in output:
        error_info["errors"].append("Docker dependency")
    if "UndefinedColumnError" in output:
        error_info["errors"].append("Database schema issue")
    if "unexpected keyword argument" in output:
        error_info["errors"].append("API mismatch")

    # Extract specific error messages
    for line in output.split("\n"):
        if "FAILED" in line or "ERROR" in line:
            error_info["failed_test"] = line.strip()
            break

    results[test_file] = error_info

    # Print summary
    print(f"Status: {error_info['status']}")
    if error_info["errors"]:
        print(f"Errors: {', '.join(error_info['errors'])}")

# Print summary
print(f"\n{'='*60}")
print("SUMMARY OF E2E TEST FAILURES")
print("=" * 60)

failed_tests = {k: v for k, v in results.items() if v["status"] == "FAILED"}
grouped_by_error = {}

for test, info in failed_tests.items():
    for error in info["errors"]:
        if error not in grouped_by_error:
            grouped_by_error[error] = []
        grouped_by_error[error].append(test)

print(f"\nTotal tests analyzed: {len(results)}")
print(f"Failed tests: {len(failed_tests)}")
print("\nFailures grouped by error type:")
for error_type, tests in sorted(grouped_by_error.items()):
    print(f"\n{error_type}:")
    for test in tests:
        print(f"  - {test}")
