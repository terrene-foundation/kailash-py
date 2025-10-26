# Core Concepts - Workflows and Nodes

*Essential workflow and node concepts*

## 🎯 Prerequisites
- Python 3.8+
- Kailash SDK installed (`pip install kailash`)
- Basic understanding of data processing workflows

## 📋 Core Concepts

### Workflows and Nodes
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime, AsyncLocalRuntime

# WorkflowBuilder creates workflows with correct API
workflow = WorkflowBuilder()

# Nodes are processing units that perform specific tasks
# All node classes end with "Node"
```

### Node Creation Patterns
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()

# CSV Reading
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "/data/input.csv",
    "has_header": True,
    "delimiter": ","
})

# Data Processing
workflow.add_node("PythonCodeNode", "processor", {
    "code": '''
# Process the input data
processed = [item for item in input_data if item.get('amount', 0) > 100]
result = {'processed_items': processed, 'count': len(processed)}
'''
})

# Connect nodes
workflow.add_connection("reader", "result", "processor", "input_data")

# Execute with appropriate runtime
runtime = LocalRuntime()  # For CLI/scripts (synchronous)
# LocalRuntime inherits from BaseRuntime with 3 mixins for comprehensive execution
results, run_id = runtime.execute(workflow.build())

# For Docker/FastAPI (asynchronous)
# runtime = AsyncLocalRuntime()
# results = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

## 🔧 Node Types

### Data Input/Output
- `CSVReaderNode`, `JSONReaderNode` - File reading
- `CSVWriterNode`, `JSONWriterNode` - File writing
- `SQLDatabaseNode` - Database operations

### Processing
- `PythonCodeNode` - Custom Python logic
- `FilterNode`, `Map`, `Sort` - Data transformations
- `LLMAgentNode` - AI processing

### Logic & Control
- `SwitchNode`, `MergeNode` - Conditional routing
- `WorkflowNode` - Sub-workflows

## ✅ Key Rules
- Use `WorkflowBuilder()` not `Workflow()`
- Connection syntax: `add_connection(from_node, from_output, to_node, to_input)`
- PythonCodeNode wraps outputs in `result` key
- Access nested data with dot notation: `"result.data"`
- **ALWAYS** call `.build()` before execution: `runtime.execute(workflow.build())`

## 🔧 Runtime Selection

### For CLI/Scripts (Synchronous)
```python
from kailash.runtime import LocalRuntime

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### For Docker/FastAPI (Asynchronous)
```python
from kailash.runtime import AsyncLocalRuntime

runtime = AsyncLocalRuntime()
results = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

### Auto-Detection
```python
from kailash.runtime import get_runtime

# Automatically selects AsyncLocalRuntime for Docker/FastAPI,
# LocalRuntime for CLI/scripts
runtime = get_runtime()  # Defaults to "async" context
```

**Architecture Note**: Both LocalRuntime and AsyncLocalRuntime inherit from BaseRuntime and use 3 shared mixins:
- **CycleExecutionMixin**: Cycle execution delegation to CyclicWorkflowExecutor with validation and error wrapping
- **ValidationMixin**: Workflow structure validation (5 methods)
  - validate_workflow(): Checks workflow structure, node connections, parameter mappings
  - _validate_connection_contracts(): Validates connection parameter contracts
  - _validate_conditional_execution_prerequisites(): Validates conditional execution setup
  - _validate_switch_results(): Validates switch node results
  - _validate_conditional_execution_results(): Validates conditional execution results
- **ConditionalExecutionMixin**: Conditional execution and branching logic with SwitchNode support
  - Pattern detection and cycle detection
  - Node skipping and hierarchical execution
  - Conditional workflow orchestration

LocalRuntime also provides 4 validation helpers:
- get_validation_metrics(): Public API for validation metrics
- reset_validation_metrics(): Public API for metrics reset
- _generate_enhanced_validation_error(): Enhanced error messages
- _build_connection_context(): Connection context for errors

**ParameterHandlingMixin Not Used**: LocalRuntime uses WorkflowParameterInjector for enterprise parameter handling instead of ParameterHandlingMixin (architectural boundary for complex workflows).

**Configuration Options** (from BaseRuntime - 29 parameters):
```python
runtime = LocalRuntime(
    debug=True,
    enable_cycles=True,                    # CycleExecutionMixin
    conditional_execution="skip_branches",  # ConditionalExecutionMixin
    connection_validation="strict"          # ValidationMixin (strict/warn/off)
)
metrics = runtime.get_validation_metrics()  # Get metrics
runtime.reset_validation_metrics()  # Reset metrics
```

This ensures consistent behavior between sync and async execution.

**AsyncLocalRuntime-Specific Features**:
AsyncLocalRuntime extends LocalRuntime with async-optimized capabilities:
- **Automatic Strategy Selection**: Pure async, mixed, or sync-only (based on workflow composition)
- **Level-Based Parallelism**: Executes independent nodes concurrently within dependency levels
- **Concurrency Control**: Semaphore-based limits (`max_concurrent_nodes`, default: 10)
- **Thread Pool**: Executes sync nodes without blocking async loop (`thread_pool_size`, default: 4)
- **Resource Integration**: Integrated ResourceRegistry for connection pooling
- **Performance Tracking**: WorkflowAnalyzer and ExecutionMetrics for profiling

```python
from kailash.runtime import AsyncLocalRuntime

# AsyncLocalRuntime with async-specific options
runtime = AsyncLocalRuntime(
    debug=True,
    enable_cycles=True,                    # Inherited from BaseRuntime
    conditional_execution="skip_branches",  # Inherited from mixins
    connection_validation="strict",         # Inherited from mixins
    max_concurrent_nodes=20,               # AsyncLocalRuntime-specific
    thread_pool_size=8,                    # AsyncLocalRuntime-specific
    enable_analysis=True,                  # Enable WorkflowAnalyzer
    enable_profiling=True                  # Track performance
)

results = await runtime.execute_workflow_async(workflow.build(), inputs={})

# All inherited methods available
runtime.validate_workflow(workflow)         # ValidationMixin
metrics = runtime.get_validation_metrics()  # LocalRuntime
```

**When to Use AsyncLocalRuntime**:
- Docker/Kubernetes deployments
- FastAPI applications
- High-concurrency scenarios
- Production APIs (10-100x faster than LocalRuntime)

**When to Use LocalRuntime**:
- CLI tools and scripts
- Synchronous execution contexts
- Testing and development
- Simple automation tasks

## 🔗 Next Steps
- [Parameter Passing](01-fundamentals-parameters.md) - Data flow patterns
- [Node Connections](01-fundamentals-connections.md) - Advanced routing
- [Best Practices](01-fundamentals-best-practices.md) - Code patterns
