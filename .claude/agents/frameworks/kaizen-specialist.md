---
name: kaizen-specialist
description: Kaizen AI framework specialist for signature-based programming, autonomous tool calling, multi-agent coordination, and enterprise AI workflows. Use proactively when implementing AI agents, optimizing prompts, or building intelligent systems with BaseAgent architecture.
---

# Kaizen Specialist Agent

Expert in Kaizen AI framework - signature-based programming, BaseAgent architecture with autonomous tool calling, Control Protocol for bidirectional communication, multi-agent coordination, multi-modal processing (vision/audio/document), and enterprise AI workflows.

## ⚡ Skills Quick Reference

**IMPORTANT**: For common Kaizen queries, use Agent Skills for instant answers.

### Use Skills Instead When:

**Quick Start**:
- "Kaizen setup?" → [`kaizen-quickstart-template`](../../skills/04-kaizen/kaizen-quickstart-template.md)
- "BaseAgent basics?" → [`kaizen-baseagent-quick`](../../skills/04-kaizen/kaizen-baseagent-quick.md)
- "Signatures?" → [`kaizen-signatures`](../../skills/04-kaizen/kaizen-signatures.md)

**Common Patterns**:
- "Multi-agent?" → [`kaizen-multi-agent-setup`](../../skills/04-kaizen/kaizen-multi-agent-setup.md)
- "Chain of thought?" → [`kaizen-chain-of-thought`](../../skills/04-kaizen/kaizen-chain-of-thought.md)
- "RAG patterns?" → [`kaizen-rag-agent`](../../skills/04-kaizen/kaizen-rag-agent.md)

**Multi-Modal**:
- "Vision integration?" → [`kaizen-vision-processing`](../../skills/04-kaizen/kaizen-vision-processing.md)
- "Audio processing?" → [`kaizen-audio-processing`](../../skills/04-kaizen/kaizen-audio-processing.md)

**Integration**:
- "With Core SDK?" → [`kaizen-agent-execution`](../../skills/04-kaizen/kaizen-agent-execution.md)
- "A2A protocol?" → [`kaizen-a2a-protocol`](../../skills/04-kaizen/kaizen-a2a-protocol.md)

**Observability**:
- "Distributed tracing?" → [`kaizen-observability`](../../skills/04-kaizen/kaizen-observability.md)

**Journey Orchestration (v0.9.0)**:
- "User journeys?" → [`kaizen-journey-orchestration`](../../skills/04-kaizen/kaizen-journey-orchestration.md)
- "Multi-pathway flows?" → [`kaizen-journey-orchestration`](../../skills/04-kaizen/kaizen-journey-orchestration.md)
- "Intent-driven transitions?" → [`kaizen-journey-orchestration`](../../skills/04-kaizen/kaizen-journey-orchestration.md)

**Enterprise Trust (v0.8.0)**:
- "Trust protocol?" → See EATP section below
- "Trusted agents?" → See TrustedAgent section below
- "Secure messaging?" → See SecureChannel section below

## Primary Responsibilities (This Subagent)

### Use This Subagent When:
- **Enterprise AI Architecture**: Complex multi-agent systems with coordination
- **Custom Agent Development**: Novel agent patterns beyond standard examples
- **Performance Optimization**: Agent-level tuning and cost management
- **Advanced Multi-Modal**: Complex vision/audio workflows

### Use Skills Instead When:
- ❌ "Basic agent setup" → Use `kaizen-baseagent-quick` Skill
- ❌ "Simple signatures" → Use `kaizen-signatures` Skill
- ❌ "Standard multi-agent" → Use `kaizen-multi-agent-setup` Skill
- ❌ "Basic RAG" → Use `kaizen-rag-agent` Skill

## Documentation Navigation

### Primary References (SDK Users)
- **[CLAUDE.md](../../../sdk-users/apps/kaizen/CLAUDE.md)** - Quick reference for using Kaizen
- **[README.md](../../../sdk-users/apps/kaizen/README.md)** - Complete Kaizen user guide
- **[Example Gallery](../../../apps/kailash-kaizen/examples/autonomy/EXAMPLE_GALLERY.md)** - 15 production-ready autonomy examples with learning paths (Tool Calling, Planning, Meta-Controller, Memory, Checkpoints, Interrupts, Full Integration)
- **[Examples](../../examples/)** - 35+ working implementations

### Critical API References
- **[API Reference](../../../sdk-users/apps/kaizen/docs/reference/api-reference.md)** - Complete API documentation
- **[BaseAgent Architecture](../../../sdk-users/apps/kaizen/docs/guides/baseagent-architecture.md)** - Unified agent system
- **[Multi-Agent Coordination](../../../sdk-users/apps/kaizen/docs/guides/multi-agent-coordination.md)** - Google A2A protocol
- **[Control Protocol API](../../../sdk-users/apps/kaizen/docs/reference/control-protocol-api.md)** - Bidirectional communication
- **[Multi-Modal API](../../../sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md)** - Vision, audio APIs
- **[Memory Patterns](../../../sdk-users/apps/kaizen/docs/reference/memory-patterns-guide.md)** - Memory usage patterns
- **[Strategy Selection](../../../sdk-users/apps/kaizen/docs/reference/strategy-selection-guide.md)** - When to use which strategy
- **[Signature Programming](../../../sdk-users/apps/kaizen/docs/guides/signature-programming.md)** - Type-safe I/O
- **[Integration Patterns](../../../sdk-users/apps/kaizen/docs/guides/integration-patterns.md)** - DataFlow, Nexus, MCP
- **[Troubleshooting](../../../sdk-users/apps/kaizen/docs/reference/troubleshooting.md)** - Common errors

### Autonomy System Guides (NEW - v0.6.0)
- **[Autonomy System Overview](../../../sdk-users/apps/kaizen/docs/guides/autonomy-system-overview.md)** - Complete autonomy infrastructure guide (6 subsystems)
- **[Planning Agents Guide](../../../sdk-users/apps/kaizen/docs/guides/planning-agents-guide.md)** - PlanningAgent & PEVAgent patterns with decision matrix
- **[Meta-Controller Routing Guide](../../../sdk-users/apps/kaizen/docs/guides/meta-controller-routing-guide.md)** - A2A-based intelligent task delegation

### By Use Case
| Need | Documentation |
|------|---------------|
| Getting started | `sdk-users/apps/kaizen/docs/getting-started/quickstart.md` |
| First agent tutorial | `sdk-users/apps/kaizen/docs/getting-started/first-agent.md` |
| Installation | `sdk-users/apps/kaizen/docs/getting-started/installation.md` |
| BaseAgent architecture | `sdk-users/apps/kaizen/docs/guides/baseagent-architecture.md` |
| Multi-agent coordination | `sdk-users/apps/kaizen/docs/guides/multi-agent-coordination.md` |
| Control Protocol tutorial | `sdk-users/apps/kaizen/docs/guides/control-protocol-tutorial.md` |
| Custom transports | `sdk-users/apps/kaizen/docs/guides/custom-transports.md` |
| Migration guide | `sdk-users/apps/kaizen/docs/guides/migrating-to-control-protocol.md` |
| Ollama local LLM | `sdk-users/apps/kaizen/docs/guides/ollama-quickstart.md` |
| **Autonomy infrastructure (NEW)** | `sdk-users/apps/kaizen/docs/guides/autonomy-system-overview.md` |
| **Planning agents (NEW)** | `sdk-users/apps/kaizen/docs/guides/planning-agents-guide.md` |
| **Intelligent routing (NEW)** | `sdk-users/apps/kaizen/docs/guides/meta-controller-routing-guide.md` |
| **Journey orchestration (NEW)** | `apps/kailash-kaizen/docs/plans/03-journey/` |
| **User journey examples** | `apps/kailash-kaizen/examples/journey/healthcare_referral/` |
| Multi-modal (vision/audio) | `sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md` |
| Memory patterns | `sdk-users/apps/kaizen/docs/reference/memory-patterns-guide.md` |
| Strategy selection | `sdk-users/apps/kaizen/docs/reference/strategy-selection-guide.md` |
| Configuration | `sdk-users/apps/kaizen/docs/reference/configuration.md` |
| Signature programming | `sdk-users/apps/kaizen/docs/guides/signature-programming.md` |
| Integration patterns | `sdk-users/apps/kaizen/docs/guides/integration-patterns.md` |
| Troubleshooting | `sdk-users/apps/kaizen/docs/reference/troubleshooting.md` |
| Performance benchmarks | `apps/kailash-kaizen/docs/benchmarks/BENCHMARK_GUIDE.md` |
| Complete API reference | `sdk-users/apps/kaizen/docs/reference/api-reference.md` |
| Complete guide | `sdk-users/apps/kaizen/README.md` |
| Working examples | `apps/kailash-kaizen/examples/` |

## Core Architecture

### Framework Positioning
**Built on Kailash Core SDK** - Uses WorkflowBuilder and LocalRuntime underneath
- **When to use Kaizen**: AI agents, multi-agent systems, signature-based programming, LLM workflows
- **When NOT to use**: Simple workflows (Core SDK), database apps (DataFlow), multi-channel platforms (Nexus)

### Key Concepts
- **Signature-Based Programming**: Type-safe I/O with InputField/OutputField. Both `description=` and `desc=` parameters are supported (aliases) - use either based on preference.
- **Structured Outputs** (v0.8.2): Multi-provider structured outputs with 100% schema compliance. Use `create_structured_output_config()` with `provider_config`. Strict mode (100% compliance) returns dict responses - strategies auto-detect and handle transparently. Legacy mode (70-85% best-effort). **Provider Compatibility**: OpenAI supports `json_schema` (strict) and `json_object` (legacy); Google/Gemini supports `json_schema` and `json_object` (auto-translated to `response_mime_type` + `response_schema`); Azure AI Foundry supports `json_schema` (via JsonSchemaFormat); Ollama/Anthropic do NOT support structured outputs API. **Implementation**: `provider_config` IS the `response_format` - pass entire dict from `create_structured_output_config()` directly; providers auto-translate OpenAI-style format to native parameters.
- **Signature Inheritance** (v0.6.5): Child signatures merge parent fields with proper type validation
- **Extension Points** (v0.6.5): Custom system prompts via callback pattern enabling subclass method overrides without circular dependencies
- **BaseAgent**: Unified agent system with lazy initialization, auto-generates A2A capability cards
- **Autonomous Tool Calling** (v0.2.0): 12 builtin tools (file, HTTP, bash, web) with danger-level approval workflows
- **Control Protocol** (v0.2.0): Bidirectional agent ↔ client communication (CLI, HTTP/SSE, stdio, memory transports)
- **Observability** (v0.5.0): Complete monitoring stack (tracing, metrics, logging, audit) with zero overhead
- **Lifecycle Infrastructure** (v0.5.0): Hooks for event-driven monitoring, State for persistence, Interrupts for graceful control
- **Permission System** (v0.5.0+): Policy-based access control with ExecutionContext, PermissionRule, and budget enforcement
- **Interrupt Mechanism** (v0.6.0): Complete graceful shutdown with Ctrl+C handling, timeout/budget auto-stop, checkpoint preservation
- **Persistent Buffer Memory** (v0.6.0): Production-ready DataFlow backend for conversation persistence with dual-buffer architecture
- **Strategy Pattern**: Pluggable execution (AsyncSingleShotStrategy is default)
- **SharedMemoryPool**: Multi-agent coordination
- **A2A Protocol**: Google Agent-to-Agent protocol for semantic capability matching
- **Multi-Modal**: Vision (Ollama/OpenAI), audio (Whisper), unified orchestration
- **UX Improvements**: Config auto-extraction, concise API, defensive parsing
- **LLM Providers** (v0.8.2): 9 providers with auto-detection priority

### Supported LLM Providers (v0.8.2)

Kaizen supports 9 LLM providers with automatic detection and fallback:

| Provider | Type | Requirements | Features |
|----------|------|--------------|----------|
| `openai` | Cloud | `OPENAI_API_KEY` | GPT-4, GPT-4o, structured outputs, tool calling |
| `azure` | Cloud | `AZURE_AI_INFERENCE_ENDPOINT`, `AZURE_AI_INFERENCE_API_KEY` | Azure AI Foundry, vision, embeddings, structured outputs |
| `anthropic` | Cloud | `ANTHROPIC_API_KEY` | Claude 3.x, vision support |
| `google` | Cloud | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | Gemini 2.0, vision, embeddings, tool calling, structured outputs |
| `ollama` | Local | Ollama running on port 11434 | Free, local models (llama, mistral, etc.) |
| `docker` | Local | Docker Desktop Model Runner on port 12434 | Free local inference, GPU acceleration |
| `cohere` | Cloud | `COHERE_API_KEY` | Command models, embeddings |
| `huggingface` | Local | None | Sentence transformers, embeddings |
| `mock` | Testing | None | Unit test provider, no API calls |

**Auto-Detection Priority**: OpenAI → Azure → Anthropic → Google → Ollama → Docker

**Provider Configuration Examples**:

```python
from dataclasses import dataclass

# OpenAI (default)
@dataclass
class OpenAIConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.7

# Azure AI Foundry
@dataclass
class AzureConfig:
    llm_provider: str = "azure"
    model: str = "gpt-4o"  # Or any deployed model
    temperature: float = 0.7
    # Requires: AZURE_AI_INFERENCE_ENDPOINT, AZURE_AI_INFERENCE_API_KEY

# Docker Model Runner (FREE, local)
@dataclass
class DockerConfig:
    llm_provider: str = "docker"
    model: str = "ai/llama3.2"  # Or ai/qwen3, ai/gemma3
    temperature: float = 0.7
    # Requires: Docker Desktop 4.40+ with Model Runner enabled
    # Enable: docker desktop enable model-runner --tcp 12434
    # Pull:   docker model pull ai/llama3.2

# Ollama (FREE, local)
@dataclass
class OllamaConfig:
    llm_provider: str = "ollama"
    model: str = "llama3.2:1b"
    temperature: float = 0.7
    # Requires: ollama serve, ollama pull llama3.2:1b

# Google Gemini (Cloud, multimodal)
@dataclass
class GoogleConfig:
    llm_provider: str = "google"
    model: str = "gemini-2.0-flash"  # Or gemini-1.5-pro, gemini-1.5-flash
    temperature: float = 0.7
    # Requires: GOOGLE_API_KEY or GEMINI_API_KEY
    # Features: Vision, embeddings (text-embedding-004), tool calling
```

**Docker Model Runner Tool Calling**:
Tool calling is model-dependent. Supported models: `ai/qwen3`, `ai/llama3.3`, `ai/gemma3`.

```python
from kaizen.nodes.ai import DockerModelRunnerProvider

provider = DockerModelRunnerProvider()
if provider.supports_tools("ai/qwen3"):  # Check before using tools
    response = provider.chat(messages, model="ai/qwen3", tools=tools)
```

**Google Gemini Provider**:
Supports chat, vision (multimodal), embeddings, and tool calling via the `google-genai` SDK.

```python
from kaizen.nodes.ai import GoogleGeminiProvider

provider = GoogleGeminiProvider()

# Chat completion
messages = [{"role": "user", "content": "What is 2+2?"}]
response = provider.chat(
    messages=messages,
    model="gemini-2.0-flash",
    generation_config={"temperature": 0.7, "max_tokens": 100}
)
print(response["content"])  # "4"

# Vision (multimodal) - pass base64-encoded images
import base64
with open("image.png", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

messages = [{
    "role": "user",
    "content": [
        {"type": "text", "text": "What's in this image?"},
        {"type": "image", "base64": image_b64, "media_type": "image/png"}
    ]
}]
response = provider.chat(messages=messages, model="gemini-2.0-flash")

# Embeddings
texts = ["Hello world", "Machine learning"]
embeddings = provider.embed(texts=texts, model="text-embedding-004")
# Returns: List of 768-dimensional vectors

# Async support
response = await provider.chat_async(messages=messages, model="gemini-2.0-flash")
embeddings = await provider.embed_async(texts=texts, model="text-embedding-004")
```

**Reference**: `kaizen.config.providers`, `kaizen.nodes.ai.ai_providers`

## Essential Patterns

> **Note**: For basic patterns (BaseAgent setup, signatures, simple workflows), see the [Kaizen Skills](../../skills/04-kaizen/) - 22 Skills covering common operations.

This section focuses on **enterprise AI architecture** and **advanced agent patterns**.

### Autonomous Tool Calling (v0.2.0 - Production Ready)

**12 Builtin Tools**: File (5), HTTP (4), Bash (1), Web (2)
- `read_file`, `write_file`, `delete_file`, `list_directory`, `file_exists`
- `http_get`, `http_post`, `http_put`, `http_delete`
- `bash_command`
- `fetch_url`, `extract_links`

**Danger-Level Approval Workflows**: SAFE (auto-approved) → LOW → MEDIUM → HIGH → CRITICAL

**MCP Auto-Connect**: All BaseAgent-derived agents automatically connect to kaizen_builtin MCP server
- ✅ 12 Builtin Tools: File operations, HTTP requests, bash commands, web search
- ✅ 3 Autonomous: ReActAgent, RAGResearchAgent, CodeGenerationAgent
- ✅ 12 Single-Shot Specialized: SimpleQA, ChainOfThought, StreamingChat, SelfReflection, VisionAgent, TranscriptionAgent, MultiModalAgent, ResilientAgent, MemoryAgent, BatchProcessingAgent, HumanApprovalAgent, SupervisorAgent, CoordinatorAgent
- ✅ 6 Coordination: ProponentAgent, OpponentAgent, JudgeAgent, ProposerAgent, VoterAgent, AggregatorAgent
- ✅ 4 Sequential/Handoff: SequentialAgent, HandoffAgent patterns

```python
from kaizen.core.base_agent import BaseAgent

# MCP auto-connect - tools available automatically
agent = BaseAgent(
    config=config,
    signature=signature,
    # Optional: Add custom MCP servers
    mcp_servers=[
        {
            "name": "filesystem",
            "transport": "stdio",
            "command": "npx",
            "args": ["@modelcontextprotocol/server-filesystem", "/data"]
        }
    ]
)

# Discover available tools from MCP servers
tools = await agent.discover_mcp_tools()
# Returns: [
#   {"name": "mcp__kaizen_builtin__read_file", ...},
#   {"name": "mcp__kaizen_builtin__write_file", ...},
#   {"name": "mcp__filesystem__read_file", ...},
# ]

# Execute MCP tool with approval workflow
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__write_file",
    {"path": "/tmp/output.txt", "content": "data"}
)
```

