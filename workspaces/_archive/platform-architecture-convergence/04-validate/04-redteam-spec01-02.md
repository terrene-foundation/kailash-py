# Red Team Report — SPEC-01 + SPEC-02

**Date**: 2026-04-08
**Branch**: feat/platform-architecture-convergence
**Auditor**: analyst (red team mode)
**Scope**: Verify implementation against SPEC-01 (kailash-mcp Package) and SPEC-02 (Provider Layer Split)
**Result**: **FAIL** — both specs are partially implemented with major gaps

---

## Summary

| Spec    | Sections Verified | Sections PASS | Sections PARTIAL | Sections FAIL |
| ------- | ----------------- | ------------- | ---------------- | ------------- |
| SPEC-01 | 13                | 1             | 5                | 7             |
| SPEC-02 | 11                | 2             | 4                | 5             |

**Critical findings**: 8
**High findings**: 11
**Medium findings**: 9
**Minor findings**: 6

**Top-line verdict**: The new packages (`packages/kailash-mcp/`, `packages/kailash-kaizen/.../providers/`) exist as scaffolding, but the canonical wire types, capability protocols, and consumer migrations that the specs treated as the _whole point_ of the work are absent. Both specs were implemented as **file copies + structural skeletons** rather than the type-driven, capability-first refactors they describe. Most critically, the **#339 fix is not implemented** (BaseAgent still imports from old paths), and the **#340 Gemini guard is not implemented** (tools + response_format still go through together without mutual exclusion).

The work that did land (file moves, pyproject.toml, ai_providers.py shim, cost.py skeleton) is real but it stops short of delivering the architectural outcomes the specs promised.

---

## SPEC-01 Findings

### CRITICAL

#### C1.1 — Canonical JSON-RPC types DO NOT EXIST

**Spec reference**: §2.1 (lines 50–195)
**Files expected**: `packages/kailash-mcp/src/kailash_mcp/protocol/jsonrpc.py`
**Files actual**: missing — only `protocol/protocol.py` (the legacy MessageType/ProgressManager file) and an `__init__.py` exposing those legacy classes.
**Evidence**:

- `grep -r "class JsonRpcRequest" packages/kailash-mcp/` → no matches
- `grep -r "class JsonRpcResponse" packages/kailash-mcp/` → no matches
- `grep -r "class JsonRpcError" packages/kailash-mcp/` → no matches

The spec calls these the "SINGLE source of truth for JSON-RPC types" that "Both Python and Rust MUST produce and consume". Without them, the cross-SDK interop test vectors (§7) cannot be implemented because there is nothing to serialize/deserialize through. ADR-008 cross-SDK alignment is unfounded.

#### C1.2 — McpToolInfo DOES NOT EXIST

