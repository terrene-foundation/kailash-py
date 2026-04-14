# Kailash Kaizen -- Domain Specification — Providers, Strategies, Tools & Memory

Version: 2.7.3
Package: `kailash-kaizen`

Parent domain: Kailash Kaizen AI agent framework. This file covers the provider system, execution strategies, tool integration (MCP), memory system, error handling, and streaming support. See also `kaizen-core.md`, `kaizen-signatures.md`, and `kaizen-advanced.md`.

---

## 8. Provider System

### 8.1 Provider Hierarchy

**Legacy ABC layer (backward compatibility):**

```
BaseAIProvider (ABC)
  LLMProvider(BaseAIProvider)       -- chat(), chat_async()
  EmbeddingProvider(BaseAIProvider) -- embed()
  UnifiedAIProvider(LLMProvider, EmbeddingProvider)
```

**SPEC-02 Protocol layer (structural typing):**

```
BaseProvider (Protocol)             -- name, capabilities, supports()
AsyncLLMProvider (Protocol)         -- chat_async()
StreamingProvider (Protocol)        -- stream_chat() -> AsyncGenerator[StreamEvent]
ToolCallingProvider (Protocol)      -- chat_with_tools()
StructuredOutputProvider (Protocol) -- chat_structured()
```

Protocols are `@runtime_checkable`. Concrete providers inherit from the ABC layer and satisfy the Protocol layer structurally.

### 8.2 ProviderCapability Enum

```python
class ProviderCapability(Enum):
    CHAT_SYNC = "chat_sync"
    CHAT_ASYNC = "chat_async"
    CHAT_STREAM = "chat_stream"
    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_output"
    EMBEDDINGS = "embeddings"
    VISION = "vision"
    AUDIO = "audio"
    REASONING_MODELS = "reasoning_models"
    BYOK = "byok"
```

### 8.3 Provider Registry

```python
PROVIDERS: dict[str, type | str] = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "cohere": CohereProvider,
    "huggingface": HuggingFaceProvider,
    "mock": MockProvider,
    "azure": "_unified_azure",        # Lazy-loaded
    "azure_openai": "_unified_azure",
    "azure_ai_foundry": AzureAIFoundryProvider,
    "docker": DockerModelRunnerProvider,
    "google": GoogleGeminiProvider,
    "gemini": GoogleGeminiProvider,
    "perplexity": PerplexityProvider,
    "pplx": PerplexityProvider,
}
```

#### get_provider(provider_name, provider_type=None)

Resolves a provider by name (case-insensitive). Optional `provider_type` filter: `"chat"` or `"embeddings"`.

Raises `ValueError` for unknown providers or capability mismatches.

#### get_provider_for_model(model: str) -> BaseProvider

Resolves a model identifier to its provider via structural prefix matching (NOT semantic classification):

| Prefix                                                    | Provider   |
| --------------------------------------------------------- | ---------- |
| `gpt-`, `o1-`, `o3-`, `o4-`, `ft:gpt`                     | openai     |
| `claude-`                                                 | anthropic  |
| `gemini-`                                                 | google     |
| `llama`, `mistral`, `mixtral`, `qwen`, `phi-`, `deepseek` | ollama     |
| `ai/`                                                     | docker     |
| `sonar`, `sonar-`                                         | perplexity |
| `mock-`, `mock`                                           | mock       |

Raises `UnknownProviderError` if no prefix matches.

#### get_streaming_provider(name_or_model: str) -> StreamingProvider

Resolves to a provider satisfying the `StreamingProvider` protocol. Raises `CapabilityNotSupportedError` if the provider does not support streaming.

### 8.4 Provider Error Hierarchy

```
ProviderError (base)
  UnknownProviderError          -- Provider name not in registry
  ProviderUnavailableError      -- Missing API key, uninstalled SDK, unreachable service
  CapabilityNotSupportedError   -- Requested capability not supported
  AuthenticationError           -- API key/credential validation failure
  RateLimitError                -- Rate limit / quota exceeded
  ModelNotFoundError            -- Model not available on provider
```

All errors carry `provider_name` and optional `original_error` attributes.

### 8.5 Unified Types

#### Message

```python
MessageContent = Union[str, List[Dict[str, Any]]]
Message = Dict[str, Union[str, MessageContent]]
```

