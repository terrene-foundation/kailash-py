# ADR-007: Edge Infrastructure Integration into WorkflowBuilder

## Status
Accepted

## Context
Edge computing nodes in the Kailash SDK require shared infrastructure components (EdgeDiscovery, ComplianceRouter) to function properly. Previously, these components were created separately by each node, leading to:
- Resource inefficiency (multiple EdgeDiscovery instances)
- Configuration inconsistency across nodes
- Complex setup requirements for users
- Test failures due to missing infrastructure during runtime node creation

## Decision
We integrated edge infrastructure management directly into the existing WorkflowBuilder rather than creating a separate EdgeWorkflowBuilder. The implementation uses:
1. A singleton EdgeInfrastructure class for shared resource management
2. Automatic edge node detection based on naming patterns and interfaces
3. Lazy initialization to avoid overhead for non-edge workflows
4. Infrastructure injection during workflow build phase

## Consequences

### Positive
- **Unified API**: Users continue using the familiar WorkflowBuilder API
- **Resource Efficiency**: Single EdgeInfrastructure instance shared across all nodes
- **Zero-Config Operation**: Edge nodes work with default settings
- **Backward Compatibility**: Existing workflows continue to work unchanged
- **Test Stability**: Infrastructure properly initialized during test execution
- **DataFlow Integration**: Clean hooks for future app framework integration

### Negative
- **Hidden Complexity**: Edge infrastructure management is less visible to users
- **Naming Dependency**: Edge node detection relies on naming conventions
- **Singleton Pattern**: Global state management requires careful cleanup in tests

### Neutral
- **Configuration Flexibility**: Edge config passed through WorkflowBuilder constructor
- **Performance Impact**: Minimal overhead due to lazy initialization

## Implementation Details

### EdgeInfrastructure Singleton
```python
class EdgeInfrastructure:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, config=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
```

### WorkflowBuilder Enhancement
```python
class WorkflowBuilder:
    def __init__(self, edge_config=None):
        self.edge_config = edge_config
        self._edge_infrastructure = None

    def build(self):
        if self._has_edge_nodes and self.edge_config:
            self._edge_infrastructure = EdgeInfrastructure(self.edge_config)
            # Inject into edge nodes...
```

### Edge Node Detection
- Checks for "Edge" keyword in node type name
- Extensible to check node interfaces
- Minimal performance impact

## Alternatives Considered

### 1. Separate EdgeWorkflowBuilder
- **Pros**: Explicit edge support, cleaner separation
- **Cons**: API fragmentation, user confusion, maintenance burden

### 2. Manual Infrastructure Management
- **Pros**: Full control, explicit configuration
- **Cons**: Complex setup, error-prone, poor user experience

### 3. Global Infrastructure Registry
- **Pros**: Decoupled from WorkflowBuilder
- **Cons**: Hidden global state, cleanup complexity

## References
- Original issue: Edge nodes failing in WorkflowBuilder due to missing infrastructure
- Related: AsyncNode implementation patterns (ADR-006)
- DataFlow integration patterns
- Test-driven development approach (TODO-111)
