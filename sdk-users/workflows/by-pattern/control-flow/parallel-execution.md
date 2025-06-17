# Parallel Execution Patterns

**Concurrent processing for performance and scalability** - Execute multiple workflow paths simultaneously.

## 📋 Pattern Overview

Parallel execution allows workflows to process multiple independent tasks concurrently, dramatically improving performance for I/O-bound operations like API calls, database queries, and file processing. Kailash automatically handles parallel execution when workflow paths don't have dependencies.

## 🚀 Working Examples

### Basic Parallel API Aggregation
**Script**: [scripts/parallel_execution_basic.py](scripts/parallel_execution_basic.py)

```python
from kailash import Workflow
from kailash.nodes.api import RestClientNode
from kailash.nodes.logic import MergeNode
from kailash.runtime import LocalRuntime

def create_parallel_api_workflow():
    """Aggregate data from multiple APIs in parallel."""
    workflow = Workflow("data_aggregation", "Parallel API Data Collection")

    # Define multiple API endpoints to call in parallel
    apis = {
        "weather": "https://api.weather.com/current",
        "news": "https://api.news.com/headlines",
        "stocks": "https://api.stocks.com/market",
        "traffic": "https://api.traffic.com/conditions"
    }

    # Create API nodes - these will execute in parallel
    for name, url in apis.items():
        api_node = RestClientNode(
            id=f"{name}_api",
            url=url,
            method="GET",
            timeout=5000  # 5 second timeout
        )
        workflow.add_node(f"{name}_api", api_node)

    # Merge all results
    merger = MergeNode(
        id="data_merger",
        merge_strategy="combine_dict"
    )
    workflow.add_node("data_merger", merger)

    # Connect all APIs to merger - automatic parallel execution
    for name in apis.keys():
        workflow.connect(f"{name}_api", "data_merger",
                        mapping={"response": f"{name}_data"})

    return workflow

# Execute - all APIs called simultaneously
runtime = LocalRuntime()
result = runtime.execute(workflow, parameters={
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
    workflow = Workflow("batch_processor", "Parallel Batch Processing")

    # Split data into chunks for parallel processing
    data_splitter = PythonCodeNode(
        name="data_splitter",
        code='''
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
    )
    workflow.add_node("data_splitter", data_splitter)

    # Create parallel processors for each chunk type
    chunk_processors = []
    for i in range(4):  # Assume 4 parallel processors
        processor = DataTransformer(
            id=f"chunk_processor_{i}",
            transformations=[
                # Complex transformation that benefits from parallelization
                """lambda record: {
                    **record,
                    'processed': True,
                    'score': calculate_complex_score(record),
                    'category': classify_record(record),
                    'enriched_data': fetch_enrichment(record)
                }"""
            ]
        )
        workflow.add_node(f"chunk_processor_{i}", processor)
        chunk_processors.append(f"chunk_processor_{i}")

    # Distribute chunks to processors
    chunk_router = PythonCodeNode(
        name="chunk_router",
        code='''
# Distribute chunks across available processors
chunks = splitter_result['chunks']
num_processors = 4

distributed_chunks = {f'processor_{i}': [] for i in range(num_processors)}

for idx, chunk in enumerate(chunks):
    processor_id = idx % num_processors
    distributed_chunks[f'processor_{processor_id}'].append(chunk)

result = distributed_chunks
'''
    )
    workflow.add_node("chunk_router", chunk_router)

    # Result aggregator
    result_aggregator = PythonCodeNode(
        name="result_aggregator",
        code='''
# Combine results from all parallel processors
all_results = []

# Collect from all processor outputs
for processor_id in range(4):
    processor_results = locals().get(f'processor_{processor_id}_results', [])
    all_results.extend(processor_results)

# Sort by original index to maintain order
all_results.sort(key=lambda x: x.get('original_index', 0))

result = {
    'processed_records': all_results,
    'total_processed': len(all_results),
    'processing_complete': True
}
'''
    )
    workflow.add_node("result_aggregator", result_aggregator)

    return workflow

```

