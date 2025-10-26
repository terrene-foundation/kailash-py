# Kaizen Troubleshooting Guide

Common errors and solutions when using Kaizen.

## 🔑 API Key Issues

### Error: No API Key Provided

**Error Message:**
```
AuthenticationError: No API key provided
openai.AuthenticationError: No API key provided
```

**Cause:** Missing or not loaded API key from environment.

**Solution:**

1. Create `.env` file in project root:
```bash
# .env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

2. Load environment before creating agent:
```python
from dotenv import load_dotenv
load_dotenv()  # MUST be called before creating agent

from kaizen.agents import SimpleQAAgent
config = QAConfig(llm_provider="openai", model="gpt-4")
agent = SimpleQAAgent(config)
```

### Error: Invalid API Key

**Error Message:**
```
AuthenticationError: Invalid API key
```

**Cause:** API key is incorrect or expired.

**Solution:**

1. Verify API key in `.env` file
2. Check key is not corrupted (no extra spaces/newlines)
3. Generate new API key if needed:
   - OpenAI: https://platform.openai.com/api-keys
   - Anthropic: https://console.anthropic.com/

## 🛠️ Tool Calling Issues (v0.2.0)

### Error: Agent does not have tool calling support enabled

**Error Message:**
```
ValueError: Agent does not have tool calling support enabled
```

**Cause:** Forgot to pass `tool_registry` during initialization.

**Solution:**
```python
# ❌ WRONG - No tool registry
agent = BaseAgent(config=config, signature=signature)

# ✅ CORRECT - Add tool registry
# Tools auto-configured via MCP



# 12 builtin tools enabled via MCP

agent = BaseAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
)
```

### Error: Tool execution timed out waiting for approval

**Error Message:**
```
TimeoutError: Tool execution timed out waiting for approval
```

**Cause:** No approval responder is running, or control protocol not started.

**Solution:**
```python
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import MemoryTransport

# Create and start protocol
transport = MemoryTransport()
await transport.connect()
protocol = ControlProtocol(transport)

# Create agent with protocol
agent = BaseAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
    control_protocol=protocol  # Add protocol
)

# Start protocol with task group
import anyio
async with anyio.create_task_group() as tg:
    await protocol.start(tg)
    # Now tool executions can request approval
    result = await agent.execute_tool("write_file", {...})
```

### Error: Required parameter missing

**Error Message:**
```
ValueError: Required parameter 'path' missing
```

**Cause:** Missing required parameters in tool call.

**Solution:**
```python
# ❌ WRONG - Missing required parameter
result = await agent.execute_tool("read_file", {})

# ✅ CORRECT - Provide all required parameters
result = await agent.execute_tool(
    "read_file",
    {"path": "/tmp/file.txt"}  # path is required
)

# Check tool definition for required parameters
tools = await agent.discover_tools(keyword="read_file")
tool = tools[0]
for param in tool.parameters:
    if param.required:
        print(f"Required: {param.name} ({param.type})")
```

### Error: Tool not found

**Error Message:**
```
ValueError: Tool 'invalid_tool' not found in registry
```

**Cause:** Tool name is incorrect or not registered.

**Solution:**
```python
# List available tools
tools = await agent.discover_tools()
for tool in tools:
    print(f"Tool: {tool.name}")

# Use correct tool name
result = await agent.execute_tool("read_file", {"path": "..."})  # Correct
# NOT: "readfile", "ReadFile", "read-file", etc.
```

## 🖼️ Multi-Modal Issues

### Error: Wrong Vision API Parameters

**Error Message:**
```
TypeError: analyze() got an unexpected keyword argument 'prompt'
```

**Cause:** Using incorrect parameter name.

**Solution:**

```python
# ❌ WRONG
result = agent.analyze(image=img, prompt="What is this?")
answer = result['response']

# ✅ CORRECT
result = agent.analyze(image="/path/to/image.png", question="What is this?")
answer = result['answer']
```

**Remember:**
- Use `question` parameter (NOT `prompt`)
- Use `answer` key (NOT `response`)
- Use file path (NOT base64 string)

### Error: Ollama Connection Failed

**Error Message:**
```
ConnectionError: Could not connect to Ollama at http://localhost:11434
```

**Cause:** Ollama is not installed or not running.

**Solution:**

1. Install Ollama:
```bash
# macOS/Linux
curl -fsSL https://ollama.com/install.sh | sh

