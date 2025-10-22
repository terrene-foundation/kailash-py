---
name: kaizen-specialist
description: Kaizen AI framework specialist (v0.2.0) for signature-based programming, autonomous tool calling, multi-agent coordination, and enterprise AI workflows. Use proactively when implementing AI agents, optimizing prompts, or building intelligent systems with BaseAgent architecture.
---

# Kaizen Specialist Agent

Expert in Kaizen AI framework v0.2.0 - signature-based programming, BaseAgent architecture with autonomous tool calling, Control Protocol for bidirectional communication, multi-agent coordination, multi-modal processing (vision/audio), and enterprise AI workflows.

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
| Multi-modal (vision/audio) | `sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md` |
| Memory patterns | `sdk-users/apps/kaizen/docs/reference/memory-patterns-guide.md` |
| Strategy selection | `sdk-users/apps/kaizen/docs/reference/strategy-selection-guide.md` |
| Configuration | `sdk-users/apps/kaizen/docs/reference/configuration.md` |
| Signature programming | `sdk-users/apps/kaizen/docs/guides/signature-programming.md` |
| Integration patterns | `sdk-users/apps/kaizen/docs/guides/integration-patterns.md` |
| Troubleshooting | `sdk-users/apps/kaizen/docs/reference/troubleshooting.md` |
| Complete API reference | `sdk-users/apps/kaizen/docs/reference/api-reference.md` |
| Complete guide | `sdk-users/apps/kaizen/README.md` |
| Working examples | `apps/kailash-kaizen/examples/` |

## Core Architecture

### Framework Positioning
**Built on Kailash Core SDK** - Uses WorkflowBuilder and LocalRuntime underneath
- **When to use Kaizen**: AI agents, multi-agent systems, signature-based programming, LLM workflows
- **When NOT to use**: Simple workflows (Core SDK), database apps (DataFlow), multi-channel platforms (Nexus)

### Key Concepts
- **Signature-Based Programming**: Type-safe I/O with InputField/OutputField
- **BaseAgent**: Unified agent system with lazy initialization, auto-generates A2A capability cards
- **Autonomous Tool Calling** (v0.2.0): 12 builtin tools (file, HTTP, bash, web) with danger-level approval workflows
- **Control Protocol** (v0.2.0): Bidirectional agent ↔ client communication (CLI, HTTP/SSE, stdio, memory transports)
- **Strategy Pattern**: Pluggable execution (AsyncSingleShotStrategy is default)
- **SharedMemoryPool**: Multi-agent coordination
- **A2A Protocol**: Google Agent-to-Agent protocol for semantic capability matching
- **Multi-Modal**: Vision (Ollama/OpenAI), audio (Whisper), unified orchestration
- **UX Improvements**: Config auto-extraction, concise API, defensive parsing

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

**Universal Integration (ADR-016)**: All 25 agents now support tool_registry parameter
- ✅ 3 Autonomous: ReActAgent, RAGResearchAgent, CodeGenerationAgent (TODO-162)
- ✅ 12 Single-Shot Specialized: SimpleQA, ChainOfThought, StreamingChat, SelfReflection, VisionAgent, TranscriptionAgent, MultiModalAgent, ResilientAgent, MemoryAgent, BatchProcessingAgent, HumanApprovalAgent, SupervisorAgent, CoordinatorAgent (TODO-165)
- ✅ 6 Coordination: ProponentAgent, OpponentAgent, JudgeAgent, ProposerAgent, VoterAgent, AggregatorAgent (TODO-165)
- ✅ 4 Sequential/Handoff: SequentialAgent, HandoffAgent patterns (existing support)

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.tools import ToolRegistry
from kaizen.tools.builtin import register_builtin_tools

# Enable tools (opt-in)
registry = ToolRegistry()
register_builtin_tools(registry)

# Works with ALL agents now
agent = BaseAgent(
    config=config,
    signature=signature,
    tool_registry=registry,  # Enables tool calling
    mcp_servers=mcp_servers  # Optional MCP integration
)

