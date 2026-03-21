# BYOK Security Hardening — Deferred Items from Red Team R1

## Background

Issue #12 implemented per-request API key override (BYOK) across the Kaizen provider chain.
Red team R1 (security-reviewer, intermediate-reviewer, deep-analyst) found 12 issues.
8 were fixed in the convergence round. 4 remain deferred.

## Deferred Items

### D1: API key in serializable node_config (C2 — CRITICAL)

API keys placed in `node_config` dict become part of `NodeInstance.config` (Pydantic BaseModel).
Any code that serializes the workflow (logging, persistence, export) will include plaintext API keys.
Needs architectural fix: SecretStr wrapper, runtime credential store, or non-serializable channel.

### D2: Provider coverage gap — 4 providers ignore per-request kwargs (HIGH)

Google/Gemini, Azure, Perplexity, Docker providers' `chat()` methods silently ignore
`api_key`/`base_url` kwargs. Silent fallback to env vars in BYOK scenario.

### D3: Async chat_async() has no per-request support (HIGH)

Even OpenAI's `chat_async()` (and all other providers' async methods) ignore per-request
overrides. Users with `use_async_llm=True` silently lose BYOK credentials.

### D4: auto_detect_provider drops api_key/base_url (HIGH)

When `get_provider_config()` falls through to `auto_detect_provider()`, explicit BYOK
params are silently dropped.

### D5: str(e) leaks error details to caller (HIGH)

Provider error messages passed via `str(e)` can contain auth details, base_url with
credentials, or internal error codes. Multi-tenant callers shouldn't see these.

### D6: Per-request client caching (SIGNIFICANT)

Each BYOK call creates a new OpenAI()/Anthropic() client with full TLS handshake.
At scale, this causes performance degradation. Needs bounded LRU cache.

## Cross-SDK

kailash-rs implemented their equivalent in esperie-enterprise/kailash-rs#52.
