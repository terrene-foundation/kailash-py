# ADR-020: Unified Agent API Architecture

**Status**: Accepted
**Date**: 2025-10-26
**Related**: All agent features, BaseAgent, Control Protocol, Tool System
**Supersedes**: None

---

## Context

Kaizen currently provides 16 specialized agent classes for different use cases:

**Single-Agent Patterns (10 classes)**:
- `SimpleQAAgent` - Basic question answering
- `ChainOfThoughtAgent` - Step-by-step reasoning
- `ReActAgent` - Reasoning + action cycles
- `RAGResearchAgent` - Research with retrieval
- `CodeGenerationAgent` - Code generation
- `MemoryAgent` - Memory-enhanced conversations
- `AutonomousAgent` - Autonomous task execution
- `CustomSignatureAgent` - Custom signature workflows

**Multi-Modal Agents (2 classes)**:
- `VisionAgent` - Image analysis (Ollama + OpenAI GPT-4V)
- `TranscriptionAgent` - Audio transcription (Whisper)

**Multi-Agent Patterns (5 classes)**:
- `SupervisorWorkerAgent` - Supervisor-worker coordination
- `ConsensusAgent` - Multi-agent consensus building
- `DebateAgent` - Multi-agent debate pattern
- `SequentialAgent` - Sequential agent pipeline
- `HandoffAgent` - Agent-to-agent handoff

**Production Agents (1 class)**:
- `ProductionAgent` - Full-featured production agent

### Key Problems

#### 1. Feature Discoverability Crisis

**Problem**: All features are opt-in and hidden across 16 different classes:

```python
# Memory system (hidden in MemoryAgent)
memory_agent = MemoryAgent(config)

# Tool calling (hidden in AutonomousAgent)
autonomous_agent = AutonomousAgent(config, tools="all"  # Enable 12 builtin tools via MCP

# Vision processing (hidden in VisionAgent)
vision_agent = VisionAgent(config)

# Control protocol (hidden in ProductionAgent)
production_agent = ProductionAgent(config, control_protocol=protocol)
```

**Impact**:
- Developers miss 80%+ of capabilities
- Features require class imports to discover
- Documentation scattered across 16 agent guides
- No default "batteries included" experience

#### 2. Decision Paralysis

**Current Developer Journey**:
1. "I need an AI agent... which class do I import?"
2. Reads documentation for all 16 agent classes
3. "Should I use BaseAgent? ProductionAgent? SimpleQAAgent?"
4. Picks SimpleQAAgent for simplicity
5. Later needs memory → "Do I migrate to MemoryAgent?"
6. Later needs tools → "Do I migrate to AutonomousAgent?"
7. Later needs vision → "Do I migrate to VisionAgent?"
8. **Every feature requires class migration**

**Time to First Working Agent**:
- Current: 30+ minutes (reading docs, choosing class, configuring)
- Desired: 2 minutes (import, configure, run)

#### 3. Cognitive Overhead

**Class Count by Category**:
- 16 specialized agent classes
- Each with unique configuration patterns
- Each with unique method signatures
- Each with unique import paths

**Example: Switching from Q&A to Vision**:
```python
# Before: SimpleQAAgent
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

agent = SimpleQAAgent(QAConfig(model="gpt-4"))
result = agent.ask("What is AI?")

# After: VisionAgent (COMPLETELY DIFFERENT API!)
from kaizen.agents import VisionAgent
from kaizen.agents.multi_modal.vision_agent import VisionAgentConfig

agent = VisionAgent(VisionAgentConfig(model="bakllava"))
result = agent.analyze(image="img.png", question="What is this?")
```

**Problems**:
- Different import paths
- Different config classes
- Different method names (`.ask()` vs `.analyze()`)
- Different parameter patterns
- **Complete rewrite required for every agent type change**

#### 4. Production Readiness Hidden

**Current Pattern**:
```python
# Basic agent (missing 90% of production features)
agent = SimpleQAAgent(QAConfig())

# To add production features:
# 1. Switch to MemoryAgent for memory
# 2. Switch to AutonomousAgent for tools
# 3. Switch to ProductionAgent for control protocol
# 4. Manually wire observability (hooks, tracing, metrics)
# 5. Manually wire checkpointing
# 6. Manually wire streaming
```

**Impact**:
- Production features require manual discovery and wiring
- No guidance on "production-ready" defaults
- Developers ship basic agents to production
- Miss critical capabilities (observability, checkpointing, error handling)

### Requirements

From strategic UX analysis:

1. **Single Entry Point**: `from kaizen import Agent` (not 16 classes)
2. **Zero-Config Defaults**: Everything works without configuration
3. **Configuration Over Classes**: `agent_type="react"` instead of `ReActAgent` class import
4. **Batteries Included**: Memory, tools, observability auto-enabled by default
5. **Progressive Disclosure**: Simple defaults, expert overrides available
6. **No Breaking Changes**: Backward compatible with existing agent classes

**User Vision**:
> "I want to call `Agent`, define configuration, specify `agent_type`, and everything just works seamlessly. Then I can deep dive into specific capabilities if I have requirements."

---

## Decision

We will implement a **unified `Agent` class** with **3-layer architecture**:

### Layer 1: Zero-Config (99% of Users)

