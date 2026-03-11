# ADR-014: Context-Aware Table Creation Pattern

## Status
Proposed - Supersedes previous lazy table creation approaches

## Context

The current DataFlow implementation suffers from critical architectural issues that prevent reliable production deployment:

### Primary Issues Identified

1. **Global Node Registration Context Loss**
   ```python
   # Current problematic pattern:
   NodeRegistry.register(UserCreateNode, "UserCreateNode")  # No instance context

   # Nodes lose reference to original DataFlow instance
   # Results in connection configuration errors and pool conflicts
   ```

2. **Event Loop Conflicts in Synchronous Decorators**
   ```python
   @db.model  # Synchronous decorator
   class User:
       name: str

   # Triggers async table creation during import
   # Causes "Event loop is closed" errors in many contexts
   ```

3. **Type Coercion Bugs with String Primary Keys**
   ```python
   # Current forced integer conversion:
   record_id = int(id_param)  # Breaks string/UUID primary keys

   # Results in SQL errors:
   # "operator does not exist: character varying = integer"
   ```

4. **Multi-Model Table Creation Failures**
   ```python
   @db.model
   class User: pass

   @db.model
   class Order: user_id: str  # Foreign key to User

   # Order table creation may execute before User table exists
   # No coordination between dependent models
   ```

### Business Impact

- **Developer Frustration**: Basic examples fail with cryptic async errors
- **Enterprise Blockers**: Multi-model applications cannot deploy reliably
- **Production Failures**: String ID models break in production databases
- **Framework Reputation**: Comprehensive documentation masking non-functional core

### Technical Root Causes

1. **Architectural Mismatch**: Synchronous decorators triggering async operations
2. **Context Isolation Failure**: Global node registry loses instance-specific configuration
3. **Type System Bypass**: Automatic type coercion ignoring model annotations
4. **Coordination Absence**: No orchestration for dependent schema operations

## Decision

Implement a **Context-Aware Table Creation Pattern** that fundamentally restructures how DataFlow manages model registration, node generation, and schema operations.

### Core Architectural Principles

1. **Instance Context Preservation**: All generated nodes maintain reference to originating DataFlow instance
2. **Deferred Schema Operations**: Model registration queues schema operations for coordinated execution
3. **Type-Aware Processing**: Respect model type annotations, never force type conversion
4. **Event Loop Safety**: Separate registration (sync) from execution (async) phases

### Implementation Architecture

```python
class DataFlow:
    def __init__(self):
        self._schema_operations_queue = []  # Deferred DDL operations
        self._model_registry = {}           # Instance-specific model tracking
        self._nodes_generated = {}          # Instance-bound node classes
        self._schema_state = "pending"      # pending|initializing|ready|error

    @property
    def model(self):
        """Decorator that defers all async operations."""
        def decorator(cls):
            # 1. Register model metadata (synchronous)
            self._register_model_metadata(cls)

            # 2. Queue schema operation (deferred)
            self._queue_schema_operation(cls)

            # 3. Generate instance-bound nodes (synchronous)
            self._generate_instance_nodes(cls)

            # 4. Return original class unchanged
            return cls
        return decorator

    async def ensure_schema_ready(self):
        """Execute all deferred schema operations."""
        if self._schema_state == "ready":
            return

        if self._schema_state == "pending":
            await self._execute_deferred_schema_operations()

class InstanceBoundDataFlowNode(AsyncNode):
    def __init__(self, dataflow_instance, model_class, operation):
        self.dataflow_instance = dataflow_instance  # Preserve context
        self.model_class = model_class
        self.operation = operation

    async def run(self, **kwargs):
        # Ensure schema exists before any database operation
        await self.dataflow_instance.ensure_schema_ready()

        # Use instance-specific connection configuration
        connection_config = self.dataflow_instance.get_connection_config()

        # Process ID with type awareness
        id_param = self._process_id_with_type_awareness(kwargs.get('id'))

        # Execute with proper context
        return await self._execute_database_operation(connection_config, **kwargs)

    def _process_id_with_type_awareness(self, id_param):
        """Preserve ID type based on model annotations."""
        if id_param is None:
            return None

        # Get declared type from model annotations
        id_type = self._get_model_field_type('id')

        # Type-aware processing
        if id_type == str or 'UUID' in str(id_type):
            return str(id_param)  # Preserve as string
        elif id_type == int:
            try:
                return int(id_param)  # Convert only when explicitly int
            except (ValueError, TypeError):
                return id_param  # Fallback to original
        else:
            return id_param  # Preserve original type for unknown types
```

### Schema Operation Coordination

