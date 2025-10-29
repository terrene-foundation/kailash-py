# BaseAgent Architecture Guide

## Overview

BaseAgent is the unified foundation for all Kaizen agents, providing a consistent interface for signature-based programming, execution strategies, memory management, and tool integration.

**Key Benefits:**
- **Unified Interface**: All agents extend BaseAgent with consistent patterns
- **Lazy Initialization**: Efficient resource management
- **Strategy Pattern**: Pluggable execution strategies (sync, async, multi-cycle)
- **Auto-configuration**: Domain configs automatically converted to BaseAgentConfig
- **Tool Integration**: Universal tool calling and MCP server support (v0.2.0+)
- **A2A Protocol**: Automatic capability card generation for multi-agent coordination

**Version:** Kaizen v0.2.0+

---

## Core Architecture

### Class Hierarchy

```
BaseAgent (abstract base class)
├── Signature-based I/O
├── Execution Strategy (pluggable)
├── Memory Management (optional)
├── Tool Integration (optional v0.2.0+)
├── Control Protocol (optional v0.2.0+)
└── A2A Capability Cards
```

### Key Components

**1. Signature System**
- Type-safe input/output definition
- Field validation and parsing
- Automatic prompt generation

**2. Execution Strategies**
- `AsyncSingleShotStrategy` (default) - Single LLM call, async-first
- `MultiCycleStrategy` - Autonomous multi-turn execution with convergence detection

**3. Memory Integration**
- Optional SharedMemoryPool for multi-agent coordination
- Session-based memory with configurable retention
- Automatic serialization and retrieval

**4. Tool Calling (v0.2.0+)**
- 12 builtin tools (file, HTTP, bash, web)
- Custom tool registration via ToolRegistry
- MCP server integration via mcp_servers parameter
- Danger-level based approval workflows

**5. Control Protocol (v0.2.0+)**
- Bidirectional agent ↔ client communication
- User questions, approval requests, progress reporting
- Multiple transports (CLI, HTTP/SSE, stdio, memory)

---

## Creating a Custom Agent

### Basic Pattern

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

# 1. Define Signature
class MySignature(Signature):
    input_field: str = InputField(desc="User input")
    output_field: str = OutputField(desc="Agent output")

# 2. Define Domain Config
@dataclass
class MyConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    # BaseAgent auto-extracts these fields

# 3. Extend BaseAgent
class MyAgent(BaseAgent):
    def __init__(self, config: MyConfig):
        super().__init__(
            config=config,  # Auto-converted to BaseAgentConfig
            signature=MySignature()
        )

    def process(self, user_input: str) -> dict:
        result = self.run(input_field=user_input)
        return result

# 4. Execute
agent = MyAgent(MyConfig())
result = agent.process("Hello")
print(result['output_field'])
```

---

## Execution Strategies

### AsyncSingleShotStrategy (Default)

**When to Use:**
- Single-turn question answering
- Deterministic transformations
- Non-autonomous agents
- Most common use case (95%)

**Example:**
```python
from kaizen.agents import SimpleQAAgent

agent = SimpleQAAgent(config)  # Uses AsyncSingleShotStrategy by default
result = agent.ask("What is AI?")
```

**Characteristics:**
- One LLM call per execution
- Fast and predictable
- No tool calling loop
- Async-first (anyio-based)

---

### MultiCycleStrategy (Autonomous)

**When to Use:**
- Agents need iterative refinement
- Tool calling with autonomous loops
- ReAct pattern (reasoning + action cycles)
- Complex problem solving requiring multiple steps

**Example:**
```python
from kaizen.agents import ReActAgent