```python
from kaizen import Agent

# EVERYTHING enabled by default
agent = Agent(model="gpt-4")
result = agent.run("What is AI?")

# Auto-enabled features:
# ✅ Memory (10 turns, buffer backend)
# ✅ Tools (12 builtin tools registered)
# ✅ Observability (Jaeger tracing, Prometheus metrics, structured logging)
# ✅ Checkpointing (filesystem storage)
# ✅ Streaming (console output)
# ✅ Control protocol (CLI transport)
# ✅ Error handling (automatic retries)
# ✅ Cost tracking (budget limits)
```

**Key Innovation**: **Smart Defaults System**
- Automatically initializes all production features
- Zero manual wiring required
- Sensible defaults for each capability
- Rich console output shows active features

### Layer 2: Configuration (Power Users)

```python
from kaizen import Agent

# Configuration-driven behavior (NO CLASS IMPORTS!)
agent = Agent(
    model="gpt-4",
    agent_type="react",        # Not ReActAgent class!
    memory_turns=20,            # Override default 10
    tools=["read_file", "http_get"],  # Subset of tools
    budget_limit_usd=5.0,       # Cost constraint
    streaming=True,             # Enable streaming
    checkpointing=True,         # Enable checkpointing
)

result = agent.run("Analyze this file: data.txt")

# Available agent_types:
# - "simple" (default): Direct Q&A
# - "react": Reasoning + action cycles
# - "cot": Chain of thought reasoning
# - "rag": Retrieval-augmented generation
# - "autonomous": Full autonomous agent
# - "vision": Vision processing
# - "audio": Audio transcription
```

**Key Innovation**: **agent_type Parameter**
- Replace 16 class imports with 1 configuration parameter
- Preset configurations for each agent pattern
- Easy to switch between agent types
- No code changes required

### Layer 3: Expert Override (1% of Users)

```python
from kaizen import Agent
from my_custom_memory import RedisMemory
from my_custom_tools import CustomToolRegistry
from my_observability import DatadogHooks

# Full control for advanced use cases
agent = Agent(
    model="gpt-4",
    agent_type="autonomous",

    # Custom implementations
    memory=RedisMemory(url="redis://..."),
    tools="all"  # Enable tools via MCP
    hook_manager=DatadogHooks(),
    checkpoint_manager=S3CheckpointManager(),
    control_protocol=HTTPTransport(),
)

result = agent.run("Complex enterprise task")
```

**Key Innovation**: **Override System**
- Accept custom implementations for any component
- Full backward compatibility
- Expert users get full control
- No limitations vs. current system

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent (Unified API)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 1: ZERO-CONFIG (Smart Defaults)                          │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  • Memory (10 turns, buffer)                           │    │
│  │  • Tools (12 builtin)                                  │    │
│  │  • Observability (Jaeger, Prometheus, logs)            │    │
│  │  • Checkpointing (filesystem)                          │    │
│  │  • Streaming (console)                                 │    │
│  │  • Control protocol (CLI)                              │    │
│  │  • Error handling (retries)                            │    │
│  │  • Cost tracking (budget)                              │    │
│  └────────────────────────────────────────────────────────┘    │
│                            ↓                                    │
│  Layer 2: CONFIGURATION (agent_type, params)                   │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  agent_type: simple | react | cot | rag | autonomous  │    │
│  │  memory_turns: 10 (default) | 20 | 50 | None          │    │
│  │  tools: ["all"] | ["read_file", "http_get"] | []      │    │
│  │  budget_limit_usd: None | 5.0 | 10.0                  │    │
│  └────────────────────────────────────────────────────────┘    │
│                            ↓                                    │
│  Layer 3: EXPERT OVERRIDE (custom implementations)             │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  memory: RedisMemory | PostgresMemory                  │    │
│  │  tool_registry: CustomToolRegistry                     │    │
│  │  hook_manager: DatadogHooks | PrometheusHooks         │    │
│  │  checkpoint_manager: S3CheckpointManager               │    │
│  └────────────────────────────────────────────────────────┘    │
│                            ↓                                    │
│                      BaseAgent Core                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Rationale

### Why Unified Agent API?

#### Problem: 16 Classes → Decision Paralysis

**Current (16 classes)**:
```python
# Developer mental model:
"I need memory... do I use MemoryAgent?"
"I need tools... do I use AutonomousAgent?"
"I need vision... do I use VisionAgent?"
"What if I need memory AND tools AND vision?"
"Do I extend all three classes?"
```

**Unified Agent**:
```python
# Developer mental model:
"I need an agent... use Agent"
"I need specific behavior... set agent_type"
"I need custom features... pass parameters"
```

**Impact**:
- 94% reduction in classes (16 → 1)
- 100% reduction in "which class?" decisions
- Single import path for all use cases

#### Problem: Hidden Features → Discoverability Crisis

**Current**:
```python
# Memory hidden in MemoryAgent
# Tools hidden in AutonomousAgent
# Vision hidden in VisionAgent
# Control protocol hidden in ProductionAgent
# Observability hidden in docs (not even a class!)
```

**Unified Agent**:
```python
# On first run, console shows:
"""
🤖 Kaizen Agent v0.5.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Memory: Enabled (10 turns, buffer backend)
✅ Tools: 12 builtin tools registered
✅ Observability: Jaeger (localhost:16686), Prometheus (localhost:9090)
✅ Checkpointing: Filesystem (.kaizen/checkpoints/)
✅ Streaming: Console output
✅ Control Protocol: CLI transport
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
```

**Impact**:
- 100% feature visibility on first run
- Developers immediately aware of all capabilities
- No hidden features requiring documentation mining

#### Problem: Class Migration → Cognitive Overhead

