# Documentation Requirements - Kailash Python SDK

## Overview

This document outlines the documentation standards and requirements for the Kailash Python SDK. All code must be thoroughly documented to ensure maintainability and usability.

## Docstring Standards

### Module Docstrings
Every module should have a docstring explaining its purpose:

```python
"""
Module for data transformation nodes.

This module provides various nodes for transforming data including
filtering, mapping, aggregation, and custom transformations.
"""
```

### Class Docstrings
Every class should have a comprehensive docstring:

```python
class DataTransformerNode(Node):
    """
    Transform data using configurable operations.
    
    This node provides a flexible way to transform data through a series
    of operations including filtering, mapping, sorting, and aggregation.
    
    Design Philosophy:
        Provides a declarative way to specify data transformations without
        writing custom code. Operations are applied in sequence.
    
    Upstream Dependencies:
        - Any node that outputs data (list, dict, or DataFrame)
        - Commonly used after data readers or API nodes
    
    Downstream Consumers:
        - Writer nodes for persisting transformed data
        - Analysis nodes for further processing
        - Visualization nodes for display
    
    Configuration:
        operations (List[Dict]): List of transformation operations
            Each operation dict must have a 'type' field and operation-specific parameters
    
    Example:
        >>> node = DataTransformerNode()
        >>> config = {
        ...     'operations': [
        ...         {'type': 'filter', 'condition': 'age > 18'},
        ...         {'type': 'sort', 'key': 'name'}
        ...     ]
        ... }
        >>> result = node.execute({'data': user_list})
    """
```

### Method Docstrings
Use Google-style docstrings for all public methods:

```python
def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the data transformation operations.
    
    Applies each operation in sequence to the input data. Operations
    are applied in the order specified in the configuration.
    
    Args:
        inputs (Dict[str, Any]): Input data with keys:
            - data: The data to transform (list, dict, or DataFrame)
            - context (optional): Additional context for transformations
    
    Returns:
        Dict[str, Any]: Dictionary with keys:
            - transformed: The transformed data
            - metadata: Transformation metadata (operations applied, row count, etc.)
    
    Raises:
        ValueError: If input data is missing or invalid
        TransformationError: If any transformation operation fails
        
    Side Effects:
        None - this method is pure and does not modify external state
        
    Example:
        >>> inputs = {'data': [{'name': 'John', 'age': 25}, {'name': 'Jane', 'age': 30}]}
        >>> outputs = node.execute(inputs)
        >>> print(outputs['transformed'])
        [{'name': 'Jane', 'age': 30}, {'name': 'John', 'age': 25}]
    """
```

### Comprehensive Docstring Requirements

All docstrings must include:

1. **Design Purpose and Philosophy**: Why this component exists
2. **Upstream Dependencies**: What creates/uses this class
3. **Downstream Consumers**: What depends on this class  
4. **Usage Patterns**: Common ways the component is used
5. **Implementation Details**: How it works internally
6. **Error Handling**: What exceptions are raised and when
7. **Side Effects**: Any state changes or external impacts
8. **Examples**: Concrete usage examples

## Sphinx Documentation

### Setup
Documentation uses Sphinx with:
- Napoleon extension for Google-style docstrings
- ReStructuredText (reST) format
- Auto-generated API docs from docstrings

### Building Documentation
```bash
cd docs
python build_docs.py
```

### Documentation Structure
```
docs/
├── index.rst           # Main documentation index
├── getting_started.rst # Getting started guide
├── api/               # Auto-generated API docs
│   ├── nodes.rst      # Node reference
│   ├── workflow.rst   # Workflow reference
│   └── utils.rst      # Utilities reference
├── guides/            # User guides
│   ├── workflows.rst  # Building workflows
│   ├── custom_nodes.rst # Creating custom nodes
│   └── best_practices.rst # Best practices
└── examples/          # Example documentation
```

### ReStructuredText Guidelines

For Sphinx compatibility, follow reST formatting:

```rst
Section Header
==============

Subsection
----------

Code blocks must be preceded by :: and a blank line::

    def example():
        return "code block"

Inline code uses double backticks: ``inline_code``

Links: `Link Text <https://example.com>`_

Cross-references: :class:`~kailash.Workflow`
```

## Code Examples in Documentation

### Docstring Examples
Include runnable examples using doctest format:

```python
def add_numbers(a: int, b: int) -> int:
    """
    Add two numbers together.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        Sum of a and b
        
    Examples:
        >>> add_numbers(2, 3)
        5
        >>> add_numbers(-1, 1)
        0
    """
    return a + b
```

### Standalone Examples
Create example files in `examples/` directory:

```python
"""
Example: Basic CSV Processing Workflow

This example demonstrates how to read a CSV file,
transform the data, and write the results.
"""

from kailash.workflow.graph import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.nodes.transform import DataTransformerNode

# Create workflow
workflow = Workflow(
    workflow_id="csv_processing_example",
    name="CSV Processing Example"
)

# Add nodes with detailed comments
workflow.add_node(
    "reader", 
    CSVReaderNode,  # Can pass class, instance, or string name
    file_path="input.csv",  # Config as kwargs, not dict
    headers=True  # Reads CSV into list of dicts
)

workflow.add_node(
    "transformer",
    DataTransformerNode,
    operations=[
        {"type": "filter", "condition": "age > 18"},  # Keep adults only
        {"type": "sort", "key": "name"}  # Sort by name
    ]
)

workflow.add_node(
    "writer",
    CSVWriterNode,
    file_path="output.csv"  # Write transformed data
)

# Connect nodes with mapping parameter
workflow.connect("reader", "transformer", mapping={"data": "input"})
workflow.connect("transformer", "writer", mapping={"output": "data"})

# Execute workflow (valid options)
# Option 1: Through runtime (RECOMMENDED)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# Option 2: Direct execution (without runtime)
# results = workflow.execute(inputs={})

# INVALID: workflow.execute(runtime) does NOT exist

print(f"Processed {results['transformer']['metadata']['row_count']} rows")
```

## API Documentation Requirements

### Public APIs
All public APIs must have:
1. Clear description of purpose
2. Complete parameter documentation
3. Return value documentation
4. Exception documentation
5. At least one usage example

### Internal APIs
Internal/private methods should have:
1. Brief description
2. Parameter types
3. Return type

## Documentation Testing

### Doctest
Run doctests to verify examples:
```bash
python -m doctest -v src/kailash/nodes/base.py
```

### Example Validation
All examples must be tested:
```bash
cd examples
python _utils/test_all_examples.py
```

## Documentation Maintenance

### When to Update Documentation

Update documentation when:
1. Adding new features
2. Changing API signatures
3. Fixing bugs that affect usage
4. Discovering common usage patterns
5. Receiving user feedback

### Documentation Review Checklist

- [ ] All public classes have comprehensive docstrings
- [ ] All public methods have complete parameter docs
- [ ] Examples are tested and working
- [ ] Sphinx docs build without warnings
- [ ] Cross-references are valid
- [ ] No spelling/grammar errors
- [ ] Version numbers are updated

## Special Documentation

### README.md
Must include:
- Project overview
- Installation instructions
- Quick start example
- Link to full documentation
- Contributing guidelines

### CHANGELOG.md
Track all changes:
- New features
- Bug fixes
- Breaking changes
- Deprecations

### Migration Guides
For breaking changes, provide:
- What changed
- Why it changed
- How to migrate
- Example migrations