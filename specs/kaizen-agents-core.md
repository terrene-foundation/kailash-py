# Kailash Kaizen Agents Specification — Core

Version: 0.9.2

Parent domain: Kailash `kaizen-agents` package (Layer 2 — ENGINES). This file covers package identity, Delegate (primary entry point), AgentLoop, streaming adapter protocol, wrapper stack, Delegate configuration, built-in tools, Delegate subsystems, error taxonomy, and security considerations. See also `kaizen-agents-patterns.md` and `kaizen-agents-governance.md`.

Domain truth document for the `kaizen-agents` package (Layer 2 — ENGINES). This specification is authoritative. When the code and this document disagree, the code is the source of truth and this document must be updated.

## 1. Package Identity and Layer Position

`kaizen-agents` is Layer 2 (ENGINES) built on top of `kailash-kaizen` (Layer 1 — PRIMITIVES). It adds:

- **Delegate**: Autonomous agent execution facade with streaming, tool calling, budget tracking
- **GovernedSupervisor**: PACT-governed L3 orchestration with plan execution, audit trails, budget enforcement
- **Specialized agents**: ReAct, RAG, Tree-of-Thought, Chain-of-Thought, Vision, Audio, streaming, batch, planning, memory, self-reflection, resilient, human-approval, code-generation, simple-QA, PEV
- **Multi-agent patterns**: Debate, Supervisor-Worker, Consensus, Ensemble, Handoff, Sequential, Parallel, Blackboard, Meta-Controller
- **Journey orchestration**: Declarative multi-pathway user journeys with intent detection, context accumulation, session persistence
- **Governance subsystems**: Accountability, clearance, cascade, vacancy, dereliction, bypass, budget, cost model
- **Audit integration**: EATP hash-chain audit trail
- **Message transport**: Typed inter-agent messaging via SDK MessageRouter
- **Agent lifecycle management**: Spawn, terminate, state transitions via SDK AgentFactory

### 1.1 Relationship to kailash-kaizen (Layer 1)

Layer 1 provides: `BaseAgent`, `BaseAgentConfig`, `Signature`, `InputField`, `OutputField`, `MultiCycleStrategy`, `AsyncSingleShotStrategy`, `SharedMemoryPool`, `AgentFactory`, `AgentInstanceRegistry`, `MessageRouter`, `CostTracker`.

Layer 2 (this package) composes Layer 1 primitives into opinionated engines. Layer 2 never reimplements Layer 1 primitives; it wraps, composes, and extends them.

### 1.2 Public API Surface

```python
from kaizen_agents import Delegate                    # Primary entry point
from kaizen_agents import GovernedSupervisor           # L3 orchestration
from kaizen_agents import Agent                        # Canonical async Agent API
from kaizen_agents import ReActAgent, Pipeline         # Convenience re-exports
from kaizen_agents import (                            # Multi-agent patterns
    BaseMultiAgentPattern,
    SupervisorWorkerPattern, ConsensusPattern,
    DebatePattern, HandoffPattern,
    SequentialPipelinePattern,
    create_supervisor_worker_pattern,
    create_consensus_pattern,
    create_debate_pattern,
    create_handoff_pattern,
    create_sequential_pipeline,
)
```

---

## 2. Delegate

The Delegate is the primary entry point for autonomous AI execution. It is a composition facade (not an inheritance hierarchy) that stacks wrappers according to SPEC-05.

### 2.1 Architecture

```
AgentLoop (via _LoopAgent) -> [L3GovernedAgent] -> [MonitoredAgent]
```

Only wrappers whose parameters are supplied are stacked. The `run()` method drives the `AgentLoop` directly for streaming, using the wrapper stack for governance validation and cost tracking.

### 2.2 Progressive Disclosure Layers

**Layer 1 (minimal)**:

```python
delegate = Delegate(model="claude-sonnet-4-20250514")
async for event in delegate.run("what files are here?"):
    print(event)
```

**Layer 2 (configured)**:

