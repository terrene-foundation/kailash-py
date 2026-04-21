# Migration Guide: LLM Deployment Abstraction (kailash-kaizen v2.11+)

This guide maps the legacy `kaizen.providers.*` / `kaizen.config.providers.*` surfaces to the new four-axis deployment abstraction introduced in issue #498. It covers every public symbol in the previous surface, the back-compat window, and idiomatic rewrites.

**Status**: the legacy surface is fully preserved through all v2.x releases. v3.0 is the earliest window for removal; removal will be preceded by a deprecation-window release documented in the changelog. Minimum coexistence period: 18 months from this release.

**Authoritative spec**: `specs/kaizen-llm-deployments.md`.

## Why The Change

The previous surface encoded the provider choice as a single string name (`"openai"`, `"anthropic"`, `"bedrock_claude"`, …). This conflates four independent dimensions of a real deployment target:

1. **Wire protocol** — the on-wire JSON shape (OpenAI chat format, Anthropic messages format, Google generateContent, …)
2. **Auth strategy** — how credentials are installed per request (bearer header, SigV4 signature, OAuth2 token, Azure Entra api-key)
3. **Endpoint** — the HTTPS base URL and routing path
4. **Model grammar** — how caller-supplied model aliases resolve to on-wire model identifiers

Collapsing these into one string made deployments like Bedrock-Claude (Anthropic wire, AWS SigV4 auth, Bedrock endpoint, Bedrock model grammar), Vertex-Claude (Anthropic wire, GCP OAuth2 auth, Vertex endpoint, Vertex model grammar), and air-gapped OpenAI-compatible (OpenAI wire, arbitrary bearer auth, custom endpoint, no grammar translation) impossible to express natively. Every new variant required a new adapter.

The new `LlmDeployment` primitive composes the four axes. Every preset is a 3-line classmethod. Adding a new foundation-model host is now a change at the preset layer, not a new adapter.

## Before / After — Common Call Sites

### Directly constructing a provider

**Before:**

```python
from kaizen.providers.registry import get_provider

provider = get_provider(
    "openai",
    model="gpt-4o-mini",
    api_key=os.environ["OPENAI_API_KEY"],
)
response = await provider.complete(messages=[...])
```

**After (preferred):**

```python
from kaizen.llm import LlmClient, LlmDeployment

deployment = LlmDeployment.openai(
    api_key=os.environ["OPENAI_API_KEY"],
    model=os.environ["OPENAI_PROD_MODEL"],
)
client = LlmClient.from_deployment(deployment)
response = await client.complete(messages=[...])
```

### Auto-selecting a provider from environment

**Before:**

```python
from kaizen.config.providers import autoselect_provider
provider = autoselect_provider()
```

**After (preferred):**

```python
from kaizen.llm import LlmClient
client = LlmClient.from_env()
```

`LlmClient.from_env()` resolves in three tiers: URI (`KAILASH_LLM_DEPLOYMENT`) > selector (`KAILASH_LLM_PROVIDER`) > legacy autoselect (OpenAI > Azure > Anthropic > Google ordering preserved). If nothing resolves, `NoKeysConfigured` is raised — it will NEVER fall back to a mock deployment silently.

### URI-based deployment configuration (new capability)

```bash
# Bedrock Claude
export KAILASH_LLM_DEPLOYMENT="bedrock://us-east-1/claude-3-opus-20240229"
export AWS_BEARER_TOKEN_BEDROCK="..."

# Vertex Claude / Gemini (dispatch by model prefix)
export KAILASH_LLM_DEPLOYMENT="vertex://my-project/us-central1/claude-3-sonnet@20240229"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/sa.json"

# Azure OpenAI
export KAILASH_LLM_DEPLOYMENT="azure://my-resource/gpt-4o-prod?api-version=2024-06-01"
export AZURE_OPENAI_API_KEY="..."

# OpenAI-compatible endpoints (Groq, Together, OpenRouter, self-hosted)
export KAILASH_LLM_DEPLOYMENT="openai-compat://api.groq.com/llama-3.1-70b"
export OPENAI_COMPAT_API_KEY="..."
```

