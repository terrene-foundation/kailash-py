# BYOK Hardening Requirements Breakdown

## Executive Summary

- **Feature**: BYOK (Bring Your Own Key) security hardening
- **Complexity**: High -- spans Core SDK serialization, 9 provider implementations, async runtime, and config pipeline
- **Risk Level**: Critical (D1) to Significant (D6)
- **Estimated Effort**: 8-12 days across 3 milestones

## 1. Requirements Matrix

### D1: API Key in Serializable node_config (CRITICAL)

API keys placed in `node_config` become part of `NodeInstance.config` (Pydantic BaseModel with `dict[str, Any]`).
`Workflow.to_dict()` (line 1211, graph.py) calls `node_data.model_dump()` which serializes all config fields including `api_key`.
`Workflow.to_json()`, `Workflow.to_yaml()`, and `Workflow.save()` all expose this.
Additionally, `Workflow.execute()` debug logging at line 1104 prints full config.

| Task ID | Description                                                                                                                                   | Files                                                                                       | Size | Dependencies | Parallel? |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ---- | ------------ | --------- |
| D1-T1   | Create `SecretStr` wrapper type that serializes to `"***REDACTED***"` in `model_dump()` / `to_dict()`                                         | `src/kailash/workflow/secret.py` (new)                                                      | S    | None         | Yes       |
| D1-T2   | Modify `NodeInstance` to detect and wrap known secret fields (`api_key`) before storage                                                       | `src/kailash/workflow/graph.py`                                                             | M    | D1-T1        | No        |
| D1-T3   | Add `_SENSITIVE_KEYS` constant and redaction filter in `Workflow.to_dict()`                                                                   | `src/kailash/workflow/graph.py`                                                             | S    | D1-T1        | No        |
| D1-T4   | Audit and sanitize all logging/debug `print()` statements that emit config dicts (lines 1104-1143 in graph.py, lines 842-843 in llm_agent.py) | `src/kailash/workflow/graph.py`, `packages/kailash-kaizen/src/kaizen/nodes/ai/llm_agent.py` | S    | None         | Yes       |
| D1-T5   | Write regression tests: serialize workflow with BYOK key, assert key not in output                                                            | `tests/`                                                                                    | M    | D1-T1..T3    | No        |

### D2: Provider Coverage Gap -- 4 Providers Ignore Per-Request kwargs (HIGH)

Confirmed by code inspection:

- **Google/Gemini** `chat()` (line 3670): reads `kwargs` for model/generation_config/tools only. No `api_key`/`base_url` handling. Uses `self._get_client()` which reads env vars.
- **Azure** `chat()` (line 2639): creates client from `self._get_endpoint()`/`self._get_credential()`. No per-request override.
- **Perplexity** `chat()` (line 4476): creates `self._sync_client` from `self._get_api_key()` (env var). No per-request override. Uses `kwargs.pop()` so unknown kwargs are silently consumed.
- **Docker** `chat()` (line 3059): creates `self._sync_client` from `self._get_base_url()`. No per-request override. BYOK is semantically inapplicable (local provider), but `base_url` override is reasonable.

| Task ID | Description                                                                                                                                        | Files                                          | Size | Dependencies | Parallel? |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | ---- | ------------ | --------- |
| D2-T1   | Add per-request `api_key`/`base_url` override to `GoogleGeminiProvider.chat()` -- create per-request client via `google.genai.Client(api_key=...)` | `ai_providers.py` (GeminiProvider section)     | M    | None         | Yes       |
| D2-T2   | Add per-request `api_key`/`base_url` override to `AzureProvider.chat()` -- create per-request `ChatCompletionsClient`                              | `ai_providers.py` (AzureProvider section)      | M    | None         | Yes       |
| D2-T3   | Add per-request `api_key` override to `PerplexityProvider.chat()` -- create per-request OpenAI client with Perplexity base_url                     | `ai_providers.py` (PerplexityProvider section) | S    | None         | Yes       |
| D2-T4   | Docker provider: add per-request `base_url` override (api_key not applicable)                                                                      | `ai_providers.py` (DockerProvider section)     | S    | None         | Yes       |
| D2-T5   | Write integration tests for BYOK on all 4 providers (mock client construction, verify per-request client is used)                                  | `tests/`                                       | M    | D2-T1..T4    | No        |

### D3: Async `chat_async()` Has No Per-Request Support (HIGH)

Confirmed by code inspection:

