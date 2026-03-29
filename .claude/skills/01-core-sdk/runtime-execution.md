---
name: runtime-execution
description: "Execute workflows with LocalRuntime or AsyncLocalRuntime, with parameter overrides and configuration options. Use when asking 'execute workflow', 'runtime.execute', 'LocalRuntime', 'AsyncLocalRuntime', 'run workflow', 'execution options', 'runtime parameters', 'content-aware detection', or 'workflow execution'."
---

# Runtime Execution Options

Runtime Execution Options guide with patterns, examples, and best practices.

> **Skill Metadata**
> Category: `core-sdk`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Runtime Execution Options
- **Category**: core-sdk
- **Priority**: HIGH
- **Trigger Keywords**: execute workflow, runtime.execute, LocalRuntime, AsyncLocalRuntime, run workflow

## Core Patterns

### Synchronous Execution (CLI/Scripts)

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})

# Context manager ensures proper cleanup (RECOMMENDED)
with LocalRuntime() as runtime:
    results, run_id = runtime.execute(workflow.build())
```

### Asynchronous Execution (Docker/FastAPI)

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})

# AsyncLocalRuntime for async execution (Docker-optimized)
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

### Runtime Configuration Options

Both runtimes share 29 configuration parameters:

```python
# Common configuration options
runtime = LocalRuntime(
    debug=True,                                    # Enable debug logging
    enable_cycles=True,                            # Allow cyclic workflows
    conditional_execution=True,                    # Enable conditional nodes
    connection_validation="strict",                # Validation mode: strict, warn, off
    content_aware_success_detection=True,          # Detect {"success": False} patterns
    max_iterations=100,                            # Max cycle iterations
    convergence_threshold=0.001                    # Cycle convergence threshold
)

# Get validation metrics (LocalRuntime public API)
metrics = runtime.get_validation_metrics()
runtime.reset_validation_metrics()
```

## Parameter Passing at Runtime

```python
# Override node parameters at runtime
with LocalRuntime() as runtime:
    results, run_id = runtime.execute(
        workflow.build(),
        parameters={
            "reader": {"file_path": "custom.csv"},     # Override node config
            "filter": {"threshold": 100}               # Add runtime parameter
        }
    )
```

## Runtime Architecture

Both LocalRuntime and AsyncLocalRuntime inherit from BaseRuntime and use shared mixins for consistent behavior:

**BaseRuntime Foundation**:

- Provides 29 configuration parameters (debug, enable_cycles, conditional_execution, connection_validation, etc.)
- Manages execution metadata (run IDs, workflow caching)
- Common initialization and validation modes (strict, warn, off)

**Shared Mixins**:

- **CycleExecutionMixin**: Cycle execution delegation to CyclicWorkflowExecutor with validation and error wrapping
- **ValidationMixin**: Workflow structure validation (5 methods)
  - validate_workflow(): Checks workflow structure, node connections, parameter mappings
  - \_validate_connection_contracts(): Validates connection parameter contracts
  - \_validate_conditional_execution_prerequisites(): Validates conditional execution setup
  - \_validate_switch_results(): Validates switch node results
  - \_validate_conditional_execution_results(): Validates conditional execution results
- **ConditionalExecutionMixin**: Conditional execution and branching logic with SwitchNode support
  - Pattern detection and cycle detection
  - Node skipping and hierarchical execution
  - Conditional workflow orchestration

**LocalRuntime-Specific Features**:

- \_generate_enhanced_validation_error(): Enhanced error messages with context
- \_build_connection_context(): Builds connection context for errors
- get_validation_metrics(): Public API for retrieving validation metrics
- reset_validation_metrics(): Public API for resetting validation metrics

**ParameterHandlingMixin Not Used**:
LocalRuntime uses WorkflowParameterInjector for enterprise parameter handling instead of ParameterHandlingMixin (architectural boundary for complex workflows).

All existing usage patterns remain unchanged.

## AsyncLocalRuntime Extensions

AsyncLocalRuntime inherits from LocalRuntime and adds async-specific capabilities:

### Async-Specific Components

**WorkflowAnalyzer**: Analyzes workflows to determine optimal execution strategy

- Detects async vs sync nodes
- Identifies execution levels (dependency-based)
- Calculates concurrency opportunities

**ExecutionContext**: Async execution context with integrated resource access

- Integrated ResourceRegistry support
- Execution variables management
- Performance metrics collection

**Execution Strategies**: Automatically selects optimal execution path

- Pure Async: All AsyncNode instances (maximum concurrency)
- Mixed: Combination of sync/async nodes (balanced)
- Sync-Only: All sync nodes in thread pool (compatibility)

**Level-Based Parallelism**: Executes independent nodes concurrently

- Groups nodes by dependency level
- Uses asyncio.gather() for concurrent execution
- Respects data dependencies

**Concurrency Control**: Semaphore-based limits

- Default: 10 concurrent nodes
- Configurable via max_concurrent_nodes parameter
- Prevents resource exhaustion

**Thread Pool**: Executes sync nodes without blocking

- Runs sync nodes via loop.run_in_executor()
- Configurable pool size (default: 4 threads)
- Proper cleanup in destructor

### Usage Example

```python
from kailash.runtime import AsyncLocalRuntime
from kailash.resources import ResourceRegistry

