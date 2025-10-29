# Kaizen Quickstart Guide

Get started with Kaizen in 5 minutes - from installation to your first working agent.

## 📦 Installation

```bash
# Install Kaizen (v0.2.0)
pip install kailash-kaizen

# Or install with Kailash SDK
pip install kailash[kaizen]

# Specific version
pip install kailash-kaizen==0.2.0
```

## 🔑 API Key Setup

Create a `.env` file in your project root:

```bash
# .env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

## 🚀 Your First Agent (3 Steps)

### Step 1: Import and Load Environment

```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig
from dotenv import load_dotenv

# Load API keys from .env
load_dotenv()
```

### Step 2: Create Agent

```python
# Create configuration
config = QAConfig(
    llm_provider="openai",
    model="gpt-4"
)

# Create agent
agent = SimpleQAAgent(config)
```

### Step 3: Execute

```python
# Ask a question
result = agent.ask("What is quantum computing?")

# Print results
print(result["answer"])
print(f"Confidence: {result['confidence']}")
```

**Complete Example:**
```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Create agent
config = QAConfig(llm_provider="openai", model="gpt-4")
agent = SimpleQAAgent(config)

# Execute
result = agent.ask("What is quantum computing?")
print(result["answer"])
```

## 🎯 Common Agent Patterns

### Question Answering

```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

config = QAConfig(llm_provider="openai", model="gpt-4")
agent = SimpleQAAgent(config)
result = agent.ask("What is the capital of France?")
```

### Memory-Enabled Agent

```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

# Enable memory with max_turns parameter
config = QAConfig(
    llm_provider="openai",
    model="gpt-4",
    max_turns=10  # Enable BufferMemory
)
agent = SimpleQAAgent(config)

# Use session_id for continuity
result1 = agent.ask("My name is Alice", session_id="user123")
result2 = agent.ask("What's my name?", session_id="user123")
print(result2["answer"])  # "Your name is Alice"
```

### Vision Processing

```python
from kaizen.agents import VisionAgent, VisionAgentConfig

# Ollama (free, local)
config = VisionAgentConfig(llm_provider="ollama", model="bakllava")
agent = VisionAgent(config=config)

result = agent.analyze(
    image="/path/to/image.png",
    question="What is in this image?"
)
print(result['answer'])
```

### Chain-of-Thought Reasoning

```python
from kaizen.agents import ChainOfThoughtAgent
from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtConfig

config = ChainOfThoughtConfig(llm_provider="openai", model="gpt-4")
agent = ChainOfThoughtAgent(config)

result = agent.think("If John has 3 apples and Mary gives him 5 more, how many does he have?")
print(result["reasoning_steps"])
print(result["final_answer"])
```

### Tool Calling (NEW in v0.2.0)

```python
from kaizen.core.base_agent import BaseAgent
# Tools auto-configured via MCP


# Enable tool calling

# 12 builtin tools enabled via MCP

agent = BaseAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
)

# Execute a tool
result = await agent.execute_tool("read_file", {"path": "/tmp/data.txt"})
if result.success:
    print(result.result['content'])

# Chain multiple tools
results = await agent.execute_tool_chain([
    {"tool_name": "read_file", "params": {"path": "input.txt"}},
    {"tool_name": "write_file", "params": {"path": "output.txt", "content": "processed"}}
])
```

**12 Builtin Tools Available:**
- **File**: read_file, write_file, delete_file, list_directory, file_exists
- **HTTP**: http_get, http_post, http_put, http_delete
- **Bash**: bash_command
- **Web**: fetch_url, extract_links

## 🔧 Configuration Options

### Basic Configuration

```python
from dataclasses import dataclass

@dataclass
class QAConfig:
    llm_provider: str = "openai"     # "openai", "anthropic", "ollama"
    model: str = "gpt-4"             # Model name
    temperature: float = 0.7         # Creativity (0.0-1.0)
    max_tokens: int = 500            # Maximum response length
    timeout: int = 30                # Request timeout (seconds)
```

### Progressive Configuration

```python
# Start with defaults
config = QAConfig()