```python
delegate = Delegate(
    model="claude-sonnet-4-20250514",
    tools=["read_file", "grep", "bash"],
    system_prompt="You are a code reviewer.",
    max_turns=20,
)
```

**Layer 3 (governed)**:

```python
delegate = Delegate(
    model="claude-sonnet-4-20250514",
    budget_usd=10.0,
    envelope=constraint_envelope,
)
```

### 2.3 Constructor Parameters

| Parameter       | Type                                | Default | Description                                                      |
| --------------- | ----------------------------------- | ------- | ---------------------------------------------------------------- |
| `model`         | `str`                               | `""`    | LLM model name. Falls back to `DEFAULT_LLM_MODEL` env var.       |
| `signature`     | `type[Signature] \| None`           | `None`  | Optional Signature class for structured I/O.                     |
| `tools`         | `ToolRegistry \| list[str] \| None` | `None`  | Tool registry or list of tool names.                             |
| `system_prompt` | `str \| None`                       | `None`  | Override default system prompt.                                  |
| `temperature`   | `float \| None`                     | `None`  | LLM temperature override.                                        |
| `max_tokens`    | `int \| None`                       | `None`  | Max completion tokens.                                           |
| `max_turns`     | `int`                               | `50`    | Maximum tool-calling loops per `run()` call.                     |
| `mcp_servers`   | `list[dict] \| None`                | `None`  | MCP server configurations (discovery deferred to first `run()`). |
| `budget_usd`    | `float \| None`                     | `None`  | USD budget cap. Must be finite and non-negative.                 |
| `envelope`      | `ConstraintEnvelope \| None`        | `None`  | L3 governance envelope.                                          |
| `api_key`       | `str \| None`                       | `None`  | API key for the LLM provider.                                    |
| `base_url`      | `str \| None`                       | `None`  | Base URL override for the LLM provider.                          |
| `inner_agent`   | `BaseAgent \| None`                 | `None`  | Pre-built agent escape hatch (bypasses internal construction).   |
| `adapter`       | `StreamingChatAdapter \| None`      | `None`  | Pre-built streaming adapter.                                     |
| `config`        | `KzConfig \| None`                  | `None`  | Pre-built config (overrides model, max_turns, etc.).             |

### 2.4 Constructor Invariant: No IO

The constructor MUST be synchronous and free of any network, filesystem, or subprocess calls. MCP server discovery is deferred to the first `run()` call. Violating this raises `ConstructorIOError`.

### 2.5 run() Method

```python
async def run(self, prompt: str) -> AsyncGenerator[DelegateEvent, None]
```

Yields typed `DelegateEvent` instances. Consumers pattern-match on event type:

```python
async for event in delegate.run("analyse this codebase"):
    match event:
        case TextDelta(text=t):
            print(t, end="")
        case ToolCallStart(name=n):
            show_spinner(n)
        case ToolCallEnd(name=n, result=r):
            hide_spinner(n)
        case TurnComplete(text=t):
            render_final(t)
        case BudgetExhausted():
            warn_user()
        case ErrorEvent(error=e):
            handle_error(e)
```

**Preconditions**: Delegate must not be closed. Prompt must not be empty. Budget must not be exhausted.

**Error handling**: All exceptions during execution are caught and yielded as `ErrorEvent`. The generator does not raise.

### 2.6 run_sync() Method

```python
def run_sync(self, prompt: str) -> str
```

Synchronous convenience wrapper. Collects all text deltas and returns the complete response string. Raises `RuntimeError` if called from inside a running event loop (Jupyter, FastAPI handler, Nexus channel, async test).

### 2.7 Budget Tracking

When `budget_usd` is set:

1. Cost is estimated per turn using model-prefix heuristics against a built-in cost table.
2. `_consumed_usd` accumulates across turns.
3. Before each LLM call, the budget check callback fires. If exhausted, the loop yields `"[Budget exhausted -- stopping.]"` which the Delegate converts to a `BudgetExhausted` event.
4. If `MonitoredAgent` wrapper is in the stack (kaizen.providers.cost available), it provides a second budget enforcement layer using the SDK's `CostTracker`.