### Parallel Workflow with Error Isolation
**Script**: [scripts/parallel_execution_resilient.py](scripts/parallel_execution_resilient.py)

```python
def create_resilient_parallel_workflow():
    """Parallel execution with isolated error handling."""
    workflow = Workflow("resilient_parallel", "Fault-Tolerant Parallel Processing")

    # Define services with different reliability levels
    services = [
        {"name": "reliable_service", "url": "https://stable.api.com/data", "timeout": 3000},
        {"name": "flaky_service", "url": "https://flaky.api.com/data", "timeout": 5000},
        {"name": "slow_service", "url": "https://slow.api.com/data", "timeout": 10000}
    ]

    # Create isolated processing paths
    for service in services:
        # API call
        api_node = RestClientNode(
            id=f"{service['name']}_api",
            url=service['url'],
            timeout=service['timeout']
        )
        workflow.add_node(f"{service['name']}_api", api_node)

        # Error checker for this service
        error_checker = SwitchNode(
            id=f"{service['name']}_checker",
            condition="status_code == 200 and response is not None"
        )
        workflow.add_node(f"{service['name']}_checker", error_checker)

        # Success processor
        success_processor = DataTransformer(
            id=f"{service['name']}_success",
            transformations=[
                f"lambda x: {{'service': '{service['name']}', 'status': 'success', 'data': x}}"
            ]
        )
        workflow.add_node(f"{service['name']}_success", success_processor)

        # Failure handler with fallback
        failure_handler = PythonCodeNode(
            name=f"{service['name']}_failure",
            code=f'''
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
        )
        workflow.add_node(f"{service['name']}_failure", failure_handler)

        # Connect with error isolation
        workflow.connect(f"{service['name']}_api", f"{service['name']}_checker")
        workflow.connect(f"{service['name']}_checker", f"{service['name']}_success",
                        output_key="true_output", mapping={"response": "data"})
        workflow.connect(f"{service['name']}_checker", f"{service['name']}_failure",
                        output_key="false_output", mapping={"error": "error_info"})

    # Aggregate all results (successes and failures)
    final_aggregator = MergeNode(
        id="final_aggregator",
        merge_strategy="collect_all"
    )
    workflow.add_node("final_aggregator", final_aggregator)

    # Connect all paths to aggregator
    for service in services:
        workflow.connect(f"{service['name']}_success", "final_aggregator",
                        mapping={"result": f"{service['name']}_result"})
        workflow.connect(f"{service['name']}_failure", "final_aggregator",
                        mapping={"result": f"{service['name']}_result"})

    return workflow

```

### Parallel Map-Reduce Pattern
**Script**: [scripts/parallel_execution_mapreduce.py](scripts/parallel_execution_mapreduce.py)

```python
def create_mapreduce_workflow():
    """Classic map-reduce pattern with parallel execution."""
    workflow = Workflow("mapreduce", "Parallel Map-Reduce Processing")

    # Mapper nodes - process data in parallel
    num_mappers = 4
    for i in range(num_mappers):
        mapper = PythonCodeNode(
            name=f"mapper_{i}",
            code='''
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
    'records_processed': len(data_partition)
}
'''
        )
        workflow.add_node(f"mapper_{i}", mapper)

    # Shuffle phase - group by key
    shuffler = PythonCodeNode(
        name="shuffler",
        code='''
# Collect all mapped results and group by key
from collections import defaultdict

grouped_data = defaultdict(list)

# Collect from all mappers
for i in range(4):
    mapper_results = locals().get(f'mapper_{i}_results', {})
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
    )
    workflow.add_node("shuffler", shuffler)

    # Reducer nodes - aggregate in parallel
    num_reducers = 2
    for i in range(num_reducers):
        reducer = PythonCodeNode(
            name=f"reducer_{i}",
            code='''
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
        )
        workflow.add_node(f"reducer_{i}", reducer)

    # Connect map-reduce pipeline
    # Input -> Mappers (parallel)
    for i in range(num_mappers):
        workflow.connect("input_splitter", f"mapper_{i}",
                        mapping={f"partition_{i}": "data_partition"})

    # Mappers -> Shuffler
    for i in range(num_mappers):
        workflow.connect(f"mapper_{i}", "shuffler",
                        mapping={"result": f"mapper_{i}_results"})

    # Shuffler -> Reducers (parallel)
    for i in range(num_reducers):
        workflow.connect("shuffler", f"reducer_{i}",
                        mapping={f"partition_{i}": "assigned_keys"})

    # Reducers -> Final output
    workflow.connect("reducer_0", "output_combiner",
                    mapping={"result": "reducer_0_results"})
    workflow.connect("reducer_1", "output_combiner",
                    mapping={"result": "reducer_1_results"})

    return workflow

```