All URI forms are validated against strict per-scheme regexes before any URL interpolation — hostnames, regions, project IDs, and resource names that fail validation are rejected with a typed `InvalidUri` error BEFORE a network call is issued.

## Legacy Symbol Map

| Legacy symbol                                              | New preferred path                                                | Back-compat guarantee  |
| ---------------------------------------------------------- | ----------------------------------------------------------------- | ---------------------- |
| `kaizen.providers.registry.get_provider("openai", ...)`    | `LlmClient.from_deployment(LlmDeployment.openai(...))`            | Preserved through v2.x |
| `kaizen.providers.registry.get_provider("anthropic", ...)` | `LlmClient.from_deployment(LlmDeployment.anthropic(...))`         | Preserved through v2.x |
| `kaizen.providers.registry.get_provider("google", ...)`    | `LlmClient.from_deployment(LlmDeployment.google(...))`            | Preserved through v2.x |
| `kaizen.providers.registry.get_provider("cohere", ...)`    | `LlmClient.from_deployment(LlmDeployment.cohere(...))`            | Preserved through v2.x |
| `kaizen.providers.registry.get_provider("mistral", ...)`   | `LlmClient.from_deployment(LlmDeployment.mistral(...))`           | Preserved through v2.x |
| `kaizen.providers.registry.get_provider("ollama", ...)`    | `LlmClient.from_deployment(LlmDeployment.ollama(...))`            | Preserved through v2.x |
| `kaizen.providers.registry.get_provider_for_model(model)`  | Use `LlmClient.from_env()` with `KAILASH_LLM_PROVIDER`            | Preserved through v2.x |
| `kaizen.providers.registry.PROVIDERS` dict                 | `kaizen.llm.presets.list_presets()` / `get_preset(name)`          | Additive-only in v2.x  |
| `kaizen.config.providers.validate_openai_config()`         | Env-key check still works; `LlmClient.from_env()` raises typed    | Preserved through v2.x |
| `kaizen.config.providers.validate_anthropic_config()`      | Env-key check still works                                         | Preserved through v2.x |
| `kaizen.config.providers.validate_google_config()`         | Env-key check still works                                         | Preserved through v2.x |
| `kaizen.config.providers.validate_azure_config()`          | Env-key check still works                                         | Preserved through v2.x |
| `kaizen.config.providers.autoselect_provider()`            | `LlmClient.from_env()` — internally routes through the same order | Preserved through v2.x |
| `OpenAIProvider`, `AnthropicProvider`, `GoogleProvider`, … | Unchanged importable; internally delegates to preset              | Preserved through v2.x |

### New Presets Without A Legacy Equivalent

These deployments had no single-string preset in the previous surface — they required hand-rolled adapters. They are now first-class:

| Preset                                                                                               | Enterprise surface                                           |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `LlmDeployment.bedrock_claude(...)`                                                                  | Claude models via AWS Bedrock (bearer-token auth)            |
| `LlmDeployment.bedrock_llama(...)`                                                                   | Llama models via AWS Bedrock                                 |
| `LlmDeployment.bedrock_titan(...)`                                                                   | Amazon Titan via AWS Bedrock                                 |
| `LlmDeployment.bedrock_mistral(...)`                                                                 | Mistral via AWS Bedrock                                      |
| `LlmDeployment.bedrock_cohere(...)`                                                                  | Cohere via AWS Bedrock                                       |
| `LlmDeployment.vertex_claude(...)`                                                                   | Claude via GCP Vertex AI (GCP OAuth2)                        |
| `LlmDeployment.vertex_gemini(...)`                                                                   | Gemini via GCP Vertex AI                                     |
| `LlmDeployment.azure_openai(...)`                                                                    | Azure OpenAI (AzureEntra auth: api-key / workload / managed) |
| `LlmDeployment.groq(...)` / `together(...)` / `fireworks(...)` / `openrouter(...)` / `deepseek(...)` | OpenAI-compatible hosted gateways                            |
| `LlmDeployment.lm_studio(...)` / `llama_cpp(...)` / `docker_model_runner(...)`                       | Self-hosted OpenAI-compatible runtimes                       |
| `LlmDeployment.huggingface(...)` / `perplexity(...)`                                                 | Direct inference-provider APIs                               |

