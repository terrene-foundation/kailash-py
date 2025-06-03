# Node Naming Convention

## Status
Accepted

## Context
The Kailash Python SDK initially had inconsistent naming for node classes. Some classes ended with "Node" (e.g., `PythonCodeNode`, `WorkflowNode`) while others did not (e.g., `CSVReader`, `JSONWriter`, `Switch`). This inconsistency made it difficult to:
- Immediately identify classes as nodes
- Maintain a clear naming pattern for new nodes
- Generate documentation consistently
- Search and filter node classes programmatically

## Decision
We have standardized all node class names to end with the "Node" suffix. This applies to:
- All existing node classes in the SDK
- All future node implementations
- Both synchronous and asynchronous node variants

The following renaming was performed:
- `CSVReader` → `CSVReaderNode`
- `CSVWriter` → `CSVWriterNode`
- `JSONReader` → `JSONReaderNode`
- `JSONWriter` → `JSONWriterNode`
- `TextReader` → `TextReaderNode`
- `TextWriter` → `TextWriterNode`
- `Switch` → `SwitchNode`
- `Merge` → `MergeNode`
- `LLMAgent` → `LLMAgentNode`
- `EmbeddingGenerator` → `EmbeddingGeneratorNode`

Classes that already followed the convention were unchanged:
- `PythonCodeNode`
- `WorkflowNode`
- `HTTPClientNode`
- `RESTClientNode`
- All RAG-related nodes (already had "Node" suffix)

## Consequences

### Positive
- **Consistency**: All node classes follow the same naming pattern
- **Clarity**: Immediately obvious which classes are nodes
- **Searchability**: Easy to find all nodes with pattern matching
- **Documentation**: Consistent naming in docs and examples
- **Type Safety**: Easier to create type hints for "any node class"
- **Framework Integration**: Clear distinction between nodes and other classes

### Negative
- **Breaking Change**: Existing code using old names must be updated
- **Migration Effort**: All examples, tests, and documentation required updates
- **Verbosity**: Slightly longer class names (e.g., `CSVReaderNode` vs `CSVReader`)

### Migration Guide
For users upgrading from previous versions:
1. Update all imports to use new class names
2. Update any string-based node references (e.g., in YAML configs)
3. Search and replace old class names in code
4. Update any custom node registration using old names

Example migration:
```python
# Old
from kailash.nodes.data.readers import CSVReader
reader = CSVReader(file_path="data.csv")

# New
from kailash.nodes.data.readers import CSVReaderNode
reader = CSVReaderNode(file_path="data.csv")
```

### Implementation Notes
- All docstrings were also converted from Google-style `::` format to doctest `>>>` format
- All examples and tests were updated to use new names
- The `@register_node()` decorator automatically uses the class name for registration
- Backward compatibility could be added with aliases if needed

This decision ensures consistency across the SDK and makes the codebase more maintainable and user-friendly.