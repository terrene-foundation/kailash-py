# Gaps and Risks

## 1. Risk Register

| #   | Risk                                                     | Likelihood | Impact   | Mitigation                                                                                                                                                                                                                                                                        |
| --- | -------------------------------------------------------- | ---------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | SigV4 signing drift (inlined HMAC attempt by impl agent) | M          | Critical | MUST route through `botocore.auth.SigV4Auth`. AWS known-answer vectors as Tier 1. Grep-audit forbids `hmac.new` in `kaizen/llm/auth/aws.py`.                                                                                                                                      |
| R2  | AWS credential expiry silent failure                     | M          | High     | `AwsSigV4.refresh()` triggered on 403 `ExpiredTokenException`. Single-flight via `asyncio.Lock`. Tier 2 test forces expiry, asserts re-sign.                                                                                                                                      |
| R3  | GCP OAuth token cache thundering herd                    | H          | Medium   | Single-flight `asyncio.Lock` per deployment instance. Tier 2 test spawns N concurrent callers, asserts 1 refresh call.                                                                                                                                                            |
| R4  | Azure Entra token rotation gap                           | M          | High     | Same single-flight pattern; gate auth variants behind feature flag until workload-identity landscape stable.                                                                                                                                                                      |
| R5  | SSRF via `openai_compatible(base_url)`                   | H          | Critical | `Endpoint.from_url()` only; `url_safety.check_url`. Private IP / loopback / link-local / metadata rejection. Compile-time impossibility of bypass via private fields + frozen dataclass.                                                                                          |
| R6  | DNS rebinding — URL resolves private at connect time     | M          | Critical | `SafeDnsResolver` pattern (resolve pin, validate at socket.connect). Must land in S4c alongside `LlmHttpClient`.                                                                                                                                                                  |
| R7  | Preset name drift vs Rust                                | H          | High     | Cross-SDK parity test suite (S9) asserts every preset name byte-identical; CI job runs against Rust preset registry export.                                                                                                                                                       |
| R8  | `from_env` precedence drift vs Rust                      | H          | High     | S7 lands matrix test: for each of {URI, selector, legacy, none} × {one, many, ambiguous} input combos, assert identical deployment is chosen vs Rust fixture.                                                                                                                     |
| R9  | Observability field name drift                           | H          | Medium   | Shared fixture file (`specs/llm-deployments.md` §7 snapshot) asserted by Tier 1 in both SDKs. Field names literal: `deployment_preset`, `wire_protocol`, `endpoint_host`, `auth_strategy_kind`, `model_on_wire_id`, `request_id`, `latency_ms`, `upstream_status`, `error_class`. |
| R10 | Mock deployment selected in prod                         | L          | Critical | `LlmDeployment.mock()` gated behind `kailash[test-utils]` extra OR `KAILASH_TEST_MODE=1`; `from_env()` MUST raise `NoKeysConfigured` rather than fall back.                                                                                                                       |
| R11 | Back-compat break of `kaizen.providers.registry` callers | M          | High     | S2/S3 SHIM the registry as a lazy adapter over presets; registry public API byte-frozen. Collect-only gate per `rules/orphan-detection.md` §5.                                                                                                                                    |
| R12 | Secret leakage in Python `__repr__`                      | H          | High     | `SecretStr` + custom `__repr__` on every auth class. Tier 1 test: `repr(auth)` never contains the raw key.                                                                                                                                                                        |
| R13 | Credential fingerprint echoes raw input                  | M          | Medium   | `AuthError.Invalid.fingerprint` = `sha256(raw)[:4]`. NEVER log the raw input even truncated. Tier 1 test.                                                                                                                                                                         |
| R14 | Model-grammar header injection via `caller_model`        | M          | High     | Regex gate `^[a-zA-Z0-9._:/@-]{1,256}$`. `ResolvedModel.with_extra_header` deny-list. Tier 1 fuzz test (CRLF, spaces, header-like strings).                                                                                                                                       |
| R15 | Shard scope overflow (per-session capacity)              | H          | Medium   | See §3 below — S1+S2 bundled is ~700 LOC at edge of budget; S4b may overflow invariants (SigV4 canonicalization + 5-family grammar + rotation + known-answer vectors = 4 load-bearing). Recommend sharding S4b into S4b-i (SigV4 + 1 family) + S4b-ii (5-family grammar).         |
| R16 | Python secret zeroization weaker than Rust               | M          | Low      | Python GC can't guarantee zeroization. Document the gap; use `ctypes.memset` on plaintext bytes where feasible; rely on `SecretStr` redaction as primary control. Low impact — process memory exposure requires co-resident attacker.                                             |
| R17 | Custom `AuthStrategy` contract enforcement               | M          | Medium   | `Custom.__init__` WARN log. `rules/llm-auth-strategy-hygiene.md` authored at S9. Runtime cannot enforce "don't log credentials" — documented contract only.                                                                                                                       |
| R18 | Tier 2 infrastructure cost (real Bedrock/Vertex/Azure)   | H          | Low      | Tier 2 gated on env creds; CI job optional; use VCR.py / `pytest-recording` cassette for repeatable runs; real infra Tier 2 runs nightly, not per-PR.                                                                                                                             |
| R19 | Legacy + deployment dual-config cross-contamination      | M          | High     | S7 lands `test_legacy_key_does_not_leak_into_deployment_path`. WARN `llm_client.migration.legacy_and_deployment_both_configured` on dual config.                                                                                                                                  |
| R20 | Pydantic v2 `frozen=True` + `SecretStr` ergonomics       | L          | Low      | Validated in S1+S2 prototype. Fallback: use `dataclasses.dataclass(frozen=True, slots=True)` with manual secret-redacting `__repr__`.                                                                                                                                             |

