# Developer Guide - Quick Reference

## 🚨 Critical Rules
1. **Node names**: ALL end with "Node" (`CSVReaderNode` ✓, `CSVReader` ✗)
2. **Parameter types**: ONLY `str`, `int`, `float`, `bool`, `list`, `dict`, `Any`
3. **Never use generics**: No `List[T]`, `Dict[K,V]`, `Optional[T]`, `Union[A,B]`
4. **PythonCodeNode**: Input variables EXCLUDED from outputs!
   - `mapping={"result": "input_data"}` ✓
   - `mapping={"result": "result"}` ✗
5. **Always include name**: `PythonCodeNode(name="processor", code="...")`
6. **Node Creation**: Can create without required params (validated at execution)
7. **Data Files**: Use centralized `/data/` with `examples/utils/data_paths.py`

## 📋 Quick Node Selection
| Task | Use | Don't Use |
|------|-----|-----------|
| Read CSV | `CSVReaderNode` | `PythonCodeNode` with manual CSV |
| Find files | `DirectoryReaderNode` | `PythonCodeNode` with `os.listdir` |
| Run Python | `PythonCodeNode(name="x")` | Missing `name` parameter |
| HTTP calls | `HTTPRequestNode` | `HTTPClientNode` (deprecated) |
| Transform data | `DataTransformer` | Complex PythonCodeNode |

## 📁 Guide Structure
- **[01-node-basics.md](01-node-basics.md)** - Creating nodes, base classes
- **[02-parameter-types.md](02-parameter-types.md)** - ⚠️ Type constraints (CRITICAL)
- **[03-common-patterns.md](03-common-patterns.md)** - Data processing, API, transform
- **[04-pythoncode-node.md](04-pythoncode-node.md)** - ⚠️ Input exclusion, serialization
- **[05-directory-reader.md](05-directory-reader.md)** - File discovery patterns
- **[06-document-processing.md](06-document-processing.md)** - Multi-file workflows
- **[07-troubleshooting.md](07-troubleshooting.md)** - Common errors and fixes
- **[examples/](examples/)** - Working code examples

## ⚡ Quick Fix Templates

### Basic Custom Node
```python
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter

class YourNode(Node):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            'param': NodeParameter(
                name='param',
                type=str,  # Use basic type or Any
                required=True,
                description='Description'
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        return {'result': kwargs['param']}
```

### PythonCodeNode (Best Practices)

**⚠️ MOST COMMON MISTAKE: Not using from_function for complex code**
*"This mistake keeps occurring every new run" - Session 064*

**🚀 MANDATORY: Use `.from_function()` for code > 3 lines**
```python
# ✅ ALWAYS use from_function for complex logic:
def process_files(input_data: dict) -> dict:
    """Full IDE support: highlighting, completion, debugging!"""
    files = input_data.get("files", [])
    # Complex processing with IDE support
    processed = [transform(f) for f in files]
    return {"result": processed, "count": len(processed)}

processor = PythonCodeNode.from_function(
    func=process_files,
    name="processor",
    description="Process file data"
)
```

**String code only for: dynamic generation, user input, templates, one-liners**
```python
# OK for simple one-liner
node = PythonCodeNode(name="calc", code="result = value * 1.1")

# OK for dynamic generation
code = f"result = data['{user_field}'] > {threshold}"
node = PythonCodeNode(name="filter", code=code)
```

**⚠️ Remember: Input variables EXCLUDED from outputs**
```python
# CORRECT: Different variable names for mapping
workflow.connect("discovery", "processor", mapping={"result": "input_data"})
```

### DirectoryReaderNode (Best Practice)
```python
from kailash.nodes.data import DirectoryReaderNode

# Better than manual file discovery
file_discoverer = DirectoryReaderNode(
    name="discoverer",
    directory_path="data/inputs",
    recursive=False,
    file_patterns=["*.csv", "*.json", "*.txt"],
    include_metadata=True
)
```

### Centralized Data Access
```python
from examples.utils.data_paths import get_input_data_path, get_output_data_path

# CORRECT: Use centralized data utilities
customer_file = get_input_data_path("customers.csv")
output_file = get_output_data_path("processed_data.csv")

reader = CSVReaderNode(name="reader", file_path=str(customer_file))

# WRONG: Hardcoded paths
reader = CSVReaderNode(name="reader", file_path="examples/data/customers.csv")
```

## 🔴 Common Mistakes
1. **Forgetting node suffix**: `CSVReader` → `CSVReaderNode`
2. **Using generic types**: `List[str]` → `list`
3. **Mapping to same variable**: `{"result": "result"}` → `{"result": "input_data"}`
4. **Missing PythonCodeNode name**: `PythonCodeNode(code=...)` → `PythonCodeNode(name="x", code=...)`
5. **Manual file operations**: Use `DirectoryReaderNode` not `os.listdir`
6. **Hardcoded data paths**: `"examples/data/file.csv"` → Use `get_input_data_path("file.csv")`
7. **Old execution pattern**: `node.run()` → Use `node.execute()` for complete lifecycle