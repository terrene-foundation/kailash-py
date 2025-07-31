# Basic Imports - Essential Components

## Core Runtime
```python
# Essential workflow components
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
```

## Core Nodes
```python
# Essential processing nodes
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import SwitchNode, MergeNode
```

## Common Nodes
```python
# Data I/O
from kailash.nodes.data import CSVReaderNode, CSVWriterNode, JSONReaderNode

# Processing
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.transform import DataTransformer, FilterNode
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
from kailash.api.middleware import create_gateway

# AI Agent Distribution
from kailash.nodes.ai.a2a import A2AAgentNode, A2ACoordinatorNode
from kailash.nodes.ai.self_organizing import SelfOrganizingAgentNode

```

## Quick Start Pattern
```python
# Minimal imports for basic workflow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow with modern API
workflow = WorkflowBuilder()

# Add nodes with correct syntax
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = {'data': [1, 2, 3], 'count': 3}"
})

workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'processed_count': len(input_data.get('data', []))}"
})

# Connect with correct syntax
workflow.add_connection("data_source", "result", "processor", "input_data")

# Execute with enhanced error detection (v0.9.4+)
runtime = LocalRuntime()  # content_aware_success_detection=True by default
results, run_id = runtime.execute(workflow.build())
print(f"Processed {results['processor']['result']['processed_count']} items")
```

## Next Steps
- [Quick Workflow Creation](003-quick-workflow-creation.md) - Build workflows
- [Common Node Patterns](004-common-node-patterns.md) - Node usage examples
- [Node Catalog](../nodes/comprehensive-node-catalog.md) - All 110+ nodes