**Current (changing agent types)**:
```python
# Start with SimpleQAAgent
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

agent = SimpleQAAgent(QAConfig(model="gpt-4"))
result = agent.ask("What is AI?")

# Later: Need chain of thought reasoning
# 1. Change import
from kaizen.agents import ChainOfThoughtAgent
from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtConfig

# 2. Change class
agent = ChainOfThoughtAgent(ChainOfThoughtConfig(model="gpt-4"))

# 3. Change method call
result = agent.reason("What is AI?")  # Different method name!
```

**Unified Agent (changing agent types)**:
```python
# Start with simple agent
agent = Agent(model="gpt-4", agent_type="simple")
result = agent.run("What is AI?")

# Later: Need chain of thought reasoning
agent = Agent(model="gpt-4", agent_type="cot")  # ONLY LINE CHANGED
result = agent.run("What is AI?")  # SAME METHOD, SAME CODE
```

**Impact**:
- 83% code reduction (6 lines → 1 line)
- Zero import changes
- Zero method signature changes
- Zero cognitive overhead

#### Problem: Production Features Manual → Hidden Complexity

**Current (adding production features)**:
```python
# Basic agent
agent = SimpleQAAgent(QAConfig())

# Add memory (switch to MemoryAgent)
from kaizen.agents import MemoryAgent
from kaizen.agents.specialized.memory_agent import MemoryAgentConfig
agent = MemoryAgent(MemoryAgentConfig(max_turns=10))

# Add tools (switch to AutonomousAgent)
from kaizen.agents import AutonomousAgent
# Tools auto-configured via MCP


# 12 builtin tools enabled via MCP
agent = AutonomousAgent(config, tools="all"  # Enable 12 builtin tools via MCP

# Add observability (manual wiring)
from kaizen.core.autonomy.hooks import HookManager
from kaizen.core.autonomy.observability import TracingHook, MetricsHook
hook_manager = HookManager()
hook_manager.register(HookEvent.PRE_AGENT_LOOP, TracingHook())
hook_manager.register(HookEvent.PRE_AGENT_LOOP, MetricsHook())
agent = AutonomousAgent(config, tools="all"  # Enable 12 builtin tools via MCP

# Add checkpointing (manual wiring)
from kaizen.memory.checkpoint import CheckpointManager, FilesystemStorage
checkpoint_manager = CheckpointManager(FilesystemStorage(".kaizen/checkpoints"))
agent = AutonomousAgent(
    config,
    tools="all"  # Enable 12 builtin tools via MCP
    hook_manager=hook_manager,
    checkpoint_manager=checkpoint_manager
)

# Result: 20+ lines of boilerplate for production features
```

**Unified Agent (production features auto-enabled)**:
```python
# ALL production features enabled by default
agent = Agent(model="gpt-4")

# Result: 1 line → production-ready
```

**Impact**:
- 95% boilerplate reduction (20 lines → 1 line)
- Zero manual wiring
- Zero hidden setup steps
- Production-ready by default

### Why 3-Layer Architecture?

#### Layer 1: Zero-Config (Developer Experience)

**Target**: 99% of users

**Goal**: "It just works"

**Design Principles**:
1. **No configuration required**
2. **Sensible defaults for everything**
3. **Rich console feedback**
4. **Production-ready out of the box**

**Implementation**:
```python
class Agent:
    def __init__(self, model: str, **kwargs):
        # Smart defaults system
        self.config = self._setup_smart_defaults(model, kwargs)

        # Auto-enable production features
        self.memory = kwargs.get("memory") or self._create_default_memory()
        self.tool_registry = kwargs.get("tool_registry") or self._create_default_tools()
        self.hook_manager = kwargs.get("hook_manager") or self._create_default_hooks()
        self.checkpoint_manager = kwargs.get("checkpoint_manager") or self._create_default_checkpointing()

        # Rich console output
        self._show_startup_banner()
```

**Benefits**:
- **Time to first agent**: 30min → 2min (93% faster)
- **Lines of code**: 20+ → 1 (95% reduction)
- **Production readiness**: Manual → Automatic (100% improvement)

#### Layer 2: Configuration (Power Users)

**Target**: Power users who need specific behavior

**Goal**: Configuration over classes

**Design Principles**:
1. **agent_type parameter replaces class imports**
2. **Behavioral parameters override defaults**
3. **No code changes when switching agent types**
4. **Documentation via type hints**

**Implementation**:
```python
agent = Agent(
    model="gpt-4",
    agent_type="react",           # Preset: ReAct pattern
    memory_turns=20,               # Override default 10
    tools=["read_file", "http_get"],  # Subset of tools
    budget_limit_usd=5.0,          # Cost constraint
    streaming=True,                # Enable streaming
)
```

**Benefits**:
- **Class imports**: 16 → 0 (100% reduction)
- **Configuration clarity**: Explicit parameters vs. hidden class behavior
- **Switching cost**: High (class migration) → Low (parameter change)

#### Layer 3: Expert Override (Advanced Users)

**Target**: 1% of users with custom requirements

**Goal**: Full control without limitations

**Design Principles**:
1. **Accept custom implementations for any component**
2. **Full backward compatibility**
3. **No limitations vs. current system**
4. **Expert users can replace any default**

**Implementation**:
```python
agent = Agent(
    model="gpt-4",
    agent_type="autonomous",

    # Custom implementations
    memory=RedisMemory(url="redis://..."),
    tools="all"  # Enable tools via MCP
    hook_manager=DatadogHooks(),
    checkpoint_manager=S3CheckpointManager(),
)
```

