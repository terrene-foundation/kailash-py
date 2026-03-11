# ErrorEnhancer API

## What Is This

ErrorEnhancer transparently enriches Python exceptions with error codes, contextual information, possible causes, actionable solutions, and documentation links. It provides three performance modes for different deployment scenarios.

## When to Use

- **Production**: MINIMAL mode for essential context with <1ms overhead
- **Development**: FULL mode for complete diagnostic information with <5ms overhead
- **High-Performance**: DISABLED mode for passthrough with <0.1ms overhead

## Basic Usage

### Initialize ErrorEnhancer

```python
from dataflow.core.error_enhancer import ErrorEnhancer
from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode

# Default FULL mode (development)
enhancer = ErrorEnhancer()

# MINIMAL mode (production)
config = ErrorEnhancerConfig(mode=PerformanceMode.MINIMAL, cache_size=200)
enhancer = ErrorEnhancer(config=config)

# DISABLED mode (high-performance)
config = ErrorEnhancerConfig(mode=PerformanceMode.DISABLED)
enhancer = ErrorEnhancer(config=config)
```

**Performance Modes**:
- `FULL`: Complete enhancement with all context and solutions (<5ms)
- `MINIMAL`: Essential context and top solution only (<1ms)
- `DISABLED`: Passthrough with minimal wrapper (<0.1ms)

---

## Core Methods

### enhance_parameter_error()

Enhance parameter-related errors with performance mode support.

**Signature**:
```python
def enhance_parameter_error(
    node_id: str,
    node_type: Optional[str] = None,
    parameter_name: Optional[str] = None,
    expected_type: Optional[str] = None,
    received_value: Any = None,
    original_error: Optional[Exception] = None,
) -> EnhancedDataFlowError
```

**Parameters**:
- `node_id` (str, required): ID of the node with error
- `node_type` (str, optional): Type of node (e.g., "UserCreateNode")
- `parameter_name` (str, optional): Name of the missing/invalid parameter
- `expected_type` (str, optional): Expected parameter type
- `received_value` (Any, optional): Actual value received
- `original_error` (Exception, optional): Original exception

**Returns**: `EnhancedDataFlowError` with context and solutions

**Example**:
```python
try:
    workflow.add_node("UserCreateNode", "create", {"name": "Alice"})
except KeyError as e:
    enhanced = enhancer.enhance_parameter_error(
        node_id="create",
        node_type="UserCreateNode",
        parameter_name="id",
        expected_type="str",
        received_value=None,
        original_error=e
    )
    raise enhanced from e
```

**Enhanced Output** (FULL mode):
```
EnhancedDataFlowError: DF-101: Missing Parameter: 'id' in node 'create'

Context:
  node_id: create
  node_type: UserCreateNode
  parameter: id
  expected_type: str
  received_type: NoneType
  received_value: None

Causes:
  - Field 'id' not included in node parameters
  - Node definition missing required field

Solutions:
  1. Add 'id' field to node parameters
     Code: workflow.add_node("UserCreateNode", "create", {"id": "user-123", ...})

Docs: https://docs.kailash.ai/dataflow/errors/df-101
```

**Enhanced Output** (MINIMAL mode):
```
EnhancedDataFlowError: DF-101: Missing Parameter: 'id' in node 'create'

Context:
  node_id: create
  node_type: UserCreateNode
  parameter: id

Causes:
  - Field 'id' not included in node parameters

Solutions:
  1. Add 'id' field to node parameters

Docs: https://docs.kailash.ai/dataflow/errors/df-101
```

---

### enhance_connection_error()

Enhance connection-related errors.

**Signature**:
```python
def enhance_connection_error(
    source_node: str,
    target_node: str,
    source_param: Optional[str] = None,
    target_param: Optional[str] = None,
    original_error: Optional[Exception] = None,
) -> EnhancedDataFlowError
```