## 🎯 Common Use Cases

### 1. Multi-Source Data Aggregation
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Gather data from multiple databases simultaneously
for db_name in ["users_db", "orders_db", "inventory_db"]:
workflow = Workflow("example", name="Example")
workflow.workflow.add_node(f"{db_name}_reader", SQLReaderNode())

# All queries execute in parallel
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("data_joiner", MergeNode())
for db_name in ["users_db", "orders_db", "inventory_db"]:
workflow = Workflow("example", name="Example")
workflow.workflow.connect(f"{db_name}_reader", "data_joiner")

```

### 2. Parallel Validation
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Run multiple validation checks concurrently
validators = [
    "schema_validator",
    "business_rules_validator",
    "security_validator",
    "compliance_validator"
]

for validator in validators:
workflow = Workflow("example", name="Example")
workflow.workflow.add_node(validator, ValidationNode())
workflow = Workflow("example", name="Example")
workflow.workflow.connect("input_data", validator)
workflow = Workflow("example", name="Example")
workflow.workflow.connect(validator, "validation_aggregator")

```

### 3. Fan-Out Notifications
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Send notifications through multiple channels
channels = ["email", "sms", "push", "webhook"]

for channel in channels:
workflow = Workflow("example", name="Example")
workflow.workflow.add_node(f"{channel}_sender", NotificationNode())
workflow = Workflow("example", name="Example")
workflow.workflow.connect("notification_trigger", f"{channel}_sender")

```

### 4. Parallel File Processing
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Process multiple files concurrently
file_processors = []
for i in range(num_workers):
    processor = FileProcessorNode(id=f"processor_{i}")
workflow = Workflow("example", name="Example")
workflow.workflow.add_node(f"processor_{i}", processor)
workflow = Workflow("example", name="Example")
workflow.workflow.connect("file_queue", f"processor_{i}")
workflow = Workflow("example", name="Example")
workflow.workflow.connect(f"processor_{i}", "results_collector")

```

## 📊 Best Practices

### 1. **Ensure Independence**
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# GOOD: Independent parallel paths
workflow = Workflow("example", name="Example")
workflow.  # Method signature)
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# BAD: Shared state causes race conditions
shared_state = {}
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("processor_1", PythonCodeNode(
    code="shared_state['key'] = value"  # Race condition!
))

```

### 2. **Set Appropriate Timeouts**
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# GOOD: Different timeouts for different services
fast_api = RestClientNode(timeout=2000)    # 2 seconds
slow_api = RestClientNode(timeout=10000)   # 10 seconds

```

### 3. **Handle Partial Failures**
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# GOOD: Continue even if some parallel tasks fail
aggregator = MergeNode(
    id="aggregator",
    merge_strategy="collect_available",  # Skip failed branches
    required_inputs=2  # Need at least 2 of 5 to succeed
)

```

### 4. **Monitor Resource Usage**
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# GOOD: Limit parallelism for resource-intensive tasks
workflow = Workflow("example", name="Example")
workflow.workflow.runtime_config = {
    "max_parallel_tasks": 10,  # Limit concurrent execution
    "task_timeout": 30000,     # 30 second timeout
    "memory_limit": "2GB"      # Per-task memory limit
}

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