**Benefits**:
- **Flexibility**: Full control when needed
- **Backward compatibility**: Existing custom implementations work
- **No limitations**: Same power as current system

### Why Smart Defaults System?

**Problem**: Current system requires manual setup for every feature

**Solution**: Smart defaults system auto-initializes production features

**Implementation**:
```python
def _setup_smart_defaults(self, model: str, kwargs: dict):
    """
    Auto-configure production features with sensible defaults.

    Features auto-enabled:
    - Memory: 10 turns, buffer backend
    - Tools: 12 builtin tools
    - Observability: Jaeger + Prometheus + logs
    - Checkpointing: Filesystem storage
    - Streaming: Console output
    - Control protocol: CLI transport
    - Error handling: Automatic retries
    - Cost tracking: Budget monitoring
    """
    defaults = {
        # Memory
        "memory_turns": 10,
        "memory_backend": "buffer",

        # Tools
        "tools": "all",  # All 12 builtin tools

        # Observability
        "enable_tracing": True,
        "tracing_endpoint": "http://localhost:16686",
        "enable_metrics": True,
        "metrics_port": 9090,
        "enable_logging": True,
        "log_level": "INFO",
        "enable_audit": True,

        # Checkpointing
        "enable_checkpointing": True,
        "checkpoint_path": ".kaizen/checkpoints",

        # Streaming
        "streaming": True,
        "stream_output": "console",

        # Control protocol
        "control_protocol": "cli",

        # Error handling
        "max_retries": 3,
        "retry_delay": 1.0,

        # Cost tracking
        "budget_limit_usd": None,  # No limit by default
        "warn_threshold": 0.8,  # Warn at 80% of budget
    }

    # Merge user overrides
    return {**defaults, **kwargs}
```

**Benefits**:
- **Zero manual configuration**: All features auto-enabled
- **Sensible defaults**: Production-ready values
- **Override flexibility**: Users can override any default
- **Documentation**: Defaults serve as implicit documentation

### Why agent_type Parameter?

**Problem**: 16 agent classes for different patterns

**Solution**: Single `agent_type` parameter for preset configurations

**Available Types**:
```python
# agent_type="simple" (default)
# - Direct Q&A with no special processing
# - Fastest response time
# - Best for: Simple questions, quick answers

# agent_type="react"
# - Reasoning + Action cycles
# - Tool calling with thought process
# - Best for: Tasks requiring tools, multi-step reasoning

# agent_type="cot"
# - Chain of thought reasoning
# - Step-by-step problem solving
# - Best for: Complex reasoning, math problems

# agent_type="rag"
# - Retrieval-augmented generation
# - Document retrieval + generation
# - Best for: Knowledge-intensive tasks

# agent_type="autonomous"
# - Full autonomous agent
# - Multi-step planning and execution
# - Best for: Complex tasks, long-running operations

# agent_type="vision"
# - Vision processing
# - Image analysis and understanding
# - Best for: Image-based tasks

# agent_type="audio"
# - Audio transcription
# - Speech-to-text processing
# - Best for: Audio processing tasks
```

**Implementation**:
```python
def _configure_agent_type(self, agent_type: str):
    """
    Configure agent behavior based on type.

    Each type is a preset configuration optimizing for specific use cases.
    """
    presets = {
        "simple": {
            "strategy": "AsyncSingleShotStrategy",
            "enable_tools": False,
            "enable_memory": True,
        },
        "react": {
            "strategy": "ReActStrategy",
            "enable_tools": True,
            "enable_memory": True,
            "max_iterations": 10,
        },
        "cot": {
            "strategy": "ChainOfThoughtStrategy",
            "enable_tools": False,
            "enable_memory": True,
            "show_reasoning": True,
        },
        "rag": {
            "strategy": "RAGStrategy",
            "enable_tools": True,
            "enable_memory": True,
            "retrieval_backend": "semantic",
        },
        "autonomous": {
            "strategy": "AutonomousStrategy",
            "enable_tools": True,
            "enable_memory": True,
            "enable_planning": True,
            "max_iterations": 20,
        },
        "vision": {
            "strategy": "VisionStrategy",
            "enable_multimodal": True,
            "enable_tools": False,
        },
        "audio": {
            "strategy": "AudioStrategy",
            "enable_multimodal": True,
            "enable_tools": False,
        },
    }

    return presets[agent_type]
```

**Benefits**:
- **Zero class imports**: `agent_type="react"` instead of `from kaizen.agents import ReActAgent`
- **Easy switching**: Change parameter, not code
- **Preset optimization**: Each type optimized for use case
- **Documentation**: Type names are self-documenting

---

## Consequences

### Positive

1. ✅ **94% Class Reduction**: 16 classes → 1 unified Agent
2. ✅ **93% Faster Onboarding**: 30min → 2min to first working agent
3. ✅ **95% Boilerplate Reduction**: 20+ lines → 1 line for production features
4. ✅ **100% Feature Visibility**: Rich console output shows all active features
5. ✅ **Zero Decision Paralysis**: Single entry point, no "which class?" decisions
6. ✅ **Configuration Over Classes**: `agent_type` parameter replaces class imports
7. ✅ **Production-Ready Defaults**: All features auto-enabled with sensible defaults
8. ✅ **Progressive Disclosure**: Simple defaults → configuration → expert override
9. ✅ **Backward Compatible**: Existing agent classes kept as thin wrappers

### Negative

