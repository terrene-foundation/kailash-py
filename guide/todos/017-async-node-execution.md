# Asynchronous Node Execution Implementation

This document describes the implementation of asynchronous node execution and parallel workflow runtime in the Kailash Python SDK.

## Background

The original Kailash Python SDK executed all nodes synchronously, even when operations were I/O-bound or multiple nodes could potentially be executed in parallel. This limited performance in many real-world scenarios, particularly when dealing with external API calls, database operations, or other I/O-bound tasks.

## Implementation Details

### 1. AsyncNode Base Class

We implemented an `AsyncNode` class that extends the base `Node` class with asynchronous execution capabilities:

```python
class AsyncNode(Node):
    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Asynchronous execution method for the node."""
        # Default implementation calls the synchronous run() method
        return self.run(**kwargs)

    async def execute_async(self, **runtime_inputs) -> Dict[str, Any]:
        """Execute with validation and error handling in async context."""
        # Similar to execute() but async
        # ...
```

Key features:
- Default `async_run()` implementation calls the synchronous `run()` method for backward compatibility
- Proper validation and error handling in the async context
- Maintains the same input/output schema as the synchronous version

### 2. Specialized Async Logic Nodes

We created specialized async versions of logic nodes:

#### AsyncMerge

Extends `AsyncNode` to efficiently merge data from multiple sources with features including:
- Chunk-based processing for large datasets
- Optimized memory usage
- Support for asynchronous concatenation, zipping, and dictionary merging

```python
class AsyncMerge(AsyncNode):
    async def async_run(self, **kwargs) -> Dict[str, Any]:
        # Process data in chunks, with proper async operations
        # ...

    async def _async_concat(self, data_inputs: List[Any], chunk_size: int) -> Any:
        # Asynchronous implementation of concat with chunking
        # ...
```

#### AsyncSwitch

Extends `AsyncNode` to provide conditional routing with features including:
- Asynchronous condition evaluation
- Support for boolean, multi-case, and list routing
- Efficient handling of large data sets

```python
class AsyncSwitch(AsyncNode):
    async def async_run(self, **kwargs) -> Dict[str, Any]:
        # Async implementation of switch node
        # ...

    async def _evaluate_condition(self, check_value: Any, operator: str, compare_value: Any) -> bool:
        # Async condition evaluation
        # ...
```

### 3. ParallelRuntime

We implemented a new runtime that can execute independent nodes concurrently:

```python
class ParallelRuntime:
    def __init__(self, max_workers: int = 8, debug: bool = False):
        """Initialize the parallel runtime."""
        self.max_workers = max_workers
        # ...

    async def execute(self, workflow: Workflow, **kwargs) -> Tuple[Dict[str, Any], Optional[str]]:
        """Execute a workflow with parallel node execution."""
        # ...

    async def _execute_workflow_parallel(self, workflow: Workflow, **kwargs) -> Dict[str, Any]:
        """Execute nodes in parallel where possible."""
        # Dynamic scheduling based on dependency resolution
        # ...
```

Key features:
- Dynamic scheduling based on dependency resolution
- Support for both `AsyncNode` and regular `Node` classes
- Configurable parallelism with `max_workers` parameter
- Detailed execution metrics and monitoring
- Proper error handling and propagation

### 4. Examples and Tests

We implemented comprehensive examples and tests:

- **parallel_workflow_example.py**: Demonstrates the use of async nodes and parallel execution
- **test_async_operations.py**: Tests for AsyncMerge, AsyncSwitch, and ParallelRuntime
- Various node implementations with async_run() methods for different use cases

## Benefits

1. **Performance Improvements**: Significantly faster execution for workflows with I/O-bound operations
2. **Resource Utilization**: Better CPU and memory utilization through concurrent execution
3. **Developer Experience**: Simple API that maintains compatibility with existing code
4. **Scalability**: Better handling of large data sets through chunk-based processing

## Challenges Addressed

1. **Backward Compatibility**: All async nodes implement the required `run()` method
2. **Error Handling**: Proper error propagation in async context
3. **Testing Complexity**: Added pytest-asyncio support for testing async code
4. **Dependency Resolution**: Ensuring proper execution order with parallel execution

## Test Coverage

All new components are covered by tests:
- AsyncMerge node functionality (concat, zip, merge_dict)
- AsyncSwitch node functionality (boolean, multi-case)
- ParallelRuntime execution with various workflow patterns
- Error handling in async context

## Next Steps

1. Update our existing node implementations to support asynchronous execution
2. Add AsyncNode support to more complex nodes like PythonCodeNode
3. Improve error reporting for async execution
4. Add monitoring and visualization for parallel execution
5. Optimize memory usage for large datasets in parallel execution

## Conclusion

The implementation of asynchronous node execution and parallel workflow runtime significantly improves the performance and resource utilization of the Kailash Python SDK, particularly for I/O-bound operations and workflows with independent execution paths.