```python
class SchemaOperationCoordinator:
    def __init__(self, dataflow_instance):
        self.dataflow_instance = dataflow_instance
        self.dependency_graph = {}  # Model dependency tracking

    async def execute_schema_operations(self):
        """Execute deferred schema operations in dependency order."""
        try:
            # 1. Analyze model dependencies
            execution_order = self._resolve_dependency_order()

            # 2. Begin transaction for atomic schema updates
            async with self._schema_transaction():

                # 3. Execute DDL operations in dependency order
                for model_class in execution_order:
                    await self._create_table_for_model(model_class)

                # 4. Create indexes and constraints
                await self._create_indexes_and_constraints()

        except Exception as e:
            # 5. Rollback on any failure
            await self._rollback_schema_operations()
            raise SchemaInitializationError(f"Schema creation failed: {e}")
```

### Node Registration with Context

```python
class NodeGenerator:
    def __init__(self, dataflow_instance):
        self.dataflow_instance = dataflow_instance

    def generate_nodes_for_model(self, model_class):
        """Generate instance-bound nodes for a model."""
        model_name = model_class.__name__

        # Create instance-bound node classes
        nodes = {
            f"{model_name}CreateNode": self._create_instance_bound_node(
                model_class, "create"
            ),
            f"{model_name}ReadNode": self._create_instance_bound_node(
                model_class, "read"
            ),
            f"{model_name}UpdateNode": self._create_instance_bound_node(
                model_class, "update"
            ),
            f"{model_name}DeleteNode": self._create_instance_bound_node(
                model_class, "delete"
            ),
            f"{model_name}ListNode": self._create_instance_bound_node(
                model_class, "list"
            ),
        }

        # Register with instance-specific namespace
        for node_name, node_class in nodes.items():
            # Use instance-specific registration key
            registry_key = f"{id(self.dataflow_instance)}::{node_name}"
            NodeRegistry.register(node_class, registry_key)

        return nodes

    def _create_instance_bound_node(self, model_class, operation):
        """Create a node class bound to this DataFlow instance."""

        class BoundNode(InstanceBoundDataFlowNode):
            def __init__(self):
                super().__init__(self.dataflow_instance, model_class, operation)

        BoundNode.__name__ = f"{model_class.__name__}{operation.title()}Node"
        return BoundNode
```

## Consequences

### Positive Outcomes

1. **Eliminates Event Loop Conflicts**
   - Model registration is purely synchronous
   - Schema operations deferred to explicit async execution
   - Compatible with all import contexts (sync/async)

2. **Fixes String ID Type Issues**
   - Respects model type annotations
   - No automatic type coercion
   - Supports UUID, string, and custom ID types

3. **Enables Reliable Multi-Model Applications**
   - Coordinated schema creation with dependency resolution
   - Atomic DDL operations with rollback capability
   - Foreign key constraints handled correctly

4. **Maintains Full Backward Compatibility**
   - Existing @db.model syntax unchanged
   - Generated node names and interfaces preserved
   - Workflow integration patterns continue working

5. **Improves Enterprise Reliability**
   - Instance isolation for multi-tenant applications
   - Proper connection pool management
   - Comprehensive error handling and recovery

### Negative Impacts

1. **Increased Implementation Complexity**
   - More sophisticated node generation lifecycle
   - Complex state management for deferred operations
   - Additional coordination logic for schema operations

2. **Memory Overhead**
   - Each node maintains DataFlow instance reference
   - Schema operation queue persisted until execution
   - Model metadata cached per instance

3. **Deferred Execution Complexity**
   - Schema operations happen at runtime, not import time
   - Potential for delayed error discovery
   - Need for explicit initialization in some contexts

4. **Development Effort Required**
   - Significant refactoring of core engine components
   - Comprehensive test coverage for new patterns
   - Documentation updates for new execution model

### Risk Mitigation Strategies

1. **Backward Compatibility Preservation**
   - Maintain all existing public APIs
   - Provide automatic migration for common patterns
   - Extensive regression testing

2. **Performance Optimization**
   - Lazy loading of schema operations
   - Efficient dependency resolution algorithms
   - Connection pooling optimization

3. **Error Handling Enhancement**
   - Clear error messages for schema failures
   - Graceful degradation for partial failures
   - Comprehensive logging and debugging support

## Alternatives Considered

### Alternative 1: Async Decorator Pattern
```python
# Proposed async decorator syntax
@await db.model  # Not valid Python syntax
class User:
    name: str
```

**Analysis:**
- **Pros**: Direct async execution, no deferral complexity
- **Cons**: Invalid Python syntax, breaks language semantics
- **Verdict**: Rejected - Not implementable in Python

### Alternative 2: Global Schema Registry
```python
# Centralized schema management
GlobalSchemaRegistry.register(User, db_instance_1)
GlobalSchemaRegistry.register(Order, db_instance_2)
```

**Analysis:**
- **Pros**: Simpler implementation, shared coordination
- **Cons**: Breaks multi-tenant isolation, global state issues
- **Verdict**: Rejected - Violates enterprise requirements

### Alternative 3: Immediate Execution with Event Loop Detection
```python
@db.model
def decorator(cls):
    if asyncio.get_event_loop().is_running():
        # Defer to next tick
        asyncio.create_task(create_table(cls))
    else:
        # Execute immediately
        asyncio.run(create_table(cls))
```