**Cost estimation table** (per 1M tokens, conservative):

| Model prefix | Input rate | Output rate |
| ------------ | ---------- | ----------- |
| `claude-`    | $3.00      | $15.00      |
| `gpt-4o`     | $2.50      | $10.00      |
| `gpt-4`      | $30.00     | $60.00      |
| `gpt-5`      | $10.00     | $30.00      |
| `o1`         | $15.00     | $60.00      |
| `o3`         | $12.00     | $48.00      |
| `o4`         | $12.00     | $48.00      |
| `gemini-`    | $1.25      | $5.00       |
| Default      | $3.00      | $15.00      |

### 2.8 Delegate Event Types

All events inherit from `DelegateEvent` which carries `event_type` (discriminator string) and `timestamp` (monotonic).

| Event             | Fields                                                   | When                                           |
| ----------------- | -------------------------------------------------------- | ---------------------------------------------- |
| `TextDelta`       | `text: str`                                              | Incremental text fragment from the model       |
| `ToolCallStart`   | `call_id: str`, `name: str`                              | Tool call begins streaming                     |
| `ToolCallEnd`     | `call_id: str`, `name: str`, `result: str`, `error: str` | Tool call completes                            |
| `TurnComplete`    | `text: str`, `usage: dict[str, int]`                     | Model finishes responding (no more tool calls) |
| `BudgetExhausted` | `budget_usd: float`, `consumed_usd: float`               | Budget cap exceeded                            |
| `ErrorEvent`      | `error: str`, `details: dict`                            | Error occurred during execution                |

### 2.9 Lifecycle Methods

- `interrupt()` — signals the loop to stop after the current operation.
- `close()` — marks the Delegate as closed; subsequent `run()` calls yield `ErrorEvent`.

---

## 3. AgentLoop

The autonomous model-driven loop at the core of the Delegate. The model decides what to do; tool calling is native; there is no structured thought extraction.

### 3.1 Loop Algorithm

```
LOOP:
  1. Assemble prompt (system + context + conversation + tool defs)
  2. Stream LLM response
  3. If tool calls -> execute tools (parallel for independent) -> append results -> loop
  4. If text only -> yield to user
  5. Repeat until user exits or max_turns reached
```

**Architectural invariant**: The core loop MUST NOT use Kaizen Pipeline primitives. Pipelines are for user-space application construction, not core orchestration.

### 3.2 ToolRegistry

```python
class ToolRegistry:
    def register(name, description, parameters, executor) -> None
    def get_openai_tools() -> list[dict]
    async def execute(name, arguments) -> str
    def has_tool(name) -> bool
    def tool_names -> list[str]
```

Tools are registered with a name, JSON Schema parameters, and an async executor function. The registry produces OpenAI-compatible function-calling format for the LLM.

**Tool collision**: `ToolRegistryCollisionError` is raised when two tools with the same name are registered from different sources.

### 3.3 Tool Hydration

When the tool count exceeds the hydrator's threshold, a `ToolHydrator` activates:

1. A `search_tools` meta-tool is injected into the registry.
2. Only a subset of tools is sent to the LLM per turn.
3. The model discovers additional tools by calling `search_tools`.
4. Hydrated tools are force-looked-up during execution even if not in the active set.

### 3.4 Conversation Management

`Conversation` maintains a flat list of messages in OpenAI format. Supports system, user, assistant (with optional tool_calls), and tool result messages. Provides `compact()` for pruning older messages while preserving recent turns.

### 3.5 Usage Tracking

`UsageTracker` accumulates prompt_tokens, completion_tokens, total_tokens, and turn count across a session.

### 3.6 Tool Execution

Independent tool calls are executed in parallel via `asyncio.gather()`. Results are appended to the conversation as tool messages. If a tool call fails:

- `json.JSONDecodeError` on arguments: returns error result, logs warning.
- `KeyError` (unknown tool): returns error result, logs warning.
- Other exceptions: returns safe error message (no stack trace leaked to the model), logs full traceback.
- `BaseException` from `asyncio.gather`: injects a synthetic error result to keep the conversation valid.

---

## 4. Streaming Adapter Protocol

### 4.1 StreamingChatAdapter Protocol

```python
@runtime_checkable
class StreamingChatAdapter(Protocol):
    async def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs,
    ) -> AsyncGenerator[StreamEvent, None]: ...
```

All LLM provider adapters implement this protocol. The AgentLoop never imports a provider SDK directly.

### 4.2 StreamEvent

```python
@dataclass
class StreamEvent:
    event_type: str       # "text_delta", "tool_call_start", "tool_call_delta", "tool_call_end", "done"
    content: str          # Accumulated text
    tool_calls: list[dict]  # Accumulated tool calls (OpenAI-compatible format)
    finish_reason: str | None
    model: str
    usage: dict[str, int]
    delta_text: str       # Incremental text fragment
```

### 4.3 Available Adapters

| Adapter            | Module                                | Provider                            |
| ------------------ | ------------------------------------- | ----------------------------------- |
| `OpenAIAdapter`    | `delegate.adapters.openai_adapter`    | OpenAI, OpenAI-compatible endpoints |
| `AnthropicAdapter` | `delegate.adapters.anthropic_adapter` | Anthropic Claude                    |
| `GoogleAdapter`    | `delegate.adapters.google_adapter`    | Google Gemini                       |
| `OllamaAdapter`    | `delegate.adapters.ollama_adapter`    | Ollama local models                 |

Provider selection is configuration branching via `delegate.adapters.registry.get_adapter_for_model()`.

---

## 5. Wrapper Stack

### 5.1 Canonical Stacking Order

```
BaseAgent -> L3GovernedAgent -> MonitoredAgent -> StreamingAgent
```

Lower priority = more innermost. Enforced by `WrapperBase`:

- `DuplicateWrapperError` if the same wrapper type appears twice.
- `WrapperOrderError` if wrappers are applied out of canonical order.

### 5.2 WrapperBase Contract

- `_inner` is ALWAYS called (verified by `_inner_called` flag).
- `get_parameters()` proxies to inner agent.
- `to_workflow()` proxies to inner agent.
- `isinstance(wrapper, BaseAgent)` is True.
- `innermost` property walks the stack to the non-wrapper base agent.

### 5.3 L3GovernedAgent

Governance wrapper that enforces `ConstraintEnvelope` BEFORE the LLM call. A rejected request never reaches the model (saves cost).

**Constraint dimensions evaluated**:

- **Financial**: Budget limits, per-action cost limits. NaN/Inf values rejected.
- **Operational**: Allowed/blocked action lists. Deny wins over allow.
- **Posture ceiling**: Agent posture clamped to envelope ceiling.

**Security**: A `_ProtectedInnerProxy` blocks direct access to the raw inner agent via `.inner._inner`. Only read-only attributes (`config`, `signature`, `get_parameters`, `to_workflow`, `to_workflow_node`) are exposed.

On rejection, `GovernanceRejectedError` is raised with `dimension` and `detail` attributes. The `rejection_count` property tracks how many requests have been rejected.

### 5.4 MonitoredAgent

Cost monitoring wrapper using `CostTracker` from `kaizen.providers.cost`. Tracks token usage per model and enforces budget via `BudgetExhaustedError`.

---

## 22. Delegate Configuration

### 22.1 KzConfig

Located at `delegate/config/loader.py`. Core configuration for the agent loop.

Key fields: `model`, `max_turns`, `temperature`, `max_tokens`, `provider`, `effort_level`.

### 22.2 Effort Levels

`delegate/config/effort.py` defines effort levels that control model behavior (temperature, token limits, etc.).

### 22.3 Execution Policy

`delegate/config/exec_policy.py` defines execution policies for tool usage and autonomy.

### 22.4 Permissions

