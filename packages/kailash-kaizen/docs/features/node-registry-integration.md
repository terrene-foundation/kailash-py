# NodeRegistry Integration

Kaizen agents are automatically registered with the Kailash Core SDK's NodeRegistry, enabling them to be used in visual workflow editors and discovered programmatically.

## Automatic Registration

When Kaizen is imported, all specialized agents are registered with the Core SDK NodeRegistry:

```python
# Agents are auto-registered when kaizen is imported
import kaizen

from kailash.nodes import NodeRegistry

# List all available agent nodes
agent_nodes = [n for n in NodeRegistry.list_nodes() if "AgentNode" in n]
# ['SimpleQAAgentNode', 'ReActAgentNode', 'ChainOfThoughtAgentNode', ...]
```

## Registered Agents

| Agent | Node Name | Description |
|-------|-----------|-------------|
| SimpleQAAgent | SimpleQAAgentNode | Basic question answering |
| ReActAgent | ReActAgentNode | Reasoning + Acting with tools |
| ChainOfThoughtAgent | ChainOfThoughtAgentNode | Step-by-step reasoning |
| RAGResearchAgent | RAGResearchAgentNode | Retrieval-augmented generation |
| CodeGenerationAgent | CodeGenerationAgentNode | Multi-language code generation |
| VisionAgent | VisionAgentNode | Image analysis and OCR |
| MemoryAgent | MemoryAgentNode | Multi-turn conversation |
| BatchProcessingAgent | BatchProcessingAgentNode | High-throughput batch processing |
| HumanApprovalAgent | HumanApprovalAgentNode | Human-in-the-loop decisions |
| ResilientAgent | ResilientAgentNode | Multi-model fallback |
| StreamingChatAgent | StreamingChatAgentNode | Real-time token streaming |
| SelfReflectionAgent | SelfReflectionAgentNode | Iterative self-improvement |
| TranscriptionAgent | TranscriptionAgentNode | Audio transcription |
| MultiModalAgent | MultiModalAgentNode | Vision + audio + text |

## Usage in Workflows

Use agents in Kailash workflows via WorkflowBuilder:

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Add agent as a node
workflow.add_node("SimpleQAAgentNode", "qa_step", {
    "question": "What is Python?",
    "llm_provider": "ollama",
    "model": "llama2"
})

# Connect to other nodes
workflow.add_node("TransformNode", "format", {"template": "Answer: {answer}"})
workflow.connect("qa_step", "format", {"answer": "answer"})
```

## Manual Registration

To manually trigger registration:

```python
from kaizen.agents.nodes import register_agents_with_node_registry

register_agents_with_node_registry()
```

## Architecture

Kaizen agents inherit from `BaseAgent`, which inherits from the Core SDK's `Node` class. This means:

- Agents ARE nodes - no wrapper needed
- Full compatibility with WorkflowBuilder
- Agents can be mixed with other node types in workflows