#### ChatResponse

```python
@dataclass
class ChatResponse:
    id: str = ""
    content: str | None = ""
    role: str = "assistant"
    model: str = ""
    created: Any = None
    tool_calls: list[Any] = field(default_factory=list)
    finish_reason: str | None = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### TokenUsage

```python
@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
```

#### ToolCall

```python
@dataclass
class ToolCall:
    id: str
    type: str = "function"
    function_name: str = ""
    function_arguments: str = "{}"
```

#### StreamEvent

```python
@dataclass
class StreamEvent:
    # Token-by-token streaming event from LLM provider
```

---

## 9. Execution Strategies

All strategies implement the `ExecutionStrategy` protocol:

```python
@runtime_checkable
class ExecutionStrategy(Protocol):
    def execute(self, agent: Any, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]: ...
    def build_workflow(self, agent: Any) -> WorkflowBuilder: ...
```

### 9.1 SingleShotStrategy

One-pass execution. Suitable for Q&A, classification, extraction.

```python
strategy = SingleShotStrategy()
result = strategy.execute(agent, {"question": "What is AI?"})
```

### 9.2 AsyncSingleShotStrategy

Async variant of SingleShotStrategy. Default strategy for BaseAgent.

### 9.3 MultiCycleStrategy

Multi-cycle execution with feedback loops. Used for ReAct, iterative refinement, tool-using agents.

```python
def __init__(
    self,
    max_cycles: int = 5,
    convergence_check: callable = None,      # Legacy: (cycle_results) -> bool
    cycle_processor: callable = None,        # (inputs, cycle_num) -> Dict
    convergence_strategy: ConvergenceStrategy = None,  # New, takes precedence
)
```

**Execution flow per cycle:**

1. Pre-cycle hook
2. Execute cycle (Reason + Act)
3. Parse cycle result
4. Extract observation
5. Check termination condition
6. Continue or break

**Termination conditions:** max_cycles reached, agent signals completion (e.g., `"FINAL ANSWER:"`), error occurs, explicit `done` flag.

### 9.4 StreamingStrategy

Token-by-token streaming for chat/interactive use cases.

```python
strategy = StreamingStrategy(chunk_size=1)

# Blocking (returns final result)
result = await strategy.execute(agent, inputs)

# Streaming (yields tokens)
async for token in strategy.stream(agent, inputs):
    print(token, end="", flush=True)