1. ⚠️ **Initial Implementation Complexity**: Smart defaults system requires careful design
2. ⚠️ **Default Resource Usage**: Auto-enabling all features may use more memory (~50MB)
3. ⚠️ **Configuration Discovery**: More parameters to document (mitigated by type hints)

### Neutral

1. **Migration Path**: Existing agent classes → deprecated but functional
2. **Documentation Update**: Need to update all guides to use unified Agent
3. **Example Migration**: 41 examples need updating to showcase new API

---

## Alternatives Considered

### Alternative 1: Keep 16 Specialized Classes

**Approach**: Maintain current 16-class system, improve documentation

**Pros**:
- No code changes required
- Explicit class names (clear intent)
- Familiar to current users

**Cons**:
- ❌ Doesn't solve decision paralysis
- ❌ Doesn't solve feature discoverability
- ❌ Doesn't solve class migration overhead
- ❌ Documentation improvements don't fix structural problems

**Rejected**: Doesn't address core UX problems.

### Alternative 2: Fluent Builder API

**Approach**: Fluent builder pattern for agent construction

```python
agent = Agent.builder() \
    .with_model("gpt-4") \
    .with_memory(turns=10) \
    .with_tools(["all"]) \
    .with_observability() \
    .build()
```

**Pros**:
- Progressive disclosure
- Clear feature opt-in
- Discoverable via IDE autocomplete

**Cons**:
- ❌ More verbose than unified API
- ❌ Still requires manual feature enabling
- ❌ Doesn't solve "batteries included" problem
- ❌ Builder pattern adds complexity

**Rejected**: More verbose without solving default-on problem.

### Alternative 3: Factory Functions

**Approach**: Factory functions for common patterns

```python
agent = create_simple_agent(model="gpt-4")
agent = create_react_agent(model="gpt-4")
agent = create_rag_agent(model="gpt-4")
```

**Pros**:
- Clear intent
- Preset configurations
- Simple API

**Cons**:
- ❌ Still requires choosing between 16 functions
- ❌ Doesn't unify API
- ❌ Switching agents requires function change

**Rejected**: Doesn't solve class proliferation problem.

### Alternative 4: Plugin System

**Approach**: Base agent with plugin system for features

```python
agent = Agent(model="gpt-4")
agent.use(MemoryPlugin(turns=10))
agent.use(ToolPlugin(tools=["all"]))
agent.use(ObservabilityPlugin())
```

**Pros**:
- Explicit feature opt-in
- Modular design
- Clear dependencies

**Cons**:
- ❌ Not "batteries included"
- ❌ Requires manual plugin registration
- ❌ More verbose than unified API

**Rejected**: Requires manual feature enabling, against "smart defaults" principle.

---

## Implementation Details

### Module Structure

```
src/kaizen/
├── __init__.py              # Exports: Agent (primary API)
├── agent.py                 # NEW: Unified Agent class
├── agent_config.py          # NEW: AgentConfig with smart defaults
├── agent_types.py           # NEW: agent_type presets
├── smart_defaults.py        # NEW: Smart defaults system
├── rich_output.py           # NEW: Rich console output manager
├── core/
│   ├── base_agent.py        # EXISTING: BaseAgent core (unchanged)
│   └── ...
└── agents/
    ├── specialized/         # DEPRECATED: Thin wrappers for backward compat
    │   ├── simple_qa.py     # SimpleQAAgent → Agent(agent_type="simple")
    │   ├── react_agent.py   # ReActAgent → Agent(agent_type="react")
    │   └── ...
    └── ...
```

### Agent Class Implementation

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.agent_config import AgentConfig
from kaizen.agent_types import get_agent_type_preset
from kaizen.smart_defaults import SmartDefaultsManager
from kaizen.rich_output import RichOutputManager

