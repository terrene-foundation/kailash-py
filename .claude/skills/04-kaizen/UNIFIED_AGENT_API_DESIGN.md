# Unified Agent API Design

ONE entry point, configuration-driven behavior, progressive disclosure.

---

## Problem: Decision Paralysis

16 agent classes (SimpleQAAgent, ReActAgent, ChainOfThoughtAgent, RAGResearchAgent, ...) force users to pick before they understand.

## Solution: ONE Agent Class

```python
from kaizen import Agent

# Zero-config (Layer 1)
agent = Agent(model=os.environ["LLM_MODEL"])
result = agent.run("What is AI?")

# Configured (Layer 2)
agent = Agent(model=os.environ["LLM_MODEL"], agent_type="react")

# Expert override (Layer 3)
agent = Agent(model=os.environ["LLM_MODEL"], memory=CustomMemory())
```

**Principles**: ONE CLASS, CONFIGURATION-DRIVEN, EVERYTHING ENABLED, PROGRESSIVE DISCLOSURE, 100% BACKWARD COMPATIBLE.

---

## Feature Categorization

### Agent Behavior (`agent_type` parameter)

| Type         | Strategy    | Cycles | Tools               | Use Case                            |
| ------------ | ----------- | ------ | ------------------- | ----------------------------------- |
| `simple`     | single_shot | 1      | No                  | Basic Q&A, fact retrieval           |
| `cot`        | single_shot | 1      | No                  | Math, logic, complex reasoning      |
| `react`      | multi_cycle | 10     | Yes                 | Research, data gathering, APIs      |
| `rag`        | single_shot | 1      | Yes (vector_search) | Document Q&A, knowledge base        |
| `autonomous` | multi_cycle | 100    | Yes                 | Complex tasks, multi-step workflows |
| `reflection` | multi_cycle | 5      | No                  | Self-improvement, error correction  |

### Additional Modifiers

- `multimodal`: `["vision"]`, `["audio"]`, `["vision", "audio", "document"]`
- `streaming`: `True` for token-by-token output
- `batch_mode`: `True` for batch processing
- `require_approval`: `True` for human-in-loop

### Infrastructure (ON by default)

| Feature       | Default                 | User Control                                       | Expert Override                      |
| ------------- | ----------------------- | -------------------------------------------------- | ------------------------------------ |
| Memory        | BufferMemory, 10 turns  | `memory_turns=20`, `memory_type="persistent"`      | `memory=CustomMemory()`              |
| Tools         | All 12 builtin          | `tools=["read_file", "http_get"]` or `tools=False` | `tool_registry=CustomRegistry()`     |
| Observability | Tracing+metrics+logging | `observability=False`, `tracing_only=True`         | `hook_manager=CustomHooks()`         |
| Checkpointing | Every 5 steps           | `checkpoint_frequency=10`, `checkpointing=False`   | `state_manager=CustomStateManager()` |
| Cost Tracking | $1.00 limit             | `budget_limit_usd=5.0` or `None`                   | Always enabled (safety)              |
| MCP           | Off (opt-in)            | `mcp_servers=["server1"]`                          | `mcp_client=CustomClient()`          |

---

## 3-Layer API

### Layer 1: Zero-Config (99% of users)

```python
agent = Agent(model=os.environ["LLM_MODEL"])
result = agent.run("Explain quantum computing")
```

Auto-enabled: memory (10 turns), tools (12 builtin), observability, checkpointing, cost tracking ($1), rich output, error handling (3 retries), A2A capability cards.

### Layer 2: Configuration (Power Users)

```python
agent = Agent(
    model=os.environ["LLM_MODEL"],
    agent_type="react",
    memory_turns=20,
    memory_type="persistent",
    tools=["read_file", "http_get"],
    budget_limit_usd=5.0,
    max_cycles=10,
    temperature=0.7,
    verbosity="verbose",
)
result = agent.run("Research AI trends and create a report")
```

**Config categories**: Agent behavior (`agent_type`, `workflow`, `multimodal`, `max_cycles`, `temperature`), Memory (`memory_turns`, `memory_type`, `memory_backend`, `shared_memory`), Tools (`tools`, `auto_approve_safe`, `require_approval`), Infrastructure (`budget_limit_usd`, `checkpoint_frequency`, `observability`), UX (`rich_output`, `verbosity`, `streaming`).

### Layer 3: Expert Override (1% of users)

```python
agent = Agent(
    model=os.environ["LLM_MODEL"],
    agent_type="react",
    memory=CustomMemorySystem(backend="redis", cluster_nodes=["n1", "n2"]),
    hook_manager=CustomHookManager(exporters=["datadog"], sampling_rate=0.1),
    state_manager=CustomStateManager(storage_backend="s3", bucket="checkpoints"),
)
```

**Override points**: `memory`, `tool_registry`, `hook_manager`, `state_manager`, `control_protocol`, `mcp_client`, `approval_callback`, `error_handler`.

---

## Workflow Integration