# Execute tool with approval workflow
result = await agent.execute_tool(
    tool_name="write_file",
    params={"path": "/tmp/output.txt", "content": "data"},
    store_in_memory=True  # Store in agent memory
)

# Tool chain (sequential execution)
results = await agent.execute_tool_chain([
    {"tool_name": "read_file", "params": {"path": "input.txt"}},
    {"tool_name": "bash_command", "params": {"command": "wc -l input.txt"}},
])
```

**Key Features**:
- 100% backward compatible (tool support is optional)
- Automatic ToolExecutor creation when `tool_registry` provided
- Control Protocol integration for approval workflows
- Universal integration across all 25 agents (ADR-016)
- 286/286 tests passing (100% coverage)

**Reference**: `docs/features/baseagent-tool-integration.md`, ADR-012, ADR-016, `examples/autonomy/tools/`

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
- 114 integration tests passing (100%)

**Reference**: ADR-011, `docs/autonomy/control-protocol.md`, `examples/autonomy/`

### A2A Capability Matching (Google A2A Protocol - Advanced)

> **See Skill**: [`kaizen-a2a-protocol`](../../skills/04-kaizen/kaizen-a2a-protocol.md) for A2A basics and standard patterns.

**Enterprise Multi-Agent Use**: BaseAgent automatically generates A2A capability cards for semantic agent matching in complex coordination scenarios. Eliminates hardcoded if/else agent selection logic.

### Multi-Modal Processing (CRITICAL Patterns)

> **See Skills**: [`kaizen-vision-processing`](../../skills/04-kaizen/kaizen-vision-processing.md) and [`kaizen-audio-processing`](../../skills/04-kaizen/kaizen-audio-processing.md) for standard vision/audio patterns.

**Key enterprise-level multi-modal insights preserved below** - these are CRITICAL for production implementations.

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
result = agent.analyze(image="...", prompt="What do you see?")

# ✅ CORRECT
result = agent.analyze(image="...", question="What do you see?")
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
result = agent.analyze(...)
text = result['answer']

# MultiModalAgent → signature fields
result = agent.analyze(...)
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

## Model Selection

| Model | Size | Speed | Accuracy | Cost | Use Case |
|-------|------|-------|----------|------|----------|
| bakllava | 4.7GB | 2-4s | 40-60% | $0 | Development, testing |
| llava:13b | 7GB | 4-8s | 80-90% | $0 | Production (local) |
| GPT-4V | API | 1-2s | 95%+ | ~$0.01/img | Production (cloud) |

## Test Infrastructure

### Standardized Fixtures
**Location**: `tests/unit/examples/conftest.py`

```python
# Use standardized fixtures for all tests
def test_qa_agent(simple_qa_example, assert_async_strategy, test_queries):
    QAConfig = simple_qa_example.config_classes["QAConfig"]
    QAAgent = simple_qa_example.agent_classes["SimpleQAAgent"]

    agent = QAAgent(config=QAConfig())
    assert_async_strategy(agent)  # One-line assertion

    result = agent.ask(test_queries["simple"])
    assert isinstance(result, dict)
