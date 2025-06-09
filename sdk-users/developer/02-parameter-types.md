# Parameter Type Constraints and Patterns

## ⚠️ Critical: Type Constraints

The most common error when creating custom nodes is using generic types from the `typing` module in NodeParameter definitions.

## The Problem

The `NodeParameter` class uses Pydantic validation that requires actual Python types, not generic type aliases:

```python
# ❌ This will fail with "Can't instantiate abstract class" error
from typing import List, Dict, Optional

def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        'items': NodeParameter(
            name='items',
            type=List[str],  # ❌ Generic alias - FAILS!
            required=True
        )
    }
```

## The Solution

Use basic Python types or `Any`:

```python
# ✅ This works correctly
from typing import Any

def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        'items': NodeParameter(
            name='items',
            type=list,  # ✅ Basic Python type
            required=True
        ),
        'complex_data': NodeParameter(
            name='complex_data',
            type=Any,  # ✅ Use Any for complex types
            required=False
        )
    }
```

## Valid Parameter Types

### Basic Types (Recommended)

| Type | Usage | Example Value |
|------|-------|---------------|
| `str` | Text data | `"hello"` |
| `int` | Whole numbers | `42` |
| `float` | Decimal numbers | `3.14` |
| `bool` | True/False | `True` |
| `list` | Lists/arrays | `[1, 2, 3]` |
| `dict` | Dictionaries/objects | `{"key": "value"}` |
| `Any` | Any type (escape hatch) | Anything |

### Invalid Types (Will Cause Errors)

| Invalid Type | Why It Fails | Use Instead |
|--------------|--------------|-------------|
| `List[str]` | Generic alias | `list` or `Any` |
| `Dict[str, Any]` | Generic alias | `dict` or `Any` |
| `Optional[str]` | Generic alias | `str` with `required=False` |
| `Union[str, int]` | Generic alias | `Any` |
| `Tuple[int, int]` | Generic alias | `list` or `Any` |

## Examples: Right vs Wrong

### Example 1: List of Strings

```python
# ❌ WRONG - Will fail
'tags': NodeParameter(
    name='tags',
    type=List[str],  # Generic type!
    required=True
)

# ✅ CORRECT - Option 1: Use list
'tags': NodeParameter(
    name='tags',
    type=list,  # Basic type
    required=True,
    description='List of tags'
)

# ✅ CORRECT - Option 2: Use Any with validation
'tags': NodeParameter(
    name='tags',
    type=Any,  # Flexible type
    required=True,
    description='List of string tags'
)
```

### Example 2: Optional Parameters

```python
# ❌ WRONG - Using Optional
'config': NodeParameter(
    name='config',
    type=Optional[dict],  # Generic type!
    required=False
)

# ✅ CORRECT - Use required=False
'config': NodeParameter(
    name='config',
    type=dict,  # Basic type
    required=False,  # Makes it optional
    default={}  # Provide default
)
```

### Example 3: Complex Data Structures

```python
# ❌ WRONG - Complex generic type
'mapping': NodeParameter(
    name='mapping',
    type=Dict[str, List[Union[str, int]]],  # Too complex!
    required=True
)

# ✅ CORRECT - Use Any for complex types
'mapping': NodeParameter(
    name='mapping',
    type=Any,  # Handles any structure
    required=True,
    description='Dictionary mapping strings to lists of strings or integers'
)
```

## Validation Patterns

### Runtime Type Checking

Since we use `Any` for complex types, add runtime validation:

```python
def run(self, **kwargs) -> Dict[str, Any]:
    # Get parameter
    items = kwargs.get('items', [])
    
    # Validate at runtime
    if not isinstance(items, list):
        raise ValueError(f"Expected list, got {type(items)}")
    
    # Validate list contents if needed
    for item in items:
        if not isinstance(item, str):
            raise ValueError(f"Expected string items, got {type(item)}")
    
    # Process validated data
    return {'count': len(items)}
```

### Using Defaults

```python
def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        'threshold': NodeParameter(
            name='threshold',
            type=float,
            required=False,
            default=0.5,  # Sensible default
            description='Threshold value (0.0-1.0)'
        ),
        'options': NodeParameter(
            name='options',
            type=dict,
            required=False,
            default={},  # Empty dict default
            description='Additional options'
        )
    }
```

## Complete Example: Data Processor Node

```python
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter

class DataProcessorNode(Node):
    """Process various data types with proper parameter handling."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            # String parameter
            'operation': NodeParameter(
                name='operation',
                type=str,
                required=True,
                description='Operation to perform: filter, transform, aggregate'
            ),
            # List parameter (not List[dict]!)
            'data': NodeParameter(
                name='data',
                type=list,  # ✅ Basic type
                required=True,
                description='List of data items to process'
            ),
            # Dictionary parameter
            'config': NodeParameter(
                name='config',
                type=dict,  # ✅ Basic type
                required=False,
                default={},
                description='Configuration options'
            ),
            # Flexible parameter using Any
            'filters': NodeParameter(
                name='filters',
                type=Any,  # ✅ For complex structures
                required=False,
                default=None,
                description='Filter conditions (can be list or dict)'
            ),
            # Boolean flag
            'verbose': NodeParameter(
                name='verbose',
                type=bool,
                required=False,
                default=False,
                description='Enable verbose output'
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        operation = kwargs['operation']
        data = kwargs['data']
        config = kwargs.get('config', {})
        filters = kwargs.get('filters')
        verbose = kwargs.get('verbose', False)
        
        # Validate data is actually a list
        if not isinstance(data, list):
            raise ValueError(f"Data must be a list, got {type(data)}")
        
        # Process based on operation
        if operation == 'filter' and filters:
            # Runtime validation of filters
            if isinstance(filters, dict):
                # Filter by dict conditions
                result = [item for item in data if self._matches_filter(item, filters)]
            elif isinstance(filters, list):
                # Filter by list of conditions
                result = [item for item in data if any(self._matches_filter(item, f) for f in filters)]
            else:
                raise ValueError(f"Filters must be dict or list, got {type(filters)}")
        else:
            result = data
        
        output = {
            'result': result,
            'count': len(result)
        }
        
        if verbose:
            output['operation'] = operation
            output['config'] = config
            
        return output
    
    def _matches_filter(self, item: Any, filter_dict: dict) -> bool:
        """Check if item matches filter conditions."""
        if not isinstance(item, dict):
            return False
        
        for key, value in filter_dict.items():
            if key not in item or item[key] != value:
                return False
        return True
```

## Key Takeaways

1. **Never use generic types** from `typing` in NodeParameter type field
2. **Use basic Python types** (str, int, float, bool, list, dict)
3. **Use `Any` for complex types** and validate at runtime
4. **Make parameters optional** with `required=False`, not `Optional[T]`
5. **Provide sensible defaults** for optional parameters
6. **Add runtime validation** when using `Any` type

---

*Continue to [03-common-patterns.md](03-common-patterns.md) →*