# Kailash SDK API Reference

**Version**: v0.6.3 | **Complete API Documentation**

## 🎯 Quick Navigation

| What you need | File | Description |
|--------------|------|-------------|
| **Quick API lookup** | [api-reference.yaml](api-reference.yaml) | Complete API specifications |
| **Usage patterns** | [usage-guide.md](usage-guide.md) | Practical API usage examples |
| **Validation rules** | [validation-rules.md](validation-rules.md) | API validation and error handling |
| **Node parameters** | [node-parameters.md](node-parameters.md) | All node parameter specifications |

## 📚 API Categories

### Core Workflow APIs
- **WorkflowBuilder** - Dynamic workflow construction
- **Runtime** - Workflow execution engines
- **Node** - Base node functionality

### Node Categories
- **AI Nodes** - LLM, embedding, agent nodes
- **Data Nodes** - Database, file, API data sources
- **Logic Nodes** - Control flow, routing, merging
- **Transform Nodes** - Data transformation and processing

### Enterprise APIs
- **Authentication** - SSO, MFA, access control
- **Security** - Encryption, audit, compliance
- **Monitoring** - Metrics, logging, alerting

## 🚀 Quick Start

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Build workflow (no name parameter needed)
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("LLMAgentNode", "analyzer", {"model": "gpt-4"})
workflow.add_connection("reader", "result", "analyzer", "input_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## 🔧 API Validation

All APIs follow these validation rules:
- **Required parameters** must be provided
- **Type checking** enforced at runtime
- **Connection validation** ensures data flow correctness
- **Error handling** provides clear error messages

See [validation-rules.md](validation-rules.md) for complete validation specifications.

## 📖 Related Documentation

- **[Node Selection Guide](../nodes/node-selection-guide.md)** - Choose the right nodes
- **[Developer Guides](../developer/)** - Step-by-step development
- **[Cheatsheet](../cheatsheet/)** - Quick code patterns
- **[Enterprise Guide](../enterprise/)** - Advanced API usage

---

*Complete, tested, and production-ready API documentation for Kailash SDK v0.6.3*
