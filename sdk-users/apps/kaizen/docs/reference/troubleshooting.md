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

**Cause:** Forgot to enable tools during initialization.

**Solution:**
```python
# ❌ WRONG - Tools not enabled
agent = BaseAgent(config=config, signature=signature)

# ✅ CORRECT - Enable tools via MCP
agent = BaseAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
)

# OR with custom MCP servers:
mcp_servers = [{
    "name": "kaizen_builtin",
    "command": "python",
    "args": ["-m", "kaizen.mcp.builtin_server"],
    "transport": "stdio"
}]
agent = BaseAgent(
    config=config,
    signature=signature,
    custom_mcp_servers=mcp_servers
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
    tools="all",  # Enable tools via MCP
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

## 🔄 Autonomy System Issues

### Hooks System

#### Error: Hook Registration Failed

**Error Message:**
```
ValueError: Hook must implement handle() method
```

**Cause:** Hook handler does not implement required interface.

**Solution:**

```python
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult

# ❌ WRONG - Missing handle() method
class MyHook(BaseHook):
    def __init__(self):
        super().__init__(name="my_hook")
        self.events = [HookEvent.POST_AGENT_LOOP]

# ✅ CORRECT - Implement handle() method
class MyHook(BaseHook):
    def __init__(self):
        super().__init__(name="my_hook")
        self.events = [HookEvent.POST_AGENT_LOOP]

    async def handle(self, context: HookContext) -> HookResult:
        """Required handle method."""
        print(f"Agent {context.agent_id} executed")
        return HookResult(success=True)

# Register hook
hook_manager = HookManager()
hook_manager.register_hook(MyHook(), priority=HookPriority.NORMAL)
```

#### Error: Hook Execution Timeout

**Error Message:**
```
TimeoutError: Hook execution timed out after 5 seconds
```

**Cause:** Hook is taking too long to execute.

**Solution:**

```python
# Option 1: Increase hook timeout
hook_manager = HookManager(default_timeout=10.0)  # 10 seconds

# Option 2: Optimize hook logic
class OptimizedHook(BaseHook):
    async def handle(self, context: HookContext) -> HookResult:
        # ❌ WRONG - Slow synchronous operation
        # result = slow_api_call()

        # ✅ CORRECT - Fast async operation
        result = await asyncio.wait_for(
            async_api_call(),
            timeout=2.0
        )
        return HookResult(success=True)

# Option 3: Use LOWEST priority for expensive hooks
hook_manager.register_hook(
    expensive_hook,
    priority=HookPriority.LOWEST  # Execute last
)
```

#### Error: Hook Order Incorrect

**Issue:** Hooks executing in wrong order.

**Cause:** Hook priorities not set correctly.

**Solution:**

```python
from kaizen.core.autonomy.hooks import HookPriority

# Set explicit priorities
hook_manager.register(
    HookEvent.PRE_AGENT_LOOP,
    auth_hook,
    priority=HookPriority.CRITICAL  # Execute first
)

hook_manager.register(
    HookEvent.PRE_AGENT_LOOP,
    rate_limit_hook,
    priority=HookPriority.HIGH  # Execute second
)

hook_manager.register(
    HookEvent.PRE_AGENT_LOOP,
    logging_hook,
    priority=HookPriority.NORMAL  # Execute third (default)
)
```

### Checkpoint System

#### Error: Checkpoint Save Failed

**Error Message:**
```
IOError: Permission denied: ./checkpoints/
```

**Cause:** Insufficient filesystem permissions.

**Solution:**

```python
import os

# Ensure checkpoint directory exists with correct permissions
checkpoint_dir = "./checkpoints"
os.makedirs(checkpoint_dir, exist_ok=True)

# Verify writable
if not os.access(checkpoint_dir, os.W_OK):
    print(f"Directory not writable: {checkpoint_dir}")
    checkpoint_dir = "/tmp/checkpoints"  # Use temp directory
    os.makedirs(checkpoint_dir, exist_ok=True)

# Create state manager with writable directory
storage = FilesystemStorage(base_dir=checkpoint_dir)
state_manager = StateManager(storage=storage)
```

#### Error: Checkpoint Load Failed

**Error Message:**
```
ValueError: Checkpoint not found: agent_123_step_10_20231025_120000
```

**Cause:** Checkpoint ID is incorrect or checkpoint was deleted.

**Solution:**

```python
# List available checkpoints
available = await state_manager.list_checkpoints("agent_123")
print(f"Available checkpoints: {[c.checkpoint_id for c in available]}")

# Load latest checkpoint instead
latest_state = await state_manager.resume_from_latest("agent_123")

# Or handle missing checkpoint gracefully
try:
    state = await state_manager.load_checkpoint(checkpoint_id)
except ValueError as e:
    print(f"Checkpoint not found: {e}")
    # Start fresh
    state = AgentState(agent_id="agent_123", step_number=0)
```

#### Error: Database Storage Backend Unavailable

**Error Message:**
```
ConnectionError: Could not connect to database
```

**Cause:** Database not running or connection string incorrect.

**Solution:**

```python
from kaizen.core.autonomy.state import DatabaseStorage, FilesystemStorage
from dataflow import DataFlow

