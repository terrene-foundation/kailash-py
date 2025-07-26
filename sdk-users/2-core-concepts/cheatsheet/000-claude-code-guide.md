# Claude Code Guide - Kailash SDK Mastery

*Essential patterns for Claude Code to successfully work with Kailash SDK*

## 🎯 Core Principles

### ✅ Always Use These Patterns
```python
# 1. STANDARD IMPORTS - Import exactly this way
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.code import PythonCodeNode

# 2. WORKFLOW CREATION - Always include name
workflow = WorkflowBuilder()

# 3. EXECUTION PATTERN - Always use runtime.execute()
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# 4. PARAMETER PASSING - Use parameters={} dict
results, run_id = runtime.execute(workflow, parameters={
    "node_id": {"param_name": "value"}
})

```

### ❌ Never Use These Patterns
```python
# ❌ WRONG - Missing runtime
workflow = WorkflowBuilder()
runtime.execute(workflow.build(), )  # AttributeError - workflows don't have execute()

# ❌ WRONG - Wrong parameter name
runtime = LocalRuntime()
runtime.execute(workflow, parameters={"data": []})  # Wrong param name

# ❌ WRONG - Missing workflow name
workflow = WorkflowBuilder()

# ❌ WRONG - Direct node execution
node = "CSVReaderNode"
result = node.run()

```

## 📋 Parameter Passing Mastery

### Runtime Parameters (Most Common)
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Override node configurations at runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "csv_reader": {
        "file_path": "/new/path.csv",    # Override config
        "delimiter": "|"                 # Override config
    },
    "processor": {
        "custom_data": [1, 2, 3]        # Inject new data
    }
})

```

### PythonCodeNode Parameter Patterns
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ✅ CORRECT - Use input_types for parameters
workflow.add_node("PythonCodeNode", "processor", {}))

# Connect with proper mapping
workflow.add_connection("source", "result", "processor", "input")

```

### Connection Mapping Patterns
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ✅ CORRECT - Map outputs to inputs
workflow.add_connection("reader", "processor", "data", "input_data")  # Map 'data' output to 'input_data' input

# ✅ COMPLEX - Nested data mapping
workflow.add_connection("api_call", "result", "processor", "input")

# ✅ MULTIPLE OUTPUTS - Route specific outputs
workflow.add_connection("analyzer", "result", "report_generator", "input")

```

## 🤖 AI Agent Node Distribution

### Agent Location Map
```python
# A2A COORDINATION - Agent-to-Agent patterns
from kailash.nodes.ai.a2a import (
    A2ACoordinatorNode,     # Task delegation & coordination
    SharedMemoryPoolNode,   # Shared context between agents
    A2AAgentNode           # Individual coordinating agent
)

# SELF-ORGANIZING - Advanced agent pools
from kailash.nodes.ai.self_organizing import (
    AgentPoolManagerNode,   # Manage dynamic agent pools
    ProblemAnalyzerNode,    # Break down complex problems
    TeamFormationNode,      # Form agent teams
    SelfOrganizingAgentNode # Self-managing agents
)

# ORCHESTRATION - High-level coordination
from kailash.nodes.ai.intelligent_agent_orchestrator import (
    OrchestrationManagerNode, # Master orchestrator
    IntelligentCacheNode     # Smart caching for agents
)

# BASIC AI - Core LLM functionality
from kailash.nodes.ai import (
    LLMAgentNode,           # Basic LLM calls
    MonitoredLLMAgentNode,  # LLM with monitoring
    EmbeddingGeneratorNode  # Generate embeddings
)

```

### Agent Coordination Patterns
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# PATTERN 1: Basic A2A Coordination
workflow.add_node("A2ACoordinatorNode", "coordinator", {})
workflow.add_node("SharedMemoryPoolNode", "memory", {
    "memory_size_limit": 1000,
    "attention_window": 50
})
workflow.add_connection("memory", "result", "coordinator", "input")

# Execute with agent registration
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "register",
        "agent_info": {
            "id": "analyst_001",
            "skills": ["analysis", "data"],
            "role": "analyst"
        }
    }
})

# PATTERN 2: Self-Organizing System
workflow.add_node("AgentPoolManagerNode", "pool", {}))
workflow.add_node("OrchestrationManagerNode", "orchestrator", {}))
workflow.add_connection("orchestrator", "result", "pool", "input")

```

## 🌐 Middleware Integration Patterns

