# Base Node Interface

## Status
Accepted

## Context
The Kailash Python SDK needs a consistent interface for all nodes to ensure compatibility with the container-node architecture. Nodes must:
- Have a standard execution contract
- Validate inputs and outputs
- Support JSON-serializable data
- Enable metadata and logging
- Work within both local and containerized environments

## Decision
We will implement a base `Node` abstract class that enforces:

1. **Standard execution contract**: `run(**kwargs) -> dict`
2. **Parameter definition**: `get_parameters()` method returning parameter metadata
3. **Validation**: Separate methods for input/output validation
4. **Lifecycle management**: `execute()` wrapper method handling validation and error handling
5. **Metadata support**: Node metadata including name, version, author, tags
6. **Logging**: Built-in logger per node instance

Key design choices:
- Use abstract base class (ABC) for enforcement
- Separate `run()` (user implements) from `execute()` (framework calls)
- Use Pydantic models for metadata and parameter definitions
- Require all outputs to be JSON-serializable dictionaries

## Consequences

### Positive
- Consistent interface across all nodes
- Type safety through parameter definitions
- Automatic validation reduces errors
- Clear separation of concerns
- Easy integration with containerization
- Built-in error handling and logging

### Negative
- Additional complexity for simple nodes
- Inheritance can be limiting for some use cases
- JSON serialization requirement may limit data types
- Parameter definitions add boilerplate

### Implementation Notes
The base class provides:
- Abstract methods that must be implemented
- Concrete methods for common functionality
- Automatic registration with NodeRegistry
- Integration with task tracking system

This design ensures all nodes work seamlessly within the Kailash architecture while providing flexibility for custom implementations.