class Agent(BaseAgent):
    """
    Unified agent API with smart defaults and progressive disclosure.

    Layer 1: Zero-Config
        agent = Agent(model="gpt-4")

    Layer 2: Configuration
        agent = Agent(model="gpt-4", agent_type="react", memory_turns=20)

    Layer 3: Expert Override
        agent = Agent(model="gpt-4", memory=RedisMemory())
    """

    def __init__(
        self,
        model: str,
        agent_type: str = "simple",

        # Layer 2: Configuration parameters
        memory_turns: int = 10,
        tools: list = "all",
        budget_limit_usd: float = None,
        streaming: bool = True,
        checkpointing: bool = True,

        # Layer 3: Expert overrides
        memory = None,
        tool_registry = None,
        hook_manager = None,
        checkpoint_manager = None,
        control_protocol = None,

        **kwargs
    ):
        """
        Initialize unified agent with smart defaults.

        Args:
            model: LLM model name (e.g., "gpt-4", "claude-3")
            agent_type: Agent behavior preset (simple, react, cot, rag, autonomous, vision, audio)

            # Layer 2: Configuration
            memory_turns: Number of conversation turns to remember (default: 10)
            tools: Tools to enable ("all", list, or None)
            budget_limit_usd: Maximum cost in USD (default: None = unlimited)
            streaming: Enable streaming output (default: True)
            checkpointing: Enable checkpointing (default: True)

            # Layer 3: Expert Overrides
            memory: Custom memory implementation (overrides memory_turns)
            tool_registry: Custom tool registry (overrides tools)
            hook_manager: Custom hook manager (overrides default observability)
            checkpoint_manager: Custom checkpoint manager (overrides checkpointing)
            control_protocol: Custom control protocol (overrides default CLI)
        """
        # Step 1: Load agent_type preset
        preset = get_agent_type_preset(agent_type)

        # Step 2: Setup smart defaults
        defaults_manager = SmartDefaultsManager()
        config = defaults_manager.create_config(
            model=model,
            preset=preset,
            memory_turns=memory_turns,
            tools=tools,
            budget_limit_usd=budget_limit_usd,
            streaming=streaming,
            checkpointing=checkpointing,
            **kwargs
        )

        # Step 3: Setup components (Layer 3 overrides or smart defaults)
        self.memory = memory or defaults_manager.create_memory(config)
        self.tool_registry = tool_registry or defaults_manager.create_tools(config)
        self.hook_manager = hook_manager or defaults_manager.create_observability(config)
        self.checkpoint_manager = checkpoint_manager or defaults_manager.create_checkpointing(config)
        self.control_protocol = control_protocol or defaults_manager.create_control_protocol(config)

        # Step 4: Initialize BaseAgent
        super().__init__(
            config=config,
            signature=preset.signature,
            memory=self.memory,
            tools="all"  # Enable tools via MCP
            hook_manager=self.hook_manager,
            checkpoint_manager=self.checkpoint_manager,
            control_protocol=self.control_protocol,
        )

        # Step 5: Rich console output
        self.rich_output = RichOutputManager()
        self.rich_output.show_startup_banner(
            agent_type=agent_type,
            config=config,
            components={
                "memory": self.memory,
                "tools": self.tool_registry,
                "observability": self.hook_manager,
                "checkpointing": self.checkpoint_manager,
            }
        )

    def run(self, prompt: str, **kwargs):
        """
        Universal execution method (replaces .ask(), .analyze(), etc).

        Args:
            prompt: Input prompt
            **kwargs: Additional parameters for specific agent types

        Returns:
            dict: Agent result
        """
        # Delegate to BaseAgent.run()
        return super().run(prompt=prompt, **kwargs)
```

### Smart Defaults Manager

```python
class SmartDefaultsManager:
    """
    Create production-ready defaults for all agent components.

    Responsibilities:
    - Memory: Create buffer memory with specified turns
    - Tools: Register builtin or custom tools
    - Observability: Setup Jaeger + Prometheus + logs + audit
    - Checkpointing: Setup filesystem checkpoint storage
    - Control Protocol: Setup CLI or custom transport
    """

    def create_memory(self, config: AgentConfig):
        """Create memory with smart defaults."""
        if config.memory_turns is None:
            return None  # Memory disabled

        from kaizen.memory import BufferMemory
        return BufferMemory(max_turns=config.memory_turns)

    def create_tools(self, config: AgentConfig):
        """Create tool registry with smart defaults."""
        # Tools auto-configured via MCP




        if config.tools == "all":
            # Register all 12 builtin tools
            # 12 builtin tools enabled via MCP
        elif config.tools and isinstance(config.tools, list):
            # Register subset of tools
            from kaizen.tools.builtin import (
                register_file_tools,
                register_api_tools,
                register_bash_tools,
                register_web_tools,
            )

            if any(t.startswith("read_file") for t in config.tools):
                register_file_tools(registry)
            if any(t.startswith("http_") for t in config.tools):
                register_api_tools(registry)
            if "bash_command" in config.tools:
                register_bash_tools(registry)
            if any(t in ["fetch_url", "extract_links"] for t in config.tools):
                register_web_tools(registry)

        return registry

    def create_observability(self, config: AgentConfig):
        """Create observability with smart defaults."""
        from kaizen.core.autonomy.hooks import HookManager
        from kaizen.core.autonomy.observability import (
            TracingHook,
            MetricsHook,
            LoggingHook,
            AuditHook,
        )

        hook_manager = HookManager()

        if config.enable_tracing:
            tracing_hook = TracingHook(endpoint=config.tracing_endpoint)
            hook_manager.register(HookEvent.PRE_AGENT_LOOP, tracing_hook.start_trace)
            hook_manager.register(HookEvent.POST_AGENT_LOOP, tracing_hook.end_trace)

        if config.enable_metrics:
            metrics_hook = MetricsHook(port=config.metrics_port)
            hook_manager.register(HookEvent.PRE_AGENT_LOOP, metrics_hook.record_start)
            hook_manager.register(HookEvent.POST_AGENT_LOOP, metrics_hook.record_end)

        if config.enable_logging:
            logging_hook = LoggingHook(level=config.log_level)
            hook_manager.register(HookEvent.PRE_AGENT_LOOP, logging_hook.log_start)
            hook_manager.register(HookEvent.POST_AGENT_LOOP, logging_hook.log_end)

        if config.enable_audit:
            audit_hook = AuditHook(path=".kaizen/audit.jsonl")
            hook_manager.register(HookEvent.PRE_AGENT_LOOP, audit_hook.record_start)
            hook_manager.register(HookEvent.POST_AGENT_LOOP, audit_hook.record_end)

        return hook_manager

    def create_checkpointing(self, config: AgentConfig):
        """Create checkpointing with smart defaults."""
        if not config.enable_checkpointing:
            return None

        from kaizen.memory.checkpoint import CheckpointManager, FilesystemStorage

        storage = FilesystemStorage(config.checkpoint_path)
        return CheckpointManager(storage)

    def create_control_protocol(self, config: AgentConfig):
        """Create control protocol with smart defaults."""
        from kaizen.core.autonomy.control import ControlProtocol
        from kaizen.core.autonomy.control.transports import CLITransport

        if config.control_protocol == "cli":
            return ControlProtocol(CLITransport())
        elif config.control_protocol == "http":
            from kaizen.core.autonomy.control.transports import HTTPTransport
            return ControlProtocol(HTTPTransport(port=8080))
        elif config.control_protocol == "stdio":
            from kaizen.core.autonomy.control.transports import StdioTransport
            return ControlProtocol(StdioTransport())
        else:
            return ControlProtocol(CLITransport())  # Default to CLI
