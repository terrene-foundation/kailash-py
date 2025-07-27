# Critical Rules for Kailash SDK Success

*5 essential rules that prevent 90% of common errors*

## 📦 **Required Imports**

All examples in this guide assume these imports:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode, JSONReaderNode, JSONWriterNode, TextReaderNode, TextWriterNode, DirectoryReaderNode
from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.logic import SwitchNode, MergeNode, WorkflowNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.transform import DataTransformerNode, FilterNode
from kailash.nodes.base import Node, NodeParameter
from kailash.security import SecurityConfig
from kailash.access_control import UserContext
```

## 🚨 **Rule #1: ALWAYS Use Exact Method Names**

### ✅ **Correct Patterns**
```python

# Workflow methods - exact names required
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "node_id", {"code": "result = {'value': 42}"})
workflow.add_connection("from_node", "result", "to_node", "input_data")

# Validation
built_workflow = workflow.build()
built_workflow.validate()

# Runtime execution (recommended)
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)

```

### ❌ **Invalid Patterns (Will Cause Errors)**
```python

# These methods DO NOT EXIST
workflow = WorkflowBuilder()
workflow.runtime.execute(workflow.build(), runtime)     # INVALID - backwards pattern
workflow = WorkflowBuilder()
workflow.addNode()           # INVALID - camelCase
workflow = WorkflowBuilder()
workflow.add()               # INVALID - incomplete name
workflow = WorkflowBuilder()
workflow.node()              # INVALID - wrong name
workflow = WorkflowBuilder()
workflow.run()               # INVALID - should be execute()
workflow = WorkflowBuilder()
workflow.connectNodes()      # INVALID - wrong name

```

## 🚨 **Rule #2: Node Class Names Must End with "Node"**

### ✅ **Correct Node Names**
```python
# All node classes end with "Node"
from kailash.nodes.data import CSVReaderNode, JSONWriterNode, TextReaderNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import WorkflowNode, SwitchNode, MergeNode
from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode
from kailash.nodes.transform import DataTransformerNode, FilterNode

```

### ❌ **Invalid Node Names (Do Not Exist)**
```python
# These classes DO NOT EXIST
from kailash.nodes.data import CSVReader        # Missing "Node"
from kailash.nodes.api import HTTPRequest       # Missing "Node"
from kailash.nodes.code import PythonCode       # Missing "Node"
from kailash.nodes.logic import Switch          # Missing "Node"
from kailash.nodes.ai import LLMAgent           # Missing "Node"

```

## 🚨 **Rule #3: Parameter Order and Names are STRICT**

### ✅ **Correct Parameter Patterns**
```python

# Workflow methods with exact signatures
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = input_data"})

# Examples with correct parameter order
workflow.add_connection("reader", "data", "processor", "input_data")

# Runtime execution with correct parameter name
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "processor": {"additional_param": "value"}
})

```

### ❌ **Invalid Parameter Patterns**
```python

# Wrong parameter order
workflow = WorkflowBuilder()
workflow.add_node("reader", "CSVReaderNode", {"file_path": "data.csv"})  # WRONG ORDER - should be node_type, node_id, config
workflow.add_connection("from_node", "to_node", "output", "input")  # WRONG ORDER - should be from_node, output, to_node, input

# Wrong parameter names
runtime = LocalRuntime()
runtime.execute(workflow.build(), config={"node": {}})     # WRONG: should be 'parameters'
runtime.execute(workflow.build(), overrides={"param": ""}) # WRONG: should be 'parameters'
runtime.execute(workflow.build(), inputs={"data": []})     # WRONG: should be 'parameters'

```

## 🚨 **Rule #4: Configuration Keys are Case-Sensitive**

### ✅ **Correct Configuration Keys**
```python

# Exact key names required
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "data.csv",        # Correct key
    "has_header": True,             # Correct key
    "delimiter": ","                # Correct key
})

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "llm", {}),
    provider="openai",           # Correct key
    model="gpt-4",              # Correct key
    temperature=0.7,            # Correct key
    max_tokens=1000             # Correct key
)

```

### ❌ **Invalid Configuration Keys**
```python

