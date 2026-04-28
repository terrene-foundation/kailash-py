# BYOK Deferred Items -- Deep Analysis

## Executive Summary

Six deferred items from the BYOK red team R1 represent a gradient from critical security
vulnerability (D1: plaintext API keys in serializable config) to performance optimization
(D6: client caching). The most urgent item is D1, which creates a credential exposure surface
across 7+ serialization paths. D2 and D3 are functionally equivalent problems -- silent
credential dropout -- across different dimensions (provider coverage and sync/async parity).
D5 is a multi-tenant isolation breach waiting to happen.

**Complexity Score: 23 (Complex)** -- Governance: 5, Legal: 3, Strategic: 8, Technical: 7.

---

## D1: API Key in Serializable node_config (CRITICAL)

### Current State

API keys are injected as plaintext strings into `node_config` dicts, which flow into
`NodeInstance.config` (a Pydantic `BaseModel` with `config: dict[str, Any]`). This config
dict participates in every serialization pathway the SDK offers.

**Key injection points** (2 locations in `workflow_generator.py`):

- Line 231: `node_config["api_key"] = api_key` (in `generate_workflow()`)
- Line 340: `node_config["api_key"] = self.config.api_key` (in `generate_fallback_workflow()`)

The `LLMAgentNode` declares `api_key` as a `NodeParameter` (line 380-384 of `llm_agent.py`),
meaning it is a first-class config field stored in the node's config dict.

### Blast Radius -- 7 Confirmed Serialization Paths

Each path that calls `model_dump()`, `to_dict()`, `to_json()`, `to_yaml()`, or `save()` on
the workflow will emit the plaintext API key.

| #   | Path                                                  | File             | Line(s)                         | Severity                                          |
| --- | ----------------------------------------------------- | ---------------- | ------------------------------- | ------------------------------------------------- |
| 1   | `Workflow.to_dict()`                                  | `graph.py`       | 1220 (`node_data.model_dump()`) | CRITICAL -- returns full config including api_key |
| 2   | `Workflow.to_json()`                                  | `graph.py`       | 1243 (calls `to_dict()`)        | CRITICAL -- JSON string with key                  |
| 3   | `Workflow.to_yaml()`                                  | `graph.py`       | 1251 (calls `to_dict()`)        | CRITICAL -- YAML string with key                  |
| 4   | `Workflow.save()`                                     | `graph.py`       | 1264-1268 (writes to file)      | CRITICAL -- key written to disk                   |
| 5   | `Workflow.export_to_kailash()`                        | `graph.py`       | 1201 + `export.py:936`          | CRITICAL -- `deepcopy(node_instance.config)`      |
| 6   | `DistributedRuntime._serialize_workflow()`            | `distributed.py` | 570 (calls `to_dict()`)         | CRITICAL -- key sent to Redis queue               |
| 7   | `_safe_serialize(inputs)` in LocalRuntime audit trail | `local.py`       | 2352                            | HIGH -- inputs contain config with key            |
| 8   | Connection error message logging                      | `graph.py`       | 457 (`c.model_dump()`)          | MEDIUM -- connection dicts, not node config       |

**Path 5 is especially dangerous**: The export utility does `deepcopy(node_instance.config)` at
line 936, meaning the api_key survives into exported workflow files that may be shared,
committed to version control, or sent to external systems.

**Path 6 is production-critical**: The distributed runtime serializes the entire workflow to
Redis. Any worker process that reads the queue has access to the tenant's API key.

### Risk

- **Likelihood**: Certain. Any user who serializes a BYOK workflow leaks their key.
- **Impact**: Critical. Credential exposure in logs, files, message queues, and audit trails.
- **Multi-tenant impact**: Tenant A's key visible to Tenant B if workflows are logged or shared.

### Fix Approaches -- Evaluated

#### Option A: Pydantic `SecretStr` Wrapper

Wrap `api_key` in `SecretStr` so `model_dump()` returns `"**********"` by default.

**Pros**:

- Minimal code change (change `NodeParameter` type, add `SecretStr` import)
- Pydantic handles redaction automatically in `model_dump()`, `__repr__()`, `__str__()`
- Convention understood by the Python ecosystem

**Cons**:

- Requires extracting with `.get_secret_value()` at every consumption point
- `LLMAgentNode.process()` reads `self.config.get("api_key")` -- would get `SecretStr` object, not string
- Every provider's `chat(**kwargs)` would receive `SecretStr` instead of `str`
- `NodeInstance.config` is `dict[str, Any]`, not typed -- `SecretStr` in a plain dict lacks type safety
- Breaks `Workflow.from_dict()` deserialization (can't reconstruct `SecretStr` from plain JSON)

**Verdict**: Moderate disruption. Requires changes at 5+ consumption points.

#### Option B: Runtime Credential Store (Sidecar Pattern)

Store API keys in a separate, non-serializable registry (`CredentialStore`). `node_config`
stores only a credential reference (e.g., `_credential_ref: "byok_1234"`). At execution time,
the runtime resolves the reference to the actual key.

**Pros**:

- Complete separation of credentials from serializable state
- Keys never enter `node_config` at all
- Works cleanly with all serialization paths (reference is safe to serialize)
- Natural fit for multi-tenant: store is per-request, not per-workflow

**Cons**:

- New abstraction (`CredentialStore`) to introduce, test, and document
- Requires changes to `WorkflowGenerator`, `LLMAgentNode`, and `_provider_llm_response()`
- Distributed runtime would need to transport credentials out-of-band
- Larger architectural change

**Verdict**: Cleanest design, but highest implementation cost.

#### Option C: Redaction in Serialization Hooks

Override `NodeInstance.model_dump()` / add a custom serializer that strips sensitive fields
(`api_key`, `base_url`) from the output. Keep the plaintext in memory, redact on serialization.

**Pros**:

- Least disruptive to consumption points (key stays as `str` in memory)
- Single redaction point protects all 7+ serialization paths
- `LLMAgentNode.process()` code unchanged
- Provider `chat(**kwargs)` receives plain string (no wrapping)

**Cons**:

- "Security by convention" -- any new serialization path must remember to use the redaction
- Does not protect against `repr()` or debugger inspection
- The key is still in the dict in memory (vulnerable to memory dumps)
- Requires maintaining a list of sensitive field names

**Verdict**: Lowest disruption, good-enough security for BYOK use case.

### Recommendation

**Option C (redaction hooks) for immediate fix, with Option B as long-term target.**

Rationale: Option C can be implemented in a single session with zero changes to the provider
layer, the LLMAgentNode execution path, or the WorkflowGenerator. It protects all 7
serialization paths by adding a `SENSITIVE_CONFIG_KEYS` set and a `_redact_config()` classmethod
to `NodeInstance`.

Implementation plan:

1. Add `SENSITIVE_CONFIG_KEYS = {"api_key", "base_url"}` to `NodeInstance`
2. Override `model_dump()` to redact sensitive keys (replace with `"***REDACTED***"`)
3. Add `config_with_secrets()` method for runtime access (returns unredacted dict)
4. Update `Workflow.to_dict()` to use the redacted version
5. Add test: serialize a BYOK workflow, assert api_key is redacted

**Estimated Complexity: M (Medium)**
**Dependencies: None -- self-contained in graph.py**

---

## D2: Provider Coverage Gap -- 4 Providers Ignore Per-Request kwargs (HIGH)

### Current State

Only OpenAI and Anthropic providers handle `api_key`/`base_url` kwargs in their `chat()`
methods. Four providers silently ignore these kwargs:

| Provider                      | Client Creation Pattern                                      | Ignores api_key?             | Ignores base_url?                        | Fix Difficulty |
| ----------------------------- | ------------------------------------------------------------ | ---------------------------- | ---------------------------------------- | -------------- |
| **GoogleGeminiProvider**      | `genai.Client(api_key=...)` via `_get_client()`              | Yes -- uses env var only     | N/A (uses project/API key, not base_url) | M              |
| **AzureAIFoundryProvider**    | `ChatCompletionsClient(endpoint=..., credential=...)`        | Yes -- uses env var only     | Yes -- uses env var only                 | M              |
| **PerplexityProvider**        | `openai.OpenAI(api_key=..., base_url=...)` via shared client | Yes -- uses `_get_api_key()` | Yes -- hardcoded `BASE_URL`              | S              |
| **DockerModelRunnerProvider** | `openai.OpenAI(api_key="docker-model-runner", base_url=...)` | N/A (no API key)             | Yes -- uses `_get_base_url()`            | S              |

### Detailed Analysis Per Provider

**GoogleGeminiProvider** (line 3648-3787):

- `_get_client()` creates a `genai.Client` using env vars only (line 3413-3426)
- No per-request client creation path exists
- Google GenAI SDK's `Client` constructor accepts `api_key` parameter -- so the fix is to
  create a per-request client when kwargs contain `api_key`
- Google does NOT have a `base_url` concept for the standard API (Vertex AI uses project/location)
- Fix pattern: mirror the OpenAI approach (create transient `genai.Client(api_key=per_request_key)`)

**AzureAIFoundryProvider** (line 2639-2741):

- Uses `ChatCompletionsClient(endpoint=..., credential=...)` from `azure.ai.inference`
- Credential comes from `_get_credential()` which uses env vars or DefaultAzureCredential
- Azure uses `AzureKeyCredential(api_key)` -- per-request override requires creating a
  new `ChatCompletionsClient` with a new credential object
- `base_url` maps to `endpoint` in Azure's SDK

**PerplexityProvider** (line 4440-4514):

- Uses `openai.OpenAI(api_key=..., base_url=BASE_URL)` -- standard OpenAI-compatible client
- Fix is nearly identical to the existing OpenAI pattern:
  check for `kwargs.get("api_key")`, create transient `openai.OpenAI(api_key=..., base_url=BASE_URL)`
- Simplest fix of the four

**DockerModelRunnerProvider** (line 3059-3147):

- Uses `openai.OpenAI(api_key="docker-model-runner", base_url=...)` -- dummy API key
- Docker Model Runner is local -- BYOK is not a meaningful concept
- `base_url` override could be useful for custom Docker endpoints
- Lowest priority -- BYOK customers do not use Docker Model Runner

### Priority Ranking (by customer demand)

1. **Perplexity** -- HIGH. BYOK customers use Perplexity for search-augmented agents.
   Fix is trivial (copy OpenAI pattern).
2. **Google Gemini** -- HIGH. Second most popular cloud provider after OpenAI.
   Fix is moderate (different SDK constructor).
3. **Azure AI Foundry** -- MEDIUM. Enterprise customers with Azure deployments.
   Fix is moderate (credential object construction).
4. **Docker Model Runner** -- LOW. Local development only, no BYOK use case.
   base_url override may be useful but not urgent.

### Recommendation

Fix Perplexity and Google Gemini first (S+M effort, covers 90% of BYOK demand).
Azure in the same batch if time permits. Docker is deferrable.

**Estimated Complexity: S (Small) for Perplexity, M (Medium) for Google/Azure, S for Docker**
**Dependencies: None -- each provider is independent**

---

## D3: Async chat_async() Has No Per-Request Support (HIGH)

### Current State

The `chat_async()` methods exist on 5 providers but none support per-request `api_key`/`base_url`:

| Provider       | Has chat_async? | Has BYOK in sync chat()? | Gap                                 |
| -------------- | --------------- | ------------------------ | ----------------------------------- |
| **OpenAI**     | Yes (line 1138) | Yes (line 855-866)       | Async path ignores api_key/base_url |
| **Anthropic**  | No              | Yes (line 1529-1539)     | No async method at all              |
| **Azure**      | Yes (line 2743) | No                       | Double gap: no BYOK in either path  |
| **Docker**     | Yes (line 3149) | No                       | Double gap (low priority)           |
| **Google**     | Yes (line 3789) | No                       | Double gap                          |
| **Perplexity** | Yes (line 4516) | No                       | Double gap                          |

### How async is used

The async path is triggered by two entry points:

1. **`BaseAgent.run_async()`** (base_agent.py:915) -- requires `use_async_llm=True` in config.
   Calls `provider.chat_async()` at line 1150. This path does NOT pass `api_key`/`base_url`
   kwargs at all (line 1150-1158). The BYOK kwargs are simply absent.

2. **`KaizenLocalRuntime`** (kaizen_local.py:840) -- calls `provider.chat_async()` directly.
   This path also does not thread per-request credentials.

### Can the fix be mechanical?

Yes. The sync BYOK pattern for OpenAI (lines 855-866) is:

```python
per_request_api_key = kwargs.get("api_key")
per_request_base_url = kwargs.get("base_url")
if per_request_api_key or per_request_base_url:
    client_kwargs = {}
    if per_request_api_key:
        client_kwargs["api_key"] = per_request_api_key
    if per_request_base_url:
        client_kwargs["base_url"] = per_request_base_url
    client = openai.OpenAI(**client_kwargs)  # Transient client
else:
    if self._sync_client is None:
        self._sync_client = openai.OpenAI()
    client = self._sync_client
```

The async equivalent is identical, substituting `AsyncOpenAI` for `OpenAI` and
`self._async_client` for `self._sync_client`. This is a mechanical copy.

**For OpenAI** (lines 1138-1344): Add the same 8-line block at the top of `chat_async()`,
replacing `openai.OpenAI` with `openai.AsyncOpenAI`.

**For Anthropic**: First implement `chat_async()` (it doesn't exist), then include BYOK.
Uses `anthropic.AsyncAnthropic(**client_kwargs)`.

**For all other providers**: Apply D2 fixes first (add BYOK to sync), then mechanically
copy to async.

### Callers that need updating

The `BaseAgent.run_async()` path (base_agent.py:1150) currently calls:

```python
response = await provider.chat_async(
    messages=messages,
    model=self.config.model or ...,
    generation_config={...},
)
```

This call does NOT pass `api_key` or `base_url`. It needs:

```python
chat_kwargs = {
    "messages": messages,
    "model": self.config.model or ...,
    "generation_config": {...},
}
if self.config.api_key:
    chat_kwargs["api_key"] = self.config.api_key
if self.config.base_url:
    chat_kwargs["base_url"] = self.config.base_url
response = await provider.chat_async(**chat_kwargs)
```

### Recommendation

Fix in the same batch as D2. For each provider, apply BYOK to both `chat()` and `chat_async()`
simultaneously. Also fix `BaseAgent.run_async()` to thread credentials.

**Estimated Complexity: M (Medium) -- mechanical, but touches 6 providers + 2 callers**
**Dependencies: D2 (sync fixes) should land first or simultaneously**

---

## D4: auto_detect_provider Drops api_key/base_url (HIGH)

### Current State

`get_provider_config()` (providers.py:607-668) correctly accepts `api_key` and `base_url`
parameters and passes them through to provider-specific config functions when a provider
is explicitly specified (line 664: `valid_kwargs` filtering via `inspect.signature()`).

However, when `provider` is `None` or not in `config_functions`, it falls through to:

```python
return auto_detect_provider(preferred=provider)
```

The `auto_detect_provider()` function (line 518-604) does NOT accept `api_key` or `base_url`
parameters. It creates configs using only environment variables. The explicit BYOK
parameters are silently dropped.

### Impact

A user who calls:

```python
config = get_provider_config(api_key="sk-tenant-key")  # No provider specified
```

expects auto-detection to use their key. Instead, `auto_detect_provider()` reads `OPENAI_API_KEY`
from the environment, ignoring the tenant's key entirely. The tenant's request runs on the
platform's API key, which is:

1. A billing attribution error (tenant is not charged)
2. A security violation (tenant traffic uses shared credentials)
3. Completely silent (no error, no warning)

### Recommendation

Pass `api_key` and `base_url` through to `auto_detect_provider()`. The function should try
each provider with the provided credentials first.

**Estimated Complexity: S (Small)**
**Dependencies: None**

---

## D5: str(e) Error Leakage (HIGH)

### Current State

Every provider wraps exceptions with `raise RuntimeError(f"... error: {str(e)}")`. The `str(e)`
representation of SDK exceptions often contains:

- API keys (e.g., OpenAI errors include the request headers)
- Base URLs with embedded credentials
- Internal endpoint paths
- Rate limit details revealing org structure

### Catalog of Leakage Points

| Location                                | Line      | Pattern                                                  | Risk                                                    |
| --------------------------------------- | --------- | -------------------------------------------------------- | ------------------------------------------------------- |
| OllamaProvider.chat()                   | 562       | `f"Ollama error: {str(e)}"`                              | LOW (local)                                             |
| OllamaProvider.embed()                  | 619       | `f"Ollama embedding error: {str(e)}"`                    | LOW                                                     |
| OpenAIProvider.chat()                   | 1134      | `f"OpenAI API error: {str(e)}"`                          | HIGH -- OpenAI BadRequestError includes request details |
| OpenAIProvider.chat()                   | 1136      | `f"OpenAI error: {str(e)}"`                              | HIGH -- generic catch-all                               |
| OpenAIProvider.chat_async()             | 1342      | `f"OpenAI API error: {str(e)}"`                          | HIGH                                                    |
| OpenAIProvider.chat_async()             | 1344      | `f"OpenAI error: {str(e)}"`                              | HIGH                                                    |
| OpenAIProvider.embed()                  | 1388      | `f"OpenAI embedding error: {str(e)}"`                    | HIGH                                                    |
| OpenAIProvider.embed_async()            | 1443      | `f"OpenAI embedding error: {str(e)}"`                    | HIGH                                                    |
| AnthropicProvider.chat()                | 1657      | `f"Anthropic error: {str(e)}"`                           | HIGH                                                    |
| CohereProvider.embed()                  | 1721      | `f"Cohere embedding error: {str(e)}"`                    | MEDIUM                                                  |
| HuggingFaceProvider.chat()              | 1911+1927 | `f"HuggingFace API error: {str(e)}"`                     | MEDIUM                                                  |
| HuggingFaceProvider.embed()             | 1987      | `f"HuggingFace local error: {str(e)}"`                   | LOW                                                     |
| AzureAIFoundryProvider.chat()           | 2741      | `f"Azure AI Foundry error: {str(e)}"`                    | HIGH                                                    |
| AzureAIFoundryProvider.chat_async()     | 2838      | `f"Azure AI Foundry async error: {str(e)}"`              | HIGH                                                    |
| AzureAIFoundryProvider.embed()          | 2868      | `f"Azure AI Foundry embedding error: {str(e)}"`          | MEDIUM                                                  |
| AzureAIFoundryProvider.embed_async()    | 2896      | `f"Azure AI Foundry async embedding error: {str(e)}"`    | MEDIUM                                                  |
| DockerModelRunnerProvider.chat()        | 3147      | `f"Docker Model Runner error: {str(e)}"`                 | LOW                                                     |
| DockerModelRunnerProvider.chat_async()  | 3234      | `f"Docker Model Runner async error: {str(e)}"`           | LOW                                                     |
| DockerModelRunnerProvider.embed()       | 3261      | `f"Docker Model Runner embedding error: {str(e)}"`       | LOW                                                     |
| DockerModelRunnerProvider.embed_async() | 3288      | `f"Docker Model Runner async embedding error: {str(e)}"` | LOW                                                     |
| GoogleGeminiProvider.chat()             | 3787      | `f"Google Gemini error: {str(e)}"`                       | HIGH                                                    |
| GoogleGeminiProvider.chat_async()       | 3916      | `f"Google Gemini async error: {str(e)}"`                 | HIGH                                                    |
| GoogleGeminiProvider.embed()            | 3970      | `f"Google Gemini embedding error: {str(e)}"`             | MEDIUM                                                  |
| GoogleGeminiProvider.embed_async()      | 4019      | `f"Google Gemini async embedding error: {str(e)}"`       | MEDIUM                                                  |
| PerplexityProvider.chat()               | 4508-4514 | `f"Perplexity error: {error_msg}"`                       | HIGH                                                    |
| PerplexityProvider.chat_async()         | 4564-4570 | `f"Perplexity error: {error_msg}"`                       | HIGH                                                    |
| LLMAgentNode.\_provider_llm_response()  | 2199      | `f"Provider {provider} error: {str(e)}"`                 | HIGH -- re-wraps with provider name                     |

**Total: 27 leakage points across 10 providers + 1 orchestrator.**

The Perplexity provider already does partial sanitization (lines 4508-4513):

```python
error_msg = str(e)
if "api_key" in error_msg.lower():
    raise RuntimeError("Perplexity API key invalid or not set. ...")
```

This is a good start but insufficient -- it only catches the word "api_key", not actual key values.

### Proposed Sanitization Pattern

Create a `sanitize_provider_error(e: Exception, provider_name: str) -> str` utility:

```python
import re

_SENSITIVE_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),           # OpenAI keys
    re.compile(r'key-[a-zA-Z0-9]{20,}'),           # Anthropic keys
    re.compile(r'pplx-[a-zA-Z0-9]{20,}'),          # Perplexity keys
    re.compile(r'AIza[a-zA-Z0-9_-]{35}'),           # Google API keys
    re.compile(r'Bearer\s+[a-zA-Z0-9._-]+'),       # Bearer tokens
    re.compile(r'api[_-]?key["\s:=]+["\']?[^"\'>\s]+', re.IGNORECASE),
    re.compile(r'https?://[^@\s]*:[^@\s]*@'),      # URLs with credentials
]

def sanitize_provider_error(e: Exception, provider_name: str) -> str:
    msg = str(e)
    for pattern in _SENSITIVE_PATTERNS:
        msg = pattern.sub("[REDACTED]", msg)
    return f"{provider_name} error: {msg}"
```

### Recommendation

1. Create `kaizen/nodes/ai/_error_sanitizer.py` with the sanitization utility
2. Replace all 27 `str(e)` patterns with `sanitize_provider_error(e, "ProviderName")`
3. Add test: construct an exception containing an API key, verify it is redacted

**Estimated Complexity: S (Small) -- mechanical replacement + 1 new utility module**
**Dependencies: None**

---

## D6: Client Caching (SIGNIFICANT)

### Current State

When a per-request API key is provided, the OpenAI provider creates a new `openai.OpenAI()`
client for every `chat()` call (line 866):

```python
client = openai.OpenAI(**client_kwargs)
```

Each `openai.OpenAI()` instantiation:

- Creates a new `httpx.Client` (connection pool)
- Performs TLS handshake on first request
- Allocates connection pool resources (default: 100 connections, 20 keepalive)
- These resources are NOT reused between calls

For BYOK scenarios at scale (e.g., 100 tenants, 10 requests/second each), this means:

- 1000 new clients/second
- 1000 TLS handshakes/second
- Unbounded client accumulation (no cleanup)

The same issue applies to Anthropic (line 1539: `anthropic.Anthropic(**client_kwargs)`)
and will apply to all providers once D2 is fixed.

### OpenAI SDK Client Lifecycle

The `openai.OpenAI` client:

- Uses `httpx.Client` internally for HTTP/2 connection pooling
- Is thread-safe for concurrent use
- Supports connection reuse across requests with the same base_url
- Has a `close()` method for resource cleanup
- Creating a new client is ~1-2ms (mostly httpx pool initialization)
- TLS handshake on first request adds ~50-100ms to the first call

Creating a new client per-request is expensive primarily due to the TLS handshake cost
and connection pool waste. For high-throughput BYOK, this becomes a bottleneck.

### Proposed LRU Cache Design

```python
import hashlib
import threading
import time
from collections import OrderedDict

class _ProviderClientCache:
    """Bounded LRU cache for per-request provider clients.

    Keys are hashed (api_key, base_url) tuples. Values are (client, last_used) tuples.
    Eviction: LRU when capacity reached. TTL-based cleanup on access.
    """

    def __init__(self, max_size: int = 128, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, tuple] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def _make_key(self, api_key: str, base_url: str = None) -> str:
        """Hash credentials to avoid storing plaintext keys as dict keys."""
        raw = f"{api_key}:{base_url or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get_or_create(self, api_key: str, base_url: str = None,
                      factory=None) -> Any:
        """Get cached client or create new one."""
        key = self._make_key(api_key, base_url)
        now = time.monotonic()

        with self._lock:
            # Check cache
            if key in self._cache:
                client, _ = self._cache[key]
                self._cache[key] = (client, now)  # Update last_used
                self._cache.move_to_end(key)       # LRU: move to end
                return client

            # Evict expired entries
            expired = [k for k, (_, t) in self._cache.items()
                       if now - t > self._ttl]
            for k in expired:
                old_client, _ = self._cache.pop(k)
                if hasattr(old_client, 'close'):
                    try:
                        old_client.close()
                    except Exception:
                        pass

            # Evict LRU if at capacity
            while len(self._cache) >= self._max_size:
                _, (old_client, _) = self._cache.popitem(last=False)
                if hasattr(old_client, 'close'):
                    try:
                        old_client.close()
                    except Exception:
                        pass

            # Create new client
            client = factory()
            self._cache[key] = (client, now)
            return client
```

Key design decisions:

- **Hashed keys**: The cache key is `sha256(api_key + base_url)`. Plaintext keys never
  appear as dict keys, preventing memory inspection attacks.
- **Bounded size (128)**: Limits memory to ~128 httpx connection pools. For 128 tenants,
  this is ample. Beyond that, LRU eviction kicks in.
- **TTL (300s)**: Clients not used for 5 minutes are closed and evicted. This prevents
  stale connections and controls resource usage.
- **Thread-safe**: Uses a threading lock for concurrent access.
- **Client cleanup**: Calls `client.close()` on eviction to release httpx resources.

### Recommendation

1. Create `kaizen/nodes/ai/_client_cache.py` with `_ProviderClientCache`
2. Add a module-level instance: `_client_cache = _ProviderClientCache()`
3. In OpenAI `chat()`, replace direct `openai.OpenAI(**kwargs)` with cache lookup
4. Same for Anthropic and all providers once D2 is implemented
5. Add async variant using `asyncio.Lock` for `chat_async()` paths

**Estimated Complexity: M (Medium)**
**Dependencies: D2 (more providers to cache once they support BYOK)**

---

## Risk Register

| ID  | Risk                                                    | Likelihood             | Impact   | Severity        | Mitigation                                       |
| --- | ------------------------------------------------------- | ---------------------- | -------- | --------------- | ------------------------------------------------ |
| D1  | API key leaked via workflow serialization               | Certain                | Critical | **CRITICAL**    | Redaction hooks on NodeInstance.model_dump()     |
| D2  | BYOK silently falls back to env var on 4 providers      | High                   | High     | **HIGH**        | Add per-request client creation to each provider |
| D3  | Async path silently drops BYOK credentials              | High                   | High     | **HIGH**        | Mirror sync BYOK pattern to chat_async()         |
| D4  | auto_detect drops explicit api_key/base_url             | Medium                 | High     | **HIGH**        | Thread kwargs through auto_detect_provider()     |
| D5  | Error messages leak credentials to callers              | Medium                 | High     | **HIGH**        | Sanitization utility for all 27 error paths      |
| D6  | New client per BYOK call causes performance degradation | Low (at current scale) | Medium   | **SIGNIFICANT** | Bounded LRU cache with hashed keys               |

---

## Implementation Roadmap

### Phase 1: Critical Security (D1 + D5)

**Priority**: Ship immediately.
**Effort**: 1 session.

- D1: Add `SENSITIVE_CONFIG_KEYS` and redaction to `NodeInstance`
- D5: Create error sanitizer, apply to all 27 locations
- Tests: Serialization leak test, error sanitization test

### Phase 2: Functional Completeness (D2 + D3 + D4)

**Priority**: Ship within 1 week.
**Effort**: 1-2 sessions.

- D4: Fix auto_detect_provider to accept and thread api_key/base_url (smallest, do first)
- D2: Add BYOK to Perplexity (S), Google (M), Azure (M), Docker (S) sync methods
- D3: Mirror all sync BYOK patterns to async methods; fix BaseAgent.run_async() caller
- Tests: Per-provider BYOK integration tests (mock SDK clients)

### Phase 3: Performance (D6)

**Priority**: Ship within 2 weeks.
**Effort**: 1 session.

- D6: Implement \_ProviderClientCache, integrate with OpenAI + Anthropic
- Tests: Cache hit/miss/eviction/TTL tests

---

## Cross-Reference Audit

### Documents affected by these changes

- `packages/kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py` -- D2, D3, D5, D6
- `packages/kailash-kaizen/src/kaizen/nodes/ai/llm_agent.py` -- D1 (api_key NodeParameter), D3 (async caller)
- `packages/kailash-kaizen/src/kaizen/core/base_agent.py` -- D3 (run_async caller)
- `packages/kailash-kaizen/src/kaizen/core/workflow_generator.py` -- D1 (api_key injection)
- `packages/kailash-kaizen/src/kaizen/config/providers.py` -- D4 (auto_detect_provider)
- `src/kailash/workflow/graph.py` -- D1 (NodeInstance serialization)
- `src/kailash/runtime/distributed.py` -- D1 (workflow serialization to Redis)
- `src/kailash/runtime/local.py` -- D1 (audit trail serialization)
- `src/kailash/utils/export.py` -- D1 (workflow export)

### Inconsistencies found

1. **OpenAI has BYOK in sync but not async** -- inconsistent API surface
2. **Anthropic has BYOK in sync but no async method at all** -- missing capability
3. **Perplexity partially sanitizes errors but no other provider does** -- inconsistent safety
4. **ProviderConfig stores api_key as plaintext str** -- no SecretStr protection at config level
5. **`use_async_llm` is restricted to OpenAI only** (config.py:133) -- artificial limitation
   once async BYOK is implemented across all providers

---

## Decision Points

- **D1 fix approach**: Confirm Option C (redaction hooks) for immediate fix, or invest in
  Option B (credential store) for a stronger long-term solution?
- **D2 priority**: Should Docker Model Runner be included in the initial batch, or deferred?
- **D3 scope**: Should we remove the `use_async_llm` OpenAI-only restriction (config.py:133)
  once all providers support async BYOK?
- **D6 cache parameters**: Is max_size=128 and TTL=300s appropriate for expected tenant
  concurrency? What is the target tenant count for BYOK?
- **Cross-SDK**: Should kailash-rs be notified of D1 (serialization leak)? If they have an
  equivalent pattern, it needs the same fix.

---

## Success Criteria

| Item | Criterion                                                                                                 | Measurable?                                  |
| ---- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| D1   | `workflow.to_dict()` / `to_json()` / `to_yaml()` / `save()` / export never contain plaintext API keys     | Yes -- assertion test                        |
| D2   | All 4 providers accept and use `api_key`/`base_url` kwargs in `chat()`                                    | Yes -- mock client test per provider         |
| D3   | All providers' `chat_async()` accept and use BYOK kwargs; `BaseAgent.run_async()` threads credentials     | Yes -- async mock test                       |
| D4   | `get_provider_config(api_key="sk-test")` with no provider specified uses the provided key                 | Yes -- unit test                             |
| D5   | No `RuntimeError` message from any provider contains a pattern matching `sk-`, `key-`, `pplx-`, or `AIza` | Yes -- regex assertion on all 27 error paths |
| D6   | Second BYOK call with same credentials reuses client (no TLS handshake)                                   | Yes -- mock client creation count            |