```python
# Create workers
researcher = Agent(model=os.environ["LLM_MODEL"], agent_type="react", agent_id="researcher")
analyst = Agent(model=os.environ["LLM_MODEL"], agent_type="cot", agent_id="analyst")
writer = Agent(model=os.environ["LLM_MODEL"], agent_type="simple", agent_id="writer")

# Create supervisor with workflow
supervisor = Agent(
    model=os.environ["LLM_MODEL"],
    workflow="supervisor_worker",
    workers=[researcher, analyst, writer],
    workflow_config={"selection_strategy": "semantic", "parallel_execution": True}
)
result = supervisor.run("Research AI trends, analyze data, write report")
```

**Workflow types**: `supervisor_worker` (delegation), `consensus` (multi-agent agreement), `debate` (adversarial), `sequential` (pipeline), `handoff` (dynamic routing).

---

## Smart Defaults Philosophy

**ON by default** if: safety (cost, errors), productivity (memory, tools), observability, resilience (checkpoints), better UX.

**OFF by default** if: experimental (MCP, control protocol), changes behavior significantly (streaming), specialized mode (batch), requires external setup.

```python
# Disable everything optional
agent = Agent(
    model=os.environ["LLM_MODEL"],
    memory=False, tools=False, observability=False,
    checkpointing=False, rich_output=False, budget_limit_usd=None,
)
```

---

## Agent Class Signature

```python
class Agent:
    def __init__(
        self,
        model: str,                                     # REQUIRED
        provider: str = "openai",
        agent_id: Optional[str] = None,
        agent_type: Literal["simple","cot","react","rag","autonomous","reflection"] = "simple",
        workflow: Optional[Literal["supervisor_worker","consensus","debate","sequential","handoff"]] = None,
        multimodal: Optional[List[Literal["vision","audio","document"]]] = None,
        memory_turns: int = 10,
        memory_type: Literal["buffer","persistent","summary","vector","knowledge_graph"] = "buffer",
        tools: Union[Literal["all"], List[str], Literal[False]] = "all",
        max_cycles: int = 10,
        temperature: float = 0.7,
        budget_limit_usd: Optional[float] = 1.0,
        checkpoint_frequency: int = 5,
        observability: bool = True,
        rich_output: bool = True,
        verbosity: Literal["quiet","normal","verbose"] = "normal",
        streaming: bool = False,
        workers: Optional[List['Agent']] = None,
        # Expert overrides
        signature: Optional[Signature] = None,
        memory: Optional[BaseMemory] = None,
        tool_registry: Optional[ToolRegistry] = None,
        hook_manager: Optional[HookManager] = None,
        state_manager: Optional[StateManager] = None,
        **kwargs
    ): ...

    def run(self, *args, **kwargs) -> Dict[str, Any]: ...
    async def run_async(self, *args, **kwargs) -> Dict[str, Any]: ...
```

---

## Migration: Before/After

### Simple Q&A: 18 lines -> 4

```python
# BEFORE
from kaizen_agents.agents import SimpleQAAgent
config = QAConfig(llm_provider="openai", model=os.environ["LLM_MODEL"], temperature=0.7)
agent = SimpleQAAgent(llm_provider=config.llm_provider, model=config.model, temperature=config.temperature)
result = agent.ask("What is AI?")

# AFTER
from kaizen import Agent
agent = Agent(model=os.environ["LLM_MODEL"])
result = agent.run("What is AI?")
```

### Multi-Agent Workflow: 47 lines -> 11

```python
# BEFORE: Separate SharedMemoryPool, 4 SimpleQAAgent instances, SupervisorWorkerPattern setup
# AFTER:
researcher = Agent(model=os.environ["LLM_MODEL"], agent_type="react", agent_id="researcher")
analyst = Agent(model=os.environ["LLM_MODEL"], agent_type="cot", agent_id="analyst")
writer = Agent(model=os.environ["LLM_MODEL"], agent_type="simple", agent_id="writer")
supervisor = Agent(model=os.environ["LLM_MODEL"], workflow="supervisor_worker", workers=[researcher, analyst, writer])
result = supervisor.run("Research, analyze, and write report on AI")
```

### Multi-Modal: 33 lines -> 9

```python
# BEFORE: Separate VisionAgent, TranscriptionAgent, MultiModalAgent with individual configs
# AFTER:
agent = Agent(model=os.environ["LLM_MODEL"], multimodal=["vision", "audio"])
result = agent.run(image="video_frame.png", audio="audio.mp3", question="What is happening?")
```

---

## Migration Strategy

1. **Phase 1** (Week 1-2): Implement `Agent` class, 100% test coverage
2. **Phase 2** (Week 3): Documentation, migration guide, 20+ examples
3. **Phase 3** (Week 4): Soft deprecation warnings on specialized classes
4. **Phase 4** (Month 2-6): Dual API support, refactor specialized classes as thin wrappers
5. **Recommendation**: Keep specialized classes as thin wrappers indefinitely (no breaking changes)

Existing code continues to work:

```python
# Still works
from kaizen_agents.agents import SimpleQAAgent
agent = SimpleQAAgent(llm_provider="openai", model=os.environ["LLM_MODEL"])
```