**Spec reference**: §2.2 (lines 197–230) and §3.4 (sub-issue 1 of #339)
**Files expected**: `packages/kailash-mcp/src/kailash_mcp/protocol/types.py`
**Files actual**: missing
**Evidence**: `grep -r "class McpToolInfo" packages/kailash-mcp/` → no matches

This is the type that was supposed to carry `server_name` and `server_config` through the conversion pipeline — the _root-cause fix_ for issue #339 sub-issue 1. Without it, the metadata that `tool_formatters.py` was stripping is still being stripped and #339 remains unfixed at the type level.

#### C1.3 — Unified ToolRegistry DOES NOT EXIST

**Spec reference**: §2.5 (lines 523–678)
**Files expected**: `packages/kailash-mcp/src/kailash_mcp/tools/registry.py`
**Files actual**: `packages/kailash-mcp/src/kailash_mcp/tools/__init__.py` is a 5-line stub with only a docstring; only `hydrator.py` exists in the directory.
**Evidence**:

- `grep -r "class ToolRegistry" packages/kailash-mcp/` → no matches
- `grep -r "class ToolDef" packages/kailash-mcp/` → no matches
- `grep -r "to_openai_format" packages/kailash-mcp/` → no matches

The unified ToolRegistry was the second half of the #339 fix — the bridge that gives every tool both a JSON schema (for LLM signature) and a callable executor (for AgentLoop). Without it, BaseAgent's tool system and Delegate's tool system remain split, and the spec's promise that "All consumers (BaseAgent, Delegate, Nexus, etc.) use this class" is not delivered.

#### C1.4 — kailash_mcp.MCPClient is missing the API the spec requires

**Spec reference**: §2.3 (lines 260–472), §3.2 (server lifecycle)
**Files actual**: `packages/kailash-mcp/src/kailash_mcp/client.py` exists but is a copy-paste of the legacy `src/kailash/mcp_server/client.py` (both files are exactly 1088 lines with `class MCPClient:` on the same line 29).
**Evidence**:

- `wc -l` on both shows 1088 lines.
- `grep -n "discover_and_register" packages/kailash-mcp/` → no matches.
- The spec class signature requires `__init__(*, transport, discovery, auth, retry, metrics, timeout)` plus `__aenter__/__aexit__/start/stop/list_tools/call_tool/list_resources/read_resource/get_prompt/discover_and_register/server_info/is_connected`.
- The actual class is the legacy production client which uses `discover_tools(server_config)` and per-call session management — a totally different surface.

The new client cannot satisfy §2.3 because its method names, parameters, and lifecycle differ from the spec. There is no `discover_and_register()` (the bridge that fixes #339 sub-issues 2 and 4).

#### C1.5 — Backward-compat shim at `src/kailash/mcp_server/__init__.py` is NOT a shim — it is a duplicate codebase

**Spec reference**: §4 (lines 747–778)
**Files actual**: `src/kailash/mcp_server/__init__.py` still imports from local `.client`, `.server`, `.auth`, `.discovery`, `.errors`, `.protocol`, `.advanced_features`, `.transports`, `.oauth`, `.registry_integration`, `.subscriptions`. **It does NOT import from `kailash_mcp`.** No `DeprecationWarning` is raised.
**Evidence**:

- `grep -r DeprecationWarning src/kailash/mcp_server/` → 0 matches
- `head -200 src/kailash/mcp_server/__init__.py` still uses relative imports
- `wc -l src/kailash/mcp_server/client.py` = 1088 (same as `packages/kailash-mcp/src/kailash_mcp/client.py`)
- `wc -l src/kailash/mcp_server/server.py` = 2508 vs `packages/kailash-mcp/src/kailash_mcp/server.py` = 2518 (slight drift already!)
- `wc -l src/kailash/mcp_server/oauth.py` = 1424 = `packages/kailash-mcp/src/kailash_mcp/auth/oauth.py` = 1424

This is the worst possible outcome: TWO copies of every file exist in the tree. The spec called for `MOVE` (delete source) plus a re-export shim. Instead, the source files were COPIED and the original `src/kailash/mcp_server/` remains the canonical implementation that the rest of the codebase imports. The drift is already starting (server.py: 10-line gap). Every future bug fix will have to be applied twice or the two will diverge silently.

#### C1.6 — Consumer migration NOT performed (#339 not fixed at the import boundary)

**Spec reference**: §4 import path migration table; §9 step 15 ("Migrate BaseAgent (`base_agent.py:40`) to import from `kailash_mcp` — fixes #339")
**Evidence**: `grep -r "from kailash.mcp_server\|from kailash.mcp " packages/kailash-kaizen/src/kaizen/`

```
packages/kailash-kaizen/src/kaizen/core/base_agent.py
packages/kailash-kaizen/src/kaizen/core/mcp_mixin.py
packages/kailash-kaizen/src/kaizen/nodes/ai/llm_agent.py
packages/kailash-kaizen/src/kaizen/nodes/ai/iterative_llm_agent.py
packages/kailash-kaizen/src/kaizen/mcp/builtin_server/server.py
packages/kailash-kaizen/src/kaizen/mcp/builtin_server/tools/__init__.py
```

And there are zero `from kailash_mcp` imports anywhere in `packages/kailash-kaizen/src/kaizen/`.

BaseAgent and the AI nodes still import from the legacy path. Step 15 of §9 (the _primary_ purpose of the spec — fix #339) was not performed. The new package is therefore an orphaned duplicate that no production code uses.

#### C1.7 — kaizen-agents/delegate/mcp.py NOT deleted

**Spec reference**: §1 manifest table row "DELETED" + §9 step 16
**Evidence**: `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` still exists (full file with `McpServerConfig` dataclass). No `from kailash_mcp` redirect; no DeprecationWarning. It is the same 509-LOC file the spec told us to delete after the new MCPClient was wired in.

Because step 15 (#1.6) was skipped, this file cannot be deleted yet — but no migration plan or shim exists to make that deletion safe. Two MCP clients still live in the tree.

#### C1.8 — Files marked DELETED in §1 still exist at full size

**Spec reference**: §1 manifest table
**Evidence**:

- `src/kailash/api/mcp_integration.py` — spec says DELETED ("zero consumers verified") — still exists, 425 lines.
- `src/kailash/middleware/mcp/enhanced_server.py` — spec says AUDIT — still exists, 513 lines, no decision recorded.
- `src/kailash/middleware/mcp/client_integration.py` — spec says AUDIT — still exists, 538 lines, no decision recorded.
- `packages/kailash-nexus/src/nexus/mcp/__init__.py` — spec says DELETED — not verified (would need to glob nexus tree).

§8 explicitly said "Read the file during implementation, decide based on consumer count. Track in the /todos phase." That decision was never made or recorded.

### HIGH

#### H1.1 — Channels/mcp_channel.py NOT refactored

**Spec reference**: §1 row "REFACTORED to import from `kailash_mcp`"
**Evidence**: `src/kailash/channels/mcp_channel.py` lines 19–28 still import from `..middleware.mcp.enhanced_server`. No `kailash_mcp` import. The refactor described in §1 + §9 step 18 did not happen.

#### H1.2 — `nodes/enterprise/mcp_executor.py` NOT refactored

**Spec reference**: §1 row "Refactor to import from `kailash_mcp`" + §9 step 20
**Evidence**: `grep "from kailash_mcp" src/kailash/nodes/enterprise/mcp_executor.py` → no matches. The file imports nothing MCP-related from the new package.

#### H1.3 — `nodes/mixins/mcp.py` NOT refactored

**Spec reference**: §1 row + §9 step 21
**Evidence**: same — no `kailash_mcp` imports.

#### H1.4 — `MCPTransport` protocol class is not exposed as the spec defines

**Spec reference**: §2.4 (lines 474–521)
**Files actual**: `transports/transports.py` defines `BaseTransport`, `EnhancedStdioTransport`, `SSETransport`, `StreamableHTTPTransport`, `WebSocketTransport`, `TransportSecurity`, `TransportManager`, but NO `MCPTransport` `Protocol` class. The spec wants `@runtime_checkable class MCPTransport(Protocol)` with `connect/disconnect/send/is_connected`.

Without the Protocol, there is no structural typing contract for third-party transports, and the rust crate cannot mirror it via trait equivalence per §13.

#### H1.5 — Public API exports do not include the canonical types

**Spec reference**: §4 import migration table — `from kailash_mcp import MCPClient, MCPServer, JsonRpcRequest, JsonRpcResponse, JsonRpcError, McpError, ..., McpToolInfo, McpResourceInfo, ServerInfo, ServerCapabilities, ToolRegistry, ToolDef`
**Evidence**: `packages/kailash-mcp/src/kailash_mcp/__init__.py` `__all__` (lines 162–277) lists 80+ symbols but **none** of these spec-required ones: `JsonRpcRequest`, `JsonRpcResponse`, `JsonRpcError`, `McpToolInfo`, `McpResourceInfo`, `ServerCapabilities`, `ToolRegistry`, `ToolDef`. The `ServerInfo` that IS exported is from `discovery/discovery.py` (a discovery struct with `transport`/`capabilities: List[str]`), not the spec's `ServerInfo` (identity + `ServerCapabilities` dataclass).

Anyone following the spec example `from kailash_mcp import McpToolInfo` will get an `ImportError`.

#### H1.6 — `__init__.py` does not emit deprecation warnings on the legacy path

**Spec reference**: §4 (lines 752–761) — the shim at `src/kailash/mcp_server/__init__.py` MUST raise `DeprecationWarning`.
**Evidence**: `grep -r DeprecationWarning src/kailash/mcp_server/` → 0 matches.

Even if the duplication issue C1.5 were fixed, the deprecation signal is missing — users have no migration trigger.

#### H1.7 — `errors.py` exports do not align with the spec hierarchy

**Spec reference**: §3.3 (lines 702–735) — defines `McpError`, `McpTransportError`, `McpProtocolError`, `McpToolNotFoundError`, `McpToolExecutionError`, `McpTimeoutError`, `McpAuthenticationError`, `ToolNotFoundError`, `ToolNotExecutableError`, `ToolExecutionError`.
**Evidence**: `kailash_mcp/__init__.py` exports `MCPError`, `MCPErrorCode`, `AuthenticationError`, `AuthorizationError`, `RateLimitError`, `ToolError`, `ResourceError`, `TransportError`, `ServiceDiscoveryError`, `ValidationError`, `RetryStrategy`, `RetryableOperation`, `ExponentialBackoffRetry`, `CircuitBreakerRetry`, `ErrorAggregator`. **None** of the `Mcp*Error` classes from the spec exist. The legacy `MCPError`/`ToolError` shape is preserved instead.

`McpToolNotFoundError`, `McpToolExecutionError`, `McpTimeoutError`, `McpAuthenticationError`, `ToolNotFoundError`, `ToolNotExecutableError`, `ToolExecutionError` cannot be raised, caught, or matched by callers writing to the spec.

#### H1.8 — Test directories exist but contain ZERO tests

**Spec reference**: §10 — list of new tests required (Unified ToolRegistry tests, MCPClient + ToolRegistry integration, cross-SDK interop vectors, backward-compat shim tests)
**Evidence**: `glob packages/kailash-mcp/tests/**/*.py` → only `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/e2e/__init__.py`, `tests/conftest.py`. Not a single test file.

None of the §10 tests exist. The interop vectors in §7 (5 JSON test cases) have nothing to validate against.

### MEDIUM

#### M1.1 — pyproject.toml `name` matches but other details drift from spec §12

**Spec §12** lists:

```toml
dependencies = [ ]   # Minimal core
[project.optional-dependencies]
http = ["httpx>=0.27"]
sse = ["sse-starlette>=1.8"]
auth-jwt = ["pyjwt>=2.8"]
auth-oauth = ["authlib>=1.3"]
server = ["mcp>=1.0"]
```

**Actual**:

```toml
dependencies = [ "kailash>=2.2.0", "mcp[cli]>=1.23.0", "pydantic>=2.6" ]
http = ["aiohttp>=3.12.4", "httpx>=0.25.0"]
sse = ["aiohttp>=3.12.4"]                  # not sse-starlette
auth-jwt = ["PyJWT>=2.8", "cryptography>=41.0"]
auth-oauth = ["PyJWT>=2.8", "cryptography>=41.0", "aiohttp>=3.12.4"]   # not authlib
server = ["fastapi>=0.115.12", "uvicorn[standard]>=0.31.0"]            # not mcp>=1.0
```

- The spec said the core should be minimal; actual core has 3 deps including a dependency on the parent `kailash>=2.2.0`, which **inverts the dependency direction** (the new sub-package now depends on the parent SDK rather than being usable standalone — defeats the extraction).
- `http` shouldn't pull in aiohttp.
- `auth-oauth` uses cryptography+aiohttp instead of authlib.
- `server` uses fastapi/uvicorn rather than the official `mcp` Python SDK.
- `httpx>=0.25.0` is below the spec's `>=0.27` floor.
- Build backend is `setuptools` (spec says `hatchling`).

These are not necessarily wrong choices, but they were not justified anywhere. They drift from the spec without an ADR.

#### M1.2 — Discovery/ServerInfo namespace collision

The exported `ServerInfo` (from `discovery/discovery.py`) is structurally different from the spec's `ServerInfo` (from `protocol/types.py`). Same name, different shape, exported from `kailash_mcp` top level. Anyone reading the spec will use one type and find their code breaking against the other.

#### M1.3 — Spec §8 decision points not recorded

- TrustPlane: §8 recommends Option B (keep at original location). Implementation matches Option B _de facto_ but a `contrib/trust.py` was added that does **lightweight reading**, not the moved server. The decision was effectively "neither A nor B" (write a third file). This is fine but undocumented.
- `middleware/mcp/enhanced_server.py`: §8 says "Read the file during implementation, decide based on consumer count. Track in the /todos phase." Not done.
- `oauth.py`: §8 picks Option A. Implementation matches (lives in `kailash_mcp/auth/oauth.py`) — but the file at the _old_ location also still exists at full size (C1.5). So the decision was applied as a copy, not a move.

#### M1.4 — Server name qualification semantics not validated

**Spec §3.1** mandates `{server_name}__{tool_name}` qualification when using ServiceRegistry. Without `discover_and_register()` and `McpToolInfo`, there is no place to enforce this. Single-server vs multi-server semantics are not exercised.

#### M1.5 — Migration order steps 1–14 partially executed but in copy mode

Steps 1, 2, 4, 5, 6, 7, 9, 10, 13 (file presence) are visibly attempted. Steps 3 (transport base.py with the Protocol class), 8 (retry — the directory exists with only `__init__.py`), 11 (unified ToolRegistry), 12 (ToolHydrator move), 14 (real shims), 15 (BaseAgent migration), 16 (delete delegate/mcp.py), 17 (delete api/mcp_integration.py), 18 (refactor channels/mcp_channel.py), 19 (decide middleware/mcp), 20 (refactor mcp_executor.py), 21 (refactor mixins/mcp.py), 22 (run full test suite), 23 (add new tests) are NOT executed.

12 of 23 steps incomplete or unstarted = 52% incomplete.

### MINOR

#### m1.1 — README.md exists but spec doesn't require auditing it; not checked here.

#### m1.2 — `retry/` directory has only `__init__.py` (the retry implementations live inside `errors.py` as `ExponentialBackoffRetry`/`CircuitBreakerRetry`). Functional, but the spec layout in §6 implies a separate `retry/` module.

#### m1.3 — `subscriptions.py` lives in `advanced/subscriptions.py` (matches spec) — PASS.

#### m1.4 — `resource_cache.py` lives in `advanced/resource_cache.py` (matches spec) — PASS.

#### m1.5 — The duplicate `src/kailash/mcp_server/servers/ai_registry.py` referenced by `grep` (a sub-directory of the legacy mcp_server/) was never mentioned in §1; it is now orphaned by the spec's intent.

---

## SPEC-02 Findings

### CRITICAL

#### C2.1 — Capability Protocol classes DO NOT EXIST

**Spec reference**: §2.1 (lines 30–101)
**Files expected**: `packages/kailash-kaizen/src/kaizen/providers/base.py` with `ProviderCapability` enum + `BaseProvider`, `LLMProvider`, `AsyncLLMProvider`, `StreamingProvider`, `EmbeddingProvider`, `ToolCallingProvider`, `StructuredOutputProvider` as `@runtime_checkable Protocol` classes.
**Files actual**: `base.py` defines `BaseAIProvider(ABC)`, `LLMProvider(BaseAIProvider)`, `EmbeddingProvider(BaseAIProvider)`, `UnifiedAIProvider(LLMProvider, EmbeddingProvider)`. **None are `Protocol`** — they are ABCs. There is **no `ProviderCapability` enum**. There is **no `AsyncLLMProvider`, no `StreamingProvider`, no `ToolCallingProvider`, no `StructuredOutputProvider`**. Capabilities are stored as `dict[str, bool]` with only two keys (`"chat"`, `"embeddings"`).

The "capability protocol split" that the spec is _named after_ was not performed. The implementation reproduces the old monolith's hierarchy 1:1 with no protocol/runtime-checkable split. ADR-005 is not delivered.

#### C2.2 — Wire types are NOT frozen dataclasses, and several types are missing

**Spec reference**: §2.2 (lines 105–173)
**Spec required**:

- `Message` as `@dataclass` with `role: Literal[...]`, `content: Union[str, list[ContentBlock]]`, `name`, `tool_call_id`, `tool_calls`
- `ContentBlock` dataclass with type/text/image_url/audio_url
- `ToolCall` dataclass with `id`, `type: Literal["function"]`, `function: Optional[ToolCallFunction]`
- `ToolCallFunction` dataclass with `name`, `arguments`
- `ChatResponse` dataclass with `id`, `model`, `content`, `role: Literal["assistant"]`, `finish_reason`, `tool_calls`, `usage: TokenUsage`, `metadata`
- `TokenUsage` dataclass
- `StreamEvent` dataclass with `event_type: Literal[...]`, `delta_text`, `tool_call: Optional[ToolCall]`, `finish_reason`, `usage: Optional[TokenUsage]`, `content`

**Actual** (`providers/types.py`):

- `Message = Dict[str, Union[str, MessageContent]]` — a **type alias to dict**, not a dataclass. Spec violation.
- `ContentBlock` — **does not exist**.
- `ToolCallFunction` — **does not exist**.
- `ToolCall` — exists but has `function_name`/`function_arguments` flat fields instead of nested `function: ToolCallFunction`. Different shape on the wire.
- `ChatResponse` — exists but `usage: dict[str, int]` instead of `TokenUsage`, `finish_reason: str | None` instead of `Literal[...]`, `role: str` instead of `Literal["assistant"]`.
- `TokenUsage` — exists but is **not frozen**.
- `StreamEvent` — exists but `event_type: str` instead of `Literal[...]`, `tool_calls: list[dict[str, Any]]` instead of `tool_call: Optional[ToolCall]`. Different shape.

Cross-SDK type parity (§11) is not achievable because Python's `Message` is a dict and Rust's would be a struct — they cannot share a wire format.

#### C2.3 — Gemini #340 mutual-exclusion guard NOT implemented

**Spec reference**: §2.7 (lines 601–647) and §7.3 test vector
**Files actual**: `providers/llm/google.py` `_build_config_params()` (lines 288–314) and `chat()/chat_async()` (lines 361–400, 401+).
**Evidence**: There is **no check** that strips `response_format` when `tools` are present. Both can be set simultaneously and both are passed through:

```python
config_params = self._build_config_params(generation_config)        # adds response_mime_type if response_format set
request_config = types.GenerateContentConfig(**config_params)
...
if tools:
    request_config.tools = self._convert_tools(tools)                # tools added regardless
```

No warning is logged. No guard exists. Issue #340 is reproduced verbatim by the new code.

This is the _only_ Gemini-specific work the spec called out by issue number, and it is missing.

#### C2.4 — `get_provider_for_model()`, `get_streaming_provider()`, `get_embedding_provider()` DO NOT EXIST

**Spec reference**: §2.4 (lines 309–352)
**Evidence**: `providers/registry.py` exposes only `get_provider(provider_name, provider_type)` and `get_available_providers()`. No model-prefix dispatch, no auto-detection by model name, no streaming-capability lookup, no embedding-capability lookup. `_auto_register()` lazy initialization is also missing.

Without `get_provider_for_model()`, BaseAgent cannot resolve a provider from `model="claude-sonnet-4-5"` — which is _exactly_ what SPEC-04 (BaseAgent slimming) §10 says it depends on. This blocks SPEC-04.

#### C2.5 — No streaming support whatsoever in the new providers

**Spec reference**: §2.5 (lines 440–484) — `OpenAIProvider.stream_chat()` returning `AsyncGenerator[StreamEvent, None]`; §1 row "merged into `kaizen/providers/llm/openai.py`" — streaming + sync in one file
**Evidence**: `grep -r "async def stream_chat\|def stream_chat" packages/kailash-kaizen/src/kaizen/providers/llm/` → no matches. **No `stream_chat` method exists in any provider**.

The legacy streaming code lives in `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/openai_stream.py` and the four `*_adapter.py` files, all of which are still in place and not migrated. The promised merge of streaming into the per-provider modules did not happen.

This means `StreamingProvider` (which doesn't exist anyway, see C2.1) has no implementations, and SPEC-03 (StreamingAgent) cannot use this layer.

### HIGH

#### H2.1 — `kaizen_agents/delegate/adapters/` NOT deleted or shimmed

**Spec reference**: §1 manifest table — every adapter file is either DELETED or replaced by a shim; §4 (lines 696–707) — `__init__.py` becomes a deprecation shim re-exporting from `kaizen.providers`.
**Evidence**: All eight original files (`__init__.py`, `protocol.py`, `registry.py`, `openai_adapter.py`, `openai_stream.py`, `anthropic_adapter.py`, `google_adapter.py`, `ollama_adapter.py`) still exist with full content. `__init__.py` imports from `kaizen_agents.delegate.adapters.protocol` and `kaizen_agents.delegate.adapters.registry` (both still local), not from `kaizen.providers`. **No `DeprecationWarning`**.

#### H2.2 — `cost.py` API does not match the spec

**Spec reference**: §2.3 (lines 175–263)
**Spec required**:

- `CostTracker.record_usage(model: str, usage: TokenUsage) -> float`
- Microdollar (integer) precision
- `total_cost_usd` property
- `check_budget() -> bool`
- `_resolve_pricing(model)` with **prefix matching** against `DEFAULT_PRICING`
- `DEFAULT_PRICING` constant pre-populated
- `CostConfig.budget_limit_usd: Optional[float]`

**Actual**:

- `record(model, *, prompt_tokens, completion_tokens) -> float` — different signature, takes ints not `TokenUsage`.
- Float precision (`self._total_cost_usd: float += cost`) — drift risk over millions of calls (the precise reason the spec mandates microdollars).
- `total_cost_usd` exists — PASS.
- `check_budget()` — **does not exist**.
- Pricing lookup is exact match (`self._config.pricing.get(model, ModelPricing())`); no prefix matching.
- `DEFAULT_PRICING` — **does not exist**. Empty dict default.
- `budget_limit_usd` — **does not exist**.

Budget enforcement (which SPEC-03 §10 says is the consumer of CostTracker) cannot be implemented against this API.

#### H2.3 — `format_tools_for_provider()` and `format_response_schema()` do not exist

**Spec reference**: §2.5 (OpenAI) lines 500–514, §2.6 implications, §2.7 Google
**Evidence**: `grep -r "format_tools_for_provider\|format_response_schema" packages/kailash-kaizen/src/kaizen/providers/` → no matches. The provider-side tool/schema formatting that `ToolRegistry` is supposed to call is absent.

This means the unified ToolRegistry → provider tool-format pipeline (the bridge between SPEC-01 and SPEC-02) has no provider-side hook. Provider-specific tool format conversion still lives in `kaizen_agents/runtime_adapters/tool_mapping/openai.py` and friends — separate code path.

#### H2.4 — Hardcoded model name defaults across providers (env-models.md violation + spec §5.4)

**Spec §5.4**: "model names MUST come from `.env` or explicit parameter, never hardcoded."
**Evidence**:

- `providers/llm/anthropic.py:122,197` → `kwargs.get("model", "claude-3-sonnet-20240229")` (and the comment claims this is a deprecated model)
- `providers/llm/openai.py:158,295` → `"o4-mini"`
- `providers/llm/openai.py:430,458` → `"text-embedding-3-small"`
- `providers/llm/google.py:365,407` → `"gemini-2.0-flash"`
- `providers/llm/google.py:447,481` → `"text-embedding-004"`
- `providers/llm/ollama.py:93,210` → `"llama3.1:8b-instruct-q8_0"`, `"snowflake-arctic-embed2"`
- `providers/llm/docker.py:99,189,276,296` → `"ai/llama3.2"`, `"ai/mxbai-embed-large"`

Spec-rule violation in 6 of 9 LLM providers. The Anthropic default in particular (`claude-3-sonnet-20240229`) is a deprecated model — calls will fail.

#### H2.5 — `streaming.py` (StreamingChatAdapter protocol) does not exist

**Spec reference**: §1 manifest row — `kaizen_agents/delegate/adapters/protocol.py` → `kaizen/providers/streaming.py`
**Evidence**: `glob packages/kailash-kaizen/src/kaizen/providers/streaming.py` → no file. The protocol class was not moved. (The legacy file still lives at `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/protocol.py`.)

#### H2.6 — Public API (`providers/__init__.py`) does not export the spec-required names

**Spec reference**: §2 + §4 (consumers should `from kaizen.providers import get_streaming_provider`, etc.)
**Evidence**: `providers/__init__.py` `__all__` does not include `BaseProvider`, `AsyncLLMProvider`, `StreamingProvider`, `ToolCallingProvider`, `StructuredOutputProvider`, `ProviderCapability`, `get_provider_for_model`, `get_streaming_provider`, `get_embedding_provider`. (Many of these don't exist anyway — see C2.1, C2.4.)

Exports `BaseAIProvider`, `LLMProvider`, `EmbeddingProvider`, `UnifiedAIProvider` instead — the legacy ABC names.

#### H2.7 — No new provider-layer tests

**Spec reference**: §9 (lines 814–823) — `tests/unit/providers/test_*.py` per provider, plus `test_registry.py`, `test_cost.py`, `test_capabilities.py`
**Evidence**: `glob packages/kailash-kaizen/tests/unit/providers/*.py` →

```
test_ollama_availability.py
test_ollama_provider.py
test_ollama_vision_provider.py
test_ollama_model_manager.py
test_multi_modal_adapter.py
__init__.py
```

Only legacy Ollama tests. **No `test_registry.py`, `test_cost.py`, `test_capabilities.py`, `test_openai.py`, `test_anthropic.py`, `test_google.py` (with #340 vector), `test_perplexity.py`, `test_docker.py`, `test_azure.py`, `test_mock.py`, `test_cohere.py`, `test_huggingface.py`**.

The §7 interop test vectors (capability consistency, reasoning model filtering, Gemini mutual exclusion) cannot run because the test files don't exist and the underlying types/capabilities don't exist either.

### MEDIUM

#### M2.1 — `ai_providers.py` shim does not emit DeprecationWarning

**Spec reference**: §4 (lines 682–694) — explicit `warnings.warn(... DeprecationWarning ...)` at the top of the shim.
**Evidence**: `packages/kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py` lines 17–22 explicitly opt out: "No module-level deprecation warning here because internal modules ... import from this shim. A module-level warning would fire on every `import kaizen`."

The justification is sensible (avoid spam), but it means external users get no migration signal. A reasonable middle ground (filter on module name, or warn only on specific symbols) was not attempted. Spec text is violated.

#### M2.2 — `ai_providers.py` is the only file that was actually shimmed

A real shim exists for `kaizen.nodes.ai.ai_providers` (63 lines, re-exports from `kaizen.providers`). This is the one thing that was done correctly per spec §4. No other shim from §1 (delegate/adapters/**init**.py, etc.) exists.

#### M2.3 — Provider modules use ABCs and dict capabilities — they pass `isinstance` checks against `LLMProvider` (the ABC) but cannot pass them against the spec's `runtime_checkable` Protocol classes (which don't exist)

This means the §7.1 capability consistency test ("every provider's declared capabilities match the protocols it implements") is impossible to write.

#### M2.4 — `errors.py` file structure differs

**Spec required**: `errors.py` next to `base.py` exposing `ProviderError`, `UnknownProviderError`, `CapabilityNotSupportedError`. **Actual**: file exists, exports `AuthenticationError`, `CapabilityNotSupportedError`, `ModelNotFoundError`, `ProviderError`, `ProviderUnavailableError`, `RateLimitError`, `UnknownProviderError`. PASS overall, but `CapabilityNotSupportedError` is unused (no `get_streaming_provider` to raise it).

#### M2.5 — Embedding provider directory matches spec layout (cohere, huggingface). PASS.

### MINOR

#### m2.1 — `embedding/openai.py` and `embedding/ollama.py` are not separate modules

**Spec §6** shows `embedding/openai.py` and `embedding/ollama.py` as possibilities ("if separate from LLM — or merged into llm/openai.py"). Implementation merged — explicitly allowed. PASS.

#### m2.2 — `llm/azure.py` exists and inherits from `UnifiedAzureProvider` lazily — matches spec §3 wrapper pattern intent.

#### m2.3 — `mock.py` provider exists (PASS).

#### m2.4 — `perplexity.py` and `docker.py` providers exist (PASS).

#### m2.5 — Embedding `cohere.py` and `huggingface.py` exist (PASS).

#### m2.6 — `_REASONING_PREFIXES` in spec is a tuple constant; the actual `OpenAIProvider` uses regex patterns (`^o1`, `^o3`) — functionally equivalent but slightly more permissive (matches `o1` exact, `o3` exact, etc.). Acceptable.

---

## Spec Coverage Matrix

### SPEC-01

| Spec Section                                                                | Implementation File                                                       | Status      | Notes                                           |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ----------- | ----------------------------------------------- |
| §1 manifest — `mcp_server/client.py` MOVE                                   | `kailash_mcp/client.py` AND `src/kailash/mcp_server/client.py`            | **FAIL**    | Both copies exist, drift risk                   |
| §1 manifest — `mcp_server/server.py` MOVE                                   | both                                                                      | **FAIL**    | Drift already (10-line gap)                     |
| §1 manifest — `mcp_server/protocol.py` MOVE+SPLIT                           | `kailash_mcp/protocol/protocol.py` (single file)                          | **PARTIAL** | No split into jsonrpc/types                     |
| §1 manifest — `mcp_server/transports.py` MOVE+SPLIT                         | `kailash_mcp/transports/transports.py` (single file)                      | **PARTIAL** | No per-transport split                          |
| §1 manifest — `mcp_server/auth.py` MOVE+SPLIT                               | `kailash_mcp/auth/providers.py`                                           | **PARTIAL** | Single file, no split                           |
| §1 manifest — `mcp_server/oauth.py` MOVE                                    | `kailash_mcp/auth/oauth.py` (1424 LOC) AND original                       | **FAIL**    | Duplicate                                       |
| §1 manifest — `mcp_server/discovery.py` MOVE                                | `kailash_mcp/discovery/discovery.py` AND original                         | **FAIL**    | Duplicate                                       |
| §1 manifest — `kailash/mcp/platform_server.py`                              | `kailash_mcp/platform_server.py` AND `src/kailash/mcp/platform_server.py` | **FAIL**    | Duplicate                                       |
| §1 manifest — `kailash/mcp/contrib/`                                        | `kailash_mcp/contrib/` AND `src/kailash/mcp/contrib/`                     | **FAIL**    | Duplicate                                       |
| §1 manifest — `kaizen_agents/delegate/mcp.py` DELETE                        | still exists at full size                                                 | **FAIL**    |                                                 |
| §1 manifest — `kaizen_agents/delegate/tools/hydrator.py` MOVE               | `kailash_mcp/tools/hydrator.py` AND original                              | **FAIL**    | Duplicate                                       |
| §1 manifest — `api/mcp_integration.py` DELETE                               | still exists, 425 LOC                                                     | **FAIL**    |                                                 |
| §1 manifest — `channels/mcp_channel.py` REFACTOR                            | not refactored                                                            | **FAIL**    | Still imports from middleware/mcp               |
| §1 manifest — `middleware/mcp/enhanced_server.py` AUDIT                     | not audited                                                               | **FAIL**    |                                                 |
| §1 manifest — `middleware/mcp/client_integration.py` AUDIT                  | not audited                                                               | **FAIL**    |                                                 |
| §1 manifest — `kailash-nexus/.../mcp/__init__.py` DELETE                    | not verified                                                              | UNKNOWN     |                                                 |
| §1 — `nodes/enterprise/mcp_executor.py` REFACTOR                            | not refactored                                                            | **FAIL**    | No `kailash_mcp` import                         |
| §1 — `nodes/mixins/mcp.py` REFACTOR                                         | not refactored                                                            | **FAIL**    | No `kailash_mcp` import                         |
| §2.1 — `JsonRpcRequest/Response/Error`                                      | missing                                                                   | **FAIL**    | Critical                                        |
| §2.2 — `McpToolInfo`, `McpResourceInfo`, `ServerInfo`, `ServerCapabilities` | missing (different ServerInfo exists in discovery)                        | **FAIL**    | Critical                                        |
| §2.3 — `MCPClient` public API                                               | wrong API surface (legacy client copied)                                  | **FAIL**    | No `discover_and_register`                      |
| §2.4 — `MCPTransport` Protocol                                              | missing                                                                   | **FAIL**    |                                                 |
| §2.5 — Unified `ToolRegistry` + `ToolDef`                                   | missing                                                                   | **FAIL**    | Critical                                        |
| §3.1 — Tool name qualification semantics                                    | not implemented                                                           | **FAIL**    | No place to enforce                             |
| §3.2 — Server lifecycle (initialize handshake)                              | exists in legacy client                                                   | PASS        | inherited                                       |
| §3.3 — Error semantics (Mcp\* class hierarchy)                              | wrong hierarchy (legacy MCPError instead)                                 | **FAIL**    |                                                 |
| §3.4 — How #339 is fixed                                                    | NOT fixed (BaseAgent still imports legacy path)                           | **FAIL**    | Critical                                        |
| §4 — Backward compat shim                                                   | source files duplicated, no DeprecationWarning                            | **FAIL**    | Critical                                        |
| §5 — SSRF protection                                                        | inherited from legacy client                                              | PASS        | (assuming code copied correctly)                |
| §5 — API key handling                                                       | inherited                                                                 | PASS        |                                                 |
| §6 — Examples                                                               | not testable (no `kailash_mcp.MCPClient` matching spec)                   | **FAIL**    |                                                 |
| §7 — Interop test vectors                                                   | not implemented (no canonical types)                                      | **FAIL**    |                                                 |
| §8 — Implementation decisions                                               | mostly undocumented                                                       | PARTIAL     | TrustPlane Option B taken; middleware/oauth not |
| §9 — Migration order (23 steps)                                             | ~12 of 23 incomplete                                                      | **FAIL**    | 52% incomplete                                  |
| §10 — Test migration                                                        | new tests not written; old tests not migrated                             | **FAIL**    | Empty test dirs                                 |
| §12 — pyproject.toml                                                        | name+version match; deps + extras drift; build-backend differs            | **PARTIAL** |                                                 |
| §13 — Rust parallel                                                         | N/A (out of scope)                                                        | —           |                                                 |

### SPEC-02

| Spec Section                                                                                                                                                                            | Implementation File                                                                                                              | Status      | Notes                            |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ----------- | -------------------------------- |
| §1 — Monolith reduced (5,001 → ~12 files)                                                                                                                                               | `nodes/ai/ai_providers.py` is now 83 lines (shim)                                                                                | PASS        | Real shim ✓                      |
| §1 — Adapters/ migrated                                                                                                                                                                 | still exists in full at `kaizen_agents/delegate/adapters/`                                                                       | **FAIL**    |                                  |
| §1 — `streaming.py` created                                                                                                                                                             | not created                                                                                                                      | **FAIL**    |                                  |
| §1 — `cost.py` created (NEW from Rust)                                                                                                                                                  | created with wrong API                                                                                                           | PARTIAL     |                                  |
| §2.1 — Capability protocols (BaseProvider, LLMProvider, AsyncLLMProvider, StreamingProvider, EmbeddingProvider, ToolCallingProvider, StructuredOutputProvider, ProviderCapability enum) | missing — replaced with legacy ABCs                                                                                              | **FAIL**    | Critical                         |
| §2.2 — Wire types (Message, ContentBlock, ToolCall, ToolCallFunction, ChatResponse, TokenUsage, StreamEvent) as frozen dataclasses with Literal types                                   | wrong types (Message is dict alias; ContentBlock missing; not frozen; not Literal)                                               | **FAIL**    | Critical                         |
| §2.3 — CostTracker (microdollar precision, prefix pricing, budget)                                                                                                                      | wrong API (float, exact match, no budget)                                                                                        | **FAIL**    |                                  |
| §2.4 — Registry (`get_provider`, `get_provider_for_model`, `get_streaming_provider`, `get_embedding_provider`)                                                                          | only `get_provider` and `get_available_providers`                                                                                | **PARTIAL** | Critical missing functions       |
| §2.5 — OpenAI per-provider (chat + chat_async + stream_chat + embed + format_tools_for_provider + format_response_schema + reasoning model filtering)                                   | chat ✓, chat_async ✓, stream_chat ✗, embed ✓, format_tools_for_provider ✗, format_response_schema ✗, reasoning model filtering ✓ | PARTIAL     |                                  |
| §2.6 — Embedding-only Cohere                                                                                                                                                            | exists                                                                                                                           | PASS        | Not verified for purity          |
| §2.7 — Google #340 mutual-exclusion guard                                                                                                                                               | NOT implemented                                                                                                                  | **FAIL**    | Critical                         |
| §3.1 — Provider selection by model prefix                                                                                                                                               | not implemented (`get_provider_for_model` missing)                                                                               | **FAIL**    |                                  |
| §3.2 — BYOK multi-tenant per-request keys                                                                                                                                               | implemented in OpenAI provider via `BYOKClientCache`                                                                             | PASS        | Inherited                        |
| §3.3 — Reasoning model handling (o1/o3/o4)                                                                                                                                              | implemented in OpenAI provider                                                                                                   | PASS        | (regex-based)                    |
| §3.4 — Error sanitization                                                                                                                                                               | `sanitize_provider_error` called in providers                                                                                    | PASS        |                                  |
| §4 — Backward compat shim for `ai_providers`                                                                                                                                            | shim file exists                                                                                                                 | PASS        | But no DeprecationWarning (M2.1) |
| §4 — Backward compat shim for `delegate/adapters/__init__.py`                                                                                                                           | not implemented                                                                                                                  | **FAIL**    |                                  |
| §5 — Security (SSRF, error sanitization, no eval, no hardcoded models)                                                                                                                  | SSRF inherited; error sanitization PASS; hardcoded models in 6 of 9 providers                                                    | **FAIL**    | H2.4                             |
| §6 — Directory layout                                                                                                                                                                   | matches except `streaming.py` missing                                                                                            | PARTIAL     |                                  |
| §7 — Migration order                                                                                                                                                                    | most steps unstarted (no CostTracker port to spec API, no BaseAgent migration, no Delegate migration, no adapter delete)         | **FAIL**    |                                  |
| §8 — Migration order — same as §7                                                                                                                                                       | **FAIL**                                                                                                                         |             |
| §9 — Test migration                                                                                                                                                                     | none of the new test files exist                                                                                                 | **FAIL**    |                                  |

---

## Risk Register

| ID  | Risk                                                                                                                                                     | Likelihood | Impact   | Mitigation                                                                                                                                                                 |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | Two MCP code copies drift, fixes applied to one and not the other                                                                                        | High       | High     | Convert `src/kailash/mcp_server/__init__.py` into a true re-export shim, delete file bodies in `src/kailash/mcp_server/*.py` (replace with `from kailash_mcp... import *`) |
| R2  | #339 not actually fixed — same root cause still in BaseAgent path                                                                                        | Certain    | Critical | Implement `McpToolInfo` + `ToolRegistry`, refactor BaseAgent to import from `kailash_mcp`                                                                                  |
| R3  | #340 reproduced verbatim in new code                                                                                                                     | Certain    | High     | Add the mutual-exclusion guard to `GoogleGeminiProvider._build_config_params`                                                                                              |
| R4  | New providers package cannot interop with Rust because wire types are dicts                                                                              | High       | High     | Rewrite `providers/types.py` to use frozen dataclasses with `Literal` types as spec §2.2 mandates                                                                          |
| R5  | Cost tracking will silently drift over millions of calls (float precision)                                                                               | Medium     | Medium   | Convert CostTracker to integer microdollars per spec §2.3                                                                                                                  |
| R6  | Spec consumers (SPEC-03, SPEC-04, SPEC-05) blocked because `get_provider_for_model` and `get_streaming_provider` don't exist                             | Certain    | High     | Implement the missing dispatch functions                                                                                                                                   |
| R7  | Hardcoded model defaults in 6 providers will break when those models are deprecated (already happening with `claude-3-sonnet-20240229`)                  | High       | Medium   | Replace with `os.environ.get("DEFAULT_LLM_MODEL")` per env-models.md                                                                                                       |
| R8  | Zero new tests means no validation of any of the spec semantics                                                                                          | Certain    | High     | Write the §10 (SPEC-01) and §9 (SPEC-02) test files before any further migration                                                                                           |
| R9  | Undeleted `kaizen_agents/delegate/adapters/` and `kaizen_agents/delegate/mcp.py` mean two parallel implementations are now both in production code paths | Certain    | High     | Either delete now (forcing the migration) or land the proper deprecation shims                                                                                             |
| R10 | `kailash-mcp` depends on `kailash>=2.2.0`, inverting the dependency direction the extraction was supposed to enable                                      | High       | Medium   | Audit and remove the `kailash` dependency from the new package, or document why the inversion is acceptable                                                                |

---

## Recommended Implementation Roadmap

The current branch is approximately **30% of the way** to the specs. The remaining work breaks into three convergence sessions:

**Session 1 — Type & Protocol Foundation (blocks everything)**

- Write `protocol/jsonrpc.py` with the 3 dataclasses + `to_dict/from_dict`
- Write `protocol/types.py` with `McpToolInfo`, `McpResourceInfo`, `ServerInfo`, `ServerCapabilities`
- Rewrite `providers/types.py` with frozen dataclasses and Literal types
- Write `providers/base.py` with `ProviderCapability` enum and the 7 Protocol classes
- Write `tools/registry.py` with `ToolDef` + `ToolRegistry`
- Add the spec-shaped exports to both packages' `__init__.py`

**Session 2 — Consumer Migration & Bug Fixes**

- Implement `get_provider_for_model`, `get_streaming_provider`, `get_embedding_provider` in registry
- Add the Gemini #340 mutual-exclusion guard with logging
- Migrate BaseAgent to `from kailash_mcp import MCPClient` and call `discover_and_register`
- Replace 6 hardcoded model defaults with `os.environ.get("DEFAULT_LLM_MODEL")`
- Add `stream_chat()` to OpenAI/Anthropic/Google providers (porting from delegate/adapters)
- Add `format_tools_for_provider` and `format_response_schema` to each provider
- Convert `src/kailash/mcp_server/*.py` to true re-export shims
- Delete (or shim) `kaizen_agents/delegate/mcp.py` and `delegate/adapters/`
- Delete `src/kailash/api/mcp_integration.py` after final consumer audit
- Refactor `channels/mcp_channel.py`, `nodes/enterprise/mcp_executor.py`, `nodes/mixins/mcp.py` to import from `kailash_mcp`

**Session 3 — Tests & Validation**

- Write all §10 (SPEC-01) test files including the 5 interop vectors as parameterized tests
- Write all §9 (SPEC-02) test files including `test_capabilities.py`, `test_registry.py`, `test_cost.py`, and per-provider tests including the #340 vector
- Run full test suite, fix any drift the duplicate code introduced
- Cross-SDK alignment check against `crates/kailash-mcp/` (Rust)

---

## Success Criteria

For the next red team to certify SPEC-01 + SPEC-02 as PASS, the following must hold:

- [ ] `from kailash_mcp import JsonRpcRequest, JsonRpcResponse, JsonRpcError, McpToolInfo, McpResourceInfo, ServerInfo, ServerCapabilities, ToolRegistry, ToolDef, MCPClient, MCPTransport` succeeds
- [ ] `grep -r "class JsonRpcRequest" packages/kailash-mcp/src/` returns exactly one file
- [ ] `wc -l src/kailash/mcp_server/client.py` returns ≤ 20 lines (re-export shim)
- [ ] `from kailash.mcp_server import MCPClient` raises a `DeprecationWarning`
- [ ] `grep -r "from kailash_mcp" packages/kailash-kaizen/src/kaizen/core/base_agent.py` returns at least one match
- [ ] `from kaizen.providers import get_provider_for_model, get_streaming_provider, get_embedding_provider, BaseProvider, LLMProvider, AsyncLLMProvider, StreamingProvider, EmbeddingProvider, ToolCallingProvider, StructuredOutputProvider, ProviderCapability, Message, ContentBlock, ChatResponse, StreamEvent, TokenUsage, ToolCall, ToolCallFunction` succeeds
- [ ] `Message`, `ChatResponse`, `StreamEvent`, `TokenUsage`, `ToolCall`, `ToolCallFunction`, `ContentBlock` are all `@dataclass`es (verify with `dataclasses.is_dataclass`)
- [ ] `GoogleGeminiProvider`, when called with both `tools` and `response_format`, strips `response_format` and emits a warning (test reproducing #340)
- [ ] `CostTracker` uses integer microdollars internally; `check_budget()` returns `False` when `budget_limit_usd` is exceeded
- [ ] Zero hardcoded model defaults in `kaizen/providers/llm/*.py` (verify: `grep -E 'kwargs.get."model", "(gpt|claude|gemini|llama|o[134]|text-embedding)' kaizen/providers/llm/`)
- [ ] `packages/kailash-mcp/tests/unit/test_jsonrpc.py`, `test_tool_registry.py`, `test_mcp_client.py` exist and pass
- [ ] `packages/kailash-kaizen/tests/unit/providers/test_capabilities.py`, `test_registry.py`, `test_cost.py`, `test_google.py` (with #340 vector) exist and pass
- [ ] `pytest packages/kailash-mcp/tests/ packages/kailash-kaizen/tests/unit/providers/ -x` returns 0
- [ ] Full kailash-py test suite passes with no `kailash.mcp_server` imports outside the shim layer
