# ADR-0001 — LLM Deployment-Target Abstraction (Python)

- **Status**: Proposed (pending `/todos` gate)
- **Date**: 2026-04-18
- **Authors**: `/analyze` on `workspaces/issue-498-llm-deployment/`
- **Deciders**: Jack Hong (project owner)
- **Cross-SDK parent**: Rust ADR-0001 at `/Users/esperie/repos/loom/kailash-rs/workspaces/use-feedback-triage/02-plans/02-adrs/ADR-0001-llm-deployment-abstraction.md`
- **Related**: `specs/llm-deployments.md` (Python, authored at S9), GH issue `terrene-foundation/kailash-py#498`, cross-SDK `esperie-enterprise/kailash-rs#406`, reporter `terrene-foundation/kailash-coc-claude-rs#52`

## Context

The Rust SDK is landing a four-axis LLM deployment abstraction (kailash-rs#406) that decomposes the LLM-call grammar into `(wire × auth × endpoint × model_grammar)`. Per EATP D6 (independent implementation, matching semantics), the Python SDK MUST expose the identical abstraction.

The Python SDK's current state is NOT identical to Rust's starting point. Python has NO `LlmClient` class today — LLM work routes through `kaizen.providers.registry.get_provider(name)` + `kaizen.config.providers.*` + concrete per-provider classes. The provider-name keyspace conflates four axes into one string. The failure mode is the same as Rust's (Bedrock-Claude / Vertex-Claude / Azure-OpenAI / Groq / air-gapped vLLM cannot be expressed natively), and the architectural fix is the same.

The Python back-compat surface is therefore DIFFERENT from Rust back-compat. Python preserves `kaizen.providers.registry.*` + `kaizen.config.providers.*` + today's concrete provider classes; Rust preserves `LlmClient::new() + with_*_key()`.

## Decision

Adopt the four-axis deployment-target abstraction in `packages/kailash-kaizen/src/kaizen/llm/` with Python-idiomatic signatures:

```
LLM call = (wire_protocol × auth × endpoint × model_grammar)
```

- **`WireProtocol`** — `enum.Enum` subclass (closed set): `OpenAiChat`, `AnthropicMessages`, `GoogleGenerateContent`, `CohereGenerate`, `MistralChat`, `OllamaNative`, `HuggingFaceInference`.
- **`AuthStrategy`** — `typing.Protocol` with `async apply(request)`, `auth_strategy_kind() -> str`, `async refresh() -> None`. No `__repr__` that echoes credentials. Observability uses `auth_strategy_kind()` only.
- **`Endpoint`** — `pydantic.BaseModel` frozen=True, private attr names. Only constructor `Endpoint.from_url(url)` runs `url_safety.check_url()`. Struct-literal bypass is impossible because Pydantic `frozen=True` + `model_config = ConfigDict(arbitrary_types_allowed=False, extra='forbid')` rejects side-door writes.
- **`ModelGrammar`** — Protocol with `resolve(caller_model: str) -> ResolvedModel`. `caller_model` validated against `^[a-zA-Z0-9._:/@-]{1,256}$`. `ResolvedModel.extra_headers` allowlist-gated (deny: `authorization`, `host`, `cookie`, `x-amz-security-token`, `x-api-key`, `x-goog-api-key`, `anthropic-version`).
- **`LlmDeployment`** — frozen Pydantic model with `wire_protocol`, `auth`, `endpoint`, `model_grammar`, `default_model`, `retry`, `timeout`. Constructed only via preset classmethods (`LlmDeployment.openai(...)`, `.bedrock_claude(...)`, etc.) or a builder.

Providers become **presets** — classmethods over `LlmDeployment` (≤10 LOC each). Users write `LlmDeployment.bedrock_claude(region, AwsBearerToken.from_env())` not `LlmClient(provider='bedrock')`.

`LlmClient.from_deployment(deployment)` and `LlmClient.from_env()` are the primary constructors. `LlmClient()` zero-arg is introduced additively (it does NOT exist today).

## D-decisions (D1–D13)

Mirroring Rust ADR-0001 for traceability. Every D applies to Python unless annotated otherwise.

### Core architecture

- **D1** — Four-axis decomposition over provider-centric classes. ✅ Accepted.
- **D2** — `WireProtocol` shape: closed `enum.Enum` (NOT Protocol/ABC). Composition at `LlmDeployment` level.
- **D3** — `AuthStrategy` shape: `typing.Protocol` with `@runtime_checkable` so downstream callers can `isinstance(auth, AuthStrategy)` check. `Custom(inner: AuthStrategy)` wrapper emits WARN on construction (§6.7 threat).
- **D4** — `Endpoint` private attrs + constructor-only access via `Endpoint.from_url(url)`. `url_safety.check_url` is a structural gate (not aspiration). Frozen Pydantic model enforces at construction time.
- **D5** — `ModelGrammar` ownership: per-preset, not per-wire-protocol. Bedrock-Claude and Vertex-Claude share `AnthropicMessages` wire but differ in model ID translation.

### Back-compat against the Python REAL API

- **D6 (Python-rewritten)** — Back-compat covers today's Python public surface:
  - `kaizen.providers.registry.get_provider(name)` — preserved; returns today's provider class instance. Internals MAY route via `LlmClient.from_deployment(LlmDeployment.<preset>())`.
  - `kaizen.providers.registry.get_provider_for_model(model)` — preserved.
  - `kaizen.providers.registry.PROVIDERS` dict — additive only (no renames, no removals in v0).
  - `kaizen.config.providers.validate_*_config()` / `autoselect_provider()` — preserved; ordering preserved (OpenAI > Azure > Anthropic > Google).
  - Every concrete provider class (`OpenAIProvider`, `AnthropicProvider`, etc.) remains importable and functionally identical.
  - New symbols are ADDITIVE under `kailash.kaizen` top-level: `LlmClient`, `LlmDeployment`, `AwsBearerToken`, `AwsSigV4`, `GcpOauth`, `AzureEntra`, `ApiKeyBearer`, `StaticNone`.
  - **Zero breaking changes** for callers on today's provider registry API.

### Environment auto-detection

- **D7** — `LlmClient.from_env()` precedence identical to Rust:
  1. `KAILASH_LLM_DEPLOYMENT` URI (strict per-scheme grammar).
  2. `KAILASH_LLM_PROVIDER` selector + preset env keys.
  3. Legacy per-provider env keys (today's `autoselect_provider()` order preserved).
  4. `NoKeysConfigured` typed error. MUST NOT fall back to mock.
  - `AWS_BEARER_TOKEN_BEDROCK` + `BEDROCK_MODEL_ID` + `AWS_REGION` activate `bedrock_claude`. No default region.

### Observability

- **D8** — Every `LlmClient.complete` / `stream_completion` emits `llm.request.{start,ok,error}` with exact fields: `deployment_preset` (regex-validated `^[a-z][a-z0-9_]{0,31}$`), `wire_protocol`, `endpoint_host` (URL-encoded), `auth_strategy_kind` (NOT credential), `model_on_wire_id`, `request_id`, `latency_ms`, `upstream_status`, `error_class`. Credential-carrying headers masked BEFORE any logger sees the request (`observability.md` §6 uniform mask helper).

### Cross-SDK + deprecation

- **D9** — Cross-SDK: semantics MUST match Rust. S9 ships a parity test suite over preset names, env-precedence fixture, observability field-name snapshot, error-taxonomy enum equivalence.
- **D10** — Deprecation cadence: provider registry preserved through v2.x. v3.0 earliest removal. ≥ 18 months coexistence.

### Security hardening

- **D11** — Every public class private attrs + constructor-only invariant enforcement:
  - `Endpoint` frozen Pydantic with `Endpoint.from_url` as only constructor.
  - `AuthStrategy` has no `__repr__` that echoes credentials; `__repr__` uses `auth_strategy_kind()` only.
  - `AwsCredentials` uses `SecretStr` for `access_key_id`, `secret_access_key`, `session_token`. Custom `__repr__` redacts to fingerprint.
  - `AwsSigV4` rotation via `asyncio.Lock` guarding an immutable `AwsCredentials` slot. On upstream 403 `ExpiredTokenException`, `refresh()` re-reads the credential provider chain.
  - `AwsSigV4.sign_request` MUST route through `botocore.auth.SigV4Auth` (or equivalent AWS-maintained lib). Inlined HMAC signing is BLOCKED (grep-auditable).
  - `GcpOauth` / `AzureEntra` token caches use `asyncio.Lock` single-flight refresh.
  - `ResolvedModel.with_extra_header` deny-lists the 7 forbidden headers.
  - `ModelGrammar.resolve` validates `caller_model` against the regex before any parsing.
  - `LlmDeployment.mock()` gated behind `KAILASH_TEST_MODE=1` OR optional extra `kailash[test-utils]`. `from_env()` MUST NEVER return mock.
  - `ApiKey` newtype wraps `SecretStr`. No `__eq__` / `__hash__`. Only `ApiKey.constant_time_eq(other)` via `hmac.compare_digest`.
  - Region allowlist at `AwsBearerToken.__init__` / `AwsSigV4.__init__`. No default `AWS_REGION`.

### Capability axes

- **D12** — Explicitly out of four-axis scope: tool calling, vision, batch API, prompt caching, Assistants API, audio. Captured elsewhere (`CompletionRequest.attachments`, separate facades). Capability negotiation deferred.

### Migration window

- **D13** — Legacy provider registry + new deployment path coexist through v2.x. Dual-config emits WARN `llm_client.migration.legacy_and_deployment_both_configured` and deployment wins. Regression test `test_legacy_key_does_not_leak_into_deployment_path` asserts no credential cross-contamination.

## Sharding

See `01-shard-breakdown.md` for the full shard-by-shard implementation plan. Summary:

| Shard  | Scope                                               | LOC  | STP effect       |
| ------ | --------------------------------------------------- | ---- | ---------------- |
| S1+S2  | Foundation + OpenAI preset                          | ~700 | none             |
| S3     | Anthropic + Google + direct providers               | ~450 | none             |
| S4a    | AwsBearerToken + bedrock_claude                     | ~250 | **UNBLOCKED**    |
| S4b-i  | AwsSigV4 core + rotation                            | ~180 | —                |
| S4b-ii | 5-family Bedrock grammars                           | ~150 | —                |
| S4c    | LlmHttpClient + SafeDnsResolver + §6 security tests | ~250 | hardening        |
| S5     | GcpOauth + vertex_claude + vertex_gemini            | ~400 | —                |
| S6-i   | Azure api-key + workload identity + grammar         | ~200 | —                |
| S6-ii  | Azure managed identity + api-version + audience     | ~200 | —                |
| S7     | from_env richer config + migration isolation        | ~250 | ergonomic        |
| S8     | Plugin extensibility + sync client                  | ~200 | —                |
| S9     | Cross-SDK parity + docs + release notes             | ~350 | drift prevention |

**Total**: ~3,580 LOC across 8 sessions. S8 is Python-specific polish (Rust's S8 is binding surface work that is N/A in Python).

## Alternatives Considered

### Alternative A — Extend provider registry with a `family` field

Add a second dimension to each registry entry (e.g. `{name: 'bedrock_claude', family: 'aws', wire: 'anthropic'}`) without restructuring.

**Rejected.** Same failure mode as Rust's Alternative A. Adding a field doesn't decompose the axes — it just annotates them. Downstream callers still dispatch on `name`, and `bedrock_claude` remains a monolithic entry. Cross-SDK drift guaranteed because Rust and Python would describe the same concept with different shapes.

### Alternative B — Delegate to LiteLLM

Take a hard dep on LiteLLM as the provider layer.

**Rejected** (same reasons as Rust ADR). Violates `rules/dependencies.md` § "Own the Stack" for a load-bearing SDK surface. Cross-SDK parity broken — Rust SDK cannot depend on LiteLLM Python. Acceptable coexistence only as `LlmDeployment.litellm_proxy(base_url, api_key)` among many presets; not the primary path.

### Alternative C — Narrow-fix: add a `bedrock_claude` provider class beside `OpenAIProvider`

Add `BedrockClaudeProvider` to `kaizen/providers/llm/` as a sibling.

**Rejected.** Leaves the decomposition wrong. Every future cloud-hosted foundation model becomes a new adapter. Rust rejected the same pattern at kailash-rs#404; Python cannot diverge.

### Alternative D — Python-first shape (diverge from Rust)

Design a Python-native API that doesn't mirror Rust.

**Rejected.** Violates EATP D6. Code ported between SDKs would silently change behavior. Cross-SDK parity is the entire point of the `rules/cross-sdk-inspection.md` discipline.

## Consequences

### Positive

- Every future provider is a 3-line preset in Python, not a 500-LOC adapter.
- Enterprise deployments (Bedrock-Claude, Vertex-Claude, Azure-OpenAI, air-gapped vLLM, Groq, Together) become first-class via presets.
- Cross-SDK parity preserved by design — preset names, env precedence, observability fields, error taxonomy all identical.
- Security posture improved beyond today's state: private attrs, `SecretStr` wrapping, single-flight refresh, constant-time comparison, SigV4 via `botocore`, SSRF guard structural.
- STP unblocked at end of S4a (Bedrock bearer path functional).

### Negative

- ~3,580 LOC across 8 sessions (vs Alternative C's ~200 LOC one-shot). Justified by the Rust precedent and the 10-month+ maintenance savings on adapter-per-provider growth.
- Provider-registry semantics preserved means a shim layer exists through v2.x. Documentation must clearly mark which path is preferred for new code.
- Cloud-auth dependencies (`botocore`, `google-auth`, `azure-identity`) added as optional extras — new install-time surface area.
- Python's weaker zeroization (GC vs Rust's `zeroize` crate) is documented but unclosable without a Python-process-level primitive. Mitigation: `SecretStr` redaction + `ctypes.memset` on plaintext buffers where feasible.

### Risks

See `01-analysis/03-gaps-and-risks.md` for the full risk register. Highest-impact:

- R1: SigV4 signing drift → mitigated by mandatory `botocore` + AWS known-answer vectors.
- R5: SSRF via `openai_compatible` → mitigated by structural `Endpoint.from_url` + frozen Pydantic.
- R7/R8/R9: cross-SDK drift → mitigated by S9 parity suite and shared fixture files.
- R15: shard invariant overflow → mitigated by recommended splits (S4b-i/ii, S6-i/ii).

## Implementation Plan

Session 1: S1+S2 — Foundation + OpenAI. Existing OpenAI Tier 1/2 tests are the feedback loop.
Session 2: S3 — migrate remaining direct providers.
Session 3: S4a + S4b-i — **STP unblocked**.
Session 4: S4b-ii + S4c — security hardening.
Session 5: S5 — Vertex.
Session 6: S6-i + S6-ii — Azure.
Session 7: S7 + S8 — `from_env` + Python polish.
Session 8: S9 — parity + docs + release.

Every session runs `pytest --collect-only -q tests/unit tests/integration tests/regression` at end as merge gate (`rules/orphan-detection.md` §5).

## References

- Rust ADR-0001: `/Users/esperie/repos/loom/kailash-rs/workspaces/use-feedback-triage/02-plans/02-adrs/ADR-0001-llm-deployment-abstraction.md`
- Rust spec: `/Users/esperie/repos/loom/kailash-rs/specs/llm-deployments.md`
- Python spec (to be authored at S9): `specs/llm-deployments.md` (+ `specs/_index.md` entry)
- GH issues: `terrene-foundation/kailash-py#498`, `esperie-enterprise/kailash-rs#406`
- Reporter: `terrene-foundation/kailash-coc-claude-rs#52`
- Security foundation: `rules/security.md` § "Credential Decode Helpers", `rules/observability.md` § "Mask Helper Output Forms"
- Autonomous execution: `rules/autonomous-execution.md` § "Per-Session Capacity Budget"

## Status Log

- 2026-04-18 — Drafted during `/analyze` on workspaces/issue-498-llm-deployment/. Pending `/redteam` round and `/todos` gate.