**Parameters**:
- `source_node` (str, required): Source node ID
- `target_node` (str, required): Target node ID
- `source_param` (str, optional): Source parameter name
- `target_param` (str, optional): Target parameter name
- `original_error` (Exception, optional): Original exception

**Returns**: `EnhancedDataFlowError` with connection-specific context

**Example**:
```python
try:
    workflow.add_connection("input", "invalid_output", "user_create", "data")
except Exception as e:
    enhanced = enhancer.enhance_connection_error(
        source_node="input",
        target_node="user_create",
        source_param="invalid_output",
        target_param="data",
        original_error=e
    )
    raise enhanced from e
```

**Enhanced Output**:
```
EnhancedDataFlowError: DF-201: Invalid connection from 'input' to 'user_create'

Context:
  source_node: input
  target_node: user_create
  source_param: invalid_output
  target_param: data

Causes:
  - Source node doesn't produce 'invalid_output'
  - Parameter reference incorrect

Solutions:
  1. Check source node outputs
  2. Verify parameter name spelling
```

---

### enhance_migration_error()

Enhance migration-related errors.

**Signature**:
```python
def enhance_migration_error(
    model_name: str,
    operation: Optional[str] = None,
    details: Optional[Dict] = None,
    original_error: Optional[Exception] = None,
) -> EnhancedDataFlowError
```

**Parameters**:
- `model_name` (str, required): Name of the model
- `operation` (str, optional): Migration operation (e.g., "create_table")
- `details` (dict, optional): Additional details about the error
- `original_error` (Exception, optional): Original exception

**Returns**: `EnhancedDataFlowError` with migration-specific context

**Example**:
```python
try:
    db.ensure_table_exists("User")
except Exception as e:
    enhanced = enhancer.enhance_migration_error(
        model_name="User",
        operation="create_table",
        original_error=e
    )
    raise enhanced from e
```

---

### enhance_runtime_error()

Enhance runtime execution errors.

**Signature**:
```python
def enhance_runtime_error(
    node_id: Optional[str] = None,
    node_type: Optional[str] = None,
    workflow_id: Optional[str] = None,
    operation: Optional[str] = None,
    original_error: Optional[Exception] = None,
) -> EnhancedDataFlowError
```

**Parameters**:
- `node_id` (str, optional): Node ID where error occurred
- `node_type` (str, optional): Type of node
- `workflow_id` (str, optional): Workflow ID
- `operation` (str, optional): Operation being performed
- `original_error` (Exception, optional): Original exception

**Returns**: `EnhancedDataFlowError` with runtime-specific context

**Example**:
```python
try:
    results, run_id = runtime.execute(workflow.build())
except Exception as e:
    enhanced = enhancer.enhance_runtime_error(
        node_id="user_create",
        node_type="UserCreateNode",
        operation="execute",
        original_error=e
    )
    raise enhanced from e
```

---

### enhance_generic_error()

Enhance generic errors by pattern matching.

**Signature**:
```python
def enhance_generic_error(
    exception: Exception,
    context: Optional[Dict] = None
) -> EnhancedDataFlowError
```

**Parameters**:
- `exception` (Exception, required): The exception to enhance
- `context` (dict, optional): Additional context information

**Returns**: `EnhancedDataFlowError` with matched error definition

**Example**:
```python
try:
    # Some DataFlow operation
    pass
except Exception as e:
    enhanced = enhancer.enhance_generic_error(
        exception=e,
        context={"operation": "workflow_execution"}
    )
    raise enhanced from e
```

---

## Performance Monitoring

### get_cache_hit_rate()

Get cache hit rate for performance monitoring.

**Signature**:
```python
def get_cache_hit_rate() -> float
```

**Returns**: Hit rate as float (0.0 to 1.0)

**Example**:
```python
hit_rate = enhancer.get_cache_hit_rate()
print(f"Cache hit rate: {hit_rate:.2%}")  # "Cache hit rate: 92.5%"
```

**Use Case**: Monitor cache effectiveness in production.

---

### get_cache_info()

