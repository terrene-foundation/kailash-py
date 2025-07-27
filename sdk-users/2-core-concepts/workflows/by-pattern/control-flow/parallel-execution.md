# Parallel Execution Patterns

**Concurrent processing for performance and scalability** - Execute multiple workflow paths simultaneously.

## 📋 Pattern Overview

Parallel execution allows workflows to process multiple independent tasks concurrently, dramatically improving performance for I/O-bound operations like API calls, database queries, and file processing. Kailash automatically handles parallel execution when workflow paths don't have dependencies.

## 🚀 Working Examples

### Basic Parallel API Aggregation
**Script**: [scripts/parallel_execution_basic.py](scripts/parallel_execution_basic.py)

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.api import RestClientNode
from kailash.nodes.logic import MergeNode
from kailash.runtime.local import LocalRuntime

def create_parallel_api_workflow():
    """Aggregate data from multiple APIs in parallel."""
    workflow = WorkflowBuilder()

    # Define multiple API endpoints to call in parallel
    apis = {
        "weather": "https://api.weather.com/current",
        "news": "https://api.news.com/headlines",
        "stocks": "https://api.stocks.com/market",
        "traffic": "https://api.traffic.com/conditions"
    }

    # Create API nodes - these will execute in parallel
    for name, url in apis.items():
        workflow.add_node("RestClientNode", f"{name}_api", {
            "url": url,
            "method": "GET",
            "timeout": 5000  # 5 second timeout
        })

    # Merge all results
    workflow.add_node("MergeNode", "data_merger", {
        "merge_strategy": "combine_dict"
    })

    # Connect all APIs to merger - automatic parallel execution
    for name in apis.keys():
        workflow.add_connection(f"{name}_api", "result", "data_merger", "input")

    return workflow

# Execute - all APIs called simultaneously
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "weather_api": {"headers": {"API-Key": "weather-key"}},
    "news_api": {"headers": {"API-Key": "news-key"}},
    "stocks_api": {"headers": {"API-Key": "stocks-key"}},
    "traffic_api": {"headers": {"API-Key": "traffic-key"}}
})

```

### Parallel Data Processing
**Script**: [scripts/parallel_execution_batch.py](scripts/parallel_execution_batch.py)

```python
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.transform import DataTransformer
from kailash.nodes.code import PythonCodeNode

def create_parallel_batch_processor():
    """Process large datasets in parallel chunks."""
    workflow = WorkflowBuilder()

    # Split data into chunks for parallel processing
    workflow.add_node("PythonCodeNode", "data_splitter", {
        "code": '''
import math

# Split data into chunks for parallel processing
chunk_size = 1000
total_records = len(input_data)
num_chunks = math.ceil(total_records / chunk_size)

chunks = []
for i in range(num_chunks):
    start_idx = i * chunk_size
    end_idx = min((i + 1) * chunk_size, total_records)
    chunk = {
        'chunk_id': i,
        'data': input_data[start_idx:end_idx],
        'start_index': start_idx,
        'end_index': end_idx
    }
    chunks.append(chunk)

result = {
    'chunks': chunks,
    'total_chunks': num_chunks,
    'chunk_size': chunk_size
}
'''
    })

    # Create parallel processors for each chunk type
    chunk_processors = []
    for i in range(4):  # Assume 4 parallel processors
        workflow.add_node("PythonCodeNode", f"chunk_processor_{i}", {
            "code": """
# Complex transformation that benefits from parallelization
processed_records = []
for record in input_data:
    processed_record = {
        **record,
        'processed': True,
        'score': len(str(record)),  # Simple score calculation
        'category': 'default',
        'enriched_data': {'timestamp': 'now'}
    }
    processed_records.append(processed_record)

result = processed_records
"""
        })
        chunk_processors.append(f"chunk_processor_{i}")

    # Distribute chunks to processors
    workflow.add_node("PythonCodeNode", "chunk_router", {
        "code": '''
# Distribute chunks across available processors
chunks = splitter_result['chunks']
num_processors = 4

distributed_chunks = {f'processor_{i}': [] for i in range(num_processors)}

for idx, chunk in enumerate(chunks):
    processor_id = idx % num_processors
    distributed_chunks[f'processor_{processor_id}'].append(chunk)

result = distributed_chunks
'''
    })

    # Result aggregator
    workflow.add_node("PythonCodeNode", "result_aggregator", {
        "code": '''
# Combine results from all parallel processors
all_results = []

# Collect from all processor outputs
for processor_id in range(4):
    processor_results = globals().get(f'processor_{processor_id}_results', [])
    all_results.extend(processor_results)

# Sort by original index to maintain order
all_results.sort(key=lambda x: x.get('original_index', 0))

result = {
    'processed_records': all_results,
    'total_processed': len(all_results),
    'processing_complete': True
}
'''
    })

    return workflow

