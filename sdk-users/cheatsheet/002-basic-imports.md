# Basic Imports - Essential Components

## Core Workflow
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime

```

## Common Nodes
```python
# Data I/O
from kailash.nodes.data import CSVReaderNode, CSVWriterNode, JSONReaderNode

# Processing
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.transform import DataTransformerNode
from kailash.nodes.logic import SwitchNode, MergeNode

# AI/LLM
from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode

```

## Advanced Components
```python
# Security & Access Control
from kailash.runtime.access_controlled import AccessControlledRuntime
from kailash.access_control import UserContext, PermissionRule

# API & Integration
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.api.gateway import WorkflowAPIGateway

# AI Agent Distribution
from kailash.nodes.ai.a2a import A2AAgentNode, A2ACoordinatorNode
from kailash.nodes.ai.self_organizing import SelfOrganizingAgentNode

```

## Quick Start Pattern
```python
# Minimal imports for basic workflow
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.code import PythonCodeNode

# Create and execute
workflow = Workflow("example", name="Example")
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
workflow.add_node("process", PythonCodeNode(
    name="process",
    code="result = {'count': len(data)}",
    input_types={"data": list}
))
workflow.connect("reader", "process")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

## Next Steps
- [Quick Workflow Creation](003-quick-workflow-creation.md) - Build workflows
- [Common Node Patterns](004-common-node-patterns.md) - Node usage examples
- [Node Catalog](../nodes/comprehensive-node-catalog.md) - All 110+ nodes
