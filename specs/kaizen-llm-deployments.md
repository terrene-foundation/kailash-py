# Kaizen LLM Deployment Abstraction

Authoritative spec for the four-axis LLM deployment abstraction shipped by issue #498. Cross-SDK with `kailash-rs` issue #406.

## Four Axes

Every LLM deployment is fully described by four orthogonal axes:

1. **Wire protocol** — the on-wire JSON shape (OpenAIChat, AnthropicMessages, VertexGenerateContent, BedrockInvoke, etc.)
2. **Endpoint** — `(base_url, path_prefix)` tuple identifying the HTTPS target
3. **Auth strategy** — how credentials are installed on each request (ApiKeyBearer, AwsBearerToken, AwsSigV4, GcpOauth, AzureEntra)
4. **Model grammar** — how caller-supplied model aliases resolve to on-wire identifiers (BedrockClaudeGrammar, VertexClaudeGrammar, AzureOpenAIGrammar, etc.)

The `LlmDeployment` primitive composes these four axes into a single frozen value. `LlmClient.from_deployment(d)` wraps it for execution.

## Preset Catalog

Every preset is registered under a snake*case name matching `^[a-z]a-z0-9*]{0,31}$`. Preset names are **byte-identical** across kailash-py and kailash-rs.

### Direct providers (Session 2 — S3)

| Preset name           | Wire protocol         | Auth         |
| --------------------- | --------------------- | ------------ |
| `openai`              | OpenAIChat            | ApiKeyBearer |
| `anthropic`           | AnthropicMessages     | ApiKeyBearer |
| `google`              | GoogleGenerateContent | ApiKeyBearer |
| `cohere`              | CohereGenerate        | ApiKeyBearer |
| `mistral`             | MistralChat           | ApiKeyBearer |
| `perplexity`          | OpenAIChat            | ApiKeyBearer |
| `huggingface`         | HuggingfaceInference  | ApiKeyBearer |
| `ollama`              | OllamaNative          | StaticNone   |
| `docker_model_runner` | OllamaNative          | StaticNone   |
| `groq`                | OpenAIChat            | ApiKeyBearer |
| `together`            | OpenAIChat            | ApiKeyBearer |
| `fireworks`           | OpenAIChat            | ApiKeyBearer |
| `openrouter`          | OpenAIChat            | ApiKeyBearer |
| `deepseek`            | OpenAIChat            | ApiKeyBearer |
| `lm_studio`           | OpenAIChat            | StaticNone   |
| `llama_cpp`           | OpenAIChat            | StaticNone   |

### AWS Bedrock (Sessions 3 + 4 — S4a, S4b-i, S4b-ii)

| Preset name       | Grammar               | Auth           |
| ----------------- | --------------------- | -------------- |
| `bedrock_claude`  | BedrockClaudeGrammar  | AwsBearerToken |
| `bedrock_llama`   | BedrockLlamaGrammar   | AwsBearerToken |
| `bedrock_titan`   | BedrockTitanGrammar   | AwsBearerToken |
| `bedrock_mistral` | BedrockMistralGrammar | AwsBearerToken |
| `bedrock_cohere`  | BedrockCohereGrammar  | AwsBearerToken |

Bedrock region allowlist is `BEDROCK_SUPPORTED_REGIONS` (27 regions, cross-SDK parity with kailash-rs). Requests to any non-allowlisted region raise `RegionNotAllowed`.

SigV4 canonicalization routes through `botocore.auth.SigV4Auth` — inlined `hmac.new` in `kaizen/llm/auth/aws.py` is BLOCKED by the grep audit.

### GCP Vertex AI (Session 5 — S5)

| Preset name     | Grammar             | Auth     |
| --------------- | ------------------- | -------- |
| `vertex_claude` | VertexClaudeGrammar | GcpOauth |
| `vertex_gemini` | VertexGeminiGrammar | GcpOauth |

