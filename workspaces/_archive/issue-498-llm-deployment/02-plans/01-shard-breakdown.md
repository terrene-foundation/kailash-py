# Shard Breakdown — Python Implementation Plan

Mirrors Rust S1–S9 with S8 elided (Python IS the binding surface).

## Conventions

- All paths relative to `/Users/esperie/repos/loom/kailash-py/`.
- Public symbols exported under `kailash.kaizen` (top) and `kaizen.llm` (submodule).
- Tier 2 test file naming per `rules/facade-manager-detection.md` §2: `tests/integration/test_<lowercase_manager>_wiring.py`.
- Each shard MUST carry cross-SDK parity assertions (S9 consolidates, individual shards seed).

## Legend

- **T1** = Tier 1 (unit, mocking allowed, <1s per test)
- **T2** = Tier 2 (integration, real infra / recorded cassette, no mocking)
- **Load-bearing LOC** excludes type scaffolding, DTOs, boilerplate.

---

## S1+S2 (Bundled) — Foundation + OpenAI Migration

**Describe:** Add `LlmDeployment`/`WireProtocol`/`Endpoint`/`AuthStrategy`/`ModelGrammar` types in `kaizen/llm/`, `url_safety.check_url()` SSRF guard, and migrate OpenAI to a preset.

### Files to create

- `packages/kailash-kaizen/src/kaizen/llm/deployment.py` — `LlmDeployment`, `WireProtocol` (enum), `Endpoint`, `ResolvedModel`, `EmbedOptions`, `CompletionRequest`, `StreamingConfig`, `RetryConfig`. Pydantic v2 frozen models.
- `packages/kailash-kaizen/src/kaizen/llm/auth/__init__.py` — `AuthStrategy` Protocol, `Custom`.
- `packages/kailash-kaizen/src/kaizen/llm/auth/bearer.py` — `StaticNone`, `ApiKeyBearer`, `ApiKeyHeaderKind` (closed enum).
- `packages/kailash-kaizen/src/kaizen/llm/client.py` — `LlmClient.from_deployment(...)`, `LlmClient()` zero-arg stub (preserves Python back-compat — though today no `LlmClient` class exists, creating it additively).
- `packages/kailash-kaizen/src/kaizen/llm/url_safety.py` — `check_url()`, private-range checks (IPv4+IPv6), cloud-metadata block, scheme allowlist.
- `packages/kailash-kaizen/src/kaizen/llm/errors.py` — full `LlmClientError` + `LlmError` + `AuthError` + `EndpointError` + `ModelGrammarError` taxonomy.
- `packages/kailash-kaizen/src/kaizen/llm/presets.py` — `LlmDeployment.openai(api_key=None)`, internal preset registry with regex-validated names.

### Files to modify

- `packages/kailash-kaizen/src/kaizen/llm/__init__.py` — export new symbols.
- `packages/kailash-kaizen/src/kaizen/providers/llm/openai.py` — thin adapter that delegates to `LlmDeployment.openai()` internally (keep public `OpenAIProvider` class for registry back-compat).
- `packages/kailash-kaizen/src/kaizen/providers/registry.py` — no API change; internals may route through new preset layer.
- `packages/kailash-kaizen/pyproject.toml` — no new deps.

### New public API

- `LlmClient.from_deployment(deployment: LlmDeployment) -> LlmClient`
- `LlmClient.from_env() -> LlmClient` (stub; full impl in S7)
- `LlmDeployment.openai(api_key: str | None = None, model: str | None = None) -> LlmDeployment`
- `LlmDeployment.mock()` (test-only — gated behind `KAILASH_TEST_MODE=1`)
- `AuthStrategy` Protocol: `apply(request)`, `auth_strategy_kind() -> str`, `async refresh() -> None`
- `ApiKeyBearer(key: str, header_kind: ApiKeyHeaderKind)`
- `Endpoint.from_url(url: str) -> Endpoint` (only constructor; runs SSRF check)
- `ResolvedModel.new(on_wire_id: str)`, `.with_path_suffix(...)`, `.with_extra_header(name, value) -> Self` (deny-list gate)

