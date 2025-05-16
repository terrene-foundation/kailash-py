# Local Execution Strategy

## Status
Accepted

## Context
The Kailash Python SDK needs to execute workflows locally for testing before deployment to the container environment. The execution engine must:
- Execute nodes in topological order
- Pass data between nodes correctly
- Handle errors gracefully
- Support debugging and monitoring
- Integrate with task tracking
- Allow parameter overrides

## Decision
We will implement a `LocalRuntime` class that:

1. **Executes workflows** in topological order using NetworkX
2. **Manages data flow** between nodes through explicit mappings
3. **Handles errors** with configurable stop-on-error behavior
4. **Integrates task tracking** for monitoring and debugging
5. **Supports parameter overrides** at runtime
6. **Provides debugging mode** with detailed logging

Key execution flow:
```
1. Validate workflow (no cycles, required inputs)
2. Create run in task tracker
3. For each node in topological order:
   - Create task record
   - Gather inputs from previous nodes
   - Apply parameter overrides
   - Execute node
   - Store outputs for downstream nodes
   - Update task status
4. Return aggregated results
```

## Consequences

### Positive
- Deterministic execution order
- Clear data flow tracking
- Comprehensive error handling
- Full execution visibility
- Easy debugging with task tracking
- Supports testing workflows locally

### Negative
- Sequential execution (no parallelism)
- Memory usage for storing all outputs
- Overhead from task tracking
- Limited to local resources

### Implementation Notes
The local runtime:
- Uses the same node execution contract as containers
- Preserves all intermediate outputs for debugging
- Integrates seamlessly with task tracking
- Provides foundation for other runtimes (Docker, K8s)

This design ensures workflows behave identically in local testing and production deployment.