## Migration Warning

When deployment-tier signals coexist with legacy per-provider keys, `LlmClient.from_env()` emits one structured log line:

```
WARNING  llm_client.migration.legacy_and_deployment_both_configured
         legacy_env_var=OPENAI_API_KEY  deployment_path=uri
```

The deployment path wins. No credential cross-contamination — `tests/regression/test_legacy_key_does_not_leak_into_deployment_path` enforces this.

## Optional Extras

Cloud-auth dependencies are optional extras so code that does not use them does not install them:

```bash
pip install kailash-kaizen            # base install; openai / anthropic / google / ollama / openai-compat all work
pip install kailash-kaizen[bedrock]   # adds botocore for AWS SigV4 canonicalization
pip install kailash-kaizen[vertex]    # adds google-auth for GCP OAuth2
pip install kailash-kaizen[azure]     # adds azure-identity for workload / managed identity variants
```

API-key-only Azure usage does NOT require `[azure]` — only the workload-identity / managed-identity variants need the extra.

## Security Hardening (New Defaults)

The migration brings security improvements that apply automatically when you adopt the new surface:

- Every `Endpoint.from_url(url)` runs an SSRF guard before the endpoint is finalized — private IPs, link-local, loopback, and non-HTTPS schemes are rejected with a typed `InvalidEndpoint`.
- DNS resolution for all LLM HTTP calls routes through `SafeDnsResolver`, which re-validates the resolved IP after connect to close the DNS-rebinding window.
- `ApiKey` uses `SecretStr` internally, has no `__eq__` / `__hash__`, and only supports constant-time comparison via `ApiKey.constant_time_eq(other)` backed by `hmac.compare_digest`.
- Every auth class's `__repr__` emits `auth_strategy_kind()` plus an 8-hex-char SHA-256 fingerprint — the raw credential never reaches a log line, a repr, or a pickled trace event.
- `AwsSigV4` canonicalization routes through `botocore.auth.SigV4Auth`. Inlined HMAC signing is grep-blocked in CI.
- `AwsBearerToken` and `AwsSigV4` enforce a region allowlist at construction time (`BEDROCK_SUPPORTED_REGIONS`). No default `AWS_REGION`.
- `LlmDeployment.mock()` is gated behind `KAILASH_TEST_MODE=1` OR the optional `[test-utils]` extra. `LlmClient.from_env()` NEVER returns a mock deployment.

## Deprecation Timeline

| Milestone                             | Action                                                                 |
| ------------------------------------- | ---------------------------------------------------------------------- |
| kailash-kaizen 2.11.0 (this release)  | New surface ships; legacy surface fully preserved                      |
| kailash-kaizen 2.x (next 18+ months)  | Legacy surface remains fully functional; no warnings on legacy imports |
| Later 2.x release (date TBD)          | Legacy imports begin emitting `DeprecationWarning`                     |
| kailash-kaizen 3.0 (earliest removal) | Legacy symbols removed; all call sites must use `kaizen.llm.*`         |

## References

- Spec: `specs/kaizen-llm-deployments.md`
- ADR: `workspaces/issue-498-llm-deployment/02-plans/02-adr-0001-llm-deployment-abstraction.md`
- Cross-SDK parity tests: `packages/kailash-kaizen/tests/cross_sdk_parity/`
- Issue: [terrene-foundation/kailash-py#498](https://github.com/terrene-foundation/kailash-py/issues/498)