Get cache statistics.

**Signature**:
```python
def get_cache_info() -> Dict[str, int]
```

**Returns**: Dictionary with cache size, hits, misses, evictions, maxsize

**Example**:
```python
info = enhancer.get_cache_info()
print(f"Cache size: {info['size']}")         # Current size
print(f"Cache hits: {info['hits']}")         # Total hits
print(f"Cache misses: {info['misses']}")     # Total misses
print(f"Cache evictions: {info['evictions']}")  # Total evictions
print(f"Max size: {info['maxsize']}")        # Maximum size
```

**Use Case**: Debug cache performance issues.

---

### set_performance_mode()

Switch performance mode at runtime.

**Signature**:
```python
def set_performance_mode(mode: PerformanceMode)
```

**Parameters**:
- `mode` (PerformanceMode, required): New performance mode (FULL, MINIMAL, DISABLED)

**Example**:
```python
from dataflow.core.config import PerformanceMode

# Start in FULL mode for debugging
enhancer = ErrorEnhancer()

# Switch to MINIMAL for production
enhancer.set_performance_mode(PerformanceMode.MINIMAL)

# Switch to DISABLED for high-performance scenarios
enhancer.set_performance_mode(PerformanceMode.DISABLED)
```

**Use Case**: Dynamic performance tuning based on environment.

---

## Auto-Fix Methods

### auto_fix_wrap_in_dict()

Auto-fix by wrapping value in dictionary.

**Signature**:
```python
def auto_fix_wrap_in_dict(parameter_name: str, value: Any) -> Dict
```

**Parameters**:
- `parameter_name` (str, required): Parameter name for the key
- `value` (Any, required): Value to wrap

**Returns**: Dictionary with {parameter_name: value}

**Example**:
```python
# Fix: "Alice" → {"data": "Alice"}
fixed = enhancer.auto_fix_wrap_in_dict("data", "Alice")
# Result: {"data": "Alice"}

workflow.add_node("UserCreateNode", "create", fixed)
```

---

### auto_fix_remove_auto_managed_fields()

Auto-fix by removing auto-managed fields (created_at, updated_at).

**Signature**:
```python
def auto_fix_remove_auto_managed_fields(data: Dict) -> Dict
```

**Parameters**:
- `data` (dict, required): Data dictionary with potential auto-managed fields

**Returns**: Dictionary with auto-managed fields removed

**Example**:
```python
# Fix: Remove created_at, updated_at
data = {
    "id": "user-123",
    "name": "Alice",
    "created_at": "2025-10-30",  # Will be removed
    "updated_at": "2025-10-30"   # Will be removed
}

fixed = enhancer.auto_fix_remove_auto_managed_fields(data)
# Result: {"id": "user-123", "name": "Alice"}

workflow.add_node("UserCreateNode", "create", fixed)
```

---

## Advanced Usage

### find_error_definition()

Find error definition by matching exception to catalog patterns.

**Signature**:
```python
def find_error_definition(exception: Exception) -> Optional[Dict]
```

**Parameters**:
- `exception` (Exception, required): The exception to match

**Returns**: Error definition dict with 'code' key, or None if no match

**Example**:
```python
try:
    raise KeyError("Parameter 'data' is missing")
except KeyError as e:
    error_def = enhancer.find_error_definition(e)
    if error_def:
        print(f"Error code: {error_def['code']}")  # "DF-101"
        print(f"Error name: {error_def['name']}")  # "Missing Parameter"
```

**Use Case**: Pattern matching for custom error handling.

---

## Error Codes Reference

| Code | Category | Description |
|------|----------|-------------|
| **DF-101** | Parameter | Missing required parameter |
| **DF-102** | Parameter | Type mismatch |
| **DF-104** | Parameter | Auto-managed field included |
| **DF-105** | Parameter | Missing primary key ('id') |
| **DF-201** | Connection | Invalid connection |
| **DF-202** | Connection | Missing source output |
| **DF-301** | Migration | Migration failure |
| **DF-302** | Migration | Schema mismatch |
| **DF-303** | Migration | Column type mismatch |
| **DF-501** | Runtime | Runtime execution error |
| **DF-999** | Generic | Passthrough (DISABLED mode) |

