# Coding Standards - Kailash Python SDK

## General Principles

1. **Clean Architecture**: Follow the principles of clean architecture with clear separation of concerns.
2. **Pythonic Style**: Write code that follows Python best practices and idioms.
3. **Type Hints**: Use type hints throughout the codebase to enhance IDE support and documentation.
4. **Documentation**: All classes, methods, and functions must have docstrings.
5. **Error Handling**: Use explicit error handling with descriptive error messages.

## Style Guidelines

### Naming Conventions
- **Classes**: `PascalCase`
- **Functions/Methods**: `snake_case`
- **Variables**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private attributes/methods**: `_leading_underscore`
- **Node classes**: MUST end with `Node` suffix (e.g., `DataProcessorNode`)

### Code Formatting
- **Line length**: 88 characters (Black standard)
- **Indentation**: 4 spaces (no tabs)
- **String quotes**: Double quotes preferred
- **Trailing commas**: Use in multi-line structures
- Follow PEP 8 for other formatting guidelines

### Imports
Group imports in the following order:
1. Standard library imports
2. Third-party library imports  
3. Local application imports

Example:
```python
import os
import sys
from typing import Dict, List, Optional

import networkx as nx
import numpy as np
from pydantic import BaseModel

from kailash.workflow.graph import Workflow
from kailash.nodes.base import Node
from kailash.utils.export import export_workflow
```

## Design Principles

### 1. Composition Over Inheritance
- Prefer composing functionality over deep inheritance hierarchies
- Keep inheritance hierarchies shallow (max 2-3 levels)
- Use mixins for shared behavior

### 2. Single Responsibility Principle
- Each class should have a single responsibility
- Each module should have a clear, focused purpose
- Split large classes into smaller, focused components

### 3. Interface Segregation
- Define clear interfaces through abstract base classes
- Keep interfaces small and focused
- Don't force classes to implement unused methods

### 4. Dependency Inversion
- Depend on abstractions, not concretions
- Use dependency injection where appropriate
- Define interfaces for external dependencies

### 5. Fail Fast
- Validate inputs early
- Provide clear error messages
- Do not silently ignore errors
- Use custom exceptions for different error conditions

## Node-Specific Standards

### Node Naming
- **ALWAYS** use full class names with "Node" suffix
- **NEVER** create aliases that remove "Node" from the name
- Use descriptive names that indicate the node's purpose
- Register nodes without aliases: `@register_node()`

### Node Structure

Custom nodes must inherit from the base `Node` class and implement two required methods:

#### Required Methods

```python
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter, register_node

@register_node()
class MyCustomNode(Node):
    """One-line description of the node.
    
    Longer description explaining purpose and usage.
    """
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for the node.
        
        This method MUST be implemented by all custom nodes.
        """
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=list,
                required=True,
                description="Data to process"
            ),
            "threshold": NodeParameter(
                name="threshold",
                type=float,
                required=False,
                default=0.5,
                description="Processing threshold"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic.
        
        This method MUST be implemented by all custom nodes.
        Receives validated parameters as keyword arguments.
        Must return a JSON-serializable dictionary.
        """
        input_data = kwargs["input_data"]
        threshold = kwargs.get("threshold", 0.5)
        
        # Process data
        result = self._process_data(input_data, threshold)
        
        return {
            "result": result,
            "count": len(result)
        }
    
    def _process_data(self, data: List[Any], threshold: float) -> List[Any]:
        """Private helper method."""
        return [item for item in data if item > threshold]
```

#### Optional Methods

```python
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define expected output schema for validation.
        
        This method is OPTIONAL. If not provided, outputs are only
        validated for JSON-serializability.
        """
        return {
            "result": NodeParameter(
                name="result",
                type=list,
                required=True,
                description="Filtered results"
            ),
            "count": NodeParameter(
                name="count",
                type=int,
                required=True,
                description="Number of results"
            )
        }
```

#### Complete Example with Configuration