**Analysis:**
- **Pros**: No deferral needed, immediate feedback
- **Cons**: Complex event loop management, still has timing issues
- **Verdict**: Rejected - Too fragile, doesn't solve coordination

### Alternative 4: Explicit Initialization Required
```python
db = DataFlow()

@db.model
class User:
    name: str

await db.initialize()  # Required call
```

**Analysis:**
- **Pros**: Clear separation, simple implementation
- **Cons**: Breaking change, extra step for users
- **Verdict**: Considered but deferred - Could be fallback option

## Implementation Plan

### Phase 1: Foundation Infrastructure (Days 1-5)

**Day 1-2: Instance Context Preservation**
- Refactor NodeGenerator to bind DataFlow instance
- Implement InstanceBoundDataFlowNode base class
- Create instance-specific node registration

**Day 3-4: Type-Aware ID Processing**
- Implement model annotation inspection utilities
- Fix string ID coercion in all CRUD operations
- Add comprehensive type preservation logic

**Day 5: Basic Integration Testing**
- Verify instance context preservation works
- Test string ID handling with various types
- Validate backward compatibility

### Phase 2: Deferred Schema Management (Days 6-10)

**Day 6-7: Schema Operation Queue**
- Implement deferred operation collection
- Create schema operation metadata structure
- Add dependency tracking between models

**Day 8-9: Coordinated Execution**
- Implement SchemaOperationCoordinator
- Add dependency resolution algorithm
- Create atomic DDL execution with rollback

**Day 10: Event Loop Safety**
- Test execution in various async contexts
- Implement safe async operation patterns
- Add synchronous fallback mechanisms

### Phase 3: Multi-Model Coordination (Days 11-15)

**Day 11-12: Foreign Key Handling**
- Implement dependency analysis for related models
- Create foreign key constraint coordination
- Add circular dependency detection

**Day 13-14: Performance Optimization**
- Optimize schema state caching
- Minimize connection pool overhead
- Implement efficient batch DDL operations

**Day 15: Integration and Documentation**
- Comprehensive integration testing
- Update documentation with new patterns
- Create migration guide for existing applications

## Success Metrics

### Functional Validation
- [ ] String ID models execute without type conversion errors
- [ ] Multi-model applications with 50+ models register successfully
- [ ] Foreign key relationships create in correct dependency order
- [ ] All existing @db.model decorators continue working unchanged
- [ ] Schema operations execute reliably in all async contexts

### Performance Benchmarks
- [ ] Model registration latency: <100ms per model
- [ ] Schema batch operations: <2s for 50 models
- [ ] Memory overhead: <10MB per DataFlow instance with 100 models
- [ ] Connection pool efficiency: No degradation from current implementation

### Reliability Targets
- [ ] Schema operation success rate: >99.9%
- [ ] Event loop conflict rate: 0% (complete elimination)
- [ ] DDL rollback success rate: >99% when failures occur
- [ ] Multi-tenant isolation: 100% (no cross-instance data leakage)

### Enterprise Readiness
- [ ] Support 1000+ models without performance degradation
- [ ] Handle concurrent schema operations across multiple instances
- [ ] Provide comprehensive error messages and debugging information
- [ ] Maintain audit trail for all schema modification operations

## Monitoring and Observability

### Key Metrics to Track
```python
# Schema operation metrics
schema_operation_duration = Histogram("dataflow_schema_operation_seconds")
schema_operation_failures = Counter("dataflow_schema_operation_failures_total")
deferred_operations_queue_size = Gauge("dataflow_deferred_operations_count")

# Type processing metrics
id_type_coercion_attempts = Counter("dataflow_id_coercion_attempts_total")
id_type_preservation_success = Counter("dataflow_id_preservation_success_total")

# Instance context metrics
node_instance_context_misses = Counter("dataflow_node_context_misses_total")
instance_bound_node_executions = Counter("dataflow_instance_bound_executions_total")
```

### Health Checks
- Schema operation queue health
- Instance context preservation validation
- Connection pool efficiency monitoring
- Type system compatibility verification

## Migration Strategy for Existing Applications

### Automatic Migration (Recommended)
```python
# Existing code continues to work unchanged
db = DataFlow(database_url="postgresql://...")

@db.model
class User:
    name: str

# Schema operations deferred automatically
# First database operation triggers schema creation
```

### Explicit Migration (Advanced Users)
```python
# For applications needing fine-grained control
db = DataFlow(database_url="postgresql://...")

@db.model
class User:
    name: str

# Explicit schema initialization
await db.ensure_schema_ready()

# Or synchronous initialization
db.ensure_schema_ready_sync()
```

### Testing Migration
```python
# TDD mode for isolated testing
db = DataFlow(tdd_mode=True, test_context=test_instance)

@db.model
class User:
    name: str

# Schema operations isolated to test context
# Automatic cleanup after test completion
```

This ADR represents a comprehensive solution to the critical architectural issues identified in the DataFlow framework, providing a path to reliable production deployment while maintaining full backward compatibility and developer experience.