`delegate/config/permissions.py` defines permission models for tool and filesystem access.

---

## 23. Built-in Tools

### 23.1 Available Tools

| Tool           | Module                         | Description                       |
| -------------- | ------------------------------ | --------------------------------- |
| `bash`         | `delegate/tools/bash_tool.py`  | Execute shell commands            |
| `read_file`    | `delegate/tools/file_read.py`  | Read file contents                |
| `write_file`   | `delegate/tools/file_write.py` | Write file contents               |
| `edit_file`    | `delegate/tools/file_edit.py`  | Edit file with string replacement |
| `glob`         | `delegate/tools/glob_tool.py`  | File pattern matching             |
| `grep`         | `delegate/tools/grep_tool.py`  | Content search                    |
| `search_tools` | `delegate/tools/search.py`     | Meta-tool for tool hydration      |

### 23.2 Tool Hydration

`delegate/tools/hydrator.py` — `ToolHydrator` manages large tool sets by presenting only a subset to the LLM and allowing discovery via the `search_tools` meta-tool.

---

## 24. Delegate Subsystems

### 24.1 MCP Integration

`delegate/mcp.py` — MCP server configuration and tool discovery, deferred to first `run()` call.

### 24.2 Conversation Compaction

`delegate/compact.py` — Compacts conversation history by pruning older messages and replacing with summaries while preserving recent turns.

### 24.3 Hooks

`delegate/hooks.py` — Hook system for extending Delegate behavior at lifecycle points.

### 24.4 Commands

`delegate/commands.py` — Built-in slash commands for the interactive CLI.

### 24.5 Builtins

`delegate/builtins.py` — Built-in tool registrations.

### 24.6 Print Mode

`delegate/print_mode.py` — Non-interactive single-prompt execution mode.

---

## 27. Error Taxonomy

| Error                        | Module                                          | When                                    |
| ---------------------------- | ----------------------------------------------- | --------------------------------------- |
| `ConstructorIOError`         | `delegate/delegate.py`                          | IO detected in Delegate constructor     |
| `ToolRegistryCollisionError` | `delegate/delegate.py`                          | Duplicate tool name registration        |
| `GovernanceRejectedError`    | `governed_agent.py`                             | Envelope constraint violation           |
| `BudgetExhaustedError`       | `monitored_agent.py`                            | Budget cap exceeded                     |
| `DuplicateWrapperError`      | `wrapper_base.py`                               | Same wrapper type applied twice         |
| `WrapperOrderError`          | `wrapper_base.py`                               | Wrappers applied out of canonical order |
| `DelegationCapExceeded`      | `patterns/patterns/supervisor_worker.py`        | Delegation count exceeds cap            |
| `StreamTimeoutError`         | `events.py`                                     | Streaming operation timeout             |
| `GovernanceHeldError`        | `supervisor.py` (from kailash.trust.pact.agent) | External governance verdict: hold       |

---

## 28. Security Considerations

1. **Constructor IO ban**: No network, filesystem, or subprocess calls in `Delegate.__init__()`.
2. **Protected inner proxy**: `L3GovernedAgent` blocks access to raw inner agent via `_ProtectedInnerProxy`.
3. **NaN/Inf validation**: All financial fields validated with `math.isfinite()`.
4. **Delegation depth limiting**: `max_total_delegations` prevents runaway recursive delegation.
5. **Tool argument sanitization**: Audit trail records argument keys only, not values.
6. **Session file permissions**: 0o600 files, 0o700 directories, path traversal prevention.
7. **Hash chain integrity**: Audit records use SHA-256 chain with timing-safe comparison.
8. **Budget enforcement**: Pre-execution budget check prevents cost overruns.
9. **Governance before LLM**: Rejected requests never reach the model (cost savings).
10. **Read-only views**: All Layer 3 governance subsystem properties return read-only proxies.
11. **Default-deny tools**: Empty tool list by default (PACT Rule 5).
12. **Fail-closed governance**: All error paths in governance checks result in rejection, never permissive fallback.