```

### 9.5 ParallelBatchStrategy

Concurrent batch processing for high-throughput scenarios. Executes multiple inputs in parallel.

### 9.6 FallbackStrategy

Sequential fallback with progressive degradation. Tries strategies in order until one succeeds.

### 9.7 HumanInLoopStrategy

Human approval checkpoints for critical decisions. Pauses execution to request human input via ControlProtocol.

### 9.8 Convergence Strategies

Used with `MultiCycleStrategy` to determine when to stop iterating:

| Strategy                  | Description                          |
| ------------------------- | ------------------------------------ |
| `TestDrivenConvergence`   | Stop when all tests pass             |
| `SatisfactionConvergence` | Stop when confidence threshold met   |
| `HybridConvergence`       | Compose strategies with AND/OR logic |

---

## 10. Tool Integration (MCP)

Kaizen uses MCP (Model Context Protocol) as the sole tool integration mechanism. `ToolRegistry` and `ToolExecutor` are removed.

### 10.1 Builtin MCP Server

BaseAgent auto-connects to `kaizen.mcp.builtin_server` which provides 12 builtin tools:

- File operations (read_file, write_file, list_directory)
- HTTP operations (http_get, http_post)
- System operations (bash_command)
- Web operations (web_search)
- And more

### 10.2 Tool Discovery

```python
tools = await agent.discover_tools(
    category=ToolCategory.FILE,    # Optional filter
    safe_only=True,                # Only SAFE danger level
    keyword="file",                # Keyword search
)
```

### 10.3 Tool Execution

```python
result = await agent.execute_mcp_tool("read_file", {"path": "/tmp/data.txt"})
```

### 10.4 Tool Types

```python
class DangerLevel(Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ToolCategory(Enum):
    SYSTEM = "system"
    FILE = "file"
    API = "api"
    # ... etc.
```

```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    category: ToolCategory
    danger_level: DangerLevel
    parameters: List[ToolParameter]
    returns: Dict
    executor: Optional[Callable]

@dataclass
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = False

@dataclass
class ToolResult:
    # Tool execution result
```

### 10.5 MCP Suppression

When `config.has_structured_output` is True, MCP auto-discovery is suppressed because some providers (notably Gemini) reject requests combining function calling with JSON response mode. This is logged at DEBUG level.

---

## 11. Memory System

### 11.1 KaizenMemory (Abstract Base)

```python
class KaizenMemory(ABC):
    @abstractmethod
    def load_context(self, session_id: str) -> Any: ...

    @abstractmethod
    def save_turn(self, session_id: str, turn: Dict) -> None: ...
```

### 11.2 Memory Implementations

| Class                    | Storage         | Description                                        |
| ------------------------ | --------------- | -------------------------------------------------- |
| `BufferMemory`           | In-memory       | Full conversation history, configurable turn limit |
| `PersistentBufferMemory` | Database        | Buffer memory with DataFlow persistence backend    |
| `SummaryMemory`          | In-memory + LLM | LLM-generated summaries with recent verbatim turns |
| `VectorMemory`           | Vector store    | Semantic similarity search over conversation       |
| `KnowledgeGraphMemory`   | Graph           | Entity extraction and relationship tracking        |

### 11.3 SharedMemoryPool

Shared insight storage for multi-agent collaboration:

```python
pool = SharedMemoryPool()
pool.write_insight({
    "agent_id": "agent_1",
    "content": "User prefers concise answers",
    "tags": ["preference"],
    "importance": 0.8,
    "segment": "observation",
})

insights = pool.read_relevant(
    agent_id="agent_2",
    exclude_own=True,
    limit=10,
)
```

### 11.4 Enterprise Memory System

3-tier caching architecture:

```
HotMemoryTier   -- Recent, frequently accessed (in-memory)
WarmMemoryTier  -- Less frequent (database-backed)
ColdMemoryTier  -- Archival (cold storage)
```

```python
config = MemorySystemConfig(...)
system = EnterpriseMemorySystem(config)
monitor = MemoryMonitor(system)
```

### 11.5 Persistence Backends

```python
class PersistenceBackend(ABC):
    @abstractmethod
    async def save(self, session_id: str, data: Any) -> None: ...
    @abstractmethod
    async def load(self, session_id: str) -> Any: ...
```

---

## 20. Error Handling

### 20.1 BaseAgent Error Handling

The `_handle_error` extension point controls error behavior:

- When `error_handling_enabled=True` (default): logs error, returns `{"error": str, "type": class_name, "success": False}`.
- When `error_handling_enabled=False`: re-raises the exception.

### 20.2 Retry via RetryMixin

Applied when `error_handling_enabled=True` in config. Wraps execution with configurable retry logic.

### 20.3 Fallback Strategy

`FallbackStrategy` provides sequential fallback:

```python
strategy = FallbackStrategy(strategies=[
    primary_strategy,
    degraded_strategy,
    minimal_strategy,
])
```

Tries each strategy in order. First success wins.

### 20.4 Provider Errors

All provider-specific exceptions are wrapped into the `ProviderError` hierarchy (section 8.4). Consumers never need to depend on provider SDK exception types.

---

## 21. Streaming Support

### 21.1 StreamingProvider Protocol

```python
@runtime_checkable
class StreamingProvider(Protocol):
    def stream_chat(
        self,
        messages: List[Message],
        **kwargs,
    ) -> AsyncGenerator[StreamEvent, None]: ...
```

A single synthesized yield does NOT satisfy the contract -- real token-by-token streaming is required.

### 21.2 StreamingStrategy

```python
strategy = StreamingStrategy(chunk_size=1)

# Async generator
async for token in strategy.stream(agent, inputs):
    print(token, end="", flush=True)
```

### 21.3 StreamEvent

Emitted by providers during streaming. Contains token delta, metadata, and completion status.

### 21.4 Resolving a Streaming Provider

```python
from kaizen.providers.registry import get_streaming_provider

provider = get_streaming_provider("openai")       # By name
provider = get_streaming_provider("gpt-4o")        # By model
# Raises CapabilityNotSupportedError if provider can't stream
```
