# Kaizen Examples & Tutorials

Welcome to Kaizen! This directory provides **two learning paths** depending on your goals:

## 🎯 Choose Your Path

### Path 1: Using Specialized Agents (Quick Start - 5 minutes)

**Goal**: Use pre-built, production-ready agents immediately

**Who**: Developers who want to use AI agents without building from scratch

**Start Here**: [`quickstart/01-using-simple-qa-agent.py`](quickstart/01-using-simple-qa-agent.py)

```python
from kaizen.agents import SimpleQAAgent

agent = SimpleQAAgent()  # Zero-config!
result = agent.ask("What is AI?")
print(result["answer"])
```

**What You'll Learn**:
- How to import and use specialized agents
- Zero-config vs progressive configuration
- Memory and session management
- All available specialized agents

**Examples**:
- `quickstart/` - 2-minute quick starts for each agent
- `guides/using-specialized-agents/` - Detailed usage guides

---

### Path 2: Creating Custom Agents (Learning - 30 minutes)

**Goal**: Build your own specialized agents from BaseAgent

**Who**: Developers who want to create custom AI agents for specific domains

**Start Here**: [`guides/creating-custom-agents/01-basic-custom-agent.py`](guides/creating-custom-agents/01-basic-custom-agent.py)

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField

class MyCustomAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(
            config=MyConfig(**kwargs),
            signature=MySignature()
        )

    def my_method(self, input_data):
        return self.run(**input_data)
```

**What You'll Learn**:
- How to extend BaseAgent
- How to define Signatures (inputs/outputs)
- How to create Configurations
- How to add domain-specific methods
- How to leverage BaseAgent features (async, logging, memory)

**Examples**:
- `guides/creating-custom-agents/` - Step-by-step agent creation
- `tutorials/` - Complete agent implementation tutorials

---

## 📁 Directory Structure

```
examples/
├── README.md (this file)
│
├── quickstart/                    # 5-minute quick starts
│   ├── 01-using-simple-qa-agent.py
│   ├── 02-using-react-agent.py
│   ├── 03-using-rag-agent.py
│   └── ...
│
├── guides/
│   ├── using-specialized-agents/  # PATH 1: Using pre-built agents
│   │   ├── README.md
│   │   ├── 01-basic-usage.py
│   │   ├── 02-configuration.py
│   │   ├── 03-memory-sessions.py
│   │   └── 04-all-agents-overview.py
│   │
│   └── creating-custom-agents/    # PATH 2: Creating custom agents
│       ├── README.md
│       ├── 01-basic-custom-agent.py
│       ├── 02-advanced-signatures.py
│       ├── 03-custom-strategies.py
│       ├── 04-custom-memory.py
│       └── 05-production-agent.py
│
├── tutorials/                      # Complete implementations
│   ├── building-qa-system/
│   ├── multi-agent-debate/
│   ├── production-rag-system/
│   └── custom-domain-agent/
│
└── recipes/                        # Full application examples
    ├── customer-service-bot/
    ├── code-review-assistant/
    └── research-assistant/
```

---

## 🚀 Quick Start Guide

### For Users (Path 1)

**Install Kaizen**:
```bash
pip install kailash-kaizen
```

**Use an Agent (3 lines)**:
```python
from kaizen.agents import SimpleQAAgent

agent = SimpleQAAgent()
result = agent.ask("What is machine learning?")
print(result["answer"])
```

**Next Steps**:
1. Try [`quickstart/01-using-simple-qa-agent.py`](quickstart/01-using-simple-qa-agent.py)
2. Explore other agents: `ReActAgent`, `RAGAgent`, `ChainOfThoughtAgent`
3. Learn configuration in [`guides/using-specialized-agents/`](guides/using-specialized-agents/)

---

### For Builders (Path 2)

**Create Custom Agent (Basic Pattern)**:
```python
# 1. Define signature
class MySignature(Signature):
    input_field: str = InputField(desc="Input description")
    output_field: str = OutputField(desc="Output description")

# 2. Define configuration
@dataclass
class MyConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    # ... more config

# 3. Extend BaseAgent
class MyAgent(BaseAgent):
    def __init__(self, **kwargs):
        config = MyConfig(**kwargs)
        super().__init__(config=config, signature=MySignature())

    def my_method(self, data):
        return self.run(**data)
