# Testing Guidelines - Kailash Python SDK

## Testing Philosophy

1. **Test-Driven Development (TDD)**: Write tests before implementation when possible
2. **Comprehensive Coverage**: Aim for >80% code coverage
3. **Fast and Reliable**: Tests should run quickly and consistently
4. **Clear Failure Messages**: Failed tests should clearly indicate what went wrong

## Test Structure

### Directory Organization
```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── test_nodes/              # Node tests
│   ├── test_base.py
│   ├── test_data.py
│   ├── test_transform.py
│   └── test_api.py
├── test_workflow/           # Workflow tests
│   ├── test_graph.py
│   ├── test_execution.py
│   └── test_state.py
├── integration/             # Integration tests
│   ├── test_full_workflows.py
│   └── test_node_communication.py
└── test_utils/              # Utility tests
```

### Test File Naming
- Unit tests: `test_<module_name>.py`
- Integration tests: `test_<feature>_integration.py`
- Test class: `Test<ClassName>`
- Test method: `test_<method>_<scenario>`

## Writing Unit Tests

### Basic Test Structure
```python
import pytest
from unittest.mock import Mock, patch

from kailash.nodes.data.readers import CSVReaderNode
from kailash.sdk_exceptions import NodeExecutionError


class TestCSVReaderNode:
    """Test cases for CSVReaderNode."""

    @pytest.fixture
    def node(self):
        """Create a node instance for testing."""
        return CSVReaderNode()

    @pytest.fixture
    def valid_config(self):
        """Valid configuration for the node."""
        return {"file_path": "test.csv", "delimiter": ","}

    def test_validate_config_with_valid_config(self, node, valid_config):
        """Test config validation with valid configuration."""
        # Act
        result = node.validate_config(valid_config)

        # Assert
        assert result == valid_config

    def test_validate_config_missing_file_path(self, node):
        """Test config validation with missing file_path."""
        # Arrange
        invalid_config = {"delimiter": ","}

        # Act & Assert
        with pytest.raises(ValueError, match="file_path is required"):
            node.validate_config(invalid_config)

    @patch("builtins.open", create=True)
    @patch("csv.DictReader")
    def test_execute_reads_csv_file(self, mock_reader, mock_open, node, valid_config):
        """Test that execute properly reads CSV file."""
        # Arrange
        node.config = valid_config
        mock_reader.return_value = [
            {"name": "John", "age": "25"},
            {"name": "Jane", "age": "30"}
        ]

        # Act
        result = node.execute({})

        # Assert
        assert result["default"] == [
            {"name": "John", "age": "25"},
            {"name": "Jane", "age": "30"}
        ]
        mock_open.assert_called_once_with("test.csv", "r", encoding="utf-8")
```

### Testing Patterns

#### Arrange-Act-Assert (AAA)
```python
def test_data_transformation():
    # Arrange - Set up test data and dependencies
    transformer = DataTransformer()
    input_data = [1, 2, 3, 4, 5]

    # Act - Execute the code under test
    result = transformer.filter_even(input_data)

    # Assert - Verify the results
    assert result == [2, 4]
```

#### Parameterized Tests
```python
@pytest.mark.parametrize("input_value,expected", [
    ("hello", "HELLO"),
    ("World", "WORLD"),
    ("", ""),
    ("123", "123"),
])
def test_uppercase_conversion(input_value, expected):
    assert input_value.upper() == expected
```

#### Testing Exceptions
```python
def test_node_execution_error():
    node = BrokenNode()

    with pytest.raises(NodeExecutionError) as exc_info:
        node.execute({})

    assert "Execution failed" in str(exc_info.value)
    assert exc_info.value.node_id == node.id
```

## Fixtures and Mocking

### Common Fixtures
```python
# conftest.py
import pytest
from kailash.workflow.graph import Workflow
from kailash.runtime.local import LocalRuntime

@pytest.fixture
def workflow():
    """Create a basic workflow for testing."""
    return Workflow(
        workflow_id="test_workflow",
        name="Test Workflow"
    )

@pytest.fixture
def runtime():
    """Create a runtime for testing."""
    return LocalRuntime()

@pytest.fixture
def sample_data():
    """Sample data for testing."""
    return [
        {"id": 1, "name": "Alice", "age": 30},
        {"id": 2, "name": "Bob", "age": 25},
        {"id": 3, "name": "Charlie", "age": 35}
    ]
```

### Mocking External Dependencies
```python
from unittest.mock import patch, Mock
from kailash.nodes.api.http import HTTPRequestNode

@patch("requests.get")
def test_api_node_makes_request(mock_get):
    # Arrange
    mock_response = Mock()
    mock_response.json.return_value = {"status": "success"}
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    node = HTTPRequestNode(url="https://api.example.com/data")

    # Act
    result = node.execute({})

    # Assert
    mock_get.assert_called_once_with(
        "https://api.example.com/data",
        params=None,
        headers=None,
        timeout=30
    )
    assert result["response"] == {"status": "success"}
```

## Integration Tests