# Or download from https://ollama.com
```

2. Start Ollama service:
```bash
ollama serve
```

3. Pull vision model:
```bash
ollama pull bakllava
```

4. Verify Ollama is running:
```bash
curl http://localhost:11434
# Should return: "Ollama is running"
```

### Error: Vision Model Not Found

**Error Message:**
```
ModelNotFoundError: Model 'bakllava' not found
```

**Cause:** Vision model not downloaded.

**Solution:**

```bash
# Pull the vision model
ollama pull bakllava

# Or use llava
ollama pull llava

# Verify models
ollama list
```

### Error: Image File Not Found

**Error Message:**
```
FileNotFoundError: [Errno 2] No such file or directory: '/path/to/image.png'
```

**Cause:** Image path is incorrect or file doesn't exist.

**Solution:**

```python
import os

# Verify file exists
image_path = "/path/to/image.png"
if not os.path.exists(image_path):
    print(f"File not found: {image_path}")

# Use absolute paths
image_path = os.path.abspath("images/photo.jpg")
result = agent.analyze(image=image_path, question="...")
```

## 🎵 Audio Issues

### Error: Audio Format Not Supported

**Error Message:**
```
ValueError: Unsupported audio format: .avi
```

**Cause:** Audio file format is not supported.

**Solution:**

Convert to supported format (MP3, WAV, M4A, FLAC, OGG):

```bash
# Using ffmpeg
ffmpeg -i input.avi -acodec mp3 output.mp3

# Or use online converter
```

```python
result = agent.transcribe(audio_path="/path/to/audio.mp3")
```

## 📦 Import Issues

### Error: Cannot Import Agent

**Error Message:**
```
ImportError: cannot import name 'SimpleQAAgent' from 'kaizen'
```

**Cause:** Incorrect import path.

**Solution:**

```python
# ✅ CORRECT
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

# ❌ WRONG
from kaizen import SimpleQAAgent  # Doesn't work
from kaizen.agents.simple_qa import SimpleQAAgent  # Wrong path
```

### Error: Module Not Found

**Error Message:**
```
ModuleNotFoundError: No module named 'kaizen'
```

**Cause:** Kaizen is not installed.

**Solution:**

```bash
# Install Kaizen
pip install kailash-kaizen

# Or install with Kailash SDK
pip install kailash[kaizen]

# Verify installation
python -c "import kaizen; print(kaizen.__version__)"
```

## ⚙️ Configuration Issues

### Error: Invalid Configuration

**Error Message:**
```
TypeError: __init__() got an unexpected keyword argument 'invalid_param'
```

**Cause:** Using incorrect configuration parameter.

**Solution:**

Check valid configuration fields:

```python
from dataclasses import dataclass

@dataclass
class QAConfig:
    llm_provider: str = "openai"   # Valid
    model: str = "gpt-4"           # Valid
    temperature: float = 0.7       # Valid
    max_tokens: int = 500          # Valid
    timeout: int = 30              # Valid
    max_turns: int = None          # Valid (memory)
    # invalid_param: str = "..."  # Invalid!

# ✅ CORRECT
config = QAConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7
)

# ❌ WRONG
config = QAConfig(invalid_param="value")  # Error!
```

### Error: Using BaseAgentConfig Directly

**Error Message:**
```
TypeError: Domain config cannot be converted to BaseAgentConfig
```

**Cause:** Using `BaseAgentConfig` instead of domain config.

**Solution:**

```python
# ❌ WRONG
from kaizen.core.config import BaseAgentConfig
config = BaseAgentConfig(model="gpt-4")  # Don't do this!

# ✅ CORRECT
from kaizen.agents.specialized.simple_qa import QAConfig
config = QAConfig(model="gpt-4")
agent = SimpleQAAgent(config)  # Auto-converts to BaseAgentConfig
```

## 🧠 Memory Issues

### Error: Session ID Not Working

**Issue:** Memory not persisting across calls.

**Cause:** Memory not enabled or missing session_id.

**Solution:**

```python
# Enable memory with max_turns
config = QAConfig(
    llm_provider="openai",
    model="gpt-4",
    max_turns=10  # MUST set max_turns to enable memory
)
agent = SimpleQAAgent(config)