### Create Gateway (Primary Pattern)
```python
# ✅ CORRECT - Use create_gateway for all middleware
from kailash.api.middleware import create_gateway

# Basic gateway
gateway = create_gateway(
    title="My Application",
    cors_origins=["http://localhost:3000"],
    enable_docs=True
)

# Access components
agent_ui = gateway.agent_ui       # Session management
realtime = gateway.realtime       # WebSocket events
api_gateway = gateway.api_gateway # REST APIs

# Start server
gateway.run(port=8000)

```

### Session-Based Workflows
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Create session for user isolation
session_id = await agent_ui.create_session(user_id="user123")

# Dynamic workflow from frontend JSON
workflow_config = {
    "nodes": [
        {
            "id": "reader",
            "type": "CSVReaderNode",
            "config": {"name": "reader", "file_path": "/data/input.csv"}
        }
    ],
    "connections": []
}

# Create workflow in session
workflow_id = await agent_ui.create_dynamic_workflow(
    session_id=session_id,
    workflow_config=workflow_config
)

# Execute with monitoring
execution_id = await agent_ui.execute_workflow(
    session_id=session_id,
    workflow_id=workflow_id,
    parameters={"custom_param": "value"}
)

```

### Frontend Communication
```javascript
// Frontend pattern for middleware communication
const session = await fetch('http://localhost:8000/api/sessions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user_id: 'frontend_user'})
});

const execution = await fetch('http://localhost:8000/api/executions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        session_id: session.session_id,
        workflow_id: 'data_processing',
        inputs: {file_path: '/data/input.csv'}
    })
});

// Real-time updates via WebSocket
const ws = new WebSocket(`ws://localhost:8000/ws?session_id=${session.session_id}`);
ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    console.log('Update:', update);
};
```

## 🔧 Common Workflow Patterns

### ETL Pipeline
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()

# Extract
workflow.add_node("CSVReaderNode", "extractor", {
    "file_path": "/data/input.csv",
    "has_header": True
})

# Transform
workflow.add_node("PythonCodeNode", "transformer", {})}
        for row in data if row.get("active") == "true"
    ]
}
''',
    input_types={"data": list}
))

# Load
workflow.add_node("JSONWriterNode", "loader", {
    "file_path": "/data/output.json",
    "indent": 2
})

# Connect pipeline
workflow.add_connection("extractor", "transformer", "data", "data")
workflow.add_connection("transformer", "loader", "result.processed", "data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

### Conditional Processing
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Route data based on conditions
workflow.add_node("SwitchNode", "router", {
    "conditions": [
        {"output": "high", "expression": "score > 0.8"},
        {"output": "medium", "expression": "score > 0.5"},
        {"output": "low", "expression": "score <= 0.5"}
    ]
)

# Connect to different handlers
workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping
workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping
workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping

```

### Agent Coordination
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Multi-agent problem solving
workflow.add_node("A2ACoordinatorNode", "coordinator", {})
workflow.add_node("SharedMemoryPoolNode", "memory", {"memory_size_limit": 1000})

# Task delegation
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "delegate",
        "task": {
            "type": "analysis",
            "description": "Analyze Q4 sales data",
            "required_skills": ["analysis", "data"],
            "priority": "high"
        },
        "coordination_strategy": "best_match"
    }
})

```

## 🚨 Critical Success Rules

1. **ALWAYS** use `from kailash.workflow.builder import WorkflowBuilder` and `LocalRuntime()`
2. **ALWAYS** include workflow `name=` parameter
3. **ALWAYS** use `runtime.execute(workflow, parameters={})`
4. **ALWAYS** use `input_types={}` with PythonCodeNode
5. **ALWAYS** use `create_gateway()` for middleware (never raw FastAPI)
6. **ALWAYS** map connections with proper output→input mapping
7. **ALWAYS** handle the tuple return: `results, run_id = runtime.execute()`

## 📚 Next Steps

- [Workflow Patterns](004-common-node-patterns.md) - More node examples
- [Parameter Passing](006-execution-options.md) - Advanced parameter patterns
- [Middleware Guide](../middleware/README.md) - Complete middleware documentation
- [Agent Coordination](023-a2a-agent-coordination.md) - Advanced agent patterns
- [Common Mistakes](018-common-mistakes-to-avoid.md) - What to avoid

**Remember**: Follow these patterns exactly and Kailash SDK will work perfectly with Claude Code!