### Testing Workflows
```python
class TestWorkflowIntegration:
    """Integration tests for complete workflows."""

    def test_csv_processing_workflow(self, tmp_path):
        """Test complete CSV processing workflow."""
        # Arrange - Create test data
        input_file = tmp_path / "input.csv"
        output_file = tmp_path / "output.csv"

        input_file.write_text("name,age\nJohn,25\nJane,30\n")

        # Create workflow
        from kailash.workflow.graph import Workflow
        from kailash.nodes.data.readers import CSVReaderNode
        from kailash.nodes.data.writers import CSVWriterNode
        from kailash.nodes.transform import DataTransformerNode

        workflow = Workflow(
            workflow_id="csv_processing",
            name="CSV Processing"
        )
        workflow.add_node(
            "reader",
            CSVReaderNode,
            file_path=str(input_file)
        )
        workflow.add_node(
            "filter",
            DataTransformerNode,
            operations=[{"type": "filter", "condition": "age > 25"}]
        )
        workflow.add_node(
            "writer",
            CSVWriterNode,
            file_path=str(output_file)
        )

        workflow.connect("reader", "filter", mapping={"data": "input"})
        workflow.connect("filter", "writer", mapping={"output": "data"})

        # Act
        from kailash.runtime.local import LocalRuntime
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        # Assert
        assert output_file.exists()
        output_content = output_file.read_text()
        assert "Jane,30" in output_content
        assert "John,25" not in output_content
```

### Testing Node Communication
```python
def test_node_data_passing():
    """Test that data passes correctly between nodes."""
    from kailash.workflow.graph import Workflow
    from kailash.runtime.local import LocalRuntime
    # Import your custom nodes here
    # from myproject.nodes import DataSourceNode, MultiplyNode, DataSinkNode

    workflow = Workflow(
        workflow_id="data_passing",
        name="Data Passing Test"
    )

    # Add nodes (example with hypothetical custom nodes)
    # workflow.add_node("source", DataSourceNode, data=[1, 2, 3])
    # workflow.add_node("multiplier", MultiplyNode, factor=2)
    # workflow.add_node("sink", DataSinkNode)

    # Connect with mapping
    # workflow.connect("source", "multiplier", mapping={"data": "input"})
    # workflow.connect("multiplier", "sink", mapping={"output": "data"})

    # Execute through runtime (RECOMMENDED)
    # runtime = LocalRuntime()
    # results, run_id = runtime.execute(workflow)
    # INVALID: workflow.execute(runtime) does NOT exist

    # Verify data transformation
    assert results["sink"]["collected_data"] == [2, 4, 6]
```

## Performance Tests

```python
import time
import pytest

@pytest.mark.performance
def test_large_dataset_processing():
    """Test performance with large datasets."""
    # Generate large dataset
    large_data = [{"id": i, "value": i * 2} for i in range(10000)]

    node = DataTransformerNode()
    node.config = {
        "operations": [
            {"type": "filter", "condition": "value > 5000"},
            {"type": "sort", "key": "value", "reverse": True}
        ]
    }

    # Measure execution time
    start_time = time.time()
    result = node.execute({"data": large_data})
    execution_time = time.time() - start_time

    # Assert performance requirements
    assert execution_time < 1.0  # Should complete in under 1 second
    assert len(result["transformed"]) < len(large_data)
```

## Test Configuration

### pytest.ini
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --cov=kailash
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=80
markers =
    slow: marks tests as slow
    integration: marks tests as integration tests
    performance: marks tests as performance tests
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=kailash

# Run specific test file
pytest tests/test_nodes/test_data.py

# Run specific test
pytest tests/test_nodes/test_data.py::TestCSVReaderNode::test_execute_reads_csv_file

# Run tests matching pattern
pytest -k "csv"

# Run excluding slow tests
pytest -m "not slow"

# Run only integration tests
pytest -m integration

# Run with verbose output
pytest -v

# Run with parallel execution
pytest -n auto
```

## Testing Best Practices

### 1. Test Independence
- Each test should be independent
- Use fixtures for setup/teardown
- Don't rely on test execution order

### 2. Clear Test Names
- Test names should describe what they test
- Include the scenario being tested
- Bad: `test_execute`
- Good: `test_execute_with_empty_input_returns_empty_result`

### 3. Single Assertion Focus
- Each test should test one thing
- Multiple assertions are okay if testing related aspects
- Split complex tests into multiple focused tests

### 4. Use Appropriate Assertions
```python
# Specific assertions are better
assert result == expected  # Good
assert result  # Less clear

# Use pytest's rich assertions
assert "error" in str(excinfo.value)
assert len(items) == 5
assert all(item > 0 for item in values)
```

### 5. Mock External Dependencies
- Mock file I/O, network calls, databases
- Test the logic, not the external systems
- Use `unittest.mock` or `pytest-mock`

### 6. Test Edge Cases
- Empty inputs
- None values
- Maximum/minimum values
- Invalid types
- Boundary conditions

### 7. Test Error Conditions
- Invalid inputs
- Missing required parameters
- Network failures
- File not found
- Permission errors

## Continuous Integration

Tests run automatically on:
- Every commit (pre-commit hooks)
- Every pull request (GitHub Actions)
- Before deployment

### GitHub Actions Workflow
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -e .[dev]
      - run: pytest --cov=kailash
```
