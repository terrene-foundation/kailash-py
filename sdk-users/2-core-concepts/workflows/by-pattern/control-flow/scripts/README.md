# Control Flow Pattern Scripts

This directory contains working examples of control flow patterns using Kailash SDK best practices.

## Available Scripts

### 1. Conditional Routing Examples
- `conditional_routing_basic.py` - Simple if/else routing with SwitchNode
- `conditional_routing_multi.py` - Multi-way routing with multiple conditions
- `conditional_routing_nested.py` - Nested conditions without complexity

### 2. Parallel Execution Examples
- `parallel_api_calls.py` - Concurrent API requests with proper error handling
- `parallel_batch_processing.py` - Process large datasets in parallel chunks
- `parallel_with_timeout.py` - Parallel execution with timeouts and fallbacks

### 3. Cyclic Workflow Examples
- `retry_with_backoff.py` - API retry with exponential backoff
- `optimization_loop.py` - Iterative optimization with convergence
- `state_machine.py` - Order processing state machine

### 4. Error Handling Examples
- `try_catch_pattern.py` - Basic error handling with fallbacks
- `circuit_breaker.py` - Prevent cascade failures
- `error_aggregation.py` - Collect and report errors from multiple sources

## Running the Examples

Each script is self-contained and can be run directly:

```bash
python conditional_routing_basic.py
```

## Environment Variables

Most scripts use environment variables for configuration:

```bash
export API_ENDPOINT=https://api.example.com
export API_KEY=your-api-key
export DATABASE_URL=postgresql://user:pass@localhost/db
```

## Key Patterns Demonstrated

1. **Minimal PythonCodeNode Usage** - Examples show how to avoid PythonCodeNode
2. **Real Integrations** - All examples use real APIs, not mock data
3. **Proper Error Handling** - Built-in retry logic and fallbacks
4. **Clear Data Flow** - Easy to understand workflow logic
5. **Production Ready** - Examples include monitoring and logging

## Creating Your Own Workflows

Use these examples as templates:

1. Copy the most similar example
2. Replace API endpoints and credentials
3. Adjust business logic using existing nodes
4. Test with real data
5. Add monitoring and error handling as needed

Remember: If you're writing more than a few lines in a PythonCodeNode, you're probably doing it wrong!