# ReActAgent uses MultiCycleStrategy internally
agent = ReActAgent(config, tools="all"  # Enable 12 builtin tools via MCP
result = agent.solve("Find and summarize the latest research on AI safety")
# Agent autonomously:
# 1. Reasons about task
# 2. Calls tools (search, read files)
# 3. Iterates until objective met
# 4. Returns final answer
```

**Characteristics:**
- Multiple LLM calls (autonomous loop)
- Objective-based convergence detection
- Tool calling integration
- Complex reasoning patterns

---

## Configuration System

### Domain Configs → BaseAgentConfig

BaseAgent automatically extracts configuration fields:

```python
@dataclass
class MyDomainConfig:
    # BaseAgent extracts these:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 500

    # Domain-specific fields (not extracted):
    my_custom_field: str = "value"

# Internally converted to:
# BaseAgentConfig(
#     llm_provider="openai",
#     model="gpt-4",
#     temperature=0.7,
#     max_tokens=500
# )
```

**Auto-extracted Fields:**
- `llm_provider`
- `model`
- `temperature`
- `max_tokens`
- `provider_config`
- `max_turns` (for memory)
- `session_id` (for memory)

---

## Memory Integration

### Opt-in Memory

```python
@dataclass
class ConfigWithMemory:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    max_turns: int = 10  # Enables BufferMemory

agent = MyAgent(config)

# Use session_id for memory continuity
result1 = agent.run(input="My name is Alice", session_id="user123")
result2 = agent.run(input="What's my name?", session_id="user123")
# Returns: "Your name is Alice"
```

### Shared Memory (Multi-Agent)

```python
from kaizen.memory import SharedMemoryPool

shared_pool = SharedMemoryPool()

agent1 = MyAgent(config, shared_memory=shared_pool, agent_id="agent1")
agent2 = MyAgent(config, shared_memory=shared_pool, agent_id="agent2")

# agent1 writes insight
agent1.write_to_memory(
    content={"finding": "Important discovery"},
    tags=["research"],
    importance=0.9
)

# agent2 can read it
insights = agent2.read_from_memory(tags=["research"])
```

---

## Tool Integration (v0.2.0+)

### Enable Tool Calling

```python
# Tools auto-configured via MCP

# Create registry

# 12 builtin tools enabled via MCP

# Enable for agent (opt-in)
agent = MyAgent(config, tools="all"  # Enable 12 builtin tools via MCP

# Agent can now call tools
result = await agent.execute_tool("read_file", {"path": "data.txt"})
```

### MCP Server Integration

```python
# Add MCP servers
mcp_servers = [
    {"name": "filesystem", "command": "mcp-server-filesystem"},
    {"name": "git", "command": "mcp-server-git"}
]

agent = MyAgent(
    config,
    tools="all"  # Enable 12 builtin tools via MCP
    mcp_servers=mcp_servers  # MCP integration
)
```

**All 25 agents support tool_registry and mcp_servers (v0.2.0+)**

---

## Control Protocol (v0.2.0+)

### Interactive Agents

```python
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

# Setup protocol
transport = CLITransport()
protocol = ControlProtocol(transport)

# Enable for agent
agent = MyAgent(config, control_protocol=protocol)

# Agent can now interact with user
class InteractiveAgent(BaseAgent):
    async def process(self):
        answer = await self.ask_user_question(
            "Which option?",
            ["Fast", "Accurate", "Balanced"]
        )

        approved = await self.request_approval(
            "Delete temp files",
            {"count": 10}
        )

        await self.report_progress("Processing...", 50.0)
```

---

## A2A Protocol Integration

### Automatic Capability Cards

BaseAgent automatically generates A2A capability cards:

```python
agent = MyAgent(config)

# Get A2A capability card
card = agent.to_a2a_card()
# {
#   "name": "MyAgent",
#   "description": "...",
#   "capabilities": ["can_process", "can_analyze"],
#   "input_schema": {...},
#   "output_schema": {...}
# }

# Used by multi-agent coordinator for semantic matching
coordinator.select_agent_for_task(task, agents)  # Uses A2A cards
```

---

## Lifecycle Methods

### Initialization

```python
def __init__(self, config, signature, **kwargs):
    # 1. Config extraction
    # 2. Signature validation
    # 3. Strategy selection
    # 4. Memory setup (if configured)
    # 5. Tool integration (if provided)
    # 6. Control protocol (if provided)
```

### Execution

```python
def run(self, **inputs) -> dict:
    # 1. Validate inputs against signature
    # 2. Build prompt from signature + inputs
    # 3. Execute via strategy
    # 4. Parse outputs from signature
    # 5. Return structured results
```

### Helper Methods

**Result Extraction:**
```python
# Defensive parsing with defaults
value = self.extract_str(result, "field", default="")
items = self.extract_list(result, "items", default=[])
data = self.extract_dict(result, "data", default={})
number = self.extract_float(result, "score", default=0.0)
```

**Memory Helpers:**
```python
# Concise memory writing
self.write_to_memory(
    content={"key": "value"},
    tags=["category"],
    importance=0.8
)
```

---

## Best Practices

### 1. Use Domain Configs

```python
# ✅ GOOD
@dataclass
class MyConfig:
    llm_provider: str = "openai"
    my_domain_field: str = "value"

agent = MyAgent(MyConfig())  # Auto-conversion

# ❌ BAD
config = BaseAgentConfig(llm_provider="openai")
agent = MyAgent(config)  # Manual BaseAgentConfig
```

---

### 2. Let Strategy Be Default

```python
# ✅ GOOD - AsyncSingleShotStrategy used automatically
agent = MyAgent(config)

# ❌ BAD - Manual strategy selection (unnecessary)
from kaizen.strategies import AsyncSingleShotStrategy
agent = MyAgent(config, strategy=AsyncSingleShotStrategy())
```

---

### 3. Use Helper Methods

```python
# ✅ GOOD
answer = self.extract_str(result, "answer", default="No answer")

# ❌ BAD
answer = result.get("answer", "No answer") if "answer" in result else "No answer"
```

---

### 4. Opt-in Features

```python
# ✅ GOOD - Only add what you need
agent = MyAgent(config)  # Minimal

# ✅ GOOD - Add memory when needed
agent = MyAgent(config, shared_memory=pool)

# ✅ GOOD - Add tools when needed
agent = MyAgent(config, tools="all"  # Enable 12 builtin tools via MCP
```

---

## Common Patterns

### Pattern 1: Simple QA Agent

```python
class QAAgent(BaseAgent):
    def ask(self, question: str) -> str:
        result = self.run(question=question)
        return self.extract_str(result, "answer", default="")
```

### Pattern 2: Multi-Step Agent

```python
class MultiStepAgent(BaseAgent):
    async def process(self, task: str) -> dict:
        # Step 1: Plan
        plan_result = self.run(task=task, step="plan")

        # Step 2: Execute
        exec_result = self.run(plan=plan_result["plan"], step="execute")

        # Step 3: Verify
        verify_result = self.run(execution=exec_result, step="verify")

        return verify_result
```

### Pattern 3: Autonomous Agent with Tools

```python
from kaizen.strategies import MultiCycleStrategy

class AutonomousAgent(BaseAgent):
    def __init__(self, config, tool_registry):
        super().__init__(
            config=config,
            signature=MySignature(),
            strategy=MultiCycleStrategy(),  # Explicit for autonomous
            tools="all"  # Enable tools via MCP
        )

    def solve(self, problem: str) -> dict:
        return self.run(problem=problem)
        # Automatically loops with tool calls until solved
```

---

## Testing

### Unit Testing with Mock Provider

```python
@dataclass
class TestConfig:
    llm_provider: str = "mock"  # Use mock provider
    model: str = "mock-model"

agent = MyAgent(TestConfig())
result = agent.run(input="test")

assert "output_field" in result
```

---

## Related Documentation

- **[Signature Programming](signature-programming.md)** - Type-safe I/O with signatures
- **[Strategy Selection Guide](../reference/strategy-selection-guide.md)** - When to use which strategy
- **[Memory Patterns](../reference/memory-patterns-guide.md)** - Memory usage patterns
- **[Tool Integration](../reference/control-protocol-api.md)** - Tool calling and MCP
- **[API Reference](../reference/api-reference.md)** - Complete API documentation

---

**Last Updated:** 2025-10-22
**Version:** Kaizen v0.2.0
**Status:** Production-ready ✅
