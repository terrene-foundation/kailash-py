# BYOK Hardening — Implementation Plan

## Approach (ADR-001 — Accepted)

**Credential Store**: Separate credentials from serializable workflow config entirely. API keys never enter `NodeInstance.config`. They flow through a non-serializable, request-scoped `CredentialStore`.

Plus defense-in-depth: `model_dump()` redaction as safety net, error sanitization, debug statement removal.

## Stakeholder Decisions

1. **D1 approach**: Credential Store (not redaction) — architecturally clean, eliminates all 10 leak vectors
2. **Docker provider**: Include in M2 — full consistency across all providers
3. **Async restriction**: Remove `use_async_llm` OpenAI-only check after M2 is complete
4. **Cross-SDK**: Full alignment audit in progress — file issues for all gaps

## Milestones

### M1: Critical Security — must ship before BYOK production use

| TODO | Task                                                                                                | Item | Size | Files                    |
| ---- | --------------------------------------------------------------------------------------------------- | ---- | ---- | ------------------------ |
| 01   | Create `CredentialStore` module with register/resolve/clear/extract_sensitive                       | D1   | M    | credentials.py (new)     |
| 02   | Integrate CredentialStore into WorkflowGenerator — extract creds, store ref in node_config          | D1   | M    | workflow_generator.py    |
| 03   | Update LLMAgentNode to resolve credentials from store (with fallback to config for backward compat) | D1   | M    | llm_agent.py             |
| 04   | Add `_SENSITIVE_KEYS` safety net to NodeInstance.model_dump() (defense-in-depth)                    | D1   | S    | graph.py                 |
| 05   | Remove debug print() statements from graph.py and llm_agent.py                                      | D1   | S    | graph.py, llm_agent.py   |
| 06   | Sanitize NodeConfigurationError messages (strip config values)                                      | D1   | S    | graph.py                 |
| 07   | Create `error_sanitizer.py` with `sanitize_provider_error()`                                        | D5   | M    | error_sanitizer.py (new) |
| 08   | Apply sanitizer to all 27+ except blocks in ai_providers.py                                         | D5   | M    | ai_providers.py          |
| 09   | Apply sanitizer to LLMAgentNode error response and \_provider_llm_response                          | D5   | S    | llm_agent.py             |
| 10   | Thread api_key/base_url through auto_detect_provider()                                              | D4   | S    | providers.py             |
| 11   | Clear CredentialStore after workflow execution in LocalRuntime/AsyncLocalRuntime                    | D1   | S    | local.py, async_local.py |
| 12   | Regression tests for M1: serialization leak, error sanitization, auto-detect, credential lifecycle  | All  | M    | tests/                   |

### M2: Provider Parity + Async — multi-provider BYOK complete

| TODO | Task                                                                           | Item  | Size | Files           |
| ---- | ------------------------------------------------------------------------------ | ----- | ---- | --------------- |
| 13   | Perplexity chat() per-request api_key (copy OpenAI pattern)                    | D2    | S    | ai_providers.py |
| 14   | Google/Gemini chat() per-request api_key                                       | D2    | M    | ai_providers.py |
| 15   | Azure chat() per-request api_key + base_url                                    | D2    | M    | ai_providers.py |
| 16   | Docker chat() per-request base_url                                             | D2    | S    | ai_providers.py |
| 17   | OpenAI chat_async() per-request support (mirror sync pattern)                  | D3    | M    | ai_providers.py |
| 18   | Anthropic chat_async() per-request support                                     | D3    | M    | ai_providers.py |
| 19   | Google/Azure/Perplexity/Docker chat_async() per-request support                | D3    | M    | ai_providers.py |
| 20   | BaseAgent.run_async() thread BYOK credentials to provider                      | D3    | M    | base_agent.py   |
| 21   | Remove `use_async_llm` OpenAI-only restriction from BaseAgentConfig            | D3    | S    | config.py       |
| 22   | Ensure extensible provider pattern — document how to add BYOK to new providers | D2/D3 | S    | docs or skill   |
| 23   | Regression tests for M2: all providers sync + async BYOK                       | D2,D3 | M    | tests/          |

### M3: Performance — at-scale optimization

| TODO | Task                                                                                                    | Item | Size | Files                 |
| ---- | ------------------------------------------------------------------------------------------------------- | ---- | ---- | --------------------- |
| 24   | Create BYOKClientCache (bounded LRU, SHA-256 hashed keys, TTL, thread-safe, client cleanup on eviction) | D6   | M    | client_cache.py (new) |
| 25   | Integrate cache into OpenAI + Anthropic sync + async providers                                          | D6   | M    | ai_providers.py       |
| 26   | Integrate cache into Google/Azure/Perplexity/Docker providers                                           | D6   | M    | ai_providers.py       |
| 27   | Cache eviction, thread-safety, and TTL tests                                                            | D6   | M    | tests/                |

## Dependency Graph

```
M1 (Critical Security):
  TODO-01 ──> TODO-02 ──> TODO-03 ──> TODO-12
  TODO-01 ──> TODO-04 (safety net)
  TODO-01 ──> TODO-11 (runtime cleanup)
  TODO-05 (parallel)
  TODO-06 (parallel)
  TODO-07 ──> TODO-08 ──> TODO-09 ──> TODO-12
  TODO-10 ──> TODO-12

M2 (Provider Parity):
  TODO-13,14,15,16 (all parallel — sync providers)
  TODO-13..16 ──> TODO-17,18,19 (async mirrors sync)
  TODO-20 (parallel with 17-19)
  TODO-17..20 ──> TODO-21 (remove restriction after async done)
  TODO-22 (parallel)
  ALL ──> TODO-23

M3 (Performance):
  TODO-24 ──> TODO-25 ──> TODO-26 ──> TODO-27
  Depends on M2 (more providers to cache)
```

## Risk Register

| ID  | Risk                                           | Severity    | Phase |
| --- | ---------------------------------------------- | ----------- | ----- |
| D1  | API key leaked via 10 serialization paths      | CRITICAL    | M1    |
| D5  | 31 except blocks leak credentials via str(e)   | HIGH        | M1    |
| D4  | auto_detect_provider silently drops BYOK keys  | HIGH        | M1    |
| D2  | 4 providers silently ignore per-request kwargs | HIGH        | M2    |
| D3  | All async paths ignore per-request credentials | HIGH        | M2    |
| D6  | New client per BYOK call, no connection reuse  | SIGNIFICANT | M3    |

## Cross-SDK Actions

Full alignment audit running. Will file issues for:

- D1 serialization leak (if kailash-rs has equivalent pattern)
- R1 convergence fixes (tool-call loop, error hooks, SSRF validation)
- Any other gaps found since last alignment (2026-03-17)

## Success Criteria

| Item | Criterion                                                                                                  |
| ---- | ---------------------------------------------------------------------------------------------------------- |
| D1   | `workflow.to_dict()` / `to_json()` / `save()` / export contain NO plaintext API keys                       |
| D1   | CredentialStore cleared after every workflow execution                                                     |
| D4   | `get_provider_config(api_key="sk-test")` without provider uses the provided key                            |
| D5   | No RuntimeError from any provider contains `sk-`, `key-`, `pplx-`, `AIza`, or URL credentials              |
| D2   | All 6 providers (OpenAI, Anthropic, Google, Azure, Perplexity, Docker) honor per-request api_key in chat() |
| D3   | All providers' chat_async() honor per-request credentials                                                  |
| D3   | `use_async_llm=True` works with all providers, not just OpenAI                                             |
| D6   | Second BYOK call with same credentials reuses cached client                                                |