- **OpenAI** `chat_async()` (line 1138): creates `self._async_client = AsyncOpenAI()` with NO per-request overrides. The sync `chat()` handles it at line 856.
- **Azure** `chat_async()` (line 2743): creates `self._async_chat_client` from `self._get_endpoint()` -- no override.
- **Docker** `chat_async()` (line 3149): no override.
- **Google** `chat_async()` (line 3789): no override.
- **Perplexity** `chat_async()` (line 4516): creates async client from `self._get_api_key()` -- no override.
- **Anthropic**: sync `chat()` has per-request support, but `chat_async()` needs verification.

| Task ID | Description                                                                                                                  | Files                                    | Size | Dependencies | Parallel? |
| ------- | ---------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- | ---- | ------------ | --------- |
| D3-T1   | Add per-request `api_key`/`base_url` to `OpenAIProvider.chat_async()` -- mirror sync pattern                                 | `ai_providers.py` (OpenAIProvider)       | M    | None         | Yes       |
| D3-T2   | Add per-request override to `AzureProvider.chat_async()`                                                                     | `ai_providers.py` (AzureProvider)        | M    | D2-T2        | No        |
| D3-T3   | Add per-request override to `DockerProvider.chat_async()`                                                                    | `ai_providers.py` (DockerProvider)       | S    | D2-T4        | No        |
| D3-T4   | Add per-request override to `GoogleGeminiProvider.chat_async()`                                                              | `ai_providers.py` (GoogleGeminiProvider) | M    | D2-T1        | No        |
| D3-T5   | Add per-request override to `PerplexityProvider.chat_async()`                                                                | `ai_providers.py` (PerplexityProvider)   | S    | D2-T3        | No        |
| D3-T6   | Verify and fix `AnthropicProvider.chat_async()` per-request support                                                          | `ai_providers.py` (AnthropicProvider)    | S    | None         | Yes       |
| D3-T7   | Add `_provider_llm_response_async()` to `LLMAgentNode` or modify `async_run()` to thread BYOK credentials through async path | `llm_agent.py`                           | M    | D3-T1..T6    | No        |
| D3-T8   | Write async BYOK integration tests                                                                                           | `tests/`                                 | M    | D3-T7        | No        |

### D4: `auto_detect_provider` Drops `api_key`/`base_url` (HIGH)

Root cause at `providers.py` line 668: when `provider` is not in `config_functions` (e.g., `None` or unknown string), the else-branch calls `auto_detect_provider(preferred=provider)` which accepts ONLY `preferred: Optional[ProviderType]`. The `api_key`, `base_url`, and `model` kwargs are silently dropped.

Additionally, `auto_detect_provider()` at line 563 calls each `config_functions[preferred]()` with NO arguments -- even when the preferred provider is valid, overrides are lost.

| Task ID | Description                                                                                                                            | Files          | Size | Dependencies | Parallel? |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------- | -------------- | ---- | ------------ | --------- |
| D4-T1   | Extend `auto_detect_provider()` signature to accept `api_key`, `base_url`, `model` kwargs and thread them to provider config functions | `providers.py` | M    | None         | Yes       |
| D4-T2   | Update `get_provider_config()` else-branch to pass kwargs to `auto_detect_provider()`                                                  | `providers.py` | S    | D4-T1        | No        |
| D4-T3   | Write regression test: `get_provider_config(api_key="sk-test")` with no explicit provider, verify key reaches ProviderConfig           | `tests/`       | S    | D4-T2        | No        |

### D5: `str(e)` Leaks Error Details to Caller (HIGH)

Provider errors passed via `str(e)` at `llm_agent.py` line 2199 (`raise RuntimeError(f"Provider {provider} error: {str(e)}")`) and line 1049 (`"error": str(e)`) can contain:

- Auth error messages with partial API key prefixes
- Base URLs that reveal internal infrastructure
- Provider-internal error codes

In multi-tenant BYOK, Tenant A's error should not leak Tenant B's credentials or infrastructure details.