# Override specific fields
config = QAConfig(
    model="gpt-3.5-turbo",  # Use cheaper model
    temperature=0.2         # Lower creativity
)

# Full customization
config = QAConfig(
    llm_provider="anthropic",
    model="claude-3-opus",
    temperature=0.1,
    max_tokens=1000,
    timeout=60,
    max_turns=20  # Enable memory
)
```

## 📚 Available Agents

```python
from kaizen.agents import (
    # Single-Agent Patterns
    SimpleQAAgent,           # Question answering
    ChainOfThoughtAgent,     # Step-by-step reasoning
    ReActAgent,              # Reasoning + action cycles
    RAGResearchAgent,        # Research with retrieval
    CodeGenerationAgent,     # Code generation
    MemoryAgent,             # Memory-enhanced conversations

    # Multi-Modal Agents
    VisionAgent,             # Image analysis
    TranscriptionAgent,      # Audio transcription
)
```

## ⚠️ Common Issues

### Issue 1: Missing API Key

**Error:**
```
AuthenticationError: No API key provided
```

**Solution:**
```bash
# Create .env file
echo "OPENAI_API_KEY=sk-..." > .env
```

```python
from dotenv import load_dotenv
load_dotenv()  # Load before creating agent
```

### Issue 2: Ollama Not Running

**Error:**
```
ConnectionError: Could not connect to Ollama
```

**Solution:**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama
ollama serve

# Pull model
ollama pull bakllava
```

### Issue 3: Wrong Import Path

**Error:**
```
ImportError: cannot import name 'SimpleQAAgent'
```

**Solution:**
```python
# ✅ CORRECT
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

# ❌ WRONG
from kaizen import SimpleQAAgent  # This doesn't work
```

## 🎓 Next Steps

### Learn More

1. **[Complete API Reference](../reference/api-reference.md)** - All available methods
2. **[Multi-Modal Guide](../reference/multi-modal-api-reference.md)** - Vision and audio processing
3. **[Integration Patterns](../guides/integration-patterns.md)** - DataFlow, Nexus, MCP
4. **[Troubleshooting](../reference/troubleshooting.md)** - Common errors and solutions

### Try Examples

Explore 35+ working examples:
```bash
# Clone repository
git clone https://github.com/terrene-foundation/kailash-py

# Navigate to examples
cd kailash_python_sdk/apps/kailash-kaizen/examples

# Try simple Q&A
python 1-single-agent/simple-qa/workflow.py
```

### Create Custom Agent

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

# 1. Define configuration
@dataclass
class SentimentConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.2

# 2. Define signature
class SentimentSignature(Signature):
    text: str = InputField(desc="Text to analyze")
    sentiment: str = OutputField(desc="Sentiment category")
    confidence: float = OutputField(desc="Confidence 0.0-1.0")

# 3. Extend BaseAgent
class SentimentAgent(BaseAgent):
    def __init__(self, config: SentimentConfig):
        super().__init__(config=config, signature=SentimentSignature())

    def analyze(self, text: str):
        return self.run(text=text)

# Usage
config = SentimentConfig()
agent = SentimentAgent(config)
result = agent.analyze("This product is amazing!")
print(result["sentiment"])  # "positive"
```

## 💡 Quick Tips

1. **Always load .env first**: Use `load_dotenv()` before creating agents
2. **Start simple**: Use SimpleQAAgent to understand the pattern
3. **Enable memory**: Set `max_turns` parameter to enable BufferMemory
4. **Use Ollama for testing**: Free local inference for development
5. **Check examples**: 35+ working examples in the repository

## 🔗 Related Documentation

- **[README.md](../../README.md)** - Complete Kaizen guide
- **[Multi-Modal API](../reference/multi-modal-api-reference.md)** - Vision and audio
- **[Troubleshooting](../reference/troubleshooting.md)** - Error solutions
- **[Examples](../../../../apps/kailash-kaizen/examples/)** - Working code

---

**Ready to build?** Check out the **[Complete Examples](../../../../apps/kailash-kaizen/examples/)** or read the **[Full Documentation](../../README.md)**.