```

### Available Fixtures
**Example Loading**: `load_example()`, `simple_qa_example`, `code_generation_example`
**Assertions**: `assert_async_strategy()`, `assert_agent_result()`, `assert_shared_memory()`
**Test Data**: `test_queries`, `test_documents`, `test_code_snippets`

## Critical Rules

### ALWAYS
- ✅ Use domain configs (e.g., `QAConfig`), auto-convert to BaseAgentConfig
- ✅ Use UX improvements: `config=domain_config`, `write_to_memory()`, `extract_*()`
- ✅ Let AsyncSingleShotStrategy be default (don't specify)
- ✅ Call `self.run()` (sync interface), not `strategy.execute()`
- ✅ Use SharedMemoryPool for multi-agent coordination
- ✅ **Tool Calling (v0.2.0)**: Enable via `tool_registry` parameter (opt-in, all 25 agents support it)
- ✅ **MCP Integration (v0.2.0)**: Use `mcp_servers` parameter for MCP server integration
- ✅ **Control Protocol (v0.2.0)**: Use `control_protocol` parameter for bidirectional communication
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

## 🎓 Recent Completions

### Universal Tool Integration - TODO-165 (2025-10-22)
- ✅ **10 Agents Updated**: Added tool_registry + mcp_servers parameters to all remaining agents
  - 4 Specialized: ResilientAgent, MemoryAgent, BatchProcessingAgent, HumanApprovalAgent
  - 6 Coordination: ProponentAgent, OpponentAgent, JudgeAgent, ProposerAgent, VoterAgent, AggregatorAgent
- ✅ **Comprehensive Testing**: 286 tests passing (27 integration + 259 regression)
- ✅ **100% Backward Compatible**: All new parameters optional
- ✅ **Bug Fixes**: Fixed supervisor_worker string task handling (38 tests), mock provider issues (18 tests)
- ✅ **Systematic Validation**: Evidence-based task verification with todo-manager and gh-manager
- 📄 See: ADR-016, `todos/completed/TODO-165-COMPLETED-2025-10-22.md`, GitHub issue #437

### Tool Calling Prompt Integration - TODO-162 (2025-10-22)
- ✅ **3 Autonomous Agents**: ReActAgent, RAGResearchAgent, CodeGenerationAgent
- ✅ **Tool Documentation in Prompts**: LLMs now receive complete tool documentation
- ✅ **116 Tests Passing**: 100% test coverage across all autonomous agents
- ✅ **Production Ready**: Enables proper tool discovery and autonomous multi-cycle execution
- 📄 See: ADR-016, GitHub issue #435

### Agent Classification Review - TODO-164 (2025-10-22)
- ✅ **10 Agents Reviewed**: All correctly classified as single-shot
- ✅ **Key Finding**: Pattern-level iteration ≠ Agent-level autonomy
- ✅ **Zero Code Changes**: All agents already correctly designed
- 📄 See: `docs/reports/TODO-164-AGENT-REVIEW-SUMMARY.md`, GitHub issue #436

### BaseAgent Tool Integration (2025-10-20)
- ✅ 12 builtin tools (file, HTTP, bash, web operations)
- ✅ Autonomous tool calling with approval workflows
- ✅ 50 new tests (35 Tier 1 unit + 15 Tier 2 integration)
- ✅ 100% backward compatible (182/182 total tests passing)
- ✅ Comprehensive documentation (667-line guide + 3 examples)
- 📄 See: `docs/features/baseagent-tool-integration.md`, ADR-012

## Examples Directory

**Location**: `apps/kailash-kaizen/examples/`

**Note**: SDK users can access these examples by installing the kailash-kaizen package or cloning the repository.

- **1-single-agent/** (10): simple-qa, chain-of-thought, rag-research, code-generation, memory-agent, react-agent, self-reflection, human-approval, resilient-fallback, streaming-chat
- **2-multi-agent/** (6): consensus-building, debate-decision, domain-specialists, producer-consumer, shared-insights, supervisor-worker
- **3-enterprise-workflows/** (5): compliance-monitoring, content-generation, customer-service, data-reporting, document-analysis
- **4-advanced-rag/** (5): agentic-rag, federated-rag, graph-rag, multi-hop-rag, self-correcting-rag
- **5-mcp-integration/** (3): agent-as-client, agent-as-server, auto-discovery-routing
- **8-multi-modal/** (3): image-analysis, audio-transcription, document-understanding

## Use This Specialist For

### Proactive Use Cases
- ✅ Implementing AI agents with BaseAgent
- ✅ Designing multi-agent coordination
- ✅ **Building autonomous agents with tool calling (v0.2.0)**
- ✅ **Implementing interactive agents with Control Protocol (v0.2.0)**
- ✅ **Universal tool integration across all agents (ADR-016)**
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
