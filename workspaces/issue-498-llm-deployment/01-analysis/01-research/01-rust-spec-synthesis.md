# Rust Spec Synthesis (Python-oriented)

Source: `/Users/esperie/repos/loom/kailash-rs/specs/llm-deployments.md` (724 lines)
Source: `/Users/esperie/repos/loom/kailash-rs/workspaces/use-feedback-triage/02-plans/02-adrs/ADR-0001-llm-deployment-abstraction.md` (217 lines)
Authority: Rust spec is the single source of truth for semantics (EATP D6, independent impl + matching semantics). Python impl is idiomatic but must emit identical preset names, env precedence, log field shapes, and error taxonomy.

## 1. Four-Axis Decomposition

An LLM call is a cross product of four axes:

```
LlmDeployment = (wire_protocol × auth × endpoint × model_grammar)
```

- **WireProtocol** — closed enum (payload shape + response parser):
  `OpenAiChat`, `AnthropicMessages`, `GoogleGenerateContent`, `CohereGenerate`, `MistralChat`, `OllamaNative`, `HuggingFaceInference`. Small finite set; composition happens at the deployment level.
- **AuthStrategy** — Python ABC / Protocol with `async apply(request)`, `auth_strategy_kind() -> str`, optional `async refresh()`. Canonical impls: `StaticNone`, `ApiKeyBearer`, `AwsBearerToken`, `AwsSigV4`, `GcpOauth`, `AzureEntra`, `IbmIam`, `Custom`. **No `__repr__`/`__str__` that echoes credentials.**
- **Endpoint** — frozen dataclass / Pydantic model: `base_url`, `region`, `tls_overrides`. **Construct only via `Endpoint.new(url)` (or `Endpoint.from_url`)** which runs `url_safety.check_url()` (SSRF guard). Private-fields discipline — private attrs + only-constructor-sets invariants.
- **ModelGrammar** — Protocol with `resolve(caller_model: str) -> ResolvedModel`. `caller_model` MUST validate against `^[a-zA-Z0-9._:/@-]{1,256}$`. `ResolvedModel.extra_headers` is allowlist-gated (no `Authorization`, `Host`, `Cookie`, `x-api-key`, `x-amz-security-token`, `x-goog-api-key`, `anthropic-version`).

`LlmDeployment` holds: `wire_protocol`, `auth`, `endpoint`, `model_grammar`, `default_model`, `retry`, `timeout`. Construct via preset methods or a builder — never via kwargs into `__init__`.

## 2. Preset Names (EXACT — match Rust literally)

Name regex enforced by the observability layer: `^[a-z][a-z0-9_]{0,31}$`.

| Preset                                                                | Wire                      | Auth                              | Notes                                   |
| --------------------------------------------------------------------- | ------------------------- | --------------------------------- | --------------------------------------- |
| `openai`                                                              | OpenAiChat                | ApiKeyBearer(Authorization)       | reads `OPENAI_API_KEY`                  |
| `anthropic`                                                           | AnthropicMessages         | ApiKeyBearer(AnthropicApiKey hdr) | reads `ANTHROPIC_API_KEY`               |
| `google`                                                              | GoogleGenerateContent     | ApiKeyBearer(XGoogApiKey)         | reads `GOOGLE_API_KEY`/`GEMINI_API_KEY` |
| `mistral`, `cohere`, `perplexity`, `huggingface`                      | varies                    | ApiKeyBearer                      | direct providers                        |
| `groq`, `together`, `fireworks`, `openrouter`, `deepseek`             | OpenAiChat                | ApiKeyBearer                      | OpenAI-compat aliases                   |
| `bedrock_claude`                                                      | AnthropicMessages         | AwsBearerToken / AwsSigV4         | region+model required                   |
| `bedrock_llama`, `bedrock_titan`, `bedrock_mistral`, `bedrock_cohere` | varies                    | Aws                               | Bedrock family                          |
| `vertex_claude`, `vertex_gemini`                                      | Anthropic / Google        | GcpOauth                          | project+region                          |
| `azure_openai`                                                        | OpenAiChat                | AzureEntra / ApiKey               | resource+deployment                     |
| `watsonx`, `databricks_model_serving`                                 | varies                    | IbmIam / token                    | cloud                                   |
| `ollama`, `llama_cpp`, `lm_studio`, `docker_model_runner`             | OllamaNative / OpenAiChat | optional                          | local                                   |
| `openai_compatible`                                                   | OpenAiChat                | ApiKeyBearer                      | user-supplied `base_url` — SSRF-gated   |
| `anthropic_compatible`                                                | AnthropicMessages         | auth arg                          | same                                    |
| `mock`                                                                | —                         | StaticNone                        | test-only (see §6)                      |

