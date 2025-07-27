# Data Processing Patterns

Patterns for handling complex data flows, aggregation, and large-scale processing.

## 1. Multi-Node Input Aggregation (MergeNode)

**Purpose**: Combine outputs from multiple nodes into a single aggregator node

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.logic import MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Multiple AI agents for different perspectives
workflow.add_node("LLMAgentNode", "market_analyst", {}),
    provider="openai",
    model="gpt-4",
    system_prompt="You are a market analysis expert. Analyze the market potential."
)

workflow.add_node("LLMAgentNode", "tech_analyst", {}),
    provider="openai",
    model="gpt-4",
    system_prompt="You are a technical feasibility expert. Assess technical viability."
)

workflow.add_node("LLMAgentNode", "risk_analyst", {}),
    provider="openai",
    model="gpt-4",
    system_prompt="You are a risk assessment expert. Identify potential risks."
)

# MergeNode to combine all outputs
workflow.add_node("MergeNode", "merger", {}),
    merge_strategy="concat"  # Options: concat, zip, merge_dict
)

# Aggregator to synthesize insights
workflow.add_node("PythonCodeNode", "synthesizer", {}),
    code="""
# merged_data is a list containing all inputs
market_analysis = merged_data[0] if len(merged_data) > 0 else {}
tech_analysis = merged_data[1] if len(merged_data) > 1 else {}
risk_analysis = merged_data[2] if len(merged_data) > 2 else {}

# Extract content from each analysis
market_insights = market_analysis.get('content', 'No market analysis available')
tech_insights = tech_analysis.get('content', 'No technical analysis available')
risk_insights = risk_analysis.get('content', 'No risk analysis available')

# Synthesize findings
result = {
    'summary': {
        'market_perspective': market_insights[:200] + '...',
        'technical_perspective': tech_insights[:200] + '...',
        'risk_perspective': risk_insights[:200] + '...'
    },
    'recommendation': 'Proceed with caution' if 'high risk' in risk_insights.lower() else 'Favorable opportunity',
    'confidence_scores': {
        'market': 0.8 if market_analysis.get('finish_reason') == 'stop' else 0.5,
        'technical': 0.8 if tech_analysis.get('finish_reason') == 'stop' else 0.5,
        'risk': 0.8 if risk_analysis.get('finish_reason') == 'stop' else 0.5
    }
}
"""
)

# Connect all agents to merger
workflow.add_connection("market_analyst", "merger", "response", "data1")
workflow.add_connection("tech_analyst", "merger", "response", "data2")
workflow.add_connection("risk_analyst", "merger", "response", "data3")

# Connect merger to synthesizer
workflow.add_connection("merger", "synthesizer", "merged_data", "merged_data")

# Execute with a business proposal
runtime = LocalRuntime()
proposal = "Launch a new AI-powered customer service platform"
results, run_id = runtime.execute(workflow.build(), parameters={
    "market_analyst": {"prompt": f"Analyze market potential for: {proposal}"},
    "tech_analyst": {"prompt": f"Assess technical feasibility of: {proposal}"},
    "risk_analyst": {"prompt": f"Identify risks for: {proposal}"}
})

```

**Key Points**:
- MergeNode accepts up to 5 inputs: `data1`, `data2`, `data3`, `data4`, `data5`
- Output is always `merged_data`
- Merge strategies:
  - `concat`: List of all inputs (default)
  - `zip`: Pairs corresponding elements
  - `merge_dict`: Combines dictionaries

**Common Mistake**: Trying to connect multiple nodes directly to one node
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

# ❌ WRONG - This will fail
workflow.add_connection("agent1", "result", "processor", "input")
workflow.add_connection("agent2", "result", "processor", "input")  # Error: Multiple inputs!

# ✅ CORRECT - Use MergeNode
workflow.add_node("MergeNode", "merger", {})
workflow.add_connection("agent1", "result", "merger", "data1")
workflow.add_connection("agent2", "result", "merger", "data2")
workflow.add_connection("merger", "merged_data", "processor", "input")

```

## 2. Parallel Data Processing

**Purpose**: Process multiple data streams concurrently for performance

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.parallel import ParallelRuntime
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import MergeNode

workflow = WorkflowBuilder()

# Split data into chunks
workflow.add_node("PythonCodeNode", "splitter", {
    "code": """
# Split data into 4 chunks for parallel processing
chunk_size = len(data) // 4
chunks = []
for i in range(0, len(data), chunk_size):
    chunks.append(data[i:i+chunk_size])

result = {
    'chunk1': chunks[0] if len(chunks) > 0 else [],
    'chunk2': chunks[1] if len(chunks) > 1 else [],
    'chunk3': chunks[2] if len(chunks) > 2 else [],
    'chunk4': chunks[3] if len(chunks) > 3 else []
}
"""
})