```

### Rich Output Manager

```python
class RichOutputManager:
    """
    Rich console output for agent startup and execution.

    Shows:
    - Startup banner with active features
    - Real-time execution progress
    - Performance metrics summary
    """

    def show_startup_banner(
        self,
        agent_type: str,
        config: AgentConfig,
        components: dict,
    ):
        """
        Show startup banner with active features.

        Example output:
        🤖 Kaizen Agent v0.5.0
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Agent Type: react (Reasoning + Action)
        Model: gpt-4

        Active Features:
        ✅ Memory: Enabled (10 turns, buffer backend)
        ✅ Tools: 12 builtin tools registered
        ✅ Observability:
           • Jaeger tracing (localhost:16686)
           • Prometheus metrics (localhost:9090)
           • Structured logging (INFO level)
           • Audit trail (.kaizen/audit.jsonl)
        ✅ Checkpointing: Filesystem (.kaizen/checkpoints/)
        ✅ Streaming: Console output
        ✅ Control Protocol: CLI transport
        ✅ Cost Tracking: No limit
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
        print("\n" + "=" * 70)
        print(f"🤖 Kaizen Agent v0.5.0")
        print("=" * 70)
        print(f"Agent Type: {agent_type}")
        print(f"Model: {config.model}")
        print(f"\nActive Features:")

        # Memory
        if components["memory"]:
            print(f"✅ Memory: Enabled ({config.memory_turns} turns, buffer backend)")
        else:
            print("⚪ Memory: Disabled")

        # Tools
        if components["tools"]:
            tool_count = len(components["tools"].list_tools())
            print(f"✅ Tools: {tool_count} tools registered")
        else:
            print("⚪ Tools: Disabled")

        # Observability
        if components["observability"]:
            print("✅ Observability:")
            if config.enable_tracing:
                print(f"   • Jaeger tracing ({config.tracing_endpoint})")
            if config.enable_metrics:
                print(f"   • Prometheus metrics (localhost:{config.metrics_port})")
            if config.enable_logging:
                print(f"   • Structured logging ({config.log_level} level)")
            if config.enable_audit:
                print("   • Audit trail (.kaizen/audit.jsonl)")
        else:
            print("⚪ Observability: Disabled")

        # Checkpointing
        if components["checkpointing"]:
            print(f"✅ Checkpointing: Filesystem ({config.checkpoint_path})")
        else:
            print("⚪ Checkpointing: Disabled")

        # Streaming
        print(f"✅ Streaming: {'Enabled' if config.streaming else 'Disabled'}")

        # Control Protocol
        print(f"✅ Control Protocol: {config.control_protocol} transport")

        # Cost Tracking
        if config.budget_limit_usd:
            print(f"✅ Cost Tracking: ${config.budget_limit_usd} limit")
        else:
            print("✅ Cost Tracking: No limit")

        print("=" * 70 + "\n")
```

---

## Testing Strategy

### Tier 1 (Unit Tests) - 50 tests

**Smart Defaults System (15 tests)**:
- Test default memory creation (buffer, 10 turns)
- Test default tool registry (12 builtin tools)
- Test default observability (Jaeger, Prometheus, logs, audit)
- Test default checkpointing (filesystem storage)
- Test default control protocol (CLI transport)

**Agent Configuration (20 tests)**:
- Test agent_type presets (simple, react, cot, rag, autonomous, vision, audio)
- Test configuration parameter overrides
- Test expert override with custom implementations
- Test backward compatibility with existing agents

**Rich Output Manager (15 tests)**:
- Test startup banner generation
- Test feature visibility in console output
- Test progress reporting
- Test performance metrics display

### Tier 2 (Integration Tests) - 25 tests

**Agent Type Switching (10 tests)**:
- Test switching between agent types (simple → react → cot)
- Test configuration preservation across switches
- Test memory continuity across agent types
- Test tool registry preservation

**Production Features Integration (15 tests)**:
- Test memory + tools + observability integration
- Test checkpointing + streaming integration
- Test control protocol + cost tracking integration
- Test all features enabled simultaneously

### Tier 3 (E2E Tests) - 15 tests

**Real-World Scenarios (15 tests)**:
- Test zero-config agent with real LLM
- Test agent_type switching with real tasks
- Test production features with real infrastructure
- Test backward compatibility with existing examples

**Total**: 90 new tests (targeting 100% passing)

---

## Usage Examples

### Example 1: Zero-Config (Layer 1)

```python
from kaizen import Agent

# EVERYTHING works out of the box
agent = Agent(model="gpt-4")

# Startup banner shows:
# ✅ Memory: Enabled (10 turns)
# ✅ Tools: 12 builtin tools
# ✅ Observability: Jaeger + Prometheus + logs + audit
# ✅ Checkpointing: Filesystem
# ✅ Streaming: Console
# ✅ Control Protocol: CLI

result = agent.run("What is AI?")
print(result["answer"])

# Memory automatically preserves context
result = agent.run("Tell me more")
```

### Example 2: Configuration (Layer 2)

```python
from kaizen import Agent

# Configuration-driven behavior
agent = Agent(
    model="gpt-4",
    agent_type="react",        # ReAct pattern (not ReActAgent class!)
    memory_turns=20,            # 20 turns instead of 10
    tools=["read_file", "http_get"],  # Subset of tools
    budget_limit_usd=5.0,       # Cost constraint
)

result = agent.run("Analyze the file data.txt")
# Agent automatically uses read_file tool
```

### Example 3: Agent Type Switching

```python
from kaizen import Agent

# Start with simple Q&A
agent = Agent(model="gpt-4", agent_type="simple")
result = agent.run("What is quantum computing?")

# Switch to chain of thought for reasoning
agent = Agent(model="gpt-4", agent_type="cot")
result = agent.run("Explain step by step how quantum computers work")

# Switch to RAG for research
agent = Agent(model="gpt-4", agent_type="rag")
result = agent.run("What are the latest quantum computing breakthroughs?")

# NO CLASS CHANGES, NO IMPORT CHANGES, SAME .run() METHOD
```

### Example 4: Expert Override (Layer 3)

```python
from kaizen import Agent
from my_custom_memory import RedisMemory
from my_custom_tools import CustomToolRegistry
from my_observability import DatadogHooks

# Full control for advanced use cases
agent = Agent(
    model="gpt-4",
    agent_type="autonomous",

    # Custom implementations
    memory=RedisMemory(url="redis://prod:6379"),
    tools="all"  # Enable tools via MCP
    hook_manager=DatadogHooks(api_key="dd_key"),
    checkpoint_manager=S3CheckpointManager(bucket="prod-checkpoints"),
)

result = agent.run("Complex enterprise task")
```

### Example 5: Before/After Migration

**BEFORE (Current System)**:
```python
# Basic agent
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

config = QAConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7
)

agent = SimpleQAAgent(config)
result = agent.ask("What is AI?")

# Add memory → switch to MemoryAgent
from kaizen.agents import MemoryAgent
from kaizen.agents.specialized.memory_agent import MemoryAgentConfig

config = MemoryAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7,
    max_turns=10
)

agent = MemoryAgent(config)
result = agent.ask("What is AI?")

# Add tools → switch to AutonomousAgent
from kaizen.agents import AutonomousAgent
# Tools auto-configured via MCP



# 12 builtin tools enabled via MCP

config = MemoryAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7,
    max_turns=10
)

agent = AutonomousAgent(config, tools="all"  # Enable 12 builtin tools via MCP
result = agent.run("What is AI?")  # Different method!

# Total: 30+ lines, 3 class migrations, 2 method changes
```

**AFTER (Unified Agent)**:
```python
from kaizen import Agent

# Basic agent (memory + tools auto-enabled)
agent = Agent(model="gpt-4")
result = agent.run("What is AI?")

# Total: 2 lines, 0 class migrations, 0 method changes
```

**Impact**: 93% code reduction (30 lines → 2 lines)

---

## Migration Strategy

### Phase 1: Implementation (Week 1)

1. Create `agent.py` with unified Agent class
2. Create `agent_config.py` with AgentConfig
3. Create `agent_types.py` with preset configurations
4. Create `smart_defaults.py` with SmartDefaultsManager
5. Create `rich_output.py` with RichOutputManager

### Phase 2: Testing (Week 2)

1. Write 50 unit tests for smart defaults
2. Write 25 integration tests for agent types
3. Write 15 E2E tests for real-world scenarios
4. Target: 90 tests passing

### Phase 3: Documentation (Week 3)

1. Update all guides to use unified Agent
2. Create migration guide (BaseAgent → Agent)
3. Update SKILL.md to reflect unified approach
4. Update examples to showcase new API

### Phase 4: Backward Compatibility (Week 4)

1. Keep existing agent classes as thin wrappers
2. Add deprecation warnings
3. Update imports to point to unified Agent
4. Maintain 100% backward compatibility

### Backward Compatibility Example

```python
# OLD: SimpleQAAgent (deprecated but functional)
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

agent = SimpleQAAgent(QAConfig(model="gpt-4"))
result = agent.ask("What is AI?")

# IMPLEMENTATION (thin wrapper):
class SimpleQAAgent(Agent):
    """Deprecated: Use Agent(agent_type='simple') instead."""

    def __init__(self, config: QAConfig):
        warnings.warn(
            "SimpleQAAgent is deprecated. Use Agent(agent_type='simple') instead.",
            DeprecationWarning
        )
        super().__init__(
            model=config.model,
            agent_type="simple",
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    def ask(self, question: str):
        """Deprecated: Use .run() instead."""
        return self.run(prompt=question)
```

**Benefits**:
- Existing code continues to work
- Deprecation warnings guide migration
- No breaking changes
- Users can migrate at their own pace

---

## References

- **Implementation**: `src/kaizen/agent.py`, `src/kaizen/smart_defaults.py`, `src/kaizen/rich_output.py`
- **Tests**: `tests/unit/test_unified_agent.py`, `tests/integration/test_agent_types.py`, `tests/e2e/test_unified_agent_e2e.py`
- **Documentation**: `docs/guides/unified-agent-api.md`, `docs/guides/migration-guide.md`
- **Examples**: `examples/unified-agent/` (15 new examples)
- **Related ADRs**: ADR-006 (BaseAgent Architecture), ADR-012 (Tool Integration), ADR-011 (Control Protocol)

---

**Approved**: 2025-10-26
**Implementation**: TBD (Phase 1-4, 4 weeks)
**Test Coverage**: Target 90 tests (100% passing)
