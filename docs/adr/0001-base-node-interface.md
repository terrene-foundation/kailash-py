### ADR-0001: Base Node Interface

**Status**: Accepted

**Date**: 2025-05-16

**Context**: We need to define a standard interface for all nodes in the Kailash Python SDK to ensure consistency and composability.

**Decision**: We will use a Python class-based approach where each node implements a `run(**kwargs) -> dict` method. This method takes arbitrary keyword arguments and returns a JSON-serializable dictionary.

**Rationale**: This approach provides flexibility while ensuring a consistent interface. The use of keyword arguments allows for optional parameters and future extensibility. Returning a dictionary enables a standard way to pass data between nodes.

**Consequences**:
- All nodes must implement the same interface
- Parameters and return values must be JSON-serializable
- Type hints should be used to improve IDE support and documentation
- Runtime validation will be needed to ensure contract compliance