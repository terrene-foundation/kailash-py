# Common Mistakes & How to Fix Them

*Real examples of errors and their solutions*

## 📦 **Required Imports**

All examples in this guide assume these imports:

```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode, JSONReaderNode, JSONWriterNode
from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.logic import SwitchNode, MergeNode, WorkflowNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.transform import DataTransformerNode
from kailash.nodes.base import Node, NodeParameter
```

## 🚨 **Most Common Mistakes**

### **Mistake #1: Cycle Parameter Passing Errors**

```python
# ❌ WRONG - Direct field mapping for PythonCodeNode
counter = PythonCodeNode.from_function(lambda x=0: {"count": x+1}, name="counter")
workflow.connect("counter", "counter", {"count": "x"}, cycle=True)

# ✅ CORRECT - Use dot notation for PythonCodeNode outputs
workflow.connect("counter", "counter", {"result.count": "x"}, cycle=True)
```

```python
# ❌ WRONG - No initial parameters for cycle
runtime.execute(workflow)  # ERROR: Required parameter 'x' not provided

# ✅ CORRECT - Provide initial parameters
runtime.execute(workflow, parameters={"counter": {"x": 0}})
```

```python
# ❌ WRONG - Dot notation in convergence check
.converge_when("result.done == True")

# ✅ CORRECT - Flattened field names in convergence
.converge_when("done == True")
```

### **Mistake #2: Wrong Execution Pattern**
```python

# ❌ WRONG - This will cause an error
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.workflow.execute(runtime)

# ✅ CORRECT - Two valid patterns
# Pattern 1: Direct execution (basic features)
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.execute()

# Pattern 2: Runtime execution (recommended)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

### **Mistake #2: Wrong Parameter Name for Overrides**
```python

# ❌ WRONG - These parameter names don't exist
runtime = LocalRuntime()
workflow.execute(workflow, inputs={"reader": {"file_path": "data.csv"}})
runtime = LocalRuntime()
workflow.execute(workflow, config={"reader": {"file_path": "data.csv"}})
runtime = LocalRuntime()
workflow.execute(workflow, overrides={"reader": {"file_path": "data.csv"}})

# ✅ CORRECT - Use 'parameters'
runtime = LocalRuntime()
# Parameters setup
workflow.{"reader": {"file_path": "data.csv"}})

```

### **Mistake #3: Missing "Node" Suffix**
```python
# ❌ WRONG - These classes don't exist
from kailash.nodes.data import CSVReader, JSONWriter
from kailash.nodes.api import HTTPRequest, RESTClient

# ✅ CORRECT - All classes end with "Node"
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode

```

### **Mistake #4: CamelCase Method Names**
```python

# ❌ WRONG - camelCase methods don't exist
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.workflow.addNode("reader", CSVReaderNode())
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connectNodes("reader", "processor")

# ✅ CORRECT - Use snake_case
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.add_node("reader", CSVReaderNode())
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor")

```

### **Mistake #5: Wrong Parameter Order**
```python

# ❌ WRONG - Parameter order matters
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.add_node(CSVReaderNode(), "reader", file_path="data.csv")
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

# ✅ CORRECT - node_id first, then node, then config
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

```

## 🔧 **Real Error Examples & Fixes**

### **Example 1: CSV Reading Gone Wrong**

#### ❌ **Broken Code**
```python
from kailash import Workflow
from kailash.nodes.data import CSVReader  # WRONG: Missing "Node"

workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.workflow.addNode("reader", CSVReader(),   # WRONG: camelCase method
    filePath="data.csv")                  # WRONG: camelCase config key

runtime = LocalRuntime()
results = workflow.execute(runtime)      # WRONG: backwards execution

```

#### ✅ **Fixed Code**
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode  # CORRECT: With "Node"

workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.add_node("reader", CSVReaderNode(),  # CORRECT: snake_case
    file_path="data.csv")                     # CORRECT: snake_case key

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)  # CORRECT: runtime executes workflow

```

### **Example 2: LLM Integration Mistakes**

#### ❌ **Broken Code**
```python
from kailash.nodes.ai import LLMAgent     # WRONG: Missing "Node"

workflow.add_node("llm", LLMAgent(),      # WRONG: Class doesn't exist
    Provider="openai",                    # WRONG: Capital P
    Model="gpt-4",                       # WRONG: Capital M
    Temperature=0.7)                     # WRONG: Capital T

runtime.execute(workflow, inputs={       # WRONG: 'inputs' parameter
    "llm": {"prompt": "Hello"}
})

```

#### ✅ **Fixed Code**
```python
from kailash.nodes.ai import LLMAgentNode  # CORRECT: With "Node"

workflow.add_node("llm", LLMAgentNode(),   # CORRECT: Proper class name
    provider="openai",                     # CORRECT: lowercase
    model="gpt-4",                        # CORRECT: lowercase
    temperature=0.7)                      # CORRECT: lowercase

runtime.execute(workflow, parameters={    # CORRECT: 'parameters'
    "llm": {"prompt": "Hello"}
})

```

### **Example 3: Connection Mapping Errors**

#### ❌ **Broken Code**
```python

# Wrong mapping parameter order
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

# Missing mapping parameter name
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

# Self-referencing mapping in PythonCodeNode
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

```

#### ✅ **Fixed Code**
```python

# Correct parameter order with explicit mapping
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

# Automatic mapping when names match
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor")  # maps "data" → "data"

# Proper cyclic connection (different output/input names)
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

```

## 🐛 **Debugging Checklist**

When your code fails, check these in order:

