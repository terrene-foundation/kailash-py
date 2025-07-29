# Best Practices

General guidelines and recommendations for building effective Kailash workflows.

## Node Design Best Practices

### 1. Single Responsibility Principle
**Each node should do one thing well**

```python
# ❌ Bad: Node doing multiple unrelated tasks
class BadNode(Node):
    def run(self, **kwargs):
        # Reading file
        data = read_csv(kwargs['file_path'])

        # Processing data
        processed = transform_data(data)

        # Sending email
        send_email(processed)

        # Writing to database
        save_to_database(processed)

        return processed

# ✅ Good: Separate nodes for each responsibility
class CSVReaderNode(Node):
    def run(self, **kwargs):
        return {'data': read_csv(kwargs['file_path'])}

class DataTransformerNode(Node):
    def run(self, **kwargs):
        return {'result': transform_data(kwargs['data'])}

class EmailNotifierNode(Node):
    def run(self, **kwargs):
        send_email(kwargs['data'])
        return {'sent': True}

class DatabaseWriterNode(Node):
    def run(self, **kwargs):
        save_to_database(kwargs['data'])
        return {'saved': True}

```

### 2. Clear Interfaces
**Define explicit input/output schemas**

```python
from kailash.nodes.base import Node, NodeParameter

class WellDefinedNode(Node):
    """Node with clear parameter definitions"""

    def get_parameters(self):
        return {
            'input_data': NodeParameter(
                type=list,
                description="List of dictionaries containing customer records",
                required=True,
                schema={
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'id': {'type': 'integer'},
                            'name': {'type': 'string'},
                            'value': {'type': 'number'}
                        },
                        'required': ['id', 'name']
                    }
                }
            ),
            'threshold': NodeParameter(
                type=float,
                description="Minimum value threshold for filtering",
                required=False,
                default=100.0
            )
        }

    def run(self, **kwargs):
        data = kwargs['input_data']
        threshold = kwargs.get('threshold', 100.0)

        # Process with confidence in data structure
        filtered = [r for r in data if r.get('value', 0) > threshold]

        return {
            'filtered_data': filtered,
            'removed_count': len(data) - len(filtered),
            'threshold_used': threshold
        }

```

### 3. Error Handling
**Handle errors gracefully with meaningful messages**

```python
class RobustNode(Node):
    """Node with comprehensive error handling"""

    def run(self, **kwargs):
        try:
            # Validate inputs
            if 'data' not in kwargs:
                raise ValueError("Required parameter 'data' is missing")

            data = kwargs['data']

            # Type checking
            if not isinstance(data, list):
                raise TypeError(f"Expected list, got {type(data).__name__}")

            # Business logic validation
            if not data:
                self.logger.warning("Empty data received, returning empty result")
                return {'result': [], 'warning': 'No data to process'}

            # Process data with specific error handling
            results = []
            errors = []

            for i, item in enumerate(data):
                try:
                    processed = self.process_item(item)
                    results.append(processed)
                except Exception as e:
                    errors.append({
                        'index': i,
                        'item': item,
                        'error': str(e)
                    })
                    self.logger.error(f"Failed to process item {i}: {e}")

            # Return partial results with error information
            return {
                'result': results,
                'success_count': len(results),
                'error_count': len(errors),
                'errors': errors
            }

        except Exception as e:
            # Log full error for debugging
            self.logger.exception("Node execution failed")

            # Return error in structured format
            return {
                'error': {
                    'type': type(e).__name__,
                    'message': str(e),
                    'node': self.__class__.__name__
                }
            }

```

### 4. Documentation
**Include comprehensive docstrings with examples**

