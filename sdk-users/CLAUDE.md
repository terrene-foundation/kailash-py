# SDK Users - Essential Patterns Only

## 🚨 **Debugging Workflow Errors**
**"Node 'X' missing required inputs"** → [Parameter Solution Guide](2-core-concepts/validation/common-mistakes.md#mistake--1-missing-required-parameters-new-in-v070)

## ⚡ CRITICAL PATTERNS

### Workflow Pattern (Always use this)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "read", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "process", {"code": "result = len(data)"})
workflow.add_connection("read", "data", "process", "data")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())  # ALWAYS .build()
```

### Common Mistakes
```python
# ❌ NEVER
workflow.add_node("reader", CSVReaderNode(), {})  # Instance-based
workflow.connect("a", "b")                       # 2-param
runtime.execute(workflow)                        # Missing .build()

# ✅ ALWAYS
workflow.add_node("CSVReaderNode", "reader", {})  # String-based
workflow.add_connection("a", "data", "b", "input") # 4-param
runtime.execute(workflow.build())                  # With .build()
```

### PythonCodeNode Pattern
```python
# For >3 lines, use from_function
def process_data(data):
    return {"result": data}

workflow.add_node("process", PythonCodeNode.from_function(process_data))
```

### Quick Links
- **Node Selection**: [2-core-concepts/nodes/node-selection-guide.md](2-core-concepts/nodes/node-selection-guide.md)
- **Parameter Passing**: [3-development/parameter-passing-guide.md](3-development/parameter-passing-guide.md)
- **Common Errors**: [2-core-concepts/validation/common-mistakes.md](2-core-concepts/validation/common-mistakes.md)
- **Patterns**: [2-core-concepts/cheatsheet/](2-core-concepts/cheatsheet/)

## 🎯 Navigation

### Architecture Decisions
**ALWAYS check first**: [1-overview/decision-matrix.md](1-overview/decision-matrix.md)

### Core Concepts
- **Nodes**: [2-core-concepts/nodes/node-selection-guide.md](2-core-concepts/nodes/node-selection-guide.md)
- **Patterns**: [2-core-concepts/cheatsheet/](2-core-concepts/cheatsheet/)
- **Errors**: [2-core-concepts/validation/common-mistakes.md](2-core-concepts/validation/common-mistakes.md)

### Development
- **Guides**: [3-development/](3-development/)
- **Testing**: [3-development/12-testing-production-quality.md](3-development/12-testing-production-quality.md)
- **Async**: [3-development/async-node-guide.md](3-development/async-node-guide.md)

### Enterprise
- **Patterns**: [5-enterprise/](5-enterprise/)
- **Security**: [5-enterprise/security-patterns.md](5-enterprise/security-patterns.md)
- **Resilience**: [5-enterprise/resilience-patterns.md](5-enterprise/resilience-patterns.md)

### App Frameworks
- **DataFlow**: [../apps/kailash-dataflow/](../apps/kailash-dataflow/)
- **Nexus**: [../apps/kailash-nexus/](../apps/kailash-nexus/)

### Advanced Features
- **Edge Computing**: [4-features/edge/](4-features/edge/) - Migration, monitoring, coordination
- **MCP Integration**: [4-features/mcp/](4-features/mcp/) - Model Context Protocol
- **Middleware**: [4-features/middleware/](4-features/middleware/) - Custom middleware

### Workflow Guidance
- **Production Workflows**: [4-workflows/](4-workflows/)
- **Monitoring**: [6-monitoring/](6-monitoring/)

## ⚠️ Rules
- Check [1-overview/decision-matrix.md](1-overview/decision-matrix.md) FIRST
- Use string-based node API
- Use 4-parameter connections
- Always call .build() before execute
- Use .from_function() for PythonCodeNode >3 lines

---
**Root patterns**: [../CLAUDE.md](../CLAUDE.md)
**Contributors**: [../# contrib (removed)/CLAUDE.md](../# contrib (removed)/CLAUDE.md)