### Tests (T1)

- `tests/unit/llm/test_endpoint.py` — SSRF guard: private IPv4, private IPv6, metadata IPs, localhost, loopback literal, decimal-encoded IP, IPv4-mapped IPv6.
- `tests/unit/llm/test_apikey.py` — `ApiKey.constant_time_eq` via `hmac.compare_digest`; `ApiKey` has no `__eq__`; `repr(ApiKeyBearer(...))` contains no key bytes.
- `tests/unit/llm/test_resolved_model.py` — `with_extra_header` rejects `authorization`, `host`, `cookie`, `x-amz-security-token`, `x-api-key`, `x-goog-api-key`, `anthropic-version`.
- `tests/unit/llm/test_deployment_openai_preset.py` — `LlmDeployment.openai()` shape (wire=OpenAiChat, endpoint=api.openai.com, auth=ApiKeyBearer).
- `tests/unit/llm/test_errors_no_credential_leak.py` — `AuthError.Invalid(raw_key)` fingerprint is `sha256(raw)[:4]`, raw never in `str(err)`.

### Tests (T2)

- `tests/integration/llm/test_llmclient_openai_wiring.py` — `LlmClient.from_deployment(LlmDeployment.openai())` executes a real completion against `OPENAI_API_KEY` (cassette-gated).

### Invariants (4)

1. Private-field discipline on `Endpoint`, `LlmDeployment`, every auth class (validated via `__dataclass_fields__` / Pydantic `model_fields` and frozen=True).
2. AuthStrategy Protocol signatures match Rust trait byte-equivalent (names + arities).
3. Existing OpenAI provider tests pass unchanged.
4. SSRF guard rejects every private/metadata/loopback payload.

### Cross-SDK parity assertions

- `WireProtocol` members = Rust enum variants (string-compared).
- Preset name `"openai"` registered, regex-valid.

### Estimated load-bearing LOC: ~700 (edge of budget; feedback loop active)

### Depends on: none (seed shard)

---

## S3 — Migrate Anthropic + Google + direct providers

**Describe:** Move `AnthropicProvider`, `GoogleGeminiProvider`, `CohereProvider`, `MistralProvider`, `PerplexityProvider`, `OllamaProvider`, `DockerModelRunnerProvider`, `HuggingFaceProvider` onto preset-backed impls.

### Files to create

- `kaizen/llm/presets.py` — add `LlmDeployment.anthropic()`, `.google()`, `.mistral()`, `.cohere()`, `.perplexity()`, `.huggingface()`, `.ollama(base_url)`, `.docker_model_runner()`, `.groq()`, `.together()`, `.fireworks()`, `.openrouter()`, `.deepseek()`, `.lm_studio(base_url)`, `.llama_cpp(base_url)`.
- `kaizen/llm/wire_protocols/anthropic_messages.py`, `google_generate_content.py`, `cohere_generate.py`, `mistral_chat.py`, `ollama_native.py`, `huggingface_inference.py` — payload shapers + response parsers.

### Files to modify

- `packages/kailash-kaizen/src/kaizen/providers/llm/anthropic.py`, `google.py`, `perplexity.py`, `ollama.py`, `docker.py`, `mock.py` — thin adapters.
- `packages/kailash-kaizen/src/kaizen/providers/embedding/cohere.py`, `huggingface.py` — same.
- `packages/kailash-kaizen/src/kaizen/providers/registry.py` — no public API change.

### Tests (T1)

- `tests/unit/llm/presets/test_anthropic_preset.py`, `test_google_preset.py`, ... — one per preset, asserting (wire, endpoint, auth) tuple shape.

### Tests (T2)

- `tests/integration/llm/test_llmclient_anthropic_wiring.py` (cassette or live per `ANTHROPIC_API_KEY`).
- `tests/integration/llm/test_llmclient_google_wiring.py` (same for Gemini).
- Existing `tests/integration/nodes/ai/test_google_provider_integration.py` etc. stay green — no migration required for today's call sites.

### Invariants (3)