**Required Python surface (v0):** `openai`, `anthropic`, `google`, `bedrock_claude`, `vertex_claude`, `azure_openai`, `groq`, `openai_compatible`, `anthropic_compatible`, `mock`. Rest are additive aliases.

## 3. `from_env()` Precedence (Strict — first match wins)

1. **`KAILASH_LLM_DEPLOYMENT` URI** (strict per-scheme grammar):
   - `bedrock_claude://{region}/{model}` — `region` matches `^[a-z]{2}-[a-z]+-\d{1,2}$` AND is in the Bedrock allowlist. **Endpoint DERIVED from region, never parsed from URI.**
   - `bedrock_llama://{region}/{model}`, etc.
   - `vertex_claude://{project}/{region}/{model}` — project/region strict charset.
   - `azure_openai://{resource}/{deployment}` — `resource` matches `^[a-z0-9][a-z0-9-]{2,23}$`.
   - `groq://{model}`.
   - `openai_compatible://{host}/{path}?api_key_env={env_name}` — host runs through `url_safety.check_url`.
   - Ambiguity/failure → typed `LlmClientError` (no silent fallthrough).
2. **`KAILASH_LLM_PROVIDER` selector** + preset-specific env keys (e.g. `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION`, `BEDROCK_MODEL_ID`).
3. **Legacy per-provider keys** (today's semantics preserved): `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`/`GEMINI_API_KEY`, `MISTRAL_API_KEY`, `COHERE_API_KEY`, `PERPLEXITY_API_KEY`, `HUGGINGFACE_API_KEY`, `AZURE_OPENAI_*`, `DOCKER_MODEL_RUNNER_KEY`. Multiple matches produce a multi-deployment client.
4. **No keys detected** → `LlmClientError.NoKeysConfigured`. MUST NOT fall back to mock.

### 3a. AWS Bedrock STP-unblock path

`AWS_BEARER_TOKEN_BEDROCK` alone activates `bedrock_claude` IF `AWS_REGION` is set (fail-closed — NO default region). `BEDROCK_MODEL_ID` resolves the on-wire model; absence → typed `LlmClientError.ModelRequired(deployment_preset="bedrock_claude")`.

### 3b. Migration-window isolation

While legacy provider-key config and the new deployment path coexist, each call path picks exactly one. Both configured for the same wire protocol → emit WARN `llm_client.migration.legacy_and_deployment_both_configured` and the deployment path wins. Python MUST carry a regression test `test_legacy_key_does_not_leak_into_deployment_path`.

## 4. Preset-Specific Invariants

### 4.1 Bedrock (AwsBearerToken, AwsSigV4)

- **Region allowlist** (updated per AWS): `us-east-1, us-east-2, us-west-2, ap-southeast-1, ap-southeast-2, ap-northeast-1, eu-central-1, eu-west-3, ca-central-1`. Regions outside the allowlist → `AuthError.RegionNotAllowed`.
- **Credential expiry:** `AwsSigV4` uses a lock-free atomic credential slot (Python analog: `threading.RLock` around an immutable `AwsCredentials` frozen dataclass, or `asyncio.Lock` for async swap; NO arc-swap equivalent in Python stdlib — document the chosen primitive). On upstream 403 `ExpiredTokenException`, call `refresh()` which re-reads the credential provider.
- **SigV4 correctness:** MUST route through `botocore` / `aws-sigv4` (Python: `botocore.auth.SigV4Auth` from the boto3 family or `aws-requests-auth`). Inlined HMAC signing is BLOCKED. Ship the AWS SigV4 known-answer test vectors as Tier 1.
- **Secret handling:** `AwsCredentials` wraps `access_key_id`, `secret_access_key`, `session_token` in `SecretStr` (Pydantic) or a typed `Secret` wrapper with `__repr__` redaction. Explicit `zeroize()` on drop is Python-weak (GC), so compensate with `del` + `ctypes` zeroization on sensitive bytes where feasible, document the gap.

### 4.2 Vertex (GcpOauth)

- **Single-flight refresh:** N concurrent callers produce 1 refresh request. Python: `asyncio.Lock` guarding a `CachedToken` with `expires_at` check; sync path uses `threading.Lock`.
- **Credential source:** `GOOGLE_APPLICATION_CREDENTIALS` service account JSON or application-default credentials via `google-auth` library.
- **Vertex grammar:** Anthropic-on-Vertex model IDs `claude-3-5-sonnet@20241022` (@-delimited version); endpoint DERIVED from project + region.

### 4.3 Azure OpenAI (AzureEntra)

- **Auth variants (S6 ordering):** api-key fallback first, then workload identity, then managed identity — match Rust's S6 order.
- **Token cache:** `CachedToken` with `asyncio.Lock` single-flight refresh; 5-min skew tolerance.
- **Endpoint grammar:** `https://{resource}.openai.azure.com/openai/deployments/{deployment}/chat/completions?api-version={v}`. `resource` validated at construction.
- **Header shape:** `api-key: <KEY>` OR `Authorization: Bearer <entra-token>` — the `with_auth_mode(AuthMode.AzureApiKey)` legacy path routes to the former.

### 4.4 `openai_compatible` escape hatch

- `base_url` MUST go through `Endpoint.new()` → `url_safety.check_url()`.
- SSRF guard rejects: private IPv4/IPv6, loopback, link-local, cloud-metadata (`169.254.169.254`, `metadata.google.internal`, `metadata.azure.com`), localhost hostnames.
- DNS rebinding: construct the HTTP client via `LlmHttpClient.new(endpoint)` which installs a `SafeDnsResolver` (Python equivalent: resolve once, pin, validate resolved IP is not private — verify during the actual TCP connect not just name lookup).

## 5. Security Threats (spec § 6 — Python MUST carry all)

| #    | Threat                                  | Python mitigation                                                                                                                                                                                                            |
| ---- | --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 6.1  | SSRF via attacker `base_url`            | Private-fields + `Endpoint.from_url()` only; `url_safety.check_url` compulsory.                                                                                                                                              |
| 6.2  | Credential leakage in error messages    | `AuthError.Invalid` carries 4-byte SHA-256 fingerprint only; upstream bodies regex-scrubbed for `Bearer …`, `"access_token":…`, `"session_token":…`.                                                                         |
| 6.3  | Credential in logs                      | Mask `Authorization`, `x-api-key`, `x-goog-api-key`, `anthropic-api-key`, `x-amz-security-token` before any handler logs. Mask sentinel `"***"` on success, `"<mask-failed>"` on malformed (observability.md §6 compliance). |
| 6.4  | Timing side channel on API-key compare  | `ApiKey` newtype wrapping `SecretStr`; only `ApiKey.constant_time_eq(other)` via `hmac.compare_digest`. No `__eq__`.                                                                                                         |
| 6.5  | Classification-aware redaction          | Advisory `data_residency` field on `LlmDeployment`. SDK advertises; PACT/trust-plane enforce via optional `ClassificationPolicy` hook. Default `AllowAll`.                                                                   |
| 6.6  | DNS rebinding + grammar injection       | `SafeDnsResolver` + strict per-scheme URI grammar. Region allowlist at auth construction. No default `AWS_REGION`.                                                                                                           |
| 6.7  | Custom AuthStrategy leakage             | `Custom.__init__` emits WARN `llm.auth.custom_constructed`. Contract: `apply()` MUST NOT log credentials; `__repr__` MUST redact.                                                                                            |
| 6.8  | Credential zeroization + rotation       | `SecretStr`; `refresh()` called on 401/403; single-flight refresh via `asyncio.Lock`.                                                                                                                                        |
| 6.9  | SigV4 correctness / replay              | MUST use botocore/aws-sigv4 lib. AWS known-answer vectors as Tier 1. 5-min skew window.                                                                                                                                      |
| 6.10 | Model-grammar header injection          | `caller_model` regex gate; `ResolvedModel.with_extra_header` deny-list.                                                                                                                                                      |
| 6.M1 | Mock in prod                            | `LlmDeployment.mock()` gated via `__debug__` + env/runtime guard; `from_env()` MUST NOT return mock.                                                                                                                         |
| 6.M2 | Observability log injection             | Preset name regex at registration + validated at emit. `endpoint_host` URL-encoded.                                                                                                                                          |
| 6.M5 | Legacy API cannot configure new presets | Legacy setters enumerated: only `{openai, anthropic, google}` have key-setter methods. Bedrock/Vertex/Azure reachable only via `from_deployment`.                                                                            |

## 6. Observability Contract (§ 7 — exact field names)

Every `LlmClient.complete` / `stream_completion` emits:

- `llm.request.start` — `deployment_preset`, `wire_protocol`, `endpoint_host`, `auth_strategy_kind`, `model_on_wire_id`, `request_id`
- `llm.request.ok` — `deployment_preset`, `model_on_wire_id`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `request_id`
- `llm.request.error` — `deployment_preset`, `model_on_wire_id`, `upstream_status`, `error_class`, `latency_ms`, `request_id`

`deployment_preset` field name + regex + values are byte-for-byte identical to Rust emissions. `auth_strategy_kind` values (literals) shared: `static_none`, `api_key_bearer`, `aws_bearer_token`, `aws_sigv4`, `gcp_oauth`, `azure_entra`, `ibm_iam`, `custom`. Credential-carrying headers masked BEFORE any log sees them.

## 7. Public API Shape (Python-idiomatic)

```python
from kailash.kaizen import LlmClient, LlmDeployment, AwsBearerToken

# Preset constructors are classmethods returning LlmDeployment
client = LlmClient.from_deployment(
    LlmDeployment.bedrock_claude(
        region="ap-southeast-1",
        auth=AwsBearerToken.from_env(),
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
    )
)

# Env-driven
client = LlmClient.from_env()

# Back-compat (current callers must keep working)
client = LlmClient()  # zero-arg
client = client.with_openai_key(os.environ["OPENAI_API_KEY"])

# Embeddings
resp = await client.embed(EmbedOptions.from_deployment(deployment).with_model("text-embedding-3-large").with_input(["..."]))

# Streaming
async for chunk in client.stream_completion(request): ...
```

Python idioms: classmethod constructors (`AwsBearerToken.from_env`), keyword-only args for all preset methods, `pydantic.BaseModel` frozen=True for value types, `Protocol` + `ABC` for `AuthStrategy` / `ModelGrammar`, `SecretStr` for credentials. No `asdict()` / `__fields__` leak of secrets.

## 8. Error Taxonomy (Python)

```python
class LlmClientError(Exception): ...
class NoKeysConfigured(LlmClientError): ...
class UnsupportedProviderForLegacyApi(LlmClientError):
    provider: str
class AmbiguousDeploymentSelection(LlmClientError):
    candidates: list[str]
class ModelRequired(LlmClientError):
    deployment_preset: str
class EndpointError(LlmClientError): ...   # InvalidScheme, Private, Loopback, LinkLocal, CloudMetadata
class AuthError(LlmClientError):
    strategy_kind: str    # Missing, Invalid(fingerprint:4bytes), ExpiredRefreshRequired, RegionNotAllowed, SigV4Failed
class ModelGrammarError(LlmClientError): ...
class LlmError(Exception):
    Transport, RateLimited(retry_after), AuthDenied, InBandError(preset, body),
    Upstream(status, body_scrubbed), Canceled, InvalidInput, Internal
```

Errors NEVER echo raw credential bytes. Fingerprint is `hashlib.sha256(raw).digest()[:4]`.

## 9. Migration & Back-Compat

- v2.x: `LlmDeployment` + presets land additively. Legacy provider registry preserved. `LlmClient()` zero-arg + fluent setters wrap deployments internally.
- v3.0 earliest: legacy provider registry removal. ≥ 18 months coexistence.
- No breaking changes for callers of today's `kaizen.providers.*` surface.

## 10. Out-of-Scope Capability Axes (§ 4.7)

Explicitly NOT four-axis: tool calling, vision/multimodal, batch API, prompt caching, Assistants API, audio. These cross-cut wire protocols and are handled by separate surfaces (`CompletionRequest.attachments`, `AssistantClient`, `AudioClient`).

## 11. Dependency Budget (Python)

New direct deps:

- `botocore` or `aws-requests-auth` (SigV4 signing — MUST use AWS-maintained lib, NOT inlined HMAC)
- `google-auth` (Vertex OAuth — Google-maintained)
- `azure-identity` (Entra workload/managed identity — Microsoft-maintained)
- `pydantic >= 2.0` (already a kaizen dep; used for frozen value types + `SecretStr`)

All gated behind optional extras per `rules/dependencies.md` with loud `ImportError` fallbacks naming the extra (`pip install kailash[bedrock]`, `kailash[vertex]`, `kailash[azure]`).

## 12. Session Sharding Summary

Rust splits into S1+S2 bundled / S3 / S4a-b-c / S5 / S6 / S7 / S8 / S9. Python mirrors with S8 elided (Python IS the binding surface — no FFI). See `02-plans/01-shard-breakdown.md` for the Python per-shard invariant count and file list.