```python
class DocumentedNode(Node):
    """Process customer data with configurable filters.

    This node filters customer records based on multiple criteria
    and enriches them with calculated fields.

    Parameters
    ----------
    customers : list[dict]
        List of customer records with required fields:
        - id (int): Customer identifier
        - age (int): Customer age
        - purchase_history (list): List of purchase amounts

    filters : dict, optional
        Filtering criteria:
        - min_age (int): Minimum age (default: 18)
        - min_purchases (int): Minimum purchase count (default: 1)
        - active_only (bool): Filter inactive customers (default: True)

    Returns
    -------
    dict
        Processed results containing:
        - customers (list): Filtered and enriched customer records
        - stats (dict): Processing statistics
        - metadata (dict): Execution metadata

    Examples
    --------
    >>> node = DocumentedNode()
    >>> result = node.execute(
    ...     customers=[
    ...         {'id': 1, 'age': 25, 'purchase_history': [100, 200]},
    ...         {'id': 2, 'age': 17, 'purchase_history': [50]}
    ...     ],
    ...     filters={'min_age': 18}
    ... )
    >>> len(result['customers'])
    1
    >>> result['customers'][0]['total_purchases']
    300
    """

    def run(self, **kwargs):
        # Implementation here
        pass

```

## Workflow Design Best Practices

### 1. Modularity
**Build small, reusable workflows**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Create focused, reusable workflows
def create_validation_workflow():
    """Reusable validation workflow"""
    workflow = WorkflowBuilder()

workflow = WorkflowBuilder()
workflow.add_node("SchemaValidatorNode", "schema_validator", {}))
workflow = WorkflowBuilder()
workflow.add_node("BusinessRulesNode", "business_rules", {}))
workflow = WorkflowBuilder()
workflow.add_node("QualityCheckerNode", "quality_checker", {}))

workflow = WorkflowBuilder()
workflow.add_connection("schema_validator", "result", "business_rules", "input")
workflow = WorkflowBuilder()
workflow.add_connection("business_rules", "result", "quality_checker", "input")

    return workflow

def create_enrichment_workflow():
    """Reusable enrichment workflow"""
    workflow = WorkflowBuilder()

workflow = WorkflowBuilder()
workflow.add_node("GeocoderNode", "geocoder", {}))
workflow = WorkflowBuilder()
workflow.add_node("CustomerScorerNode", "customer_scorer", {}))
workflow = WorkflowBuilder()
workflow.add_node("CategoryTaggerNode", "category_tagger", {}))

workflow = WorkflowBuilder()
workflow.add_connection("geocoder", "result", "customer_scorer", "input")
workflow = WorkflowBuilder()
workflow.add_connection("customer_scorer", "result", "category_tagger", "input")

    return workflow

# Compose workflows together
main_workflow = WorkflowBuilder()

workflow = WorkflowBuilder()
workflow.add_node("WorkflowNode", "validator", {}),
    workflow=create_validation_workflow())
workflow = WorkflowBuilder()
workflow.add_node("WorkflowNode", "enricher", {}),
    workflow=create_enrichment_workflow())
workflow = WorkflowBuilder()
workflow.add_node("OutputNode", "output", {}))

workflow = WorkflowBuilder()
workflow.add_connection("validator", "result", "enricher", "input")
workflow = WorkflowBuilder()
workflow.add_connection("enricher", "result", "output", "input")

```

### 2. Validation
**Always validate workflows before execution**

```python
from kailash.workflow.safety import validate_workflow

# Create workflow
workflow = create_complex_workflow()

# Validate before execution
validation_result = validate_workflow(workflow)

if not validation_result.is_valid:
    print("Workflow validation failed:")
    for error in validation_result.errors:
        print(f"  - {error}")
    raise ValueError("Invalid workflow configuration")

# Safe to execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

### 3. Testing
**Test workflows with edge cases**