1. Every new preset registered with a regex-valid name matching Rust spec literal.
2. Wire-protocol parity: payload bytes produced by the Python wire-shaper match Rust output for identical input (captured snapshot test).
3. Today's provider-registry callers (39 files) compile and test unchanged.

### Cross-SDK parity assertions

- Presets `anthropic`, `google`, `mistral`, `cohere`, `perplexity`, `huggingface`, `ollama`, `groq`, `together`, `fireworks`, `openrouter`, `deepseek`, `lm_studio`, `llama_cpp`, `docker_model_runner` all registered.

### Estimated LOC: ~450

### Depends on: S1+S2

---

## S4a — AWS Bearer + Bedrock-Claude + Region Allowlist

**Describe:** `AwsBearerToken` auth + `LlmDeployment.bedrock_claude()` bearer-only preset + Bedrock-Claude model grammar + Tier 2 test. **STP unblocked.**

### Files to create

- `packages/kailash-kaizen/src/kaizen/llm/auth/aws.py` — `AwsBearerToken(token, region)`, `AwsBearerToken.from_env()`, `AwsCredentials` dataclass (SecretStr fields), `BEDROCK_SUPPORTED_REGIONS` constant.
- `packages/kailash-kaizen/src/kaizen/llm/grammar/bedrock.py` — `BedrockClaudeGrammar` with `resolve(caller_model)` regex gate + caller-model→on-wire translation.
- `tests/integration/llm/test_awsbearertoken_wiring.py` (facade naming).

### Files to modify

- `kaizen/llm/presets.py` — add `LlmDeployment.bedrock_claude(region, auth, model=None)`.
- `packages/kailash-kaizen/pyproject.toml` — add optional extra `bedrock = ["botocore>=1.34"]` (botocore is imported in S4b; S4a only imports nothing heavy, but pyproject landing here keeps the extras grouped).

### Tests (T1)

- `tests/unit/llm/auth/test_aws_bearer_token.py` — `from_env()` with `AWS_BEARER_TOKEN_BEDROCK` + `AWS_REGION` + `BEDROCK_MODEL_ID`. No default region. `RegionNotAllowed` on unknown.
- `tests/unit/llm/grammar/test_bedrock_grammar.py` — caller_model regex gate; `resolve("claude-sonnet-4-6")` → `"anthropic.claude-3-5-sonnet-20241022-v2:0"` mapping table.
- `tests/unit/llm/test_bedrock_claude_preset.py` — preset shape.
- `tests/unit/llm/test_llmclient_modelrequired_error.py` — `AWS_BEARER_TOKEN_BEDROCK` + `AWS_REGION` but no `BEDROCK_MODEL_ID` → `ModelRequired(deployment_preset="bedrock_claude")`.

### Tests (T2)

- `tests/integration/llm/test_awsbearertoken_wiring.py` — real Bedrock call gated on `AWS_BEARER_TOKEN_BEDROCK` presence; cassette fallback via `pytest-recording`.

### Invariants (5)

1. Bearer header application: `Authorization: Bearer <token>`.
2. Region allowlist: every Bedrock ctor validates region in constant.
3. Bedrock-Claude grammar: caller model regex-gated AND mapping table covers Claude 3, 3.5 Sonnet, 3 Haiku, 3 Opus, 3.5 Haiku.
4. Log field canonical form: `deployment_preset="bedrock_claude"`, `auth_strategy_kind="aws_bearer_token"`, `endpoint_host="bedrock-runtime.<region>.amazonaws.com"`.
5. `ModelRequired` typed error when model missing.

### Cross-SDK parity assertions

- Preset `bedrock_claude` registered.
- Region allowlist byte-identical to Rust constant.
- Auth strategy literal `aws_bearer_token` identical to Rust.

### Estimated LOC: ~250

### Depends on: S1+S2

---

## S4b — AWS SigV4 + 5-family Bedrock grammar + rotation

**Describe:** `AwsSigV4` via botocore + multi-family Bedrock grammars + atomic credential rotation.

