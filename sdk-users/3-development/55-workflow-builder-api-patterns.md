# WorkflowBuilder API Patterns Guide

*Comprehensive guide to WorkflowBuilder's flexible API patterns*

## 🎯 Overview

WorkflowBuilder supports multiple API patterns for maximum flexibility and backward compatibility. All patterns are fully supported and will continue to work in future versions.

## 📋 Supported API Patterns

### 1. Current/Preferred Pattern ⭐
**Recommended for new code**

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Standard syntax - explicit and clear
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://api.example.com",
    "method": "GET"
})
```

**Benefits:**
- ✅ Clear separation of node type, ID, and configuration
- ✅ Excellent IDE support and autocomplete
- ✅ Easy to read and maintain

### 2. Keyword-Only Pattern
**Best for complex configurations**

```python
workflow = WorkflowBuilder()

# Pure keyword arguments
workflow.add_node(
    node_type="PythonCodeNode",
    node_id="data_processor",
    config={
        "code": "result = process_data(input_data)",
        "timeout": 30
    }
)
```

**Benefits:**
- ✅ Self-documenting parameter names
- ✅ Flexible parameter ordering
- ✅ Clear intent

### 3. Mixed Pattern
**Common in existing codebases**

```python
workflow = WorkflowBuilder()

# Positional node type + keyword parameters
workflow.add_node("CSVReaderNode",
                  node_id="data_reader",
                  config={"file_path": "data.csv"})
```

**Benefits:**
- ✅ Backward compatibility
- ✅ Concise yet explicit
- ✅ Works with existing code

### 4. Auto ID Generation Pattern ⭐
**Perfect for rapid prototyping**

```python
workflow = WorkflowBuilder()

# Automatic ID generation
reader_id = workflow.add_node("CSVReaderNode")
processor_id = workflow.add_node("PythonCodeNode", config={
    "code": "result = {'count': len(input_data)}"
})

print(f"Generated IDs: {reader_id}, {processor_id}")
# Output: Generated IDs: node_abc123def, node_456xyz789
```

**Benefits:**
- ✅ Faster development for prototypes
- ✅ No need to think of unique IDs
- ✅ Returns the generated ID for connections

### 5. Simple Two-String Pattern
**Quick and minimal**

```python
workflow = WorkflowBuilder()

# Just node type and ID
workflow.add_node("DataProcessorNode", "processor")
```

**Benefits:**
- ✅ Minimal syntax
- ✅ Clear and concise
- ✅ Good for simple nodes

## 🚀 Advanced Patterns

### Class-Based Pattern (Advanced)
**For type safety and IDE support**

```python
from kailash.nodes.ai import LLMAgentNode

workflow = WorkflowBuilder()

# Use actual class for better IDE support
workflow.add_node(LLMAgentNode, "llm_agent", {
    "model": "gpt-4",
    "provider": "openai"
})
```

⚠️ **Note:** Generates deprecation warning encouraging string-based usage

### Instance-Based Pattern (Advanced)
**For pre-configured complex nodes**

```python
from kailash.nodes.data import PythonCodeNode

# Pre-configure complex node
complex_processor = PythonCodeNode.from_function(my_complex_function)

workflow = WorkflowBuilder()
workflow.add_node(complex_processor, "processor")
```

⚠️ **Note:** Generates deprecation warning encouraging configuration-based usage

## 🔗 Connection Patterns

All API patterns work seamlessly with connections:

```python
workflow = WorkflowBuilder()

# Mix different patterns in same workflow
api_id = workflow.add_node("HTTPRequestNode", "api_call", {"url": "..."})
processor_id = workflow.add_node("PythonCodeNode", node_id="processor", config={...})
output_id = workflow.add_node("JSONWriterNode")  # Auto-generated ID

# Connect using returned IDs
workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern
workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern
```

## 📐 Migration Patterns

### From Old to New
```python
# OLD: Less clear parameter ordering
workflow.add_node("processor", HTTPRequestNode, url="https://api.com")

# NEW: Clear and explicit
workflow.add_node("HTTPRequestNode", "processor", {"url": "https://api.com"})
```

### Adding Auto IDs to Existing Code
```python
# BEFORE: Manual ID management
workflow.add_node("CSVReaderNode", "reader_001", {})
workflow.add_node("PythonCodeNode", "proc_001", {})