# Use same session_id for continuity
result1 = agent.ask("My name is Alice", session_id="user123")
result2 = agent.ask("What's my name?", session_id="user123")  # MUST use same ID
```

## 🌐 Network Issues

### Error: Connection Timeout

**Error Message:**
```
requests.exceptions.Timeout: Request timed out
```

**Cause:** Network slow or timeout too short.

**Solution:**

```python
# Increase timeout
config = QAConfig(
    llm_provider="openai",
    model="gpt-4",
    timeout=60  # Increase to 60 seconds
)
agent = SimpleQAAgent(config)
```

### Error: Rate Limit Exceeded

**Error Message:**
```
RateLimitError: Rate limit reached for model gpt-4
```

**Cause:** Too many requests to API.

**Solution:**

1. Add delays between requests:
```python
import time

for question in questions:
    result = agent.ask(question)
    time.sleep(1)  # Wait 1 second between requests
```

2. Use cheaper/faster model:
```python
config = QAConfig(
    model="gpt-3.5-turbo"  # Faster, cheaper, higher rate limit
)
```

3. Upgrade API tier (OpenAI/Anthropic)

## 🔧 Integration Issues

### Error: DataFlow Integration

**Issue:** Agent results not storing in database.

**Solution:**

```python
from dataflow import DataFlow
from kaizen.agents import SimpleQAAgent, QAConfig
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create DataFlow model
db = DataFlow()

@db.model
class QASession:
    question: str
    answer: str
    confidence: float

# Get agent result
agent = SimpleQAAgent(QAConfig())
result = agent.ask("What is AI?")

# Store in database via workflow
workflow = WorkflowBuilder()
workflow.add_node("QASessionCreateNode", "store", {
    "question": "What is AI?",
    "answer": result["answer"],
    "confidence": result.get("confidence", 0.0)
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Error: Nexus Deployment

**Issue:** Agent not accessible via Nexus channels.

**Solution:**

```python
from nexus import Nexus
from kaizen.agents import SimpleQAAgent, QAConfig

# Create agent
agent = SimpleQAAgent(QAConfig())

# Convert to workflow before registering
agent_workflow = agent.to_workflow()

# Create Nexus and register
nexus = Nexus(
    title="AI Platform",
    enable_api=True,
    enable_cli=True,
    enable_mcp=True
)

# Register built workflow
nexus.register("qa_agent", agent_workflow.build())

# Now available on all channels
```

## 📊 Performance Issues

### Issue: Slow Execution

**Symptoms:** Agent takes too long to respond.

**Solutions:**

1. Use faster model:
```python
config = QAConfig(
    model="gpt-3.5-turbo"  # Much faster than gpt-4
)
```

2. Reduce max_tokens:
```python
config = QAConfig(
    max_tokens=300  # Shorter responses = faster
)
```

3. Use local Ollama for development:
```python
config = QAConfig(
    llm_provider="ollama",
    model="llama2"
)
```

### Issue: High Memory Usage

**Symptoms:** Python process using too much memory.

**Solutions:**

1. Limit memory buffer:
```python
config = QAConfig(
    max_turns=10  # Limit conversation history
)
```

2. Clear memory periodically:
```python
# If using custom BaseAgent extension
agent.memory.clear()  # Clear memory buffer
```

## 🧪 Testing Issues

### Error: Tests Failing

**Issue:** Unit tests not working.

**Solution:**

Use mock provider for unit tests:

```python
import pytest
from kaizen.agents import SimpleQAAgent, QAConfig

def test_simple_qa():
    # Use mock provider for fast unit tests
    config = QAConfig(llm_provider="mock")
    agent = SimpleQAAgent(config)

    result = agent.ask("Test question")

    assert "answer" in result
    assert isinstance(result["answer"], str)
```

## 🆘 Getting Help

### Debug Mode

Enable detailed logging:

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Now run your agent
agent = SimpleQAAgent(config)
result = agent.ask("Test")
# Will show detailed execution logs
```

### Check Documentation

1. **[Multi-Modal API Reference](multi-modal-api-reference.md)** - Vision/audio specifics
2. **[Quickstart Guide](../getting-started/quickstart.md)** - Basic setup
3. **[README](../../README.md)** - Complete guide
4. **[Examples](../../../../apps/kailash-kaizen/examples/)** - Working code

### Report Issues

If problem persists:

1. Check **[GitHub Issues](https://github.com/terrene-foundation/kailash-py/issues)**
2. Create new issue with:
   - Error message
   - Code to reproduce
   - Python version
   - Kaizen version
   - Environment details

---

**Still stuck?** Check **[Examples](../../../../apps/kailash-kaizen/examples/)** for working code or review **[API Reference](api-reference.md)**.