Audience scope is pinned to `https://www.googleapis.com/auth/cloud-platform` (stored as `CLOUD_PLATFORM_SCOPE`). Single-flight OAuth2 refresh via `asyncio.Lock`.

### Azure OpenAI (Session 6 — S6)

| Preset name    | Grammar            | Auth       |
| -------------- | ------------------ | ---------- |
| `azure_openai` | AzureOpenAIGrammar | AzureEntra |

`AzureEntra` has three variants (mutually exclusive):

- `api_key=...` → `api-key: <KEY>` header (NOT Authorization)
- `workload_identity=True` → DefaultAzureCredential
- `managed_identity_client_id=<id>` → ManagedIdentityCredential

Audience scope pinned to `https://cognitiveservices.azure.com/.default` (`COGNITIVE_SERVICES_SCOPE`). Default api-version pinned to `2024-06-01` (`AZURE_OPENAI_DEFAULT_API_VERSION`).

## Environment Resolution

`LlmClient.from_env()` resolves a deployment from environment in three tiers (Session 7 — S7):

### Tier 1: URI (`KAILASH_LLM_DEPLOYMENT`)

| Scheme             | Format                                              | Example                                              |
| ------------------ | --------------------------------------------------- | ---------------------------------------------------- |
| `bedrock://`       | `bedrock://{region}/{model}`                        | `bedrock://us-east-1/claude-3-opus`                  |
| `vertex://`        | `vertex://{project}/{region}/{model}`               | `vertex://my-gcp-project/us-central1/gemini-1.5-pro` |
| `azure://`         | `azure://{resource}/{deployment}?api-version={ver}` | `azure://my-resource/gpt-4o?api-version=2024-06-01`  |
| `openai-compat://` | `openai-compat://{host}/{model}`                    | `openai-compat://api.groq.com/llama-3.1-70b`         |

Per-scheme regex validation is strict: attacker hostnames (`evil.attacker.com`), malformed regions (`not-a-region`), or leading-digit projects (`1bad-project`) are rejected BEFORE any URL interpolation.

### Tier 2: Selector (`KAILASH_LLM_PROVIDER`)

Holds a preset name. Corresponding env vars per preset resolved automatically:

- `openai` → `OPENAI_API_KEY`, `OPENAI_PROD_MODEL` (fallback `OPENAI_MODEL`)
- `anthropic` → `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- `google` → `GOOGLE_API_KEY` (fallback `GEMINI_API_KEY`), `GOOGLE_MODEL` (fallback `GEMINI_MODEL`)
- `bedrock_claude` → `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION`, `BEDROCK_CLAUDE_MODEL_ID`
- `azure_openai` → `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_RESOURCE`, `AZURE_OPENAI_DEPLOYMENT`

### Tier 3: Legacy autoselect

Falls back to today's `autoselect_provider()` ordering:

1. `OPENAI_API_KEY` → openai
2. `AZURE_OPENAI_API_KEY` → azure_openai
3. `ANTHROPIC_API_KEY` → anthropic
4. `GOOGLE_API_KEY` → google

### Migration window isolation

When deployment-tier signals (URI or selector) coexist with legacy per-provider keys, `WARNING llm_client.migration.legacy_and_deployment_both_configured` is emitted and the deployment path wins. No credential cross-contamination.

## Security Contract (§6)

All §6 threats enumerated in the spec have named tests in `packages/kailash-kaizen/tests/unit/llm/security/`:

| Threat                                          | Test file                                            |
| ----------------------------------------------- | ---------------------------------------------------- |
| 6.1 URL safety                                  | `test_llmhttpclient_ssrf_rejects_private_ips.py`     |
| 6.2 DNS rebinding                               | `test_llmhttpclient_ssrf_rejects_private_dns.py`     |
| 6.3 Log-injection via preset names              | `test_deployment_preset_regex_rejects_injection.py`  |
| 6.4 Timing side-channel (credential comparison) | `test_credential_comparison_uses_constant_time.py`   |
| 6.5 Classification-aware prompt redaction       | `test_llmclient_redacts_classified_prompt_fields.py` |
| 6.6 Credential scrub in error bodies            | `test_apikey.py` + `test_errors.py`                  |
| 6.7 Secret-serialization hygiene                | `test_apikey.py` pickle/deepcopy overrides           |
| 6.8 Credential zeroize on rotate                | `test_aws_credentials_zeroize_on_rotate.py`          |

## Cross-SDK Parity

The following MUST be byte-identical between kailash-py and kailash-rs:

- Preset names (all entries in the catalog above)
- `CLOUD_PLATFORM_SCOPE` = `"https://www.googleapis.com/auth/cloud-platform"`
- `COGNITIVE_SERVICES_SCOPE` = `"https://cognitiveservices.azure.com/.default"`
- `AZURE_OPENAI_DEFAULT_API_VERSION` = `"2024-06-01"`
- `BEDROCK_SUPPORTED_REGIONS` region list
- `auth_strategy_kind()` labels: `api_key`, `aws_bearer_token`, `aws_sigv4`, `gcp_oauth`, `azure_entra_api_key`, `azure_entra_workload_identity`, `azure_entra_managed_identity`
- `grammar_kind()` labels: `bedrock_claude`, `bedrock_llama`, `bedrock_titan`, `bedrock_mistral`, `bedrock_cohere`, `vertex_claude`, `vertex_gemini`, `azure_openai`
- Fingerprint algorithm: first 8 hex chars of SHA-256

## Observability Contract (ADR-0001 D8)

Every `LlmClient.complete` / `stream_completion` call emits three structured log events (`llm.request.start`, `llm.request.ok`, `llm.request.error`) whose canonical field-name set is byte-identical across kailash-py and kailash-rs:

| Field                | Description                                                       | Emitted on         |
| -------------------- | ----------------------------------------------------------------- | ------------------ |
| `deployment_preset`  | Preset name, regex `^[a-z][a-z0-9_]{0,31}$`                       | start / ok / error |
| `wire_protocol`      | `WireProtocol` enum member (`OpenAiChat`, `AnthropicMessages`, …) | start / ok / error |
| `endpoint_host`      | URL-encoded hostname only — NOT the full URL                      | start / ok / error |
| `auth_strategy_kind` | Result of `auth.auth_strategy_kind()` — NEVER the credential      | start / ok / error |
| `model_on_wire_id`   | Resolved model id returned by `ModelGrammar.resolve()`            | start / ok / error |
| `request_id`         | UUID correlation id (see `rules/observability.md` §2)             | start / ok / error |
| `latency_ms`         | Wall-clock float                                                  | ok / error         |
| `upstream_status`    | HTTP status code                                                  | ok                 |
| `error_class`        | Exception class name                                              | error              |

Transport-layer emission (`kaizen.llm.http_client.LlmHttpClient`) currently ships a subset (`deployment_preset`, `auth_strategy_kind`, `endpoint_host`, `request_id`, `latency_ms`, `method`, `status_code`, `exception_class`). The LlmClient wrapper above HTTP adds `wire_protocol`, `model_on_wire_id`, `upstream_status`, `error_class` before final emission. Credential-carrying names (`api_key`, `authorization`, `token`, `secret_access_key`) MUST NEVER appear as field NAMES in any emission path — enforced by `tests/cross_sdk_parity/test_observability_field_names_match_rust.py`.

Field names are validated against `logging.LogRecord` reserved attributes (`module`, `name`, `msg`, etc.) per `rules/observability.md` §9 — a collision silently corrupts log triage.

## Error Taxonomy

Full hierarchy under `kaizen.llm.errors.LlmClientError`. Every class is an importable `Exception` subclass AND a cross-SDK variant in Rust's `LlmClientError` enum (EATP D6):

```
LlmClientError                         -- root; catch-all for the deployment surface
├── LlmError                           -- provider-call failures
│   ├── Timeout(timeout_s: float)
│   ├── RateLimited(retry_after: float)
│   ├── ProviderError(status, body)    -- body is credential-scrubbed before construction
│   └── InvalidResponse(reason: str)
├── AuthError
│   ├── Invalid(...)                   -- credential rejected by provider
│   ├── Expired(...)
│   └── MissingCredential(source_hint: str)
├── EndpointError
│   ├── InvalidEndpoint(reason: str)   -- scheme / ip / host validation failed
│   └── Unreachable(host: str)
├── ModelGrammarError
│   ├── ModelGrammarInvalid(reason: str)
│   └── ModelRequired(deployment_preset, env_hint)
└── ConfigError
    ├── NoKeysConfigured(...)          -- from_env() found zero credentials
    ├── InvalidUri(...)                -- KAILASH_LLM_DEPLOYMENT URI failed regex
    └── InvalidPresetName(...)         -- register_preset() name regex violation