---

## Configuration

### ErrorEnhancerConfig

**Import**:
```python
from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
```

**Parameters**:
- `mode` (PerformanceMode): Performance mode (FULL, MINIMAL, DISABLED) [default: FULL]
- `cache_size` (int): LRU cache size for pattern compilation [default: 100]

**Example**:
```python
# Production configuration
config = ErrorEnhancerConfig(
    mode=PerformanceMode.MINIMAL,
    cache_size=200
)
enhancer = ErrorEnhancer(config=config)
```

---

## Performance Characteristics

| Mode | Overhead | Context | Solutions | Use Case |
|------|----------|---------|-----------|----------|
| **FULL** | <5ms | Complete | All | Development, debugging |
| **MINIMAL** | <1ms | Essential | Top 1 | Production |
| **DISABLED** | <0.1ms | Node ID only | None | High-performance |

**Cache Performance**:
- 90%+ hit rate with default cache_size=100
- Thread-safe concurrent access
- LRU eviction policy

---

## Best Practices

### Pattern 1: Development Mode

```python
# Use FULL mode in development for maximum diagnostic info
from dataflow.core.error_enhancer import ErrorEnhancer

enhancer = ErrorEnhancer()  # Default FULL mode

try:
    # DataFlow operations
    pass
except Exception as e:
    enhanced = enhancer.enhance_parameter_error(...)
    print(enhanced)  # Complete diagnostic output
    raise enhanced from e
```

---

### Pattern 2: Production Mode

```python
# Use MINIMAL mode in production for performance
from dataflow.core.error_enhancer import ErrorEnhancer
from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode

config = ErrorEnhancerConfig(mode=PerformanceMode.MINIMAL, cache_size=200)
enhancer = ErrorEnhancer(config=config)

try:
    # DataFlow operations
    pass
except Exception as e:
    enhanced = enhancer.enhance_parameter_error(...)
    logger.error(enhanced)  # Log essential context
    raise enhanced from e
```

---

### Pattern 3: High-Performance Mode

```python
# Use DISABLED mode for high-performance scenarios
from dataflow.core.error_enhancer import ErrorEnhancer
from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode

config = ErrorEnhancerConfig(mode=PerformanceMode.DISABLED)
enhancer = ErrorEnhancer(config=config)

try:
    # DataFlow operations
    pass
except Exception as e:
    enhanced = enhancer.enhance_parameter_error(...)
    # Minimal overhead, passthrough error
    raise enhanced from e
```

---

### Pattern 4: Dynamic Mode Switching

```python
import os
from dataflow.core.config import PerformanceMode

# Initialize based on environment
enhancer = ErrorEnhancer()

# Switch mode dynamically
if os.getenv("ENV") == "production":
    enhancer.set_performance_mode(PerformanceMode.MINIMAL)
elif os.getenv("ENV") == "staging":
    enhancer.set_performance_mode(PerformanceMode.FULL)
```

---

### Pattern 5: Cache Monitoring

```python
# Monitor cache performance
enhancer = ErrorEnhancer()

# ... after some operations ...

hit_rate = enhancer.get_cache_hit_rate()
if hit_rate < 0.80:
    print(f"Warning: Low cache hit rate: {hit_rate:.2%}")

    # Increase cache size if needed
    cache_info = enhancer.get_cache_info()
    if cache_info['evictions'] > 100:
        print("Consider increasing cache_size")
```

---

## Related

- [Error Cheat Sheet](../guides/cheat-sheet-errors.md) - Common errors and solutions
- [Inspector API](inspector.md) - Model introspection utilities
- [DataFlow Exceptions](../guides/exceptions.md) - Exception hierarchy
