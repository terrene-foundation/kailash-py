# Integration Tests for Kailash Python SDK

This directory contains comprehensive integration tests that verify the correct interaction between multiple components of the Kailash SDK.

## Test Structure

The integration tests are organized into the following categories:

1. **test_workflow_execution.py** - End-to-end workflow execution tests
2. **test_node_communication.py** - Tests for data passing between nodes
3. **test_task_tracking_integration.py** - Task tracking during execution
4. **test_error_propagation.py** - Error handling across workflows
5. **test_complex_workflows.py** - Complex multi-branch workflow tests
6. **test_export_integration.py** - Export functionality tests
7. **test_cli_integration.py** - CLI command tests
8. **test_storage_integration.py** - Storage backend tests
9. **test_visualization_integration.py** - Visualization tests
10. **test_performance.py** - Performance and load tests

## Running Integration Tests

### Run All Integration Tests
```bash
pytest tests/integration/
```

### Run Specific Test File
```bash
pytest tests/integration/test_workflow_execution.py
```

### Run with Verbose Output
```bash
pytest tests/integration/ -v
```

### Run with Coverage
```bash
pytest tests/integration/ --cov=kailash --cov-report=html
```

### Run Performance Tests Only
```bash
pytest tests/integration/test_performance.py -v
```

## Test Configuration

### conftest.py

The `conftest.py` file provides shared fixtures for all integration tests:

- `temp_data_dir` - Temporary directory for test data
- `sample_csv_file` - Sample CSV file for testing
- `sample_json_file` - Sample JSON file for testing
- `simple_workflow` - Simple workflow for basic tests
- `complex_workflow` - Complex workflow with multiple branches
- `task_tracker` - Task tracking instance
- `large_dataset` - Large dataset for performance testing

## Performance Testing

The performance tests include:

- Large workflow construction and execution
- Parallel workflow execution
- Large data processing
- Memory efficiency tests
- Concurrent execution tests
- Scalability tests

To run performance tests with detailed output:

```bash
pytest tests/integration/test_performance.py -v -s
```

## Environment Variables

Some tests support configuration via environment variables:

- `KAILASH_TEST_DATA_SIZE` - Size of test data for performance tests
- `KAILASH_TEST_TIMEOUT` - Timeout for long-running tests
- `KAILASH_TEST_PARALLEL_WORKERS` - Number of parallel workers for tests

## Test Data

Integration tests create test data in temporary directories. Large datasets are generated on-the-fly for performance testing. Test data is automatically cleaned up after test execution.

## Troubleshooting

### Common Issues

1. **GraphViz not installed** - Some visualization tests require GraphViz:
   ```bash
   # macOS
   brew install graphviz

   # Ubuntu/Debian
   apt-get install graphviz
   ```

2. **Memory issues** - Performance tests may require significant memory:
   ```bash
   # Run with limited test set
   pytest tests/integration/ -k "not large_data"
   ```

3. **Database lock errors** - Ensure no other processes are using test databases:
   ```bash
   # Clear test data
   rm -rf /tmp/kailash_test_*
   ```

## Contributing

When adding new integration tests:

1. Follow the existing test structure
2. Use appropriate fixtures from `conftest.py`
3. Add docstrings explaining test purpose
4. Ensure tests are isolated and don't affect other tests
5. Clean up any created resources

## CI/CD Integration

Integration tests are run as part of the CI/CD pipeline. Long-running performance tests may be configured to run only on dedicated performance testing branches.

```yaml
# Example GitHub Actions configuration
- name: Run Integration Tests
  run: |
    pytest tests/integration/ --cov=kailash

- name: Run Performance Tests
  if: github.ref == 'refs/heads/performance-testing'
  run: |
    pytest tests/integration/test_performance.py -v
```