```

### Parallel Workflow with Error Isolation
**Script**: [scripts/parallel_execution_resilient.py](scripts/parallel_execution_resilient.py)

```python
def create_resilient_parallel_workflow():
    """Parallel execution with isolated error handling."""
    workflow = WorkflowBuilder()

    # Define services with different reliability levels
    services = [
        {"name": "reliable_service", "url": "https://stable.api.com/data", "timeout": 3000},
        {"name": "flaky_service", "url": "https://flaky.api.com/data", "timeout": 5000},
        {"name": "slow_service", "url": "https://slow.api.com/data", "timeout": 10000}
    ]

    # Create isolated processing paths
    for service in services:
        # API call
        workflow.add_node("RestClientNode", f"{service['name']}_api", {
            "url": service['url'],
            "timeout": service['timeout']
        })

        # Error checker for this service
        workflow.add_node("SwitchNode", f"{service['name']}_checker", {
            "condition": "status_code == 200 and response is not None"
        })

        # Success processor
        workflow.add_node("PythonCodeNode", f"{service['name']}_success", {
            "code": f"""
result = {{
    'service': '{service['name']}',
    'status': 'success',
    'data': input_data
}}
"""
        })

        # Failure handler with fallback
        workflow.add_node("PythonCodeNode", f"{service['name']}_failure", {
            "code": f'''
# Handle failure with appropriate fallback
fallback_data = {{
    'service': '{service['name']}',
    'status': 'failed',
    'data': {{'message': 'Using cached data', 'cached_values': [1, 2, 3]}},
    'error': error_info.get('message', 'Unknown error'),
    'fallback_used': True
}}

result = fallback_data
'''
        })

        # Connect with error isolation
        workflow.add_connection(f"{service['name']}_api", "result", f"{service['name']}_checker", "input")
        workflow.add_connection(f"{service['name']}_checker", "pass", f"{service['name']}_success", "input")
        workflow.add_connection(f"{service['name']}_checker", "fail", f"{service['name']}_failure", "input")

    # Aggregate all results (successes and failures)
    workflow.add_node("MergeNode", "final_aggregator", {
        "merge_strategy": "collect_all"
    })

    # Connect all paths to aggregator
    for service in services:
        workflow.add_connection(f"{service['name']}_success", "result", "final_aggregator", "input")
        workflow.add_connection(f"{service['name']}_failure", "result", "final_aggregator", "input")

    return workflow

```

### Parallel Map-Reduce Pattern
**Script**: [scripts/parallel_execution_mapreduce.py](scripts/parallel_execution_mapreduce.py)

```python
def create_mapreduce_workflow():
    """Classic map-reduce pattern with parallel execution."""
    workflow = WorkflowBuilder()

    # Mapper nodes - process data in parallel
    num_mappers = 4
    for i in range(num_mappers):
        workflow.add_node("PythonCodeNode", f"mapper_{i}", {
            "code": '''
# Map function - process assigned data partition
mapped_results = []

for record in data_partition:
    # Example: word count mapping
    words = record.get('text', '').lower().split()
    for word in words:
        mapped_results.append({'key': word, 'value': 1})

result = {
    'mapped_data': mapped_results,
    'partition_id': partition_id,
    'records_processed': len(data_partition) if 'data_partition' in locals() else 0
}
'''
        })

    # Shuffle phase - group by key
    workflow.add_node("PythonCodeNode", "shuffler", {
        "code": '''
# Collect all mapped results and group by key
from collections import defaultdict

grouped_data = defaultdict(list)

# Collect from all mappers
for i in range(4):
    mapper_results = globals().get(f'mapper_{i}_results', {})
    mapped_data = mapper_results.get('mapped_data', [])

    for item in mapped_data:
        key = item['key']
        value = item['value']
        grouped_data[key].append(value)

# Convert to list for reducers
shuffled_data = [
    {'key': key, 'values': values}
    for key, values in grouped_data.items()
]

result = {
    'shuffled_data': shuffled_data,
    'unique_keys': len(grouped_data)
}
'''
    })

    # Reducer nodes - aggregate in parallel
    num_reducers = 2
    for i in range(num_reducers):
        workflow.add_node("PythonCodeNode", f"reducer_{i}", {
            "code": '''
# Reduce function - aggregate values for assigned keys
reduced_results = []

for item in assigned_keys:
    key = item['key']
    values = item['values']

    # Example: sum for word count
    total = sum(values)
    reduced_results.append({'key': key, 'count': total})

result = {
    'reduced_data': reduced_results,
    'reducer_id': reducer_id
}
'''
        })

    # Connect map-reduce pipeline
    # Input -> Mappers (parallel)
    for i in range(num_mappers):
        workflow.add_connection("input_data", "result", f"mapper_{i}", "data_partition")

    # Mappers -> Shuffler
    for i in range(num_mappers):
        workflow.add_connection(f"mapper_{i}", "result", "shuffler", "input")

    # Shuffler -> Reducers (parallel)
    for i in range(num_reducers):
        workflow.add_connection("shuffler", "result", f"reducer_{i}", "assigned_keys")

    # Reducers -> Final output
    workflow.add_connection("reducer_0", "output_combiner", "result", "reducer_0_results")
    workflow.add_connection("reducer_1", "output_combiner", "result", "reducer_1_results")

    return workflow