# Wrong case or naming
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {}),
    filePath="data.csv",        # WRONG: should be file_path
    hasHeader=True,             # WRONG: should be has_header
    Delimiter=","               # WRONG: should be delimiter
)

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "llm", {}),
    Provider="openai",          # WRONG: should be provider
    Model="gpt-4",             # WRONG: should be model
    Temperature=0.7,           # WRONG: should be temperature
    maxTokens=1000             # WRONG: should be max_tokens
)

```

## 🚨 **Rule #5: Import Paths are Exact**

### ✅ **Correct Import Paths**
```python
# Core imports
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Node imports - exact module paths
from kailash.nodes.data import CSVReaderNode, JSONReaderNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode
from kailash.nodes.transform import DataTransformerNode

# Utility imports
from kailash.security import SecurityConfig
from kailash.access_control import UserContext

```

### ❌ **Invalid Import Paths**
```python
# These import paths DO NOT EXIST
from kailash.nodes import CSVReaderNode        # WRONG: missing specific module
from kailash.data import CSVReaderNode         # WRONG: incorrect path
from kailash.api import HTTPRequestNode        # WRONG: incorrect path
from kailash.code import PythonCodeNode        # WRONG: incorrect path
from kailash.ai import LLMAgentNode           # WRONG: incorrect path

# Incorrect runtime imports
from kailash import LocalRuntime              # WRONG: incorrect path
from kailash.runtime.local import LocalRuntime      # WRONG: missing .local

```

## 🔧 **Quick Validation Function**

```python
def validate_kailash_pattern(workflow_code) -> bool:
    """
    Quick validation function to check if code follows critical rules
    """
    checks = [
        # Rule 1: Method names
        "workflow.add_node(" in workflow_code,
        "workflow.add_connection("source", "result", "target", "input")  # Fixed complex pattern
        "Node(" in workflow_code,

        # Rule 3: No backwards patterns
        "runtime.execute(workflow.build(), runtime)" not in workflow_code,

        # Rule 4: Proper parameter names
        "parameters=" in workflow_code or "# mapping removed,

        # Rule 5: No camelCase
        "addNode" not in workflow_code,
        "connectNodes" not in workflow_code
    ]

    passed_checks = sum(checks)
    total_checks = len(checks)

    print(f"Validation: {passed_checks}/{total_checks} checks passed")

    if passed_checks == total_checks:
        print("✅ Code follows all critical rules!")
        return True
    else:
        print("❌ Code violates critical rules - check the patterns above")
        return False

# Usage
code_snippet = '''
workflow.add_node("CSVReaderNode", "reader", {}), file_path="data.csv")
workflow.add_connection("reader", "processor", "data", "input")
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
'''

validate_kailash_pattern(code_snippet)

```

## 📋 **Success Checklist**

Before executing any Kailash SDK code, verify:

- [ ] ✅ **Method names**: `add_node()`, `connect()`, `execute()` (not camelCase)
- [ ] ✅ **Node classes**: All end with "Node" suffix
- [ ] ✅ **Parameter order**: Correct order for all method calls
- [ ] ✅ **Configuration keys**: Exact case-sensitive key names
- [ ] ✅ **Import paths**: Full module paths (e.g., `kailash.nodes.data`)
- [ ] ✅ **Execution pattern**: `runtime.execute(workflow.build())` not `runtime.execute(workflow.build(), runtime)`

## 🚨 **Emergency Debugging**

If your code fails, check these in order:

1. **Method names** - Are you using exact method names?
2. **Node names** - Do all classes end with "Node"?
3. **Parameter order** - Is node_id first, then node class, then config?
4. **Import paths** - Are you importing from the correct modules?
5. **Configuration keys** - Are keys exactly as documented?

## 🔗 **Next Steps**

- **[Common Mistakes](common-mistakes.md)** - See real examples of what to avoid
- **[API Reference](api-reference.md)** - Complete method signatures
- **[Claude Code Guide](../cheatsheet/000-claude-code-guide.md)** - Comprehensive success patterns

---

**Remember: Following these 5 rules prevents 90% of all Kailash SDK errors!**