```

Construction signatures are fixed — changing them (e.g. adding `**kwargs` that echo user input into the message) is a security-review-blocking change. `ProviderError.body_snippet` is defensively scrubbed for OpenAI / Anthropic / Google / AWS / Bearer token patterns BEFORE truncation.

## Back-Compat Guarantees (ADR-0001 D6 + D10)

Today's public surface is preserved through all v2.x releases; v3.0 is the earliest window for removal; ≥ 18 months of coexistence.

| Preserved symbol                                   | Disposition                                                         |
| -------------------------------------------------- | ------------------------------------------------------------------- |
| `kaizen.providers.registry.get_provider(name)`     | Preserved; internally MAY route via `LlmClient.from_deployment`     |
| `kaizen.providers.registry.get_provider_for_model` | Preserved                                                           |
| `kaizen.providers.registry.PROVIDERS` dict         | Additive-only; no renames, no removals in v2.x                      |
| `kaizen.config.providers.validate_*_config`        | Preserved                                                           |
| `kaizen.config.providers.autoselect_provider`      | Preserved; ordering preserved (OpenAI > Azure > Anthropic > Google) |
| Every concrete `*Provider` class (OpenAIProvider…) | Preserved; functionally identical                                   |

New symbols are ADDITIVE under `kaizen.llm.*`: `LlmClient`, `LlmDeployment`, `WireProtocol`, `Endpoint`, `ResolvedModel`, `AuthStrategy`, `ApiKeyBearer`, `StaticNone`, `AwsBearerToken`, `AwsSigV4`, `GcpOauth`, `AzureEntra`. Zero breaking changes for callers on the legacy surface.

When BOTH the deployment-tier (URI or selector) AND legacy per-provider keys are set, a single `WARNING llm_client.migration.legacy_and_deployment_both_configured` is emitted and the deployment path wins. `tests/regression/test_legacy_key_does_not_leak_into_deployment_path` enforces no credential cross-contamination.

## Migration (from v0.9.x pre-#498)

**Before:**

```python
from kaizen.providers.registry import get_provider
provider = get_provider("openai", model="gpt-4o-mini", api_key=os.environ["OPENAI_API_KEY"])
```

**After (preferred):**

```python
from kaizen.llm import LlmClient, LlmDeployment
deployment = LlmDeployment.openai(
    api_key=os.environ["OPENAI_API_KEY"],
    model=os.environ["OPENAI_PROD_MODEL"],
)
client = LlmClient.from_deployment(deployment)
```

Legacy path still works — see `docs/migration/llm-deployments-v2.md` for the full symbol-by-symbol mapping.

## References

- Workspace: `workspaces/issue-498-llm-deployment/`
- ADR-0001: `workspaces/issue-498-llm-deployment/02-plans/02-adr-0001-llm-deployment-abstraction.md`
- Cross-SDK: `kailash-rs#406`
- Parity suite: `packages/kailash-kaizen/tests/cross_sdk_parity/`
- Migration guide: `docs/migration/llm-deployments-v2.md`