# Create parallel processors
for i in range(1, 5):
    workflow.add_node("PythonCodeNode", f"processor_{i}", {
        "code": f"""
# Process chunk {i}
import time
start_time = time.time()

result = []
for item in data:
    # Simulate heavy processing
    processed = {{
        'original': item,
        'processed': item * 2,
        'processor': {i}
    }}
    result.append(processed)

processing_time = time.time() - start_time
print(f"Processor {i} completed in {{processing_time:.2f}}s")
""",
        "imports": ["time"]
    })

# Merge results
workflow.add_node("MergeNode", "merger", {"merge_strategy": "concat"})

# Connect splitter to processors
for i in range(1, 5):
    workflow.add_connection("splitter", f"chunk{i}", f"processor_{i}", "data")

# Connect processors to merger
workflow.add_connection("processor_1", "result", "merger", "data1")
workflow.add_connection("processor_2", "result", "merger", "data2")
workflow.add_connection("processor_3", "result", "merger", "data3")
workflow.add_connection("processor_4", "result", "merger", "data4")

# Execute with parallel runtime
runtime = ParallelRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "splitter": {"data": list(range(1000))}
})

```

## 3. Batch Processing Pattern

**Purpose**: Process large datasets in memory-efficient chunks

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

workflow = WorkflowBuilder()

# Batch processor with progress tracking
workflow.add_node("PythonCodeNode", "batch_processor", {
    "code": """
import math

# Configuration
batch_size = config.get('batch_size', 100)
total_items = len(data)
num_batches = math.ceil(total_items / batch_size)

print(f"Processing {total_items} items in {num_batches} batches")

results = []
errors = []
processed_count = 0

for batch_num in range(num_batches):
    start_idx = batch_num * batch_size
    end_idx = min(start_idx + batch_size, total_items)
    batch = data[start_idx:end_idx]

    try:
        # Process batch
        batch_results = []
        for item in batch:
            # Simulate processing
            if item.get('valid', True):
                result = {
                    'id': item['id'],
                    'value': item['value'] * 2,
                    'batch': batch_num
                }
                batch_results.append(result)
            else:
                errors.append({
                    'item': item,
                    'error': 'Validation failed',
                    'batch': batch_num
                })

        results.extend(batch_results)
        processed_count += len(batch)

        # Progress update
        progress = (processed_count / total_items) * 100
        print(f"Batch {batch_num + 1}/{num_batches} completed - {progress:.1f}%")

    except Exception as e:
        errors.append({
            'batch': batch_num,
            'error': str(e),
            'items_affected': len(batch)
        })
        print(f"Error in batch {batch_num}: {e}")

# Final summary
result = {
    'processed_items': results,
    'total_processed': len(results),
    'errors': errors,
    'error_count': len(errors),
    'success_rate': len(results) / total_items if total_items > 0 else 0
}
""",
    imports=["math"],
    config={"batch_size": 250}
)

# Memory-efficient file writer
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "stream_writer", {}),
    code="""
import json

output_file = config.get('output_file', 'output.jsonl')
batch_size = 100

# Write results in streaming fashion
with open(output_file, 'w') as f:
    for i in range(0, len(processed_items), batch_size):
        batch = processed_items[i:i+batch_size]
        for item in batch:
            f.write(json.dumps(item) + '\\n')

# Write summary
summary_file = output_file.replace('.jsonl', '_summary.json')
with open(summary_file, 'w') as f:
    json.dump({
        'total_processed': total_processed,
        'error_count': error_count,
        'success_rate': success_rate
    }, f, indent=2)

result = {
    'output_file': output_file,
    'summary_file': summary_file,
    'status': 'completed'
}
""",
    imports=["json"],
    config={"output_file": "results.jsonl"}
)

workflow = WorkflowBuilder()
workflow.add_connection("batch_processor", "result", "stream_writer", "input")

```

## 4. Stream Processing Pattern

**Purpose**: Process continuous data streams in real-time