| Task ID | Description                                                                                                                                                     | Files                                                                  | Size | Dependencies | Parallel? |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | ---- | ------------ | --------- |
| D5-T1   | Create error sanitization utility: `sanitize_provider_error(e: Exception) -> str` that strips API key fragments, base URLs, and auth tokens from error messages | `packages/kailash-kaizen/src/kaizen/nodes/ai/error_sanitizer.py` (new) | M    | None         | Yes       |
| D5-T2   | Apply sanitizer to `_provider_llm_response()` error re-raise (line 2199)                                                                                        | `llm_agent.py`                                                         | S    | D5-T1        | No        |
| D5-T3   | Apply sanitizer to `process()` error return (line 1049)                                                                                                         | `llm_agent.py`                                                         | S    | D5-T1        | No        |
| D5-T4   | Audit all `str(e)` patterns in `llm_agent.py` (11 occurrences found) and apply sanitizer where error surfaces to caller                                         | `llm_agent.py`                                                         | M    | D5-T1        | No        |
| D5-T5   | Write tests: simulate provider error with embedded API key, verify sanitized output                                                                             | `tests/`                                                               | S    | D5-T4        | No        |

### D6: Per-Request Client Caching (SIGNIFICANT)

Each BYOK call creates a new `openai.OpenAI(api_key=...)` or `anthropic.Anthropic(api_key=...)` client. Each client performs TLS handshake, connection pooling setup, etc. At scale (100+ concurrent BYOK tenants), this causes:

- TLS handshake overhead (~50-100ms per new client)
- Connection pool exhaustion
- Memory growth from uncollected client objects

| Task ID | Description                                                                                      | Files                                                               | Size | Dependencies                | Parallel? |
| ------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------- | ---- | --------------------------- | --------- |
| D6-T1   | Create `BYOKClientCache` with bounded LRU eviction keyed on `(provider, api_key_hash, base_url)` | `packages/kailash-kaizen/src/kaizen/nodes/ai/client_cache.py` (new) | M    | None                        | Yes       |
| D6-T2   | Integrate cache into `OpenAIProvider.chat()` and `chat_async()` per-request path                 | `ai_providers.py` (OpenAIProvider)                                  | M    | D6-T1                       | No        |
| D6-T3   | Integrate cache into `AnthropicProvider.chat()` per-request path                                 | `ai_providers.py` (AnthropicProvider)                               | S    | D6-T1                       | No        |
| D6-T4   | Integrate cache into remaining providers (Google, Azure, Perplexity) after D2/D3                 | `ai_providers.py`                                                   | M    | D6-T1, D2-T1..T3, D3-T1..T6 | No        |
| D6-T5   | Write cache eviction and thread-safety tests                                                     | `tests/`                                                            | M    | D6-T1                       | No        |

---

## 2. Priority Ranking

Ranking by `(risk x likelihood x ease_of_fix)` -- goal is maximum risk reduction per unit effort.

| Priority | Item                        | Risk        | Likelihood                                   | Ease               | Rationale                                                                                                                           |
| -------- | --------------------------- | ----------- | -------------------------------------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| **1**    | D1 (Serialization leak)     | CRITICAL    | High -- any workflow export/log exposes keys | Easy -- 2-3 days   | Most severe security defect. Plaintext API keys in serialized workflows is a data breach vector. Straightforward redaction pattern. |
| **2**    | D5 (Error message leaks)    | HIGH        | High -- every provider error can leak        | Easy -- 1-2 days   | Multi-tenant info leakage. Small, self-contained fix.                                                                               |
| **3**    | D4 (auto_detect drops keys) | HIGH        | High -- common BYOK usage pattern            | Easy -- 1 day      | Silent credential loss means BYOK silently fails, falling back to env var (wrong tenant).                                           |
| **4**    | D2 (Provider coverage gap)  | HIGH        | Medium -- only affects 4 specific providers  | Medium -- 2-3 days | BYOK users on Google/Azure/Perplexity get silent credential fallback. Each provider is independent work.                            |
| **5**    | D3 (Async gap)              | HIGH        | Medium -- only affects `use_async_llm=True`  | Medium -- 3-4 days | Requires D2 for full coverage. Async users in FastAPI deployments lose BYOK silently.                                               |
| **6**    | D6 (Client caching)         | SIGNIFICANT | Low -- only at scale (100+ tenants)          | Medium -- 2-3 days | Performance, not correctness. Only matters at production scale.                                                                     |

---

## 3. Milestone Plan

### M1: Critical Security (must ship before any BYOK production use)

**Duration**: 3-4 days
**Gate**: No API key appears in any serialized output or error message.

| Task      | Item                                              | Est      |
| --------- | ------------------------------------------------- | -------- |
| D1-T1..T5 | SecretStr, redaction, logging audit, tests        | 2-3 days |
| D5-T1..T5 | Error sanitizer, apply across llm_agent.py, tests | 1-2 days |
| D4-T1..T3 | auto_detect_provider kwarg threading, tests       | 1 day    |