# AFTER: Let WorkflowBuilder handle IDs
reader = workflow.add_node("CSVReaderNode")
processor = workflow.add_node("PythonCodeNode")
```

## ⚡ Best Practices

### 1. Choose the Right Pattern
- **Prototyping**: Use auto ID generation
- **Production**: Use explicit IDs with descriptive names
- **Complex configs**: Use keyword-only pattern
- **Simple cases**: Use two-string pattern

### 2. Consistent Style
```python
# ✅ GOOD: Consistent style within a workflow
workflow.add_node("APINode", "fetcher", {"url": "..."})
workflow.add_node("ProcessorNode", "analyzer", {"model": "..."})
workflow.add_node("OutputNode", "writer", {"format": "json"})

# ❌ MIXED: Different styles (works but inconsistent)
workflow.add_node("APINode", "fetcher", {"url": "..."})
auto_id = workflow.add_node("ProcessorNode")
workflow.add_node(node_type="OutputNode", node_id="writer", config={})
```

### 3. Descriptive Node IDs
```python
# ✅ GOOD: Clear purpose
workflow.add_node("HTTPRequestNode", "customer_api_fetcher", {})
workflow.add_node("PythonCodeNode", "data_validator", {})

# ❌ BAD: Generic names
workflow.add_node("HTTPRequestNode", "node1", {})
workflow.add_node("PythonCodeNode", "node2", {})
```

### 4. Configuration Organization
```python
# ✅ GOOD: Organized configuration
api_config = {
    "url": "https://api.example.com/customers",
    "method": "GET",
    "headers": {"Authorization": "Bearer token"},
    "timeout": 30
}
workflow.add_node("HTTPRequestNode", "api_fetcher", api_config)

# ❌ INLINE: Hard to read for complex configs
workflow.add_node("HTTPRequestNode", "api_fetcher", {"url": "https://api.example.com/customers", "method": "GET", "headers": {"Authorization": "Bearer token"}, "timeout": 30})
```

## 🔄 Pattern Conversion Examples

### Example 1: API to Keyword
```python
# API Pattern
workflow.add_node("LLMAgentNode", "agent", {
    "model": "gpt-4",
    "provider": "openai",
    "temperature": 0.7
})

# Keyword Pattern (equivalent)
workflow.add_node(
    node_type="LLMAgentNode",
    node_id="agent",
    config={
        "model": "gpt-4",
        "provider": "openai",
        "temperature": 0.7
    }
)
```

### Example 2: Manual to Auto ID
```python
# Manual IDs
workflow.add_node("CSVReaderNode", "csv_reader_001", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor_001", {"code": "..."})
workflow.add_connection("csv_reader_001", "result", "processor_001", "input")

# Auto IDs
reader = workflow.add_node("CSVReaderNode", config={"file_path": "data.csv"})
processor = workflow.add_node("PythonCodeNode", config={"code": "..."})
workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern
```

## 🎯 Choosing the Right Pattern

| Use Case | Recommended Pattern | Example |
|----------|-------------------|---------|
| **Production workflows** | Current API | `add_node("NodeType", "descriptive_id", config)` |
| **Rapid prototyping** | Auto ID | `add_node("NodeType", config=config)` |
| **Complex configurations** | Keyword-only | `add_node(node_type="...", node_id="...", config=...)` |
| **Simple nodes** | Two-string | `add_node("NodeType", "node_id")` |
| **Existing codebases** | Mixed (maintain consistency) | Follow existing patterns |

## 💡 Pro Tips

1. **Return Values**: All patterns return the node ID (useful for auto-generated IDs)
2. **Backward Compatibility**: All patterns will continue to work in future versions
3. **Deprecation Warnings**: Some advanced patterns show warnings but still work
4. **IDE Support**: String-based patterns provide the best IDE autocomplete
5. **Error Messages**: Enhanced error messages help identify pattern issues

## 🔧 Error Handling

Common errors and solutions:

```python
# ❌ Error: Invalid node type
workflow.add_node(123, "node_id")  # TypeError

# ✅ Solution: Use string node type
workflow.add_node("PythonCodeNode", "node_id")

# ❌ Error: Missing node_type in keyword-only
workflow.add_node(node_id="test", config={})  # WorkflowValidationError

# ✅ Solution: Include node_type
workflow.add_node(node_type="PythonCodeNode", node_id="test", config={})
```

See [common-mistakes.md](../validation/common-mistakes.md) for more error patterns.