```python
from kailash.nodes.data.streaming import StreamReaderNode
from kailash.nodes.code import PythonCodeNode

workflow = WorkflowBuilder()

# Streaming data source
workflow.add_node("StreamReaderNode", "stream_reader", {}),
    source_type="kafka",
    topic="events",
    batch_size=50,
    timeout=1000
)

# Windowed aggregation
workflow.add_node("PythonCodeNode", "windowed_aggregator", {}),
    code="""
from collections import defaultdict
from datetime import datetime, timedelta

# Initialize window state
if not hasattr(self, 'windows'):
    self.windows = defaultdict(lambda: {'count': 0, 'sum': 0})
    self.window_start = datetime.now()

# Current time and window
current_time = datetime.now()
window_duration = timedelta(minutes=5)

# Clean old windows
cutoff_time = current_time - window_duration
self.windows = {k: v for k, v in self.windows.items()
                if datetime.fromisoformat(k) > cutoff_time}

# Process events
for event in events:
    window_key = current_time.replace(second=0, microsecond=0).isoformat()
    self.windows[window_key]['count'] += 1
    self.windows[window_key]['sum'] += event.get('value', 0)

# Calculate current window stats
current_window = self.windows.get(current_time.replace(second=0, microsecond=0).isoformat(),
                                  {'count': 0, 'sum': 0})

result = {
    'window_stats': {
        'count': current_window['count'],
        'sum': current_window['sum'],
        'average': current_window['sum'] / current_window['count'] if current_window['count'] > 0 else 0
    },
    'active_windows': len(self.windows),
    'timestamp': current_time.isoformat()
}
""",
    imports=["from collections import defaultdict", "from datetime import datetime, timedelta"]
)

# Real-time alerting
workflow.add_node("PythonCodeNode", "alerting", {}),
    code="""
# Check for anomalies
if window_stats['average'] > config.get('threshold', 100):
    alert = {
        'type': 'high_average',
        'value': window_stats['average'],
        'timestamp': timestamp,
        'severity': 'warning' if window_stats['average'] < 150 else 'critical'
    }

    # Send alert (placeholder)
    print(f"ALERT: {alert['severity'].upper()} - Average {alert['value']:.2f} exceeds threshold")

    result = {'alert': alert, 'triggered': True}
else:
    result = {'triggered': False}
""",
    config={"threshold": 100}
)

workflow.add_connection("stream_reader", "windowed_aggregator", "data", "events")
workflow.add_connection("windowed_aggregator", "alerting", "result", "window_data")

```

## 5. Fan-Out/Fan-In Pattern

**Purpose**: Distribute work across multiple processors and collect results

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

workflow = WorkflowBuilder()

# Distributor node
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "distributor", {}),
    code="""
# Distribute items to different queues based on type
queues = {
    'type_a': [],
    'type_b': [],
    'type_c': [],
    'unclassified': []
}

for item in items:
    item_type = item.get('type', 'unclassified')
    if item_type in queues:
        queues[item_type].append(item)
    else:
        queues['unclassified'].append(item)

result = queues
"""
)

# Specialized processors for each type
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor_a", {}),
    code="result = [{'id': item['id'], 'processed_by': 'A', 'value': item['value'] * 1.1} for item in data]"
)

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor_b", {}),
    code="result = [{'id': item['id'], 'processed_by': 'B', 'value': item['value'] * 1.2} for item in data]"
)

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor_c", {}),
    code="result = [{'id': item['id'], 'processed_by': 'C', 'value': item['value'] * 1.3} for item in data]"
)

# Collector with MergeNode
workflow = WorkflowBuilder()
workflow.add_node("MergeNode", "collector", {}), merge_strategy="concat")

# Final aggregation
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "aggregator", {}),
    code="""
# Flatten and sort results
all_results = []
for sublist in merged_data:
    if isinstance(sublist, list):
        all_results.extend(sublist)

# Sort by ID
all_results.sort(key=lambda x: x.get('id', 0))

# Calculate statistics
result = {
    'total_processed': len(all_results),
    'by_processor': {},
    'results': all_results
}

for item in all_results:
    processor = item.get('processed_by', 'unknown')
    if processor not in result['by_processor']:
        result['by_processor'][processor] = 0
    result['by_processor'][processor] += 1
"""
)

# Connect the fan-out
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Connect the fan-in
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## Best Practices

1. **Choose the Right Pattern**:
   - Use MergeNode for combining multiple node outputs
   - Use batch processing for large datasets
   - Use streaming for real-time data
   - Use parallel processing for CPU-intensive tasks

2. **Memory Management**:
   - Process data in chunks to avoid memory issues
   - Use streaming writes for large outputs
   - Clear intermediate results when possible

3. **Error Handling**:
   - Always handle partial failures in batch processing
   - Implement retry logic for transient errors
   - Log errors with context for debugging

4. **Performance Optimization**:
   - Use appropriate batch sizes (typically 100-1000 items)
   - Leverage parallel processing for independent operations
   - Monitor memory usage in long-running workflows

## See Also
- [Control Flow Patterns](02-control-flow-patterns.md) - Routing and conditional logic
- [Performance Patterns](06-performance-patterns.md) - Optimization techniques
- [Error Handling Patterns](05-error-handling-patterns.md) - Resilient data processing