```

**Next Steps**:
1. Follow [`guides/creating-custom-agents/01-basic-custom-agent.py`](guides/creating-custom-agents/01-basic-custom-agent.py)
2. Learn advanced patterns in subsequent guides
3. Build a complete agent in [`tutorials/custom-domain-agent/`](tutorials/custom-domain-agent/)

---

## 📚 Available Specialized Agents

Kaizen provides 24+ production-ready agents across 5 categories:

### Specialized Agents
- `SimpleQAAgent` - Question answering
- `ChainOfThoughtAgent` - Step-by-step reasoning
- `ReActAgent` - Reasoning + action cycles
- `RAGResearchAgent` - Research with retrieval
- `CodeGenerationAgent` - Code generation
- `MemoryAgent` - Memory-enhanced conversations

### Enterprise Workflow Agents
- `ComplianceMonitoringAgent` - Regulatory compliance
- `DocumentAnalysisAgent` - Document processing
- `CustomerServiceAgent` - Customer support
- `DataReportingAgent` - Automated reporting

### Multi-Agent Coordination
- `SupervisorAgent` - Task delegation
- `ConsensusAgent` - Group decision-making
- `DebateAgent` - Adversarial reasoning
- `DomainSpecialistAgent` - Expert routing

### Advanced RAG Agents
- `AgenticRAGAgent` - Agent-driven retrieval
- `GraphRAGAgent` - Knowledge graph retrieval
- `SelfCorrectingRAGAgent` - Error-correcting RAG
- `MultiHopRAGAgent` - Multi-step retrieval
- `FederatedRAGAgent` - Multi-source retrieval

### MCP Integration Agents
- `AutoDiscoveryAgent` - Tool discovery
- `AgentAsClientAgent` - MCP tool consumption
- `AgentAsServerAgent` - Expose agents as MCP
- `HybridCoordinationAgent` - Internal/external coordination
- `MultiServerOrchestrator` - Dynamic orchestration

**See full list**: `from kaizen.agents import *`

---

## 🎓 Learning Path Recommendations

### Beginner (Never used AI agents)
1. **Start**: Quickstart examples (Path 1)
2. **Practice**: Try different specialized agents
3. **Learn**: Configuration and memory
4. **Build**: Simple custom agent (Path 2)

### Intermediate (Used LangChain, CrewAI, etc.)
1. **Compare**: See how Kaizen differs (cleaner imports, zero-config)
2. **Migrate**: Use specialized agents instead of custom code
3. **Extend**: Create custom agents for your domain (Path 2)
4. **Scale**: Multi-agent coordination patterns

### Advanced (Building production AI systems)
1. **Architecture**: Study BaseAgent architecture
2. **Customize**: Build domain-specific agents (Path 2)
3. **Optimize**: Custom strategies, memory systems
4. **Deploy**: Enterprise workflows, MCP integration

---

## 💡 Key Concepts

### Zero-Config Design
All specialized agents work with **zero configuration**:
```python
agent = SimpleQAAgent()  # Uses sensible defaults
```

### Progressive Configuration
Override only what you need:
```python
agent = SimpleQAAgent(
    model="gpt-3.5-turbo",  # Override model
    temperature=0.7         # Override temperature
    # Everything else uses defaults
)
```

### Environment Variable Support
Configure via environment variables:
```bash
export KAIZEN_LLM_PROVIDER=openai
export KAIZEN_MODEL=gpt-4
export KAIZEN_TEMPERATURE=0.7
```

```python
agent = SimpleQAAgent()  # Reads from environment
```

### Dual Learning Paths
- **Path 1 (Using)**: Import and use pre-built agents
- **Path 2 (Creating)**: Build custom agents from BaseAgent

Both paths are equally valid - choose based on your needs!

---

## ❓ FAQ

**Q: Should I use Path 1 or Path 2?**
A: Start with Path 1 (using specialized agents). Move to Path 2 when you need domain-specific customization.

**Q: Can I use both paths?**
A: Absolutely! Use specialized agents for common tasks, create custom agents for unique domains.

**Q: What's the difference between examples/ and src/kaizen/agents/?**
A: `src/kaizen/agents/` = production library code (import this). `examples/` = tutorials and learning materials.

**Q: Do I need to copy code from examples/?**
A: No! Examples show how to USE the importable agents. Just `from kaizen.agents import X`.

**Q: How do I create my own specialized agent?**
A: Follow Path 2: [`guides/creating-custom-agents/`](guides/creating-custom-agents/)

---

**Ready to start?** Choose your path above and dive in! 🚀