# Create runtime with async-specific options
runtime = AsyncLocalRuntime(
    debug=True,
    enable_cycles=True,                    # Inherited from BaseRuntime
    conditional_execution=True,            # Inherited from mixins
    connection_validation="strict",        # Inherited from mixins
    max_concurrent_nodes=20,               # AsyncLocalRuntime-specific
    thread_pool_size=8,                    # AsyncLocalRuntime-specific
    enable_analysis=True,                  # Enable WorkflowAnalyzer
    enable_profiling=True                  # Enable performance metrics
)

# Execute with async context
results = await runtime.execute_workflow_async(workflow.build(), inputs={})

# All inherited methods available
runtime.validate_workflow(workflow)         # ValidationMixin
metrics = runtime.get_validation_metrics()  # LocalRuntime
```

### When to Use AsyncLocalRuntime

Use AsyncLocalRuntime when:

- Deploying to Docker/Kubernetes
- Building FastAPI applications
- Requiring high concurrency
- Using async nodes (AsyncPythonCodeNode, etc.)
- Production API deployments (10-100x faster than LocalRuntime)

Use LocalRuntime when:

- Building CLI tools or scripts
- Synchronous execution contexts
- Testing and development
- Simple automation tasks

## Advanced: Custom Runtime Development

For advanced users building custom runtimes:

```python
from kailash.runtime.base import BaseRuntime
from kailash.runtime.mixins.cycle_execution import CycleExecutionMixin
from kailash.runtime.mixins.validation import ValidationMixin
from kailash.runtime.mixins.conditional_execution import ConditionalExecutionMixin

class CustomRuntime(BaseRuntime, CycleExecutionMixin, ValidationMixin, ConditionalExecutionMixin):
    """Custom runtime inheriting shared foundation (3 mixins)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)  # Initialize BaseRuntime
        # Add custom initialization

    def execute(self, workflow, **kwargs):
        """Implement custom execution logic."""
        # Use self._generate_run_id(), self._cache_workflow(), etc.
        pass
```

Note: ParameterHandlingMixin is not included as LocalRuntime uses WorkflowParameterInjector for enterprise parameter handling.

See `STATE_OWNERSHIP_CONVENTION.md` for mixin development guidelines.

## Related Patterns

- **For fundamentals**: See [`workflow-quickstart`](#)
- **For parameter passing**: See [`gold-parameter-passing`](#)
- **For runtime selection**: See [`decide-runtime`](#)

## Documentation References

### Primary Sources

- [`CLAUDE.md#L111-177`](../../../CLAUDE.md)

### Advanced References


## Performance Configuration

Phase 0 optimizations reduce per-node execution overhead. Key configuration:

```python
# Default: optimized for speed (resource checks disabled)
with LocalRuntime() as runtime:
    results, run_id = runtime.execute(workflow.build())

# Opt-in: enable psutil resource limit checks (adds ~71us/node overhead)
with LocalRuntime(enable_resource_limits=True) as runtime:
    results, run_id = runtime.execute(workflow.build())

# Maximum performance: disable both resource limits and monitoring
with LocalRuntime(enable_resource_limits=False, enable_monitoring=False) as runtime:
    results, run_id = runtime.execute(workflow.build())
```

**What's optimized (automatic, no config needed)**:

- Topological sort cached per workflow (742x-6504x speedup on cache hit)
- Cycle edge classification cached with dirty-flag invalidation (60x-265x speedup)
- Module-level imports (no per-node import overhead)
- Shared MetricsCollector per workflow (skips thread spawn when psutil disabled)
- Node ID frozenset pre-computed once per execution
- Security allowed_types cached at module level (eliminates 13+ per-call lazy imports)
- Topo cache returns immutable tuple (prevents cache corruption)
- Deferred monitoring storage (zero I/O during execution, batch write after)
- Batch CARE persistence (single file per run, avoids 1M+ entry directory bloat)
- SQLite CARE storage (ACID-compliant, queryable audit trail with EATP event persistence)

**Framework overhead**: ~41-52us/node with monitoring disabled (30-34% of total execution time
for PythonCodeNode with minimal code). See `docs/guides/00-performance-optimizations.md` for
detailed benchmark results.

**Monitoring overhead**: ~35us/node in-loop + ~1.5-2.8ms SQLite flush after execution.
Monitoring ON adds ~34% overhead in-loop (down from 3200x before P0D-007). Post-execution
SQLite flush adds ~1.5ms for 5-node workflows, scaling sub-linearly at ~56us/task for 50 tasks.

**CARE audit persistence (P0E)**: Tracking data + EATP audit events written atomically to
`~/.kailash/tracking/tracking.db` using WAL mode + `executemany()` batch inserts.
`DeferredStorageBackend.flush_to_sqlite()` is called by `_flush_deferred_storage_sqlite()`
in LocalRuntime, which collects `RuntimeAuditGenerator` events before flushing.

- networkx removed from hot-path execution (local.py, async_local.py)
- BFS ancestor traversal replaces nx.ancestors for switch evaluation

**Regression tests**: `tests/unit/runtime/test_phase0{a,b,c,d,e}_optimizations.py` (113+ tests)

See `docs/guides/00-performance-optimizations.md` for full details.

## Quick Tips

- Always use `runtime.execute(workflow.build())` - never `workflow.execute()`
- Choose LocalRuntime for CLI/scripts, AsyncLocalRuntime for Docker/FastAPI
- Both runtimes share the same configuration parameters and validation logic
- Parameter resolution supports ${param} templates with type preservation
- Use context manager (`with LocalRuntime() as runtime:`) for proper resource cleanup

## Keywords for Auto-Trigger

<!-- Trigger Keywords: execute workflow, runtime.execute, LocalRuntime, AsyncLocalRuntime, run workflow -->
