# Integration Patterns

Complete guide to integrating Kaizen agents with DataFlow, Nexus, and MCP.

## 🔌 Integration Overview

Kaizen agents integrate seamlessly with the Kailash ecosystem:
- **DataFlow**: Database operations with AI agents
- **Nexus**: Multi-channel deployment (API/CLI/MCP)
- **MCP**: Model Context Protocol for AI assistants
- **Core SDK**: Workflow-based integration

## 🗄️ DataFlow Integration

### Basic Pattern: AI + Database

```python
from dataflow import DataFlow
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Step 1: Create DataFlow model
db = DataFlow()

@db.model
class QASession:
    question: str
    answer: str
    confidence: float
    timestamp: str

# Step 2: Create Kaizen agent
agent = SimpleQAAgent(QAConfig(llm_provider="openai", model="gpt-4"))

# Step 3: Get AI response
result = agent.ask("What is the capital of France?")

# Step 4: Store in database via workflow
workflow = WorkflowBuilder()
workflow.add_node("QASessionCreateNode", "store", {
    "question": "What is the capital of France?",
    "answer": result["answer"],
    "confidence": result.get("confidence", 0.0),
    "timestamp": "2025-01-17T10:30:00"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Advanced: Query + AI Analysis

```python
from dataflow import DataFlow
from kaizen.agents import SimpleQAAgent
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# DataFlow for data retrieval
db = DataFlow()

@db.model
class SalesRecord:
    product: str
    amount: float
    date: str