### RECOMMENDED SPLIT (see 03-gaps-and-risks.md R15 — 6 invariants exceeds budget)

#### S4b-i — SigV4 core + rotation + Claude family

- Files: `kaizen/llm/auth/aws.py` extension (`AwsSigV4`, `AwsCredentials.rotate`), Bedrock-Claude grammar already lands in S4a.
- Deps: `botocore>=1.34` imported here (optional extra `bedrock`).
- Tests (T1): AWS known-answer vector suite for canonical-request + string-to-sign + signing-key + final-signature (GET+query, POST+JSON, multi-header, path-normalization, empty-query).
- Tests (T2): real Bedrock SigV4 call, cassette-recorded.
- Invariants (4): SigV4 canonicalization correctness, 5-min skew window, async-safe rotation via `asyncio.Lock`, streaming-hash (`aws-chunked`) for streaming calls.

#### S4b-ii — 5-family Bedrock grammars (Llama, Titan, Mistral, Cohere)

- Files: `kaizen/llm/grammar/bedrock.py` extension + per-family mapping tables.
- Tests (T1): grammar-per-family resolution tests.
- Invariants (2): every Bedrock family has a grammar; caller_model regex gate applied uniformly.

### Combined estimated LOC: ~300

### Depends on: S4a

---

## S4c — In-band error normalization + LlmHttpClient + security test suite

**Describe:** `LlmHttpClient` wrapper that structurally installs `SafeDnsResolver`; § 6 security tests land.

### Files to create

- `kaizen/llm/http_client.py` — `LlmHttpClient` wraps `httpx.AsyncClient` with custom resolver; the inner client is never exposed; only way to build an HTTP client for LLM calls.
- `kaizen/llm/safe_dns.py` — `SafeDnsResolver` pinning resolved IPs, validating at connect.
- `tests/unit/llm/security/` — every § 6 threat has a test file matching Rust spec §6.

### Files to modify

- `kaizen/llm/client.py` — every transport call routes through `LlmHttpClient`.

### Tests (T1)

- `test_endpoint_rejects_private_ip.py`, `test_endpoint_rejects_metadata_endpoint.py`, `test_endpoint_rejects_localhost_hostnames.py`, `test_llm_http_client_uses_safe_dns_resolver.py`, `test_auth_error_invalid_contains_only_fingerprint.py`, `test_upstream_error_body_scrubs_bearer_tokens.py`, `test_llm_request_log_masks_authorization_header.py`, `test_resolved_model_rejects_authorization_header.py`, `test_model_grammar_rejects_caller_model_with_crlf.py`, `test_custom_auth_strategy_construction_emits_warn.py`.
- `test_stream_in_band_error_normalized_to_llmerror.py` — AnthropicMessages-on-Bedrock first chunk MUST be valid start event; otherwise `LlmError.InBandError`.

### Invariants (4)

1. `LlmHttpClient` is the ONLY constructor path for LLM HTTP clients (grep-auditable).
2. `SafeDnsResolver` validates peer IP at socket connect (not just name lookup).
3. All § 6 tests land and pass.
4. In-band error policy applied consistently.

### Estimated LOC: ~250

### Depends on: S4b

---

## S5 — GCP OAuth + Vertex presets

**Describe:** `GcpOauth` with single-flight refresh + `LlmDeployment.vertex_claude()` + `vertex_gemini()` + grammars.

### Files to create

- `kaizen/llm/auth/gcp.py` — `GcpOauth` wrapping `google-auth`'s `Credentials.refresh`; `asyncio.Lock` single-flight.
- `kaizen/llm/grammar/vertex.py` — Vertex-Claude + Vertex-Gemini grammars.
- `tests/integration/llm/test_gcpoauth_wiring.py`.

### Files to modify

- `kaizen/llm/presets.py` — add `vertex_claude`, `vertex_gemini`.
- `pyproject.toml` — `vertex = ["google-auth>=2.0"]` optional extra.

### Tests (T1)