## 2. Per-Auth-Method Security Deep Dive

### 2.1 AWS (Bedrock)

- **Bearer token expiry** (`AWS_BEARER_TOKEN_BEDROCK`): AWS-issued short-lived bearer tokens. On 403, re-read env; if env token is also stale, raise `AuthError.ExpiredRefreshRequired` — caller must rotate the token externally. **No automatic token issuance** (Python does not call STS here; that is `AwsSigV4`'s job).
- **SigV4 credential chain**: must follow the AWS credential provider chain (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` env → `~/.aws/credentials` profile → EC2/ECS IMDS → IRSA/Web Identity). Each hop has different expiry semantics. botocore handles this; do NOT re-implement.
- **Region allowlist**: Bedrock region set is operational truth (AWS adds/removes regions). Hardcode the v0 set; make it extensible via `BEDROCK_SUPPORTED_REGIONS` env override for Foundation-internal testing only (document the override is not for production).

### 2.2 GCP (Vertex)

- **Service account JSON** — file or `GOOGLE_APPLICATION_CREDENTIALS` env pointing at JSON. `google-auth` library handles ADC (application default credentials), workload identity, user creds.
- **Token refresh cadence**: 1h default. Single-flight refresh via `asyncio.Lock`; N callers → 1 refresh. Test: spawn 20 concurrent `complete()` calls across expired boundary, count `refresh()` invocations = 1.
- **Project+region injection**: project ID and region ARE used to compose the endpoint. Grammar-injection risk: validate project ID against `^[a-z][-a-z0-9]{4,28}[a-z0-9]$` (GCP project ID rules).

### 2.3 Azure (Entra)

- **Api-key path** (legacy, today's `AZURE_OPENAI_API_KEY`) — `api-key: <KEY>` header.
- **Workload Identity path** — AKS + federated credentials; `azure-identity.DefaultAzureCredential` walks the chain. Uses `Authorization: Bearer <entra-token>`.
- **Managed Identity path** — VM/container system-assigned or user-assigned.
- **Token cache**: Entra tokens ~1h expiry; `DefaultAzureCredential` caches internally BUT we wrap it in our own `CachedToken` so refresh timing is testable and single-flight.
- **Tenant+resource binding**: Entra tokens are audience-scoped. Audience for Azure OpenAI = `https://cognitiveservices.azure.com/.default`. Hardcode; document the audience contract.

## 3. Per-Session Capacity (rules/autonomous-execution.md)

Each shard MUST stay within: ≤500 LOC load-bearing, ≤5-10 invariants, ≤3-4 call-graph hops, 3-sentence describable.

| Shard                | LOC  | Invariants                                                                                                                                                         | Verdict                                                                                                                                                                                                                                                    |
| -------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1+S2 (bundled)      | ~700 | 4: private-field discipline, trait/Protocol signatures, OpenAI wire parity, SSRF guard                                                                             | **At edge — acceptable** because feedback loop is live (pytest-asyncio + existing OpenAI Tier 1/2 tests fire during session) and most LOC is type-scaffolding not state-holding logic.                                                                     |
| S3                   | ~450 | 3: Anthropic wire parity, Google wire parity, preset-backed registry shim preserves today's tests                                                                  | **Within**                                                                                                                                                                                                                                                 |
| S4a                  | ~250 | 5: bearer-header application, region allowlist, Bedrock-Claude grammar, log field canonical form, `BEDROCK_MODEL_ID` required-error taxonomy                       | **Within**                                                                                                                                                                                                                                                 |
| S4b                  | ~300 | 6: SigV4 canonicalization correctness, 5-family Bedrock grammar, `ArcSwap`→`asyncio.Lock` rotation, skew-window, streaming-hash support, known-answer vector suite | **Edge — recommend split** into S4b-i (SigV4 core + Claude grammar + rotation, ~180 LOC, 4 invariants) and S4b-ii (Llama/Titan/Mistral/Cohere Bedrock grammars + known-answer vectors, ~150 LOC, 2 invariants).                                            |
| S4c                  | ~250 | 4: in-band error normalization, `LlmHttpClient` + `SafeDnsResolver` structural install, § 6 security test suite landing, DNS guard behavior                        | **Within**                                                                                                                                                                                                                                                 |
| S5                   | ~400 | 5: `GcpOauth` concurrency safety, Vertex-Claude grammar, Vertex-Gemini grammar, project/region validation, single-flight refresh                                   | **Within**                                                                                                                                                                                                                                                 |
| S6                   | ~400 | 6: `AzureEntra` api-key variant, workload-identity variant, managed-identity variant, Azure OpenAI deployment-ID grammar, api-version handling, audience-scope     | **Edge — recommend split** into S6-i (api-key + workload identity + grammar, 3 invariants) and S6-ii (managed identity + api-version + audience, 3 invariants).                                                                                            |
| S7                   | ~250 | 4: URI-scheme grammar parser, selector tier, legacy tier, migration-window isolation test                                                                          | **Within**                                                                                                                                                                                                                                                 |
| S8 (Python-specific) | 0    | —                                                                                                                                                                  | **N/A** — Python IS the binding surface; no FFI layer. S8's Rust workload is absent in Python; repurpose S8 budget into a **"Python ergonomics"** shard if needed (e.g. `LlmDeployment` subclass hooks for plugin presets). Can also be collapsed into S9. |
| S9                   | ~350 | 3: cross-SDK parity test suite, docs update, migration guide                                                                                                       | **Within**                                                                                                                                                                                                                                                 |

**Total sessions (with recommended splits):** 9 sessions vs Rust's ~5 sessions. Python comes in lower because no FFI work but higher because Python's cryptographic primitives surface more invariants in auth shards (async locks vs arc-swap, SecretStr vs Zeroize).

## 4. Cross-SDK Semantic Drift Risks

- **Preset names** — drift vector: Python impl adds a `gemini` alias not in Rust. Mitigation: preset registry in Python MUST import literal from a shared fixture; parity test imports Rust's exported preset names and asserts identity.
- **`from_env` precedence** — drift vector: Python prioritizes selector over URI by mistake. Mitigation: matrix-based test imports a shared fixture (`tests/shared/from_env_fixtures.json` mirrored in both SDKs).
- **Observability fields** — drift vector: Python impl renames `endpoint_host` → `endpoint`. Mitigation: S9 ships a JSON snapshot of required field names; Tier 1 test asserts `set(log_fields) == set(snapshot_fields)`.
- **Error taxonomy** — drift vector: Python adds a variant absent in Rust (e.g. `InvalidPydantic`). Mitigation: base exceptions documented in spec §4.8; parity test asserts enum/class equivalence.
- **Region allowlist** — drift vector: Python list includes a region Rust removed. Mitigation: shared constants file; CI cross-SDK parity job fails on diff.

## 5. Back-Compat Risks

- **`kaizen.providers.registry.get_provider('azure')` returning a different class** — today it lazy-resolves to `UnifiedAzureProvider`. S6 MUST keep this alias working; introduce `azure_openai` as a separate preset that wraps the same underlying functionality with the new abstraction.
- **`kaizen.config.providers.autoselect_provider()` ordering** — today: OpenAI > Azure > Anthropic > Google. `LlmClient.from_env()` legacy tier MUST preserve this order exactly (test asserts).
- **Model prefix-dispatch `_MODEL_PREFIX_MAP`** — today's structural SPEC-02 table. New abstraction: `LlmDeployment.default_model` + explicit `deployment_id` selection at call site means the prefix table becomes routing-only, not dispatch. Preserve for legacy callers; new callers opt into explicit deployment.
- **Agents consuming providers** — 39 files import from `kaizen.providers.*`. NONE should break. S2/S3 registry shim is the compatibility layer.

## 6. SSRF + DNS-Rebinding Details

### SSRF (S1+S2 lands `url_safety.check_url`)

Reject schemes ∉ {http, https}. Reject hosts matching:

- IPv4 private ranges: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `169.254.0.0/16` (link-local + metadata).
- IPv6 equivalents: `::1/128`, `fe80::/10`, `fc00::/7`.
- Cloud metadata hostnames: `metadata.google.internal`, `metadata.azure.com`, `169.254.169.254`, `fd00:ec2::254`.
- Localhost literals: `localhost`, `*.localhost`, `*.local`, `*.internal`.

Testing MUST include: raw IPv4, IPv4 encoded decimal (`2130706433`), IPv4 encoded octal (`0177.0.0.1`), IPv6 compressed (`::ffff:127.0.0.1`), hostname that resolves to private IP.

### DNS rebinding (S4c lands `SafeDnsResolver`)

- Resolve hostname ONCE at `Endpoint.from_url()` time.
- Pin the resolved IP set; every subsequent TCP connect validates `socket.getpeername()` IP is in the pinned set.
- Re-pin after explicit `Endpoint.refresh_dns()` (operator-initiated). No automatic re-pinning.

Python-specific challenge: `httpx` / `aiohttp` do DNS per-connect. Solution: pass a custom `resolver=SafeDnsResolver(pinned_ips)` on client construction, or build a `transport=` adapter that checks the post-connect peer address.

## 7. Tier 2 Test Infrastructure

| Preset              | Real infra cost                                 | Alternative                                             |
| ------------------- | ----------------------------------------------- | ------------------------------------------------------- |
| `openai`            | low (existing OPENAI_API_KEY)                   | cassette                                                |
| `anthropic`         | low                                             | cassette                                                |
| `bedrock_claude`    | medium (AWS account + Bedrock enabled + region) | cassette + `moto` mock for SigV4 roundtrip validation   |
| `vertex_claude`     | medium (GCP project + Vertex enabled)           | cassette + `google-auth` mock credentials               |
| `azure_openai`      | medium (Azure resource + deployment)            | cassette + `azure-identity` DefaultAzureCredential mock |
| `openai_compatible` | low (local vLLM/ollama for SSRF+DNS tests)      | real local server + block-list IP pins                  |
| `mock`              | zero                                            | deterministic                                           |

**Recommendation:** Tier 2 runs against cassettes in CI (deterministic, no cost, no creds leakage). Real-infra Tier 2 runs in a nightly job with env-gated credentials. `rules/testing.md` Tier 2 says "real infrastructure recommended" — cassettes recorded against real infra satisfy the spirit; document this classification in `rules/testing.md` for LLM tier.

## 8. Shards That Have NO Executable Feedback Loop

Per autonomous-execution.md rule "Feedback Loops Multiply Capacity" — shards without a live loop use base budget.

- **S9 (docs + rules + cross-SDK ticket)** — documentation-only, no compile loop. Base budget applies.
- **S7 `from_env` precedence tests** — tests ARE the feedback loop. 3-5x multiplier applies.

All auth-adding shards (S4a, S4b, S5, S6) have live Tier 1 feedback loops (known-answer vectors, unit tests). S1+S2 has live loop via existing provider Tier 1 tests + new `Endpoint.from_url` tests.

## 9. Unmapped Failure Modes (Known Gaps)

- **Streaming in-band errors for Vertex / Azure** — Rust spec pins the AnthropicMessages-on-Bedrock case (S-M8). Vertex streaming + Azure streaming may have similar patterns (200 OK + error JSON in first chunk). S5/S6 MUST extend `StreamErrorPolicy.NormalizeInBandErrors` to their wire protocols.
- **Retry-After semantics across providers** — OpenAI returns `retry-after: <seconds>`; Anthropic returns `retry-after: <HTTP-date>`. `RetryConfig` MUST parse both; Rust spec assumes both work. Add Tier 1 test.
- **Request body size limits** — Bedrock has ~6MB limit; Vertex has different limits; not covered by four-axis abstraction. Document as out-of-scope for v0 but track for S9 docs.
- **Region-sharding for stream-hash** — SigV4 streaming (`aws-chunked`) has per-region behavior quirks. S4b known-answer vectors MUST cover at least 2 regions.

## 10. BLOCKING Gaps (per brief success criteria)

None identified. All brief success criteria map to a shard + a spec section. See `04-brief-traceability.md`.