```python
import pytest
from kailash.runtime.testing import TestRuntime

def test_workflow_with_empty_data():
    """Test workflow handles empty data gracefully"""
    workflow = create_data_pipeline()
    runtime = TestRuntime()

    # Test with empty data
    results, run_id = runtime.execute(workflow, parameters={
        "reader": {"data": []}
    })

    assert results['processor']['result'] == []
    assert results['processor']['warning'] == 'No data to process'

def test_workflow_with_invalid_data():
    """Test workflow handles invalid data"""
    workflow = create_data_pipeline()
    runtime = TestRuntime()

    # Test with invalid data types
    with pytest.raises(TypeError):
        runtime.execute(workflow, parameters={
            "reader": {"data": "not a list"}
        })

def test_workflow_performance():
    """Test workflow performance with large datasets"""
    workflow = create_data_pipeline()
    runtime = TestRuntime()

    # Generate large test dataset
    test_data = [{"id": i, "value": i * 10} for i in range(10000)]

    import time
    start_time = time.time()

    results, run_id = runtime.execute(workflow, parameters={
        "reader": {"data": test_data}
    })

    execution_time = time.time() - start_time

    # Performance assertions
    assert execution_time < 5.0  # Should complete in 5 seconds
    assert len(results['processor']['result']) == 10000

```

## Performance Best Practices

### 1. Async Operations
**Use async nodes for I/O operations**

```python
from kailash.nodes.base_async import AsyncNode
import aiohttp

class AsyncAPINode(AsyncNode):
    """Async node for parallel API calls"""

    async def async_run(self, **kwargs):
        urls = kwargs['urls']

        async with aiohttp.ClientSession() as session:
            # Parallel API calls
            tasks = [self.fetch_data(session, url) for url in urls]
            results = await asyncio.gather(*tasks)

        return {'results': results}

    async def fetch_data(self, session, url):
        try:
            async with session.get(url) as response:
                return await response.json()
        except Exception as e:
            return {'error': str(e), 'url': url}

# Use in async workflow
async_workflow = WorkflowBuilder()
workflow.async_workflow.add_node("AsyncAPINode", "fetcher", {}))

# Execute with async runtime
from kailash.runtime.async_local import AsyncLocalRuntime
runtime = AsyncLocalRuntime()
results = await runtime.execute(async_workflow, parameters={
    "fetcher": {"urls": ["http://api1.com", "http://api2.com", "http://api3.com"]}
})

```

### 2. Batch Processing
**Process data in chunks for large datasets**

```python
class BatchProcessorNode(Node):
    """Process large datasets in batches"""

    def get_parameters(self):
        return {
            'data': NodeParameter(type=list, required=True),
            'batch_size': NodeParameter(type=int, default=1000),
            'process_fn': NodeParameter(type=callable, required=True)
        }

    def run(self, **kwargs):
        data = kwargs['data']
        batch_size = kwargs.get('batch_size', 1000)
        process_fn = kwargs['process_fn']

        results = []
        total_batches = (len(data) + batch_size - 1) // batch_size

        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            self.logger.info(f"Processing batch {i//batch_size + 1}/{total_batches}")

            # Process batch
            batch_results = process_fn(batch)
            results.extend(batch_results)

            # Optional: yield intermediate results
            if hasattr(self, 'yield_intermediate'):
                self.yield_intermediate({
                    'batch_complete': i//batch_size + 1,
                    'total_batches': total_batches,
                    'processed_count': len(results)
                })

        return {'result': results, 'batch_count': total_batches}

```

### 3. Caching
**Cache expensive computations**

```python
from functools import lru_cache
import hashlib
import json

class CachedComputationNode(Node):
    """Node with intelligent caching"""

    def __init__(self, **config):
        super().__init__(**config)
        self.cache = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def run(self, **kwargs):
        # Generate cache key from inputs
        cache_key = self._generate_cache_key(kwargs)

        # Check cache
        if cache_key in self.cache:
            self.cache_hits += 1
            self.logger.info(f"Cache hit (rate: {self.cache_hit_rate:.1%})")
            return self.cache[cache_key]

        # Cache miss - compute result
        self.cache_misses += 1
        result = self._compute(kwargs)

        # Store in cache with size limit
        if len(self.cache) < 1000:  # Simple size limit
            self.cache[cache_key] = result
        else:
            # Evict oldest entry (simple FIFO)
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            self.cache[cache_key] = result

        return result

    def _generate_cache_key(self, params):
        """Generate stable cache key from parameters"""
        # Sort keys for consistency
        key_data = json.dumps(params, sort_keys=True)
        return hashlib.md5(key_data.encode()).hexdigest()

    def _compute(self, kwargs):
        """Expensive computation to cache"""
        # Simulate expensive operation
        import time
        time.sleep(1)

        data = kwargs['data']
        return {'computed': [item * 2 for item in data]}

    @property
    def cache_hit_rate(self):
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0

```