### **1. Import Errors**
```python
# ✅ Check imports are correct
from kailash import Workflow                           # Core
from kailash.runtime.local import LocalRuntime        # Runtime
from kailash.nodes.data import CSVReaderNode          # Data nodes
from kailash.nodes.ai import LLMAgentNode             # AI nodes
from kailash.nodes.api import HTTPRequestNode         # API nodes

```

### **2. Method Name Errors**
```python

# ✅ Verify you're using correct method names
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.add_node()    # NOT addNode()
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect()     # NOT connectNodes()
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.workflow.validate()    # NOT check()
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.workflow.execute()     # NOT run()

```

### **3. Class Name Errors**
```python
# ✅ All node classes end with "Node"
CSVReaderNode     # NOT CSVReader
LLMAgentNode      # NOT LLMAgent
HTTPRequestNode   # NOT HTTPRequest
PythonCodeNode    # NOT PythonCode

```

### **4. Parameter Errors**
```python
# ✅ Check parameter names and order
workflow.add_node("id", NodeClass(), **config)        # Correct order
runtime.execute(workflow, parameters={...})           # Use 'parameters'
workflow.connect("from", "to", mapping={...})         # Use 'mapping'

```

### **5. Configuration Key Errors**
```python
# ✅ Use exact configuration keys (case-sensitive)
file_path="..."     # NOT filePath
has_header=True     # NOT hasHeader
max_tokens=100      # NOT maxTokens
temperature=0.7     # NOT Temperature

```

## 🔍 **Error Message Decoder**

### **"AttributeError: 'Workflow' object has no attribute 'addNode'"**
- **Problem**: Using camelCase method name
- **Fix**: Use `workflow.add_node()` instead of `workflow.addNode()`

### **"ModuleNotFoundError: No module named 'kailash.nodes.data.CSVReader'"**
- **Problem**: Missing "Node" suffix in class name
- **Fix**: Use `CSVReaderNode` instead of `CSVReader`

### **"TypeError: execute() takes 1 positional argument but 2 were given"**
- **Problem**: Using backwards execution pattern
- **Fix**: Use `runtime.execute(workflow)` not `workflow.execute(runtime)`

### **"TypeError: execute() got an unexpected keyword argument 'inputs'"**
- **Problem**: Wrong parameter name for runtime overrides
- **Fix**: Use `parameters={}` instead of `inputs={}`

### **"TypeError: add_node() missing 1 required positional argument"**
- **Problem**: Wrong parameter order
- **Fix**: node_id first, then node class: `add_node("id", NodeClass())`

## ✅ **Validation Function for Your Code**

```python
def debug_workflow_code(workflow_code):
    """Debug common issues in workflow code"""
    issues = []

    # Check for camelCase methods
    if "addNode" in workflow_code:
        issues.append("❌ Use 'add_node()' not 'addNode()'")
    if "connectNodes" in workflow_code:
        issues.append("❌ Use 'connect()' not 'connectNodes()'")

    # Check for missing "Node" suffix
    if "CSVReader(" in workflow_code and "CSVReaderNode(" not in workflow_code:
        issues.append("❌ Use 'CSVReaderNode' not 'CSVReader'")
    if "LLMAgent(" in workflow_code and "LLMAgentNode(" not in workflow_code:
        issues.append("❌ Use 'LLMAgentNode' not 'LLMAgent'")

    # Check for wrong execution pattern
    if "workflow.execute(runtime)" in workflow_code:
        issues.append("❌ Use 'runtime.execute(workflow)' not 'workflow.execute(runtime)'")

    # Check for wrong parameter names
    if "inputs=" in workflow_code:
        issues.append("❌ Use 'parameters=' not 'inputs='")

    # Check for camelCase config keys
    if "filePath" in workflow_code:
        issues.append("❌ Use 'file_path' not 'filePath'")
    if "hasHeader" in workflow_code:
        issues.append("❌ Use 'has_header' not 'hasHeader'")

    if issues:
        print("🐛 Issues found:")
        for issue in issues:
            print(f"  {issue}")
        return False
    else:
        print("✅ No common issues detected!")
        return True

# Usage
your_code = '''
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
runtime.execute(workflow, parameters={"reader": {"delimiter": ","}})
'''

debug_workflow_code(your_code)

```

## 📚 **Quick Fix Templates**

### **Template 1: Basic CSV Processing**
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.code import PythonCodeNode

workflow = Workflow("csv_processing", name="CSV Processing")

workflow.add_node("reader", CSVReaderNode(),
    file_path="input.csv",
    has_header=True,
    delimiter=","
)

workflow.add_node("processor", PythonCodeNode(
    name="processor",
    code="result = {'processed': [row for row in data]}",
    input_types={"data": list}
))

workflow.add_node("writer", CSVWriterNode(),
    file_path="output.csv",
    include_header=True
)

workflow.connect("reader", "processor", mapping={"data": "data"})
workflow.connect("processor", "writer", mapping={"processed": "data"})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

### **Template 2: API + LLM Processing**
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import PythonCodeNode

workflow = Workflow("api_llm", name="API + LLM Processing")

workflow.add_node("api", HTTPRequestNode(),
    url="https://api.example.com/data",
    method="GET"
)

workflow.add_node("llm", LLMAgentNode(),
    provider="openai",
    model="gpt-4",
    temperature=0.7
)

workflow.connect("api", "llm", mapping={"response": "prompt"})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

## 🔗 **Next Steps**

- **[API Reference](api-reference.md)** - Complete method signatures
- **[Critical Rules](critical-rules.md)** - Review the 5 essential rules
- **[Advanced Patterns](advanced-patterns.md)** - Complex usage scenarios

---

**Remember: Most errors come from these 5 common mistakes. Check them first!**