```

## 🎯 Common Use Cases

### 1. Multi-Source Data Aggregation
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

# Gather data from multiple databases simultaneously
for db_name in ["users_db", "orders_db", "inventory_db"]:
    workflow.add_node("SQLDatabaseNode", f"{db_name}_reader", {
        "connection_string": f"postgresql://localhost/{db_name}",
        "query": "SELECT * FROM main_table",
        "operation": "select"
    })

# All queries execute in parallel
workflow.add_node("MergeNode", "data_joiner", {
    "merge_strategy": "combine_all"
})
for db_name in ["users_db", "orders_db", "inventory_db"]:
    workflow.add_connection(f"{db_name}_reader", "result", "data_joiner", "input")

```

### 2. Parallel Validation
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

# Run multiple validation checks concurrently
validators = [
    "schema_validator",
    "business_rules_validator",
    "security_validator",
    "compliance_validator"
]

for validator in validators:
    workflow.add_node("PythonCodeNode", validator, {
        "code": f"""
# {validator} validation logic
result = {{
    'validator': '{validator}',
    'valid': True,
    'errors': [],
    'warnings': []
}}
"""
    })
    workflow.add_connection("input_data", "result", validator, "input")
    workflow.add_connection(validator, "result", "validation_aggregator", "input")

```

### 3. Fan-Out Notifications
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

# Send notifications through multiple channels
channels = ["email", "sms", "push", "webhook"]

for channel in channels:
    workflow.add_node("HTTPRequestNode", f"{channel}_sender", {
        "url": f"https://api.{channel}.com/send",
        "method": "POST",
        "headers": {"Content-Type": "application/json"}
    })
    workflow.add_connection("notification_trigger", "result", f"{channel}_sender", "input")

```

### 4. Parallel File Processing
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

# Process multiple files concurrently
file_processors = []
num_workers = 4
for i in range(num_workers):
    workflow.add_node("PythonCodeNode", f"processor_{i}", {
        "code": """
# Process files from queue
processed_files = []
for file_path in input_data.get('files', []):
    # Process each file
    processed_files.append({
        'file': file_path,
        'status': 'processed',
        'size': len(file_path)  # Mock processing
    })

result = processed_files
"""
    })
    file_processors.append(f"processor_{i}")
    workflow.add_connection("file_queue", "result", f"processor_{i}", "input")
    workflow.add_connection(f"processor_{i}", "result", "file_aggregator", "input")

```

## 📊 Best Practices

### 1. **Ensure Independence**
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

# GOOD: Independent parallel paths
workflow.add_node("PythonCodeNode", "processor_1", {
    "code": "result = {'processor': 1, 'data': input_data}"
})
workflow.add_node("PythonCodeNode", "processor_2", {
    "code": "result = {'processor': 2, 'data': input_data}"
})

# BAD: Shared state causes race conditions (avoid this)
# shared_state = {}  # Don't use shared state in parallel paths

```

### 2. **Set Appropriate Timeouts**
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

# GOOD: Different timeouts for different services
workflow.add_node("RestClientNode", "fast_api", {
    "url": "https://fast.api.com/data",
    "timeout": 2000  # 2 seconds
})
workflow.add_node("RestClientNode", "slow_api", {
    "url": "https://slow.api.com/data",
    "timeout": 10000  # 10 seconds
})

```

### 3. **Handle Partial Failures**
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

# GOOD: Continue even if some parallel tasks fail
workflow.add_node("MergeNode", "aggregator", {
    "merge_strategy": "collect_available",  # Skip failed branches
    "required_inputs": 2  # Need at least 2 of 5 to succeed
})

```

### 4. **Monitor Resource Usage**
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

# GOOD: Limit parallelism for resource-intensive tasks
runtime = LocalRuntime()
runtime_config = {
    "max_parallel_tasks": 10,  # Limit concurrent execution
    "task_timeout": 30000,     # 30 second timeout
    "memory_limit": "2GB"      # Per-task memory limit
}
# Apply config when executing: runtime.execute(workflow.build(), config=runtime_config)

```

## 🔗 Related Examples

- **Examples Directory**: `/examples/workflow_examples/workflow_parallel.py`
- **With Error Handling**: `/examples/workflow_examples/workflow_error_handling.py`
- **Performance Testing**: `/examples/workflow_examples/workflow_performance.py`
- **Map-Reduce Pattern**: See examples in cyclic workflows

## ⚠️ Common Pitfalls

1. **Shared State**
   - Avoid modifying shared variables in parallel paths
   - Use proper synchronization if needed

2. **Resource Exhaustion**
   - Set limits on parallel execution
   - Monitor memory and CPU usage

3. **Ordering Dependencies**
   - Don't assume execution order in parallel paths
   - Use explicit sequencing when order matters

4. **Error Propagation**
   - Decide how to handle partial failures
   - Consider circuit breakers for cascading failures

---

*Parallel execution is key to building high-performance workflows. Use these patterns to maximize throughput while maintaining reliability.*
