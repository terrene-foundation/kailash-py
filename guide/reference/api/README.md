# Kailash SDK API Reference

**Version**: 0.1.4 | **Last Updated**: 2025-01-06

This directory contains the complete API reference for the Kailash Python SDK, organized by module and functionality.

## 📁 API Reference Files

| File | Module | Description |
|------|---------|-------------|
| [01-core-workflow.yaml](01-core-workflow.yaml) | `kailash.workflow` | Core Workflow and WorkflowBuilder classes |
| [02-runtime.yaml](02-runtime.yaml) | `kailash.runtime` | Execution runtimes (Local, Async, Parallel, Docker) |
| [03-nodes-base.yaml](03-nodes-base.yaml) | `kailash.nodes.base*` | Base node classes and abstractions |
| [04-nodes-ai.yaml](04-nodes-ai.yaml) | `kailash.nodes.ai` | AI/ML nodes (LLM, A2A, Self-organizing) |
| [05-nodes-data.yaml](05-nodes-data.yaml) | `kailash.nodes.data` | Data I/O nodes (Readers, Writers, Sources) |
| [06-nodes-logic.yaml](06-nodes-logic.yaml) | `kailash.nodes.logic` | Control flow nodes (Switch, Merge, Workflow) |
| [07-nodes-transform.yaml](07-nodes-transform.yaml) | `kailash.nodes.transform` | Data transformation nodes |
| [08-nodes-api.yaml](08-nodes-api.yaml) | `kailash.nodes.api` | API integration nodes (HTTP, REST, GraphQL) |
| [09-security-access.yaml](09-security-access.yaml) | `kailash.security/access_control` | Security and access control |
| [10-visualization.yaml](10-visualization.yaml) | `kailash.visualization` | Visualization and reporting |
| [11-tracking.yaml](11-tracking.yaml) | `kailash.tracking` | Task tracking and metrics |
| [12-integrations.yaml](12-integrations.yaml) | Various | MCP, SharePoint, API Gateway integrations |
| [13-utils.yaml](13-utils.yaml) | `kailash.utils` | Utilities (Export, Templates) |

## 🚀 Quick Navigation

### By Use Case
- **Building Workflows** → [01-core-workflow.yaml](01-core-workflow.yaml)
- **Running Workflows** → [02-runtime.yaml](02-runtime.yaml)
- **AI Integration** → [04-nodes-ai.yaml](04-nodes-ai.yaml)
- **Data Processing** → [05-nodes-data.yaml](05-nodes-data.yaml)
- **API Calls** → [08-nodes-api.yaml](08-nodes-api.yaml)
- **Security** → [09-security-access.yaml](09-security-access.yaml)

### By Module
- `from kailash import Workflow` → [01-core-workflow.yaml](01-core-workflow.yaml)
- `from kailash.runtime.local import LocalRuntime` → [02-runtime.yaml](02-runtime.yaml)
- `from kailash.nodes.ai import LLMAgentNode` → [04-nodes-ai.yaml](04-nodes-ai.yaml)
- `from kailash.nodes.data import CSVReaderNode` → [05-nodes-data.yaml](05-nodes-data.yaml)

## 📋 File Format

Each YAML file follows this structure:

```yaml
# Module name and description
module_name:
  module: full.python.module.path
  description: "Module description"

  classes:
    ClassName:
      description: "Class description"
      import: "from module import ClassName"
      methods:
        method_name:
          signature: "method(params) -> return_type"
          description: "What it does"
          params:
            param_name: "Description"
          example: |
            # Example code
```

## 🔍 Finding APIs

1. **Know the module?** → Check the corresponding file number
2. **Know the use case?** → Use Quick Navigation above
3. **Searching for a class?** → Check the table for the right category
4. **Need examples?** → Each API includes usage examples

## See Also
- [Node Catalog](../nodes/README.md) - Detailed node documentation
- [Validation Guide](../validation/validation-guide.md) - API usage rules
- [Cheatsheet](../cheatsheet/README.md) - Quick code snippets