**Deliverables**:

- `SecretStr` wrapper type in Core SDK
- `NodeInstance` redacts `api_key` on serialization
- Error sanitizer strips credentials from all error surfaces
- `auto_detect_provider` threads BYOK kwargs correctly
- Regression test suite for all three

**Parallelism**: D1-T1 and D1-T4 run in parallel. D5-T1 runs in parallel with D1. D4 runs in parallel with D5.

### M2: Provider Parity (needed for multi-provider BYOK customers)

**Duration**: 4-5 days
**Gate**: Every provider's sync and async `chat()` honors per-request `api_key`/`base_url`.

| Task      | Item                                                                 | Est      |
| --------- | -------------------------------------------------------------------- | -------- |
| D2-T1..T5 | 4 provider sync BYOK support + tests                                 | 2-3 days |
| D3-T1..T8 | 6 provider async BYOK support + LLMAgentNode async threading + tests | 3-4 days |

**Deliverables**:

- All 9 providers (OpenAI, Anthropic, Google, Azure, Perplexity, Docker, Ollama, Cohere, HuggingFace) support per-request credentials in sync `chat()`
- All providers with `chat_async()` support per-request credentials
- `LLMAgentNode` async execution path threads credentials correctly

**Parallelism**: D2-T1 through D2-T4 all run in parallel. D3 tasks depend on corresponding D2 tasks for pattern alignment.

### M3: Performance Optimization (needed at scale)

**Duration**: 2-3 days
**Gate**: BYOK calls with repeated keys reuse cached clients. Cache bounded at configurable max.

| Task      | Item                                              | Est      |
| --------- | ------------------------------------------------- | -------- |
| D6-T1..T5 | Client cache, integration across providers, tests | 2-3 days |

**Deliverables**:

- `BYOKClientCache` with LRU eviction, keyed on hashed credentials
- Integration with all providers that create per-request clients
- Thread-safety tests and eviction verification

**Parallelism**: Fully independent from M1 and M2, but should ship after M2 since it integrates with the per-request client creation patterns added in M2.

---

## 4. Dependency Graph

```
D1-T1 ────> D1-T2 ────> D1-T5
  |           |
  +─────────> D1-T3
D1-T4 (parallel with all D1)

D5-T1 ────> D5-T2
  |         D5-T3  (parallel with D5-T2)
  +───────> D5-T4 ────> D5-T5

D4-T1 ────> D4-T2 ────> D4-T3

D2-T1 ─┐
D2-T2 ─┼─> D2-T5
D2-T3 ─┤
D2-T4 ─┘

D2-T1 ────> D3-T4
D2-T2 ────> D3-T2
D2-T3 ────> D3-T5
D2-T4 ────> D3-T3
D3-T1 (independent)
D3-T6 (independent)
D3-T1..T6 ─> D3-T7 ────> D3-T8

D6-T1 ────> D6-T2
  |         D6-T3  (parallel with D6-T2)
  +───────> D6-T4 (after D2 + D3)
D6-T1 ────> D6-T5
```

---

## 5. File Impact Summary

| File                                                                   | Tasks                           | Change Type                                                          |
| ---------------------------------------------------------------------- | ------------------------------- | -------------------------------------------------------------------- |
| `src/kailash/workflow/secret.py` (new)                                 | D1-T1                           | New file -- SecretStr wrapper                                        |
| `src/kailash/workflow/graph.py`                                        | D1-T2, D1-T3, D1-T4             | Modify NodeInstance, to_dict(), remove debug prints                  |
| `packages/kailash-kaizen/src/kaizen/nodes/ai/llm_agent.py`             | D1-T4, D3-T7, D5-T2..T4         | Sanitize logging, add async BYOK threading, sanitize errors          |
| `packages/kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py`          | D2-T1..T4, D3-T1..T6, D6-T2..T4 | Per-request overrides in 4 sync + 6 async methods, cache integration |
| `packages/kailash-kaizen/src/kaizen/config/providers.py`               | D4-T1, D4-T2                    | Thread kwargs through auto_detect_provider                           |
| `packages/kailash-kaizen/src/kaizen/nodes/ai/error_sanitizer.py` (new) | D5-T1                           | New file -- error sanitization utility                               |
| `packages/kailash-kaizen/src/kaizen/nodes/ai/client_cache.py` (new)    | D6-T1                           | New file -- bounded LRU client cache                                 |
| Various test files (new)                                               | All T\*-T5/T8 tasks             | New test files for each deferred item                                |
