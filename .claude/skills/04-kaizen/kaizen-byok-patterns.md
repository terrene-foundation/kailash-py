# Kaizen BYOK (Bring Your Own Key) Patterns

Per-request API key and base URL overrides for multi-tenant scenarios.

## Architecture

Credentials flow through a **CredentialStore** — never stored in serializable node config.

```
BaseAgentConfig(api_key="sk-tenant-123")
  → WorkflowGenerator registers with CredentialStore
    → node_config["credential_ref"] = "cred_abc123"  (safe to serialize)
      → Kaizen agent resolves from CredentialStore at runtime
        → provider.chat(..., api_key="sk-tenant-123")
```

Key module: `kailash/workflow/credentials.py`

## Usage: Per-Request API Key

```python
from kaizen.core.config import BaseAgentConfig

# Tenant-specific config — api_key flows through CredentialStore
config = BaseAgentConfig(
    llm_provider=os.environ.get("LLM_PROVIDER", "openai"),
    model=os.environ["LLM_MODEL"],
    api_key="sk-tenant-123",        # Per-request override
    base_url="https://proxy.example.com/v1",  # Optional proxy
)

# Agent uses tenant's key, not env var
agent = MyAgent(config=config)
result = await agent.run(question="What is 2+2?")
```

## Usage: Provider Config Functions

All provider config functions accept `api_key` and `base_url`:

```python
from kaizen.config.providers import get_openai_config, get_provider_config

# Explicit provider
config = get_openai_config(api_key="sk-tenant-key", model=os.environ["LLM_MODEL"])

# Auto-detect with BYOK key
config = get_provider_config(api_key="sk-tenant-key")

# Anthropic
config = get_provider_config(provider="anthropic", api_key="sk-ant-key")
```

## Adding BYOK to a New Provider

When implementing a new provider's `chat()` method:

```python
def chat(self, messages, **kwargs):
    # 1. Extract per-request overrides
    per_request_api_key = kwargs.get("api_key")
    per_request_base_url = kwargs.get("base_url")

    # 2. Create per-request client if overrides, else shared client
    if per_request_api_key or per_request_base_url:
        client_kwargs = {}
        if per_request_api_key:
            client_kwargs["api_key"] = per_request_api_key
        if per_request_base_url:
            client_kwargs["base_url"] = per_request_base_url
        # Use cache for connection reuse
        client = _byok_cache.get_or_create(
            per_request_api_key, per_request_base_url,
            factory=lambda: SomeSDK(**client_kwargs),
        )
    else:
        if self._sync_client is None:
            self._sync_client = SomeSDK()
        client = self._sync_client

    # 3. Use client for the API call
    response = client.chat.completions.create(...)
```

Apply the same pattern to `chat_async()` using async client variants.

## Security Patterns

### Credential Redaction

`NodeInstance.model_dump()` redacts `_SENSITIVE_KEYS` as defense-in-depth. Credentials never appear in `to_dict()`, `to_json()`, `save()`, or export output.

### Error Sanitization

All provider exceptions pass through `sanitize_provider_error()` which strips API key patterns (`sk-*`, `AIza*`, `pplx-*`), bearer tokens, and URL-embedded credentials before exposing to callers.

### Input Validation

- Empty/whitespace api_key raises `ConfigurationError`
- `base_url` validated against SSRF (cloud metadata endpoints blocked)
- `Credential` dataclass is `frozen=True` (immutable)
- `Credential.__repr__()` redacts values

### Client Caching

`BYOKClientCache` (LRU, SHA-256 hashed keys, TTL 300s, max 128 entries) reuses per-request clients across calls with the same credentials. Thread-safe.

## Cross-References

- ADR-001: `workspaces/byok-hardening/02-plans/01-adr-credential-flow.md`