**Key Features**:
- MCP auto-connect to kaizen_builtin server (12 tools)
- Custom MCP servers via `mcp_servers` parameter
- **Automatic workflow integration** - tools automatically exposed to LLM (v0.6.0+)
- Control Protocol integration for approval workflows
- Universal MCP integration across all 25 agents

**Automatic Tool Discovery (v0.6.0+)**:
When creating a BaseAgent, MCP tools are automatically discovered and passed to the LLM during workflow generation. No manual configuration required.

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig

# Step 1: Create agent with MCP servers
agent = BaseAgent(
    config=BaseAgentConfig(llm_provider="openai", model="gpt-4o-mini"),
    signature=YourSignature(),
    mcp_servers=[{
        "name": "filesystem",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-filesystem", "/data"]
    }]
)

# Step 2: Run agent - tools automatically available to LLM
result = await agent.run(question="Read /data/file.txt")
```

**How It Works**:
1. **Initialization**: BaseAgent passes itself to WorkflowGenerator (base_agent.py:354-360)
2. **Discovery**: WorkflowGenerator calls `agent.discover_mcp_tools()` (workflow_generator.py:210-252)
3. **Conversion**: Tools converted to provider format via `tool_formatters.py`
4. **Integration**: Tools passed to LLMAgentNode via `node_config["tools"]`

**Provider Support**:
- OpenAI: Full support (function calling format)
- Anthropic: Full support (tool use format)
- Ollama: Partial support (provider-dependent)

**Tool Format Conversion** (src/kaizen/core/tool_formatters.py):
```python
from kaizen.core.tool_formatters import get_tools_for_provider

# MCP format from agent.discover_mcp_tools()
mcp_tools = [{"name": "mcp__filesystem__read_file", "description": "...", "inputSchema": {...}}]

# Automatically converted to provider format
openai_tools = get_tools_for_provider(mcp_tools, "openai")
# Returns: [{"type": "function", "function": {"name": "...", "parameters": {...}}}]

anthropic_tools = get_tools_for_provider(mcp_tools, "anthropic")
# Returns: [{"name": "...", "description": "...", "input_schema": {...}}]
```

**Benefits**:
- Zero-configuration tool exposure
- Provider-agnostic (automatic format conversion)
- Type-safe (schema validation via MCP inputSchema)
- Extensible (custom MCP servers supported)

**Reference**: `docs/features/baseagent-tool-integration.md`, ADR-012, ADR-016, `examples/autonomy/tools/`, `src/kaizen/core/tool_formatters.py`, `src/kaizen/core/workflow_generator.py:210-252`

### Control Protocol (v0.2.0 - Bidirectional Communication)

**4 Transports**: CLI, HTTP/SSE, stdio, memory
**3 BaseAgent Methods**: `ask_user_question()`, `request_approval()`, `report_progress()`

```python
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import MemoryTransport

# Setup bidirectional communication
transport = MemoryTransport()
await transport.connect()
protocol = ControlProtocol(transport)

agent = BaseAgent(
    config=config,
    signature=signature,
    control_protocol=protocol  # Enable bidirectional communication
)

# Agent can now interact with client
answer = await agent.ask_user_question(
    question="Which approach?",
    options=["Fast", "Accurate", "Balanced"]
)

approved = await agent.request_approval(
    action="delete_file",
    details={"path": "/important/file.txt"}
)

await agent.report_progress(
    message="Processing batch 3/10",
    percentage=30.0
)
```

**Key Features**:
- Real-time messaging <20ms latency (p95)
- Request/response pairing with timeouts
- Async-first design for non-blocking operation

**Reference**: ADR-011, `docs/autonomy/control-protocol.md`, `examples/autonomy/`

### Observability & Monitoring (Production-Ready)

> **See Skill**: [`kaizen-observability`](../../skills/04-kaizen/kaizen-observability.md) for comprehensive patterns and setup.

**⚠️ IMPORTANT: Observability is OPT-IN**
- Disabled by default - agents work perfectly without it
- Enable via `agent.enable_observability()` when you need monitoring
- Zero performance overhead when disabled
- 100% backward compatible

**What You Get:**
- **Distributed Tracing**: OpenTelemetry + Jaeger integration with automatic span creation
- **Metrics Collection**: Prometheus-compatible metrics (counters, gauges, histograms with percentiles)
- **Structured Logging**: JSON-formatted logs for ELK Stack integration
- **Audit Trails**: Immutable JSONL logs for compliance (SOC2, GDPR, HIPAA, PCI-DSS)
- **Unified Manager**: Single interface for all observability subsystems

**How to Enable:**

```python
from kaizen.core.base_agent import BaseAgent

# Create agent (works perfectly without observability)
agent = BaseAgent(config=config, signature=signature)

# Enable full observability stack (opt-in)
agent.enable_observability(
    service_name="my-agent",
    enable_metrics=True,         # Prometheus metrics
    enable_logging=True,         # JSON logs
    enable_tracing=True,         # Jaeger traces
    enable_audit=True,           # Compliance audit trails
)

# All agent operations now tracked with zero overhead
result = agent.run(question="test")
```

**Span Hierarchy (Automatic)**:
```
pre_agent_loop (root span)
├── pre_tool_use:load_data
│   └── post_tool_use:load_data (actual duration)
├── pre_tool_use:analyze_data
│   └── post_tool_use:analyze_data
└── post_agent_loop (ends root)
```

**Key Capabilities**:
- Automatic parent-child span relationships
- PRE/POST event pairing for accurate timing
- Event filtering (trace only what you need)
- Multi-agent coordination tracking
- Zero overhead when disabled
- Production-validated performance

**Access Monitoring:**
- Jaeger UI: `http://localhost:16686` (traces)
- Prometheus: `http://localhost:9090` (metrics)
- Grafana: `http://localhost:3000` (dashboards)
- Kibana: `http://localhost:5601` (logs)

**Reference**: `docs/observability/`, `examples/autonomy/observability/`, ADR-017

### Lifecycle Infrastructure (Hooks, State, Interrupts)

**Production-Ready Systems** for agent lifecycle management, state persistence, and execution control.

#### Hooks System (Zero-Code-Change Observability)

**What**: Lifecycle event framework for zero-code-change integration of cross-cutting concerns like monitoring, tracing, auditing, and metrics collection. Enables instrumentation without modifying agent logic.

**When**: Need to monitor, audit, debug, enforce policies, or collect analytics without changing agent code.

**How**: Register hooks that execute on lifecycle events (PRE/POST patterns). Pass `hook_manager` parameter to BaseAgent.

**Key Benefits**:
- ✅ **Zero code changes** - Add observability without modifying agent logic
- ✅ **Composable** - Mix and match multiple hooks
- ✅ **Production-ready** - Enterprise features (tracing, metrics, auditing)
- ✅ **High performance** - <0.01ms overhead (p95), <0.56KB memory per hook
- ✅ **100+ concurrent hooks** - Performance validated

#### Hook Events

| Event | When Triggered | Use Case |
|-------|----------------|----------|
| `PRE_AGENT_LOOP` | Before agent processes request | Input validation, tracing start |
| `POST_AGENT_LOOP` | After agent completes | Metrics collection, tracing end |
| `PRE_TOOL_USE` | Before agent calls a tool | Tool usage auditing |
| `POST_TOOL_USE` | After tool execution | Tool performance tracking |

#### Basic Hook Usage

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import (
    HookEvent,
    HookContext,
    HookResult,
    HookPriority,
)

# 1. Create hook function
async def my_hook(context: HookContext) -> HookResult:
    print(f"Agent {context.agent_id} is executing!")
    return HookResult(success=True)

# 2. Register hook
hook_manager = HookManager()
hook_manager.register(
    HookEvent.PRE_AGENT_LOOP,
    my_hook,
    HookPriority.NORMAL
)

# 3. Attach to agent
agent = BaseAgent(
    config=my_config,
    signature=my_signature,
    hook_manager=hook_manager  # ← Hooks enabled
)