```python
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter, register_node

@register_node()
class DataProcessorNode(Node):
    """Process data with configurable options."""
    
    def __init__(self, **kwargs):
        """Initialize with configuration."""
        # Configuration can be passed during node creation
        super().__init__(**kwargs)
        
        # Access configuration via self.config
        self.processing_mode = self.config.get("mode", "standard")
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define inputs."""
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data"
            ),
            "options": NodeParameter(
                name="options",
                type=dict,
                required=False,
                default={},
                description="Processing options"
            )
        }
    
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define outputs (optional)."""
        return {
            "processed": NodeParameter(
                name="processed",
                type=list,
                required=True,
                description="Processed data"
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=True,
                description="Processing metadata"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Process the data."""
        data = kwargs["data"]
        options = kwargs.get("options", {})
        
        # Use configuration
        if self.processing_mode == "advanced":
            processed = self._advanced_processing(data, options)
        else:
            processed = self._standard_processing(data, options)
        
        # Log progress
        self.logger.info(f"Processed {len(processed)} items")
        
        return {
            "processed": processed,
            "metadata": {
                "mode": self.processing_mode,
                "item_count": len(processed),
                "options_used": options
            }
        }
    
    def _standard_processing(self, data, options):
        """Standard processing logic."""
        return [item for item in data if self._is_valid(item)]
    
    def _advanced_processing(self, data, options):
        """Advanced processing logic."""
        # More complex processing
        return data
    
    def _is_valid(self, item):
        """Validation helper."""
        return True
```

## Error Handling

### Custom Exceptions
Define in `sdk_exceptions.py`:
```python
class KailashError(Exception):
    """Base exception for Kailash SDK."""
    pass

class NodeExecutionError(KailashError):
    """Raised when node execution fails."""
    def __init__(self, node_id: str, message: str):
        self.node_id = node_id
        super().__init__(f"Node '{node_id}' execution failed: {message}")

class WorkflowValidationError(KailashError):
    """Raised when workflow validation fails."""
    pass
```

### Error Handling Pattern
```python
try:
    result = risky_operation()
except SpecificError as e:
    # Handle specific error
    logger.error(f"Operation failed: {e}")
    raise NodeExecutionError(self.id, str(e))
except Exception as e:
    # Log unexpected errors
    logger.exception("Unexpected error occurred")
    raise
```

## Configuration

### Environment Variables
- Use for sensitive configuration (API keys, secrets)
- Provide sensible defaults where appropriate
- Document all environment variables

### Configuration Pattern
```python
import os
from typing import Optional

class Config:
    """Configuration management."""
    
    def __init__(self):
        self.api_key = os.environ.get("KAILASH_API_KEY")
        self.timeout = int(os.environ.get("KAILASH_TIMEOUT", "30"))
        self.debug = os.environ.get("KAILASH_DEBUG", "").lower() == "true"
    
    def validate(self):
        """Validate configuration."""
        if not self.api_key and self._requires_api_key():
            raise ValueError("KAILASH_API_KEY environment variable is required")
```

## Performance Guidelines

1. **Optimize for developer experience first**
   - Clear, readable code over micro-optimizations
   - Profile before optimizing
   
2. **Lazy Loading**
   - Import heavy dependencies only when needed
   - Use generators for large data sets
   
3. **Caching**
   - Cache expensive computations
   - Use functools.lru_cache for pure functions

## Testing Standards

1. **Test Naming**: `test_<method_name>_<scenario>`
2. **Test Structure**: Arrange-Act-Assert pattern
3. **Fixtures**: Use pytest fixtures for common setup
4. **Mocking**: Mock external dependencies
5. **Coverage**: Maintain >80% code coverage

Example:
```python
import pytest
from unittest.mock import Mock, patch

def test_node_execute_with_valid_data():
    # Arrange
    node = MyCustomNode(config={"threshold": 0.5})
    inputs = {"data": [1, 2, 3]}
    
    # Act
    result = node.execute(inputs)
    
    # Assert
    assert "result" in result
    assert isinstance(result["result"], dict)
```

## Code Review Checklist

Before submitting code:
- [ ] Follows naming conventions (PascalCase, snake_case, Node suffix)
- [ ] Has comprehensive docstrings
- [ ] Includes type hints
- [ ] Handles errors appropriately
- [ ] Has unit tests
- [ ] Passes linting (Black, isort, Ruff)
- [ ] No hardcoded secrets
- [ ] Updates relevant documentation