# Test Harness

This directory contains utilities and helpers for testing Kailash SDK features.

## Structure

### fixtures/
Test data and configurations used across multiple tests:
- Sample CSV/JSON files
- Test configurations
- Mock data generators

### validators/
Utilities for validating test results:
- Output schema validators
- Data format checkers
- Performance validators

### runners/
Test execution helpers:
- Batch test runners
- Performance measurement
- Test report generators

## Usage

### Using Test Fixtures

```python
from examples.test_harness.fixtures import get_test_csv, get_test_config

# Get standard test CSV
test_data = get_test_csv("customers")

# Get test configuration
config = get_test_config("basic_workflow")
```

### Using Validators

```python
from examples.test_harness.validators import validate_output_schema

# Validate node output
result = node.run()
is_valid, errors = validate_output_schema(result, expected_schema)
```

### Using Test Runners

```python
from examples.test_harness.runners import FeatureTestRunner

# Run all tests in a directory
runner = FeatureTestRunner()
results = runner.run_directory("feature-tests/nodes/data-nodes/")
runner.generate_report(results)
```