# Try database storage first
try:
    db = DataFlow(database_url="postgresql://localhost/kaizen")
    storage = DatabaseStorage(dataflow=db)
    print("Using database storage")
except Exception as e:
    print(f"Database unavailable: {e}")
    # Fallback to filesystem storage
    storage = FilesystemStorage(base_dir="./checkpoints")
    print("Using filesystem storage")

state_manager = StateManager(storage=storage)
```

#### Issue: Checkpoints Too Large

**Symptoms:** Checkpoint files are hundreds of MB.

**Solution:**

```python
# Enable compression
storage = FilesystemStorage(
    base_dir="./checkpoints",
    compress=True  # gzip compression (5-10x size reduction)
)

# Reduce checkpoint frequency
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=20,  # Every 20 steps instead of 10
    retention_count=50  # Keep only 50 checkpoints
)

# Clean up old checkpoints
await state_manager.cleanup_old_checkpoints(
    agent_id="agent_123",
    keep_count=10  # Keep only last 10
)
```

### Interrupt Mechanism

#### Error: Graceful Shutdown Timeout

**Error Message:**
```
TimeoutError: Graceful shutdown exceeded timeout of 5.0 seconds
```

**Cause:** Agent cycle taking too long to finish.

**Solution:**

```python
# Option 1: Increase graceful shutdown timeout
config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",
    enable_interrupts=True,
    graceful_shutdown_timeout=10.0  # Increase to 10 seconds
)

# Option 2: Use IMMEDIATE mode for faster shutdown
try:
    result = await agent.run_autonomous(task="Long task")
except InterruptedError as e:
    if e.reason.mode == InterruptMode.GRACEFUL:
        print("Graceful shutdown timed out, using immediate mode")
        # Cleanup manually
        await cleanup()
```

#### Error: Checkpoint Not Saved on Interrupt

**Issue:** State lost when interrupted.

**Cause:** `checkpoint_on_interrupt` not enabled.

**Solution:**

```python
# Enable checkpoint on interrupt
config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",
    enable_interrupts=True,
    enable_checkpoints=True,  # MUST enable checkpoints
    checkpoint_on_interrupt=True  # MUST enable this
)

agent = BaseAutonomousAgent(config=config, signature=signature)

# Verify checkpoint saved on interrupt
try:
    result = await agent.run_autonomous(task="Task")
except InterruptedError as e:
    checkpoint_id = e.reason.metadata.get("checkpoint_id")
    if checkpoint_id:
        print(f"State saved to: {checkpoint_id}")
    else:
        print("WARNING: No checkpoint saved!")
```

#### Error: Interrupt Handler Error

**Error Message:**
```
RuntimeError: Interrupt handler check_interrupt() failed
```

**Cause:** Custom interrupt handler has a bug.

**Solution:**

```python
from kaizen.core.autonomy.interrupts import BaseInterruptHandler

class SafeInterruptHandler(BaseInterruptHandler):
    async def check_interrupt(self, context: dict) -> InterruptReason | None:
        try:
            # Your interrupt logic
            if should_interrupt(context):
                return InterruptReason(
                    source=InterruptSource.PROGRAMMATIC,
                    mode=InterruptMode.GRACEFUL,
                    message="Interrupt condition met"
                )
        except Exception as e:
            # ✅ CORRECT - Handle errors gracefully
            print(f"Interrupt handler error: {e}")
            # Don't interrupt on error
            return None

        return None

# Use safe handler
agent.interrupt_manager.add_handler(SafeInterruptHandler())
```

#### Issue: Ctrl+C Not Working

**Symptoms:** Agent ignores Ctrl+C.

**Cause:** Signal handlers not installed.

**Solution:**

```python
# Verify signal handlers installed
agent.interrupt_manager.install_signal_handlers()

# Run agent
try:
    result = await agent.run_autonomous(task="Task")
except InterruptedError as e:
    print(f"Interrupted by: {e.reason.source}")
except KeyboardInterrupt:
    print("KeyboardInterrupt received (signal handlers not installed)")
    # Install handlers for next run
    agent.interrupt_manager.install_signal_handlers()
```

### Memory System

#### Error: Memory Backend Connection Failed

**Error Message:**
```
ConnectionError: Could not connect to memory database
```

**Cause:** DataFlow database not running or connection incorrect.

**Solution:**

```python
from dataflow import DataFlow
from kaizen.memory.backends import DataFlowBackend

# Test database connection first
try:
    db = DataFlow(database_url="postgresql://localhost/kaizen")

    # Test connection
    @db.model
    class TestModel:
        id: str
        content: str

    print("Database connection successful")

    backend = DataFlowBackend(db, model_name="ConversationMessage")

except Exception as e:
    print(f"Database connection failed: {e}")
    # Use alternative storage
    from kaizen.memory import BufferMemory
    backend = BufferMemory(max_turns=100)
```

#### Error: Memory Tier Promotion Failed

**Issue:** Hot tier not promoting to warm tier.

**Cause:** Access count threshold not reached.

**Solution:**

```python
from kaizen.memory.tiers import TierManager