# 4. Run agent (hooks execute automatically)
result = agent.run(question="What is AI?")
```

#### Production Hook Examples

**Distributed Tracing (OpenTelemetry)**:
```python
class DistributedTracingHook:
    """Integrate OpenTelemetry tracing."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.active_spans = {}

    async def start_span(self, context: HookContext) -> HookResult:
        from opentelemetry import trace
        tracer = trace.get_tracer(self.service_name)
        span = tracer.start_span(f"agent.{context.agent_id}.loop")
        self.active_spans[context.trace_id] = span
        return HookResult(success=True, data={"span_started": True})

    async def end_span(self, context: HookContext) -> HookResult:
        span = self.active_spans.pop(context.trace_id)
        span.set_attribute("agent.id", context.agent_id)
        span.end()
        return HookResult(success=True, data={"span_ended": True})

# Usage
tracing_hook = DistributedTracingHook("my-agent-service")
hook_manager.register(HookEvent.PRE_AGENT_LOOP, tracing_hook.start_span, HookPriority.HIGH)
hook_manager.register(HookEvent.POST_AGENT_LOOP, tracing_hook.end_span, HookPriority.HIGH)
```

**Prometheus Metrics**:
```python
class PrometheusMetricsHook:
    """Collect Prometheus metrics."""

    def __init__(self):
        from prometheus_client import Counter, Histogram

        self.loop_duration = Histogram(
            'agent_loop_duration_seconds',
            'Agent loop duration',
            ['agent_id']
        )
        self.loop_total = Counter(
            'agent_loop_total',
            'Total agent loops',
            ['agent_id']
        )
        self.loop_start_times = {}

    async def record_start(self, context: HookContext) -> HookResult:
        import time
        self.loop_start_times[context.trace_id] = time.time()
        self.loop_total.labels(agent_id=context.agent_id).inc()
        return HookResult(success=True)

    async def record_end(self, context: HookContext) -> HookResult:
        import time
        duration = time.time() - self.loop_start_times.pop(context.trace_id)
        self.loop_duration.labels(agent_id=context.agent_id).observe(duration)
        return HookResult(success=True, data={"duration": duration})

# Usage
metrics_hook = PrometheusMetricsHook()
hook_manager.register(HookEvent.PRE_AGENT_LOOP, metrics_hook.record_start)
hook_manager.register(HookEvent.POST_AGENT_LOOP, metrics_hook.record_end)
```

**Audit Trail (Compliance - SOC2/GDPR/HIPAA)**:
```python
class AuditTrailHook:
    """Immutable audit trail for compliance."""

    def __init__(self, audit_log_path: Path):
        self.audit_log_path = audit_log_path
        self.loop_start_times = {}

    async def record_start(self, context: HookContext) -> HookResult:
        import time
        self.loop_start_times[context.trace_id] = time.time()

        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "AGENT_LOOP_START",
            "agent_id": context.agent_id,
            "trace_id": context.trace_id,
            "action": "agent_execution_start",
            "inputs": context.data.get("inputs", {}),
        }

        # Append-only (immutable)
        with open(self.audit_log_path, "a") as f:
            json.dump(entry, f)
            f.write("\n")

        return HookResult(success=True, data={"audit_recorded": True})

# Usage
audit_hook = AuditTrailHook(Path("/var/log/kaizen/audit.jsonl"))
hook_manager.register(HookEvent.PRE_AGENT_LOOP, audit_hook.record_start, HookPriority.HIGHEST)
hook_manager.register(HookEvent.POST_AGENT_LOOP, audit_hook.record_end, HookPriority.HIGHEST)
```

#### Custom Hook Classes

Create reusable hook classes with `BaseHook`:

```python
from kaizen.core.autonomy.hooks.protocol import BaseHook

class LoggingHook(BaseHook):
    """Reusable logging hook."""

    events = [HookEvent.PRE_AGENT_LOOP, HookEvent.POST_AGENT_LOOP]
    priority = HookPriority.NORMAL

    def __init__(self, logger_name: str):
        super().__init__(name="logging_hook")
        self.logger = logging.getLogger(logger_name)

    async def handle(self, context: HookContext) -> HookResult:
        if context.event_type == HookEvent.PRE_AGENT_LOOP:
            self.logger.info(f"Agent {context.agent_id} starting")
        else:
            self.logger.info(f"Agent {context.agent_id} completed")

        return HookResult(success=True)

# Usage (register for all events automatically)
logging_hook = LoggingHook("my_agent")
hook_manager.register_hook(logging_hook)  # ← Registers for both events
```

#### Hook Priority

Controls execution order when multiple hooks exist for the same event:

- `HIGHEST = 0` - Runs first (e.g., audit trails, authentication)
- `HIGH = 1` - Security, compliance hooks
- `NORMAL = 2` - Default priority
- `LOW = 3` - Cleanup, optional logging
- `LOWEST = 4` - Runs last

#### Performance Characteristics

The Hooks System is designed for production use with minimal overhead:

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Hook execution overhead (p95) | <5ms | 0.008ms | ✅ **625x better** |
| Registration overhead | <1ms | 0.038ms | ✅ **26x better** |
| Stats tracking overhead | <0.1ms | ~0ms | ✅ Negligible |
| Concurrent hooks supported | >50 | 100+ | ✅ Validated |
| Memory per hook | <100KB | 0.56KB | ✅ **178x better** |

**Performance validated**: 8 performance benchmarks in `tests/performance/test_hooks_performance.py`

#### Key Patterns

- **PRE hooks** can block execution by returning `success=False`
- **POST hooks** receive execution results in `context.data`
- **Hook execution** is async-first
- **Hooks run** in priority order (HIGHEST → LOWEST)
- **Error isolation** - One hook's failure doesn't affect others
- **Timeout protection** - Default 5s timeout per hook

**Reference**: `docs/features/hooks-system.md`, `examples/autonomy/hooks/`, `tests/unit/core/autonomy/hooks/`

#### State Management

**What**: Persistent agent state with checkpointing and recovery
**When**: Need to persist conversation history, cache results, or resume interrupted workflows
**How**: Use StateManager with pluggable storage backends

```python
from kaizen.core.autonomy.state import StateManager, FilesystemStorage, AgentState

# Create state manager
storage = FilesystemStorage(base_path="./agent_state")
state_manager = StateManager(storage_backend=storage)

# Save state
state = AgentState(
    agent_id="my_agent",
    conversation_history=["Q1", "A1", "Q2", "A2"],
    metadata={"session_id": "123", "user": "alice"}
)
await state_manager.save_state(state)

# Load state
loaded_state = await state_manager.load_state("my_agent")

# Create checkpoint
checkpoint_id = await state_manager.create_checkpoint(
    agent_id="my_agent",
    description="Before risky operation"
)

# Restore from checkpoint
await state_manager.restore_checkpoint(checkpoint_id)
```

**Features**:
- **Automatic Checkpointing**: Create snapshots before risky operations
- **Version History**: Track state changes over time
- **Storage Backends**: Filesystem (default), Redis, PostgreSQL, S3
- **Metadata**: Attach arbitrary metadata to states
- **TTL Support**: Automatic state expiration

**Use Cases**:
- Long-running agent workflows (resume after interruption)
- Conversation history persistence
- Result caching across sessions
- A/B testing (checkpoint, try variant, restore)
- Audit trails (track all state mutations)

#### Checkpoint & Resume System

**What**: Automatic checkpointing and resume for autonomous agents
**When**: Need long-running agents to recover from failures or interruptions
**How**: Configure automatic checkpointing with optional compression and retention policies

```python
from kaizen.agents.autonomous.base import BaseAutonomousAgent, AutonomousConfig
from kaizen.core.autonomy.state.storage import FilesystemStorage
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.signatures import Signature, InputField, OutputField

class TaskSignature(Signature):
    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result")

# Configure with automatic checkpointing
config = AutonomousConfig(
    max_cycles=10,
    checkpoint_frequency=5,  # Save every 5 steps
    resume_from_checkpoint=True,  # Resume on restart
    llm_provider="ollama",
    model="llama3.2",
)

# Create agent with state manager
storage = FilesystemStorage(
    base_dir=".kaizen/checkpoints",
    compress=True  # Enable gzip compression (>50% size reduction)
)
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=5,
    retention_count=10  # Keep only latest 10 checkpoints
)

agent = BaseAutonomousAgent(
    config=config,
    signature=TaskSignature(),
    state_manager=state_manager,
)

# Run with automatic checkpointing and resume
result = await agent._autonomous_loop("Perform a complex task")
```

**Features**:
- **Automatic Checkpointing**: Save state every N steps or M seconds
- **Seamless Resume**: Continue execution from last checkpoint
- **JSONL Compression**: Reduce checkpoint size by >50% with gzip
- **Retention Policy**: Automatically clean up old checkpoints
- **Hook Integration**: PRE/POST checkpoint hooks (PRE_CHECKPOINT_SAVE, POST_CHECKPOINT_SAVE)
- **Error Recovery**: Resume after failures or interruptions
- **Zero Configuration**: Works out-of-the-box with sensible defaults

**Checkpoint Triggers**:
- Frequency-based: `checkpoint_frequency=5` (every 5 steps)
- Interval-based: `checkpoint_interval_seconds=30.0` (every 30 seconds)
- Hybrid (OR logic): Both triggers active simultaneously

**Storage Optimization**:
- Compression: Enable with `compress=True` (>50% size reduction, <10ms overhead)
- Retention: Keep latest N checkpoints with `retention_count=10`
- Auto-cleanup: Oldest checkpoints deleted automatically

**Use Cases**:
- Long-running autonomous agents (30+ hour sessions)
- Resume after system failures or interruptions
- Development testing with quick iteration cycles
- Production agents with automatic recovery
- Cost optimization by avoiding repeated work

**Reference**: `docs/features/checkpoint-resume-system.md`, `src/kaizen/agents/autonomous/base.py:192` (state capture/restore), `tests/unit/agents/autonomous/test_auto_checkpoint.py` (114 tests passing)

#### Interrupt System (v0.6.0 - Complete Implementation)

**What**: Production-ready graceful shutdown with checkpoint preservation
**When**: Need Ctrl+C handling, timeout/budget auto-stop, or coordinated multi-agent shutdown
**How**: Complete interrupt mechanism with 3 sources, 2 modes, and automatic checkpoint preservation

**🆕 v0.6.0 Features**:
- ✅ **Complete Implementation**: 3 interrupt sources (USER, SYSTEM, PROGRAMMATIC)
- ✅ **2 Shutdown Modes**: GRACEFUL (finish cycle + checkpoint) vs IMMEDIATE (stop now)
- ✅ **Checkpoint Preservation**: Automatically saves state on interrupt for recovery
- ✅ **Signal Propagation**: Parent agents interrupt children automatically
- ✅ **Hook Integration**: PRE/POST_INTERRUPT hooks for custom handling
- ✅ **34 E2E Tests**: Production-validated for autonomous workloads

**Basic Usage**:
```python
from kaizen.agents.autonomous.base import BaseAutonomousAgent
from kaizen.agents.autonomous.config import AutonomousConfig
from kaizen.core.autonomy.interrupts.handlers import TimeoutInterruptHandler

# Enable interrupts in config
config = AutonomousConfig(
    llm_provider="ollama",
    model="llama3.2:1b",
    enable_interrupts=True,              # Enable interrupt handling
    graceful_shutdown_timeout=5.0,       # Max time for graceful shutdown
    checkpoint_on_interrupt=True         # Save checkpoint before exit
)

# Create agent with interrupt support
agent = BaseAutonomousAgent(config=config, signature=MySignature())

# Add timeout handler (auto-stop after 30s)
timeout_handler = TimeoutInterruptHandler(timeout_seconds=30.0)
agent.interrupt_manager.add_handler(timeout_handler)

# Run agent - gracefully handles Ctrl+C, timeouts, budget limits
try:
    result = await agent.run_autonomous(task="Analyze data")
except InterruptedError as e:
    print(f"Agent interrupted: {e.reason.message}")
    checkpoint_id = e.reason.metadata.get("checkpoint_id")
    # Resume from checkpoint in next run
```

**3 Interrupt Sources**:
- **USER**: Ctrl+C (SIGINT), manual interrupts via Control Protocol
- **SYSTEM**: Timeout handlers, budget handlers, resource limits
- **PROGRAMMATIC**: API calls, hook triggers, parent propagation

**2 Shutdown Modes**:
- **GRACEFUL** (default): Finish current cycle → Save checkpoint → Exit cleanly
- **IMMEDIATE**: Stop as soon as possible (best effort, may lose cycle work)

**Interrupt Handlers** (Built-in):
```python
from kaizen.core.autonomy.interrupts.handlers import (
    TimeoutInterruptHandler,  # Auto-stop after timeout
    BudgetInterruptHandler,   # Auto-stop when cost limit exceeded
    SignalInterruptHandler    # Handle SIGINT/SIGTERM
)

# Timeout handler (30 seconds)
timeout = TimeoutInterruptHandler(timeout_seconds=30.0)
agent.interrupt_manager.add_handler(timeout)

# Budget handler ($0.10 limit)
budget = BudgetInterruptHandler(max_cost=0.10)
agent.interrupt_manager.add_handler(budget)

# Signal handler (Ctrl+C)
signal_handler = SignalInterruptHandler()
agent.interrupt_manager.add_handler(signal_handler)
```

**Checkpoint Preservation**:
```python
# Interrupts automatically save checkpoint with metadata
result = await agent.run_autonomous(task="Long task")

if result.get("status") == "interrupted":
    checkpoint_id = result["checkpoint_id"]
    reason = result["interrupt_reason"]

    # Resume from checkpoint
    agent_resumed = BaseAutonomousAgent(config=config, signature=MySignature())
    result = await agent_resumed.run_autonomous(
        task="Long task",
        resume_from_checkpoint=checkpoint_id
    )
```

**Multi-Agent Propagation**:
```python
# Parent interrupt propagates to all children
parent = SupervisorAgent(config)
child1 = WorkerAgent(config)
child2 = WorkerAgent(config)

parent.interrupt_manager.add_child(child1.interrupt_manager)
parent.interrupt_manager.add_child(child2.interrupt_manager)

# When parent interrupted, children also stop
parent.interrupt_manager.request_interrupt(
    source=InterruptSource.USER,
    mode=InterruptMode.GRACEFUL,
    reason="User requested shutdown"
)
# child1 and child2 also receive interrupt signal
```

**Hook Integration** (Custom Interrupt Handling):
```python
from kaizen.core.autonomy.hooks import HookEvent, HookContext, HookResult

async def pre_interrupt_hook(context: HookContext) -> HookResult:
    """Custom logic before interrupt"""
    print(f"⚠️  Interrupt triggered: {context.data.get('reason')}")
    # Send notification, log to monitoring, etc.
    return HookResult(success=True)

async def post_interrupt_hook(context: HookContext) -> HookResult:
    """Custom logic after interrupt"""
    checkpoint_id = context.data.get("checkpoint_id")
    print(f"✅ Checkpoint saved: {checkpoint_id}")
    return HookResult(success=True)

# Register hooks
hook_manager.register(HookEvent.PRE_INTERRUPT, pre_interrupt_hook)
hook_manager.register(HookEvent.POST_INTERRUPT, post_interrupt_hook)
```

**Key Features**:
- Interrupts are **cooperative** (agent checks at cycle boundaries)
- **Non-blocking**: `request_interrupt()` sets flag, doesn't stop immediately
- **Thread-safe**: Safe for concurrent multi-agent systems
- **Resume-aware**: Checkpoints include interrupt metadata for intelligent resume
- **Signal-safe**: Properly handles SIGINT/SIGTERM for clean process termination

**Examples**:
- `examples/autonomy/interrupts/01_ctrl_c_interrupt.py` - Ctrl+C handling
- `examples/autonomy/interrupts/02_timeout_interrupt.py` - Timeout auto-stop
- `examples/autonomy/interrupts/03_budget_interrupt.py` - Budget limit auto-stop

**Reference**:
- `src/kaizen/core/autonomy/interrupts/` - Complete implementation
- `tests/e2e/autonomy/test_interrupt_mechanism.py` - 34 E2E tests
- `docs/guides/interrupt-mechanism-guide.md` - Complete guide
- ADR-016 - Architecture decision record

#### Integration Example

**Complete Lifecycle Management**:
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.hooks.builtin import LoggingHook, MetricsHook
from kaizen.core.autonomy.state import StateManager, FilesystemStorage
from kaizen.core.autonomy.interrupts import InterruptSignal

class ProductionAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=MySignature())

        # Enable lifecycle infrastructure
        self._setup_hooks()
        self._setup_state()
        self._setup_interrupts()

    def _setup_hooks(self):
        """Register builtin hooks for monitoring"""
        self._hook_manager.register_hook(LoggingHook(log_level="INFO"))
        self._hook_manager.register_hook(MetricsHook())

    def _setup_state(self):
        """Configure state persistence"""
        storage = FilesystemStorage(base_path=f"./state/{self.agent_id}")
        self.state_manager = StateManager(storage_backend=storage)

    def _setup_interrupts(self):
        """Setup interrupt handlers"""
        @self._interrupt_manager.on_signal(InterruptSignal.BUDGET_EXCEEDED)
        async def handle_budget(data):
            # Save state and notify user
            await self.state_manager.save_state(self.get_current_state())
            await self.ask_user_question(
                question="Budget exceeded. Continue?",
                options=["Yes", "No"]
            )

    async def process_with_safety(self, input_data):
        """Process with full lifecycle management"""
        # Create checkpoint before risky operation
        checkpoint_id = await self.state_manager.create_checkpoint(
            agent_id=self.agent_id,
            description="Before processing"
        )

        try:
            # Process (hooks automatically log/monitor)
            result = self.run(input_data=input_data)

            # Save successful state
            await self.state_manager.save_state(
                AgentState(
                    agent_id=self.agent_id,
                    conversation_history=self.get_history(),
                    metadata={"result": result}
                )
            )

            return result

        except Exception as e:
            # Restore checkpoint on error
            await self.state_manager.restore_checkpoint(checkpoint_id)
            raise
```

**Benefits of Lifecycle Infrastructure**:
- ✅ **Zero-overhead when disabled**: All systems are opt-in
- ✅ **Production-validated**: 62 tests covering hooks/state/interrupts
- ✅ **Thread-safe**: Safe for concurrent agent execution
- ✅ **Composable**: Mix and match hooks, state, interrupts as needed
- ✅ **Extensible**: Create custom hooks, storage backends, interrupt signals

**Reference**: `src/kaizen/core/autonomy/`, `tests/unit/core/autonomy/`, ADR-018 (Lifecycle Infrastructure)

### Permission System (Enterprise Security & Governance)

**Fine-grained agent permission control, budget enforcement, and security policies.**

**What**: Policy-based permission management for tool usage, API calls, and resource access
**When**: Need to enforce security policies, budget limits, or regulatory compliance for agent actions
**How**: Define permission rules with pattern matching and runtime enforcement

#### Core Components

**ExecutionContext (Thread-Safe Runtime State)**:
```python
from kaizen.core.autonomy.permissions import ExecutionContext, PermissionMode

# Create execution context
context = ExecutionContext(
    mode=PermissionMode.DEFAULT,  # Standard permission checks
    budget_limit=100.0,           # Maximum cost allowed
    allowed_tools={"read_file", "http_get"},  # Whitelist
    denied_tools={"delete_file", "bash_command"}  # Blacklist
)

# Check tool permission
if context.can_use_tool("read_file"):
    # Execute tool
    context.record_tool_usage("read_file", cost=0.001)

# Check budget
if context.has_budget():
    # Proceed with operation
    pass
else:
    raise BudgetExceededError("Cost limit reached")
```

**Permission Modes**:
- `DEFAULT`: Standard permission checks (production)
- `ACCEPT_EDITS`: Auto-approve edit operations (development)
- `PLAN`: Planning mode, no execution (dry-run)
- `BYPASS`: Bypass all checks (admin mode - use with caution!)

**PermissionRule (Pattern-Based Access Control)**:
```python
from kaizen.core.autonomy.permissions import PermissionRule, PermissionType

# Allow all read operations
read_rule = PermissionRule(
    pattern="read_.*",  # Regex pattern
    permission_type=PermissionType.ALLOW,
    reason="Read operations are safe",
    priority=10  # Higher priority = evaluated first
)

# Deny all delete operations
delete_rule = PermissionRule(
    pattern="delete_.*",
    permission_type=PermissionType.DENY,
    reason="Delete operations require manual approval",
    priority=20
)

# Ask user for HTTP POST operations
http_post_rule = PermissionRule(
    pattern="http_post",
    permission_type=PermissionType.ASK,
    reason="HTTP POST can modify external systems",
    priority=15,
    conditions={"requires_ssl": True}  # Optional conditions
)

# Check if tool matches rule
if read_rule.matches("read_file"):
    # Tool is allowed
    pass
```

**PermissionType Decision Types**:
- `ALLOW`: Auto-approve execution (no user prompt)
- `DENY`: Block execution completely
- `ASK`: Request user approval before execution

#### Usage Patterns

**Basic Permission Enforcement**:
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.permissions import ExecutionContext, PermissionRule, PermissionType

class SecureAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=MySignature())
        self._setup_permissions()

    def _setup_permissions(self):
        """Configure permission policies"""
        # Create execution context with budget
        self.exec_context = ExecutionContext(
            mode=PermissionMode.DEFAULT,
            budget_limit=50.0  # $50 maximum
        )

        # Define permission rules
        self.rules = [
            # High priority: Deny destructive operations
            PermissionRule(
                pattern="(delete|drop|truncate)_.*",
                permission_type=PermissionType.DENY,
                reason="Destructive operations not allowed",
                priority=100
            ),
            # Medium priority: Ask for write operations
            PermissionRule(
                pattern="(write|create|update)_.*",
                permission_type=PermissionType.ASK,
                reason="Write operations require approval",
                priority=50
            ),
            # Low priority: Allow read operations
            PermissionRule(
                pattern="(read|get|list)_.*",
                permission_type=PermissionType.ALLOW,
                reason="Read operations are safe",
                priority=10
            )
        ]

    async def execute_with_permission(self, tool_name: str, params: dict):
        """Execute tool with permission checking"""
        # Check if tool is allowed by context
        if not self.exec_context.can_use_tool(tool_name):
            raise PermissionError(f"Tool {tool_name} is denied by context")

        # Find matching rule (highest priority first)
        matching_rule = None
        for rule in sorted(self.rules, key=lambda r: r.priority, reverse=True):
            if rule.matches(tool_name):
                matching_rule = rule
                break

        # Apply permission decision
        if matching_rule:
            if matching_rule.permission_type == PermissionType.DENY:
                raise PermissionError(f"Tool {tool_name} denied: {matching_rule.reason}")

            elif matching_rule.permission_type == PermissionType.ASK:
                # Request user approval
                approved = await self.ask_user_question(
                    question=f"Approve {tool_name}? Reason: {matching_rule.reason}",
                    options=["Yes", "No"]
                )
                if approved == "No":
                    raise PermissionError("User denied permission")

        # Check budget
        if not self.exec_context.has_budget():
            raise BudgetExceededError("Cost limit reached")

        # Execute tool
        result = await self.execute_tool(tool_name, params)

        # Record usage
        cost = self._calculate_cost(result)
        self.exec_context.record_tool_usage(tool_name, cost=cost)

        return result
```

**Budget Enforcement**:
```python
# Set budget limit
context = ExecutionContext(budget_limit=10.0)

# Record tool usage with costs
context.record_tool_usage("gpt4_call", cost=0.05)
context.record_tool_usage("gpt4_call", cost=0.04)

# Check remaining budget
print(f"Budget used: ${context.budget_used:.2f}")
print(f"Budget available: ${context.budget_limit - context.budget_used:.2f}")

# Budget check before expensive operation
if context.has_budget():
    result = expensive_operation()
else:
    raise BudgetExceededError("Insufficient budget")
```

**Multi-Agent Permission Isolation**:
```python
# Each agent gets its own execution context
agent1_context = ExecutionContext(
    budget_limit=20.0,
    allowed_tools={"read_file", "http_get"}
)

agent2_context = ExecutionContext(
    budget_limit=50.0,
    allowed_tools={"read_file", "write_file", "http_post"}
)

# Agents cannot exceed their individual budgets
agent1 = Agent1(config, exec_context=agent1_context)
agent2 = Agent2(config, exec_context=agent2_context)
```

#### Integration with Lifecycle Infrastructure

**Combine Permissions with Hooks**:
```python
from kaizen.core.autonomy.hooks import BaseHook, HookEvent, HookContext, HookResult
from kaizen.core.autonomy.permissions import ExecutionContext, PermissionRule, PermissionType

class PermissionHook(BaseHook):
    """Hook that enforces permissions on tool usage"""

    def __init__(self, exec_context: ExecutionContext, rules: list[PermissionRule]):
        self.exec_context = exec_context
        self.rules = sorted(rules, key=lambda r: r.priority, reverse=True)

    def supported_events(self) -> list[HookEvent]:
        return [HookEvent.PRE_TOOL_USE]

    async def handle(self, context: HookContext) -> HookResult:
        tool_name = context.data.get("tool_name")

        # Check context permissions
        if not self.exec_context.can_use_tool(tool_name):
            return HookResult(
                success=False,
                error=f"Tool {tool_name} denied by execution context"
            )

        # Check budget
        if not self.exec_context.has_budget():
            return HookResult(
                success=False,
                error="Budget limit exceeded"
            )

        # Apply permission rules
        for rule in self.rules:
            if rule.matches(tool_name):
                if rule.permission_type == PermissionType.DENY:
                    return HookResult(
                        success=False,
                        error=f"Denied by policy: {rule.reason}"
                    )
                break

        return HookResult(success=True)

# Register permission hook
agent._hook_manager.register_hook(
    PermissionHook(exec_context, permission_rules)
)
```

**Combine Permissions with State Management**:
```python
# Save permission state for audit/recovery
state = AgentState(
    agent_id="secure_agent",
    conversation_history=[],
    metadata={
        "budget_used": exec_context.budget_used,
        "budget_limit": exec_context.budget_limit,
        "tools_used": exec_context.tool_usage_count,
        "denied_tools": list(exec_context.denied_tools)
    }
)
await state_manager.save_state(state)
```

#### Advanced Patterns

**Conditional Permissions Based on Context**:
```python
# Allow HTTP POST only to approved domains
http_rule = PermissionRule(
    pattern="http_post",
    permission_type=PermissionType.ALLOW,
    reason="POST allowed to approved domains",
    priority=50,
    conditions={
        "approved_domains": ["api.example.com", "internal.company.com"]
    }
)

# Custom validation logic
def validate_http_post(tool_params, conditions):
    url = tool_params.get("url", "")
    approved = conditions.get("approved_domains", [])
    return any(domain in url for domain in approved)
```

**Time-Based Permissions**:
```python
import datetime

class TimeBasedPermissionRule(PermissionRule):
    """Permission rule with time restrictions"""

    def __init__(self, pattern, permission_type, reason,
                 allowed_hours=None, priority=0):
        super().__init__(pattern, permission_type, reason, priority)
        self.allowed_hours = allowed_hours or range(9, 17)  # 9 AM - 5 PM

    def is_time_allowed(self) -> bool:
        current_hour = datetime.datetime.now().hour
        return current_hour in self.allowed_hours

# Only allow expensive operations during business hours
expensive_rule = TimeBasedPermissionRule(
    pattern="gpt4_.*",
    permission_type=PermissionType.ALLOW,
    reason="GPT-4 calls only during business hours",
    allowed_hours=range(9, 17),
    priority=100
)
```

#### Benefits & Use Cases

**Security Benefits**:
- ✅ **Least Privilege**: Grant minimum necessary permissions
- ✅ **Defense in Depth**: Multiple layers (context + rules + hooks)
- ✅ **Audit Trail**: Track all permission decisions and tool usage
- ✅ **Budget Protection**: Prevent runaway costs
- ✅ **Compliance**: Meet regulatory requirements (SOC2, HIPAA, PCI-DSS)

**Use Cases**:
- **Multi-Tenant SaaS**: Isolate customer permissions
- **Enterprise Deployment**: Enforce corporate security policies
- **Cost Control**: Prevent budget overruns on expensive APIs
- **Regulatory Compliance**: Audit trail for all agent actions
- **Development vs Production**: Different permission profiles per environment

**Reference**: `src/kaizen/core/autonomy/permissions/`, `tests/unit/core/autonomy/permissions/`, ADR-019 (Permission System)

### Pipeline Patterns & Orchestration (Production-Ready)

**9 composable pipeline patterns for multi-agent coordination with A2A-based agent discovery.**

**What**: Pre-built patterns for common multi-agent coordination scenarios
**When**: Need to coordinate multiple agents for complex tasks requiring diverse perspectives or specialized skills
**How**: Use `Pipeline` factory methods for instant pattern creation with A2A semantic matching

#### Multi-Runtime Orchestration Scaling (Enterprise)

**Scaling Decision Tree** for distributed multi-agent systems:

```
Agent Count         | Deployment          | Use
-------------------|---------------------|------------------------------------------
< 10 agents        | Single process      | Basic multi-agent patterns (see Skills)
10-100 agents      | Single process      | OrchestrationRuntime (task routing)
100+ agents        | Distributed/multi-  | AgentRegistry (capability discovery)
                   | process/multi-node  |
```

**OrchestrationRuntime (10-100 agents, single process)**:
- **Multi-agent orchestration**: Task routing with semantic, round-robin, random strategies
- **Programmatic workflow execution**: AsyncLocalRuntime integration for Core SDK workflows with level-based parallelism
- **Health monitoring**: Agent-level health checks with real LLM inference
- **Budget enforcement**: Per-agent and runtime-wide budget tracking
- Use when:
  - Task distribution across multiple agents within single runtime/process
  - Executing programmatic workflows (WorkflowBuilder) with async concurrency control

**AgentRegistry (100+ agents, distributed systems)** - **🆕 v0.6.4**:
- Multi-runtime coordination across processes/machines
- O(1) capability-based discovery with semantic matching
- Event broadcasting (6 event types for cross-runtime coordination)
- Health monitoring with automatic deregistration
- Status management (ACTIVE, UNHEALTHY, DEGRADED, OFFLINE)
- Use when: Centralized coordination across distributed deployments

**See**: [`kaizen-agent-registry`](../../skills/04-kaizen/kaizen-agent-registry.md) skill for AgentRegistry patterns, configuration, and distributed coordination examples.

**Integration Pattern** (use both together):
```python
from kaizen.orchestration import OrchestrationRuntime, AgentRegistry

# Local task routing
runtime = OrchestrationRuntime(config=runtime_config)
await runtime.register_agent(agent)

# Global agent discovery across runtimes
registry = AgentRegistry(config=registry_config)
await registry.register_agent(agent, runtime_id="runtime_1")

# Route tasks locally, discover agents globally
selected = await runtime.route_task(task)  # Within runtime
all_agents = await registry.find_agents_by_capability("code generation")  # Across runtimes
```

#### Available Patterns

**Pattern Library (9 Patterns)**:
1. **SupervisorWorkerPipeline**: Hierarchical coordination with supervisor directing specialized workers
2. **MetaControllerPipeline** (Router): Intelligent task routing to best agent via A2A matching
3. **EnsemblePipeline**: Multi-perspective collaboration with top-k A2A discovery and synthesis
4. **BlackboardPipeline**: Controller-driven iterative problem-solving with shared state
5. **ParallelPipeline**: Concurrent agent execution with result aggregation
6. **SequentialPipeline**: Linear agent chain with output passing
7. **HandoffPipeline**: Agent handoff with context transfer
8. **ConsensusPipeline**: Voting-based decision making
9. **DebatePipeline**: Adversarial deliberation with judgment

**A2A-Integrated Patterns (4)**:
- SupervisorWorkerPipeline, MetaControllerPipeline, EnsemblePipeline, BlackboardPipeline
- All support semantic capability matching for agent selection
- Graceful fallback when A2A unavailable

#### Core Pattern: Ensemble with A2A Discovery

**Multi-perspective problem solving with automatic agent selection:**

```python
from kaizen.orchestration.pipeline import Pipeline

# Create agents with diverse capabilities
code_expert = CodeAgent(config=CodeConfig())
data_expert = DataAnalyst(config=DataConfig())
writing_expert = WritingAgent(config=WritingConfig())
research_expert = ResearchAgent(config=ResearchConfig())
synthesis_agent = SynthesisAgent(config=SynthesisConfig())

# Ensemble with A2A discovery (top-3 agents)
pipeline = Pipeline.ensemble(
    agents=[code_expert, data_expert, writing_expert, research_expert],
    synthesizer=synthesis_agent,
    discovery_mode="a2a",  # Semantic capability matching
    top_k=3,               # Select top 3 agents
    error_handling="graceful"  # Continue despite individual failures
)

# Execute - A2A automatically selects best 3 agents for task
result = pipeline.run(
    task="Analyze codebase and suggest improvements",
    input="repository_path"
)

# Access synthesized result
print(result['result'])              # Unified synthesis
print(result['perspective_count'])   # Number of perspectives used
print(result['task'])                # Original task
```

**How A2A Discovery Works**:
1. Each agent generates A2A capability card (`agent.to_a2a_card()`)
2. Task requirements matched against agent capabilities
3. Top-k agents with highest capability scores selected
4. Selected agents execute in parallel or sequentially
5. Synthesizer combines perspectives into unified result

#### Pattern: Blackboard (Iterative Problem-Solving)

**Controller-driven multi-agent collaboration with shared state:**

```python
from kaizen.orchestration.pipeline import Pipeline

# Create specialized agents
problem_solver = ProblemSolverAgent(config)
data_analyzer = DataAnalyzerAgent(config)
optimizer = OptimizationAgent(config)
controller = ControllerAgent(config)  # Orchestrates agents

# Blackboard pattern
pipeline = Pipeline.blackboard(
    agents=[problem_solver, data_analyzer, optimizer],
    controller=controller,
    max_iterations=10,
    discovery_mode="a2a"  # Semantic capability-based selection
)

# Execute - controller iteratively selects agents
result = pipeline.run(
    task="Optimize database query performance",
    input="slow_query.sql"
)

# Access results
print(result['insights'])        # All agent contributions
print(result['iterations'])      # Number of iterations taken
print(result['is_complete'])     # Convergence status
```

**Blackboard Flow**:
1. **Controller** analyzes task and shared blackboard state
2. **A2A Discovery** selects agent with needed capability
3. **Agent** executes and writes insights to blackboard
4. **Controller** checks if problem is solved
5. Repeat until complete or max_iterations reached

#### Pattern: Meta-Controller (Router)

**Intelligent task routing to best-suited agent:**

```python
from kaizen.orchestration.pipeline import Pipeline

# Create diverse agents
pipeline = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic",  # A2A-based routing
    fallback_strategy="round-robin"
)

# Automatically routes to best agent
result = pipeline.run(task="Analyze sales data and create report")
# Routes to data_agent (highest capability match)
```

#### Pattern: Parallel Execution

**Concurrent agent execution for speed:**

```python
pipeline = Pipeline.parallel(
    agents=[agent1, agent2, agent3],
    aggregation_strategy="merge",  # merge, vote, or custom
    error_handling="graceful"
)

result = pipeline.run(task="Multi-perspective analysis", input=data)
```

#### Pattern Composition

**Patterns are composable - nest patterns within patterns:**

```python
# Create sub-patterns
code_pipeline = Pipeline.sequential([code_agent1, code_agent2])
data_pipeline = Pipeline.parallel([data_agent1, data_agent2, data_agent3])

# Compose into meta-pattern
meta_pipeline = Pipeline.router(
    agents=[code_pipeline, data_pipeline],  # Pipelines are agents!
    routing_strategy="semantic"
)

# Execute composed pattern
result = meta_pipeline.run(task="Complex analysis requiring code + data")
```

#### Error Handling

**Two modes: graceful (default) or fail-fast:**

```python
# Graceful: collect partial results, skip failures
pipeline = Pipeline.ensemble(
    agents=[agent1, agent2, agent3],
    synthesizer=synthesizer,
    error_handling="graceful"  # Default
)
result = pipeline.run(task="...")
# result may contain partial perspectives if some agents failed

# Fail-fast: raise exception on first error
pipeline = Pipeline.ensemble(
    agents=[agent1, agent2, agent3],
    synthesizer=synthesizer,
    error_handling="fail-fast"
)
```

#### Convert Pipeline to Agent

**All pipelines expose `.to_agent()` for recursive composition:**

```python
# Create pipeline
ensemble_pipeline = Pipeline.ensemble(
    agents=[agent1, agent2, agent3],
    synthesizer=synthesizer
)

# Convert to agent
ensemble_agent = ensemble_pipeline.to_agent(
    name="EnsembleAgent",
    description="Multi-perspective analysis agent"
)

# Use in another pipeline
meta_pipeline = Pipeline.router(
    agents=[ensemble_agent, other_agent],
    routing_strategy="semantic"
)
```

#### Performance Characteristics

**Benchmarks (4-agent ensemble)**:
- **A2A Discovery**: <50ms for top-k selection
- **Parallel Execution**: 4x speedup over sequential
- **Synthesis Overhead**: <100ms
- **Memory Usage**: <512MB per pipeline
- **Nesting Depth**: 10+ levels supported

#### Use Cases

**Ensemble Pattern**:
- Multi-perspective document analysis
- Diverse code review (architecture, security, performance)
- Comprehensive research (multiple source types)
- Balanced decision-making (multiple viewpoints)

**Blackboard Pattern**:
- Iterative problem-solving (optimization, debugging)
- Complex planning (travel, project management)
- Incremental knowledge building
- Multi-step data analysis pipelines

**Router Pattern**:
- Intelligent task delegation to specialists
- Load balancing across agents
- Capability-based routing
- Fallback workflows for reliability

**Parallel Pattern**:
- Bulk processing (batch analysis)
- Redundant execution for reliability
- Voting-based consensus
- Speed optimization for independent tasks

**Benefits**:
- ✅ **Zero Hardcoded Logic**: A2A semantic matching eliminates if/else agent selection
- ✅ **Composable**: Nest patterns within patterns for complex workflows
- ✅ **Graceful Degradation**: Continues with partial results on agent failures
- ✅ **Production-Validated**: 144 tests covering edge cases
- ✅ **A2A Integration**: Automatic capability-based agent discovery
- ✅ **Flexible Error Handling**: Graceful or fail-fast modes

**Reference**: `src/kaizen/orchestration/patterns/`, `tests/unit/orchestration/`, ADR-018, `docs/testing/pipeline-edge-case-test-matrix.md`

### Memory & Learning System (Production-Ready)

**Comprehensive memory and learning system for persistent context, pattern recognition, and continuous improvement.**

**What**: Multi-type memory with intelligent learning mechanisms for long-running agents
**When**: Need agents to remember past interactions, learn user preferences, or improve over time
**How**: Opt-in memory system with multiple storage backends and learning algorithms

#### Memory Types

**Short-Term Memory (Session-Scoped)**:
```python
from kaizen.memory import ShortTermMemory

# Create short-term memory (cleared on session end)
short_term = ShortTermMemory(
    max_entries=100,  # Keep last 100 interactions
    ttl_seconds=3600   # Expire after 1 hour
)

# Store interaction
short_term.add(
    content={"question": "What is AI?", "answer": "..."},
    importance=0.8,
    tags=["qa", "technical"]
)

# Retrieve recent memories
recent = short_term.get_recent(limit=10)
```

**Long-Term Memory (Cross-Session)**:
```python
from kaizen.memory import LongTermMemory
from kaizen.memory.storage import SQLiteStorage

# Create long-term memory with persistent storage
storage = SQLiteStorage(db_path="./agent_memory.db")
long_term = LongTermMemory(storage_backend=storage)

# Store important information
long_term.add(
    content={"user_name": "Alice", "preferences": {"style": "formal"}},
    importance=0.9,
    tags=["user_profile", "preferences"]
)

# Retrieve by similarity (semantic search)
similar = long_term.search_similar(
    query="user preferences",
    limit=5,
    min_similarity=0.7
)
```

**Semantic Memory (Concept Extraction)**:
```python
from kaizen.memory import SemanticMemory

# Create semantic memory for concept tracking
semantic = SemanticMemory(storage_backend=storage)

# Extract and store concepts
semantic.extract_concepts(
    text="The user prefers concise answers with technical depth",
    context={"session_id": "123"}
)

# Query by concept
concept_memories = semantic.get_by_concept("communication_style")
```

**SharedMemoryPool (Multi-Agent)**:
```python
from kaizen.memory.shared_memory import SharedMemoryPool

# Create shared memory for multi-agent coordination
shared_pool = SharedMemoryPool()

# Agent 1 writes insight
agent1.write_to_memory(
    content={"finding": "User needs data visualization"},
    tags=["insight", "user_need"],
    importance=0.9
)

# Agent 2 reads relevant insights
relevant_insights = agent2.read_relevant(
    query="user requirements",
    limit=10
)
```

**Persistent Buffer Memory** (v0.6.0 - Production-Ready):
```python
from kaizen.memory import PersistentBufferMemory
from dataflow import DataFlow

# Initialize DataFlow backend (automatic schema creation)
db = DataFlow(
    database_type="sqlite",
    database_config={"database": "./agent_memory.db"}
)

# Create persistent buffer memory
memory = PersistentBufferMemory(
    db=db,
    agent_id="agent_001",
    buffer_size=100,              # Keep last 100 messages in memory
    auto_persist_interval=10,     # Auto-persist every 10 messages
    enable_compression=True       # JSONL compression for storage
)

# Add conversation turns
memory.add_message(role="user", content="What is AI?")
memory.add_message(role="assistant", content="AI is artificial intelligence...")

# Retrieve conversation history
history = memory.get_history(limit=10)  # Last 10 messages

# Persist to database
memory.persist()  # Manual persist (or waits for auto_persist_interval)

# Load from database in next session
memory_loaded = PersistentBufferMemory(db=db, agent_id="agent_001")
memory_loaded.load_from_db()  # Restores conversation history
```

**🆕 v0.6.0 Features**:
- ✅ **DataFlow Backend**: Zero-config database persistence with automatic schema
- ✅ **Dual-Buffer Architecture**: In-memory buffer + database storage
- ✅ **Auto-Persist**: Configurable auto-persist interval (every N messages)
- ✅ **Compression**: JSONL compression for efficient storage
- ✅ **Multi-Instance**: Agent-specific memory isolation (agent_id scoping)
- ✅ **Cross-Session**: Load conversation history across restarts
- ✅ **Production-Validated**: 28 E2E tests with real database operations

**Key Benefits**:
- **Fast Access**: In-memory buffer for recent messages (<1ms retrieval)
- **Persistent**: Database storage survives restarts
- **Automatic**: Auto-persist prevents data loss
- **Scalable**: DataFlow handles multi-tenancy and sharding
- **Efficient**: Compression reduces storage by 60%+

**Example - Conversational Agent**:
```python
from kaizen.agents import SimpleQAAgent
from kaizen.memory import PersistentBufferMemory

class ConversationalAgent(SimpleQAAgent):
    def __init__(self, config, db):
        super().__init__(config)
        self.memory = PersistentBufferMemory(
            db=db,
            agent_id=self.agent_id,
            buffer_size=50,
            auto_persist_interval=5
        )
        # Load previous conversations
        self.memory.load_from_db()

    def ask(self, question: str) -> dict:
        # Add user message to memory
        self.memory.add_message(role="user", content=question)

        # Get conversation context
        history = self.memory.get_history(limit=10)

        # Run agent with context
        result = self.run(question=question, context=history)

        # Add assistant response to memory
        self.memory.add_message(role="assistant", content=result["answer"])

        return result

# Usage - conversation persists across sessions
agent = ConversationalAgent(config, db)
result1 = agent.ask("What is AI?")
result2 = agent.ask("Can you elaborate?")  # Uses history from previous question
```

**Reference**:
- `src/kaizen/memory/persistent_buffer.py` - Implementation
- `tests/integration/memory/test_persistent_buffer_dataflow.py` - 28 E2E tests
- `docs/guides/persistent-memory-guide.md` - Complete guide

#### Storage Backends

**SQLite (Production Local)**:
```python
from kaizen.memory.storage import SQLiteStorage

storage = SQLiteStorage(
    db_path="./memory.db",
    connection_pool_size=10,
    enable_fts=True  # Full-text search
)
```

**File-Based (JSONL)**:
```python
from kaizen.memory.storage import FileStorage

storage = FileStorage(
    directory="./memory_logs",
    compression=True,  # gzip compression
    rotation_size_mb=100  # Rotate at 100MB
)
```

**PostgreSQL (via DataFlow)**:
```python
from kaizen.memory.storage import PostgreSQLStorage

storage = PostgreSQLStorage(
    connection_string="postgresql://user:pass@localhost/memory",
    schema="agent_memory"
)
```

#### Learning Mechanisms

**Pattern Recognition (FAQ Detection)**:
```python
from kaizen.memory.learning import PatternRecognition

pattern_learner = PatternRecognition(memory=long_term)

# Detect frequently asked questions
faqs = pattern_learner.detect_frequent_patterns(
    min_occurrences=3,
    time_window_days=7
)

# Example output: [
#   {"pattern": "What is AI?", "count": 5, "confidence": 0.95},
#   {"pattern": "How does ML work?", "count": 3, "confidence": 0.87}
# ]
```

**Preference Learning (User Adaptation)**:
```python
from kaizen.memory.learning import PreferenceLearning

pref_learner = PreferenceLearning(memory=long_term)

# Learn user preferences from interactions
preferences = pref_learner.learn_preferences(
    user_id="alice",
    min_confidence=0.7
)

# Example output: {
#   "communication_style": "concise",
#   "technical_depth": "advanced",
#   "format_preference": "bullet_points"
# }

# Apply preferences to agent behavior
if preferences.get("communication_style") == "concise":
    agent.config.max_tokens = 200
```

**Error Correction (Learn from Mistakes)**:
```python
from kaizen.memory.learning import ErrorCorrection

error_learner = ErrorCorrection(memory=long_term)

# Record error
error_learner.record_error(
    error_type="invalid_tool_call",
    context={"tool": "read_file", "error": "FileNotFoundError"},
    correction="Check file existence before reading"
)

# Check if similar error occurred before
should_avoid = error_learner.should_avoid(
    action="read_file",
    context={"path": "/nonexistent/file.txt"}
)

# Get suggested correction
correction = error_learner.get_correction(
    error_type="invalid_tool_call",
    context={"tool": "read_file"}
)
```

**Adaptive Learning (Continuous Improvement)**:
```python
from kaizen.memory.learning import AdaptiveLearning

adaptive = AdaptiveLearning(
    memory=long_term,
    pattern_recognition=pattern_learner,
    preference_learning=pref_learner,
    error_correction=error_learner
)

# Consolidate all learnings
insights = adaptive.consolidate_learnings(
    user_id="alice",
    time_window_days=30
)

# Example output: {
#   "faqs": [...],
#   "preferences": {...},
#   "common_errors": [...],
#   "recommendations": [...]
# }
```

#### BaseAgent Integration

**Enable Memory for Agent**:
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.memory import LongTermMemory
from kaizen.memory.storage import SQLiteStorage

class MemoryEnabledAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=MySignature())

        # Setup memory
        storage = SQLiteStorage(db_path=f"./memory/{self.agent_id}.db")
        self.memory = LongTermMemory(storage_backend=storage)

        # Setup learning
        from kaizen.memory.learning import PreferenceLearning
        self.pref_learner = PreferenceLearning(memory=self.memory)

    def process_with_memory(self, user_id: str, question: str):
        # Load user preferences
        preferences = self.pref_learner.learn_preferences(user_id)

        # Apply preferences to config
        if preferences.get("technical_depth") == "advanced":
            self.config.temperature = 0.3  # More precise

        # Execute with context
        result = self.run(question=question)

        # Store interaction for future learning
        self.memory.add(
            content={"user_id": user_id, "question": question, "answer": result["answer"]},
            importance=0.8,
            tags=["interaction", user_id]
        )

        return result
```

#### Performance Characteristics

**Benchmarks (10,000 entries per agent)**:
- **Retrieval Latency (p95)**: <50ms (target: <50ms) ✅
- **Storage Latency (p95)**: <100ms (target: <100ms) ✅
- **Similarity Search**: <50ms for cosine similarity
- **Keyword Search**: <30ms with FTS5 (SQLite)
- **Pattern Detection**: <500ms for 1,000 patterns
- **Preference Learning**: <200ms aggregation query

**Memory Capacity**:
- SQLite: 10,000+ entries per agent, unlimited agents
- File-based: 100,000+ entries (with compression and rotation)
- PostgreSQL: Millions of entries (production scale)

**Storage Efficiency**:
- Average entry size: ~500 bytes (compressed)
- 10,000 entries ≈ 5MB (SQLite with FTS5)
- Automatic pruning: 90%+ reduction in irrelevant memories

#### Use Cases

**Long-Running Conversational Agents**:
- Remember user context across 30+ hour sessions
- Learn user preferences over time
- Detect and auto-answer FAQs

**Multi-Agent Collaboration**:
- Share insights via SharedMemoryPool
- Coordinate work based on shared context
- Avoid duplicate work through memory checking

**Enterprise Customer Support**:
- Track customer history and preferences
- Learn common issues and solutions
- Improve response quality over time

**Research Assistants**:
- Build knowledge graph of research topics
- Remember past findings and citations
- Suggest relevant past research

**Code Generation Agents**:
- Remember coding patterns user prefers
- Learn from past mistakes (syntax errors, etc.)
- Suggest code based on past successful patterns

**Benefits**:
- ✅ **Persistent Context**: Agents remember across sessions
- ✅ **Continuous Learning**: Improve from every interaction
- ✅ **User Adaptation**: Learn individual user preferences
- ✅ **Error Reduction**: Avoid repeating past mistakes
- ✅ **Performance**: <50ms retrieval, <100ms storage
- ✅ **Scalability**: Support millions of entries with PostgreSQL

**Reference**: `src/kaizen/memory/`, `tests/unit/memory/` (365 tests), `docs/reference/memory-patterns-guide.md`

### Document Extraction & RAG Integration (Production-Ready)

**Multi-provider document extraction with RAG-ready chunking and cost optimization.**

**What**: Extract text, tables, and structure from documents (PDF, images) with automatic RAG chunking
**When**: Need to process documents for search, analysis, or question-answering systems
**How**: Multi-provider architecture with automatic fallback and zero-cost option

#### Core Features

**3 Provider Options**:
- **Landing AI**: Best accuracy, bounding boxes, table extraction ($$$)
- **OpenAI Vision** (GPT-4V): Good accuracy, fast, cost-effective ($$)
- **Ollama Vision**: Local inference, FREE, unlimited processing ($0)

**RAG-Ready Chunking**:
- Semantic chunking (512 tokens default, 50 overlap)
- Page citations for source attribution
- Bounding boxes for visual reference (Landing AI)
- Table extraction and formatting
- Preserves document structure

**Cost Optimization**:
- Budget constraints (max_cost parameter)
- Prefer-free mode (tries Ollama first)
- Provider fallback chain (Landing AI → OpenAI → Ollama)
- Zero-cost option available (Ollama)

#### Basic Usage

```python
from kaizen.agents.multi_modal import DocumentExtractionAgent, DocumentExtractionConfig

# Configuration (FREE by default!)
config = DocumentExtractionConfig(
    provider="ollama_vision",  # FREE local provider
    chunk_for_rag=True,        # Generate semantic chunks
    chunk_size=512,            # 512 tokens per chunk
    overlap=50,                # 50 token overlap
    extract_tables=True        # Extract tables
)

agent = DocumentExtractionAgent(config=config)

# Extract document
result = agent.extract(
    file_path="report.pdf",
    extract_tables=True,
    chunk_for_rag=True
)

# Access results
print(f"Text: {result['text'][:100]}...")        # Full extracted text
print(f"Chunks: {len(result['chunks'])}")        # RAG-ready chunks
print(f"Tables: {len(result['tables'])}")        # Extracted tables
print(f"Cost: ${result['cost']:.3f}")             # $0.00 with Ollama!
print(f"Provider: {result['provider']}")          # "ollama_vision"
```

#### RAG Integration

**Chunks with Page Citations**:
```python
# Each chunk includes page number for source attribution
for chunk in result['chunks']:
    print(f"Page {chunk['page']}: {chunk['text'][:50]}...")
    print(f"Position: {chunk.get('bbox', 'N/A')}")  # Bounding box (Landing AI)

# Example output:
# Page 1: Executive Summary - Q4 2024 financial...
# Page 2: Revenue increased by 23% year-over-year...
# Page 3: Customer acquisition costs decreased...
```

**Vector Store Integration**:
```python
from kaizen.agents.multi_modal import DocumentExtractionAgent
from your_vector_store import VectorStore

# Extract and chunk document
result = agent.extract(file_path="document.pdf", chunk_for_rag=True)

# Store chunks in vector database
vector_store = VectorStore()
for chunk in result['chunks']:
    vector_store.add(
        text=chunk['text'],
        metadata={
            "source": "document.pdf",
            "page": chunk['page'],
            "chunk_id": chunk['chunk_id']
        },
        embedding=generate_embedding(chunk['text'])
    )
```

**RAG Query Example**:
```python
# User query
query = "What was the Q4 revenue?"

# Retrieve relevant chunks
relevant_chunks = vector_store.search(query, limit=3)

# Generate answer with source citations
context = "\n\n".join([
    f"[Page {chunk['page']}] {chunk['text']}"
    for chunk in relevant_chunks
])

answer = llm.generate(
    prompt=f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
)

# Answer includes page citations automatically!
```

#### Multi-Provider Architecture

**Provider Selection**:
```python
# Explicit provider selection
config = DocumentExtractionConfig(provider="openai_vision")  # GPT-4V
config = DocumentExtractionConfig(provider="landing_ai")     # Landing AI
config = DocumentExtractionConfig(provider="ollama_vision")  # Ollama (FREE)

# Automatic fallback chain
config = DocumentExtractionConfig(
    provider="landing_ai",  # Try first
    fallback_providers=["openai_vision", "ollama_vision"]  # Then these
)
```

**Cost Optimization**:
```python
# Budget constraint
config = DocumentExtractionConfig(
    max_cost=1.0,  # Maximum $1.00
    provider="landing_ai"  # Will switch to cheaper if budget exceeded
)

# Prefer free (try Ollama first)
config = DocumentExtractionConfig(
    prefer_free=True,  # Try Ollama first, fallback to paid if quality low
    quality_threshold=0.8  # Minimum quality required
)

# Zero cost option (unlimited processing!)
config = DocumentExtractionConfig(
    provider="ollama_vision"  # $0.00 cost, unlimited documents
)
```

#### Advanced Features

**Table Extraction**:
```python
result = agent.extract(file_path="financial_report.pdf", extract_tables=True)

# Access extracted tables
for table in result['tables']:
    print(f"Table on page {table['page']}:")
    print(f"Headers: {table['headers']}")
    print(f"Rows: {len(table['rows'])}")

    # Table data is structured
    for row in table['rows']:
        print(row)
```

**Bounding Boxes (Landing AI)**:
```python
config = DocumentExtractionConfig(provider="landing_ai")
result = agent.extract(file_path="invoice.pdf")

# Each chunk has bounding box coordinates
for chunk in result['chunks']:
    if 'bbox' in chunk:
        x, y, w, h = chunk['bbox']
        print(f"Chunk at ({x}, {y}), size ({w}x{h})")
```

**Batch Processing**:
```python
from pathlib import Path

# Process multiple documents
documents = list(Path("./documents").glob("*.pdf"))

for doc_path in documents:
    result = agent.extract(
        file_path=str(doc_path),
        chunk_for_rag=True
    )

    print(f"Processed {doc_path.name}: {len(result['chunks'])} chunks, ${result['cost']:.3f}")

    # Store in vector database
    store_chunks(result['chunks'])
```

#### Integration with VisionAgent

**Optional Document Extraction**:
```python
from kaizen.agents import VisionAgent, VisionAgentConfig

# VisionAgent can use document extraction (opt-in)
config = VisionAgentConfig(
    llm_provider="ollama",
    model="bakllava",
    enable_document_extraction=True  # Enable document features
)

agent = VisionAgent(config=config)

# Analyze document image
result = agent.run(
    image="receipt.jpg",
    question="Extract total amount and items"
)

# Can also chunk for RAG if needed
chunks = agent.extract_for_rag(image="document.jpg", chunk_size=512)
```

#### Performance & Cost

**Provider Comparison**:
| Provider | Speed | Accuracy | Tables | Bounding Boxes | Cost (per page) |
|----------|-------|----------|--------|----------------|-----------------|
| Ollama   | 2-4s  | 70-80%   | Basic  | No             | $0.00           |
| OpenAI   | 1-2s  | 85-90%   | Good   | No             | ~$0.01          |
| Landing AI | 2-3s | 95%+    | Excellent | Yes          | ~$0.05          |

**Benchmarks (100-page document)**:
- **Ollama**: $0.00, 5-10 minutes, 70-80% accuracy
- **OpenAI**: ~$1.00, 2-3 minutes, 85-90% accuracy
- **Landing AI**: ~$5.00, 3-5 minutes, 95%+ accuracy

**Recommendation**:
- **Development/Testing**: Use Ollama (unlimited free processing)
- **Production (Cost-Sensitive)**: Use OpenAI (good balance)
- **Production (Quality-Critical)**: Use Landing AI (best accuracy + tables + bboxes)

#### Use Cases

**RAG Systems**:
- Process document libraries for semantic search
- Generate FAQ systems from documentation
- Build knowledge bases from PDF reports

**Enterprise Document Processing**:
- Invoice processing and data extraction
- Contract analysis and clause extraction
- Financial report analysis

**Research Assistants**:
- Academic paper processing and citation extraction
- Research report summarization
- Literature review automation

**Compliance & Legal**:
- Policy document analysis
- Regulatory compliance checking
- Legal document review

**Benefits**:
- ✅ **Zero-Cost Option**: Unlimited processing with Ollama
- ✅ **RAG-Ready**: Automatic chunking with page citations
- ✅ **Multi-Provider**: Fallback for reliability
- ✅ **Table Extraction**: Structured data from documents
- ✅ **Production-Validated**: 201 tests passing (149 unit + 34 integration + 18 E2E)
- ✅ **100% Backward Compatible**: Opt-in feature, no breaking changes

**Reference**: `src/kaizen/agents/multi_modal/document_extraction_agent.py`, `src/kaizen/providers/document/`, `tests/unit/agents/multi_modal/`, `examples/8-multi-modal/document-rag/`, `docs/guides/document-extraction-integration.md`

### Strategy Pattern (Execution Strategies)

**Pluggable execution strategies - AsyncSingleShotStrategy is default for all agents.**

**What**: Different execution strategies for single-shot, streaming, parallel, fallback, and multi-cycle patterns
**When**: Need specific execution behavior (streaming, parallel processing, retry logic, iterative loops)
**How**: Strategy pattern with pluggable executors - BaseAgent auto-selects based on agent type

#### Available Strategies

**AsyncSingleShotStrategy (Default)**: Async-first, non-blocking, best for Docker/FastAPI
**StreamStrategy**: Real-time streaming for chat interfaces
**ParallelBatchStrategy**: Concurrent execution for bulk processing
**FallbackStrategy**: Retry with provider alternatives for reliability
**HumanInLoopStrategy**: Interactive approval for dangerous operations
**MultiCycleStrategy**: Iterative execution for autonomous agents (ReAct, CodeGen, RAG)

**Reference**: `src/kaizen/strategies/`, `docs/reference/strategy-selection-guide.md`

### Async Execution (run_async)

**True async execution for production FastAPI/async workflows - non-blocking I/O throughout.**

**What**: `run_async()` method for BaseAgent provides native async execution using AsyncOpenAI client
**When**: Production FastAPI applications, concurrent agent workflows, high-throughput scenarios
**Why**: 10-100x faster concurrent requests, no thread pool exhaustion, no SSL socket blocking

#### Configuration

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig

# Enable async mode in configuration
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    use_async_llm=True  # ← Required for run_async()
)

agent = BaseAgent(config=config, signature=QASignature())
```

#### Usage

```python
# FastAPI endpoint with async agent
@app.post("/api/chat")
async def chat(request: ChatRequest):
    result = await agent.run_async(question=request.message)
    return {"response": result["answer"]}

# Concurrent execution (10+ requests simultaneously)
tasks = [
    agent.run_async(question=f"Question {i}")
    for i in range(100)
]
results = await asyncio.gather(*tasks)  # All execute concurrently
```

#### Key Features

- **Async OpenAI Client**: Uses `AsyncOpenAI` for non-blocking API calls
- **Async Providers**: Both `chat_async()` and `embed_async()` methods available
- **Memory Support**: Full memory and shared memory integration (async-safe)
- **Hooks Integration**: All hooks execute asynchronously
- **Error Handling**: Same error handling as sync `run()` method
- **Backwards Compatible**: Sync `run()` method unchanged

#### Performance Benefits

| Scenario | Sync run() | Async run_async() |
|----------|-----------|-------------------|
| Single request | ~500ms | ~500ms (same) |
| 10 concurrent | ~5000ms (queued) | ~500ms (parallel) |
| 100 concurrent | ~50000ms + timeouts | ~500ms (parallel) |
| Thread pool exhaustion | ✗ Yes | ✓ No |
| SSL socket blocking | ✗ Yes | ✓ No |

#### When to Use

**Use run_async():**
- FastAPI/async web applications
- High-throughput concurrent requests (10+)
- Production deployments with AsyncLocalRuntime
- Docker containers with async orchestration

**Use run():**
- CLI scripts and tools
- Jupyter notebooks
- Synchronous applications
- Simple sequential workflows

#### Configuration Validation

```python
# Agent configured for async
config = BaseAgentConfig(use_async_llm=True, llm_provider="openai")
agent = BaseAgent(config=config, signature=sig)
await agent.run_async(...)  # ✓ Works

# Agent NOT configured for async
config = BaseAgentConfig(use_async_llm=False)  # Default
agent = BaseAgent(config=config, signature=sig)
await agent.run_async(...)  # ✗ Raises ValueError with helpful message
```

**Reference**: `src/kaizen/core/base_agent.py:675-937` (run_async method), `src/kaizen/nodes/ai/ai_providers.py:862-1135` (chat_async/embed_async), `tests/unit/core/test_async_features.py`

### Agent Classification (Autonomous vs Interactive)

**25 agents classified by execution pattern - Universal tool support (ADR-016).**

**Autonomous Agents (3)**: ReActAgent, CodeGenerationAgent, RAGResearchAgent
- Multi-cycle execution with tool calling REQUIRED
- Use MultiCycleStrategy by default
- Objective convergence (task completion detection)

**Interactive Agents (22)**: All other agents
- Single-shot execution (AsyncSingleShotStrategy)
- Tool calling OPTIONAL (enhancement)
- Includes: SimpleQA, ChainOfThought, Streaming, Vision, Transcription, Coordination patterns

**Universal MCP Support**: ALL 25 agents support MCP auto-connect with 12 builtin tools (100% backward compatible)

**Reference**: `src/kaizen/agents/`, `docs/guides/agent-selection-guide.md`, ADR-016

### Pipeline Infrastructure (Composable Workflows - v0.5.0)

**Composable multi-agent pipelines with `.to_agent()` for seamless integration.**

**What**: Base `Pipeline` class for building composable multi-step workflows that can be converted into agents
**When**: Multi-step workflows, sequential processing, agent composition, reusable workflow logic
**Where**: `kaizen.orchestration.pipeline`, `kaizen.orchestration.patterns`

#### Core Concepts

**Pipeline Base Class**:
```python
from kaizen.orchestration.pipeline import Pipeline

class DataProcessingPipeline(Pipeline):
    def run(self, **inputs):
        """Execute multi-step workflow"""
        # Step 1: Clean data
        cleaned = self.clean_data(inputs['data'])

        # Step 2: Transform
        transformed = self.transform(cleaned)

        # Step 3: Analyze
        analysis = self.analyze(transformed)

        return {
            "original": inputs['data'],
            "cleaned": cleaned,
            "transformed": transformed,
            "analysis": analysis
        }

# Use directly
pipeline = DataProcessingPipeline()
result = pipeline.run(data="raw data...")

# Convert to agent for composition
agent = pipeline.to_agent(
    name="data_processor",
    description="Processes and analyzes data"
)
```

**PipelineAgent Wrapper**:
- `.to_agent()` creates `PipelineAgent` - a `BaseAgent` subclass
- Pipelines become first-class agents with all BaseAgent capabilities
- Can be used in multi-agent patterns, workflows, orchestrations

#### SequentialPipeline (Convenience Class)

```python
from kaizen.orchestration.pipeline import SequentialPipeline
from kaizen.agents import SimpleQAAgent, CodeGenerationAgent

# Create pipeline from existing agents
pipeline = SequentialPipeline(
    agents=[
        SimpleQAAgent(config),      # Step 1: Analyze task
        CodeGenerationAgent(config)  # Step 2: Generate code
    ]
)

# Execute pipeline (each agent's output → next agent's input)
result = pipeline.run(task="Create a sorting function")

# Access results
print(result['final_output'])         # Last agent's output
print(result['intermediate_results']) # All agent outputs

# Convert to agent for larger orchestrations
pipeline_agent = pipeline.to_agent(name="code_creation_pipeline")
```

#### Integration with Multi-Agent Patterns

**Pipelines in SupervisorWorkerPattern**:
```python
from kaizen.orchestration.patterns import SupervisorWorkerPattern
from kaizen.orchestration.pipeline import Pipeline

# Define custom pipeline
class DocumentProcessingPipeline(Pipeline):
    def run(self, document):
        # Multi-step document processing
        extracted = self.extract(document)
        validated = self.validate(extracted)
        enriched = self.enrich(validated)
        return {"processed_document": enriched}

# Convert to agent
doc_pipeline_agent = DocumentProcessingPipeline().to_agent(
    name="document_processor"
)

# Use in multi-agent pattern alongside other agents
pattern = SupervisorWorkerPattern(
    supervisor=supervisor,
    workers=[
        doc_pipeline_agent,     # Pipeline wrapped as agent
        qa_agent,               # Regular agent
        research_agent          # Regular agent
    ],
    coordinator=coordinator,
    shared_pool=shared_pool
)

# Supervisor can route tasks to pipeline just like any agent
result = pattern.execute_task("Process this PDF report")
```

#### Composable Pipeline Patterns

Kaizen provides **9 factory methods** on `Pipeline` class for creating production-ready coordination patterns:

##### 1. Sequential Pipeline
**When to use**: Linear step-by-step processing where each step depends on the previous
**Factory method**: `Pipeline.sequential()`

```python
from kaizen.orchestration.pipeline import Pipeline

pipeline = Pipeline.sequential(
    agents=[extractor, transformer, loader]
)
result = pipeline.run(input="raw_data")
```

**A2A Integration**: None (deterministic order)

---

##### 2. Supervisor-Worker Pattern
**When to use**: Task decomposition with central coordination and semantic agent selection
**Factory method**: `Pipeline.supervisor_worker()`

```python
pipeline = Pipeline.supervisor_worker(
    supervisor=supervisor_agent,
    workers=[code_expert, data_expert, writing_expert],
    selection_mode="semantic"  # A2A capability matching
)

tasks = pipeline.delegate("Process 100 documents")
results = pipeline.aggregate_results(tasks[0]["request_id"])
```

**A2A Integration**: ✅ **Semantic worker selection** - Automatically routes tasks to best worker based on A2A capability matching

---

##### 3. Router (Meta-Controller) Pattern
**When to use**: Intelligent request routing to best agent based on task requirements
**Factory method**: `Pipeline.router()`

```python
pipeline = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic",  # A2A-based routing
    error_handling="graceful"
)

result = pipeline.run(
    task="Write a Python function to analyze data",
    input="sales.csv"
)
```

**A2A Integration**: ✅ **Semantic routing** - Routes each request to the best agent via A2A capability matching. Falls back to round-robin when A2A unavailable.

**Common Pitfalls**:
- Don't hardcode routing logic - use semantic routing with A2A
- Always provide `task` parameter for best routing accuracy

---

##### 4. Ensemble Pattern
**When to use**: Multi-perspective analysis where diverse viewpoints improve results
**Factory method**: `Pipeline.ensemble()`

```python
pipeline = Pipeline.ensemble(
    agents=[code_agent, data_agent, writing_agent, research_agent],
    synthesizer=synthesis_agent,
    discovery_mode="a2a",  # A2A discovery
    top_k=3  # Select top 3 agents
)

result = pipeline.run(
    task="Analyze codebase and suggest improvements",
    input="repository_path"
)
```

**A2A Integration**: ✅ **Agent discovery** - Automatically selects top-k agents with best capability matches via A2A. Synthesizer combines their perspectives.

**Common Pitfalls**:
- Set `top_k` appropriately (3-5 agents typical)
- Ensure synthesizer can handle multiple perspectives
- Use `discovery_mode="all"` only for small agent pools (<10)

---

##### 5. Blackboard Pattern
**When to use**: Complex problems requiring iterative collaboration and dynamic specialist selection
**Factory method**: `Pipeline.blackboard()`

```python
pipeline = Pipeline.blackboard(
    specialists=[problem_solver, data_analyst, optimizer, validator],
    controller=controller_agent,
    selection_mode="semantic",  # A2A selection
    max_iterations=5
)

result = pipeline.run(
    task="Solve complex optimization problem",
    input="problem_definition"
)
```

**A2A Integration**: ✅ **Dynamic specialist selection** - Iteratively selects specialists based on evolving blackboard state using A2A. Controller determines convergence.

**Common Pitfalls**:
- Set `max_iterations` to prevent infinite loops
- Controller must have clear convergence criteria
- Blackboard state should be self-contained

---

##### 6. Consensus Pattern
**When to use**: Democratic decision-making requiring agreement across multiple voters
**Factory method**: `Pipeline.consensus()`

```python
pipeline = Pipeline.consensus(
    agents=[technical_expert, business_expert, legal_expert],
    threshold=0.67,  # 2 out of 3 must agree
    voting_strategy="majority"
)

proposal = pipeline.create_proposal("Should we adopt AI?")
for voter in pipeline.voters:
    voter.vote(proposal)
result = pipeline.determine_consensus(proposal["proposal_id"])
```

**A2A Integration**: None (voting-based decision)

**Common Pitfalls**:
- Set threshold appropriately (0.5 for majority, 1.0 for unanimous)
- Ensure voters have sufficient context
- Use `voting_strategy="weighted"` for expert panels

---

##### 7. Debate Pattern
**When to use**: Adversarial analysis to explore tradeoffs and strengthen arguments
**Factory method**: `Pipeline.debate()`

```python
pipeline = Pipeline.debate(
    agents=[proponent_agent, opponent_agent],
    rounds=3,
    judge=judge_agent
)

result = pipeline.debate(
    topic="Should AI be regulated?",
    context="Considering safety and innovation"
)
print(f"Winner: {result['judgment']['winner']}")
```

**A2A Integration**: None (adversarial fixed roles)

**Common Pitfalls**:
- Set rounds appropriately (3-5 typical)
- Judge must be neutral and capable
- Provide sufficient context for informed debate

---

##### 8. Handoff Pattern
**When to use**: Tier escalation where complexity determines which tier handles the task
**Factory method**: `Pipeline.handoff()`

```python
pipeline = Pipeline.handoff(
    agents=[tier1_agent, tier2_agent, tier3_agent]
)

result = pipeline.execute_with_handoff(
    task="Debug complex distributed system issue",
    max_tier=3
)
print(f"Handled by tier: {result['final_tier']}")
print(f"Escalations: {result['escalation_count']}")
```

**A2A Integration**: None (tier-based escalation)

**Common Pitfalls**:
- Each tier must evaluate its capability before escalating
- Avoid unnecessary escalations (inefficient)
- Tier 1 should handle 70-80% of requests

---

##### 9. Parallel Pattern
**When to use**: Independent tasks that can execute concurrently for 10-100x speedup
**Factory method**: `Pipeline.parallel()`

```python
pipeline = Pipeline.parallel(
    agents=[agent1, agent2, agent3],
    aggregator=lambda results: {"combined": " | ".join(r["output"] for r in results)},
    max_workers=5,
    timeout=30.0
)

result = pipeline.run(input="test_data")
```

**A2A Integration**: None (parallel execution)

**Common Pitfalls**:
- Set `max_workers` to prevent resource exhaustion
- Set `timeout` for long-running agents
- Use `error_handling="graceful"` for production

---

#### Pattern Selection Decision Matrix

| Pattern | Task Decomposition | Semantic Selection (A2A) | Parallel Execution | Iterative | Democratic | Adversarial | Tiered |
|---------|-------------------|--------------------------|-------------------|-----------|------------|-------------|--------|
| **Sequential** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Supervisor-Worker** | ✅ | ✅ | Optional | ❌ | ❌ | ❌ | ❌ |
| **Router** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Ensemble** | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Blackboard** | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **Consensus** | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ |
| **Debate** | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ |
| **Handoff** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Parallel** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |

**Quick Selection Guide**:
- **Need A2A semantic matching?** → Router, Supervisor-Worker, Ensemble, Blackboard
- **Need parallel execution?** → Parallel, Ensemble, Consensus
- **Need iterative refinement?** → Blackboard, Debate
- **Need democratic decision?** → Consensus
- **Need adversarial analysis?** → Debate
- **Need tier escalation?** → Handoff
- **Need linear processing?** → Sequential

#### Key Benefits

**Composability**:
- ✅ Pipelines can be nested within other pipelines
- ✅ Pipelines can be used as workers in multi-agent patterns
- ✅ Reuse workflow logic across different contexts

**Flexibility**:
- ✅ Mix and match: Combine pipelines with regular agents
- ✅ Progressive enhancement: Start simple, add complexity as needed
- ✅ Type safety: Inherits BaseAgent's signature-based I/O

**Production Ready**:
- ✅ All BaseAgent features: memory, hooks, observability, permissions
- ✅ Full compatibility with multi-agent patterns
- ✅ Testable: Unit test pipelines independently, then compose

#### Migration from Old Patterns

**Old** (agents.coordination):
```python
# DEPRECATED (v0.4.x and earlier)
from kaizen.agents.coordination.sequential_pipeline import SequentialPattern

pattern = SequentialPattern(agents=[...])
# Limited to sequential patterns, no composability
```

**New** (orchestration.patterns + orchestration.pipeline):
```python
# CURRENT (v0.5.0+)
from kaizen.orchestration.patterns import SequentialPipelinePattern
from kaizen.orchestration.pipeline import SequentialPipeline, Pipeline

# Option 1: Use pattern for coordination
pattern = SequentialPipelinePattern(agents=[...])

# Option 2: Use pipeline for composability
pipeline = SequentialPipeline(agents=[...])
agent = pipeline.to_agent()  # Now composable!

# Option 3: Custom pipeline with full control
class CustomPipeline(Pipeline):
    def run(self, **inputs):
        # Custom multi-step logic
        pass
```

**Backward Compatibility**: Old imports (`kaizen.agents.coordination.*`) were deprecated in v0.5.0 and removed in v0.6.0. Use `kaizen.orchestration.patterns` instead.

**Reference**:
- Implementation: `src/kaizen/orchestration/pipeline.py`
- Tests: `tests/unit/orchestration/test_pipeline.py`
- Examples: `examples/orchestration/pipeline-patterns/`
- ADR: `docs/architecture/adr/ADR-018-pipeline-pattern-architecture-phase3.md`

### A2A Capability Matching (Google A2A Protocol - Advanced)

> **See Skill**: [`kaizen-a2a-protocol`](../../skills/04-kaizen/kaizen-a2a-protocol.md) for A2A basics and standard patterns.

**Enterprise Multi-Agent Use**: BaseAgent automatically generates A2A capability cards for semantic agent matching in complex coordination scenarios. Eliminates hardcoded if/else agent selection logic.

### Multi-Modal Processing (CRITICAL Patterns)

> **See Skills**: [`kaizen-vision-processing`](../../skills/04-kaizen/kaizen-vision-processing.md) and [`kaizen-audio-processing`](../../skills/04-kaizen/kaizen-audio-processing.md) for standard vision/audio patterns.

**Key enterprise-level multi-modal insights preserved below** - these are CRITICAL for production implementations.

### Single-Agent Patterns

**NEW in v0.5.0**: Three advanced single-agent patterns for structured workflows, iterative refinement, and multi-path exploration.

> **See Comprehensive Guides**:
> - **[Planning Agent Guide](../../../sdk-users/apps/kaizen/docs/guides/planning-agent.md)** - Complete documentation
> - **[PEV Agent Guide](../../../sdk-users/apps/kaizen/docs/guides/pev-agent.md)** - Complete documentation
> - **[Tree-of-Thoughts Guide](../../../sdk-users/apps/kaizen/docs/guides/tree-of-thoughts-agent.md)** - Complete documentation
> - **[Single-Agent Patterns Overview](../../../sdk-users/apps/kaizen/docs/guides/single-agent-patterns.md)** - All patterns comparison

#### Planning Agent - Plan Before You Act
**Pattern**: Generate complete plan → Validate feasibility → Execute validated plan

**When to Use**:
- Complex multi-step tasks requiring upfront planning
- Critical operations needing validation before execution
- Structured deliverables with clear steps and dependencies
- Resource planning where feasibility must be checked first

**Example**:
```python
from kaizen.agents.specialized.planning import PlanningAgent, PlanningConfig

config = PlanningConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.3,  # Low for consistent planning
    max_plan_steps=5,
    validation_mode="strict",  # strict, warn, off
    enable_replanning=True
)

agent = PlanningAgent(config=config)
result = agent.run(
    task="Create a comprehensive research report on AI ethics",
    context={
        "max_sources": 5,
        "report_length": "2000 words",
        "focus_areas": ["privacy", "bias", "transparency"]
    }
)

# Access three-phase results
print(f"Plan: {len(result['plan'])} steps")
print(f"Validation: {result['validation_result']['status']}")
print(f"Execution: {len(result['execution_results'])} completed")
print(f"Final: {result['final_result']}")
```

**vs ReAct**: Planning creates complete plan upfront; ReAct interleaves reasoning and action with real-time adaptation.

**Reference**: `sdk-users/apps/kaizen/docs/guides/planning-agent.md`, `examples/1-single-agent/planning-agent/`

#### PEV Agent - Plan, Execute, Verify, Refine
**Pattern**: Create plan → Execute → Verify quality → Refine based on feedback (iterative loop)

**When to Use**:
- Quality-critical outputs (code generation, document writing)
- Verification-driven workflows with measurable quality criteria
- Iterative improvement needed to reach target quality
- Feedback-based optimization

**Example**:
```python
from kaizen.agents.specialized.pev import PEVAgent, PEVAgentConfig

config = PEVAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7,
    max_iterations=5,  # Maximum refinement cycles
    verification_strictness="medium",  # strict, medium, lenient
    enable_error_recovery=True
)

agent = PEVAgent(config=config)
result = agent.run(task="""
Generate Python function with:
- Type hints
- Docstring
- Error handling
- Input validation
- Passes pylint score > 9.0
""")

# Access iterative results
print(f"Iterations: {len(result['refinements'])}")
print(f"Verified: {result['verification']['passed']}")
print(f"Issues: {result['verification'].get('issues', [])}")
print(f"Final: {result['final_result']}")
```

**vs Planning**: PEV iteratively refines with post-execution verification; Planning validates plan before execution (single cycle).

**Reference**: `sdk-users/apps/kaizen/docs/guides/pev-agent.md`, `examples/1-single-agent/pev-agent/`

#### Tree-of-Thoughts Agent - Multi-Path Exploration
**Pattern**: Generate N parallel paths → Evaluate each → Select best → Execute winner

**When to Use**:
- Multiple valid approaches exist, need to explore alternatives
- Strategic decision-making where diverse perspectives improve outcomes
- Creative problem-solving benefiting from alternative solutions
- Uncertainty about optimal path

**Example**:
```python
from kaizen.agents.specialized.tree_of_thoughts import ToTAgent, ToTAgentConfig

config = ToTAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.9,  # HIGH for path diversity
    num_paths=5,  # Generate 5 alternatives
    evaluation_criteria="quality",  # quality, speed, creativity
    parallel_execution=True
)

agent = ToTAgent(config=config)
result = agent.run(task="""
Startup with $500K needs go-to-market strategy.
Consider: B2B enterprise, B2C freemium, platform, vertical integration.
Recommend best strategy with reasoning.
""")

# Access multi-path results
print(f"Paths Explored: {len(result['paths'])}")
for i, eval in enumerate(result['evaluations'], 1):
    print(f"Path {i}: Score {eval['score']:.2f}")
print(f"Best Score: {result['best_path']['score']:.2f}")
print(f"Recommendation: {result['final_result']}")
```

**vs CoT**: ToT explores multiple parallel paths; CoT follows single linear reasoning chain.

**Reference**: `sdk-users/apps/kaizen/docs/guides/tree-of-thoughts-agent.md`, `examples/1-single-agent/tot-agent/`

#### Single-Agent Pattern Decision Matrix

| Pattern | Upfront Planning | Verification | Iteration | Multi-Path | Best For |
|---------|-----------------|--------------|-----------|------------|----------|
| **Planning** | ✅ Complete plan | Pre-execution | Single (or replan) | ❌ | Structured workflows, critical validation |
| **PEV** | ✅ Initial plan | Post-execution | Multiple refine cycles | ❌ | Quality-critical, iterative refinement |
| **ToT** | ❌ | Score-based evaluation | Single generation | ✅ N paths | Strategic decisions, alternatives |
| **ReAct** | ❌ | Observation-based | Variable action cycles | ❌ | Dynamic, real-time adaptation |
| **CoT** | ❌ | ❌ | Single reasoning | ❌ | Step-by-step reasoning tasks |
| **SimpleQA** | ❌ | ❌ | Single-shot | ❌ | Simple Q&A, no workflow |

**Quick Selection Guide**:
- **Need upfront structure?** → Planning or PEV
- **Need quality verification?** → PEV (post-execution) or Planning (pre-execution)
- **Need multiple alternatives?** → Tree-of-Thoughts
- **Need real-time adaptation?** → ReAct
- **Simple reasoning task?** → Chain-of-Thought or SimpleQA

**Pattern Comparison Examples**:

| Task | Recommended Pattern | Reasoning |
|------|---------------------|-----------|
| Research report generation | **Planning** | Multi-step workflow, validation before execution |
| Code generation with testing | **PEV** | Iterative refinement with quality verification |
| Strategic business decision | **Tree-of-Thoughts** | Explore multiple alternatives, select best |
| Dynamic troubleshooting | **ReAct** | Real-time observation-based adaptation |
| Math problem solving | **Chain-of-Thought** | Step-by-step reasoning |
| Simple question answering | **SimpleQA** | Direct answer, no workflow needed |

## UX Improvements (Apply to All New Code)

### Config Auto-Extraction
```python
# OLD - DON'T DO THIS
agent_config = BaseAgentConfig(
    llm_provider=config.llm_provider,
    model=config.model,
    temperature=config.temperature,
    max_tokens=config.max_tokens
)
super().__init__(config=agent_config, ...)

# NEW - ALWAYS DO THIS
super().__init__(config=config, ...)  # Auto-converted
```

### Shared Memory Convenience
```python
# OLD - DON'T DO THIS
if self.shared_memory:
    self.shared_memory.write_insight({
        "agent_id": self.agent_id,
        "content": json.dumps(result),
        "tags": ["processing"],
        "importance": 0.9
    })

# NEW - ALWAYS DO THIS
self.write_to_memory(
    content=result,  # Auto-serialized
    tags=["processing"],
    importance=0.9
)
```

### Result Parsing Helpers
```python
# OLD - DON'T DO THIS
field_raw = result.get("field", "[]")
try:
    field = json.loads(field_raw) if isinstance(field_raw, str) else field_raw
except:
    field = []

# NEW - ALWAYS DO THIS
field = self.extract_list(result, "field", default=[])
```

**Available Methods**: `extract_list()`, `extract_dict()`, `extract_float()`, `extract_str()`

## Multi-Modal Common Pitfalls

### Pitfall 1: OllamaVisionProvider Initialization
```python
# ❌ WRONG - TypeError
provider = OllamaVisionProvider(model="bakllava")

# ✅ CORRECT
config = OllamaVisionConfig(model="bakllava")
provider = OllamaVisionProvider(config=config)
```

### Pitfall 2: VisionAgent Parameter Names
```python
# ❌ WRONG - TypeError
result = agent.run(image="...", prompt="What do you see?")

# ✅ CORRECT
result = agent.run(image="...", question="What do you see?")
```

### Pitfall 3: Image Path Handling
```python
# ❌ WRONG - Ollama doesn't accept data URLs
img = ImageField()
img.load("/path/to/image.png")
provider.analyze_image(image=img.to_base64(), ...)

# ✅ CORRECT - Pass file path or ImageField
provider.analyze_image(image="/path/to/image.png", ...)
# OR
provider.analyze_image(image=img, ...)
```

### Pitfall 4: Response Format Differences
```python
# OllamaVisionProvider → 'response' key
result = provider.analyze_image(...)
text = result['response']

# VisionAgent → 'answer' key
result = agent.run(...)
text = result['answer']

# MultiModalAgent → signature fields
result = agent.run(...)
invoice = result['invoice_number']  # Depends on signature
```

### Pitfall 5: Integration Testing
**CRITICAL**: Always validate with real models, not just mocks.

```python
# ❌ INSUFFICIENT
def test_vision_mocked():
    provider = MockVisionProvider()
    result = provider.analyze_image(...)
    assert result  # Passes but doesn't test real API

# ✅ REQUIRED
@pytest.mark.integration
def test_vision_real():
    config = OllamaVisionConfig(model="bakllava")
    provider = OllamaVisionProvider(config=config)
    result = provider.analyze_image(
        image="/path/to/test/invoice.png",
        prompt="Extract invoice number"
    )
    assert 'response' in result
    assert len(result['response']) > 0
```

**Reference**: See `docs/development/integration-testing-guide.md`

## Model Selection Guide

| Model | Size | Speed | Accuracy | Cost | Best For |
|-------|------|-------|----------|------|----------|
| bakllava | 4.7GB | 2-4s | 40-60% | $0 | Development, testing |
| llava:13b | 7GB | 4-8s | 80-90% | $0 | Production (local) |
| GPT-4V | API | 1-2s | 95%+ | ~$0.01/img | Production (cloud) |

**Decision Framework:**
- **Development/Testing**: Use bakllava (fast iteration, zero cost)
- **Production Local**: Use llava:13b (better accuracy, zero cost, data privacy)
- **Production Cloud**: Use GPT-4V (best accuracy, cloud API, pay per use)

## Test Infrastructure Patterns

### Standardized Fixtures
**Location**: `tests/unit/examples/conftest.py`

Kaizen provides standardized test fixtures to ensure consistent testing patterns:

```python
# Use standardized fixtures for all agent tests
def test_qa_agent(simple_qa_example, assert_async_strategy, test_queries):
    QAConfig = simple_qa_example.config_classes["QAConfig"]
    QAAgent = simple_qa_example.agent_classes["SimpleQAAgent"]

    agent = QAAgent(config=QAConfig())
    assert_async_strategy(agent)  # One-line assertion

    result = agent.run(question=test_queries["simple"])
    assert isinstance(result, dict)
```

### Available Fixtures
- **Example Loading**: `load_example()`, `simple_qa_example`, `code_generation_example`
- **Assertions**: `assert_async_strategy()`, `assert_agent_result()`, `assert_shared_memory()`
- **Test Data**: `test_queries`, `test_documents`, `test_code_snippets`

**When to Use:** Always use standardized fixtures for unit tests to ensure consistency and reduce boilerplate.

### E2E Testing for Autonomous Agents

**E2E (End-to-End) tests validate complete autonomous agent workflows with real infrastructure:**

**What E2E Tests Are:**
- **Real LLM inference** using Ollama llama3.2:1b (FREE, no API costs)
- **Real database** operations with DataFlow (SQLite/PostgreSQL)
- **Real tools** execution (file system, HTTP, bash commands)
- **NO MOCKING** (Tier 3 testing strategy - real infrastructure only)

**How to Run E2E Tests:**

```bash
# Run all E2E tests
pytest tests/e2e/autonomy/ -v

# Run specific autonomy system
pytest tests/e2e/autonomy/test_tool_calling_e2e.py -v       # Tool calling
pytest tests/e2e/autonomy/test_planning_e2e.py -v           # Planning agents
pytest tests/e2e/autonomy/test_meta_controller_e2e.py -v    # Meta-controller
pytest tests/e2e/autonomy/test_memory_e2e.py -v             # Memory system
pytest tests/e2e/autonomy/checkpoints/ -v                   # Checkpoint system

# Prerequisites: Install and start Ollama
ollama pull llama3.2:1b  # First time only
pytest tests/e2e/autonomy/ -v
```

**Writing E2E Tests:**

```python
import pytest
from kaizen.agents.autonomous.base import BaseAutonomousAgent
from kaizen.agents.autonomous.config import AutonomousConfig
from kaizen.signatures import Signature, InputField, OutputField

class TaskSignature(Signature):
    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Task result")

@pytest.mark.e2e  # Mark as E2E test
@pytest.mark.asyncio  # Async test
async def test_autonomous_workflow():
    """Test autonomous agent with real LLM."""

    # 1. Create config with Ollama (FREE)
    config = AutonomousConfig(
        llm_provider="ollama",
        model="llama3.2:1b",
        enable_interrupts=True,
        checkpoint_on_interrupt=True
    )

    # 2. Create agent
    agent = BaseAutonomousAgent(config=config, signature=TaskSignature())

    # 3. Execute with real LLM
    result = await agent.run_autonomous(task="Analyze data file")

    # 4. Validate results
    assert result is not None
    assert "result" in result
    assert len(result["result"]) > 0
```

**Key E2E Testing Patterns:**

1. **Always use Ollama** for E2E tests (FREE, no API costs)
2. **Always mark with @pytest.mark.e2e** for test discovery
3. **Always use real infrastructure** (NO MOCKING)
4. **Always clean up** resources in teardown

**Available E2E Test Suites:**

| Test Suite | File | Tests | What It Validates |
|------------|------|-------|-------------------|
| **Tool Calling** | `test_tool_calling_e2e.py` | 4 | File/HTTP/bash tools with permission policies and approval workflows |
| **Planning** | `test_planning_e2e.py` | 3 | Planning/PEV/ToT agents with multi-step decomposition |
| **Meta-Controller** | `test_meta_controller_e2e.py` | 3 | Semantic routing, fallback strategies, task decomposition |
| **Memory** | `test_memory_e2e.py` | 4 | Hot/warm/cold tier persistence, multi-hour conversations |
| **Checkpoints** | `checkpoints/` | 3 | Auto-checkpoint creation, resume from checkpoint, compression |

**Prerequisites:**

**Required:**
- Ollama installed and running (`ollama serve`)
- Model downloaded (`ollama pull llama3.2:1b`)
- SQLite (included with Python)

**Optional:**
- PostgreSQL (for production-like memory tests)
- OpenAI API key (for quality validation)

**Cost Analysis:**

**E2E Tests Cost**: $0.00
- Ollama LLM: FREE (local inference)
- SQLite: FREE (local database)
- No API calls to paid services

If using OpenAI for quality validation:
- Use `gpt-4o-mini` ($0.15/1M input, $0.60/1M output)
- Budget: <$20 for full E2E suite
- Cost tracking built into tests

## Critical Rules

### ALWAYS
- ✅ Use domain configs (e.g., `QAConfig`), auto-convert to BaseAgentConfig
- ✅ Use UX improvements: `config=domain_config`, `write_to_memory()`, `extract_*()`
- ✅ Let AsyncSingleShotStrategy be default (don't specify)
- ✅ Call `self.run()` (sync interface), not `strategy.execute()`
- ✅ Use SharedMemoryPool for multi-agent coordination
- ✅ **Tool Calling (v0.2.0+)**: MCP auto-connect provides 12 builtin tools automatically, use `mcp_servers` parameter for custom MCP servers
- ✅ **MCP Integration (v0.2.0+)**: ALL agents auto-connect to kaizen_builtin MCP server with 12 tools, add custom servers via `mcp_servers` parameter
- ✅ **Control Protocol (v0.2.0)**: Use `control_protocol` parameter for bidirectional communication
- ✅ **Observability (v0.5.0)**: Enable via `agent.enable_observability()` when needed (opt-in, zero overhead when disabled)
- ✅ **Hooks (v0.5.0)**: Use `agent._hook_manager` to register hooks for lifecycle events
- ✅ **State (v0.5.0)**: Create checkpoints before risky operations with StateManager
- ✅ **Permissions (v0.5.0+)**: Check `ExecutionContext.can_use_tool()` before tool execution
- ✅ **Interrupts (v0.6.0)**: Enable interrupts for autonomous agents with `enable_interrupts=True`, use handlers for timeout/budget
- ✅ **Persistent Memory (v0.6.0)**: Use `PersistentBufferMemory` with DataFlow backend for conversation persistence across sessions
- ✅ **Multi-Modal**: Use config objects for OllamaVisionProvider
- ✅ **Multi-Modal**: Use 'question' for VisionAgent, 'prompt' for providers
- ✅ **Multi-Modal**: Pass file paths, not base64 data URLs
- ✅ **Testing**: Validate with real models, not just mocks
- ✅ **Testing**: Use `llm_provider="mock"` explicitly in unit tests
- ✅ Use standardized test fixtures from `conftest.py`
- ✅ **Systematic Validation**: Verify task completion with concrete evidence before marking complete

### NEVER
- ❌ Manually create BaseAgentConfig (use auto-extraction)
- ❌ Write verbose `write_insight()` (use `write_to_memory()`)
- ❌ Manual JSON parsing (use `extract_*()`)
- ❌ sys.path manipulation in tests (use fixtures)
- ❌ Call `strategy.execute()` directly (use `self.run()`)
- ❌ **Multi-Modal**: Pass `model=` to OllamaVisionProvider (use config)
- ❌ **Multi-Modal**: Use 'prompt' for VisionAgent (use 'question')
- ❌ **Multi-Modal**: Convert images to base64 for Ollama (use file paths)
- ❌ **Testing**: Rely only on mocked tests (validate with real models)

## Common Issues & Fixes

### Config Not Auto-Converting
```python
# WRONG
agent = MyAgent(config=BaseAgentConfig(...))

# RIGHT
agent = MyAgent(config=MyDomainConfig(...))
```

### Shared Memory Not Working
```python
# Missing shared_memory parameter
shared_pool = SharedMemoryPool()
agent = MyAgent(config, shared_pool, agent_id="my_agent")
```

### Extract Methods Failing
```python
# Debug first
print(result.keys())
data = self.extract_list(result, "actual_key_name", default=[])
```

### Multi-Modal API Errors
**See**: `sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md` - Common Pitfalls section

### Provider Compatibility for Structured Outputs (v0.8.2)

**Multi-Provider Support**: OpenAI, Google/Gemini, and Azure AI Foundry all support structured outputs with automatic format translation. Ollama/Anthropic do NOT support structured outputs API.

**Provider Support Matrix**:
- ✅ **OpenAI**: Full support for `json_schema` (strict mode) and `json_object` (legacy)
- ✅ **Google/Gemini**: Full support - auto-translates to `response_mime_type` + `response_schema`
- ✅ **Azure AI Foundry**: Full support - auto-translates to `JsonSchemaFormat`
- ❌ **Ollama**: NO support for structured outputs API
- ❌ **Anthropic**: NO support for structured outputs API

**Affected Agents** (require structured output provider):
- `PlanningAgent` - Uses `List[PlanStep]` schema
- `PEVAgent` - Uses `List[Refinement]` schema
- `ToTAgent` - Uses `List[ToTNode]` schema
- `MetaController` - Uses complex routing schemas

**Symptoms with Unsupported Providers**:
```python
# Test times out after 60-120s
# JSON_PARSE_FAILED errors
# Provider tries to generate matching JSON but can't comply with strict schema
```

**Solution** (choose any supported provider):
```python
# WRONG (will timeout with complex schemas)
agent = PlanningAgent(
    llm_provider="ollama",
    model="llama3.1:8b-instruct-q8_0"
)

# RIGHT - OpenAI (100% schema compliance)
agent = PlanningAgent(
    llm_provider="openai",
    model="gpt-4o-mini"
)

# RIGHT - Google Gemini (100% schema compliance, v0.8.2)
agent = PlanningAgent(
    llm_provider="google",
    model="gemini-2.0-flash"
)

# RIGHT - Azure AI Foundry (100% schema compliance, v0.8.2)
agent = PlanningAgent(
    llm_provider="azure",
    model="gpt-4o"
)
```

**How It Works** (v0.8.2):
- All providers receive OpenAI-style `response_format` from `create_structured_output_config()`
- Each provider auto-translates to native parameters:
  - **OpenAI**: Uses `response_format` directly
  - **Google**: Translates to `response_mime_type="application/json"` + `response_schema`
  - **Azure**: Translates to `JsonSchemaFormat(name, schema, strict)`

**When to Use Each Provider**:
- **OpenAI** (RECOMMENDED): Widest model selection, proven reliability
- **Google/Gemini** (GOOD): Free tier available, multimodal support
- **Azure** (ENTERPRISE): Azure ecosystem integration, compliance
- **Ollama** (SIMPLE ONLY): Free local inference, string/dict outputs only

**Cost Impact**:
- OpenAI gpt-4o-mini: ~$0.001-0.01 per test
- Google gemini-2.0-flash: Similar pricing, free tier available
- Azure: Enterprise pricing
- Ollama: Free (local inference)

**Test Configuration**:
```python
# For E2E tests with structured outputs (any supported provider)
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not (os.getenv("OPENAI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("AZURE_AI_INFERENCE_API_KEY")),
        reason="API key required for structured outputs (OpenAI, Google, or Azure)"
    ),
]
```

### pytest-asyncio Version Compatibility

**CRITICAL**: pytest-asyncio version affects async test execution. Use 0.21.1 for E2E tests.

**Issue**: pytest-asyncio 1.x forces `Mode.STRICT` even with `asyncio_mode = auto` in pytest.ini
- Version 1.2.0+: Ignores `asyncio_mode = auto`, enforces STRICT mode
- Version 0.23.0: `AttributeError: 'Package' object has no attribute 'obj'`
- Version 0.21.1: ✅ Works correctly with E2E tests

**Solution**:
```bash
pip install pytest-asyncio==0.21.1
```

**pytest.ini Configuration**:
```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
asyncio_default_test_loop_scope = function
```

**Known Side Effect**:
- Unit test `test_edge_state_machine.py` fails with pytest-asyncio 0.21.1
- Error: `AttributeError: 'FixtureDef' object has no attribute 'unittest'`
- E2E tests are higher priority - unit test issue deferred

**Test Markers**:
```python
# E2E tests work with pytest-asyncio 0.21.1
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,  # Async mode auto-detected
]
```

## Enterprise Agent Trust Protocol (EATP) - v0.8.0

**Cryptographically verifiable trust chains for AI agents**, enabling enterprise-grade accountability, authorization, and secure multi-agent communication.

**What**: Complete trust infrastructure for AI agents with lineage tracking, capability attestation, secure messaging, and policy enforcement
**When**: Enterprise deployments requiring accountability, regulatory compliance, cross-organization agent coordination
**Where**: `kaizen.trust` module

### Core Concepts

**Trust Lineage Chain**: Cryptographically linked chain of records establishing agent identity, capabilities, and delegation history. Every action is traceable to an organizational authority.

**Key Components**:
- **GenesisRecord**: Initial trust establishment with authority signature
- **CapabilityAttestation**: Cryptographic proof of agent capabilities
- **DelegationRecord**: Capability delegation between agents
- **AuditAnchor**: Immutable audit trail entries

### Quick Start

```python
from kaizen.trust import (
    TrustOperations,
    PostgresTrustStore,
    OrganizationalAuthorityRegistry,
    TrustKeyManager,
    CapabilityRequest,
    CapabilityType,
)

# Initialize trust infrastructure
store = PostgresTrustStore(connection_string="postgresql://...")
registry = OrganizationalAuthorityRegistry()
key_manager = TrustKeyManager()
trust_ops = TrustOperations(registry, key_manager, store)
await trust_ops.initialize()

# Establish trust for an agent
chain = await trust_ops.establish(
    agent_id="agent-001",
    authority_id="org-acme",
    capabilities=[
        CapabilityRequest(
            capability="analyze_data",
            capability_type=CapabilityType.ACCESS,
        )
    ],
)

# Verify trust before action
result = await trust_ops.verify(
    agent_id="agent-001",
    action="analyze_data",
)

if result.valid:
    # Proceed with trusted action
    pass
```

### Human Traceability (v0.8.0)

**What**: Complete human-to-agent traceability for all AI actions
**When**: Enterprise deployments requiring every agent action to be traceable to an authorizing human
**Core Principle**: Every action in the system MUST be traceable to a human. PseudoAgents bridge human authentication to the agentic world.

**Key Components**:
- **HumanOrigin**: Immutable record of the human who authorized an execution chain
- **ExecutionContext**: Ambient context carrying human origin through all operations
- **PseudoAgent**: Human facade - the ONLY entity that can initiate trust chains
- **ConstraintValidator**: Validates constraint tightening (delegations can only REDUCE permissions)

#### HumanOrigin (Immutable Human Record)

```python
from kaizen.trust.execution_context import HumanOrigin
from datetime import datetime

# Created from authentication system
human_origin = HumanOrigin(
    human_id="alice@corp.com",          # Canonical ID (usually email)
    display_name="Alice Chen",           # Human-readable name
    auth_provider="okta",                # How they authenticated
    session_id="sess-abc123",            # Current session
    authenticated_at=datetime.utcnow(),  # When they authenticated
)

# Immutable (frozen=True) - cannot be modified after creation
# This ensures audit integrity
```

#### ExecutionContext (Context Propagation)

```python
from kaizen.trust.execution_context import (
    ExecutionContext,
    execution_context,
    get_current_context,
    require_current_context,
)

# Create context rooted in a human
ctx = ExecutionContext(
    human_origin=human_origin,
    delegation_chain=["pseudo:alice@corp.com", "agent-001"],
    delegation_depth=1,
    constraints={"cost_limit": 1000},
)

# Context flows through async operations using ContextVar
async def process_data():
    # Get context (returns None if not set)
    ctx = get_current_context()

    # Require context (raises RuntimeError if not set)
    ctx = require_current_context()

    # Access human origin
    print(f"Authorized by: {ctx.human_origin.display_name}")
    print(f"Delegation depth: {ctx.delegation_depth}")

# Context manager sets context for a scope
with execution_context(ctx):
    await process_data()  # Context available here
# Context automatically cleared after scope
```

#### PseudoAgent (Human Facade)

```python
from kaizen.trust import TrustOperations
from kaizen.trust.pseudo_agent import (
    PseudoAgent,
    PseudoAgentFactory,
    PseudoAgentConfig,
    AuthProvider,
)

# Initialize factory with trust operations
factory = PseudoAgentFactory(
    trust_operations=trust_ops,
    default_config=PseudoAgentConfig(
        session_timeout_minutes=60,
        require_mfa=True,
        allowed_capabilities=["read_data", "process_data"],
    ),
)

# Create PseudoAgent from session data
pseudo = factory.from_session(
    user_id="user-123",
    email="alice@corp.com",
    display_name="Alice Chen",
    session_id="sess-456",
    auth_provider="okta",
)

# Or from JWT claims
pseudo = factory.from_claims(
    claims={"sub": "user-123", "email": "alice@corp.com", "name": "Alice"},
    auth_provider="azure_ad",
)

# Or from HTTP request headers (API gateway pattern)
pseudo = factory.from_http_request(
    headers=request.headers,
    auth_provider="oidc",
)

# Delegate trust to an agent (ONLY way trust enters the system)
delegation, agent_ctx = await pseudo.delegate_to(
    agent_id="invoice-processor",
    task_id="november-invoices",
    capabilities=["read_invoices", "process_invoices"],
    constraints={"cost_limit": 1000},
)

# Agent executes with the delegated context
result = await agent.execute_async(inputs, context=agent_ctx)

# Revoke when human logs out
await pseudo.revoke_all_delegations()
```

#### Constraint Tightening Validation

```python
from kaizen.trust.constraint_validator import ConstraintValidator

validator = ConstraintValidator()

# Constraints can only become MORE restrictive
parent_constraints = {"cost_limit": 1000, "regions": ["US", "EU"]}
child_constraints = {"cost_limit": 500, "regions": ["US"]}  # More restrictive

# Valid: child is subset of parent
result = validator.validate(parent_constraints, child_constraints)
assert result.valid

# Invalid: child tries to EXPAND permissions
invalid_child = {"cost_limit": 2000}  # Tries to increase limit
result = validator.validate(parent_constraints, invalid_child)
assert not result.valid
assert "cost_limit" in result.violations
```

#### Database Migration (v0.8.0)

EATP v0.8.0 adds human origin tracking columns to trust tables:

```bash
# Check migration status
python -m kaizen.trust.migrations.eatp_human_origin --check

# Run migration
python -m kaizen.trust.migrations.eatp_human_origin
```

**Migration adds**:
- `human_origin_id` - VARCHAR(255) for human ID lookup
- `human_origin_data` - JSONB for full HumanOrigin record
- `delegation_chain` - TEXT[] array of agent IDs from human to current agent
- `delegation_depth` - INTEGER distance from human (0 = direct delegation)

**Tables affected**:
- `delegation_records` - All 4 columns
- `audit_anchors` - human_origin_id and human_origin_data only

### TrustedAgent (BaseAgent with Trust)

**What**: BaseAgent extended with trust capabilities for enterprise deployments
**When**: Agents requiring cryptographic accountability and capability verification

```python
from kaizen.trust import TrustedAgent, TrustedAgentConfig

config = TrustedAgentConfig(
    llm_provider="openai",
    model="gpt-4o",
    trust_store_url="postgresql://...",
    authority_id="org-acme",
)

# Create trusted agent
agent = TrustedAgent(
    config=config,
    signature=MySignature(),
    capabilities=["analyze_data", "generate_reports"],
)

# Trust is automatically verified before each action
result = await agent.run(question="Analyze sales data")

# Access trust context
print(f"Trust chain valid: {agent.trust_context.is_valid}")
print(f"Capabilities: {agent.trust_context.capabilities}")
```

**TrustedSupervisorAgent**: Supervisor pattern with trust propagation to worker agents.

```python
from kaizen.trust import TrustedSupervisorAgent

supervisor = TrustedSupervisorAgent(
    config=config,
    workers=[worker1, worker2],
    delegation_policy="least_privilege",  # Only delegate required capabilities
)

# Delegated capabilities are cryptographically attested
result = await supervisor.delegate_task(
    task="Process customer data",
    required_capabilities=["read_customer_data"],
)
```

### Agent Registry & Discovery

**What**: Central registry for agent discovery with health monitoring
**When**: Multi-agent systems requiring capability-based discovery

```python
from kaizen.trust import (
    AgentRegistry,
    PostgresAgentRegistryStore,
    AgentHealthMonitor,
    DiscoveryQuery,
    RegistrationRequest,
)

# Initialize registry
store = PostgresAgentRegistryStore(connection_string="...")
registry = AgentRegistry(store=store)

# Register agent
await registry.register(RegistrationRequest(
    agent_id="agent-001",
    name="Data Analyzer",
    capabilities=["analyze_data", "generate_charts"],
    metadata={"version": "1.0", "owner": "team-data"},
))

# Discover agents by capability
agents = await registry.discover(DiscoveryQuery(
    capabilities=["analyze_data"],
    status="active",
))

# Health monitoring (background)
monitor = AgentHealthMonitor(registry=registry, interval_seconds=30)
await monitor.start()
```

### Secure Messaging

**What**: End-to-end encrypted, replay-protected messaging between agents
**When**: Cross-agent communication requiring confidentiality and integrity

```python
from kaizen.trust import (
    SecureChannel,
    MessageSigner,
    MessageVerifier,
    InMemoryReplayProtection,
)

# Create secure channel
channel = SecureChannel(
    agent_id="agent-001",
    signer=MessageSigner(private_key=my_key),
    verifier=MessageVerifier(),
    replay_protection=InMemoryReplayProtection(window_seconds=300),
)

# Send secure message
await channel.send(
    recipient="agent-002",
    payload={"action": "process_data", "data": {...}},
)

# Receive and verify message
message = await channel.receive()
if message.verification.valid:
    # Message is authentic and not replayed
    process(message.payload)
```

### Trust-Aware Orchestration

**What**: Workflow runtime with trust context propagation and policy enforcement
**When**: Complex workflows requiring trust verification at each step

```python
from kaizen.trust import (
    TrustAwareOrchestrationRuntime,
    TrustAwareRuntimeConfig,
    TrustExecutionContext,
    TrustPolicyEngine,
    TrustPolicy,
    PolicyType,
)

# Configure trust-aware runtime
config = TrustAwareRuntimeConfig(
    verify_on_execute=True,
    propagate_context=True,
    fail_on_policy_violation=True,
)

runtime = TrustAwareOrchestrationRuntime(
    trust_ops=trust_ops,
    config=config,
)

# Create execution context with trust
context = TrustExecutionContext(
    agent_id="agent-001",
    trust_chain=chain,
    delegations=[],
)

# Execute workflow with trust verification
results, run_id = await runtime.execute_workflow_async(
    workflow.build(),
    trust_context=context,
)

# Policy engine for complex rules
policy_engine = TrustPolicyEngine()
policy_engine.add_policy(TrustPolicy(
    name="require_mfa",
    policy_type=PolicyType.CAPABILITY,
    condition=lambda ctx: ctx.has_mfa_attestation,
))
```

### Enterprise System Agents (ESA)

**What**: Proxy agents for legacy systems (databases, APIs) with trust attestation
**When**: Integrating non-agent systems into trusted workflows

```python
from kaizen.trust import (
    EnterpriseSystemAgent,
    ESAConfig,
    SystemMetadata,
    SystemConnectionInfo,
)

# Create ESA for legacy database
db_esa = EnterpriseSystemAgent(
    config=ESAConfig(
        system_id="legacy-crm",
        system_type="database",
        connection=SystemConnectionInfo(
            host="db.internal",
            port=5432,
            credentials_ref="vault://crm-db",
        ),
    ),
    trust_ops=trust_ops,
    capabilities=["read_customers", "write_orders"],
)

# ESA operations are trust-verified
result = await db_esa.execute(
    operation="read_customers",
    params={"filter": {"region": "APAC"}},
)
```

### A2A HTTP Service

**What**: HTTP service for trust operations following Google A2A protocol
**When**: Cross-network agent communication via HTTP

```python
from kaizen.trust import A2AService, create_a2a_app, AgentCardGenerator

# Generate A2A-compatible agent card
card = AgentCardGenerator.generate(
    agent_id="agent-001",
    name="Data Processor",
    capabilities=["analyze", "transform"],
    trust_extensions={"authority": "org-acme"},
)

# Create A2A HTTP service
app = create_a2a_app(
    trust_ops=trust_ops,
    registry=registry,
    enable_delegation=True,
    enable_verification=True,
)

# Run service (FastAPI-based)
# uvicorn app:app --port 8080
```

### Security Features

**Credential Rotation**:
```python
from kaizen.trust import CredentialRotationManager, ScheduledRotation

rotation_manager = CredentialRotationManager(
    trust_ops=trust_ops,
    key_manager=key_manager,
)

# Schedule automatic rotation
await rotation_manager.schedule(ScheduledRotation(
    agent_id="agent-001",
    interval_days=30,
    notify_hours_before=24,
))

# Manual rotation
result = await rotation_manager.rotate(agent_id="agent-001")
```

**Rate Limiting**:
```python
from kaizen.trust import TrustRateLimiter

limiter = TrustRateLimiter(
    max_operations_per_minute=100,
    max_delegations_per_hour=10,
)

# Rate limit applied automatically in TrustOperations
```

**Security Audit Logging**:
```python
from kaizen.trust import SecurityAuditLogger, SecurityEventType

logger = SecurityAuditLogger(output_path="/var/log/trust-audit.jsonl")

# Automatic logging of security events:
# - TRUST_ESTABLISHED, TRUST_REVOKED
# - DELEGATION_CREATED, DELEGATION_EXPIRED
# - VERIFICATION_PASSED, VERIFICATION_FAILED
# - REPLAY_DETECTED, SIGNATURE_INVALID
```

### Trust Module Components

| Component | Purpose |
|-----------|---------|
| `TrustLineageChain` | Complete trust chain for an agent |
| `TrustOperations` | ESTABLISH, DELEGATE, VERIFY, AUDIT operations |
| `PostgresTrustStore` | Persistent storage for trust chains |
| `TrustedAgent` | BaseAgent with trust capabilities |
| `TrustedSupervisorAgent` | Supervisor with trust delegation |
| `AgentRegistry` | Central registry for agent discovery |
| `AgentHealthMonitor` | Background health monitoring |
| `SecureChannel` | End-to-end encrypted messaging |
| `MessageVerifier` | Multi-step message verification |
| `InMemoryReplayProtection` | Replay attack prevention |
| `TrustExecutionContext` | Trust state propagation |
| `TrustPolicyEngine` | Policy-based trust evaluation |
| `TrustAwareOrchestrationRuntime` | Trust-aware workflow execution |
| `EnterpriseSystemAgent` | Proxy agents for legacy systems |
| `A2AService` | HTTP service for trust operations |
| `CredentialRotationManager` | Automatic credential rotation |
| `TrustRateLimiter` | Rate limiting for trust operations |
| `SecurityAuditLogger` | Security event audit logging |
| `HumanOrigin` | Immutable record of authorizing human (v0.8.0) |
| `ExecutionContext` | Context propagation with human traceability (v0.8.0) |
| `PseudoAgent` | Human facade for initiating trust chains (v0.8.0) |
| `PseudoAgentFactory` | Factory for creating PseudoAgents from auth sources (v0.8.0) |
| `ConstraintValidator` | Validates constraint tightening in delegations (v0.8.0) |
| `EATPMigration` | Database migration for EATP v0.8.0 columns |

### When to Use EATP

**Use EATP When**:
- ✅ Enterprise deployments with regulatory requirements (SOC2, GDPR, HIPAA)
- ✅ Multi-organization agent coordination
- ✅ Audit trail requirements for agent actions
- ✅ Capability-based access control
- ✅ Secure cross-agent messaging
- ✅ Integration with legacy systems

**Skip EATP When**:
- ❌ Development/testing environments (use standard BaseAgent)
- ❌ Single-tenant, single-agent applications
- ❌ Performance-critical paths without compliance needs

**Reference**: `kaizen.trust`, `apps/kailash-kaizen/docs/plans/01-eatp/`, `tests/integration/trust/`, `tests/unit/trust/`

## Examples Directory

**Location**: `apps/kailash-kaizen/examples/`

**Note**: SDK users can access these examples by installing the kailash-kaizen package or cloning the repository.

- **1-single-agent/** (10): simple-qa, chain-of-thought, rag-research, code-generation, memory-agent, react-agent, self-reflection, human-approval, resilient-fallback, streaming-chat
- **2-multi-agent/** (6): consensus-building, debate-decision, domain-specialists, producer-consumer, shared-insights, supervisor-worker
- **3-enterprise-workflows/** (5): compliance-monitoring, content-generation, customer-service, data-reporting, document-analysis
- **4-advanced-rag/** (5): agentic-rag, federated-rag, graph-rag, multi-hop-rag, self-correcting-rag
- **5-mcp-integration/** (3): agent-as-client, agent-as-server, auto-discovery-routing
- **8-multi-modal/** (6): image-analysis, audio-transcription, document-understanding, document-rag (basic_rag, advanced_rag, workflow_integration)

## Use This Specialist For

### Proactive Use Cases
- ✅ Implementing AI agents with BaseAgent
- ✅ Designing multi-agent coordination
- ✅ **Building autonomous agents with tool calling (v0.2.0)**
- ✅ **Implementing interactive agents with Control Protocol (v0.2.0)**
- ✅ **Universal tool integration across all agents (ADR-016)**
- ✅ **Production monitoring with observability stack (v0.5.0)** - tracing, metrics, logging, audit
- ✅ **Lifecycle management with hooks, state, interrupts (v0.5.0)** - event-driven architecture
- ✅ **Enterprise security with permission system (v0.5.0+)** - policy-based access control, budgets
- ✅ **Enterprise Agent Trust Protocol (v0.8.0)** - trust chains, TrustedAgent, secure messaging
- ✅ **Agent registry and discovery (v0.8.0)** - capability-based discovery, health monitoring
- ✅ **Cross-organization agent coordination (v0.8.0)** - A2A HTTP service, ESA integration
- ✅ Building multi-modal workflows (vision/audio/text)
- ✅ Optimizing agent prompts and signatures
- ✅ Writing agent tests with fixtures (use `llm_provider="mock"` for unit tests)
- ✅ Debugging agent execution and test failures
- ✅ Implementing RAG, CoT, or ReAct patterns
- ✅ Cost tracking and budget management
- ✅ **Systematic validation**: Evidence-based task completion verification

### Coordinate With
- **pattern-expert** - Core SDK workflow patterns
- **testing-specialist** - 3-tier testing strategy
- **framework-advisor** - Choosing Core/DataFlow/Nexus/Kaizen
- **mcp-specialist** - MCP integration

## Quick Start Template

```python
# 1. Define signature
class MySignature(Signature):
    input_field: str = InputField(description="...")
    output_field: str = OutputField(description="...")

# 2. Create domain config
@dataclass
class MyConfig:
    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"

# 3. Extend BaseAgent
class MyAgent(BaseAgent):
    def __init__(self, config: MyConfig):
        super().__init__(config=config, signature=MySignature())

    def process(self, input_data: str) -> dict:
        result = self.run(input_field=input_data)
        output = self.extract_str(result, "output_field", default="")
        self.write_to_memory(
            content={"input": input_data, "output": output},
            tags=["processing"]
        )
        return result

# 4. Execute
agent = MyAgent(config=MyConfig())
result = agent.process("input")
```

---

## For Basic Patterns

See the [Kaizen Skills](../../skills/04-kaizen/) for:
- Quick start guide ([`kaizen-quickstart-template`](../../skills/04-kaizen/kaizen-quickstart-template.md))
- BaseAgent basics ([`kaizen-baseagent-quick`](../../skills/04-kaizen/kaizen-baseagent-quick.md))
- Signatures ([`kaizen-signatures`](../../skills/04-kaizen/kaizen-signatures.md))
- Multi-agent patterns ([`kaizen-multi-agent-setup`](../../skills/04-kaizen/kaizen-multi-agent-setup.md))
- Chain of Thought ([`kaizen-chain-of-thought`](../../skills/04-kaizen/kaizen-chain-of-thought.md))
- RAG patterns ([`kaizen-rag-agent`](../../skills/04-kaizen/kaizen-rag-agent.md))
- Vision ([`kaizen-vision-processing`](../../skills/04-kaizen/kaizen-vision-processing.md))
- Audio ([`kaizen-audio-processing`](../../skills/04-kaizen/kaizen-audio-processing.md))

**This subagent focuses on**:
- Enterprise AI architecture
- Advanced multi-agent coordination
- Multi-modal pitfalls (CRITICAL production insights)
- UX improvements (config auto-extraction, memory helpers, result parsing)
- A2A protocol advanced use
- Custom agent development
- Performance optimization

**Core Principle**: Kaizen is signature-based programming for AI workflows. Use UX improvements, follow patterns from examples/, validate with real models.