## Error Handling Best Practices

### 1. Fail Fast
**Validate inputs early**

```python
class ValidatingNode(Node):
    """Node that validates inputs immediately"""

    def run(self, **kwargs):
        # Validate required parameters first
        self._validate_required_params(kwargs)

        # Type validation
        self._validate_types(kwargs)

        # Business logic validation
        self._validate_business_rules(kwargs)

        # Only process after all validation passes
        return self._process(kwargs)

    def _validate_required_params(self, params):
        required = ['data', 'config']
        missing = [p for p in required if p not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")

    def _validate_types(self, params):
        if not isinstance(params['data'], list):
            raise TypeError(f"Expected data to be list, got {type(params['data'])}")

        if not isinstance(params['config'], dict):
            raise TypeError(f"Expected config to be dict, got {type(params['config'])}")

    def _validate_business_rules(self, params):
        if not params['data']:
            raise ValueError("Data cannot be empty")

        if len(params['data']) > 10000:
            raise ValueError("Data exceeds maximum size of 10000 records")

```

### 2. Graceful Degradation
**Continue with partial data when possible**

```python
class ResilientNode(Node):
    """Node that handles partial failures gracefully"""

    def run(self, **kwargs):
        data = kwargs['data']
        results = []
        failures = []

        for i, item in enumerate(data):
            try:
                # Try to process each item
                result = self.process_item(item)
                results.append(result)
            except Exception as e:
                # Log but continue processing
                self.logger.warning(f"Failed to process item {i}: {e}")
                failures.append({
                    'index': i,
                    'item': item,
                    'error': str(e)
                })

        # Return partial results with metadata
        success_rate = len(results) / len(data) if data else 0

        return {
            'results': results,
            'success_count': len(results),
            'failure_count': len(failures),
            'success_rate': success_rate,
            'failures': failures,
            'status': 'partial' if failures else 'complete'
        }

    def process_item(self, item):
        # Item processing logic
        if 'required_field' not in item:
            raise ValueError("Missing required field")
        return {'processed': item['required_field'].upper()}

```

## Code Organization Best Practices

### 1. Clear Structure
**Organize workflows logically**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Good: Clear, self-documenting workflow structure
workflow = WorkflowBuilder()

# Data ingestion phase
workflow.add_node("CSVReaderNode", "read_customers", {"file_path": "customers.csv"})
workflow.add_node("FilterNode", "validate_data", {"filter_condition": "id is not None and name != ''"})
workflow.add_connection("read_customers", "data", "validate_data", "data")

# Data enrichment phase
workflow.add_node("HTTPRequestNode", "add_location", {"url": "https://geocoding.api.com/geocode", "method": "POST"})
workflow.add_node("PythonCodeNode", "calculate_scores", {"code": "result = {'score': sum(data.get('values', [0])) if data else 0}"})
workflow.add_connection("validate_data", "result", "add_location", "input")
workflow.add_connection("add_location", "result", "calculate_scores", "input")

# Analytics phase
workflow.add_node("DataTransformer", "segment_customers", {"transformations": ["data['segment'] = 'high' if data.get('score', 0) > 80 else 'medium' if data.get('score', 0) > 50 else 'low'"]})
workflow.add_node("PythonCodeNode", "generate_report", {"code": "result = {'report': f'Analytics Report: {len(data)} records processed'}"})
workflow.add_connection("calculate_scores", "result", "segment_customers", "input")
workflow.add_connection("segment_customers", "result", "generate_report", "input")

# Output phase
workflow.add_node("DiscordAlertNode", "send_report", {"webhook_url": "https://discord.com/api/webhooks/example", "message": "Report generated"})
workflow.add_node("HTTPRequestNode", "update_dashboard", {"url": "https://dashboard.company.com/api/update", "method": "POST"})
workflow.add_connection("generate_report", "result", "send_report", "input")
workflow.add_connection("generate_report", "result", "update_dashboard", "input")

