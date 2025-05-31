# ADR 0014: Asynchronous Node Execution & Parallel Workflow Runtime

## Context

The Kailash Python SDK often deals with I/O-bound operations and multiple independent execution paths in workflows. These operations can include:

1. API calls to external services
2. Database operations
3. File system operations
4. LLM/AI model inference
5. Network operations

In the original implementation, all nodes were executed synchronously, which could lead to inefficient resource utilization, especially when multiple nodes could potentially run in parallel or when I/O-bound operations caused unnecessary waiting.

## Decision

We have decided to implement a comprehensive asynchronous execution system with the following components:

1. **AsyncNode Base Class**: Extending the existing Node class to add async_run() method for asynchronous execution.
2. **Specialized Async Logic Nodes**: Creating AsyncMerge and AsyncSwitch nodes optimized for asynchronous execution.
3. **ParallelRuntime**: Implementing a new runtime that can execute independent nodes concurrently.

### AsyncNode Base Class

The AsyncNode extends the base Node class with two key methods:
- `async_run(**kwargs)`: The asynchronous equivalent of run() for implementing async operations
- `execute_async(**kwargs)`: The asynchronous equivalent of execute() for handling validation and error handling

The AsyncNode is designed to:
- Maintain backward compatibility through a default async_run implementation that calls the synchronous run() method
- Provide proper error handling in the async context
- Support the same parameter and output validation as the synchronous version

### Specialized Async Logic Nodes

The following specialized nodes were created to optimize for asynchronous execution:

1. **AsyncMerge**: Extends AsyncNode to efficiently merge data from multiple sources with features including:
   - Chunk-based processing for large datasets
   - Asynchronous concatenation, zipping, and dictionary merging
   - Optimized memory usage for large data streams

2. **AsyncSwitch**: Extends AsyncNode to provide conditional routing with features including:
   - Asynchronous condition evaluation
   - Support for boolean, multi-case, and list routing
   - Efficient handling of large data sets

### ParallelRuntime

A new ParallelRuntime was implemented to execute workflows with true concurrency:

- Supports concurrent execution of independent nodes
- Uses dynamic scheduling based on dependency resolution
- Compatible with both AsyncNode and regular Node classes
- Limits concurrency through configurable parameters
- Provides detailed execution metrics and monitoring

## Consequences

### Positive

1. **Performance Improvements**: Significantly faster execution for workflows with independent paths and I/O-bound operations
2. **Resource Utilization**: Better CPU and memory utilization through concurrent execution
3. **Developer Experience**: Simple async API that maintains compatibility with existing code
4. **Scalability**: Better handling of large data sets through chunk-based processing
5. **Flexibility**: Support for both synchronous and asynchronous nodes in the same workflow

### Negative

1. **Implementation Complexity**: More complex code with async/await patterns
2. **Testing Complexity**: Asynchronous code requires specialized testing approaches
3. **Dependency Management**: Need to ensure proper dependency resolution in parallel execution
4. **Error Handling**: More complex error propagation in async context
5. **Debugging Challenges**: Async call stacks can be harder to debug

### Neutral

1. **API Changes**: New async methods are added while maintaining existing sync methods
2. **Backward Compatibility**: Existing code continues to work without modification
3. **Documentation Needs**: More detailed documentation required for async patterns

## Alternatives Considered

1. **Async-only at merge points**: Implementing async execution only at merge nodes would be simpler but would miss many opportunities for optimization.

2. **Thread-based parallelism**: Using threads instead of async/await would offer similar benefits but with more overhead and potential complexity in Python due to the GIL.

3. **Process-based parallelism**: Using multiprocessing would enable true CPU parallelism but at the cost of higher overhead and complexity for data sharing.

4. **Event-driven callbacks**: An event-driven system with callbacks could achieve similar results but would lead to more complex code structure.

## Implementation Details

### AsyncNode Base Class

```python
class AsyncNode(Node):
    async def async_run(self, **kwargs) -> Dict[str, Any]:
        # Default implementation calls the synchronous run() method
        return self.run(**kwargs)

    async def execute_async(self, **runtime_inputs) -> Dict[str, Any]:
        # Validation and execution similar to execute() but in async context
        # ...
```

### ParallelRuntime

```python
class ParallelRuntime:
    async def execute(self, workflow: Workflow, **kwargs) -> Dict[str, Any]:
        # Dynamic scheduling based on dependency resolution
        # ...

    async def _execute_node(self, node_id: str, **kwargs) -> Tuple[Dict[str, Any], bool]:
        # Execute a single node asynchronously
        # Handle both AsyncNode and regular Node types
        # ...
```

## Example Usage

```python
# Define an async node
class MyAsyncNode(AsyncNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        # Parameter definition
        # ...

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        # Async implementation
        await asyncio.sleep(1)  # Simulating IO operation
        # Process data
        return {"output": processed_data}

# Create a workflow with async nodes
workflow = Workflow(workflow_id="async_example", name="Async Workflow")
workflow.add_node("source", MyAsyncNode())
workflow.add_node("merge", AsyncMerge())
# ... connect nodes

# Execute with parallel runtime
runtime = ParallelRuntime(max_workers=10)
results = await runtime.execute(workflow)
```

## Conclusion

By implementing comprehensive asynchronous execution support in the Kailash Python SDK, we have significantly improved the performance and resource utilization of workflow execution, particularly for I/O-bound operations and workflows with independent execution paths. The implementation maintains backward compatibility while providing a clean, intuitive API for developers to leverage asynchronous operations.

## Status

Accepted

## Date

2025-05-21

## Implementation Status

As of 2025-05-30, asynchronous node execution has been fully implemented:
- AsyncNode base class in `kailash.nodes.base_async`
- AsyncMerge and AsyncSwitch nodes in `kailash.nodes.logic.async_operations`
- ParallelRuntime in `kailash.runtime.parallel`
- Comprehensive test coverage in `tests/test_nodes/test_async_operations.py`
- Working example in `parallel_workflow_example.py`
- Full integration with existing workflow system
- All tests passing with async functionality verified
