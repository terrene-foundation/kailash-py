# kz CLI Architecture Specification

**Version**: 1.0
**Date**: 2026-03-21
**Status**: Design specification -- ready for implementation
**Authors**: deep-analyst (architecture), requirements-analyst (structure)
**Complexity Score**: 29 (Complex) -- Governance: 8, Technical: 13, Strategic: 8

---

## Executive Summary

kz is an independent agent CLI built on the Kaizen agent SDK (kailash-kaizen). It is NOT a wrapper around any existing CLI. kz implements the universal agent loop (prompt-stream-dispatch-observe) with four differentiators: PACT governance (5-dimensional operating envelope), model agnosticism (Claude/OpenAI/Gemini/Ollama), COC nativity (commands/skills/hooks/rules from day 1), and governed multi-agent delegation (child envelope is a strict subset of parent envelope).

This document specifies seven architectural components in implementation-ready detail. Each section defines the design, implementation approach, Kaizen reuse surface, new code required, and estimated line count.

**Total estimated lines**: ~7,800 (new code) + ~1,200 (tests for critical paths) = ~9,000

---

## Table of Contents

1. [The kz Agent Loop](#1-the-kz-agent-loop)
2. [The kz Multi-Agent Model](#2-the-kz-multi-agent-model)
3. [The kz Streaming Architecture](#3-the-kz-streaming-architecture)
4. [The kz Hook System](#4-the-kz-hook-system)
5. [The kz Tool System](#5-the-kz-tool-system)
6. [The kz Context Engine](#6-the-kz-context-engine)
7. [The kz Security Model](#7-the-kz-security-model)
8. [Cross-Cutting Concerns](#8-cross-cutting-concerns)
9. [Package Structure](#9-package-structure)
10. [Implementation Phases](#10-implementation-phases)

---

## 1. The kz Agent Loop

### 1.1 Design

The agent loop is the heartbeat of kz. It implements the universal cycle observed across all three competitors (Claude Code, Codex, Gemini CLI) with PACT governance as intercept middleware.

```
LOOP:
  1. ASSEMBLE prompt (system + KAIZEN.md + conversation history + tool defs)
  2. DISPATCH hooks: PreModel
  3. CHECK budget: estimate token cost, warn if approaching limit
  4. STREAM LLM response, normalizing provider events to StreamEvent protocol
  5. DISPATCH hooks: PostModel
  6. IF response contains tool calls:
       a. DISPATCH hooks: PreToolUse (per tool call)
       b. CHECK permission: permission middleware evaluates each tool call
       c. IF permitted: EXECUTE tools (parallel by default, serialize same-path writes)
       d. IF denied: inject denial as tool result text
       e. IF held (PACT): pause for human approval
       f. DISPATCH hooks: PostToolUse (per tool call)
       g. RECORD tool results as conversation turns
       h. CHECK budget: actual cost vs budget
       i. CHECK turn limit: turn_count vs max_turns
       j. GOTO LOOP
  7. IF response is text-only (no tool calls):
       a. DISPATCH hooks: PostTurn
       b. RENDER final response to terminal
       c. YIELD control to user (or exit if non-interactive)
```

The loop terminates when: (a) the LLM produces text with no tool calls, (b) budget is exhausted, (c) max_turns reached, (d) user interrupts (Ctrl+C), or (e) a TerminalError occurs.

### 1.2 Core Data Structures

```python
@dataclass(frozen=True)
class TurnConfig:
    """Immutable configuration for a single turn of the agent loop."""
    model: str                          # e.g., "claude-sonnet-4-20250514"
    system_prompt: str                  # Assembled system prompt
    tools: list[ToolDefinition]         # Available tools for this turn
    max_tokens: int = 16384             # Max output tokens
    temperature: float = 0.0            # Deterministic by default
    stop_sequences: list[str] = field(default_factory=list)

@dataclass
class TurnResult:
    """Result of a single turn (one LLM call + tool executions)."""
    turn_id: str                        # UUID
    response_text: str                  # Final text from LLM
    tool_calls: list[ToolCallRecord]    # Tool calls made
    tool_results: list[ToolResultRecord]  # Tool results received
    usage: TokenUsage                   # Input/output/cache tokens
    cost_usd: float                     # Computed cost for this turn
    duration_ms: float                  # Wall clock time
    stop_reason: StopReason             # end_turn | max_tokens | tool_use

class StopReason(Enum):
    END_TURN = "end_turn"               # LLM finished naturally
    MAX_TOKENS = "max_tokens"           # Hit output token limit
    TOOL_USE = "tool_use"               # LLM wants to call tools (loop continues)
    BUDGET_EXCEEDED = "budget_exceeded"
    TURN_LIMIT = "turn_limit"
    USER_INTERRUPT = "user_interrupt"
    TERMINAL_ERROR = "terminal_error"

@dataclass
class TokenUsage:
    """Token counts from a single LLM call."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0      # Anthropic prompt caching
    cache_read_tokens: int = 0          # Anthropic prompt caching
```

### 1.3 The `TurnRunner` Class

```python
class TurnRunner:
    """
    Core agent loop executor. One TurnRunner per session.

    Responsibilities:
    - Assemble prompts from session context
    - Call LLM via provider-agnostic streaming client
    - Dispatch tool calls through permission middleware
    - Execute tools (parallel by default)
    - Feed results back into conversation
    - Enforce budget and turn limits
    - Fire hooks at each lifecycle point
    """

    def __init__(
        self,
        client: LLMClient,              # Provider-agnostic LLM client
        tool_registry: ToolRegistry,     # All available tools
        permission_policy: PermissionPolicy,  # Permission middleware
        hook_manager: HookManager,       # Hook dispatch
        session: Session,                # Conversation state
        config: SessionConfig,           # Budget, limits, model
        renderer: TerminalRenderer,      # UI output
    ): ...

    async def run_turn(self, user_message: str) -> TurnResult:
        """Execute one turn of the agent loop (may involve multiple LLM calls)."""
        ...

    async def _execute_agent_loop(self) -> TurnResult:
        """Inner loop: LLM call -> tool dispatch -> repeat until done."""
        ...

    async def _dispatch_tools(
        self, tool_calls: list[ToolCall]
    ) -> list[ToolResultRecord]:
        """Execute tool calls with permission checking and parallel dispatch."""
        ...
```

### 1.4 Hook Dispatch Points

The agent loop fires hooks at 8 points within a single turn:

```
User message arrives
  |
  v
[Hook: UserPromptSubmit] -- can modify user message, inject context
  |
  v
Prompt assembled
  |
  v
[Hook: PreModel] -- can inspect prompt, modify parameters
  |
  v
LLM streaming begins
  |
  v
LLM streaming completes
  |
  v
[Hook: PostModel] -- can inspect response, record metrics
  |
  v
For each tool call:
  [Hook: PreToolUse] -- can BLOCK (exit code 2), modify args, record intent
    |
    v
  Permission check (PermissionPolicy.check_permission)
    |
    v
  Tool execution
    |
    v
  [Hook: PostToolUse] -- can inspect result, record outcome
  |
  v
All tool results collected
  |
  v
Loop continues OR terminates
  |
  v
[Hook: PostTurn] -- can inspect full turn result, trigger compaction
```

### 1.5 Parallel Tool Execution

Tool calls are executed in parallel by default using `asyncio.gather()` with a same-path serialization guard to prevent concurrent writes to the same file.

```python
async def _dispatch_tools(self, tool_calls: list[ToolCall]) -> list[ToolResultRecord]:
    """
    Execute tool calls with parallel dispatch.

    Strategy:
    1. Group tool calls by "conflict key" (file path for writes, None for others)
    2. Tool calls with no conflict key: execute in parallel
    3. Tool calls with same conflict key: execute sequentially
    4. Cross-group: parallel
    """
    # Build conflict groups
    groups: dict[str | None, list[ToolCall]] = defaultdict(list)
    for tc in tool_calls:
        key = self._conflict_key(tc)  # e.g., file_path for Write/Edit
        groups[key].append(tc)

    # Execute groups in parallel, items within a group sequentially
    async def execute_group(calls: list[ToolCall]) -> list[ToolResultRecord]:
        results = []
        for call in calls:
            result = await self._execute_single_tool(call)
            results.append(result)
        return results

    group_results = await asyncio.gather(
        *[execute_group(calls) for calls in groups.values()]
    )

    # Flatten and return in original order
    all_results = [r for group in group_results for r in group]
    return sorted(all_results, key=lambda r: r.call_index)
```

### 1.6 Kaizen Reuse

| Component                           | Reuse             | Notes                                                                            |
| ----------------------------------- | ----------------- | -------------------------------------------------------------------------------- |
| `PermissionPolicy`                  | **DIRECT** (100%) | 8-layer decision engine at `core/autonomy/permissions/policy.py`                 |
| `PermissionMode` / `PermissionType` | **DIRECT** (100%) | Type system at `core/autonomy/permissions/types.py`                              |
| `ExecutionContext`                  | **DIRECT** (100%) | Budget tracking, tool allow/deny lists at `core/autonomy/permissions/context.py` |
| `CostTracker`                       | **ADAPT** (70%)   | Need to add per-model token pricing; microdollar accounting reusable             |
| `NativeToolResult`                  | **DIRECT** (100%) | Tool result type at `tools/native/base.py`                                       |

### 1.7 New Code Required

| Component                                             | Lines      | Complexity |
| ----------------------------------------------------- | ---------- | ---------- |
| `TurnRunner` (core loop + tool dispatch)              | ~800       | High       |
| `TurnConfig` / `TurnResult` / supporting types        | ~150       | Low        |
| `ModelPricing` registry (per-model token costs)       | ~120       | Low        |
| Budget pre-check (token estimation before call)       | ~100       | Medium     |
| Signal handling (Ctrl+C graceful interrupt)           | ~150       | Medium     |
| Error retry layer (rate limit, server error, network) | ~250       | Medium     |
| **Subtotal**                                          | **~1,570** |            |

---

## 2. The kz Multi-Agent Model

### 2.1 Design

kz's multi-agent model takes the best from each competitor:

- From Codex: the 5-tool lifecycle model (`spawn`, `send`, `wait`, `close`, `resume`)
- From Claude Code: fresh context isolation per subagent, depth limiting
- From neither competitor: PACT envelope inheritance (child envelope is a strict subset of parent)

The model is exposed to the LLM as tools. The LLM decides WHEN to delegate -- this is the key insight from Claude Code. The infrastructure provides the HOW.

### 2.2 Agent Tree

```
Root Agent (session owner)
  |-- Envelope: E_root (from org config or session defaults)
  |-- Context: full conversation history
  |
  |-- Subagent A (spawned by root)
  |     |-- Envelope: E_a (subset of E_root, tightened by root's spawn params)
  |     |-- Context: FRESH (only receives the spawn prompt + KAIZEN.md)
  |     |-- Depth: 1
  |     `-- Cannot spawn further subagents (depth limit reached)
  |
  |-- Subagent B (spawned by root, running concurrently)
  |     |-- Envelope: E_b (subset of E_root)
  |     |-- Context: FRESH
  |     |-- Depth: 1
  |     `-- Cannot spawn further subagents
  |
  `-- Subagent C (completed, result returned to root)
        |-- Final result text in root's conversation
        `-- Full transcript persisted independently
```

### 2.3 Subagent Lifecycle Tools

Five tools exposed to the LLM (matching Codex's model):

```python
# Tool 1: spawn_agent
{
    "name": "SpawnAgent",
    "description": "Create a new agent to work on a subtask. The agent gets a fresh context "
                   "window and can use all tools available to you (within your envelope). "
                   "Use this when: (a) a subtask needs focused context, (b) multiple independent "
                   "tasks can run in parallel, (c) a task might pollute your main context.",
    "parameters": {
        "prompt": "str -- The task description for the subagent",
        "tools": "list[str] | None -- Restrict tools available (default: inherit all)",
        "max_turns": "int -- Turn limit for subagent (default: 20)",
        "max_budget_usd": "float | None -- Budget limit (default: inherit remaining)",
        "background": "bool -- If true, agent runs in background (default: false)"
    },
    "returns": "str -- Agent ID (use with WaitAgent, SendMessage, CloseAgent)"
}

# Tool 2: send_message
{
    "name": "SendMessage",
    "description": "Send a message to a running agent. Use this to provide additional context, "
                   "redirect the agent, or ask for a status update.",
    "parameters": {
        "agent_id": "str -- Target agent ID",
        "message": "str -- Message to send",
        "interrupt": "bool -- If true, interrupt current work (default: false)"
    },
    "returns": "str -- Acknowledgment or agent's response"
}

# Tool 3: wait_agent
{
    "name": "WaitAgent",
    "description": "Wait for one or more agents to complete and return their final results.",
    "parameters": {
        "agent_ids": "list[str] -- Agent IDs to wait for",
        "timeout_seconds": "int -- Max wait time (default: 300, max: 3600)"
    },
    "returns": "dict[str, str] -- Map of agent_id to final result text"
}

# Tool 4: close_agent
{
    "name": "CloseAgent",
    "description": "Shut down a running agent and all its descendants. Use when the agent's "
                   "task is no longer needed or the agent is stuck.",
    "parameters": {
        "agent_id": "str -- Agent ID to close",
        "reason": "str -- Why the agent is being closed"
    },
    "returns": "str -- Confirmation with last known status"
}

# Tool 5: resume_agent
{
    "name": "ResumeAgent",
    "description": "Resume a previously completed or paused agent with a new prompt.",
    "parameters": {
        "agent_id": "str -- Agent ID to resume",
        "prompt": "str -- New prompt or follow-up instruction"
    },
    "returns": "str -- Agent's response to the new prompt"
}
```

### 2.4 PACT Envelope Inheritance

When a subagent is spawned, its operating envelope is computed as the intersection of:

1. The parent's effective envelope
2. Any explicit constraints in the spawn parameters

The child envelope can NEVER exceed the parent envelope. This is the monotonic tightening guarantee.

```python
@dataclass(frozen=True)
class AgentEnvelope:
    """Operating envelope for an agent in the tree."""
    financial: FinancialConstraints      # max_cost, max_cost_per_action
    operational: OperationalConstraints  # max_turns, allowed_tools, rate_limits
    temporal: TemporalConstraints        # max_duration, deadline
    data_access: DataAccessConstraints   # allowed_paths, read_only_paths, denied_paths
    communication: CommunicationConstraints  # allowed_endpoints, denied_domains

def compute_child_envelope(
    parent: AgentEnvelope,
    spawn_overrides: dict[str, Any],
) -> AgentEnvelope:
    """
    Compute child envelope as intersection of parent + overrides.

    Invariant: child[dimension] <= parent[dimension] for ALL dimensions.
    Violation raises EnvelopeTighteningError.
    """
    child = AgentEnvelope(
        financial=_tighten_financial(parent.financial, spawn_overrides),
        operational=_tighten_operational(parent.operational, spawn_overrides),
        temporal=_tighten_temporal(parent.temporal, spawn_overrides),
        data_access=_tighten_data_access(parent.data_access, spawn_overrides),
        communication=_tighten_communication(parent.communication, spawn_overrides),
    )
    _validate_monotonic_tightening(parent, child)
    return child
```

### 2.5 Concurrency and Depth Control

```python
# Configuration (in SessionConfig)
DEFAULT_MAX_AGENTS = 6          # Max concurrent subagents (matches Codex)
DEFAULT_MAX_DEPTH = 1           # Max delegation depth (matches Claude Code)
DEFAULT_SUBAGENT_MAX_TURNS = 20 # Per-subagent turn limit
DEFAULT_SUBAGENT_TIMEOUT = 300  # 5 minutes per subagent
```

Depth is currently hard-limited to 1 (subagents cannot spawn further subagents). This matches Claude Code's production choice and prevents recursive explosion. The architecture SUPPORTS configurable depth (for future PACT delegation chains), but v0.1 enforces depth=1.

### 2.6 Agent Context Isolation

Each subagent gets:

- A FRESH conversation history (no parent history)
- The parent's system prompt (KAIZEN.md + organizational context)
- The spawn prompt as the first user message
- Its own `TurnRunner` instance with its own `Session`
- Access to the parent's tool registry (filtered by envelope)
- Its own budget allocation (deducted from parent's remaining budget)

What a subagent does NOT get:

- Parent's conversation history
- Access to sibling agents' contexts
- Ability to modify parent's session state

Communication between agents is ONLY through:

- The spawn prompt (parent to child)
- The final result text (child to parent)
- `SendMessage` tool calls (parent to child, mid-execution)
- Files on disk (shared filesystem is the coordination channel)

### 2.7 Agent Tree Persistence

The agent tree is persisted in the session directory as a SQLite database:

```sql
CREATE TABLE agents (
    agent_id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES agents(agent_id),
    depth INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',  -- running, completed, failed, closed
    spawn_prompt TEXT NOT NULL,
    final_result TEXT,
    envelope_json TEXT NOT NULL,             -- Serialized AgentEnvelope
    created_at TEXT NOT NULL,
    completed_at TEXT,
    cost_usd REAL DEFAULT 0.0,
    turn_count INTEGER DEFAULT 0
);
```

This survives session resume. A resumed session can see the agent tree and re-attach to running agents or inspect completed ones.

### 2.8 Kaizen Reuse

| Component                                     | Reuse                     | Notes                                                                   |
| --------------------------------------------- | ------------------------- | ----------------------------------------------------------------------- |
| `SupervisorWorkerWorkflow`                    | **INFORM** (concept only) | Different execution model; concept of supervisor delegation is relevant |
| `SharedMemoryPool`                            | **DEFER**                 | Not needed for v0.1 context isolation model                             |
| `task_tool.py`                                | **ADAPT** (50%)           | Existing task tool needs rewrite for fresh-context subagent model       |
| PACT governance (`pact.governance.envelopes`) | **PORT** (80%)            | Envelope computation and monotonic tightening from reference impl       |

### 2.9 New Code Required

| Component                                         | Lines      | Complexity |
| ------------------------------------------------- | ---------- | ---------- |
| `AgentManager` (spawn, send, wait, close, resume) | ~500       | High       |
| `AgentEnvelope` + monotonic tightening            | ~200       | Medium     |
| 5 subagent tools (LLM-facing tool definitions)    | ~300       | Medium     |
| Agent tree persistence (SQLite)                   | ~200       | Medium     |
| Agent tree rendering (terminal display)           | ~100       | Low        |
| **Subtotal**                                      | **~1,300** |            |

---

## 3. The kz Streaming Architecture

### 3.1 Design

The streaming architecture is the hardest engineering problem in the entire CLI (per red team finding A-1). The three LLM providers use fundamentally incompatible streaming protocols. kz normalizes all of them into a single `StreamEvent` protocol.

### 3.2 StreamEvent Protocol

```python
class StreamEventType(Enum):
    """All event types in the normalized stream."""
    # Content events
    TEXT_DELTA = "text_delta"                    # Incremental text chunk
    THINKING_DELTA = "thinking_delta"            # Extended thinking content

    # Tool call events
    TOOL_CALL_START = "tool_call_start"          # Tool call begins (name known)
    TOOL_CALL_ARG_DELTA = "tool_call_arg_delta"  # Partial JSON argument chunk
    TOOL_CALL_END = "tool_call_end"              # Tool call complete (all args received)

    # Lifecycle events
    MESSAGE_START = "message_start"              # Response begins
    MESSAGE_STOP = "message_stop"                # Response complete

    # Metadata events
    USAGE_UPDATE = "usage_update"                # Token usage metadata

    # Error events
    ERROR = "error"                              # Recoverable error in stream

    # PACT-specific events
    ENVELOPE_CHECK = "envelope_check"            # Envelope check result
    GRADIENT_HELD = "gradient_held"              # Action held for human approval
    GRADIENT_FLAGGED = "gradient_flagged"        # Action flagged (logged, proceeds)
    GRADIENT_BLOCKED = "gradient_blocked"        # Action blocked by envelope

@dataclass
class StreamEvent:
    """
    Provider-agnostic stream event.

    All provider-specific streaming formats normalize to this.
    The TurnRunner and TerminalRenderer consume ONLY StreamEvents.
    """
    type: StreamEventType
    data: dict[str, Any] = field(default_factory=dict)
    # data contents vary by type:
    # TEXT_DELTA:           {"text": "chunk of text"}
    # THINKING_DELTA:       {"text": "thinking text"}
    # TOOL_CALL_START:      {"tool_call_id": "...", "tool_name": "Read", "index": 0}
    # TOOL_CALL_ARG_DELTA:  {"tool_call_id": "...", "delta": '{"file_'}
    # TOOL_CALL_END:        {"tool_call_id": "...", "arguments": {...}}  # parsed JSON
    # MESSAGE_START:        {"message_id": "...", "model": "..."}
    # MESSAGE_STOP:         {"stop_reason": "end_turn|tool_use|max_tokens"}
    # USAGE_UPDATE:         {"input_tokens": N, "output_tokens": N, ...}
    # ERROR:                {"code": "...", "message": "...", "retryable": bool}
    # ENVELOPE_CHECK:       {"dimension": "financial", "verdict": "auto"}
    # GRADIENT_HELD:        {"tool_name": "...", "dimension": "...", "reason": "..."}
```

### 3.3 LLMClient Protocol

```python
class LLMClient(Protocol):
    """
    Provider-agnostic LLM client protocol.

    Each provider implements this protocol with a thin adapter that:
    1. Translates kz's canonical message format to provider format
    2. Translates kz's canonical tool definitions to provider format
    3. Consumes the provider's streaming response
    4. Yields normalized StreamEvents
    """

    @property
    def provider_name(self) -> str:
        """Provider identifier: 'anthropic', 'openai', 'gemini', 'ollama'."""
        ...

    @property
    def model_name(self) -> str:
        """Current model name."""
        ...

    async def stream_completion(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system: str,
        config: TurnConfig,
    ) -> AsyncIterator[StreamEvent]:
        """
        Stream a completion from the LLM.

        Yields StreamEvents in normalized format.
        Handles provider-specific streaming protocol internally.
        """
        ...

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses provider-specific tokenizer when available,
        falls back to tiktoken cl100k_base.
        """
        ...
```

### 3.4 Per-Provider Stream Adapters

#### 3.4.1 Anthropic Adapter

```python
class AnthropicClient(LLMClient):
    """
    Adapter for Anthropic Messages API with streaming.

    Wire format: Server-Sent Events
    Events: message_start, content_block_start, content_block_delta,
            content_block_stop, message_delta, message_stop

    Tool calls: content blocks with type "tool_use"
    Arguments: streamed as input_json_delta events (partial JSON)

    Special features:
    - Extended thinking (thinking content blocks)
    - Prompt caching (cache_creation_input_tokens, cache_read_input_tokens)
    - System prompt as dedicated parameter (not in messages)
    """

    def __init__(self, api_key: str, model: str):
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "anthropic is required for Claude models. "
                "Install: pip install kailash-kaizen[anthropic]"
            ) from exc
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def stream_completion(self, messages, tools, system, config):
        """Stream and normalize Anthropic SSE events."""
        # Active tool call accumulators (one per concurrent tool_use block)
        accumulators: dict[int, ToolCallAccumulator] = {}

        async with self._client.messages.stream(
            model=self._model,
            messages=self._to_anthropic_messages(messages),
            tools=self._to_anthropic_tools(tools),
            system=system,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        ) as stream:
            async for event in stream:
                # Normalize each Anthropic event to StreamEvent(s)
                for normalized in self._normalize_event(event, accumulators):
                    yield normalized

    def _normalize_event(self, event, accumulators) -> list[StreamEvent]:
        """Map Anthropic SSE event to zero or more StreamEvents."""
        match event.type:
            case "message_start":
                return [StreamEvent(
                    type=StreamEventType.MESSAGE_START,
                    data={"message_id": event.message.id, "model": event.message.model}
                )]
            case "content_block_start":
                if event.content_block.type == "tool_use":
                    acc = ToolCallAccumulator(
                        tool_call_id=event.content_block.id,
                        tool_name=event.content_block.name,
                        index=event.index,
                    )
                    accumulators[event.index] = acc
                    return [StreamEvent(
                        type=StreamEventType.TOOL_CALL_START,
                        data={"tool_call_id": acc.tool_call_id,
                              "tool_name": acc.tool_name, "index": acc.index}
                    )]
                return []
            case "content_block_delta":
                if event.delta.type == "text_delta":
                    return [StreamEvent(
                        type=StreamEventType.TEXT_DELTA,
                        data={"text": event.delta.text}
                    )]
                elif event.delta.type == "thinking_delta":
                    return [StreamEvent(
                        type=StreamEventType.THINKING_DELTA,
                        data={"text": event.delta.thinking}
                    )]
                elif event.delta.type == "input_json_delta":
                    acc = accumulators[event.index]
                    acc.append(event.delta.partial_json)
                    return [StreamEvent(
                        type=StreamEventType.TOOL_CALL_ARG_DELTA,
                        data={"tool_call_id": acc.tool_call_id,
                              "delta": event.delta.partial_json}
                    )]
                return []
            case "content_block_stop":
                if event.index in accumulators:
                    acc = accumulators.pop(event.index)
                    return [StreamEvent(
                        type=StreamEventType.TOOL_CALL_END,
                        data={"tool_call_id": acc.tool_call_id,
                              "arguments": acc.parse_complete()}
                    )]
                return []
            case "message_delta":
                return [StreamEvent(
                    type=StreamEventType.USAGE_UPDATE,
                    data={"output_tokens": event.usage.output_tokens}
                )]
            case "message_stop":
                return [StreamEvent(
                    type=StreamEventType.MESSAGE_STOP,
                    data={"stop_reason": event.message.stop_reason
                          if hasattr(event, 'message') else "end_turn"}
                )]
        return []
```

#### 3.4.2 OpenAI Adapter

```python
class OpenAIClient(LLMClient):
    """
    Adapter for OpenAI Chat Completions API with streaming.

    Wire format: Server-Sent Events (Chat Completions) or WebSocket (Responses API)
    Events: chunks with choices[0].delta containing content or tool_calls

    Tool calls: function calls with arguments as partial JSON strings
    Arguments: accumulated across multiple chunks (chunks carry index + partial string)

    Special features:
    - Responses API (newer, structured differently)
    - Function calling format (name + arguments separate)
    """

    async def stream_completion(self, messages, tools, system, config):
        # System prompt goes as first message with role="system"
        openai_messages = [{"role": "system", "content": system}]
        openai_messages.extend(self._to_openai_messages(messages))

        accumulators: dict[int, ToolCallAccumulator] = {}

        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=openai_messages,
            tools=self._to_openai_tools(tools),
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            for normalized in self._normalize_chunk(chunk, accumulators):
                yield normalized

    def _normalize_chunk(self, chunk, accumulators) -> list[StreamEvent]:
        """Map OpenAI streaming chunk to StreamEvents."""
        events = []

        if chunk.usage:
            events.append(StreamEvent(
                type=StreamEventType.USAGE_UPDATE,
                data={
                    "input_tokens": chunk.usage.prompt_tokens,
                    "output_tokens": chunk.usage.completion_tokens,
                }
            ))

        if not chunk.choices:
            return events

        delta = chunk.choices[0].delta
        finish_reason = chunk.choices[0].finish_reason

        # Text content
        if delta.content:
            events.append(StreamEvent(
                type=StreamEventType.TEXT_DELTA,
                data={"text": delta.content}
            ))

        # Tool calls (may arrive as partial fragments across chunks)
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in accumulators and tc_delta.function.name:
                    # New tool call starting
                    acc = ToolCallAccumulator(
                        tool_call_id=tc_delta.id or f"call_{idx}",
                        tool_name=tc_delta.function.name,
                        index=idx,
                    )
                    accumulators[idx] = acc
                    events.append(StreamEvent(
                        type=StreamEventType.TOOL_CALL_START,
                        data={"tool_call_id": acc.tool_call_id,
                              "tool_name": acc.tool_name, "index": idx}
                    ))

                if tc_delta.function and tc_delta.function.arguments:
                    acc = accumulators[idx]
                    acc.append(tc_delta.function.arguments)
                    events.append(StreamEvent(
                        type=StreamEventType.TOOL_CALL_ARG_DELTA,
                        data={"tool_call_id": acc.tool_call_id,
                              "delta": tc_delta.function.arguments}
                    ))

        # Finish reason
        if finish_reason:
            # Complete any pending tool calls
            for idx, acc in list(accumulators.items()):
                events.append(StreamEvent(
                    type=StreamEventType.TOOL_CALL_END,
                    data={"tool_call_id": acc.tool_call_id,
                          "arguments": acc.parse_complete()}
                ))
            accumulators.clear()

            events.append(StreamEvent(
                type=StreamEventType.MESSAGE_STOP,
                data={"stop_reason": self._map_finish_reason(finish_reason)}
            ))

        return events
```

#### 3.4.3 Gemini Adapter

```python
class GeminiClient(LLMClient):
    """
    Adapter for Google Gemini API with streaming.

    Wire format: google-genai SDK yields GenerateContentResponse chunks

    Tool calls: FunctionCall parts (complete, not partial)
    Arguments: complete JSON (no accumulation needed)

    Special features:
    - System instruction as separate parameter
    - 1M+ context window (Gemini 2.5 Pro)
    - Grounding with Google Search
    """

    async def stream_completion(self, messages, tools, system, config):
        response = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=self._to_gemini_contents(messages),
            config=self._build_config(tools, system, config),
        )

        async for chunk in response:
            for normalized in self._normalize_chunk(chunk):
                yield normalized

    def _normalize_chunk(self, chunk) -> list[StreamEvent]:
        """Map Gemini chunk to StreamEvents. Tool calls arrive complete."""
        events = []
        for part in chunk.candidates[0].content.parts:
            if hasattr(part, 'text') and part.text:
                events.append(StreamEvent(
                    type=StreamEventType.TEXT_DELTA,
                    data={"text": part.text}
                ))
            elif hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                call_id = f"gemini_{id(fc)}"
                events.append(StreamEvent(
                    type=StreamEventType.TOOL_CALL_START,
                    data={"tool_call_id": call_id,
                          "tool_name": fc.name, "index": 0}
                ))
                events.append(StreamEvent(
                    type=StreamEventType.TOOL_CALL_END,
                    data={"tool_call_id": call_id,
                          "arguments": dict(fc.args)}
                ))

        if chunk.usage_metadata:
            events.append(StreamEvent(
                type=StreamEventType.USAGE_UPDATE,
                data={
                    "input_tokens": chunk.usage_metadata.prompt_token_count,
                    "output_tokens": chunk.usage_metadata.candidates_token_count,
                }
            ))

        return events
```

#### 3.4.4 Ollama Adapter

```python
class OllamaClient(LLMClient):
    """
    Adapter for Ollama local models via HTTP API.

    Wire format: NDJSON streaming from /api/chat

    Tool calls: Complete function calls in message.tool_calls
    Arguments: Complete JSON (like Gemini)

    Special features:
    - Zero cost (local execution)
    - No rate limits
    - Model pull/management
    """

    async def stream_completion(self, messages, tools, system, config):
        payload = {
            "model": self._model,
            "messages": self._to_ollama_messages(messages, system),
            "tools": self._to_ollama_tools(tools),
            "stream": True,
            "options": {"temperature": config.temperature},
        }

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload
            ) as response:
                async for line in response.aiter_lines():
                    chunk = json.loads(line)
                    for normalized in self._normalize_chunk(chunk):
                        yield normalized
```

### 3.5 ToolCallAccumulator

This component is shared across providers that stream partial tool call arguments.

```python
class ToolCallAccumulator:
    """
    Accumulates partial JSON argument fragments into a complete tool call.

    Used by Anthropic (input_json_delta) and OpenAI (function.arguments fragments).
    Not needed by Gemini or Ollama (they send complete arguments).
    """

    def __init__(self, tool_call_id: str, tool_name: str, index: int):
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self.index = index
        self._fragments: list[str] = []

    def append(self, fragment: str) -> None:
        """Append a JSON fragment."""
        self._fragments.append(fragment)

    def parse_complete(self) -> dict[str, Any]:
        """
        Parse accumulated fragments as complete JSON.

        If parsing fails, attempt repair (common for Tier 3 models):
        1. Try adding missing closing braces
        2. Try removing trailing comma
        3. If all repair fails, return {"_raw": raw_string, "_parse_error": error}
        """
        raw = "".join(self._fragments)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            return self._attempt_repair(raw, e)

    def _attempt_repair(self, raw: str, original_error: json.JSONDecodeError) -> dict:
        """Attempt common JSON repairs for malformed tool call arguments."""
        repairs = [
            lambda s: s + "}",           # Missing closing brace
            lambda s: s + "}}",          # Missing two closing braces
            lambda s: s.rstrip(",") + "}", # Trailing comma
            lambda s: s.rstrip(",\n ") + "}",
        ]
        for repair in repairs:
            try:
                return json.loads(repair(raw))
            except json.JSONDecodeError:
                continue

        # All repairs failed -- return raw string so LLM can see the error
        return {"_raw": raw, "_parse_error": str(original_error)}
```

### 3.6 Mid-Stream Retry

```python
class StreamRetryPolicy:
    """
    Retry policy for streaming completions.

    Handles:
    - 429 (Rate Limit): Exponential backoff, max 4 retries
    - 500/502/503 (Server Error): Exponential backoff, max 3 retries
    - Network timeout: Exponential backoff, max 3 retries
    - 400 (Bad Request): NOT retried (terminal)
    - 401/403 (Auth): NOT retried (terminal, user recoverable)
    """

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503}
    MAX_RETRIES = 4
    BASE_DELAY_SECONDS = 1.0
    MAX_DELAY_SECONDS = 60.0

    async def execute_with_retry(
        self,
        stream_fn: Callable[..., AsyncIterator[StreamEvent]],
        renderer: TerminalRenderer,
        **kwargs,
    ) -> AsyncIterator[StreamEvent]:
        """Execute streaming call with retry on recoverable errors."""
        last_error = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                async for event in stream_fn(**kwargs):
                    yield event
                return  # Success
            except RateLimitError as e:
                last_error = e
                delay = self._compute_delay(attempt, e.retry_after)
                renderer.show_retry(attempt + 1, self.MAX_RETRIES, delay, "Rate limited")
                await asyncio.sleep(delay)
            except ServerError as e:
                last_error = e
                delay = self._compute_delay(attempt)
                renderer.show_retry(attempt + 1, self.MAX_RETRIES, delay, str(e))
                await asyncio.sleep(delay)
            except NetworkError as e:
                last_error = e
                delay = self._compute_delay(attempt)
                renderer.show_retry(attempt + 1, self.MAX_RETRIES, delay, "Network error")
                await asyncio.sleep(delay)

        raise TerminalError(f"Max retries exceeded: {last_error}") from last_error

    def _compute_delay(self, attempt: int, retry_after: float | None = None) -> float:
        """Exponential backoff with optional server-specified delay."""
        if retry_after is not None:
            return min(retry_after, self.MAX_DELAY_SECONDS)
        delay = self.BASE_DELAY_SECONDS * (2 ** attempt)
        # Add jitter (0.5x to 1.5x)
        jitter = 0.5 + random.random()
        return min(delay * jitter, self.MAX_DELAY_SECONDS)
```

### 3.7 Kaizen Reuse

| Component                       | Reuse                | Notes                                                               |
| ------------------------------- | -------------------- | ------------------------------------------------------------------- |
| `OpenAIToolMapper`              | **ADAPT** (60%)      | Tool definition formatting reusable; streaming normalization is new |
| `GeminiToolMapper`              | **ADAPT** (60%)      | Same as above                                                       |
| `base.py::extract_tool_call()`  | **INFORM** (concept) | Handles complete responses; streaming needs accumulation            |
| `base.py::format_tool_result()` | **DIRECT** (80%)     | Useful for formatting tool results back to provider format          |
| `StreamingExecutor` event types | **INFORM** (concept) | Different execution model; event taxonomy is informative            |

### 3.8 New Code Required

| Component                                | Lines      | Complexity |
| ---------------------------------------- | ---------- | ---------- |
| `StreamEvent` types and protocol         | ~120       | Low        |
| `AnthropicClient` (streaming adapter)    | ~350       | High       |
| `OpenAIClient` (streaming adapter)       | ~300       | High       |
| `GeminiClient` (streaming adapter)       | ~200       | Medium     |
| `OllamaClient` (streaming adapter)       | ~200       | Medium     |
| `ToolCallAccumulator` (shared)           | ~120       | Medium     |
| `StreamRetryPolicy`                      | ~150       | Medium     |
| `LLMClientFactory` (provider resolution) | ~100       | Low        |
| **Subtotal**                             | **~1,540** |            |

---

## 4. The kz Hook System

### 4.1 Design

Hooks are what make kz a COC platform, not just a chat CLI. They provide lifecycle interception points where external scripts (shell, Python) can observe, modify, or block agent behavior. This is the mechanism that powers COC artifacts: rules enforcement, anti-amnesia reminders, session context injection, and security guards.

kz defines **14 hook events** -- more than Gemini's 11, more than Claude Code's 5. This is deliberate: PACT governance requires hook points that no competitor needs.

### 4.2 Hook Event Catalog

| #   | Event                  | When                               | Can Block?               | Can Modify?           | Data In                                                      | Data Out                                               |
| --- | ---------------------- | ---------------------------------- | ------------------------ | --------------------- | ------------------------------------------------------------ | ------------------------------------------------------ |
| 1   | `SessionStart`         | Session begins (after config load) | No                       | Yes (inject context)  | `{session_id, model, cwd, kaizen_md_hash}`                   | `{system_prompt_additions}`                            |
| 2   | `SessionEnd`           | Session ends (before persistence)  | No                       | No                    | `{session_id, turn_count, total_cost, duration}`             | --                                                     |
| 3   | `UserPromptSubmit`     | User submits a message             | No                       | Yes (modify message)  | `{message, turn_number}`                                     | `{modified_message, context_injection}`                |
| 4   | `PreModel`             | Before LLM call                    | No                       | Yes (modify params)   | `{model, message_count, estimated_tokens}`                   | `{system_prompt_additions}`                            |
| 5   | `PostModel`            | After LLM response                 | No                       | No                    | `{model, usage, cost, stop_reason}`                          | --                                                     |
| 6   | `PreToolUse`           | Before tool execution              | **YES** (exit 2 = BLOCK) | Yes (modify args)     | `{tool_name, tool_input, tool_id}`                           | `{modified_input}` or `{blocked: true, reason: "..."}` |
| 7   | `PostToolUse`          | After tool execution               | No                       | No                    | `{tool_name, tool_input, tool_output, success, duration_ms}` | --                                                     |
| 8   | `PreCompact`           | Before context compaction          | No                       | Yes (preserve items)  | `{turn_count, token_count, items_to_compact}`                | `{preserved_items}`                                    |
| 9   | `PostCompact`          | After context compaction           | No                       | No                    | `{turns_removed, tokens_freed}`                              | --                                                     |
| 10  | `PreSubagentSpawn`     | Before subagent creation           | **YES**                  | Yes (modify envelope) | `{prompt, envelope, parent_agent_id}`                        | `{modified_envelope}` or `{blocked: true}`             |
| 11  | `PostSubagentComplete` | After subagent finishes            | No                       | No                    | `{agent_id, result, cost, turn_count}`                       | --                                                     |
| 12  | `EnvelopeViolation`    | PACT envelope boundary hit         | No                       | No                    | `{dimension, action, limit, actual, verdict}`                | --                                                     |
| 13  | `Stop`                 | Agent decides to stop              | No                       | No                    | `{reason, final_message}`                                    | --                                                     |
| 14  | `Error`                | Unhandled error occurs             | No                       | No                    | `{error_type, message, recoverable}`                         | --                                                     |

### 4.3 Hook Execution Model

Hooks are defined in two locations:

1. **Global hooks**: `~/.config/kz/hooks/` (user-level)
2. **Project hooks**: `.kaizen/hooks/` (project-level, like `.claude/hooks/`)

Each hook is a file named `{event_name}.{ext}`:

- `.sh` -- Shell script (executed via subprocess)
- `.py` -- Python script (executed via subprocess with `python -c`)
- `.js` -- JavaScript (executed via `node`)

Hook execution protocol (matching Claude Code's model):

```
1. Hook receives JSON on STDIN:
   {"event": "PreToolUse", "data": {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}}

2. Hook writes JSON to STDOUT:
   {"blocked": true, "reason": "Destructive command detected"}

3. Hook exit codes:
   0 = Success (proceed)
   1 = Error (log warning, proceed anyway)
   2 = BLOCK (stop the action, return reason to LLM as tool result)
```

### 4.4 Hook Manager

```python
class CliHookManager:
    """
    Manages hook discovery, loading, and execution for the kz CLI.

    Extends Kaizen's existing HookManager with:
    - Shell/Python/JS hook execution via subprocess
    - Project-level hook discovery (.kaizen/hooks/)
    - Blocking semantics (exit code 2)
    - JSON stdin/stdout protocol
    - Timeout enforcement (hooks cannot hang the agent)
    """

    HOOK_TIMEOUT_SECONDS = 10  # Hooks must complete within 10 seconds

    def __init__(self, project_root: Path, global_hooks_dir: Path):
        self._hooks: dict[str, list[HookScript]] = defaultdict(list)
        self._discover_hooks(project_root / ".kaizen" / "hooks")
        self._discover_hooks(global_hooks_dir)

    async def dispatch(
        self,
        event: str,
        data: dict[str, Any],
    ) -> HookDispatchResult:
        """
        Dispatch event to all registered hooks.

        Returns:
            HookDispatchResult with:
            - blocked: True if any hook returned exit code 2
            - block_reason: Human-readable reason from blocking hook
            - modifications: Merged modifications from all hooks
        """
        result = HookDispatchResult()

        for hook in self._hooks.get(event, []):
            try:
                hook_result = await asyncio.wait_for(
                    self._execute_hook(hook, event, data),
                    timeout=self.HOOK_TIMEOUT_SECONDS,
                )
                if hook_result.exit_code == 2:
                    result.blocked = True
                    result.block_reason = hook_result.output.get("reason", "Blocked by hook")
                    break  # First blocker wins
                if hook_result.output:
                    result.modifications.update(hook_result.output)
            except asyncio.TimeoutError:
                logger.warning(f"Hook {hook.path} timed out after {self.HOOK_TIMEOUT_SECONDS}s")
            except Exception as e:
                logger.warning(f"Hook {hook.path} failed: {e}")

        return result

    async def _execute_hook(
        self, hook: HookScript, event: str, data: dict
    ) -> HookExecutionResult:
        """Execute a single hook script via subprocess."""
        stdin_data = json.dumps({"event": event, "data": data})

        proc = await asyncio.create_subprocess_exec(
            hook.interpreter, str(hook.path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(stdin_data.encode())

        output = {}
        if stdout.strip():
            try:
                output = json.loads(stdout)
            except json.JSONDecodeError:
                logger.warning(f"Hook {hook.path} produced non-JSON output")

        return HookExecutionResult(
            exit_code=proc.returncode,
            output=output,
            stderr=stderr.decode() if stderr else "",
        )
```

### 4.5 COC Integration Matrix

This table maps COC artifacts to hook events:

| COC Artifact                    | Hook Event                    | Purpose                                |
| ------------------------------- | ----------------------------- | -------------------------------------- |
| `rules/zero-tolerance.md`       | `PreToolUse`                  | Block stubs, placeholder code          |
| `rules/security.md`             | `PreToolUse`                  | Block commits without security review  |
| `rules/no-stubs.md`             | `PostToolUse` (on Write/Edit) | Scan written files for stub patterns   |
| `user-prompt-rules-reminder.js` | `UserPromptSubmit`            | Inject workspace context, anti-amnesia |
| `session-start.js`              | `SessionStart`                | Load workspace, show status            |
| `validate-workflow.js`          | `PreToolUse` (on Write)       | Block production stubs                 |
| PACT envelope check             | `PreToolUse`                  | 5-dimensional constraint check         |
| EATP audit record               | `PostToolUse`                 | Record action in trust lineage         |
| Budget enforcement              | `PreModel`                    | Check remaining budget before LLM call |

### 4.6 Kaizen Reuse

| Component                            | Reuse             | Notes                                                        |
| ------------------------------------ | ----------------- | ------------------------------------------------------------ |
| `HookEvent` enum                     | **EXTEND** (70%)  | Add CLI-specific events (SessionStart/End, PreCompact, etc.) |
| `HookHandler` protocol               | **DIRECT** (100%) | Python-side hook protocol unchanged                          |
| `HookManager`                        | **EXTEND** (60%)  | Add subprocess execution, blocking semantics                 |
| `HookContext` / `HookResult`         | **DIRECT** (100%) | Context and result types reusable                            |
| `HookPriority`                       | **DIRECT** (100%) | Priority system reusable                                     |
| Builtin hooks (audit, cost, logging) | **ADAPT** (80%)   | Wire to CLI events instead of autonomy events                |

### 4.7 New Code Required

| Component                                          | Lines    | Complexity |
| -------------------------------------------------- | -------- | ---------- |
| `CliHookManager` (discovery, subprocess execution) | ~350     | Medium     |
| Hook dispatch protocol (JSON stdin/stdout)         | ~100     | Low        |
| 14 hook event definitions + schemas                | ~150     | Low        |
| COC hook bridge (map COC artifacts to hook events) | ~100     | Low        |
| Hook trust model (project hooks require approval)  | ~100     | Medium     |
| **Subtotal**                                       | **~800** |            |

---

## 5. The kz Tool System

### 5.1 Design

The tool system is structured as three concentric rings:

```
Ring 1: Built-in tools (platform-controlled, highest trust)
  |
  v
Ring 2: Project tools (from KAIZEN.md / .kaizen/, user-controlled)
  |
  v
Ring 3: MCP tools (external servers, lowest trust)
```

All tools share a uniform interface. Permission middleware intercepts ALL tool calls regardless of ring. PACT envelope checking is an additional layer on top of permissions.

### 5.2 Built-in Tool Set (v0.1)

kz ships with **18 built-in tools** (expanded from original 12 to address red team findings):

| #   | Tool            | Category    | Danger Level | Source                               |
| --- | --------------- | ----------- | ------------ | ------------------------------------ |
| 1   | `Read`          | File        | Safe         | EXISTING (`file_tools.py`)           |
| 2   | `Write`         | File        | Risky        | EXISTING (`file_tools.py`)           |
| 3   | `Edit`          | File        | Risky        | **NEW** -- surgical line-range edits |
| 4   | `Glob`          | Search      | Safe         | EXISTING (`search_tools.py`)         |
| 5   | `Grep`          | Search      | Safe         | EXISTING (`search_tools.py`)         |
| 6   | `Bash`          | System      | Dangerous    | EXISTING (`bash_tools.py`)           |
| 7   | `ListDirectory` | File        | Safe         | **NEW** -- dedicated ls equivalent   |
| 8   | `WebFetch`      | Network     | Risky        | **NEW** -- HTTP GET for docs/APIs    |
| 9   | `Ask`           | Interaction | Safe         | EXISTING (`interaction_tool.py`)     |
| 10  | `TodoRead`      | Planning    | Safe         | EXISTING (`todo_tool.py`)            |
| 11  | `TodoWrite`     | Planning    | Safe         | EXISTING (`todo_tool.py`)            |
| 12  | `Plan`          | Planning    | Safe         | EXISTING (`planning_tool.py`)        |
| 13  | `SpawnAgent`    | Multi-Agent | Risky        | **NEW**                              |
| 14  | `SendMessage`   | Multi-Agent | Risky        | **NEW**                              |
| 15  | `WaitAgent`     | Multi-Agent | Safe         | **NEW**                              |
| 16  | `CloseAgent`    | Multi-Agent | Safe         | **NEW**                              |
| 17  | `ResumeAgent`   | Multi-Agent | Risky        | **NEW**                              |
| 18  | `Notebook`      | File        | Risky        | EXISTING (`notebook_tool.py`)        |

### 5.3 The Edit Tool

The Edit tool is the most important tool for developer adoption. Without it, kz uses full file rewrites, which is catastrophic for large files.

```python
class EditTool(BaseTool):
    """
    Surgical line-range edit tool.

    Replaces a contiguous range of lines in a file with new content.
    Uses conflict detection: the caller must provide the EXACT old content
    that will be replaced (like Claude Code's Edit tool). If the old content
    does not match the file, the edit fails with a clear error showing the
    actual content at those lines.

    Parameters:
        file_path: Absolute path to the file
        old_content: The exact text to be replaced (must match file contents)
        new_content: The replacement text

    Conflict detection:
    - If old_content is not found in the file, returns error with context
    - If old_content appears multiple times, returns error with all locations
    - Preserves file permissions and ownership

    Returns:
        Success: "Edited {file_path}: replaced {n} lines with {m} lines"
        Failure: "Edit conflict: old_content not found at expected location.
                  Actual content at lines {start}-{end}:\n{actual}"
    """
    name = "Edit"
    description = (
        "Make a surgical edit to a file. Specify the exact text to find (old_content) "
        "and the text to replace it with (new_content). The old_content must match "
        "exactly -- this prevents overwriting changes you haven't seen. "
        "For creating new files, use Write instead."
    )
    danger_level = DangerLevel.RISKY
    category = ToolCategory.FILE

    async def execute(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
    ) -> NativeToolResult:
        """Execute surgical edit with conflict detection."""
        path = Path(file_path)

        # Validate path is within working directory
        if not self._is_within_cwd(path):
            return NativeToolResult.from_error(
                f"Edit blocked: {file_path} is outside the working directory"
            )

        # Read current file content
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return NativeToolResult.from_error(f"File not found: {file_path}")

        # Find old_content in file
        occurrences = self._find_occurrences(current, old_content)

        if len(occurrences) == 0:
            # Content not found -- show nearby context for debugging
            return NativeToolResult.from_error(
                f"Edit conflict: old_content not found in {file_path}.\n"
                f"The file may have changed since you last read it.\n"
                f"Use Read to see current contents."
            )

        if len(occurrences) > 1:
            # Ambiguous -- multiple matches
            locations = ", ".join(f"line {o}" for o in occurrences)
            return NativeToolResult.from_error(
                f"Edit conflict: old_content found {len(occurrences)} times "
                f"at lines {locations}. Make old_content more specific."
            )

        # Exactly one match -- perform the edit
        new_file = current.replace(old_content, new_content, 1)

        # Atomic write (temp file + rename)
        tmp_path = path.with_suffix(path.suffix + ".kz_tmp")
        try:
            tmp_path.write_text(new_file, encoding="utf-8")
            tmp_path.replace(path)
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            return NativeToolResult.from_exception(e)

        old_lines = old_content.count("\n") + 1
        new_lines = new_content.count("\n") + 1
        return NativeToolResult.from_success(
            f"Edited {file_path}: replaced {old_lines} lines with {new_lines} lines",
            old_lines=old_lines,
            new_lines=new_lines,
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit"
                },
                "old_content": {
                    "type": "string",
                    "description": "The exact text to find and replace (must match file contents)"
                },
                "new_content": {
                    "type": "string",
                    "description": "The replacement text"
                },
            },
            "required": ["file_path", "old_content", "new_content"],
        }
```

### 5.4 Permission Middleware

Every tool call passes through permission middleware before execution:

```
LLM requests tool
  |
  v
[Hook: PreToolUse] -- external hooks can block
  |
  v
PermissionPolicy.check_permission(tool_name, tool_input, estimated_cost)
  |
  +-- (True, None)  -> Execute tool
  +-- (False, reason) -> Return denial as tool result text
  +-- (None, None)   -> Ask user for approval
  |                      |
  |                      +-- User approves -> Execute tool
  |                      +-- User denies   -> Return denial as tool result text
  v
[PACT EnvelopeCheck] -- 5-dimensional constraint check (if PACT enabled)
  |
  +-- AUTO     -> Proceed
  +-- FLAGGED  -> Log, proceed
  +-- HELD     -> Pause for human approval (PseudoAgent)
  +-- BLOCKED  -> Return denial as tool result text
  |
  v
Execute tool
  |
  v
[Output truncation] -- truncate if > MAX_TOOL_OUTPUT_TOKENS
  |
  v
Return result to conversation
```

Denial is always returned as a **tool result text**, not an exception. The LLM sees "Permission denied: [reason]" and adapts its strategy. This matches Pattern 3 from the competitive analysis.

### 5.5 Tool Result Truncation

Large tool results (file reads, bash output) can consume the entire context window in a few turns.

```python
MAX_TOOL_OUTPUT_TOKENS = 8000  # ~32KB of text
TRUNCATION_NOTICE = "\n\n[Output truncated: {original_tokens} tokens -> {kept_tokens} tokens. Use more specific commands to see full content.]"

def truncate_tool_output(output: str, max_tokens: int = MAX_TOOL_OUTPUT_TOKENS) -> str:
    """
    Truncate tool output that exceeds the token budget.

    Strategy:
    1. If within budget, return unchanged
    2. If over budget, keep first 60% and last 20%, insert truncation notice
    3. Always preserve error messages (never truncate errors)
    """
    token_count = estimate_tokens(output)
    if token_count <= max_tokens:
        return output

    # Keep first 60% and last 20% of the budget
    head_budget = int(max_tokens * 0.6)
    tail_budget = int(max_tokens * 0.2)

    lines = output.split("\n")
    head_lines, tail_lines = _split_by_tokens(lines, head_budget, tail_budget)

    return (
        "\n".join(head_lines)
        + TRUNCATION_NOTICE.format(original_tokens=token_count, kept_tokens=max_tokens)
        + "\n".join(tail_lines)
    )
```

### 5.6 MCP Integration

MCP tools are integrated through the existing Kaizen MCP client, with an adapter that wraps MCP server tools as native tools.

```python
class McpToolAdapter:
    """
    Wraps MCP server tools as native kz tools.

    - Discovers tools from configured MCP servers
    - Maps MCP tool schemas to kz ToolDefinition format
    - Routes tool calls to the appropriate MCP server
    - All MCP tool calls go through the same permission middleware
    """

    def __init__(self, mcp_config: list[McpServerConfig]):
        self._servers: dict[str, McpServer] = {}

    async def discover_tools(self) -> list[ToolDefinition]:
        """Connect to all configured MCP servers and discover tools."""
        tools = []
        for config in self._mcp_configs:
            try:
                server = await self._connect_server(config)
                server_tools = await server.list_tools()
                for tool in server_tools:
                    tools.append(self._to_kz_tool(tool, config.name))
                self._servers[config.name] = server
            except Exception as e:
                logger.warning(f"Failed to connect to MCP server '{config.name}': {e}")
                # Graceful degradation: skip this server, continue with others
        return tools

    async def execute(self, server_name: str, tool_name: str, args: dict) -> str:
        """Execute a tool on an MCP server."""
        server = self._servers[server_name]
        result = await server.call_tool(tool_name, args)
        return result.content
```

### 5.7 Tool Definition Format

All tools (built-in, project, MCP) are represented uniformly:

```python
@dataclass
class ToolDefinition:
    """
    Canonical tool definition, provider-agnostic.

    Provider adapters translate this to their specific format:
    - Anthropic: {name, description, input_schema}
    - OpenAI: {type: "function", function: {name, description, parameters}}
    - Gemini: FunctionDeclaration(name, description, parameters)
    """
    name: str
    description: str
    parameters: dict[str, Any]          # JSON Schema
    source: ToolSource                  # BUILTIN, PROJECT, MCP
    danger_level: DangerLevel           # SAFE, RISKY, DANGEROUS
    read_only: bool = False             # For parallel execution decisions
    server_name: str | None = None      # For MCP tools: which server
```

### 5.8 Kaizen Reuse

| Component                       | Reuse                             | Notes                                                |
| ------------------------------- | --------------------------------- | ---------------------------------------------------- |
| `BaseTool` / `NativeToolResult` | **DIRECT** (100%)                 | Base class and result type                           |
| 12 existing native tools        | **DIRECT** (90%)                  | Minor adaptations for CLI context                    |
| `ToolRegistry`                  | **EXTEND** (70%)                  | Add MCP adapter, project tool loading                |
| `DangerLevel` / `ToolCategory`  | **DIRECT** (100%)                 | Classification enums                                 |
| `KaizenTool` dataclass          | **REPLACE** with `ToolDefinition` | KaizenTool is OpenAI-centric; need provider-agnostic |
| MCP client (`kaizen/mcp/`)      | **ADAPT** (60%)                   | Wrap as tool adapter                                 |

### 5.9 New Code Required

| Component                                           | Lines      | Complexity |
| --------------------------------------------------- | ---------- | ---------- |
| `EditTool` (surgical edits with conflict detection) | ~250       | Medium     |
| `ListDirectoryTool`                                 | ~80        | Low        |
| `WebFetchTool` (HTTP GET)                           | ~120       | Low        |
| `ToolDefinition` canonical type                     | ~60        | Low        |
| Provider-specific tool formatters (3 providers)     | ~200       | Medium     |
| `McpToolAdapter`                                    | ~200       | Medium     |
| Tool result truncation                              | ~80        | Low        |
| Tool execution timeout wrapper                      | ~60        | Low        |
| **Subtotal**                                        | **~1,050** |            |

---

## 6. The kz Context Engine

### 6.1 Design

The context engine manages everything the LLM sees: system prompt assembly, conversation history, token tracking, compaction, and memory. It implements Codex's Item/Turn/Thread model adapted for Python.

### 6.2 Conversation State Model

```
Thread (session)
  |-- System context (KAIZEN.md, org context, tool defs) -- STATIC PREFIX
  |
  |-- Turn 1 (user message + agent response)
  |     |-- Item: UserMessage ("Fix the bug in auth.py")
  |     |-- Item: AgentMessage (text: "I'll look at auth.py...")
  |     |-- Item: ToolUse (Read, {file_path: "auth.py"})
  |     |-- Item: ToolResult (file contents)
  |     |-- Item: AgentMessage (text: "Found the issue...")
  |     |-- Item: ToolUse (Edit, {file_path: "auth.py", ...})
  |     |-- Item: ToolResult ("Edited auth.py: replaced 5 lines with 8 lines")
  |     `-- Item: AgentMessage (text: "Fixed. The bug was...")
  |
  |-- Turn 2 (next user message + response)
  |     `-- ...
  |
  `-- Turn N
```

```python
class ItemType(Enum):
    USER_MESSAGE = "user_message"
    AGENT_MESSAGE = "agent_message"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    SYSTEM_MESSAGE = "system_message"
    COMPACTION_SUMMARY = "compaction_summary"

@dataclass
class Item:
    """Atomic unit of conversation history."""
    item_id: str                        # UUID
    item_type: ItemType
    content: str                        # Text content
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0                # Cached token count
    timestamp: float = field(default_factory=time.time)

    # For tool items
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_input: dict | None = None

@dataclass
class Turn:
    """A sequence of items from a single user-agent interaction."""
    turn_id: str
    items: list[Item]
    turn_number: int
    cost_usd: float = 0.0

    @property
    def token_count(self) -> int:
        return sum(item.token_count for item in self.items)

@dataclass
class Thread:
    """Durable conversation container."""
    thread_id: str
    turns: list[Turn]
    system_context: SystemContext
    created_at: float
    model: str

    @property
    def total_tokens(self) -> int:
        return self.system_context.token_count + sum(t.token_count for t in self.turns)
```

### 6.3 KAIZEN.md Loading Hierarchy

KAIZEN.md is the kz equivalent of CLAUDE.md. It is loaded from a hierarchy of locations, merged, and injected into the system prompt.

```
Priority (highest first):
1. CLI flags (--system-prompt "...")           -- overrides everything
2. .kaizen/rules/*.md  (project rules)         -- merged
3. KAIZEN.md (project root)                    -- primary project instructions
4. Parent KAIZEN.md (walk up to find root)     -- inherited
5. ~/.config/kz/KAIZEN.md (global)             -- user defaults
6. Built-in system prompt                      -- always present
```

```python
class KaizenMdLoader:
    """
    Load and merge KAIZEN.md files from the hierarchy.

    Matches Claude Code's CLAUDE.md behavior:
    - Walk up from cwd to find project root (stop at .git or KAIZEN.md)
    - Merge global + project + subdirectory
    - Hash for change detection between sessions
    - Content displayed + confirmed on first load (security)
    """

    def load(self, cwd: Path) -> KaizenMdResult:
        """Load all KAIZEN.md files and merge."""
        files = []

        # Global
        global_md = Path.home() / ".config" / "kz" / "KAIZEN.md"
        if global_md.exists():
            files.append(("global", global_md))

        # Walk up from cwd
        current = cwd
        while current != current.parent:
            kaizen_md = current / "KAIZEN.md"
            if kaizen_md.exists():
                files.append(("project", kaizen_md))

            # Also check .kaizen/rules/
            rules_dir = current / ".kaizen" / "rules"
            if rules_dir.is_dir():
                for rule_file in sorted(rules_dir.glob("*.md")):
                    files.append(("rule", rule_file))

            # Stop at git root
            if (current / ".git").exists():
                break
            current = current.parent

        # Merge (project instructions after global, rules after project)
        merged = self._merge_files(files)
        content_hash = hashlib.sha256(merged.encode()).hexdigest()[:16]

        return KaizenMdResult(
            content=merged,
            content_hash=content_hash,
            source_files=[(scope, str(path)) for scope, path in files],
        )
```

### 6.4 System Prompt Assembly

```python
class PromptAssembler:
    """
    Assembles the complete system prompt from components.

    Order matters for prompt caching (Anthropic):
    Static components first (cacheable), dynamic components last.
    """

    def assemble(
        self,
        kaizen_md: str,
        tool_definitions: list[ToolDefinition],
        pact_context: PactContext | None,
        session_config: SessionConfig,
    ) -> str:
        """
        Assemble system prompt.

        Structure:
        [1] Base identity (who is kz, capabilities)          -- STATIC, CACHED
        [2] KAIZEN.md content (project instructions)         -- STATIC per session
        [3] PACT organizational context (role, envelope)     -- STATIC per session
        [4] Tool usage instructions                          -- STATIC per session
        [5] Session-dynamic context (hook injections)        -- DYNAMIC
        """
        sections = []

        # [1] Base identity
        sections.append(self._base_identity(session_config.model))

        # [2] KAIZEN.md
        if kaizen_md:
            sections.append(f"## Project Instructions\n\n{kaizen_md}")

        # [3] PACT context (if enabled)
        if pact_context:
            sections.append(self._pact_section(pact_context))

        # [4] Tool usage
        sections.append(self._tool_instructions(tool_definitions))

        return "\n\n---\n\n".join(sections)
```

### 6.5 Compaction Strategy

Compaction triggers when conversation history approaches 80% of the model's context window. The strategy preserves critical context while freeing token budget.

```python
class CompactionEngine:
    """
    Context compaction to prevent context window overflow.

    Three compaction levels (applied progressively):
    1. TOOL_TRUNCATION: Truncate large tool results in old turns
    2. TURN_SUMMARIZATION: Summarize old turns into 1-2 sentence summaries
    3. TURN_EVICTION: Remove oldest turns entirely, keep summary anchor
    """

    COMPACTION_THRESHOLD = 0.80  # Trigger at 80% of context window
    PRESERVE_RECENT_TURNS = 5   # Always keep last 5 turns uncompacted

    async def should_compact(self, thread: Thread, model_context_limit: int) -> bool:
        """Check if compaction is needed."""
        usage_ratio = thread.total_tokens / model_context_limit
        return usage_ratio >= self.COMPACTION_THRESHOLD

    async def compact(
        self,
        thread: Thread,
        client: LLMClient,
        hook_manager: CliHookManager,
    ) -> CompactionResult:
        """
        Compact conversation history.

        Process:
        1. Fire PreCompact hook (hooks can mark items as preserved)
        2. Identify compactable turns (all except recent N)
        3. Level 1: Truncate tool results > 2000 tokens
        4. If still over threshold: Level 2: Summarize old turns via LLM
        5. If still over threshold: Level 3: Evict oldest turns
        6. Fire PostCompact hook
        """
        # Fire PreCompact hook
        hook_result = await hook_manager.dispatch(
            "PreCompact",
            {"turn_count": len(thread.turns), "token_count": thread.total_tokens},
        )
        preserved_ids = hook_result.modifications.get("preserved_items", set())

        compactable = thread.turns[:-self.PRESERVE_RECENT_TURNS]
        freed_tokens = 0

        # Level 1: Tool truncation
        for turn in compactable:
            if turn.turn_id in preserved_ids:
                continue
            for item in turn.items:
                if item.item_type == ItemType.TOOL_RESULT and item.token_count > 2000:
                    old_count = item.token_count
                    item.content = truncate_tool_output(item.content, max_tokens=500)
                    item.token_count = estimate_tokens(item.content)
                    freed_tokens += old_count - item.token_count

        # Level 2: Turn summarization (uses a cheap LLM call)
        if self._still_over_threshold(thread, freed_tokens):
            for turn in compactable:
                if turn.turn_id in preserved_ids:
                    continue
                summary = await self._summarize_turn(turn, client)
                old_tokens = turn.token_count
                turn.items = [Item(
                    item_id=f"summary_{turn.turn_id}",
                    item_type=ItemType.COMPACTION_SUMMARY,
                    content=summary,
                    token_count=estimate_tokens(summary),
                )]
                freed_tokens += old_tokens - turn.token_count

        # Level 3: Turn eviction (last resort)
        if self._still_over_threshold(thread, freed_tokens):
            evict_count = len(compactable) // 2  # Evict oldest half
            evicted = thread.turns[:evict_count]
            thread.turns = thread.turns[evict_count:]
            freed_tokens += sum(t.token_count for t in evicted)

        # Fire PostCompact hook
        await hook_manager.dispatch(
            "PostCompact",
            {"turns_removed": 0, "tokens_freed": freed_tokens},
        )

        return CompactionResult(tokens_freed=freed_tokens)
```

### 6.6 Token Tracking and Budget Enforcement

```python
class TokenTracker:
    """
    Track token usage across the session.

    Uses tiktoken for estimation (cl100k_base for OpenAI/Anthropic,
    approximation for Gemini). Maintains running totals for budget enforcement.
    """

    def __init__(self, model: str, budget_limit: float | None = None):
        self._model = model
        self._budget_limit = budget_limit
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_usd = 0.0
        self._pricing = ModelPricing.get(model)

        # Load tokenizer
        try:
            import tiktoken
            self._encoder = tiktoken.encoding_for_model(model)
        except (ImportError, KeyError):
            self._encoder = None  # Fall back to character-based estimation

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        if self._encoder:
            return len(self._encoder.encode(text))
        # Fallback: ~4 chars per token
        return len(text) // 4

    def compute_cost(self, usage: TokenUsage) -> float:
        """Compute cost from token usage."""
        input_cost = (usage.input_tokens / 1_000_000) * self._pricing.input_per_mtok
        output_cost = (usage.output_tokens / 1_000_000) * self._pricing.output_per_mtok
        # Anthropic cache tokens are cheaper
        cache_write = (usage.cache_creation_tokens / 1_000_000) * self._pricing.cache_write_per_mtok
        cache_read = (usage.cache_read_tokens / 1_000_000) * self._pricing.cache_read_per_mtok
        return input_cost + output_cost + cache_write + cache_read

    def check_budget(self, estimated_next_cost: float) -> BudgetStatus:
        """Check if budget allows the next call."""
        if self._budget_limit is None:
            return BudgetStatus.OK

        remaining = self._budget_limit - self._total_cost_usd
        if remaining <= 0:
            return BudgetStatus.EXHAUSTED
        if estimated_next_cost > remaining:
            return BudgetStatus.WOULD_EXCEED
        if remaining < self._budget_limit * 0.2:
            return BudgetStatus.LOW
        return BudgetStatus.OK

@dataclass(frozen=True)
class ModelPricingEntry:
    """Per-model pricing in USD per million tokens."""
    input_per_mtok: float
    output_per_mtok: float
    cache_write_per_mtok: float = 0.0
    cache_read_per_mtok: float = 0.0
    context_window: int = 128_000

class ModelPricing:
    """Registry of per-model pricing. Updated manually per release."""

    _REGISTRY: dict[str, ModelPricingEntry] = {
        # Anthropic
        "claude-opus-4-20250514":   ModelPricingEntry(15.0, 75.0, 18.75, 1.50, 200_000),
        "claude-sonnet-4-20250514": ModelPricingEntry(3.0, 15.0, 3.75, 0.30, 200_000),
        "claude-haiku-3.5":         ModelPricingEntry(0.80, 4.0, 1.0, 0.08, 200_000),
        # OpenAI
        "gpt-4o":                   ModelPricingEntry(2.50, 10.0, 0.0, 0.0, 128_000),
        "gpt-4o-mini":              ModelPricingEntry(0.15, 0.60, 0.0, 0.0, 128_000),
        "o3":                       ModelPricingEntry(10.0, 40.0, 0.0, 0.0, 200_000),
        # Gemini
        "gemini-2.5-pro":           ModelPricingEntry(1.25, 10.0, 0.0, 0.0, 1_048_576),
        "gemini-2.5-flash":         ModelPricingEntry(0.15, 0.60, 0.0, 0.0, 1_048_576),
        # Ollama (free)
        "ollama/*":                 ModelPricingEntry(0.0, 0.0, 0.0, 0.0, 128_000),
    }

    @classmethod
    def get(cls, model: str) -> ModelPricingEntry:
        """Look up pricing for a model. Falls back to conservative estimate."""
        if model in cls._REGISTRY:
            return cls._REGISTRY[model]
        # Check prefix matches (e.g., "ollama/*" matches "ollama/llama3")
        for pattern, entry in cls._REGISTRY.items():
            if "*" in pattern and model.startswith(pattern.rstrip("/*")):
                return entry
        # Conservative fallback
        return ModelPricingEntry(10.0, 30.0, 0.0, 0.0, 128_000)
```

### 6.7 Memory System (Tiered)

```
Hot Memory (in conversation context):
  - Current conversation history
  - KAIZEN.md content
  - PACT organizational context
  - Survives: always present until compacted

Warm Memory (on disk, loaded on demand):
  - Session JSONL transcript
  - Subagent transcripts
  - Compaction summaries
  - Survives: session resume loads these

Cold Memory (persistent, cross-session):
  - ~/.config/kz/memory/ (user memories, auto-generated)
  - .kaizen/memory/ (project memories)
  - Loaded on SessionStart, survive across sessions
  - Format: Markdown files with frontmatter metadata
```

### 6.8 Session Persistence

```python
class SessionPersistence:
    """
    Persist session state for resume and audit.

    Format: JSONL (one JSON object per line)
    Location: ~/.config/kz/sessions/{session_id}/
    Files:
      - transcript.jsonl  (full conversation history)
      - agents.db         (agent tree, SQLite)
      - metadata.json     (session config, model, timestamps)

    Security:
      - File permissions: 0600 (owner read/write only)
      - No secrets in metadata.json
      - Tool results may contain secrets (file reads of .env) -- encryption in v0.2
    """

    SESSION_DIR = Path.home() / ".config" / "kz" / "sessions"

    async def save_item(self, session_id: str, item: Item) -> None:
        """Append an item to the session transcript."""
        session_dir = self.SESSION_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        transcript = session_dir / "transcript.jsonl"

        # Set permissions on first create
        if not transcript.exists():
            transcript.touch(mode=0o600)

        async with aiofiles.open(transcript, "a") as f:
            await f.write(json.dumps(item.to_dict()) + "\n")

    async def load_session(self, session_id: str) -> Thread:
        """Load a session for resume."""
        session_dir = self.SESSION_DIR / session_id
        transcript = session_dir / "transcript.jsonl"

        if not transcript.exists():
            raise SessionNotFoundError(session_id)

        items = []
        async with aiofiles.open(transcript) as f:
            async for line in f:
                if line.strip():
                    items.append(Item.from_dict(json.loads(line)))

        return self._reconstruct_thread(session_id, items)

    async def lock_session(self, session_id: str) -> SessionLock:
        """Acquire exclusive lock on session (prevents concurrent access)."""
        lock_path = self.SESSION_DIR / session_id / "transcript.lock"
        return await SessionLock.acquire(lock_path)
```

### 6.9 Kaizen Reuse

| Component              | Reuse           | Notes                                                     |
| ---------------------- | --------------- | --------------------------------------------------------- |
| `SharedMemoryPool`     | **DEFER**       | Different memory model for CLI                            |
| `ExecutionEvent` types | **INFORM**      | Event taxonomy informative but CLI needs different events |
| `CostTracker`          | **ADAPT** (70%) | Add token-based pricing; microdollar accounting reusable  |
| Kaizen `config/`       | **ADAPT** (50%) | Config loading patterns, not direct reuse                 |

### 6.10 New Code Required

| Component                                      | Lines      | Complexity |
| ---------------------------------------------- | ---------- | ---------- |
| `Item` / `Turn` / `Thread` conversation model  | ~200       | Medium     |
| `KaizenMdLoader` (hierarchy discovery + merge) | ~180       | Medium     |
| `PromptAssembler` (system prompt construction) | ~150       | Medium     |
| `CompactionEngine` (3-level compaction)        | ~300       | High       |
| `TokenTracker` + `ModelPricing`                | ~220       | Medium     |
| `SessionPersistence` (JSONL + locking)         | ~250       | Medium     |
| Memory system (hot/warm/cold)                  | ~150       | Medium     |
| **Subtotal**                                   | **~1,450** |            |

---

## 7. The kz Security Model

### 7.1 Design

Security is not Phase 3. It is the first layer of every component. The security model has five pillars:

1. **Permission middleware** -- per-tool allow/ask/deny decisions
2. **Working directory confinement** -- tools cannot operate outside the project
3. **KAIZEN.md trust model** -- untrusted project instructions are sandboxed
4. **Session file security** -- secrets in session files are protected
5. **MCP server trust model** -- external tools have explicit permission scopes

### 7.2 Permission Levels

```python
class PermissionMode(Enum):
    """
    Permission modes for the session.
    Maps to CLI flags: --permission-mode
    """
    SUGGEST = "suggest"           # All tool calls require approval (most restrictive)
    DEFAULT = "default"           # Safe tools auto-approve, risky tools ask
    ACCEPT_EDITS = "accept_edits" # File edits auto-approve, bash still asks
    FULL_AUTO = "full_auto"       # All tools auto-approve (least restrictive)
    PLAN = "plan"                 # Read-only mode (no writes, no execution)
```

Per-tool override (in `.kaizen/settings.toml`):

```toml
[permissions]
mode = "default"

[permissions.tools]
Read = "auto"
Write = "auto"          # Auto-approve writes (user trusts the model)
Edit = "auto"
Bash = "ask"            # Always ask for bash (default)
WebFetch = "deny"       # Block network access entirely
SpawnAgent = "ask"      # Ask before spawning subagents

[permissions.patterns]
"Bash:rm *" = "deny"             # Block rm commands
"Bash:git push --force*" = "deny" # Block force push
"Write:*.env" = "deny"           # Block writing to .env files
```

### 7.3 Working Directory Confinement

All file operations are confined to the project root directory. This is enforced at the tool level, not the OS level (OS sandboxing is v0.3).

```python
class PathGuard:
    """
    Enforces working directory confinement for file tools.

    Rules:
    1. All file paths must resolve within project_root
    2. Symlinks are resolved before checking (prevents symlink escape)
    3. Parent traversal (../) is resolved and checked
    4. Home directory reads are allowed for config files only
    """

    def __init__(self, project_root: Path):
        self._root = project_root.resolve()
        self._allowed_prefixes = [
            self._root,
            Path.home() / ".config" / "kz",  # kz config
        ]

    def validate_path(self, path: str, operation: str = "read") -> Path:
        """
        Validate that a path is within allowed boundaries.

        Args:
            path: The path to validate (absolute or relative)
            operation: "read" or "write" (writes have stricter rules)

        Returns:
            Resolved Path if valid

        Raises:
            PathViolationError if path is outside boundaries
        """
        resolved = Path(path).resolve()

        if operation == "write":
            # Writes are ONLY allowed within project root
            if not str(resolved).startswith(str(self._root)):
                raise PathViolationError(
                    f"Write blocked: {path} is outside the project directory ({self._root})"
                )
        else:
            # Reads allowed in project root + config dirs
            if not any(str(resolved).startswith(str(p)) for p in self._allowed_prefixes):
                raise PathViolationError(
                    f"Read blocked: {path} is outside allowed directories"
                )

        return resolved
```

### 7.4 KAIZEN.md Trust Model

```python
class KaizenMdTrust:
    """
    Trust model for KAIZEN.md files.

    KAIZEN.md from project directories is UNTRUSTED by default
    (could be from a cloned malicious repo). The trust model:

    1. FIRST LOAD: Display KAIZEN.md content, ask user to confirm
    2. HASH TRACKING: Store SHA-256 hash in ~/.config/kz/trusted_hashes.json
    3. CHANGE DETECTION: If hash changes between sessions, warn user
    4. SAFETY OVERRIDE: KAIZEN.md CANNOT override safety-critical settings:
       - Cannot change permission mode to FULL_AUTO
       - Cannot disable path confinement
       - Cannot add tools to auto-approve list
       - Cannot disable hooks
    """

    TRUSTED_HASHES_FILE = Path.home() / ".config" / "kz" / "trusted_hashes.json"

    def check_trust(self, content: str, source_path: Path) -> TrustDecision:
        """Check if KAIZEN.md content is trusted."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        trusted_hashes = self._load_trusted_hashes()
        path_key = str(source_path.resolve())

        if path_key in trusted_hashes:
            if trusted_hashes[path_key] == content_hash:
                return TrustDecision.TRUSTED
            else:
                return TrustDecision.CHANGED  # Content changed since last trust

        return TrustDecision.NEW  # Never seen before

    def trust(self, content: str, source_path: Path) -> None:
        """Mark KAIZEN.md as trusted (after user confirmation)."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        trusted_hashes = self._load_trusted_hashes()
        trusted_hashes[str(source_path.resolve())] = content_hash
        self._save_trusted_hashes(trusted_hashes)
```

### 7.5 Destructive Command Detection

```python
class DestructiveCommandDetector:
    """
    Detect potentially destructive bash commands.

    These commands trigger an explicit confirmation prompt
    even in FULL_AUTO mode.
    """

    # Patterns that ALWAYS require confirmation
    DESTRUCTIVE_PATTERNS = [
        r"rm\s+-rf?\s",                     # rm with recursive/force
        r"rm\s+.*\*",                        # rm with wildcard
        r"mv\s+.*\s+/dev/null",             # mv to /dev/null
        r"chmod\s+-R\s",                     # recursive chmod
        r"chown\s+-R\s",                     # recursive chown
        r"git\s+push\s+.*--force",           # force push
        r"git\s+reset\s+--hard",             # hard reset
        r"git\s+clean\s+-fd",               # clean untracked
        r"dd\s+if=",                         # disk operations
        r"mkfs\.",                            # filesystem creation
        r">\s*/",                             # redirect overwrite to root path
        r"curl\s+.*\|\s*(bash|sh|python)",   # pipe curl to shell
        r"wget\s+.*\|\s*(bash|sh|python)",   # pipe wget to shell
    ]

    def is_destructive(self, command: str) -> tuple[bool, str]:
        """Check if a command is destructive. Returns (is_destructive, reason)."""
        for pattern in self.DESTRUCTIVE_PATTERNS:
            if re.search(pattern, command):
                return True, f"Destructive pattern detected: {pattern}"
        return False, ""
```

### 7.6 Session File Security

```python
# All session files created with 0600 permissions
SESSION_FILE_MODE = 0o600

# Secret patterns to redact from session transcripts (display only, not storage)
SECRET_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",                # OpenAI API keys
    r"sk-ant-[a-zA-Z0-9]{20,}",            # Anthropic API keys
    r"AIza[a-zA-Z0-9_-]{35}",              # Google API keys
    r"ghp_[a-zA-Z0-9]{36}",                # GitHub PATs
    r"glpat-[a-zA-Z0-9_-]{20,}",           # GitLab PATs
    r"xoxb-[0-9]+-[a-zA-Z0-9]+",           # Slack tokens
    r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+",  # JWTs
]
```

### 7.7 MCP Server Trust Model

```python
@dataclass
class McpServerConfig:
    """Configuration for an MCP server with explicit trust scope."""
    name: str
    command: str                         # How to start the server
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    # Trust scope
    allowed_tools: list[str] | None = None  # None = all tools
    denied_tools: list[str] = field(default_factory=list)
    max_cost_per_call: float = 1.0       # Budget limit per MCP tool call

    # Network scope
    allowed_hosts: list[str] = field(default_factory=list)  # Empty = no network

    # Approval
    auto_approve: bool = False           # If False, MCP tools go through permission middleware
    trusted: bool = False                # If False, first use requires user confirmation
```

### 7.8 Kaizen Reuse

| Component                                            | Reuse                               | Notes                   |
| ---------------------------------------------------- | ----------------------------------- | ----------------------- |
| `PermissionPolicy` (8-layer)                         | **DIRECT** (100%)                   | Core permission engine  |
| `PermissionMode`                                     | **EXTEND** (add SUGGEST, FULL_AUTO) | Two new modes           |
| `PermissionRule`                                     | **DIRECT** (100%)                   | Pattern-based rules     |
| `BudgetEnforcer`                                     | **ADAPT** (80%)                     | Wire to TokenTracker    |
| `ApprovalManager`                                    | **ADAPT** (70%)                     | Wire to terminal prompt |
| Security hooks (`authorization.py`, `validation.py`) | **ADAPT** (70%)                     | Wire to CLI hook system |

### 7.9 New Code Required

| Component                                                | Lines    | Complexity |
| -------------------------------------------------------- | -------- | ---------- |
| `PathGuard` (working directory confinement)              | ~120     | Medium     |
| `KaizenMdTrust` (hash tracking, first-load confirmation) | ~150     | Medium     |
| `DestructiveCommandDetector`                             | ~80      | Low        |
| `McpServerConfig` + trust model                          | ~100     | Medium     |
| Secret redaction for session display                     | ~60      | Low        |
| Session file permissions enforcement                     | ~40      | Low        |
| **Subtotal**                                             | **~550** |            |

---

## 8. Cross-Cutting Concerns

### 8.1 Error Taxonomy

```python
class KzError(Exception):
    """Base error for all kz errors."""
    pass

class RecoverableError(KzError):
    """Auto-retried: rate limits, network timeouts, server errors."""
    retry_after: float | None = None

class UserRecoverableError(KzError):
    """Shown to user, session continues: auth failure, invalid model."""
    pass

class TerminalError(KzError):
    """Session saved and exits: budget exceeded, unrecoverable failures."""
    pass

class EnvelopeTighteningError(KzError):
    """PACT violation: child envelope exceeds parent."""
    pass

class PathViolationError(KzError):
    """Working directory confinement violated."""
    pass
```

### 8.2 Signal Handling

```python
class SignalHandler:
    """
    Graceful signal handling for the kz CLI.

    Ctrl+C behavior:
    - First press: Set cancellation flag, cancel current LLM stream
    - Second press (within 1s): Force exit, save session
    - SIGTERM: Save session, exit
    - SIGTSTP (Ctrl+Z): Not intercepted (allows backgrounding)
    """

    def __init__(self, session_persistence: SessionPersistence):
        self._cancel_flag = asyncio.Event()
        self._force_exit = False
        self._last_interrupt = 0.0
        self._session = session_persistence

    def install(self):
        """Install signal handlers."""
        signal.signal(signal.SIGINT, self._handle_sigint)
        signal.signal(signal.SIGTERM, self._handle_sigterm)

    def _handle_sigint(self, sig, frame):
        now = time.monotonic()
        if now - self._last_interrupt < 1.0:
            # Double Ctrl+C: force exit
            self._force_exit = True
            raise SystemExit(130)
        self._last_interrupt = now
        self._cancel_flag.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel_flag.is_set()

    def reset(self):
        """Reset cancellation flag for next turn."""
        self._cancel_flag.clear()
```

### 8.3 Terminal Renderer

```python
class TerminalRenderer:
    """
    Renders agent output to the terminal using Rich.

    Responsibilities:
    - Stream text deltas as they arrive (character-by-character rendering)
    - Show tool call headers with spinners
    - Show tool results (collapsible for large output)
    - Show cost per turn
    - Show retry notices with countdown
    - Show PACT gradient notifications
    - Show permission prompts
    """

    def __init__(self, console: Console):
        self._console = console

    def stream_text(self, delta: str) -> None:
        """Render a text delta (part of streaming response)."""
        self._console.print(delta, end="", highlight=False)

    def show_tool_start(self, tool_name: str, tool_input: dict) -> Live:
        """Show tool execution header with spinner."""
        ...

    def show_tool_result(self, tool_name: str, result: str, success: bool) -> None:
        """Show tool result (truncated if large)."""
        ...

    def show_cost(self, turn_cost: float, total_cost: float, budget: float | None) -> None:
        """Show cost for the current turn."""
        ...

    def show_permission_prompt(self, tool_name: str, tool_input: dict) -> bool:
        """Show permission prompt, return True if approved."""
        ...

    def show_retry(self, attempt: int, max_retries: int, delay: float, reason: str) -> None:
        """Show retry notice with countdown."""
        ...

    def show_pact_gradient(self, event: StreamEvent) -> None:
        """Show PACT gradient notification (flagged/held/blocked)."""
        ...
```

### 8.4 CLI Entry Point

```python
# pyproject.toml
[project.scripts]
kz = "kaizen.cli.main:app"

# kaizen/cli/main.py
import typer

app = typer.Typer(name="kz", help="PACT-constrained AI agent CLI")

@app.command()
def run(
    prompt: str = typer.Argument(None, help="Initial prompt (or omit for REPL)"),
    model: str = typer.Option(None, "-m", "--model", help="LLM model"),
    permission_mode: str = typer.Option("default", "--permission-mode",
        help="Permission level: suggest|default|accept_edits|full_auto|plan"),
    max_turns: int = typer.Option(100, "--max-turns"),
    max_budget: float = typer.Option(None, "--max-budget", help="Budget in USD"),
    resume: str = typer.Option(None, "--resume", "-r", help="Resume session ID"),
    print_mode: bool = typer.Option(False, "--print", "-p",
        help="Non-interactive: print response and exit"),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
    system_prompt: str = typer.Option(None, "--system-prompt"),
):
    """Start a kz agent session."""
    asyncio.run(_run_session(
        prompt=prompt, model=model, permission_mode=permission_mode,
        max_turns=max_turns, max_budget=max_budget, resume=resume,
        print_mode=print_mode, verbose=verbose, system_prompt=system_prompt,
    ))

@app.command()
def config():
    """Manage kz configuration."""
    ...

@app.command()
def sessions():
    """List and manage saved sessions."""
    ...
```

### 8.5 REPL

```python
class KzRepl:
    """
    Interactive REPL using prompt_toolkit.

    Features:
    - Async input (doesn't block event loop)
    - History (persisted to ~/.config/kz/history)
    - Multi-line paste detection
    - Auto-complete for slash commands
    - Key bindings (Ctrl+C, Ctrl+D, etc.)
    """

    SLASH_COMMANDS = {
        "/help": "Show available commands",
        "/model": "Switch model",
        "/cost": "Show session cost",
        "/compact": "Trigger context compaction",
        "/clear": "Clear conversation history",
        "/save": "Save session",
        "/resume": "Resume a previous session",
        "/tree": "Show agent tree",
        "/exit": "Exit kz",
    }

    async def run(self, turn_runner: TurnRunner) -> None:
        """Run the REPL loop."""
        session = PromptSession(
            history=FileHistory(str(Path.home() / ".config" / "kz" / "history")),
            auto_suggest=AutoSuggestFromHistory(),
            completer=SlashCommandCompleter(self.SLASH_COMMANDS),
        )

        while True:
            try:
                user_input = await session.prompt_async("kz> ")

                if user_input.startswith("/"):
                    await self._handle_slash_command(user_input, turn_runner)
                else:
                    await turn_runner.run_turn(user_input)

            except EOFError:
                break  # Ctrl+D
            except KeyboardInterrupt:
                continue  # Ctrl+C at prompt just clears the line
```

### 8.6 First-Run Experience

```python
class FirstRunSetup:
    """
    First-run experience for new kz users.

    Triggered when no API keys are configured.
    Guides user through:
    1. Provider selection (Claude, OpenAI, Gemini, Ollama)
    2. API key input (stored in ~/.config/kz/config.toml)
    3. Default model selection
    4. Permission mode selection
    """

    async def run(self) -> Config:
        """Interactive first-run setup."""
        console = Console()
        console.print("[bold]Welcome to kz[/bold] -- PACT-constrained AI agent CLI\n")

        # Detect existing API keys in environment
        detected = self._detect_env_keys()
        if detected:
            console.print(f"Detected API keys: {', '.join(detected)}")
            return self._auto_config(detected)

        # Interactive setup
        provider = Prompt.ask(
            "Choose your provider",
            choices=["anthropic", "openai", "gemini", "ollama"],
            default="anthropic",
        )

        if provider == "ollama":
            # No API key needed
            return self._ollama_config()

        api_key = Prompt.ask(f"Enter your {provider} API key", password=True)

        # Store securely
        config_path = Path.home() / ".config" / "kz" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.touch(mode=0o600)

        # Write config
        ...
```

### 8.7 Lines for Cross-Cutting

| Component                      | Lines      | Complexity |
| ------------------------------ | ---------- | ---------- |
| Error taxonomy                 | ~60        | Low        |
| Signal handling                | ~120       | Medium     |
| Terminal renderer (Rich-based) | ~400       | Medium     |
| CLI entry point (typer)        | ~150       | Low        |
| REPL (prompt_toolkit)          | ~250       | Medium     |
| First-run setup                | ~120       | Low        |
| Config loading + validation    | ~150       | Medium     |
| **Subtotal**                   | **~1,250** |            |

---

## 9. Package Structure

```
packages/kailash-kaizen/
  src/kaizen/
    cli/                              # NEW: All CLI code lives here
      __init__.py
      main.py                         # Typer app, entry point
      repl.py                         # prompt_toolkit REPL
      config.py                       # Config loading + validation
      first_run.py                    # First-run API key setup
      renderer.py                     # Terminal renderer (Rich)

      agent/                          # Agent loop
        __init__.py
        turn_runner.py                # Core agent loop
        types.py                      # TurnConfig, TurnResult, etc.
        signal_handler.py             # Ctrl+C handling
        compaction.py                 # Context compaction engine

      streaming/                      # Provider-agnostic streaming
        __init__.py
        protocol.py                   # StreamEvent types
        accumulator.py                # ToolCallAccumulator
        retry.py                      # StreamRetryPolicy
        clients/
          __init__.py
          base.py                     # LLMClient protocol
          anthropic.py                # AnthropicClient
          openai.py                   # OpenAIClient
          gemini.py                   # GeminiClient
          ollama.py                   # OllamaClient
          factory.py                  # LLMClientFactory

      multi_agent/                    # Multi-agent model
        __init__.py
        manager.py                    # AgentManager
        envelope.py                   # AgentEnvelope + monotonic tightening
        persistence.py                # Agent tree SQLite persistence
        tools.py                      # 5 subagent tools

      hooks/                          # Hook system
        __init__.py
        manager.py                    # CliHookManager
        events.py                     # 14 hook event definitions
        executor.py                   # Shell/Python hook execution
        coc_bridge.py                 # COC artifact -> hook mapping

      tools/                          # New tools for CLI
        __init__.py
        edit.py                       # EditTool
        list_dir.py                   # ListDirectoryTool
        web_fetch.py                  # WebFetchTool

      context/                        # Context engine
        __init__.py
        conversation.py               # Item/Turn/Thread model
        kaizen_md.py                  # KAIZEN.md loader
        prompt_assembler.py           # System prompt assembly
        token_tracker.py              # Token counting + budget
        pricing.py                    # ModelPricing registry
        persistence.py                # Session JSONL persistence
        memory.py                     # Hot/warm/cold memory

      security/                       # Security model
        __init__.py
        path_guard.py                 # Working directory confinement
        kaizen_trust.py               # KAIZEN.md trust model
        destructive_detector.py       # Destructive command detection
        mcp_trust.py                  # MCP server trust model
        secrets.py                    # Secret redaction

      errors.py                       # Error taxonomy
```

### Dependency Graph

```
main.py
  |
  +-- repl.py (prompt_toolkit)
  |
  +-- agent/turn_runner.py
  |     |
  |     +-- streaming/clients/*.py (LLM clients)
  |     +-- streaming/protocol.py (StreamEvent)
  |     +-- streaming/retry.py (retry policy)
  |     |
  |     +-- tools/ (Edit, ListDir, WebFetch)
  |     +-- kaizen.tools.native/ (EXISTING: 12 native tools)
  |     |
  |     +-- hooks/manager.py (hook dispatch)
  |     +-- kaizen.core.autonomy.permissions/ (EXISTING: permission policy)
  |     |
  |     +-- context/conversation.py (Item/Turn/Thread)
  |     +-- context/compaction.py
  |     +-- context/token_tracker.py
  |     |
  |     +-- security/path_guard.py
  |     +-- security/destructive_detector.py
  |     |
  |     +-- multi_agent/manager.py (subagent dispatch)
  |
  +-- context/kaizen_md.py (KAIZEN.md loading)
  +-- context/prompt_assembler.py
  +-- context/persistence.py (session JSONL)
  |
  +-- security/kaizen_trust.py (KAIZEN.md trust)
  +-- first_run.py (API key setup)
  +-- config.py (settings loading)
```

---

## 10. Implementation Phases

### Phase 1: Core Loop (Sessions 1-2)

**Goal**: kz can have a multi-turn conversation with one model (Anthropic), execute tools, and save sessions.

| Task         | Component                                  | Lines      | Critical Path       |
| ------------ | ------------------------------------------ | ---------- | ------------------- |
| 1.1          | CLI entry point + REPL                     | 400        | Start here          |
| 1.2          | AnthropicClient (streaming)                | 350        | Parallel with 1.1   |
| 1.3          | StreamEvent protocol + ToolCallAccumulator | 240        | Before TurnRunner   |
| 1.4          | TurnRunner (core loop)                     | 800        | Depends on 1.2, 1.3 |
| 1.5          | Item/Turn/Thread conversation model        | 200        | Before TurnRunner   |
| 1.6          | Permission middleware wiring               | 100        | In TurnRunner       |
| 1.7          | Terminal renderer                          | 400        | Parallel with 1.4   |
| 1.8          | KAIZEN.md loading                          | 180        | Before first use    |
| 1.9          | Signal handling                            | 150        | In session loop     |
| 1.10         | Session persistence                        | 250        | After turns work    |
| **Subtotal** |                                            | **~3,070** |                     |

**Exit criteria**: `kz "What files are in this directory?"` works end-to-end with Claude, streams output, executes Read/Glob/Bash tools, persists session.

### Phase 2: Model Agnostic + Hooks (Sessions 3-4)

**Goal**: kz works with OpenAI, Gemini, and Ollama. Hook system fires COC artifacts.

| Task         | Component                                      | Lines      | Critical Path |
| ------------ | ---------------------------------------------- | ---------- | ------------- |
| 2.1          | OpenAIClient                                   | 300        |               |
| 2.2          | GeminiClient                                   | 200        |               |
| 2.3          | OllamaClient                                   | 200        |               |
| 2.4          | LLMClientFactory + model resolution            | 100        | After 2.1-2.3 |
| 2.5          | Hook system (14 events + subprocess execution) | 800        |               |
| 2.6          | COC bridge (hooks -> COC artifacts)            | 100        | After 2.5     |
| 2.7          | First-run setup                                | 120        |               |
| 2.8          | Config loading + validation                    | 150        |               |
| 2.9          | Error retry layer                              | 250        |               |
| **Subtotal** |                                                | **~2,220** |               |

**Exit criteria**: `kz -m gpt-4o "Explain this code"` works. `kz -m ollama/llama3 "Hello"` works. Hooks fire on every turn.

### Phase 3: Multi-Agent + Context Engine (Sessions 5-6)

**Goal**: Subagents work. Context compaction prevents overflow. Full tool set.

| Task         | Component                                       | Lines      | Critical Path |
| ------------ | ----------------------------------------------- | ---------- | ------------- |
| 3.1          | AgentManager (spawn, send, wait, close, resume) | 500        |               |
| 3.2          | 5 subagent tools                                | 300        | After 3.1     |
| 3.3          | Agent tree persistence                          | 200        | After 3.1     |
| 3.4          | CompactionEngine (3-level)                      | 300        |               |
| 3.5          | TokenTracker + ModelPricing                     | 220        |               |
| 3.6          | EditTool                                        | 250        |               |
| 3.7          | WebFetchTool + ListDirectoryTool                | 200        |               |
| 3.8          | Tool result truncation                          | 80         |               |
| **Subtotal** |                                                 | **~2,050** |               |

**Exit criteria**: kz can spawn subagents for parallel research. Context compaction works across 50+ turns. Edit tool enables surgical file edits.

### Phase 4: Security + PACT (Sessions 7-8)

**Goal**: Full security model. PACT envelope enforcement.

| Task         | Component                            | Lines      | Critical Path |
| ------------ | ------------------------------------ | ---------- | ------------- |
| 4.1          | PathGuard (confinement)              | 120        |               |
| 4.2          | KAIZEN.md trust model                | 150        |               |
| 4.3          | Destructive command detection        | 80         |               |
| 4.4          | MCP trust model                      | 100        |               |
| 4.5          | AgentEnvelope + monotonic tightening | 200        |               |
| 4.6          | PACT-specific StreamEvents           | 100        |               |
| 4.7          | Memory system (hot/warm/cold)        | 150        |               |
| 4.8          | Session file encryption (basic)      | 100        |               |
| 4.9          | MCP tool adapter                     | 200        |               |
| **Subtotal** |                                      | **~1,200** |               |

**Exit criteria**: kz enforces working directory confinement. PACT envelope checks intercept every tool call. Subagent envelopes are monotonically tightened.

### Phase Summary

| Phase | Sessions   | New Lines | Cumulative | Milestone                      |
| ----- | ---------- | --------- | ---------- | ------------------------------ |
| 1     | 1-2        | ~3,070    | ~3,070     | Single-model interactive agent |
| 2     | 3-4        | ~2,220    | ~5,290     | Model-agnostic + COC hooks     |
| 3     | 5-6        | ~2,050    | ~7,340     | Multi-agent + context engine   |
| 4     | 7-8        | ~1,200    | ~8,540     | Security + PACT governance     |
| Tests | Throughout | ~1,200    | **~9,740** | Full test coverage             |

---

## Appendix A: Kaizen Reuse Summary

| Kaizen Component                    | Reuse Level   | Where Used in kz                |
| ----------------------------------- | ------------- | ------------------------------- |
| `PermissionPolicy` (8-layer)        | DIRECT (100%) | Turn runner tool dispatch       |
| `PermissionMode` / `PermissionType` | DIRECT (100%) | Security model                  |
| `ExecutionContext`                  | DIRECT (100%) | Turn runner permission checking |
| `PermissionRule`                    | DIRECT (100%) | Config-driven tool permissions  |
| `BaseTool` / `NativeToolResult`     | DIRECT (100%) | All tools                       |
| `DangerLevel` / `ToolCategory`      | DIRECT (100%) | Tool classification             |
| 12 native tools                     | DIRECT (90%)  | Built-in tool set               |
| `CostTracker`                       | ADAPT (70%)   | Budget enforcement              |
| `HookHandler` protocol              | DIRECT (100%) | Python hooks                    |
| `HookEvent` enum                    | EXTEND (70%)  | CLI hook events                 |
| `HookManager`                       | EXTEND (60%)  | CLI hook manager                |
| `HookContext` / `HookResult`        | DIRECT (100%) | Hook dispatch                   |
| `OpenAIToolMapper`                  | ADAPT (60%)   | Tool definition formatting      |
| `GeminiToolMapper`                  | ADAPT (60%)   | Tool definition formatting      |
| MCP client                          | ADAPT (60%)   | MCP tool adapter                |
| `RetryMixin`                        | ADAPT (50%)   | Stream retry policy             |

**True reuse rate**: ~45% (aligns with red team's revised estimate of 40%, slightly higher due to permission system being directly usable).

---

## Appendix B: External Dependencies

```toml
[project]
dependencies = [
    "typer>=0.12",
    "rich>=13.0",
    "prompt-toolkit>=3.0",
    "aiofiles>=24.0",
    "httpx>=0.27",
    "tiktoken>=0.7",
]

[project.optional-dependencies]
anthropic = ["anthropic>=0.40"]
openai = ["openai>=1.50"]
gemini = ["google-genai>=1.0"]
ollama = []  # Uses httpx (already a dependency)
all = ["anthropic>=0.40", "openai>=1.50", "google-genai>=1.0"]
cli = ["kailash-kaizen[all]"]
```

---

## Appendix C: Success Criteria

| #   | Criterion          | Measurable Target                                           |
| --- | ------------------ | ----------------------------------------------------------- |
| 1   | Startup time       | First prompt visible in <500ms                              |
| 2   | Streaming latency  | First text delta rendered within 100ms of LLM start         |
| 3   | Tool execution     | Parallel tool calls complete within 1.1x of slowest         |
| 4   | Budget accuracy    | Actual cost within 10% of pre-call estimate                 |
| 5   | Context efficiency | Compaction frees 50%+ of non-recent tokens                  |
| 6   | Session resume     | Full context restored in <1s for 100-turn sessions          |
| 7   | Subagent isolation | Zero parent context leakage (verified by test)              |
| 8   | PACT enforcement   | 100% of tool calls pass through envelope check when enabled |
| 9   | Hook reliability   | 100% of hook events fire at correct lifecycle points        |
| 10  | Provider parity    | All 4 providers pass the same integration test suite        |
| 11  | Edit precision     | Edit tool handles all Claude Code edit test cases           |
| 12  | Confinement        | Zero path escapes under adversarial testing                 |

---

## Appendix D: Risk Register

| ID  | Risk                                                   | Likelihood | Impact   | Mitigation                                              | Status  |
| --- | ------------------------------------------------------ | ---------- | -------- | ------------------------------------------------------- | ------- |
| R1  | Streaming normalization breaks on provider API changes | Medium     | High     | Pin SDK versions, integration tests per provider        | Phase 2 |
| R2  | Context compaction loses critical information          | Medium     | High     | PreCompact hook for preservation, regression tests      | Phase 3 |
| R3  | Subagent budget accounting drift                       | Medium     | Medium   | Deduct from parent before spawn, reconcile on complete  | Phase 3 |
| R4  | KAIZEN.md injection attack                             | High       | Critical | Trust model + first-load confirmation in Phase 1        | Phase 1 |
| R5  | Destructive command not detected                       | Medium     | Critical | Pattern list + community contributions + ask-by-default | Phase 1 |
| R6  | Python startup time > 1s                               | Medium     | Low      | Lazy imports, measure on every release                  | Phase 1 |
| R7  | Ollama tool calling quality                            | High       | Medium   | JSON repair in ToolCallAccumulator                      | Phase 2 |
| R8  | asyncio task leaks in long sessions                    | Medium     | Medium   | TaskGroup, session health check                         | Phase 1 |
| R9  | MCP server exfiltration                                | Low        | High     | MCP trust model, explicit permission scopes             | Phase 4 |
| R10 | Agent tree persistence corruption                      | Low        | High     | SQLite WAL mode, atomic writes                          | Phase 3 |

---

_This specification is the implementation contract for the kz CLI. Every component, every interface, every data structure is defined here. Implementation sessions execute against this document, not against ad-hoc decisions._