```

### 2. Configuration Management
**Separate configuration from code**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# config/workflow_config.yaml
"""
workflow:
  id: customer_pipeline
  name: Customer Processing Pipeline
  version: 2.1.0

nodes:
  reader:
    type: CSVReaderNode
    config:
      file_path: ${INPUT_PATH}/customers.csv
      encoding: utf-8
      delimiter: ","

  validator:
    type: SchemaValidatorNode
    config:
      schema_path: schemas/customer.json
      strict_mode: true

  processor:
    type: DataProcessorNode
    config:
      transformations:
        - type: uppercase
          fields: [name, city]
        - type: calculate_age
          birth_date_field: dob
        - type: categorize
          rules_file: rules/customer_categories.yaml

connections:
  - from: reader
    to: validator
    mapping:
      data: input_data
  - from: validator
    to: processor
    mapping:
      valid_data: data

execution:
  timeout: 3600
  retries: 3
  parallel: true
"""

# Load and use configuration
import yaml

with open('config/workflow_config.yaml') as f:
    config = yaml.safe_load(f)

workflow = WorkflowFactory.create_from_config(config)

```

## Testing Pattern Best Practices

### 1. Unit Testing Nodes
**Test nodes in isolation**

```python
import pytest
from unittest.mock import Mock, patch

class TestDataProcessorNode:
    """Test suite for DataProcessorNode"""

    def test_process_valid_data(self):
        """Test processing with valid data"""
        node = DataProcessorNode()
        result = node.execute(data=[
            {'id': 1, 'value': 100},
            {'id': 2, 'value': 200}
        ])

        assert len(result['processed']) == 2
        assert result['processed'][0]['value'] == 110  # 10% increase
        assert result['status'] == 'success'

    def test_process_empty_data(self):
        """Test handling of empty data"""
        node = DataProcessorNode()
        result = node.execute(data=[])

        assert result['processed'] == []
        assert result['warning'] == 'No data to process'

    def test_process_invalid_data(self):
        """Test error handling for invalid data"""
        node = DataProcessorNode()

        with pytest.raises(TypeError) as exc_info:
            node.execute(data="not a list")

        assert "Expected list" in str(exc_info.value)

    @patch('external_api.get_enrichment_data')
    def test_with_mocked_external_service(self, mock_api):
        """Test with mocked external dependencies"""
        mock_api.return_value = {'enrichment': 'data'}

        node = EnrichmentNode()
        result = node.execute(data=[{'id': 1}])

        assert mock_api.called
        assert result['enriched'][0]['enrichment'] == 'data'

```

### 2. Integration Testing Workflows
**Test complete workflow execution**

```python
from kailash.runtime.testing import TestRuntime

def test_complete_workflow():
    """Test end-to-end workflow execution"""
    workflow = create_customer_pipeline()
    runtime = TestRuntime()

    # Prepare test data
    test_data = [
        {'id': 1, 'name': 'john doe', 'age': 25, 'value': 1000},
        {'id': 2, 'name': 'jane smith', 'age': 30, 'value': 2000}
    ]

    # Execute workflow
    results, run_id = runtime.execute(workflow.build(), parameters={
        'reader': {'data': test_data}
    })

    # Verify results
    assert 'processor' in results
    assert len(results['processor']['result']) == 2

    # Check data transformation
    processed = results['processor']['result']
    assert processed[0]['name'] == 'JOHN DOE'  # Uppercase transform
    assert processed[0]['category'] == 'standard'  # Categorization

    # Verify workflow metadata
    assert runtime.get_execution_time(run_id) < 5.0  # Performance check
    assert runtime.get_node_status(run_id, 'validator') == 'success'

```

## See Also
- [Core Patterns](01-core-patterns.md) - Fundamental workflow patterns
- [Error Handling Patterns](05-error-handling-patterns.md) - Detailed error handling strategies
- [Performance Patterns](06-performance-patterns.md) - Performance optimization techniques
- [Security Patterns](10-security-patterns.md) - Security best practices