# Lower promotion thresholds
tier_manager = TierManager({
    "hot_promotion_threshold": 2,      # Promote after 2 accesses (default: 5)
    "warm_promotion_threshold": 1,     # Promote to warm after 1 access (default: 3)
    "access_window_seconds": 1800      # 30 min window (default: 3600)
})

# Or disable automatic promotion
tier_manager = TierManager({
    "enable_auto_promotion": False  # Manual promotion only
})

# Manual promotion
await tier_manager.promote_to_warm("key")
```

#### Issue: Memory Retrieval Too Slow

**Symptoms:** Memory access taking > 100ms.

**Cause:** Cold tier queries too slow or tier not optimal.

**Solution:**

```python
# Option 1: Increase cache sizes
config = DataFlowConfig(
    cache_enabled=True,
    cache_ttl=600,  # Increase from 300 to 600 seconds
    batch_size=200  # Increase batch size for bulk operations
)

# Option 2: Use indexes on database
# In DataFlow model:
@db.model
class ConversationMessage:
    id: str
    conversation_id: str  # Add index on this field
    content: str

# Create index via SQL
# CREATE INDEX idx_conversation_id ON conversation_messages(conversation_id);

# Option 3: Reduce query complexity
backend.load_turns(
    conversation_id="session_123",
    limit=10  # Fetch fewer turns
)
```

### Planning Agents

#### Error: Plan Validation Failed

**Error Message:**
```
ValidationError: Plan validation failed: Invalid step 3
```

**Cause:** Generated plan has errors.

**Solution:**

```python
# Option 1: Enable replanning
config = PlanningConfig(
    llm_provider="openai",
    model="gpt-4",
    max_plan_steps=10,
    validation_mode="strict",
    enable_replanning=True,  # ✅ Enable replanning
    max_replanning_attempts=3
)

# Option 2: Use warn mode instead of strict
config = PlanningConfig(
    validation_mode="warn"  # Log warnings but continue
)

# Option 3: Increase max plan steps
config = PlanningConfig(
    max_plan_steps=20  # Allow more complex plans
)
```

#### Error: PEVAgent Not Converging

**Issue:** PEVAgent reaches max iterations without passing verification.

**Cause:** Verification too strict or task too complex.

**Solution:**

```python
# Option 1: Increase max iterations
config = PEVConfig(
    llm_provider="openai",
    model="gpt-4",
    max_iterations=20,  # Increase from 10 to 20
    verification_strictness="medium"  # Reduce strictness
)

# Option 2: Lower confidence threshold
config = PEVConfig(
    min_confidence_threshold=0.7  # Reduce from 0.8 to 0.7
)

# Option 3: Use lenient verification for complex tasks
config = PEVConfig(
    verification_strictness="lenient"  # Most lenient
)

# Check refinement history
result = agent.run(task="Complex task")
print(f"Iterations: {len(result['refinements'])}")
for refinement in result['refinements']:
    print(f"  Issue: {refinement['issue']}")
    print(f"  Fix: {refinement['fix']}")
```

### Meta-Controller Routing

#### Error: No Agent Selected

**Error Message:**
```
ValueError: No suitable agent found for task
```

**Cause:** No agent capabilities match task.

**Solution:**

```python
# Option 1: Add fallback agent
pipeline = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="semantic",
    fallback_agent=general_agent  # ✅ Add fallback
)

# Option 2: Lower match threshold
pipeline = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="semantic",
    min_confidence_score=0.3  # Lower from default 0.5
)

# Option 3: Use round-robin instead
pipeline = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="round-robin"  # Always selects an agent
)
```

#### Issue: Wrong Agent Selected

**Symptoms:** Router selecting suboptimal agent.

**Cause:** Agent capability cards not descriptive enough.

**Solution:**

```python
# ❌ WRONG - Vague capability
qa_agent.capability = "Answering questions"

# ✅ CORRECT - Specific capability
qa_agent.capability = "Question answering for general knowledge, science, and history topics"

# Update A2A capability card
qa_agent_card = qa_agent.to_a2a_card()
qa_agent_card["capabilities"] = [
    "General knowledge Q&A",
    "Scientific explanations",
    "Historical facts",
    "Conceptual understanding"
]

# Test routing
result = pipeline.run(
    task="Explain quantum entanglement",
    debug=True  # Show agent selection scores
)

print(f"Selected: {result['selected_agent']}")
print(f"Score: {result['confidence_score']}")
print(f"All scores: {result['agent_scores']}")  # See all agent scores
```

#### Error: Agent Pipeline Execution Failed

**Error Message:**
```
RuntimeError: Agent execution failed: Agent 'code_agent' raised exception
```

**Cause:** Selected agent failed during execution.

**Solution:**

```python
# Use graceful error handling
pipeline = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="semantic",
    error_handling="graceful",  # ✅ Try fallback on error
    fallback_agent=safe_agent,
    max_retries=2  # Retry up to 2 times
)

# Or catch errors manually
try:
    result = pipeline.run(task="Complex task")
except RuntimeError as e:
    print(f"Primary agent failed: {e}")
    # Try secondary agent manually
    result = secondary_agent.run(task="Complex task")
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