- `test_gcp_oauth_concurrent_refresh_single_flight.py` — 20 concurrent callers → 1 refresh.
- `test_vertex_claude_grammar.py`, `test_vertex_gemini_grammar.py`.
- `test_vertex_project_id_regex.py` — project ID validation.

### Tests (T2)

- `tests/integration/llm/test_gcpoauth_wiring.py` — gated on `GOOGLE_APPLICATION_CREDENTIALS`.

### Invariants (5): GCP OAuth concurrency safety, Vertex-Claude grammar, Vertex-Gemini grammar, project/region validation, `asyncio.Lock` single-flight.

### Estimated LOC: ~400

### Depends on: S4c

---

## S6 — Azure Entra + Azure OpenAI preset

**Describe:** `AzureEntra` (api-key + workload-identity + managed-identity) + `LlmDeployment.azure_openai()`.

### RECOMMENDED SPLIT (R15 — 6 invariants)

#### S6-i — api-key variant + workload identity + Azure grammar

- Files: `kaizen/llm/auth/azure.py` (partial), `kaizen/llm/grammar/azure_openai.py`.
- Deps: `azure-identity>=1.15` optional extra.
- Invariants (3): api-key variant, workload-identity variant, Azure deployment-ID grammar.

#### S6-ii — managed identity + api-version + audience scope

- Files: `kaizen/llm/auth/azure.py` (completion).
- Invariants (3): managed-identity variant, api-version handling, Entra audience scope.

### Combined estimated LOC: ~400

### Depends on: S5

---

## S7 — from_env Richer Config + Migration-Window Isolation

**Describe:** `LlmClient.from_env()` full implementation — URI > selector > legacy. Migration-window guard prevents cross-contamination.

### Files to create

- `kaizen/llm/from_env.py` — URI parser (strict per-scheme grammar), selector reader, legacy-key detector, multi-deployment builder, migration-window isolation guard.

### Files to modify

- `kaizen/llm/client.py` — `LlmClient.from_env()` delegates to `from_env.py`.
- `kaizen/config/providers.py` — `autoselect_provider()` internally routes through `LlmClient.from_env()`'s legacy tier (back-compat preservation).

### Tests (T1)

- `test_from_env_uri_bedrock_claude.py`, `test_from_env_uri_vertex_claude.py`, `test_from_env_uri_azure_openai.py`, `test_from_env_uri_openai_compatible.py`, `test_from_env_uri_rejects_attacker_host_in_region_field.py`.
- `test_from_env_selector_kailash_llm_provider.py`.
- `test_from_env_legacy_openai_only.py`, `test_from_env_legacy_multiple.py`, `test_from_env_legacy_ordering.py` — asserts OpenAI > Azure > Anthropic > Google.
- `test_from_env_no_keys_raises_noconfigured.py`, `test_from_env_never_returns_mock.py`.
- `test_legacy_key_does_not_leak_into_deployment_path.py` — both configured → WARN + deployment wins.

### Invariants (4)

1. URI scheme grammar strict (region regex, project regex, resource regex).
2. Selector tier maps name → preset via regex-validated registry.
3. Legacy tier preserves today's `autoselect_provider()` ordering.
4. Migration-window isolation guard: dual-config emits WARN and picks deployment.

### Cross-SDK parity assertions

- `from_env` precedence matrix byte-identical to Rust. Shared fixture file.

### Estimated LOC: ~250

### Depends on: S6

---

## S8 — (Python-specific: ergonomics + plugin extensibility)

**Describe:** Python IS the binding surface. Repurpose Rust's S8 budget for Python-specific polish: `LlmDeployment` plugin hook for third-party presets, `asyncio` + `threading` parity smoke tests, sync-variant `LlmClient.from_deployment_sync()`.

### Files to create

- `kaizen/llm/plugin.py` — `register_preset(name, factory)` for third-party presets (still goes through preset-name regex + SSRF on endpoint).
- `kaizen/llm/sync_client.py` — sync-variant via `asyncio.run` wrappers.

### Tests (T1)

- `test_plugin_preset_name_regex_enforced.py`.
- `test_plugin_preset_endpoint_ssrf_gated.py`.
- `test_sync_client_parity.py` — sync methods produce identical output to async.