# Workflow: Query data
workflow = WorkflowBuilder()
workflow.add_node("SalesRecordListNode", "get_sales", {
    "filter": {"date": {"$gte": "2025-01-01"}},
    "limit": 100
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
sales_data = results["get_sales"]["result"]

# Kaizen for AI analysis
agent = SimpleQAAgent(QAConfig())
analysis = agent.ask(
    f"Analyze this sales data and provide insights: {sales_data[:5]}"
)
print(analysis["answer"])
```

### Pattern: Multi-Modal + Database

```python
from dataflow import DataFlow
from kaizen.agents import VisionAgent, VisionAgentConfig
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# DataFlow model for image analysis results
db = DataFlow()

@db.model
class ImageAnalysis:
    image_path: str
    analysis: str
    detected_objects: str
    timestamp: str

# Vision agent
config = VisionAgentConfig(llm_provider="ollama", model="bakllava")
agent = VisionAgent(config=config)

# Analyze image
result = agent.analyze(
    image="/path/to/product.jpg",
    question="Describe this product and list all visible features"
)

# Store analysis in database
workflow = WorkflowBuilder()
workflow.add_node("ImageAnalysisCreateNode", "store", {
    "image_path": "/path/to/product.jpg",
    "analysis": result['answer'],
    "detected_objects": result.get('objects', ''),
    "timestamp": "2025-01-17T11:00:00"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## 🌐 Nexus Integration

### Basic Pattern: Multi-Channel Agent Deployment

```python
from nexus import Nexus
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

# Step 1: Create Kaizen agent
agent = SimpleQAAgent(QAConfig(llm_provider="openai", model="gpt-4"))

# Step 2: Convert agent to workflow
agent_workflow = agent.to_workflow()

# Step 3: Create Nexus platform
nexus = Nexus(
    title="AI Q&A Platform",
    enable_api=True,
    enable_cli=True,
    enable_mcp=True
)

# Step 4: Register agent
nexus.register("qa_agent", agent_workflow.build())

# Agent now available on all channels:
# - REST API: POST /workflows/qa_agent
# - CLI: nexus run qa_agent --question "What is AI?"
# - MCP: qa_agent tool for AI assistants like Claude
```

### Advanced: Multiple Agents via Nexus

```python
from nexus import Nexus
from kaizen.agents import (
    SimpleQAAgent,
    ChainOfThoughtAgent,
    VisionAgent
)
from kaizen.agents.specialized.simple_qa import QAConfig
from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtConfig
from kaizen.agents import VisionAgentConfig

# Create multiple specialized agents
qa_agent = SimpleQAAgent(QAConfig())
cot_agent = ChainOfThoughtAgent(ChainOfThoughtConfig())
vision_agent = VisionAgent(VisionAgentConfig(llm_provider="ollama", model="bakllava"))

# Create Nexus platform
nexus = Nexus(title="Multi-Agent Platform")

# Register all agents
nexus.register("qa", qa_agent.to_workflow().build())
nexus.register("reasoning", cot_agent.to_workflow().build())
nexus.register("vision", vision_agent.to_workflow().build())

# All agents accessible via:
# - API: POST /workflows/{agent_name}
# - CLI: nexus run {agent_name}
# - MCP: {agent_name} tools
```

### Pattern: Agent + DataFlow + Nexus

```python
from nexus import Nexus
from dataflow import DataFlow
from kaizen.agents import SimpleQAAgent
from kailash.workflow.builder import WorkflowBuilder

# DataFlow for persistence
db = DataFlow()

@db.model
class Conversation:
    question: str
    answer: str
    user_id: str

# Kaizen agent
agent = SimpleQAAgent(QAConfig())

# Combined workflow: Agent + Database
def create_qa_with_persistence_workflow(question: str, user_id: str):
    # Get AI answer
    result = agent.ask(question)

    # Create workflow that stores result
    workflow = WorkflowBuilder()
    workflow.add_node("ConversationCreateNode", "store", {
        "question": question,
        "answer": result["answer"],
        "user_id": user_id
    })
    return workflow.build()

# Deploy via Nexus
nexus = Nexus(title="Persistent Q&A Platform")
# (Note: Nexus workflow registration with dynamic parameters requires custom integration)
```

## 🤖 MCP Integration

### Pattern 1: Expose Agent as MCP Tool

```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

# Create agent
agent = SimpleQAAgent(QAConfig())

# Convert to MCP tool (via Nexus)
from nexus import Nexus

nexus = Nexus(
    title="AI Platform",
    enable_mcp=True  # Enable MCP server
)

# Register agent - automatically exposed as MCP tool
nexus.register("qa_agent", agent.to_workflow().build())

# Now available to AI assistants (Claude, etc.) as:
# Tool: qa_agent(question: str) -> answer
```

### Pattern 2: Agent Consuming MCP Tools

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField

# Custom agent that uses MCP tools
class MCPIntegratedAgent(BaseAgent):
    def __init__(self, config, mcp_tools):
        super().__init__(config=config, signature=MySignature())
        self.mcp_tools = mcp_tools  # MCP tools available to agent

    def process(self, task: str):
        # Agent can use MCP tools for enhanced capabilities
        # Example: Use MCP search tool, file tools, etc.
        result = self.run(task=task)
        return result

# See examples/5-mcp-integration/ for complete examples
```

## 🔄 Core SDK Integration

### Basic Pattern: Agent as Workflow Node

```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create agent
agent = SimpleQAAgent(QAConfig())

# Method 1: Use agent directly
result = agent.ask("What is AI?")

# Method 2: Convert to workflow for Core SDK integration
agent_workflow = agent.to_workflow()

# Method 3: Integrate into larger workflow
main_workflow = WorkflowBuilder()
# Add data processing nodes
main_workflow.add_node("DataProcessorNode", "process", {...})
# Add agent as node (requires workflow composition)
# (Advanced: See Core SDK documentation for workflow composition)

runtime = LocalRuntime()
results, run_id = runtime.execute(main_workflow.build())
```

### Advanced: Multi-Step Agent Workflow

```python
from kaizen.agents import SimpleQAAgent, VisionAgent
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Step 1: Vision analysis
vision_agent = VisionAgent(VisionAgentConfig())
image_result = vision_agent.analyze(
    image="/path/to/image.png",
    question="What is in this image?"
)

# Step 2: Text analysis based on vision result
qa_agent = SimpleQAAgent(QAConfig())
text_result = qa_agent.ask(
    f"Given this image contains: {image_result['answer']}, what category does it belong to?"
)

# Combine results
workflow = WorkflowBuilder()
workflow.add_node("ResultAggregatorNode", "combine", {
    "vision_result": image_result['answer'],
    "category": text_result['answer']
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## 🎯 Best Practices

### 1. Separation of Concerns

```python
# ✅ GOOD: Separate AI logic from data persistence
# AI processing
agent = SimpleQAAgent(QAConfig())
result = agent.ask(question)

# Data persistence (separate step)
workflow = WorkflowBuilder()
workflow.add_node("StoreNode", "store", {"data": result})

# ❌ BAD: Mixing AI and database logic tightly
```

### 2. Error Handling

```python
# ✅ GOOD: Handle errors at each step
try:
    # AI processing
    result = agent.ask(question)
except Exception as e:
    print(f"Agent error: {e}")
    result = {"answer": "Error occurred", "confidence": 0.0}

try:
    # Database storage
    workflow = WorkflowBuilder()
    workflow.add_node("StoreNode", "store", {"data": result})
    runtime.execute(workflow.build())
except Exception as e:
    print(f"Storage error: {e}")
```

### 3. Configuration Management

```python
# ✅ GOOD: Centralized configuration
from dataclasses import dataclass

@dataclass
class AppConfig:
    # AI config
    llm_provider: str = "openai"
    model: str = "gpt-4"

    # Database config
    database_url: str = "postgresql://..."

    # Nexus config
    enable_api: bool = True
    enable_cli: bool = True

config = AppConfig()

# Use config across integrations
agent = SimpleQAAgent(QAConfig(llm_provider=config.llm_provider))
db = DataFlow(database_url=config.database_url)
nexus = Nexus(enable_api=config.enable_api, enable_cli=config.enable_cli)
```

### 4. Testing Integration

```python
import pytest

def test_agent_dataflow_integration():
    """Test agent result storage in database."""
    # Create agent with mock provider
    agent = SimpleQAAgent(QAConfig(llm_provider="mock"))
    result = agent.ask("Test question")

    # Verify result structure
    assert "answer" in result

    # Test database storage
    workflow = WorkflowBuilder()
    workflow.add_node("TestCreateNode", "store", {
        "question": "Test",
        "answer": result["answer"]
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    assert results["store"]["success"]
```

## 📚 Examples

### Complete Integration Examples

See working examples in the repository:

**DataFlow Integration:**
- `examples/6-dataflow-integration/` - Complete DataFlow patterns

**Nexus Integration:**
- `examples/7-nexus-integration/` - Multi-channel deployment

**MCP Integration:**
- `examples/5-mcp-integration/` - MCP tool patterns

## 🔗 Related Documentation

- **[README](../../README.md)** - Complete Kaizen guide
- **[Quickstart](../getting-started/quickstart.md)** - Getting started
- **[Multi-Modal API](../reference/multi-modal-api-reference.md)** - Vision/audio
- **[Troubleshooting](../reference/troubleshooting.md)** - Common issues

### External Documentation
- **[DataFlow Guide](../../../dataflow/README.md)** - Database framework
- **[Nexus Guide](../../../nexus/README.md)** - Multi-channel platform
- **[Core SDK](../../../../CLAUDE.md)** - Foundation patterns

---

**Need help?** Check **[Examples](../../../../apps/kailash-kaizen/examples/)** for working code.