### Invariants (3): plugin regex gate, plugin SSRF gate, sync/async parity.

### Estimated LOC: ~200

### Depends on: S7

### Collapsing-into-S9 option: if budget permits, S8 can be merged into S9.

---

## S9 — Cross-SDK Parity Suite + Docs + Release Notes

**Describe:** Ship the parity test suite, migration guide, `specs/llm-deployments.md` Python spec, release notes, and the loom rules authored in Rust S9 (adapted to Python variant if needed).

### Files to create

- `tests/cross_sdk_parity/test_preset_names_match_rust.py` — imports from a shared fixture checked into both repos.
- `tests/cross_sdk_parity/test_from_env_precedence_matches_rust.py`.
- `tests/cross_sdk_parity/test_observability_field_names_match_rust.py`.
- `tests/cross_sdk_parity/test_error_taxonomy_matches_rust.py`.
- `specs/llm-deployments.md` — Python spec file (Python-oriented synthesis from Rust spec); `specs/_index.md` updated.
- `docs/migration/llm-deployments-v2.md` — migration guide for callers of the provider registry.
- `packages/kailash-kaizen/CHANGELOG.md` entry for v0 release.

### Files to modify

- `specs/_index.md` — add `llm-deployments.md` entry under Kaizen section.

### Tests (T2): cassette-recorded cross-SDK parity snapshots.

### Invariants (3)

1. Cross-SDK parity suite green against current Rust preset registry.
2. `specs/llm-deployments.md` ≤300 LOC (per `rules/specs-authority.md` §8); split into sub-files if larger.
3. Migration guide covers every symbol today's callers import.

### Estimated LOC: ~350

### Depends on: S8 (or S7 if S8 collapsed)

---

## Dependency Graph

```
S1+S2 (seed)
   │
   ├──> S3
   │     │
   └─────┴──> S4a
                │
                └──> S4b (→ S4b-i + S4b-ii)
                       │
                       └──> S4c
                              │
                              └──> S5
                                    │
                                    └──> S6 (→ S6-i + S6-ii)
                                          │
                                          └──> S7
                                                │
                                                └──> S8
                                                      │
                                                      └──> S9
```

**STP unblocked at end of S4a** (Bedrock-Claude bearer-only path functional).

## Session Plan (per rules/autonomous-execution.md)

| Session | Shards       | LOC  | STP effect                       |
| ------- | ------------ | ---- | -------------------------------- |
| 1       | S1+S2        | ~700 | none                             |
| 2       | S3           | ~450 | none                             |
| 3       | S4a + S4b-i  | ~430 | **STP UNBLOCKED**                |
| 4       | S4b-ii + S4c | ~400 | security hardening               |
| 5       | S5           | ~400 | Vertex presets                   |
| 6       | S6-i + S6-ii | ~400 | Azure presets                    |
| 7       | S7 + S8      | ~450 | from_env complete; Python polish |
| 8       | S9           | ~350 | parity + docs + release          |

**Total:** ~3,580 LOC across 8 sessions. Matches Rust's ~3,650 LOC / 5 sessions but with more shards (Python has finer invariant boundaries around async-primitive complexity in auth shards).

## Global Invariants Across All Shards

- Every shard MUST carry a facade-manager wiring test (`rules/facade-manager-detection.md` §1).
- Every new public attribute on `LlmClient`/`LlmDeployment` that returns a `*Manager`/`*Executor`/`*Store`/`*Registry`/`*Engine`/`*Service` MUST have a production call site in the same PR (`rules/orphan-detection.md` §1).
- Every new security threat documented MUST have a matching `test_<threat>` function (`rules/testing.md` § "Verify security mitigations have tests").
- Every shard MUST run `pytest --collect-only -q` successfully across `tests/unit tests/integration tests/regression` (orphan-detection §5).
- Every shard MUST NOT introduce `except Exception: continue` without a WARN log (observability.md §7).
- Credential comparisons use `hmac.compare_digest` only (no `==` on `ApiKey`).
