# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased — issue-603]

### Added

- **`BudgetTracker.set_threshold_callback(threshold_pct, callback)`** at `src/kailash/trust/constraints/budget_tracker.py` — public API for registering a one-shot callback that fires when budget utilization first reaches a caller-supplied fraction of allocated budget. Distinct from the existing `on_threshold()` (which fires only at hardcoded 80/95/100% marks). Callback fires when `(committed + reserved) / allocated >= threshold_pct` after a successful `reserve()` or `record()` call. Multiple callbacks may be registered at the same threshold (registration order preserved); each (threshold, handle) fires AT MOST ONCE per BudgetTracker instance. Returns an integer handle for symmetric removal via `unregister_threshold_callback(handle)`. Thread-safe under existing `self._lock`; predicate evaluated under lock, callbacks dispatched outside the lock to prevent re-entrancy deadlock. Callback exceptions are logged at WARNING via `logger.exception` and never propagate to `record()`/`reserve()` callers. Motivation: Envoy Phase 01 Grant Moment trigger — operator wires "you've used 80% of your budget" notification to drive escalation. Cross-SDK alignment with `kailash-rs#30`.
- **`BudgetEvent` payload extended** with optional `threshold_pct: Optional[float]`, `committed_microdollars: Optional[int]`, `reserved_microdollars: Optional[int]` fields. Custom-threshold events carry the registered fraction; legacy `threshold_80` / `threshold_95` / `exhausted` events now also carry their corresponding fraction (0.80 / 0.95 / 1.00) for cross-callback uniformity. `to_dict()` / `from_dict()` are backward-compatible — older payloads without these keys deserialize cleanly with the new fields set to `None`.
- **Tier 1 unit tests** at `tests/trust/unit/test_budget_tracker_callbacks.py` (27 tests) covering happy path, registration order, multi-threshold ordering, exception isolation, once-only firing, threshold-pct validation (NaN/Inf/0/1/boundary), claimed-amount predicate, unregister semantics, allocated-zero edge case, and `_max_callbacks` limit.
- **Tier 2 integration tests** at `tests/trust/integration/test_budget_tracker_callbacks.py` (5 tests) exercising callback dispatch under concurrent `reserve()`/`record()` workers (16-thread + 50-thread scenarios), callback-exception isolation under load, multi-threshold independence under load, and end-to-end Grant Moment scenario. NO mocking — all tests use real `threading` primitives.

### Related

- Cross-SDK: `esperie/kailash-rs#30` (Rust `BudgetTracker::set_threshold_callback`).

## Note: Changelog Reorganized

The changelog has been reorganized into individual files for better management. Please see:

- **[sdk-users/6-reference/changelogs/](sdk-users/6-reference/changelogs/)** - Main changelog directory
- **[sdk-users/6-reference/changelogs/unreleased/](sdk-users/6-reference/changelogs/unreleased/)** - Unreleased changes
- **[sdk-users/6-reference/changelogs/releases/](sdk-users/6-reference/changelogs/releases/)** - Individual release changelogs

## Recent Releases

### kailash 2.9.2 — 2026-04-25 — 1.1.2 patch wave (docstring + cross-SDK)

**Docstring + docstring-only changes** — no behavior change in `src/kailash/`. Ships alongside `kailash-dataflow 2.2.0` (public API expose, #601) + `kailash-kaizen 2.12.3` (security sweep, #614 + #617).

**Changed**

- **`fingerprint_secret` docstring enhancement** (#617 MEDIUM-2) at `src/kailash/utils/url_credentials.py`. Added caveat section naming: (a) fingerprints are collision-stable across installs intentionally (cross-node trace correlation requirement); (b) MUST NOT be treated as per-tenant-unique identifiers; (c) MUST NOT be treated as secrets (not keyed; anyone with plaintext reproduces the fingerprint). No behavior change.
- **`cascade_revoke` cross-SDK parity docstring** (#595) at `src/kailash/trust/revocation/cascade.py`. Added § "Cross-SDK parity (EATP D6)" clause pinning: Python BFS and Rust DFS produce identical SET of revoked descendants for any delegation tree (result set is order-independent; only event emission order may differ). Consumers MUST NOT rely on event ordering for cross-SDK correlation. Regression test: `tests/regression/test_issue_595_cascade_revocation_cross_sdk_parity.py` (6 tests: linear / binary-tree / star / diamond / order-invariant / idempotent-re-revoke).

### kailash 2.9.1 — 2026-04-24 — Security patch (issue #613)

**CodeQL security patch** — closes all HIGH findings from PR #611 scan across three rule classes (`py/clear-text-logging-sensitive-data`, `py/incomplete-url-substring-sanitization`, `py/weak-sensitive-data-hashing`). Scope grew mid-review: reviewer flagged a sibling `mysql.py:105-107` site (same bug class as postgresql.py) that the initial scan did not surface; closed in the same PR per `rules/agents.md` fix-immediately. Ships as part of the 1.1.x post-M1 security patch wave.

**Fixed**

- **`trust.auth.jwt` issuer validation** (`py/incomplete-url-substring-sanitization`) — replaced `"github.com" in issuer_lower` substring-match with `urlparse(issuer).hostname` hostname-equality/suffix check against a trusted-hosts allowlist. Blocks `evilgithub.com`-style spoofs. Added GitHub Actions OIDC + Azure v1.0 issuers; non-URL issuers fall through to `"local"` (fail-closed). Regression test: `tests/trust/unit/test_jwt_issuer_hostname_validation.py`.

**Added**

- **`kailash.utils.url_credentials.fingerprint_secret(value, *, length=8)`** — BLAKE2b short-form fingerprint helper for grep-able correlation of secrets in `__repr__` / log lines. Defense-in-depth only; NOT a password-hashing primitive. CodeQL `py/weak-sensitive-data-hashing` flags `hashlib.sha256(secret)` at correlation sites; BLAKE2b is neither flagged nor password-appropriate — exactly the contract correlation sites need. Consumed by kaizen 2.12.1 and mcp 0.2.9 in the same patch wave.

### kailash 2.9.0 — 2026-04-23 — ML integration foundations (W31.a + W31.d)

**Ships the kailash-core pieces of the kailash-ml 1.0.0 wave.** Per `specs/kailash-core-ml-integration.md`, 2.9.0 adds:

**New surfaces**

- **`kailash.diagnostics.protocols`** expansion:
  - `RLDiagnostic` Protocol (`record_episode`, `record_eval`, `record_policy_step`) — shared by classical RL (SB3/d3rlpy) and RLHF (kailash-align) metric emitters. Conformance is structural; an implementation satisfying both `Diagnostic` and the three `record_*` methods satisfies `RLDiagnostic` at runtime via `isinstance(..., RLDiagnostic)`.
  - `DiagnosticReport` frozen dataclass with `{schema_version: "1.0", events, summary, rollup, tenant_id, actor_id}`. `schema_version` is a `Literal["1.0"]` — a 2.0 bump requires a new literal plus forward-compat shims. Round-trip via `to_dict()` / `from_dict()` preserves byte shape.
- **`kailash.workflow.nodes.ml`** — three string-name-addressable workflow nodes:
  - `MLTrainingNode` — train via a kailash-ml engine; required params `engine`, `schema`, `model_spec`, `eval_spec`, `tenant_id`, `actor_id`; emits `kailash_ml_train_duration_seconds` at end of run.
  - `MLInferenceNode` — run batch inference via the InferenceServer; required params `model_name`, `version`, `input_ref`, `tenant_id`; emits `kailash_ml_inference_latency_ms`.
  - `MLRegistryPromoteNode` — promote a model through registry tiers; required params `model_name`, `from_tier`, `to_tier`, `tenant_id`, `actor_id`; audit row written via the ambient `km.track()` run.
  - All three raise `RuntimeError` with an actionable install hint when `kailash-ml` is not installed (per `rules/dependencies.md` § "Optional Extras with Loud Failure"). `tenant_id` and `actor_id` are strict — silent fallback to `"default"` is BLOCKED (per `rules/tenant-isolation.md` §2).
- **`kailash.observability.ml`** — ML-lifecycle metrics module with bounded-cardinality tenant labels:
  - `record_train_duration(engine_name, model_name, tenant_id, duration_s)` → `kailash_ml_train_duration_seconds` (Histogram, buckets 1s-4h).
  - `record_inference_latency(model_name, version, tenant_id, latency_ms)` → `kailash_ml_inference_latency_ms` (Histogram, buckets 1ms-2.5s).
  - `record_drift_alert(feature_name, severity, tenant_id, count)` → `kailash_ml_drift_alerts_total` (Counter).
  - Top-N-by-traffic tenant bucketing (default N=100, configurable via `KAILASH_ML_METRICS_TOP_TENANTS`). Tenants beyond the top-N bucket as `"_other"` so Prometheus cardinality stays bounded per `rules/tenant-isolation.md` §4.
  - OpenTelemetry bridge: when `opentelemetry-api` is installed, the same metrics emit via the OTel SDK under identical names + labels.
  - No-op fallback when `prometheus_client` is absent emits a loud startup `UserWarning` AND returns an explanatory body from `metrics_endpoint_body()` pointing to `pip install kailash[observability]` (per `rules/zero-tolerance.md` § "Fake metrics").

**Dependency changes**

- `[project.optional-dependencies].ml` bumped to `kailash-ml>=1.1.0`.

**Migration path**

- 2.8.x users: `src/kailash/diagnostics/protocols.py` existing `Diagnostic` / `JudgeCallable` / `TraceEvent` are unchanged. `RLDiagnostic` + `DiagnosticReport` are additive.
- `kailash.workflow.nodes.ml` is a NEW subpackage — zero migration for non-ML users. The nodes register on import via `@register_node()`, so `WorkflowBuilder.add_node("MLTrainingNode", ...)` resolves at the first `import kailash` after upgrade.
- `kailash.observability.ml` is a NEW module — zero migration for non-ML users. Existing observability surfaces unchanged.

No breaking changes.

### kailash 2.8.12 — 2026-04-21 (closes #573) — `immutable_audit_log` orphan removed

**Cross-SDK orphan-check mirroring kailash-rs#461 / PR #466.** `src/kailash/trust/immutable_audit_log.py` defined `ImmutableAuditLog` (541 LOC) as a deque-based append-only log with SHA-256 hash chaining. Grep across `src/` + `packages/*/src/` + `tests/` + `packages/*/tests/` returned zero production or test consumers — the module was a pure facade per `rules/orphan-detection.md` §1, never wired into any call site. The canonical audit-storage surface is `kailash.trust.audit_store` (`InMemoryAuditStore` + `AuditStoreProtocol`), which has real production consumers.

**What changed:**

- **Deleted** `src/kailash/trust/immutable_audit_log.py` entirely (`ImmutableAuditLog`, `AuditEntry`, `RetentionPolicy`, `ChainVerificationResult`, `_compute_entry_hash`). Per `rules/orphan-detection.md` §3 ("Removed = Deleted, Not Deprecated") — no deprecation banner, no feature flag, no re-export shim. The module was not exported from `kailash.trust.__init__` so no public-surface change was required.
- **Regression guard** at `tests/regression/test_issue_573_immutable_audit_log_orphan.py` (3 assertions: module is not importable, file is absent from tree, `kailash.trust.ImmutableAuditLog` attribute does not exist). Re-introduction without a production call site fails the test loudly.
- **`specs/trust-posture.md` § 8.5** renamed "Immutable Audit Log" → "Append-Only Audit Storage" and points to `kailash.trust.audit_store`.
- **`docs/migration/v2-to-v3.md` § Audit Store** annotates the prior import path as "removed in 2.8.12" with the canonical `kailash.trust.audit_store` replacement.

**Why this matters:** Orphan facades in audit-chain surfaces are especially dangerous — downstream consumers may import them believing audit protection is active, when in fact the facade runs in isolation with no persistence integration. The deletion eliminates this vector before it can be triggered.

Closes #573.

### kailash 2.8.11 — 2026-04-20 — dialect-safety sweep

**Post-2.8.10 follow-up.** 2.8.10 shipped `quote_identifier` into the core dialect layer, but `/redteam` found 40+ DDL sites across `src/kailash/trust/audit_store.py`, DataFlow migrations (`application_safe_rename_strategy`, `column_removal_manager`, `not_null_handler`), DataFlow optimization (`index_recommendation_engine`, `query_plan_analyzer`, `sql_query_optimizer`), and the migration generator (`src/kailash/utils/migrations/generator.py`) that were still interpolating dynamic identifiers via raw f-string. 2.8.11 routes every remaining dynamic DDL identifier through `dialect.quote_identifier()` or `_validate_identifier()` and adds 20 regression tests (4 audit_store + 10 migrations + 6 optimization advisories) covering PostgreSQL / MySQL / SQLite payloads.

No API surface changes. Pure hardening per `rules/dataflow-identifier-safety.md` MUST Rules 1 + 5.

### kailash 2.8.10 — 2026-04-20 (closes #550)

**Identifier-safety parity with DataFlow.** `kailash.db.dialect` now ships a canonical `quote_identifier(name)` helper on `PostgresDialect` / `MySQLDialect` / `SQLiteDialect` that BOTH validates against the allowlist regex AND wraps in the dialect's quote character. Previously, core DDL paths (notably `ConnectionManager.create_index()` and every `src/kailash/infrastructure/*` bootstrap-table CREATE) validated the identifier via `_validate_identifier` but then interpolated the raw name into DDL — an injection vector per `rules/dataflow-identifier-safety.md` MUST Rule 1 that DataFlow's own `dataflow.adapters.dialect` had already closed.

**What changed:**

- `kailash.db.dialect` adds `IdentifierError` (a `ValueError` subclass) and `quote_identifier` on every dialect. Contract matches DataFlow: PG/SQLite use `"`, MySQL uses backtick; length limits 63 / 64 / 128; error messages never echo the raw input (fingerprint only).
- `ConnectionManager.create_index()` now quotes `index_name`, `table`, and each column via `dialect.quote_identifier()`.
- Every `src/kailash/infrastructure/*.py` bootstrap table (`task_queue`, `worker_registry`, `dlq`, `checkpoint_store`, `event_store`, `idempotency_store`, `execution_store`) routes its `TABLE_NAME` / `self._table` through `dialect.quote_identifier()` in the `CREATE TABLE IF NOT EXISTS` DDL. DML sites are unchanged — `_validate_identifier` already vets the identifier at `__init__` per Rule 5 defense-in-depth.
- `_validate_identifier` is retained for validate-only call sites (upsert SET-clause column interpolation, hardcoded-list defense-in-depth). It now raises `IdentifierError` instead of `ValueError`; existing callers that `except ValueError` continue to work because `IdentifierError` subclasses `ValueError`.
- `specs/infra-sql.md` updated to document the quote+validate contract.
- 64 new regression tests — 54 unit (injection payloads, length limits, dialect-appropriate quoting, fingerprint-no-echo across all three dialects) + 10 Tier 2 (real SQLite, `ConnectionManager.create_index()` rejects unsafe identifiers before DDL reaches the driver, DDL-is-quoted reflection).

Closes #550.

### Packaging: `kailash-trust` removed — 2026-04-20 (closes #549)

The `kailash-trust` package has been deleted from the monorepo. It was a re-export shim over `kailash.trust` with zero downstream consumers, zero test coverage, and a publication history beginning 2026-04-19. Users should migrate to the canonical path:

```python
# Before
from kailash_trust import TrustOperations, GenesisRecord

# After
from kailash.trust import TrustOperations, GenesisRecord
```

The `kailash-trust` project on PyPI will be yanked (requires human action at https://pypi.org/manage/project/kailash-trust/releases/). No further `trust-v*` tags will trigger publish workflows.

### kailash 2.8.9 — 2026-04-20 (hotfix; closes #538)

**Hotfix release.** Cuts the kailash core wheel containing commit `646c3d74` ("fix(nexus): release 2.1.1 — drive on_startup/on_shutdown lists directly (#531)"). Yesterday's release tagged `nexus-v2.1.1` published the kailash-nexus wheel but did NOT publish a new kailash core wheel — even though commit `646c3d74` modifies BOTH `packages/kailash-nexus/...` AND `src/kailash/servers/workflow_server.py` (which is shipped by the kailash core wheel). Result: every `pip install kailash-nexus==2.1.1` pulled `kailash>=2.8.7` (the broken core), and every Nexus 2.1.0/2.1.1 service crashed at uvicorn lifespan with `AttributeError: 'APIRouter' object has no attribute 'startup'`.

**Fix shipped in this release**: `src/kailash/servers/workflow_server.py` lifespan now iterates the `on_startup` / `on_shutdown` lists directly instead of calling `app.router.startup()` / `app.router.shutdown()`. Closes #538.

No other changes vs 2.8.8. Pure cross-package release-coordination fix.

**Audit lesson** (codified in `rules/agents.md` MUST: Reviewer Prompts Include Mechanical AST/Grep Sweep): a mechanical sweep on the nexus-v2.1.1 release would have grep-noticed that the diff touched `src/kailash/...` AND flagged that a kailash core release was also required. Future cross-package releases MUST run the parity sweep before tagging.

### kailash 2.8.8 + kailash-dataflow 2.0.11 + kailash-ml 0.11.0 + kailash-align 0.3.2 + kailash-pact 0.8.2 + kailash-trust 0.1.1 + kaizen-agents 0.9.3 — 2026-04-19

Bundle release: BP-049 classified-data leak security patch (DataFlow) + ML Phase 1 GPU-first foundation. See individual package changelogs for full entries.

#### kailash-dataflow 2.0.11

- **BP-049 security patch**: `NotFoundError` for classified-PK models now echoes a sha256 fingerprint instead of the raw value. Read-path cache keys sanitize classified PKs before inclusion. Validation error messages for classified fields emit a fingerprint only.

#### kailash-ml 0.11.0

- **GPU-first Phase 1**: `DeviceReport`, `km.device()`, `km.use_device()` context manager, and `DeviceNotAvailableError`. Hardware inventory probe covering CUDA, MPS (Apple Silicon), and CPU. See `packages/kailash-ml/CHANGELOG.md` for full entry.

#### kailash 2.8.8 / kailash-align 0.3.2 / kailash-pact 0.8.2 / kailash-trust 0.1.1 / kaizen-agents 0.9.3

- Extras pin tightening: `kailash-dataflow>=2.0.11`, `kailash-ml>=0.11.0`, `kaizen-agents>=0.9.3` to propagate the security fix and new ML API to all downstream installs.

---

### kailash 2.8.7 + kailash-kaizen 2.7.5 + kailash-dataflow 2.0.10 + kailash-nexus 2.1.0 + kailash-ml 0.10.0 + kailash-mcp 0.2.5 — 2026-04-19

#### kailash-kaizen 2.7.5

- **`LlmClient.embed()` for OpenAI + Ollama (#462, PR #502)**: `LlmClient.embed(texts, *, model)` exposes a first-class embedding API on the existing `LlmClient` surface. Supports OpenAI (`text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`) and Ollama (`nomic-embed-text` and any Ollama-hosted embedding model). Returns a `List[List[float]]` consistent with OpenAI's embedding response shape.
- **LLM endpoint trust migration identifier validation fix (#499, PR #504)**: The trust migration module in `kaizen.llm.migration` used f-string interpolation for identifier names in several log and error message paths, which was flagged as a medium-severity finding in the #499 defense-in-depth audit. All identifier-containing paths now route through `_validate_identifier()` before use.

#### kailash-dataflow 2.0.10

- See `packages/kailash-dataflow/CHANGELOG.md` for full entry.

#### kailash-nexus 2.1.0

- See `packages/kailash-nexus/CHANGELOG.md` for full entry.

#### kailash-ml 0.10.0

- See `packages/kailash-ml/CHANGELOG.md` for full entry.

#### kailash-mcp 0.2.5

- **`oauth.py` optional-extras gating (#514, PR #518)**: `kailash_mcp/auth/oauth.py` had module-level `import aiohttp`, `import jwt`, and `from cryptography...` — all declared as optional under the `[auth-oauth]` extra. These are now wrapped in `try/except ImportError` blocks with a `_require_oauth_extras()` loud-failure helper. The module now imports cleanly on a bare `pip install kailash-mcp` and raises a descriptive `ImportError` naming the required extra when OAuth classes are instantiated without the extra installed. Aligns with `rules/dependencies.md` § "Declared = Gated Consistently".

---

## kailash-kaizen — #498 LLM Deployment Abstraction (Sessions 1-8 complete)

Four-axis LLM deployment abstraction: 24 preset factories spanning direct providers (OpenAI, Anthropic, Google, 13 others), AWS Bedrock (5 families), GCP Vertex (Claude + Gemini), and Azure OpenAI — all with cross-SDK byte-parity to `kailash-rs#406`. Additive API: existing `kaizen.providers.registry` continues to work unchanged (39 consumer files verified via regression test).

#### Added

- **`LlmDeployment` + `LlmClient`** — `kaizen.llm.deployment.LlmDeployment` (frozen four-axis: wire + endpoint + auth + grammar), `kaizen.llm.client.LlmClient.from_deployment()`, `from_deployment_sync()`, `from_env()`.
- **Direct-provider presets (S3)** — 16 factories: `openai`, `anthropic`, `google`, `cohere`, `mistral`, `perplexity`, `huggingface`, `ollama`, `docker_model_runner`, `groq`, `together`, `fireworks`, `openrouter`, `deepseek`, `lm_studio`, `llama_cpp`. Each classmethod on `LlmDeployment` (e.g. `LlmDeployment.anthropic(...)`).
- **AWS Bedrock (S4a + S4b-i + S4b-ii)** — 5 preset families (`bedrock_claude`, `bedrock_llama`, `bedrock_titan`, `bedrock_mistral`, `bedrock_cohere`) with `AwsBearerToken` (bearer-only path unblocks STP) and `AwsSigV4` (botocore-backed canonicalization + `asyncio.Lock` credential rotation). `BEDROCK_SUPPORTED_REGIONS` allowlist with 27 regions (cross-SDK parity).
- **GCP Vertex AI (S5)** — `vertex_claude` + `vertex_gemini` presets with `GcpOauth` (single-flight `asyncio.Lock` refresh, `CachedToken`, cloud-platform scope pinned).
- **Azure OpenAI (S6)** — `azure_openai` preset with `AzureEntra` (3 variants: api-key, workload-identity, managed-identity via `azure.identity`). `COGNITIVE_SERVICES_SCOPE` + `AZURE_OPENAI_DEFAULT_API_VERSION="2024-06-01"` pinned.
- **`LlmClient.from_env()` three-tier precedence (S7)** — URI (`KAILASH_LLM_DEPLOYMENT`) > selector (`KAILASH_LLM_PROVIDER`) > legacy per-provider keys. Per-scheme strict regex validation on `bedrock://`, `vertex://`, `azure://`, `openai-compat://`. Migration-window isolation: deployment-tier + legacy coexistence emits `WARNING llm_client.migration.legacy_and_deployment_both_configured` and the deployment path wins.
- **`LlmHttpClient` + `SafeDnsResolver` (S4c)** — single constructor path for LLM HTTP traffic; structural SSRF defense at DNS-resolve time rejects literal private IPs AND DNS that resolves to private IPs (TOCTOU / rebinding protection). Grep-auditable: only `http_client.py` may construct `httpx.AsyncClient` in `kaizen/llm/**`.
- **§6 security test suite** — `test_credential_comparison_uses_constant_time.py` (6.4), `test_llmclient_redacts_classified_prompt_fields.py` (6.5), `test_llmhttpclient_ssrf_rejects_private_ips.py` + `..._dns.py`, `test_deployment_preset_regex_rejects_injection.py`, `test_aws_credentials_zeroize_on_rotate.py` (6.8).
- **ApiKey pickle/deepcopy hygiene** — `__reduce__` / `__deepcopy__` / `__copy__` overrides route reconstruction through `__init__` (re-derives fingerprint). Prevents accidental `__slots__`-level SecretStr exposure.
- **Cross-SDK parity suite (S9)** — `packages/kailash-kaizen/tests/cross_sdk_parity/test_preset_names_match_rust.py` pins preset names, region lists, scope constants, api-version default, and `auth_strategy_kind`/`grammar_kind` labels byte-for-byte against the Rust SDK.
- **Spec: `specs/kaizen-llm-deployments.md`** — domain-truth authority per `rules/specs-authority.md`.

#### Fixed

- **Nexus `router.on_startup` hooks ignored (#500)** — custom FastAPI `lifespan` was replacing Starlette's `_DefaultLifespan` without invoking `app.router._startup()`. Fixed by routing all startup/shutdown through a unified lifespan (`src/kailash/servers/workflow_server.py`).
- **Nexus plugin `on_startup` tasks cancelled (#501)** — `asyncio.run(hook())` created a throwaway event loop that killed any `create_task(...)` the hook scheduled. Fixed by running plugin hooks inside uvicorn's loop via `_call_startup_hooks_async` in the FastAPI lifespan.
- **Nexus cancel-cleanup contract (M-N2)** — added three-clause contract to `startup_hook_timeout` docstring: plugin `on_shutdown` MUST be safe against partial-init state, `on_startup` MUST handle `CancelledError` for spawned tasks, MUST NOT swallow. Two Tier 2 tests verify.
- **Third `asyncio.iscoroutinefunction` residual** — replaced with `inspect.iscoroutinefunction` in `packages/kailash-nexus/src/nexus/auth/audit/backends/custom.py` (Python 3.14 forward-compatible).
- **`model="gpt-4"` hardcoded default removed** — `openai_preset` now requires `model` explicitly per `rules/env-models.md`.

#### Changed

- **`LlmDeployment._NOT_YET_IMPLEMENTED` is now empty.** Every primary preset classmethod is fully wired; no `NotImplementedError` stubs remain on `LlmDeployment`.
- **`model` parameter required on every preset** (no hardcoded defaults per `rules/env-models.md`).

#### Related

- Cross-SDK: `kailash-rs#406` (parallel implementation), `kailash-rs#409` (brief-template verification).
- Workspace: `workspaces/issue-498-llm-deployment/` (ADR-0001, 8 session todos, redteam amendments).

---

## Recent Releases

### kailash 2.8.7 / kailash-kaizen 2.7.5 / kailash-dataflow 2.0.9 / kaizen-agents 0.9.3 — 2026-04-15 — Python 3.14 compatibility (#477) + DataFlow internal LocalRuntime warning (#478)

#### Fixed

- **Python 3.14 (PEP 649 / PEP 749) lazy annotations** (`kailash`, `kailash-kaizen`, `kailash-dataflow`, `kaizen-agents`) — fixes #477: every Kaizen agent built from a class-based `Signature` failed to register on Python 3.14 because the `SignatureMeta.__new__` metaclass read `namespace.get("__annotations__", {})` directly. PEP 649 stops populating that dict and emits a lazy `__annotate__` callable instead, so the metaclass produced signatures with zero input/output fields and every dependent `BaseAgent` refused to construct.
- **DataFlow `LocalRuntime` deprecation warning leaked from internal code** (`kailash-dataflow 2.0.9`, `kailash 2.8.7`) — fixes #478: long-lived `LocalRuntime` instances owned by DataFlow internals were triggering Core SDK's "use context manager" deprecation warning on every call from `model_registry.py:173` and seven other framework-owned construction sites (eight sites total across DataFlow). Core SDK 2.8.7 now exposes a public `LocalRuntime.mark_externally_managed()` opt-out; each DataFlow owner invokes it on the runtime immediately after construction so Core SDK suppresses both the ad-hoc-usage deprecation warning AND the fallback `atexit` cleanup registration — the owning framework is responsible for calling `runtime.close()` at its own shutdown. The prior iteration of this fix set the private `_cleanup_registered` flag directly; that workaround has been removed in favour of the public API so the contract is documented and survives Core SDK refactors. Without this fix the warning would become a hard error in Core SDK v0.12.0.

#### Added

- **`kailash.utils.annotations` shared helper** (`kailash 2.8.7`): single source of truth for annotation introspection across the SDK — `get_namespace_annotations(namespace)` for metaclass `__new__`, `get_class_annotations(cls)` for raw introspection, and `get_resolved_type_hints(cls)` for callers that need fully resolved types (e.g. DataFlow `@db.model` SQL generation). The `get_resolved_type_hints` path mirrors the kailash-rs handler — on Python 3.14 it falls back to `annotationlib.get_annotations(cls, format=FORWARDREF)` and raises a clear per-field error naming the class, the field, and the unresolvable forward reference, instead of the bare `NameError` that raw `cls.__annotations__` access produces.
- **`LocalRuntime.mark_externally_managed()` public opt-out** (`kailash 2.8.7`): frameworks that hold a long-lived `LocalRuntime` across many `execute()` calls (e.g. DataFlow's `ModelRegistry`, `DataFlow` instance, migration inspectors, gateway, adapter) now have a documented public API to declare that lifecycle is externally managed. The runtime responds by suppressing the "use context manager" deprecation warning and skipping atexit cleanup registration — the owning framework MUST call `runtime.close()` at its own shutdown. This replaces the earlier private-attribute workaround (`runtime._cleanup_registered = True`) that was flagged at `/redteam` as a Rule-4 violation.
- **Regression test** `tests/regression/test_python_314_annotations.py` (12 tests): covers eager and lazy namespace forms, raw and resolved class annotations, forward-reference handling, the original Kaizen Signature symptom, the Core SDK Port descriptor extraction path, and an import-wiring check across every patched module so a typo in any helper import surfaces structurally rather than at first agent use.

#### Changed

- **All annotation introspection routed through the shared helper.** Sites updated: `src/kailash/nodes/ports.py`; `kailash-dataflow/src/dataflow/{core/engine.py, core/engine_production.py, core/model_registry.py, migrations/fk_aware_model_integration.py}`; `kailash-kaizen/src/kaizen/{signatures/core.py, deploy/introspect.py, core/type_introspector.py, core/autonomy/state/types.py, memory/enterprise.py, strategies/single_shot.py, strategies/multi_cycle.py}`; `kaizen-agents/src/kaizen_agents/integrations/dataflow/connection.py`. No inline `namespace.get("__annotations__")` or unguarded `cls.__annotations__` access remains in production code paths.
- **Pyright cleanup in `kaizen/signatures/core.py`** (caught while we were in the file): `description: str = None` → `Optional[str] = None` on `InputField` / `OutputField`; dropped `ClassVar[…]` on the `_signature_*` attributes that get per-instance overrides during `clone`/`copy`; declared the multi-output `_outputs_list: List[Union[str, List[str]]]` instance type at class scope; added a `TYPE_CHECKING` import for `SignatureComposition` so the `Union[Signature, "SignatureComposition"]` forward refs resolve; cast at the dispatcher call sites where `hasattr` already narrowed the type.

### kailash-nexus 2.0.3 — 2026-04-14

#### Added

- **`ForbiddenError` canonical 403 class** (`kailash-nexus 2.0.3`): Added `nexus.ForbiddenError` as the canonical name for authorization failures. Avoids shadowing Python's stdlib `PermissionError` for any consumer that `from nexus.errors import *` or rebinds `PermissionError` locally. The previous `PermissionError` class is kept as a deprecated alias — `from nexus.errors import PermissionError` and `from nexus import NexusPermissionError` continue to work unchanged. Resolves security-review finding M1.

#### Changed

- **Internal `core.py` callers migrated to `ForbiddenError`** — the guard-failure code path (`_wrap_with_guard` for both sync and async) now raises `ForbiddenError` directly. The runtime class is identical (`PermissionError is ForbiddenError`), so existing `except nexus.NexusPermissionError` handlers continue to catch it.

### kailash 2.8.6 + kailash-dataflow 2.0.8 + kailash-kaizen 2.7.4 + kailash-nexus 2.0.2 + kailash-mcp 0.2.4 — 2026-04-14

#### Fixed

- **All 63 unit test warnings resolved** (`kailash 2.8.6`, `kailash-mcp 0.2.4`): The test suite emitted 63 warnings across 10 categories (ResourceWarnings for unclosed CLIChannel/Runtime/aiosqlite/AsyncSQLDatabaseNode, RuntimeWarnings for never-awaited coroutines, InsecureKeyLengthWarnings for short JWT keys, datetime.utcnow() DeprecationWarning, PytestCollectionWarning for misnamed test class, UserWarning for hypothesis directory and instance-based API). All resolved at source — production fix in `kailash_mcp/advanced/subscriptions.py` replaces `datetime.utcnow()` with `datetime.now(UTC)`. Test fixtures now properly close resources via yield+cleanup. PR #466.

#### Added (Nexus 2.0.2)

- **Per-handler auth guards enforced at function-wrap level for all transports** (`kailash-nexus 2.0.2`): `AuthGuard` and `NexusAuthPlugin` now wrap handlers consistently across HTTP, WebSocket, and CLI transports. Typed errors (`NexusPermissionError`, `NexusAuthenticationError`) replace generic exceptions. PR #459/#460.
- **WebSocket message handlers with per-connection state** (`kailash-nexus 2.0.2`): Composable per-connection handler registration via `@app.on_message`. PR #448.
- **Composable HTTP middleware injection** (`kailash-nexus 2.0.2`): `@app.use_middleware` decorator for ordered middleware composition. PR #449.
- **Subapp mounting** (`kailash-nexus 2.0.2`): Mount independent Nexus apps as subapps under a parent app. PR #447.
- **A2A service migrated from raw FastAPI to Nexus** (`kailash 2.8.6`): A2A protocol service now uses Nexus instead of raw FastAPI imports. PR #445.

#### Fixed (Security)

- **DLQ identifier validation hoisted to `__init__` + spec corrected** (`kailash 2.8.6`): Workflow DLQ DDL identifiers now validated at construction time, not first use. PR #446.
- **Identifier validator tolerates unhashable inputs** (`kailash 2.8.6`): `_validate_identifier` round 4 hardening — gracefully rejects unhashable inputs without raising `TypeError`.
- **CodeQL alerts resolved on PR #444** (`kailash 2.8.6`, `kailash-dataflow 2.0.8`): Five CodeQL findings addressed; credential masking, identifier fingerprinting, preencode fixes, connection_string taint chain broken.
- **Identifier length limit enforced** (`kailash-dataflow 2.0.8`): `quote_identifier` now rejects identifiers exceeding dialect max length (PostgreSQL 63, MySQL 64, SQLite 128).

#### Refactored

- **Track 3 fastapi → starlette import normalization** (`kailash 2.8.6`): Engine-layer Nexus imports normalized to Starlette base; channel app type annotated as `Any` with circular-import explanation. PR #445.

### kailash-dataflow 2.0.7 — 2026-04-13

#### Fixed

- **Integer record ID coercion for PostgreSQL** (`kailash-dataflow 2.0.7`): `express_sync.update/read/delete` rejected string IDs for integer primary key models on PostgreSQL because type coercion compared raw annotations (`Optional[int]`) against `int` directly. Additionally, the `conditions["id"]` path (used by update's filter dict) had zero type coercion. Extracted `_coerce_record_id()` helper that normalizes type annotations and applied at all 9 record ID paths. Express API type hints updated to accept `Union[str, int]`. Fixes #439. Cross-SDK: esperie-enterprise/kailash-rs#377.

### kailash 2.8.5 + kailash-mcp 0.2.2 — 2026-04-13

#### Fixed

- **CLI entry point references wrong module path** (`kailash-mcp 0.2.2`): The root `kailash` package defined a conflicting `kailash-mcp` console script entry point that pointed at the deprecated `kailash.mcp.platform_server` shim. When both packages were installed, this overwrote the correct entry point, making `kailash-mcp --help` fail with `ModuleNotFoundError`. Fixed by removing the conflicting entry point and deleting the deprecated `kailash.mcp` shim entirely. Fixes #435.
- **Simplified FastMCP import** (`kailash-mcp 0.2.2`): Removed the 60-line `_get_fastmcp_class()` workaround that was only needed because `kailash.mcp` shadowed the third-party `mcp` package. With the shim removed, FastMCP imports normally.

### Post-Convergence Security Hardening — 2026-04-12

kailash 2.8.4 + kailash-dataflow 2.0.6 + kailash-kaizen 2.7.3

#### Security

- **SQL injection fix in kaizen security audit** (`kailash-kaizen 2.7.3`): `query_events()` in `security/audit.py` built a raw f-string `WHERE` clause from caller-supplied `event_type` and `agent_id` — these arguments could contain SQL metacharacters. Fixed to use parameterized queries; identifier path validated with `re.match` before interpolation.
- **Identifier fingerprint error messages** (`kailash 2.8.4`, `kailash-dataflow 2.0.6`): all `IdentifierError` messages now emit a hex fingerprint of the offending input (`hash(name) & 0xFFFF:04x`) rather than echoing the raw value, preventing log-poisoning / stored-XSS via crafted identifier names.
- **CAS fail-closed guards** (`kailash 2.8.4`): `cache.py` CAS path now raises `CASConflictError` on version mismatch instead of silently overwriting. Guards added to the async write-through path.
- **Tenant-scoped cache `_clear`** (`kailash 2.8.4`): `InMemoryCache._clear()` now accepts an optional `tenant_id` parameter; without it the method refuses to clear across tenants, preventing accidental cross-tenant cache eviction.
- **`schema_manager` defense-in-depth** (`kailash 2.8.4`): `SchemaManager.drop_table()` and `drop_column()` require `force_drop=True` per `rules/dataflow-identifier-safety.md` Rule 4; previously a missing flag would silently drop.
- **EATP human-origin identifier validation** (`kailash 2.8.4`): `eatp_human_origin.py` migration now routes all dynamic identifiers through `dialect.quote_identifier()` — the earlier version interpolated tenant-supplied model names directly into DDL.
- **Audit forwarding with `exc_info`** (`kailash-kaizen 2.7.3`): audit `logger.error()` calls in `core/autonomy/observability/audit.py` and `security/audit.py` now pass `exc_info=True` so stack traces appear in the log pipeline instead of just the message string.
- **Classification fail-closed** (`kailash-dataflow 2.0.6`): `ClassificationPolicy.classify()` changed default from `PUBLIC` (fail-open) to `HIGHLY_CONFIDENTIAL` (fail-closed) for unclassified fields, matching kailash-rs semantics per EATP D6 (cross-SDK alignment #418). A WARN log is emitted when the default is applied.
- **Connection parser consolidated credential decode** (`kailash-dataflow 2.0.6`): `connection_parser.py` now routes credential decode through the shared `decode_userinfo_or_raise` helper, eliminating a hand-rolled `unquote()` site that lacked null-byte rejection.

#### Fixed

- **Cache CAS + tenant eviction** (`kailash 2.8.4`): `cache.py` CAS version eviction path now correctly scopes eviction to the originating tenant's partition; previously a version mismatch could evict entries belonging to a different tenant.
- **Bulk operations WARN on partial failure** (`kailash 2.8.4`): `bulk_operations.py` `BulkCreate._handle_batch_error()` and `BulkUpsert` now emit a structured `WARN` log when `failed > 0`, including attempted count, failure count, and first error sample. Previously these swallowed exceptions silently.
- **`CoreErrorEnhancer` runtime/validation exports** (`kailash 2.8.4`): `src/kailash/runtime/validation/__init__.py` now exports `CoreErrorEnhancer` so downstream importers can reach it via the public package path without private module traversal.
- **Strategy deprecations in kaizen** (`kailash-kaizen 2.7.3`): `async_single_shot.py` and `single_shot.py` emit `DeprecationWarning` when called, directing users to the canonical `DelegateEngine` strategies.

#### Breaking Changes

- **`ClassificationPolicy.classify()` default changed** (`kailash-dataflow 2.0.6`): unclassified fields now default to `HIGHLY_CONFIDENTIAL` instead of `PUBLIC`. Callers that relied on implicit PUBLIC classification must now explicitly annotate fields with `@classify("field", DataClassification.PUBLIC)`. See migration notes in `packages/kailash-dataflow/CHANGELOG.md`.

### Platform Architecture Convergence — Completion — 2026-04-12

kailash 2.8.3 + kailash-ml 0.9.0 + kailash-dataflow 2.0.5 + kaizen-agents 0.9.2

#### Added

- **EventLoopWatchdog** (kailash 2.8.3): async stall detection that fires when the event loop blocks for longer than a configurable threshold, emitting structured WARN logs with stack traces of the blocking coroutine. Integrated into `AsyncLocalRuntime`.
- **ProgressUpdate contract** (kailash 2.8.3): long-running nodes can now emit structured progress updates via `ProgressRegistry`, enabling real-time status reporting to callers without polling.
- **PACT N4/N5/N6 exports** (kailash 2.8.3): complete public API surface for PACT conformance types with cross-SDK vector integrity verification (32 conformance tests, SHA-256 vector checksums).
- **Cross-SDK conformance CI** (kailash 2.8.3): new GitHub Actions workflow validates PACT N6 byte-identical JSON serialization against committed test vectors on every push to trust/pact code.
- **Convergence verification script** (`scripts/verify-convergence.py`): automated check that all convergence-202 deliverables are present and wired.
- **v2-to-v3 migration guide** expanded with convergence deliverables and upgrade paths.

#### Changed

- **DriftMonitor API rename** (kailash-ml 0.9.0, **breaking**): `set_reference()` → `set_reference_data()`, `_load_baseline`/`_store_baseline` → `_load_performance_baseline`/`_store_performance_baseline`. New `DriftCallback` type alias for the `on_drift_detected` handler. The `DriftSpec.on_drift_detected` field is now properly typed as `DriftCallback | None` instead of `Any`.
- **CodeQL sanitizer barriers** (kailash-dataflow 2.0.5): `safe_log_value()` helper added to `dataflow.utils.masking` as a taint-sink barrier for structured log fields. PostgreSQL, MySQL, and factory adapter init logs now route connection coordinates through this helper, eliminating false-positive HIGH alerts from CodeQL's `py/clear-text-logging-sensitive-data` rule.
- **SQLAlchemy availability probe** (kaizen-agents 0.9.2): replaced `try/import/except` pattern with `importlib.util.find_spec()` to eliminate CodeQL unused-import false positives.
- **MongoDB adapter typing** (kailash-dataflow 2.0.5): motor type hints changed from `TYPE_CHECKING` forward references to `Any` to avoid CodeQL false positives on unused imports.

#### Fixed

- **PACT N6 conformance CI** (kailash 2.8.3): workflow was failing with `No module named pytest` because `uv sync` doesn't install optional extras. Fixed to use `uv pip install -e ".[trust,dev]"`.
- **Watchdog `loop=` deprecation** (kailash 2.8.3): removed deprecated `loop=` parameter from `asyncio.ensure_future` calls in the watchdog module.
- **Progress registry orphan wiring** (kailash 2.8.3): `ProgressRegistry` context var lifecycle fixed under exception paths to prevent orphaned registries.

#### Internal

- **Specs authority system** synced from loom — `specs/_index.md` manifest and domain-organized spec files now available for all phase commands.
- **Convergence-202 knowledge codified** into skills and proposal manifest (95+ entries at `pending_review`).
- **12 institutional patterns** from R1/R2/R3 audit rounds captured as rule updates and CodeQL configuration.

### Arbor Upstream Fixes — Security Patch — 2026-04-12

kailash 2.8.2 + kailash-dataflow 2.0.4 + kailash-nexus 2.0.1 + kailash-mcp 0.2.1 + kailash-kaizen 2.7.2 + kaizen-agents 0.9.1

#### Security

- **HIGH — null-byte MySQL auth-bypass** (kailash 2.8.2, kailash-dataflow 2.0.4, kaizen-agents 0.9.1): a crafted `mysql://user:%00bypass@host/db` URL would decode to `\x00bypass`, the MySQL C client truncates at null, and the driver sends an empty password against any row in `mysql.user` with an empty `authentication_string`. Null-byte rejection existed at 2 of 5 MySQL credential-decode sites. R3 consolidates all 6 sites (`db/connection.py`, `trust/esa/database.py`, `nodes/data/async_sql.py`, `dataflow/core/pool_utils.py`, `kaizen-agents/state_manager.py`, plus dict-returning `ConnectionParser.parse_connection_string`) through the new shared helper `kailash.utils.url_credentials.decode_userinfo_or_raise`, eliminating the drift class.
- **HIGH — clear-text credential logging in DataFlow adapter init** (kailash-dataflow 2.0.4): `factory.py` logged the raw `connection_string` in a structured `extra={...}` field at adapter creation time, leaking PostgreSQL/MySQL passwords into log pipelines. Now routes through `dataflow.utils.masking.mask_url`. Companion `postgresql.py` and `mysql.py` connection-pool init logs converted from f-string to structured positional-arg format to clear CodeQL `py/clear-text-logging` taint flow and to satisfy `rules/observability.md` "no f-string log messages."
- **MED — Redis sanitize sentinel collision** (kailash 2.8.2, kailash-nexus 2.0.1): both `_sanitize_url` helpers in `trust/rate_limit/backends/redis.py` and `nexus/auth/rate_limit/backends/redis.py` returned `"redis://***"` on parse failure — indistinguishable from a successfully-masked URL. Replaced with the distinct sentinel `"<unparseable redis url>"` so log triage can tell the failure mode apart from the success mode.
- **MED — Redis masking form drift** (kailash 2.8.2, kailash-nexus 2.0.1): both Redis backends previously stripped userinfo entirely (`host:port` with no `@`) while the other three masking helpers (`database_config.get_masked_connection_string`, `dataflow.utils.masking.mask_url`) used `***@host`. The drift made operators grepping for `***@` miss every Redis log. Aligned both backends to `***@host` form.
- **LOW — JWT delegate `__new__`-bypass** (kailash-nexus 2.0.1): the SPEC-06 backward-compat delegate methods on `JWTMiddleware` would raise an opaque `AttributeError: 'NoneType'` when a caller constructed the middleware via `__new__` without assigning `_validator`. Added `_require_validator()` guard that raises a typed `RuntimeError` naming the root cause.
- **MCP credential leak in Redis URL logs** (kailash-mcp 0.2.1): `cache.py` and `advanced/subscriptions.py` logged Redis URLs via unstructured f-strings, exposing passwords in log pipelines. Replaced with `urlparse`-based structured format that emits only scheme, host, and port. 24 additional unstructured log lines in the same files were converted to structured form to satisfy `rules/observability.md` MUST NOT "No unstructured f'...' log messages."

#### Fixed

- **Arbor #3 — Nexus workflow metadata** (kailash-nexus 2.0.1): `Nexus.register()` now accepts a `metadata=` kwarg. Metadata is JSON-validated (64 KiB cap) before mutating the workflow and stored as a shallow copy so caller post-register mutations don't leak through. `@handler` decorator and `register_handler()` also accept metadata. Cross-SDK: `esperie-enterprise/kailash-rs#323`.
- **Arbor #4 — Dependency hygiene** (kailash 2.8.2, kailash-dataflow 2.0.4, kailash-kaizen 2.7.2): removed undeclared `numpy`, `aiohttp` from kailash-dataflow main deps (not imported in src/); added `requests>=2.32` to kailash-kaizen (3 lazy import sites in providers/embedding, config, signatures); kept `websockets>=12.0` in kailash-nexus (directly imported by transports); root kailash moved `websockets` to dev extras. `uv pip check` clean (142 packages).
- **Arbor #5 — DATABASE_URL special characters** (kailash 2.8.2, kailash-dataflow 2.0.4, kaizen-agents 0.9.1): four builder methods (`DatabaseConfigBuilder.{postgresql,mysql}` + `AsyncDatabaseConfigBuilder.{postgresql,mysql}`) now URL-encode credentials via `quote_plus`. Nine downstream parse sites now `unquote` credentials after `urlparse`. The hand-rolled regex MySQL parser in `trust/esa/database.py` (which rejected valid percent-encoded passwords) is removed. The pre-encoder helper `_encode_password_special_chars` is promoted to `kailash.utils.url_credentials.preencode_password_special_chars` and applied at all 6 dialect parse sites uniformly.
- **DataFlow MongoDB lazy import** (kailash-dataflow 2.0.4): `motor` was imported unconditionally at module top, breaking `from dataflow import DataFlow` for projects without motor installed. Moved import inside `MongoDBAdapter.connect()` with a descriptive `ImportError` pointing at `pip install motor pymongo`.
- **ModelRegistry deprecation warning** (kailash-dataflow 2.0.4): `LocalRuntime.execute()` emitted a `DeprecationWarning` on every `ModelRegistry` call. Fixed by setting `runtime._cleanup_registered = True` after constructing the registry-owned runtime.
- **47 JWT auth tests** (kailash-nexus 2.0.1): test helpers used `__new__` to bypass `JWTMiddleware.__init__` but never assigned `mw._validator` after SPEC-06 extracted the crypto path. Updated 8 `_make_middleware` helpers + 1 inline case. Pass count: 428/475 → 475/475.
- **MongoDB replica-set URL masking** (kailash-dataflow 2.0.4): `mask_url()` now handles comma-separated netloc (replica-set) URLs and query-string credentials; `mongodb.py` delegates to the canonical masker.

#### Changed

- **Editable sub-package install via `[tool.uv.sources]`** (root `pyproject.toml`): all 8 monorepo sub-packages now resolve from local source via path overrides, eliminating the `PYTHONPATH=packages/.../src:...` workaround that violated `rules/python-environment.md` MUST Rule 2 and the `uv sync` resolution failure caused by root pinning `kailash-dataflow>=2.0.3` against PyPI's only-2.0.0.

#### Internal

- **62 new regression tests** in `tests/regression/test_arbor_database_url_special_chars.py` covering builder encoding, downstream parse decoding, null-byte rejection (via the shared helper), `connection_parser` inline defense, Redis masking sentinel + drift alignment, JWT delegate None defense, preencoder consolidation across all 6 sites, and Nexus metadata shallow-copy semantics.
- **40/40 Nexus registry metadata tests** including 11 metadata-specific cases.
- **Red team converged at R3** with 0 CRITICAL / 0 HIGH / 0 MEDIUM findings across three independent rounds. Prior session's "COMPLETE" claim was premature — R1 surfaced 1 HIGH (the null-byte drift), R2 surfaced 2 LOW pre-existing items, R3 resolved everything.
- **Rule updates** originating from this session: `rules/infrastructure-sql.md` Rule 8a (lazy-import regression test); `rules/python-environment.md` MUST Rule 1 (explicit venv interpreter) + MUST Rule 2 (monorepo editable installs).
- **CodeQL alert handling**: 4 new alerts from PR 421 (1 unused logger fixed, 3 false-positive availability-probe patterns dismissed via API). 3 pre-existing HIGH alerts on dataflow adapter init fixed inline as part of the security narrative.

### Platform Architecture Convergence Complete — 2026-04-11

kailash 2.8.0 + kailash-kaizen 2.7.0 + kaizen-agents 0.9.0 + kailash-pact 0.8.1 + kailash-dataflow 2.0.2 + kailash-ml 0.8.0

#### [kailash 2.8.0]

##### Added

- **CostEvent** frozen dataclass with call_id dedup and `CostDeduplicator` bounded LRU (SPEC-08)
- **Canonical JSON** module (`kailash.trust._json`) with duplicate key rejection, NaN/Inf rejection, sorted-key deterministic output (SPEC-09)
- **Cross-SDK test vectors** for agent-result, streaming, and parser-differential edge cases (SPEC-09)
- **TrustPosture backward-compatible aliases** — `PSEUDO_AGENT`, `SHARED_PLANNING`, `CONTINUOUS_INSIGHT`, `DELEGATED` resolve to canonical names via enum aliases (Decision 007)

##### Fixed

- CI: `kailash-mcp` sub-package now installed in unified-ci.yml
- `PactAuditAction` count assertion (16→19)

#### [kailash-kaizen 2.7.0]

##### Added

- **SPEC-02 Provider registry** — 14 providers with prefix-dispatch model detection, `CostTracker` with thread-safe accumulation, 390 tests
- **SPEC-04 BaseAgent slimming** — 2103→859 LOC, removed duplicate MCP methods, eliminated extension point shim layer, posture immutability guard

##### Fixed

- `AgentPosture.DELEGATED` → `AgentPosture.DELEGATING` (Decision 007 alignment)

#### [kaizen-agents 0.9.0]

##### Added

- **SPEC-05 Delegate facade** — `ConstructorIOError`, `ToolRegistryCollisionError`, `run_sync()` event loop guard, deferred MCP, introspection properties (`.core_agent`, `.signature`, `.model`), 57 new tests
- **SPEC-10 Multi-agent deprecation** — 11 subclasses emit `DeprecationWarning`, `max_total_delegations` cap (default 20), `DelegationCapExceeded` error, 30 new tests

#### [kailash-pact 0.8.1]

##### Fixed

- Version consistency: `__init__.py` 0.7.2 → 0.8.1 to match `pyproject.toml`
- PACT tests updated from old posture names to canonical Decision 007 names
- `TrustPostureLevel` backward-compatible enum aliases

#### [kailash-dataflow 2.0.2]

##### Fixed

- Platform clearance fixes from full convergence

#### [kailash-ml 0.8.0]

##### Added

- PCA dimensionality reduction engine
- Full clearance features (8 ML engine improvements)

---

### Platform Architecture Convergence — 2026-04-09

kailash 2.7.0 + kailash-kaizen 2.6.0 + kailash-nexus 2.0.0 + kaizen-agents 0.8.0 + kailash-mcp 0.2.0 + kailash-dataflow 2.0.1

#### [kailash 2.7.0]

##### Added

- **ConstraintEnvelope** canonical implementation (SPEC-07) with financial, operational, temporal, data access, communication dimensions, posture ceiling, monotonic intersection, and NaN/Inf protection
- **AgentPosture** enum (SPEC-04) with 5 posture levels, coercion from strings, and ceiling intersection arithmetic
- **AuditEvent** consolidated to single canonical class with AuditEventType enum — 4 duplicate classes deleted
- **Auth consolidation** (SPEC-06) — JWT validation, RBAC, SSO providers moved to `kailash.trust.auth`
- Cross-SDK wire type fixtures for envelope and JSON-RPC round-trip testing

##### Fixed

- `from_yaml` symlink vulnerability — replaced bare `open()` with `safe_read_text()` (O_NOFOLLOW)
- `ChainConstraintEnvelope` renamed from `ConstraintEnvelope` to avoid name collision with canonical SPEC-07 class

#### [kailash-kaizen 2.6.0]

##### Added

- **Provider capability protocols** (SPEC-02): `StreamingProvider`, `ToolCallingProvider`, `StructuredOutputProvider`, `AsyncLLMProvider`, `BaseProvider` with `@runtime_checkable`
- **`ProviderCapability`** enum and `get_provider_for_model()` registry function
- **OpenAI `stream_chat()`** async generator for real token-by-token streaming
- **`@deprecated`** decorator applied to 7 BaseAgent extension points (SPEC-04)
- **`BaseAgentConfig.posture`** typed as `AgentPosture` enum (was `str`)
- **LLM-first reasoning module** (`kaizen.llm.reasoning`) with `llm_text_similarity` and `llm_capability_match`

##### Removed

- Dead `ai_chat` middleware module (LLM-first rule violation)
- `_simple_text_similarity` Jaccard/substring scoring (replaced by LLM reasoning)

##### Fixed

- Debug `sys.stderr.write` statements removed from `mcp_mixin.py` (information disclosure)
- Closure-over-loop-variable bug in `expose_as_mcp_server` (all tools invoked last method)
- All `kailash.mcp_server` imports migrated to `kailash_mcp`

#### [kailash-nexus 2.0.0] — BREAKING

##### Added

- **PACTMiddleware** governance enforcement (SPEC-06) with envelope evaluation, rejection counting
- SSO/JWT security tests (expired token, invalid signature, algorithm confusion, nonce replay)

##### Changed

- **BREAKING**: Auth middleware consolidated to `kailash.trust.auth`. Old `nexus.auth` path works via deprecation shim but will be removed in 3.0.0.

#### [kaizen-agents 0.8.0]

##### Added

- **Wrapper composition system**: `WrapperBase` with canonical stack ordering (`BaseAgent → L3GovernedAgent → MonitoredAgent → StreamingAgent`), duplicate detection, and `WrapperOrderError`
- **`StreamingAgent`** with real token streaming via `StreamingProvider.stream_chat()` and batch fallback
- **`MonitoredAgent`** with cost tracking via `CostTracker` and budget enforcement (NaN/Inf protected)
- **`L3GovernedAgent`** with `ConstraintEnvelope` enforcement (financial, operational, posture dimensions) and `_ProtectedInnerProxy`
- **`LLMBased`** routing strategy wrapping `llm_capability_match` for agent selection
- **`SupervisorWrapper(WrapperBase)`** delegating sub-tasks to worker pool via LLM routing
- **Typed event system**: `TextDelta`, `ToolCallStart`, `ToolCallEnd`, `TurnComplete`, `BudgetExhausted`, `ErrorEvent`, `StreamBufferOverflow`
- 176 new tests across 11 test files (wrapper, security, routing, protocol)

##### Fixed

- `CostTracker._records` bounded to `deque(maxlen=10000)` (memory exhaustion prevention)

#### [kailash-mcp 0.2.0]

##### Added

- **Canonical wire types**: `JsonRpcRequest`, `JsonRpcResponse`, `JsonRpcError`, `McpToolInfo` with `to_dict()`/`from_dict()` round-trip
- Protocol message validation and prompt injection security tests

#### [kailash-dataflow 2.0.1]

##### Fixed

- Fabric sync products offloaded to thread + parameterized source-change fix

### kailash 2.6.0 + kailash-pact 0.8.0 + kailash-dataflow 1.8.0 + kailash-ml 0.5.0 + kailash-align 0.3.0 — 2026-04-06

#### [kailash 2.6.0]

##### Added

- **SUSPENDED VettingStatus** in clearance FSM with full transition validation (#309)
- FSM transitions: PENDING→ACTIVE→SUSPENDED→ACTIVE (reinstatement) or →REVOKED (terminal)
- `validate_transition()` for clearance state machine enforcement
- `transition_clearance()` for safe status transitions with audit trail
- Revoke guard against already-revoked clearances

##### Fixed

- **Security**: Code injection and shell injection vulnerabilities addressed (#306)
- `AuditChain.from_dict()` called nonexistent `verify_integrity()` method

#### [kailash-pact 0.8.0]

##### Added

- **SUSPENDED** added to `VettingStatus` enum with FSM transition validation (#309)
- Clearance FSM pattern: PENDING→ACTIVE→SUSPENDED↔ACTIVE, SUSPENDED→REVOKED
- `revoke_clearance()` preserves record with REVOKED status for audit trail

#### [kailash-dataflow 1.8.0]

##### Added

- `bulk_upsert` operation for efficient batch insert-or-update (#294-#303)

#### [kailash-ml 0.5.0]

##### Added

- ML correlation robustness improvements (#294-#303)

##### Fixed

- Cramer's V pivot fallback with logging for edge cases

#### [kailash-align 0.3.0]

##### Added

- Agent support and on-premises deployment patterns (#294-#303)

##### Fixed

- **Security**: Code injection prevention in alignment pipeline (#306)

### kailash-ml 0.4.0 + kailash-pact 0.7.2 — 2026-04-05

#### [kailash-ml 0.4.0]

##### Added

- **DataExplorer promoted to P1** with ydata-profiling feature parity
- Async-first API: `profile()`, `visualize()`, `compare()`, `to_html()` are all async with parallel matrix computation via `asyncio.gather()`
- **Skewness + kurtosis** per numeric column (numpy, excess kurtosis)
- **Spearman rank correlation** via polars `rank()` + Pearson (no scipy)
- **Cramer's V** categorical association matrix (hand-rolled, no scipy, bounded at 20 cols / 100 cardinality)
- **IQR outlier detection** per numeric column (1.5x IQR Tukey fence)
- **Type inference**: boolean, id, constant, categorical, numeric, text
- **AlertConfig** with 8 configurable alert types: high_nulls, constant, high_skewness, high_zeros, high_cardinality, high_correlation, duplicates, imbalanced
- **Duplicate row detection** via `polars.is_duplicated()`
- **zero_count / zero_pct** per numeric column
- **cardinality_ratio** (unique/count) for all columns
- **memory_bytes**, **sample_head**, **sample_tail**, **type_summary** in DataProfile
- **HTML report** (`to_html()`): self-contained, inline plotly.js, dark/light theme, sidebar navigation, XSS-safe
- `_data_explorer_report.py`: HTML report generator with safe uid sanitization, NaN-safe correlation colors
- `from_dict()` validation: required field checks, type/range validation on count/null_count/n_rows
- PyCaret comparison test suite (13 tests covering full ML lifecycle)

##### Changed

- DataExplorer API is now **async** (breaking: `profile()` → `await explorer.profile()`)
- Missing patterns computation bounded at 20 null columns (prevents O(2^n) group-by)
- `@experimental` decorator removed (P2 → P1 promotion)

##### Security

- XSS-safe HTML report: `html.escape()` on all user content, `_safe_uid()` for plotly div IDs
- `math.isfinite()` guards on all numpy-computed statistics (skewness, kurtosis, correlation)
- Silent `except: pass` replaced with `logger.debug()` logging
- Double HTML-escape bug fixed in `to_html()` title

#### [kailash-pact 0.7.2]

##### Fixed

- **#291**: WorkResult constructor now validates cost_usd and budget_allocated via `__post_init__` — NaN/Inf clamped to 0.0/None with warning log
- **#292**: PactEngine.submit() now acquires `asyncio.Lock` making check-remaining → execute → record-cost atomic — prevents concurrent budget overspend race

##### Security

- NaN/Inf in WorkResult financial fields no longer propagate to downstream consumers (dashboards, billing)
- Concurrent submit() calls serialized — budget integrity guaranteed under multi-threaded server deployments

---

### Multi-Package Release — 2026-04-05

#### [kailash 2.5.1] — Core SDK

##### Fixed

- Abstract Node subclasses missing `run()` method across 24+ classes (security, data, system, transaction, monitoring, governance nodes)
- `SecurityEventNode` severity comparison used string ordering instead of numeric ranking (CRITICAL < HIGH was wrong)

#### [kailash-nexus 1.9.0]

##### Added

- **WebSocket transport** (`nexus.transports.websocket`): bidirectional real-time communication with connection lifecycle, heartbeat, max_connections enforcement
- **Webhook transport** (`nexus.transports.webhook`): inbound HMAC-SHA256 verification, outbound delivery with retry, idempotency deduplication, DNS-pinned SSRF prevention
- **ResponseCache middleware** (`nexus.middleware.cache`): TTL + LRU eviction, ETag/304 support, Cache-Control parsing, thread-safe, per-handler configuration

##### Fixed

- Handler parameter validation: tests updated for new `register_handler` validation (30 pre-existing failures)
- `SecurityEventNode` and `AuditLogNode` missing `run()` (auth plugin instantiation failure)

##### Security

- SSRF prevention with blocked IP ranges (RFC 1918, loopback, link-local, cloud metadata, IPv4-mapped IPv6)
- DNS rebinding prevention via IP pinning in webhook delivery
- Generic error messages in WebSocket and health endpoints (no `str(exc)` leaks)
- `max_connections` enforcement prevents WebSocket resource exhaustion

#### [kailash-ml 0.3.0]

##### Added

- `kailash_ml.types` module — consolidated type contracts (MLToolProtocol, AgentInfusionProtocol, FeatureField, FeatureSchema, ModelSignature, MetricSpec)
- `pyarrow>=14.0` as base dependency for Arrow interop
- `MetricSpec.__post_init__` validates `math.isfinite(value)` — rejects NaN/Inf
- README expanded from 133 to 917 lines (all 15 engines, type contracts, agent integration, dashboard)
- Dashboard redesigned: sidebar navigation, search/filter, dark mode, 5 new API routes (overview, features, drift)

##### Removed

- `kailash-ml-protocols` package eliminated — all types merged into `kailash_ml.types`

#### [kailash-dataflow 1.7.1]

##### Fixed

- `logger.info` → `logger.debug` for audit trail initialization (log level compliance)
- Added `run()` to 4 Node subclasses (AggregateNode, NaturalLanguageFilterNode, SmartMergeNode, DataFlowConnectionManager)

#### [kailash-pact 0.7.1]

##### Fixed

- Pre-existing test collection errors resolved (hypothesis dependency)

#### [kailash-align 0.2.1]

##### Fixed

- `datasets` version cap removed (`<4.0` → `>=4.0`) — resolves `trl>=1.0` dependency conflict
- Test version assertion updated to match 0.2.0 release

#### [kailash-kaizen 2.5.0] (first PyPI release at this version)

Breaking: `structured_output_mode` default changed from "auto" to "explicit".

#### Changed

- `structured_output_mode` default flipped from "auto" to "explicit" — auto-generation no longer happens implicitly
- "auto" mode still accepted but emits `FutureWarning` (will be removed in v3.0)
- Removed hardcoded `"gpt-4"` fallback in WorkflowGenerator — now requires `DEFAULT_LLM_MODEL` env var or explicit `model` config

#### Added (kailash-pact)

- `submit()` input validation: rejects empty/whitespace `objective` and `role` parameters
- `WorkResult.budget_allocated` field: tracks the budget ceiling allocated to the submission
- `WorkResult.audit_trail` field: structured audit entries at each governance/execution milestone

#### Added (kailash-dataflow)

- Fabric-only mode (#251): DataFlow instances with sources but no `@db.model` classes skip database initialization entirely
- `serving.py` parameter validation (security): consumer names validated against alphanumeric pattern (max 255 chars), refresh must be "true"/"false" exactly
- Consumer error messages no longer leak the available consumer registry list

#### Fixed

- MCP `_product_params_to_schema` now handles `from __future__ import annotations` string annotations for int/float/bool types
- Pre-existing test regex mismatches in `test_file_adapter.py`, `test_config.py`, and `test_providers_azure_docker.py`

### [kailash-kaizen 2.4.0] - 2026-04-04

Explicit provider configuration refactor — eliminates implicit magic that caused #254-257.

#### Added

- `response_format` field on BaseAgentConfig for explicit structured output configuration
- `structured_output_mode` field ("auto"/"explicit"/"off") with deprecation path
- `StructuredOutput` helper class: `from_signature()`, `for_provider()`, `prompt_hint()`
- `prompt_utils.py` — single source of truth for signature-based prompt generation
- `resolve_azure_env()` helper for canonical-first env var resolution with deprecation
- NaN/Inf guard on `temperature` and `budget_limit_usd` fields

#### Changed

- `provider_config` now holds only provider-specific settings (api_version, deployment)
- Azure env vars canonicalized: `AZURE_ENDPOINT`, `AZURE_API_KEY`, `AZURE_API_VERSION`
- System prompt generation unified — BaseAgent and WorkflowGenerator share `prompt_utils`
- Hardcoded `"gpt-4"` model default replaced with `os.environ.get("DEFAULT_LLM_MODEL")`

#### Deprecated

- `provider_config` for structured output (use `response_format` instead) — migration shim auto-converts
- `structured_output_mode="auto"` (will change to "explicit" in next minor)
- Legacy Azure env vars (`AZURE_OPENAI_*`, `AZURE_AI_INFERENCE_*`) — use canonical names

#### Fixed

- #254: Azure json_object response_format requires 'json' in system prompt
- #255: provider_config dual purpose — api_version misinterpreted as response_format
- #256: Azure endpoint detection missing cognitiveservices.azure.com pattern
- #257: AZURE_OPENAI_API_VERSION env var not read

#### Removed

- Error-based Azure backend fallback (`handle_error()`) — use `AZURE_BACKEND` explicitly

### [2.5.0] - 2026-04-04

**Multi-Package Release** — kailash 2.5.0, kailash-pact 0.7.0, kailash-dataflow 1.7.0, kailash-nexus 1.8.0

Consolidated 23 GitHub issues (#231-#253) across 5 workstreams.

#### Added

- PACT: Enforcement modes ENFORCE/SHADOW/DISABLED with env var guard (#239)
- PACT: Per-node GovernanceCallback protocol (#234)
- PACT: HELD verdict distinct from BLOCKED with HeldActionCallback (#238)
- PACT: Envelope-to-execution adapter mapping 5 PACT dimensions (#240)
- PACT: Degenerate envelope detection at init (#241)
- Governance: reject_bridge() with vacancy check (#231)
- Nexus: Prometheus /metrics endpoint (optional dependency) (#233)
- Nexus: SSE /events/stream with filtered subscriptions (#233)
- DataFlow: Provenance[T] field-level source tracking (#242)
- DataFlow: Audit trail persistence — SQLite + PostgreSQL (#243)
- DataFlow: Consumer adapter registry for product transforms (#244)
- Fabric: Cache invalidation API (#246)
- Fabric: ?refresh=true cache bypass (#247)
- Fabric: MCP tool generation from products (#250)
- Fabric: FileSourceAdapter directory scanning (#249)
- Fabric: Fabric-only mode without database (#251)

#### Fixed

- PACT: Stale supervisor budget — fresh per submit() (#235)
- PACT: Mutable GovernanceEngine → ReadOnlyGovernanceView (#236)
- PACT: NaN guard on budget_consumed (#237)
- Governance: Vacant roles blocked from bridge approval (#231)
- Fabric: Virtual products execute inline instead of returning None (#245)
- Fabric: dev_mode pre-warming with prewarm parameter (#248)
- Fabric: ChangeDetector dict-vs-adapter crash (#253)

#### Changed

- DataFlow: BaseAdapter.database_type → source_type with deprecation shim (#252)
- DataFlow: datetime.utcnow() → datetime.now(UTC) in audit code

### [2.4.1] - 2026-04-03

**Patch Release** — kailash 2.4.1

#### Fixed

- MCP `ResourceCache` implementation and collection error fix
- Removed editable install symlinks accidentally committed
- Resolved 42 pre-existing DataFlow test failures (knowledge_base path, SQLite isolation, flaky assertions)
- Resolved 7 pre-existing trust/PACT test failures (audit action count, vacancy enforcement, MCP import)

### [2.4.0] - 2026-04-01

**Minor Release** — kailash 2.4.0

#### Added

- **Unified MCP Platform Server**: Single FastMCP server consolidating 7 AST contributors (workflow, node, runtime, trust, PACT, test generation, execution). Security tier system (public/authenticated/admin) for tool access control. MCP resources for workflow listings and node catalogs.
- **PACT write-time tightening for all 5 CARE dimensions** (#200): `validate_tightening()` now checks Temporal, Data Access, and Communication dimensions. Per-dimension gradient thresholds (`DimensionThresholds`, `GradientThresholdsConfig`) with configurable auto-approve/flag/hold/block ranges. Gradient dereliction and pass-through envelope detection.
- **PACT auto-create vacant head roles** (#201): `compile_org()` auto-synthesizes vacant head roles for headless departments and teams per spec Section 4.2. Bridge bilateral consent protocol (`consent_bridge()`) and scope validation against endpoint envelopes.
- **PACT vacancy interim envelope** (#202): Vacant roles within configurable deadline window operate under an interim envelope (intersection of own + parent's). `vacancy_deadline_hours` parameter on `GovernanceEngine`.
- **PACT EATP record emission** (#199): `GovernanceEngine` emits `GenesisRecord`, `DelegationRecord`, and `CapabilityAttestation` via `PactEatpEmitter` protocol. `InMemoryPactEmitter` default implementation. Access denials include `barrier_enforced` audit flag.

#### Security

- 11 findings fixed (4 CRITICAL + 7 HIGH), 0 open CRITICAL/HIGH across all workspaces

---

### [kailash-dataflow 1.5.0] - 2026-04-01

#### Added

- **DerivedModel**: Computed models that auto-update when source models change. Declarative derivation rules with dependency tracking.
- **FileSource node**: Import data from CSV, JSON, and Parquet files directly into DataFlow models with schema inference and validation.
- **Validation DSL**: Declarative field validation rules (`required`, `min`/`max`, `pattern`, `unique`, custom validators) applied at model level before database writes.
- **Express cache wiring**: Transparent caching layer for `db.express` reads with configurable TTL and invalidation on writes.
- **ReadReplica support**: Route read queries to replica databases automatically. Configurable read/write splitting with lag-aware routing.
- **Retention engine**: Time-based and count-based data retention policies. Automatic cleanup of expired records with configurable schedules.
- **EventMixin**: `on_source_change` callback system for reactive data pipelines. Models can subscribe to changes in other models.

---

### [kailash-nexus 1.7.0] - 2026-04-01

#### Added

- **Transport ABC**: Abstract base class for pluggable transport implementations. Clean separation of protocol handling from business logic.
- **HTTPTransport**: Production HTTP transport implementation replacing the monolithic gateway. Supports middleware, CORS, and streaming.
- **MCPTransport**: Dedicated MCP transport with proper protocol handling, resource management, and tool dispatch.
- **HandlerRegistry**: Centralized handler registration and dispatch. Type-safe handler resolution with middleware support.
- **EventBus**: Internal event system for cross-component communication. Publish/subscribe pattern with typed events.
- **BackgroundService**: Managed background task lifecycle with graceful shutdown, health monitoring, and restart policies.
- **Phase 2 APIs**: File serving, bridge patterns, and extended handler capabilities for complex multi-channel workflows.

#### Changed

- Transport layer refactored from monolithic gateway to pluggable architecture. Existing APIs remain backward-compatible via `MIGRATION.md`.

---

### [kailash-ml 0.1.0] - 2026-04-01

**Initial Release** — kailash-ml 0.1.0

#### Added

- **ML Protocol layer** (`kailash-ml-protocols`): Shared interfaces for model training, evaluation, feature engineering, and serving.
- **9 ML engines**: FeatureStore, FeatureEngineer, ModelTrainer, ModelEvaluator, ModelRegistry, ExperimentTracker, DataVersioner, PipelineOrchestrator, ModelServer.
- **8 interop converters**: Polars-native data handling with converters for pandas, NumPy, PyArrow, scikit-learn, XGBoost, LightGBM, CatBoost, and PyTorch.
- **MLflow v1 compatibility**: Drop-in experiment tracking compatible with MLflow's logging API.
- **ONNX bridge**: Export trained models to ONNX format for cross-framework inference.

---

### [kailash-align 0.1.0] - 2026-04-01

**Initial Release** — kailash-align 0.1.0

#### Added

- **AdapterRegistry**: Pluggable adapter system for model fine-tuning backends (LoRA, QLoRA, full fine-tune).
- **AlignmentConfig**: Unified configuration for SFT, DPO, and RLHF training pipelines.
- **SFT/DPO pipeline**: Supervised fine-tuning and direct preference optimization with dataset validation and checkpoint management.
- **Evaluator**: Model quality assessment with configurable metrics, benchmark suites, and regression detection.
- **Serving (GGUF)**: Quantized model serving with GGUF format support for efficient on-device inference.
- **Bridge**: Integration layer connecting kailash-ml training outputs to alignment workflows.
- **OnPrem**: On-premises deployment utilities for air-gapped environments.

---

### [2.3.4] - 2026-03-31

**Patch Release** — kailash 2.3.4

#### Fixed

- **PACT default constraint envelope** (#195): Relaxed two overly restrictive defaults on `ConstraintEnvelopeConfig`:
  - `financial`: Changed from `FinancialConstraintConfig(max_spend_usd=0.0)` to `None` — financial dimension is now skipped during evaluation when not explicitly configured, matching the M23/2301 design intent
  - `CommunicationConstraintConfig.internal_only`: Changed from `True` to `False` — agents are no longer restricted to internal-only communication by default. Predefined postures already set explicit values per trust level.

---

### [2.3.3] - 2026-03-31

**Patch Release** — kailash 2.3.3

#### Fixed

- **TrustPosture pseudo alias** (#191): `TrustPosture("pseudo")` now resolves correctly via `_missing_` classmethod instead of raising `ValueError`
- **ShadowEnforcer test attribute** (#193): Corrected `bounded_memory` test to use `_call_log` attribute (renamed from `call_log` during red team hardening)
- **Hardcoded version assertions**: Removed 2 fragile hardcoded version checks in trust CLI and coverage tests

---

### [kailash-dataflow 1.4.0] - 2026-03-31

#### Added

- **Sync Express API** (#187): New `SyncExpress` class available via `db.express_sync` — wraps all 11 async Express methods for non-async contexts (CLI scripts, sync handlers, pytest without asyncio). Uses persistent daemon thread event loop.

#### Fixed

- **SQLite timestamp read-back** (#184): `express.create()` on SQLite now returns `created_at`/`updated_at` via follow-up query, matching PostgreSQL RETURNING behavior
- **Migration log noise** (#185): 16 WARNING-level messages for expected/idempotent operations reduced to DEBUG
- **`__del__` finalizer safety** (#186): 12 DataFlow classes hardened with `_warnings=warnings` guard
- **`id_type.__name__` AttributeError**: Fixed crash when model defines `id` as `str` type in generated CreateNode parameters

---

### [2.3.2] - 2026-03-31

**Patch Release** — kailash 2.3.2

#### Fixed

- **`__del__` finalizer safety** (#186): 6 core classes (3 runtimes, 2 channels, 1 middleware) hardened with `_warnings=warnings` guard for interpreter shutdown safety
- **SQLite cursor leak**: Fixed unclosed cursor in `SQLiteAdapter.execute()` causing "cannot commit — SQL statements in progress" errors
- **CodeQL compliance**: `AsyncLocalRuntime.__del__` now calls `super().__del__()` so `LocalRuntime` finalizer runs

---

### [kailash-nexus 1.6.1] - 2026-03-31

#### Fixed

- **`__del__` finalizer safety** (#186): 3 Nexus classes (NexusWorkflow, MCPServer, MCPWebsocketServer) hardened with `_warnings=warnings` guard

---

### [kailash-kaizen 2.3.3] - 2026-03-31

#### Fixed

- **`__del__` finalizer safety** (#186): 5 Kaizen classes (trust stores, governance storage, nexus storage) hardened with `_warnings=warnings` guard

---

### [2.3.1] - 2026-03-30

**Patch Release** — kailash 2.3.1

#### Fixed

- **PACT internal_only enforcement** (#179): Actions without explicit `is_external` context no longer blocked for internal-only agents. Only explicitly external actions are denied.

---

### [kailash-pact 0.5.0] - 2026-03-30

#### Added

- **Bridge LCA Approval** (#168): `create_bridge()` requires lowest common ancestor approval with 24h expiry
- **Vacancy Enforcement** (#169): `verify_action()` checks vacancy status before envelope checks — vacant roles auto-suspended
- **Dimension-Scoped Delegation** (#170): `DelegationRecord.dimension_scope` for delegations scoped to specific constraint dimensions

#### Fixed

- **internal_only Enforcement** (#179): `is_external` context field no longer blocks actions when unspecified — only explicitly external actions are blocked for internal-only agents. Fixes 11 test failures from overly strict `is_external is not False` check

---

### [2.3.0] - 2026-03-30

**Multi-Package Release** — kailash 2.3.0, kailash-dataflow 1.3.0, kaizen-agents 0.6.0, kailash-kaizen 2.3.2

#### Added

- **PACT Vacancy Enforcement** (#169): `verify_action()` now checks vacancy status before envelope checks — vacant roles without acting occupant designation are auto-suspended. `designate_acting_occupant()` API with 24h expiry
- **PACT LCA Bridge Approval** (#168): `create_bridge()` now requires lowest common ancestor (LCA) approval. `approve_bridge()` API with 24h expiry, `Address.lowest_common_ancestor()` utility
- **PACT Dimension-Scoped Delegation** (#170): `DelegationRecord.dimension_scope` field allows delegations scoped to specific constraint dimensions (e.g., Financial + Temporal only). `intersect_envelopes()` respects dimension scope
- **DataFlow Lazy Connection** (#171): `DataFlow.__init__()` no longer connects eagerly — pool creation, validation probe, and auto-migration deferred to first query via `_ensure_connected()`. Fixes import-time failures in unit tests

#### Fixed

- **DurableWorkflowServer Dedup** (#175): POST request bodies now correctly included in dedup fingerprints. Previously all POSTs to the same endpoint produced identical fingerprints, returning stale cached responses
- **Agent API Bugs** (#172, #173, #174): `AgentResult.error()` → `from_error()` (crash fix), silent success fabrication removed, Agent class deprecated in favor of Delegate
- **Agent `run_sync()` Deprecation** (BUG-4): Replaced deprecated `asyncio.get_event_loop()` with modern `asyncio.run()` pattern
- **OrchestrationRuntime Memory Leak** (BUG-5): `_execution_history` bounded with `deque(maxlen=10000)`
- **Pipeline ABC** (BUG-6): `Pipeline` now uses `abc.ABC` + `@abstractmethod` instead of `raise NotImplementedError`
- **60+ Pre-Existing Test Failures**: Missing proxy modules (`kaizen.agents`, `kaizen.journey`, `kaizen.orchestration`), MemoryAgent error handling, tool event callback refactor, registry imports

#### Changed

- **Agent API Deprecated**: `kaizen_agents.api.Agent` emits `DeprecationWarning` — use `kaizen_agents.Delegate` instead
- **COC Three-Layer Model**: New `rules/framework-first.md` establishing engine-first principle across all frameworks

---

### [2.2.1] - 2026-03-29

**Patch Release** — kailash 2.2.1 (security hardening post-release fix)

#### Fixed

- Trust-plane security hardening from red team round 2: ShadowEnforcer `deque(maxlen=N)`, BudgetTracker callback bounds, `str(exc)` leak in PactEngine + MCP middleware, `EnforcementRecord frozen=True`, ShadowEnforcer `threading.Lock`

---

### [2.2.0] - 2026-03-28

**Multi-Package Release** — kailash 2.2.0, kailash-nexus 1.6.0, kaizen-agents 0.4.0, kailash-kaizen 2.3.1, kailash-dataflow 1.2.1, kailash-pact 0.4.1

#### Added

- **OpenTelemetry Progressive Tracing** (S5): `TracingLevel` enum (NONE/BASIC/DETAILED/FULL), node-level instrumentation, DataFlow/DB instrumentation, Prometheus metrics bridge
- **Nexus K8s Integration** (S4): K8s probe endpoints (`/healthz`, `/readyz`, `/startup`), OpenAPI 3.0.3 generation, security headers middleware, CSRF middleware, middleware presets (Lightweight/Standard/SaaS/Enterprise)
- **Delegate Facade** (S9): Unified `Delegate` class with typed events (`TextDelta`, `ToolCallStart`, `ToolCallEnd`, `TurnComplete`), progressive disclosure API, budget tracking with NaN/Inf defense
- **Multi-Provider LLM Adapters** (S8): `StreamingChatAdapter` protocol with OpenAI, Anthropic, Google (Gemini), and Ollama adapters; auto-detection from model name
- **Tool Search/Hydration** (S7): BM25 tool search for large tool sets (30+), automatic hydration with `search_tools` meta-tool
- **Incremental Token Streaming** (S6): `AgentLoop.run_turn()` yields text deltas as they arrive instead of buffering

#### Changed

- Trust-plane `Delegate` renamed to `DelegationRecipient` with backward-compatible alias (S3e-004, #97)
- `TracingLevel` defaults to BASIC when OpenTelemetry is installed (backward compatible)
- CI pipeline: per-test timeout (30s), Python 3.13 continue-on-error, thread-heavy tests marked slow

#### Fixed

- 52-file security hardening: bare excepts replaced with specific types, CORS deny-by-default, bind 127.0.0.1, error message disclosure
- PACT monotonic tightening test compliance
- Pickle RCE removal from CacheNode and persistent tiers
- Redis URL SSRF validation
- eval/exec hardening with bounded power operator
- 21 missing dependency declarations
- CI test isolation (test pollution, thread leaks, module identity)

#### Security

- All 42 bare `except:` replaced with specific exception types (E722 re-enabled)
- CORS default changed from `["*"]` to `[]` (deny-by-default)
- Server bind default changed from `0.0.0.0` to `127.0.0.1`
- Error responses no longer leak internal details via `str(e)`
- Timing-safe HMAC comparison enforced across trust plane

---

### [2.1.0] - 2026-03-26

**Multi-Package Release** — kailash 2.1.0, kailash-dataflow 1.2.0, kailash-nexus 1.5.0, kailash-kaizen 2.3.0, kaizen-agents 0.3.0

#### Added

- `ImmutableAuditLog` and RBAC matrix export (#80, #81, #100)
- `EventBus` with pluggable backends (#79)
- `DataFlowEngine` with builder pattern and enterprise features (#77, #78)
- `NexusEngine` with builder pattern and middleware presets (#77, #78)
- Field-level validation (`@field_validator`) and data classification (`@classify`) for DataFlow (#82, #83, #99)
- kaizen-agents 0.3.0: structural split — governed agent L2 engine

#### Fixed

- Runtime lifecycle management and runtime injection (#71, #72)
- Docker stage-1 setup.py references (#94, #95)

#### Security

- Replaced `eval()` with safe exception class allowlist in retry config (C1)
- Removed internal error detail leakage from API/MCP/A2A error responses (C2, C3)
- All trust hash comparisons now use `hmac.compare_digest()` (H1)
- ESA database methods validate table names against identifier pattern (H2)
- Trust-plane verification bundle uses `textContent` instead of `innerHTML` (H5)

#### Changed

- kailash-dataflow dependency updated to `kailash>=2.1.0,<3.0.0`
- kailash-nexus dependency updated to `kailash>=2.1.0,<3.0.0`
- All framework dependency pins updated in main SDK extras

### [2.0.1] - 2026-03-23

#### Fixed

- Node validation now detects and warns on unknown/misspelled parameters (#45)

#### Changed

- kailash-dataflow dependency constraint relaxed to `>=1.0.0,<3.0.0` (was `<2.0.0`)

### kailash-kaizen [2.1.0] - 2026-03-22

**L3 Autonomy Primitives** — Five deterministic SDK primitives for governed agent autonomy (`kaizen.l3`). EnvelopeTracker/Splitter/Enforcer, ScopedContext, MessageRouter/Channel, AgentFactory/Registry, Plan DAG/Validator/Executor. 868 new tests.

### [2.0.0] - 2026-03-21

**Trust Integration — EATP + Trust-Plane merged into kailash.trust**

#### Added

- `kailash.trust` namespace — EATP protocol implementation (chains, attestations, signing, verification, constraints, postures, enforcement)
- `kailash.trust.plane` namespace — Trust-plane platform (projects, sessions, decisions, milestones, holds, RBAC, SIEM, dashboard)
- `kailash[trust]` optional extra for Ed25519 cryptography (pynacl)
- CLI entry points: `eatp`, `attest`, `trustplane-mcp`
- `filelock>=3.0` added to core dependencies

#### Changed

- kailash-kaizen 2.0.0 drops standalone `eatp` dependency (uses `kailash.trust`)
- kailash-dataflow and kailash-nexus accept kailash 2.x (`<3.0.0`)

#### Removed

- `packages/eatp/` — merged into `src/kailash/trust/`. Import from `kailash.trust` instead.
- `packages/trust-plane/` — merged into `src/kailash/trust/plane/`. Import from `kailash.trust.plane` instead.
- `pydantic>=2.6` phantom dependency removed from EATP (was declared but never imported).

### [1.0.0] - 2026-03-17

**First Stable Release**

The core API (WorkflowBuilder, LocalRuntime, AsyncLocalRuntime, Node, 140+ nodes) is now under semver stability guarantees. No breaking changes until 2.0.0.

#### Added

- **Progressive Infrastructure (Level 0/1/2)** — Start with zero config (SQLite), scale to multi-worker PostgreSQL/MySQL by setting environment variables. No application code changes required.
  - `KAILASH_DATABASE_URL` switches all stores to PostgreSQL or MySQL
  - `KAILASH_QUEUE_URL` enables multi-worker task distribution (Redis or SQL-backed)
  - `StoreFactory` auto-detects configuration and creates appropriate backends
- **QueryDialect strategy pattern** (`kailash.db`) — Dialect-portable SQL generation across PostgreSQL, MySQL 8.0+, and SQLite from the same code. Canonical `?` placeholders translated automatically per dialect.
- **ConnectionManager with transaction support** — Async database connection manager with `transaction()` context manager for multi-statement atomicity across all three databases.
- **5 dialect-portable store backends** (`kailash.infrastructure`) — DBEventStoreBackend, DBCheckpointStore, DBDeadLetterQueue, DBExecutionStore, DBIdempotencyStore. All share a single ConnectionManager.
- **SQL-backed task queue** — `SQLTaskQueue` with `FOR UPDATE SKIP LOCKED` (PostgreSQL/MySQL) and `BEGIN IMMEDIATE` (SQLite) for concurrent dequeue without contention.
- **SQLWorkerRegistry** — Worker heartbeat tracking and dead worker reaping with transactional task recovery.
- **IdempotentExecutor** — Execution-level exactly-once semantics with claim-then-execute-then-store pattern and TTL-based cache expiration.
- **Queue factory** (`create_task_queue()`) — Auto-detect queue backend from `KAILASH_QUEUE_URL` (Redis, PostgreSQL, MySQL, SQLite, or file path).
- **Schema versioning** via `kailash_meta` table with downgrade protection. `migration.py` utilities for version checking.
- **SQL identifier validation** — All table/column names in dynamic SQL validated against `^[a-zA-Z_][a-zA-Z0-9_]*$` to prevent injection.
- **228 unit tests + 141 integration tests** for infrastructure layer, parameterized across SQLite, PostgreSQL, and MySQL.
- **5 reference docs** (`docs/enterprise-infrastructure/`) covering overview, store backends, task queues, idempotency, and migration guide.
- **Multi-worker quickstart guide** (`docs/guides/multi-worker-quickstart.md`) with 3 progressive example applications.

#### Fixed

- **BRPOPLPUSH → BLMOVE** — Redis 7.0+ compatibility for distributed task queue (`distributed.py`)
- **asyncpg lazy import** — `storage_backends.py` no longer crashes at import time without `kailash[postgres]`
- **DatabaseStateStorage stub** — `_ensure_table_exists()` fully implemented with schema + index creation
- **Worker deserialization** — `_execute_workflow_sync()` uses `Workflow.from_dict()`/`to_dict()` for round-trip serialization
- **WorkflowVisualizer tests** — Updated from removed matplotlib API to Mermaid/DOT API
- **Health monitor tests** — Fixed flaky HTTP mocks (aiohttp, not httpx)
- **Saga state storage tests** — Fixed `_initialized` attribute access after initialization refactor
- **Distributed runtime tests** — Updated mock from `brpoplpush` to `blmove`
- **Legacy fluent API test** — Updated to expect `WorkflowValidationError` (removed in v1.0.0)

#### Changed

- Version: 0.13.0 -> 1.0.0
- DataFlow version: 0.12.4 -> 1.0.0
- Classifier: Development Status :: 3 - Alpha -> 5 - Production/Stable
- Sub-package dependency pins updated to `kailash>=1.0.0,<2.0.0`
- `WorkflowGraph` import now emits `DeprecationWarning` (use `Workflow` instead, removal in 2.0)
- Legacy middleware (`AgentUIMiddleware`, `AIChatMiddleware`, `APIGateway`, `RealtimeMiddleware`) no longer exported from `kailash` top-level; import from `kailash.middleware` instead
- **Dependencies slimmed from 34 to 4 mandatory packages**. Core install (`pip install kailash`) now only requires `jsonschema`, `networkx`, `pydantic`, `pyyaml`. All other dependencies moved to optional extras. Use `pip install kailash[all]` to restore the pre-1.0 behavior, or install only what you need: `kailash[server]`, `kailash[http]`, `kailash[database]`, `kailash[auth]`, `kailash[viz]`, `kailash[monitoring]`, `kailash[distributed]`, `kailash[mcp]`, etc.
- **Replaced numpy/scipy/scikit-learn with stdlib `_math_utils`** — pure Python implementations of mean, stdev, median, percentile, linregress, dot product, norm, FFT. No scientific computing packages required for core SDK operation.
- `WorkflowVisualizer` is now lazy-loaded (requires `kailash[data-science]` for matplotlib)
- Server classes (`WorkflowServer`, `create_gateway`, etc.) now lazy-loaded (requires `kailash[server]`)

#### Removed (Breaking)

- **`twilio`** dependency removed entirely (no code in the SDK used it)
- **`pandas`**, **`scipy`**, **`scikit-learn`**, **`plotly`** removed from optional extras (replaced with stdlib or existing fallbacks)
- **`httpx`** removed from `http` extra (consolidated to `aiohttp` + `requests`)
- **`data-science`** extra renamed to **`viz`** (now just `matplotlib`)
- **`setup.py`** removed from all packages — `pyproject.toml` is the single source of truth
- **Legacy fluent API**: `add_node("node_id", NodeClass, param=value)` pattern removed (deprecated since v0.8.0). Use `add_node("NodeType", "node_id", {"param": value})`
- **`cycle=True` in `connect()`**: Direct `workflow.connect(a, b, cycle=True)` removed (deprecated since v0.2.0). Use `CycleBuilder` API
- **`create_gateway_legacy()`**: Removed from `kailash.servers.gateway` (use `create_gateway()`)
- **`HTTPClientNode`**: Alias removed from `kailash.nodes.api` (use `HTTPRequestNode`)
- **JWT backward-compat methods**: `generate_token()`, `verify_and_decode_token()`, `blacklist_token()`, `generate_refresh_token()` removed (use `create_access_token()`, `verify_token()`, `revoke_token()`, `create_refresh_token()`)
- **`execute_workflow()`**: Removed from `AgentUIMiddleware` (use `execute()`)
- **`add_node_fluent()`**: Method removed from `WorkflowBuilder`

### [0.13.0] - 2026-03-17

**Production Readiness Release**

35 production readiness TODOs implemented, 72 security findings resolved across 4 red team rounds, 14 hardened patterns codified.

#### Added

- Real saga execution via NodeExecutor protocol (M1/M2) — no more simulated results
- Real 2PC participant transport: LocalNodeTransport + HttpTransport with SSRF prevention (M3)
- Workflow checkpoint state capture/restore via ExecutionTracker (M4/M5)
- DurableRequest.\_create_workflow with schema validation (M6)
- Prometheus /metrics endpoint on all server classes (M7)
- SQLite EventStore backend with WAL mode (S1)
- Workflow signals and queries: SignalChannel + QueryRegistry + REST endpoints + SignalWaitNode (S2)
- Built-in workflow scheduler via APScheduler integration (S3)
- Persistent dead letter queue with exponential backoff retry (S4)
- Distributed circuit breaker via Redis with Lua atomic transitions (S5)
- OpenTelemetry tracing with graceful degradation (S6)
- Coordinated graceful shutdown via ShutdownCoordinator (S7)
- Workflow versioning with semver registry (S8)
- Multi-worker task queue architecture (S9)
- Continue-as-new pattern for infinite-duration workflows (N1)
- WebSocket-based live monitoring dashboard (N2)
- Kubernetes deployment manifests + Helm chart (N3)
- System-wide resource quotas with semaphore-based concurrency control (N4)
- Default persistent EventStore backend via KAILASH_EVENT_STORE_PATH env var (N5)
- Workflow pause/resume controller (N6)
- Connection dashboard integration into main server (N7)
- Comprehensive execution audit trail: NODE_EXECUTED/FAILED + WORKFLOW lifecycle events
- Search attributes: typed EAV table with indexed cross-execution queries
- Edge migration, MCP client/executor, credential backends, LDAP, API gateway implementations
- TestParticipantNode for real (NO MOCKING) integration tests

#### Security

- 72 findings resolved across 4 red team rounds (R1: 62, R2: 3, R3: 2, R4: 5)
- SSRF prevention with DNS rebinding protection
- SQL injection prevention via table name + filter key + attribute name regex validation
- Bounded collections (deque maxlen) on all long-lived lists/dicts
- math.isfinite() on all numeric configuration fields including EATP CostLimitDimension
- CancelledError/KeyboardInterrupt/SystemExit re-raising in saga coordinator
- Node type allowlist blocking PythonCodeNode/AsyncPythonCodeNode by default
- SQLite 0o600 file permissions including WAL/SHM (re-applied after first write)
- Rate limiting on signal/query endpoints with periodic key eviction
- Response header allowlist on proxy handler
- Generic API error messages (no str(e) in responses)
- Redis URL scheme validation
- No silent no-op defaults (LocalNodeTransport defaults to RegistryNodeExecutor)

### [0.12.1] - 2026-02-22

**V4 Audit Hardening Patch**

Post-release security and reliability hardening from V4 final audit (22 fixes across 12 files).

#### Fixed

- **Error Sanitization**: Health check and proxy error responses use `type(e).__name__` instead of `str(e)` to prevent internal detail leakage
- **Silent Exception Swallows**: 16 bare `except: pass` blocks replaced with debug-level logging across engine, transaction nodes, migration API, timestamping, and cloud integration
- **Proxy Header Filtering**: Workflow server proxy now strips sensitive headers (Authorization, Cookie, X-API-Key) before forwarding requests
- **Custom Node Timing**: Actual `time.monotonic()` execution timing replaces hardcoded `0` placeholder
- **Hardcoded Model Removal**: `BaseAgent._execute_signature` no longer falls back to hardcoded `"gpt-4o"`
- **NotImplementedError Cleanup**: Cloud integration uses `RuntimeError` for unsupported operations instead of `NotImplementedError`
- **DB URL Masking**: Database health check masks credentials in URL before including in responses

#### Test Results

- Core SDK: 4,479 passed
- All pre-commit hooks passed

### [0.12.0] - 2026-02-21

**Quality Milestone Release - V4 Audit Cleared**

This release completes 4 rounds of production quality audits (V1-V4) remediating 15 of 16 identified gaps. C5 (AWS KMS integration) is deferred to SDK 2.0.

#### Added

- **Custom Node Execution**: Fully async pipeline with CodeExecutor, AsyncLocalRuntime, and aiohttp for custom node API/Python execution
- **Azure Cloud Integration**: Azure support alongside AWS in edge resource management (DefaultAzureCredential, VM operations, monitoring)
- **Cache TTL**: MemoryCache supports TTL-based expiration with background reaper thread for automatic cleanup
- **Resource Resolver**: Centralized resource resolution with SecretManager credential handling and health checks

#### Changed

- **CORS Hardening**: `cors_allow_credentials=False` when wildcard origins used; restricted allowed headers whitelist
- **Sensitive Header Filtering**: DurableGateway strips authorization, cookie, x-api-key, x-auth-token, proxy-authorization, set-cookie from request metadata
- **DSN Encoding**: `quote_plus()` for special characters in database connection strings
- **Error Sanitization**: Only `type(e).__name__` returned to clients; full errors logged server-side
- **WebSocket Error Messages**: Sanitized to prevent internal detail leakage (type-only responses)
- **Bare Exception Cleanup**: All bare `except:` blocks replaced with `except Exception:` across engine.py

#### Fixed

- **Runtime Crash**: Fixed crash path in custom node execution when CodeExecutor unavailable
- **S3 Client Resolution**: Fixed MessageQueueFactory credential exclusion from config output
- **CLI Channel Execution**: Fixed async execution flow in CLI channel
- **Cost Optimizer**: Removed hardcoded sample data, now requires real infrastructure data

#### Security

- No hardcoded model names (all from environment variables)
- No secrets in logs or error messages
- Parameterized SQL throughout (no f-string interpolation)
- V4 audit: 0 CRITICAL, 0 blocking findings

#### Test Results

- Core SDK: 4,479 passed
- DataFlow: 794 passed
- Kaizen: 385 passed (+1 pre-existing)
- Nexus: 638 passed (+1 pre-existing)

### Application Framework Releases

#### DataFlow [0.3.1] - 2025-01-22

**Test Infrastructure & Reliability Release**

- **Test Coverage**: Improved from ~40% to 90.7% pass rate (330/364 tests)
- **Zero Failures**: All tests now pass or are properly skipped
- **Enhanced Multi-Database Integration**: Fixed PostgreSQL precision and context passing
- **Improved Multi-Tenancy**: Fixed Row Level Security tests with proper permissions
- **Transaction Support**: Enhanced transaction management and schema operations
- **Documentation**: Enhanced CLAUDE.md guidance for parameter validation

#### Nexus [1.0.3] - 2025-01-22

**Production Ready Release**

- **100% Documentation Validation**: All code examples verified with real infrastructure
- **77% Test Coverage**: Comprehensive test suite with 248 passing unit tests
- **WebSocket Transport**: Full MCP protocol implementation with concurrent clients
- **API Correctness**: All documented patterns validated and corrected
- **Enhanced Stability**: Robust error handling and timeout enforcement

### Core SDK Releases

### [0.10.6] - 2025-11-02

**Database Adapter Rowcount Fix**

Critical bug fix for SQLite and MySQL database adapters not capturing rowcount from DML operations, causing bulk operations to report incorrect counts.

#### 🐛 Fixed

**Database Adapter Rowcount Capture**

- **Fixed**: SQLite and MySQL adapters not capturing `cursor.rowcount` for DML operations (DELETE, UPDATE, INSERT)
- **Location**: `src/kailash/nodes/data/async_sql.py`
  - **SQLiteAdapter**: Lines 1554-1558 (transaction path), 1594-1599 (memory DB), 1638-1643 (file DB)
  - **MySQLAdapter**: Lines 1329-1333 (transaction path), 1367-1372 (pool connection)
- **Root Cause**: Adapters were not capturing rowcount from cursor after DML operations, causing downstream bulk operations to report incorrect counts
- **Solution**:
  - Added `cursor.rowcount` capture for all DML operations (DELETE, UPDATE, INSERT)
  - Standardized return format to `[{"rows_affected": N}]` across all adapters (PostgreSQL, MySQL, SQLite)
- **Impact**: Bulk operations (BulkCreate, BulkUpdate, BulkDelete) now correctly report actual database rowcounts
- **Breaking**: NO - fully backward compatible, fixes internal behavior only

#### 📊 Test Results

All comprehensive tests passing:

- ✅ Bulk CREATE: Correctly reports inserted count
- ✅ Bulk UPDATE: Correctly reports updated count
- ✅ Bulk DELETE: Correctly reports deleted count and persists to database

#### 🔗 Related

- DataFlow v0.7.12 includes complementary fix for bulk operation extraction logic
- Requires DataFlow v0.7.12+ for full bulk operations accuracy

---

### [0.10.0] - 2025-10-26

**Runtime Parity & Parameter Scoping Release - BREAKING CHANGES**

This release achieves 100% runtime parity between LocalRuntime and AsyncLocalRuntime, introduces intelligent parameter scoping to prevent cross-node parameter leakage, and includes breaking API changes.

#### 🚨 Breaking Changes

1. **AsyncLocalRuntime Return Structure**

   ```python
   # Before (v0.9.31):
   result = await runtime.execute_workflow_async(workflow, inputs={})
   results = result["results"]
   run_id = result["run_id"]

   # After (v0.10.0):
   results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
   ```

   **Migration**: Update all AsyncLocalRuntime calls to unpack the tuple return value.

2. **Validation Exception Types**

   ```python
   # Before (v0.9.31):
   except RuntimeExecutionError:  # For validation errors

   # After (v0.10.0):
   except ValueError:  # For validation errors
   ```

   **Migration**: Update exception handlers for runtime configuration validation.

3. **Parameter Scoping (Behavior Change)**
   - Node-specific parameters are now automatically unwrapped before passing to nodes
   - Cross-node parameter leakage prevented by filtering
   - Parameters format unchanged, but internal handling improved
   ```python
   # Same API, improved behavior:
   parameters = {
       "node1": {"value": 10},  # Only goes to node1
       "node2": {"value": 20},  # Only goes to node2
       "api_key": "global"      # Goes to all nodes
   }
   ```
   **Migration**: Most code works unchanged. Edge cases with nested conditionals may need parameter adjustments.

#### ✨ Added

- **Runtime Parity (100%)**:
  - AsyncLocalRuntime and LocalRuntime now return identical tuple structure: `(results, run_id)`
  - Both runtimes share identical parameter passing semantics
  - 28 shared parity tests ensure ongoing compatibility
  - Comprehensive parity documentation (incorporated into main changelog)

- **Parameter Scoping System**:
  - Automatic unwrapping of node-specific parameters
  - Prevention of cross-node parameter leakage
  - Smart filtering based on node IDs in workflow graph
  - Support for deep nesting (4-5+ levels tested)
  - 8 comprehensive edge case tests added

- **CI Performance Improvements**:
  - Removed coverage collection from parity workflow (10x speed improvement)
  - Reduced parity workflow timeout from 30min to 10min
  - Added concurrency control to prevent duplicate runs

#### 🐛 Fixed

- Fixed 47 test failures across runtime, parity, and integration tests
- Fixed AsyncLocalRuntime conditional execution mode detection
- Fixed nested conditional execution bugs in branch map traversal
- Fixed parameter normalization in test helpers
- Fixed contract import path (`kailash.contracts` → `kailash.workflow.contracts`)
- Fixed logger name in conditional execution tests

#### 📚 Documentation

- Updated 18 documentation files for new parameter scoping behavior
- Updated 5 parameter passing guides (sdk-users + skills)
- Updated 4 runtime execution docs with tuple return structure
- Updated 2 error handling docs with new exception types
- Marked cyclic workflow documentation status clearly
- Added comprehensive migration guide (incorporated into main changelog)

#### 🗑️ Removed

- Removed 6 incomplete TDD stub tests (cyclic workflow - feature is fully implemented, stubs were redundant)
- Removed coverage collection from CI (historical performance issue)

#### ⚙️ Internal

- Implementation: `src/kailash/runtime/local.py:1621-1640` (parameter filtering)
- 872 tier 1 tests passing (100%)
- 28 parity tests passing (100%)
- Test execution time: ~20 seconds (locally)

#### 📊 Test Results

```
Tier 1 Tests: 872/872 passing (100%)
Parity Tests: 28/28 passing (100%)
Shared Tests: 24/28 passing (4 edge cases under investigation)
Total: 896/900 passing (99.6%)
```

#### 🔗 Related

- Runtime parity migration details are incorporated into this changelog above
- See `sdk-users/3-development/parameter-passing-guide.md` for parameter scoping docs
- See `sdk-users/3-development/10-unified-async-runtime-guide.md` for async runtime docs

---

### [0.9.27] - 2025-10-22

**CRITICAL: AsyncLocalRuntime Parameter Passing Fix**

This release resolves a P0 critical bug where AsyncLocalRuntime failed to pass node configuration parameters to async_run(), causing ALL DataFlow operations to fail.

#### Fixed

- 🐛 **CRITICAL: AsyncLocalRuntime Parameter Passing Bug**: AsyncLocalRuntime now correctly calls `execute_async()` instead of `async_run()` directly, ensuring node.config parameters are merged before execution
- 🐛 **DataFlow Complete Failure**: Fixed 100% failure rate for ALL DataFlow CRUD operations (Create, Update, Delete, List) with AsyncLocalRuntime
- 🐛 **Parameter Loss**: Resolved issue where node configuration parameters (from `workflow.add_node()`) were never passed to nodes
- 🐛 **Docker/FastAPI Impact**: Fixed recommended runtime for Docker deployments being completely non-functional

#### Changed

- ⚡ **Pattern Alignment**: AsyncLocalRuntime now follows same pattern as LocalRuntime (calls `execute_async()` which merges config at base_async.py:190)
- ⚡ **Resource Registry Handling**: Resource registry now passed via inputs dict instead of separate parameter

#### Added

- ✅ **Regression Tests**: Comprehensive test suite ensuring parameter passing stays fixed (tests/runtime/test_async_local_bug_fix_v0926.py)
- ✅ **Integration Tests**: DataFlow integration tests verify end-to-end CRUD operations work correctly

#### Impact

- 🚀 **Success Rate**: DataFlow with AsyncLocalRuntime - 0% → 100% success rate
- 🚀 **Production Ready**: AsyncLocalRuntime now fully functional for Docker/FastAPI deployments
- 🚀 **Backward Compatible**: Pure bug fix - no API changes, existing code works unchanged
- 🚀 **Zero Regressions**: 587/588 runtime tests passing (1 unrelated timeout)

#### Technical Details

**Root Cause**: AsyncLocalRuntime called `node_instance.async_run(**inputs)` directly at async_local.py:753, bypassing `execute_async()` which merges node.config with runtime inputs (base_async.py:190).

**Solution**: Changed async_local.py:745-756 to call `execute_async()` instead, matching LocalRuntime's pattern (local.py:1362):

```python
# Before (BROKEN):
result = await node_instance.async_run(**inputs)

# After (FIXED):
result = await node_instance.execute_async(**inputs)  # Merges config internally
```

**Evidence**: Users independently discovered bug and documented workarounds: "Use LocalRuntime (not AsyncLocalRuntime) - AsyncLocalRuntime has parameter passing bug"

**Full Bug Report**: packages/kailash-dataflow/reports/bugs/014-asynclocalruntime/

### [0.9.25] - 2025-10-15

**CRITICAL: Multi-Node Workflow Threading Fix**

This release resolves a P0 critical bug where all multi-node workflows with connections failed in Docker deployments due to threading issues.

#### Fixed

- 🐛 **CRITICAL: Multi-Node Workflow Threading Bug**: AsyncLocalRuntime now properly overrides `execute()` and `execute_async()` methods to prevent thread creation in async contexts
- 🐛 **Docker Deployment Failures**: Fixed 100% failure rate for multi-node workflows in Docker/FastAPI environments
- 🐛 **Thread Creation in Async Contexts**: Eliminated problematic thread creation when LocalRuntime.execute() was called in async contexts
- 🐛 **MemoryError in Docker**: Resolved file descriptor issues causing MemoryError in containerized deployments

#### Changed

- ⚡ **Performance Improvement**: Multi-node workflow execution time reduced from timeout (>2min) to ~1.4 seconds
- ⚡ **Async Context Detection**: Added helpful error message when execute() called from async context, guiding users to execute_workflow_async()
- ⚡ **DataFlow Version**: Bumped to 0.5.4 for consistency with release cycle

#### Added

- ✅ **Method Overrides**: AsyncLocalRuntime.execute() and execute_async() now properly override parent methods
- ✅ **CLI Context Support**: execute() uses asyncio.run() in CLI contexts (no event loop)
- ✅ **Comprehensive Testing**: 84/84 tests passing (8 custom tests + 76 regression tests)

#### Impact

- 🚀 **Success Rate**: Multi-node workflows - 0% → 100% success rate in Docker
- 🚀 **Execution Speed**: 99%+ faster execution (~1.4s vs >2min timeout)
- 🚀 **Production Ready**: All Example-Project workflows now functional
- 🚀 **Backward Compatible**: Fully compatible with existing code patterns

#### Technical Details

**Root Cause**: AsyncLocalRuntime inherited execute() from LocalRuntime without overriding it, causing thread creation (line 808 in local.py) when called in Docker/FastAPI async contexts.

**Solution**: Added two method overrides in AsyncLocalRuntime (src/kailash/runtime/async_local.py:374-452):

1. `execute()` - Uses asyncio.run() in CLI context, raises helpful error in async context
2. `execute_async()` - Delegates to execute_workflow_async() (pure async, no threads)

**Full Details**: [PR #411](https://github.com/terrene-foundation/kailash-py/pull/411)

### [0.9.20] - 2025-10-06

**Provider Registry Fix & Multi-Modal Support Release**

Critical bug fix enabling custom mock providers and Kaizen AI framework integration, plus enhanced test infrastructure.

#### Fixed

- 🐛 **Mock Provider Bypass**: Removed hardcoded `if provider == "mock"` logic from LLMAgentNode
- 🐛 **Tool Execution Flow**: Unified provider response generation for all providers
- 🐛 **Provider Registry**: All providers now use consistent registry path
- 🐛 **Mock Tool Calls**: MockProvider now generates tool_calls when appropriate
- 🐛 **Test Timeouts**: Marked slow tests with @pytest.mark.slow for CI optimization

#### Added

- ✅ **Custom Mock Provider Support**: Enables signature-aware mock providers (e.g., KaizenMockProvider)
- ✅ **Multi-Modal Foundation**: Foundation for vision/audio processing in Kaizen framework
- ✅ **Enhanced Testing**: 510+ tests passing with custom mock providers
- ✅ **Tool Call Generation**: MockProvider generates mock tool_calls for action-oriented messages

#### Changed

- ⚡ **Consistent Registry Usage**: All providers use `_provider_llm_response()` method
- ⚡ **MockProvider Model**: Always returns "mock-model" to indicate mocked response
- 🧹 **Code Cleanup**: Removed obsolete a2a_backup.py (1,807 lines)

**Full Details**: [v0.9.20 Changelog](sdk-users/6-reference/changelogs/releases/v0.9.20-provider-registry-fix.md)

### [0.9.11] - 2025-08-04

**Testing Excellence & DataFlow Integration Enhancement Release**

This release focuses on testing infrastructure excellence and enhanced DataFlow integration capabilities, achieving a major milestone of 4,000+ passing tier 1 tests.

#### Added

- ✅ **Testing Milestone Achievement**: 4,072 passing tier 1 tests with comprehensive coverage
- ✅ **Enhanced DataFlow Integration**: Improved AsyncSQL node compatibility with DataFlow parameters
- ✅ **Test Infrastructure Hardening**: Better test isolation and cleanup mechanisms
- ✅ **Performance Optimization**: Test execution optimization for development workflows

#### Changed

- 🔄 **Code Quality**: Comprehensive formatting updates with black, isort, and ruff compliance
- 🔄 **Documentation**: Enhanced integration examples and troubleshooting guides
- 🔄 **Test Organization**: Restructured test suite for better maintainability

#### Fixed

- 🐛 **AsyncSQL Parameter Handling**: Improved parameter conversion for DataFlow integration
- 🐛 **Import Order**: Corrected import ordering across test modules
- 🐛 **Connection Management**: Enhanced connection pool handling in test environments

#### Infrastructure

- 🏗️ **Test Excellence**: Achieved comprehensive test coverage milestone
- 🏗️ **CI/CD Readiness**: Enhanced build validation and quality gates
- 🏗️ **Development Experience**: Streamlined development and testing procedures

### [0.8.7] - 2025-01-25 (Unreleased - Superseded)

**MCP Ecosystem Enhancement Release**

This release completes the MCP ecosystem with comprehensive parameter validation, 100% protocol compliance, and enterprise-grade subscriptions.

#### Added

- ✅ **MCP Parameter Validation Tool**: 7 validation endpoints, 28 error types, 132 unit tests
- ✅ **MCP Protocol Compliance**: 4 missing handlers implemented for 100% compliance
- ✅ **MCP Subscriptions Phase 2**: GraphQL optimization, WebSocket compression, Redis coordination
- ✅ **Claude Code Integration**: Full MCP tool integration with configuration guides
- ✅ **A/B Testing Framework**: Legitimate blind testing methodology for validation

### [0.8.6] - 2025-07-22

**Enhanced Parameter Validation & Debugging Release**

#### Added

- ✅ **Enhanced Parameter Validation**: 4 modes (off/warn/strict/debug) with <1ms overhead
- ✅ **Parameter Debugging Tools**: ParameterDebugger provides 10x faster issue resolution
- ✅ **Comprehensive Documentation**: 1,300+ lines of troubleshooting guides

### [0.8.5] - 2025-01-20

**Architecture Cleanup & Enterprise Security Release**

This release removes the confusing `src/kailash/nexus` module, adds comprehensive edge computing infrastructure, implements enterprise-grade connection parameter validation, and introduces advanced monitoring capabilities.

#### Added

- ✅ **Connection Parameter Validation**: Enterprise-grade validation framework with type safety
- ✅ **Edge Computing Infrastructure**: 50+ new nodes for geo-distributed computing
- ✅ **AlertManager**: Proactive monitoring with configurable thresholds
- ✅ **Connection Contracts**: Define and enforce data flow contracts between nodes
- ✅ **Validation Metrics**: Track connection validation performance and failures
- ✅ **Edge Node Discovery**: Automatic discovery and coordination of edge resources
- ✅ **Predictive Scaling**: Resource optimization with predictive algorithms
- ✅ **Comprehensive Monitoring**: Enhanced monitoring patterns and guides

#### Changed

- Updated all documentation to use correct Nexus imports (`from nexus import Nexus`)
- Enhanced LocalRuntime with validation enabled by default
- Improved error messages with validation suggestions
- Updated DataFlow integration to use proper imports

#### Removed

- ⚠️ **BREAKING**: Removed `src/kailash/nexus` module (use `packages/kailash-nexus` instead)
- Removed `tests/integration/test_nexus_framework.py`
- Removed outdated nexus import references from documentation

#### Security

- Enterprise-grade connection parameter validation
- Real-time security event monitoring
- Compliance-aware edge routing
- Enhanced error handling with security considerations

### [0.8.4] - 2025-01-19

**A2A Google Protocol Enhancement Release**

This release implements comprehensive Agent-to-Agent (A2A) communication enhancements with Google protocol best practices, significantly improving multi-agent insight quality and coordination capabilities.

#### Added

- ✅ **Enhanced Agent Cards**: Detailed capability descriptions with performance metrics and collaboration styles
- ✅ **Structured Task Management**: Complete lifecycle management with state machine (CREATED → COMPLETED)
- ✅ **Multi-stage LLM Insight Pipeline**: Quality-focused insight extraction with confidence scoring
- ✅ **Semantic Memory Pool**: Vector embeddings with concept extraction and semantic search
- ✅ **Hybrid Search Engine**: Combines semantic, keyword, and fuzzy matching capabilities
- ✅ **Streaming Analytics**: Real-time performance monitoring and optimization
- ✅ **Comprehensive Testing**: 1,174 lines across 3 new test files (2930/2930 unit tests passing)
- ✅ **A2A Documentation**: Complete cheatsheet and workflow examples
- ✅ **Integration Examples**: Working multi-agent coordination patterns

#### Changed

- Enhanced A2ACoordinatorNode with backward-compatible action-based routing
- Improved insight extraction quality from ~0.6 to >0.8 average scores
- Updated root CLAUDE.md with A2A quick start and multi-step guidance

#### Technical Details

- Full backward compatibility maintained (all existing tests pass)
- Action-based routing preserves legacy API usage patterns
- Integration with existing workflow builder and runtime systems
- No breaking changes, no migration required

### [0.8.3] - 2025-01-18

**SDK Critique Response & Documentation Improvements Release**

This release addresses developer experience issues identified in comprehensive SDK critique, implements critical architectural fixes, and establishes comprehensive documentation structure with Claude Code integration patterns.

#### Added

- ✅ **DataFlow CLAUDE.md**: Comprehensive usage patterns guide (412 lines) for Claude Code integration
- ✅ **Nexus CLAUDE.md**: Multi-channel platform patterns guide (542 lines) for Claude Code integration
- ✅ **Enhanced Connection Error Messages**: Improved validation with helpful suggestions and port discovery
- ✅ **hashlib Support**: Added to PythonCodeNode ALLOWED_MODULES for cryptographic operations
- ✅ **Documentation Structure**: Migrated 90+ missing files from apps/\*/docs/ to sdk-users/4-apps/
- ✅ **Comprehensive API Guidance**: Quick reference system and developer onboarding paths

#### Changed

- 🔄 **Documentation Architecture**: Established apps/\*/docs/ as gold standard for ALL documentation
- 🔄 **API Patterns**: Cleaned up deprecated patterns in core cheatsheet files
- 🔄 **Parameter Access**: Fixed Claude Code patterns to use try/except NameError (not parameters.get())
- 🔄 **Nexus Documentation**: Corrected import paths, method signatures, and API examples

#### Fixed

- 🐛 **CRITICAL: DataFlow-Kailash Integration**: Resolved type annotation incompatibility making DataFlow unusable
- 🐛 **Type Normalization**: Added system to convert complex types (List[str], Optional[str]) to simple types
- 🐛 **NodeParameter Validation**: Fixed ValidationError on all DataFlow models with complex type annotations
- 🐛 **Import Sorting**: Applied isort with black profile across all modified files
- 🐛 **Documentation Links**: Fixed broken references and navigation paths

#### Impact

- 🚀 **DataFlow Usability**: Made DataFlow usable in real-world scenarios (91.7% success rate)
- 🚀 **Claude Code Integration**: Enabled correct implementation of both frameworks on first try
- 🚀 **Developer Experience**: Eliminated frustration through comprehensive documentation access
- 🚀 **Architecture Validation**: Confirmed sophisticated design patterns enable enterprise features

#### Package Updates

- **kailash-dataflow**: 0.1.0 → 0.1.1 (critical bug fix)
- **kailash-nexus**: 1.0.0 → 1.0.1 (documentation fixes)
- **kailash**: 0.8.1 → 0.8.3 (comprehensive improvements)

### [0.8.0] - 2025-01-17

**Test Infrastructure & Quality Improvements Release**

This release focuses on comprehensive test infrastructure improvements, systematic test fixing, and better SDK organization for enhanced developer experience and CI/CD reliability.

#### Added

- ✅ **Centralized Node Registry Management**: New `node_registry_utils.py` for consistent test isolation
- ✅ **Automatic Timeout Enforcement**: `conftest_timeouts.py` with 1s/5s/10s timeout compliance
- ✅ **TODO System Organization**: Clear separation between completed infrastructure work (TODO-111c) and remaining feature implementation (TODO-115)
- ✅ **Comprehensive Test Documentation**: Updated CLAUDE.md with execution patterns and test directives
- ✅ **Node Execution Pattern Guide**: `node-execution-pattern.md` clarifying run() vs execute()

#### Changed

- 🔄 **Test Infrastructure Overhaul**: Fixed test execution problems that were masking real functionality issues
- 🔄 **Improved Test Isolation**: All tests now use proper process isolation with `--forked` requirement
- 🔄 **Enhanced Performance**: Reduced test execution times from 10s/5s/2s to 0.1-0.2s across multiple test files
- 🔄 **Better Error Handling**: Fixed Ruff violations, circuit breaker timeouts, and eval() usage patterns

#### Fixed

- 🐛 **Test Timeout Issues**: Resolved hanging tests and timeout violations across all test tiers
- 🐛 **FastMCP Import Timeout**: Fixed MCP server test timing out due to slow external imports
- 🐛 **Import Order Dependencies**: Resolved circular import test subprocess timeout issues
- 🐛 **BehaviorAnalysisNode**: Fixed risk scoring, email alerts, and webhook functionality
- 🐛 **AsyncSQL Compatibility**: Fixed aioredis compatibility issues for Python 3.12
- 🐛 **NetworkDiscovery**: Fixed datagram_received for proper async/sync handling
- 🐛 **API Gateway Tests**: Resolved NodeRegistry empty state issues

#### Infrastructure

- 🏗️ **CI/CD Readiness**: Achieved 100% test infrastructure readiness for merge and deployment
- 🏗️ **Test Quality Assurance**: 2798 passed tests with proper isolation and timeout compliance
- 🏗️ **Code Quality**: Fixed all linting violations and improved code consistency
- 🏗️ **Docker E2E Optimization**: Reduced from 50000→500 operations, 100→10 workers for faster execution

#### Security

- 🔒 **Enhanced Security Testing**: Improved security node test coverage and validation
- 🔒 **Better Timeout Handling**: Prevents test hangs that could mask security issues

### [0.7.0] - 2025-07-10

**Major Framework Release: Complete Application Ecosystem & Infrastructure Hardening**

**🚀 New Framework Applications:**

- **DataFlow Framework**: Complete standalone ETL/database framework with 100% documentation validation
  - 4 production-ready example applications (simple CRUD, enterprise, data migration, API backend)
  - MongoDB-style query builder with Redis caching
  - Comprehensive testing infrastructure with Docker/Kubernetes deployment
- **Nexus Multi-Channel Platform**: Enterprise orchestration supporting API, CLI, and MCP interfaces
  - Complete application structure with enterprise features (multi-tenant, RBAC, marketplace)
  - 105 tests with 100% pass rate and production deployment ready
  - Unified session management across all channels

**🔧 Enterprise Resilience & Monitoring:**

- **Distributed Transaction Management**: Automatic pattern selection (Saga/2PC) with compensation logic
  - 122 unit tests + 23 integration tests (100% pass rate)
  - State persistence with Memory, Redis, and PostgreSQL backends
  - Enterprise-grade recovery and monitoring capabilities
- **Transaction Monitoring System**: 5 specialized monitoring nodes for production environments
  - TransactionMetricsNode, TransactionMonitorNode, DeadlockDetectorNode, RaceConditionDetectorNode, PerformanceAnomalyNode
  - 219 unit tests + 8 integration tests (100% pass rate)
  - Complete documentation with enterprise patterns

**🗄️ Data Management Enhancements:**

- **MongoDB-Style Query Builder**: Production-ready query builder with cross-database support
  - Supports PostgreSQL, MySQL, SQLite with MongoDB-style operators ($eq, $ne, $lt, $gt, $in, $regex)
  - 33 unit tests + 8 integration tests with automatic tenant isolation
- **Redis Query Cache**: Enterprise-grade caching with pattern-based invalidation
  - 40 unit tests with TTL management and tenant isolation
  - Multiple invalidation strategies and performance optimization

**🤖 AI & MCP Enhancements:**

- **Real MCP Execution**: Default behavior for all AI agents (breaking change from mock execution)
  - IterativeLLMAgent and LLMAgentNode now use real MCP tools by default
  - Enhanced error handling and protocol compliance
  - Backward compatibility with `use_real_mcp=False` option

**📚 Documentation & Standards:**

- **Complete Documentation Validation**: 100% test pass rate across all examples
  - Updated all frameworks with standardized documentation structure
  - Created comprehensive validation framework for all code examples
  - Application documentation standards across DataFlow and Nexus

**🏗️ Infrastructure Enhancements (TODO-109):**

- **Enhanced AsyncNode Event Loop Handling**: Thread-safe async execution with automatic event loop detection
  - Fixed "RuntimeError: no running event loop" in threaded contexts
  - Smart detection and handling of different async contexts
  - Zero performance impact with improved stability
- **Monitoring Node Operations**: Added 8 new operations across 4 monitoring nodes
  - `complete_transaction`, `acquire_resource`, `release_resource` (aliases for compatibility)
  - `request_resource`, `initialize`, `complete_operation` (new operations)
  - Automatic success rate calculations in all monitoring responses
- **E2E Test Infrastructure**: Achieved 100% pass rate (improved from 20%)
  - Fixed all infrastructure gaps preventing test success
  - Enhanced schema validation with backward-compatible aliases
  - Stable Docker test environment (PostgreSQL:5434, Redis:6380)

**🔧 Technical Improvements:**

- **Gateway Architecture Cleanup**: Renamed server classes for clarity
  - WorkflowAPIGateway → WorkflowServer
  - DurableAPIGateway → DurableWorkflowServer
  - EnhancedDurableAPIGateway → EnterpriseWorkflowServer
- **Version Consistency**: Fixed version synchronization across all package files
- **Test Suite Excellence**: 2,400+ tests passing with comprehensive coverage
  - Unit: 1,617 tests (enhanced with infrastructure tests)
  - Integration: 233 tests (including new monitoring tests)
  - E2E: 21 core tests (100% pass rate achieved)

**Breaking Changes:**

- Real MCP execution is now default for AI agents (can be disabled with `use_real_mcp=False`)
- Gateway class names updated (backward compatibility maintained with deprecation warnings)

**Migration Guide:**

- DataFlow and Nexus are new frameworks - no migration needed
- MCP execution change requires explicit `use_real_mcp=False` if mock execution is needed
- Gateway class renames are backward compatible
- Infrastructure enhancements require no code changes - all improvements are transparent
- New monitoring operations are additive - existing code continues to work
- See [migration-guides/version-specific/v0.6.6-infrastructure-enhancements.md](sdk-users/6-reference/migration-guides/version-specific/v0.6.6-infrastructure-enhancements.md) for details

### [0.6.6] - 2025-07-08

**AgentUIMiddleware Shared Workflow Fix & API Standardization**

**Fixed:**

- **AgentUIMiddleware Shared Workflow Execution**: Shared workflows registered with `make_shared=True` couldn't be executed from sessions. Now automatically copied to sessions when first executed.

**Changed:**

- **API Method Standardization**: Deprecated `AgentUIMiddleware.execute_workflow()` in favor of `execute()` for consistency with runtime API

**Enhanced:**

- **Documentation**: Updated Agent-UI communication guide with shared workflow behavior section
- **Testing**: Added 4 comprehensive integration tests for shared workflow functionality
- **Migration Guide**: Added v0.6.5+ migration guide explaining the fix

**Breaking Changes:** None - fully backward compatible

### [0.6.5] - 2025-07-08

**Enterprise AsyncSQL Enhancements & Production Testing**

**Major Features:**

- **AsyncSQL Transaction Management**: Auto, manual, and none modes for precise control
- **Optimistic Locking**: Version-based concurrency control with conflict resolution
- **Advanced Parameter Handling**: PostgreSQL ANY(), JSON, arrays, date/datetime support
- **100% Test Pass Rate**: All AsyncSQL tests passing with strict policy compliance

**Fixed:**

- **PostgreSQL ANY() Parameters**: Fixed list parameter conversion for array operations
- **DNS/Network Error Retries**: Added missing error patterns for network failures
- **Optimistic Locking Version Check**: Fixed WHERE clause detection for version validation
- **E2E Transaction Timeouts**: Added timeout configurations to prevent deadlocks

**Enhanced:**

- **Testing Infrastructure**: Removed ALL mocks from integration tests (policy compliance)
- **Documentation Quality**: Complete AsyncSQL enterprise patterns with validated examples
- **Connection Pool Sharing**: Event loop management for shared pools across instances

**Breaking Changes:** None - fully backward compatible

### [0.6.4] - 2025-07-06

**Enterprise Parameter Injection & E2E Test Excellence**

**Major Features:**

- **Enterprise Parameter Injection**: WorkflowBuilder `add_workflow_inputs()` with dot notation support
- **E2E Test Excellence**: 100% pass rate on all comprehensive E2E tests
- **Documentation Quality**: Updated based on E2E test findings with correct patterns

**Fixed:**

- **Permission Check Structure**: Fixed nested result structure (`result.check.allowed`)
- **PythonCodeNode Parameters**: Direct namespace injection now working correctly
- **Integration Test Stability**: Improved cache handling and async node behavior

**Enhanced:**

- **Test Infrastructure**: Achieved 100% E2E test pass rate with improved stability
- **Documentation Updates**: Comprehensive updates based on E2E test findings
- **Parameter Injection**: Enterprise-grade system with complex workflow support

**Breaking Changes:** None - fully backward compatible

### [0.6.3] - 2025-07-05

**Comprehensive MCP Platform, Testing Infrastructure & Documentation Quality**

**Major Features:**

- **MCP Testing Infrastructure**: 407 comprehensive tests (391 unit, 14 integration, 2 E2E) with 100% pass rate
- **MCP Tool Execution**: Complete LLMAgent automatic tool execution with multi-round support
- **Enterprise MCP Testing**: 4 E2E tests with custom enterprise nodes for real-world scenarios
- **Documentation Validation**: Framework achieving 100% test pass rate across all patterns

**Fixed:**

- **MCP Namespace Collision**: Resolved critical import error (`kailash.mcp` → `kailash.mcp_server`)
- **Core SDK Issues**: EdgeDiscovery, SSOAuthenticationNode, PythonCodeNode, StreamPublisherNode fixes
- **Documentation**: 200+ pattern corrections ensuring all examples work correctly

**Enhanced:**

- **Migration Guide Consolidation**: Unified location at `sdk-users/6-reference/migration-guides/`
- **MCP Platform Unification**: Created `apps/mcp_platform/` from 6 scattered directories
- **Documentation Quality**: 100% coverage (up from 72.7%), all examples validated
- **API Design**: Clean server hierarchy with backward compatibility

**Breaking Changes:** None - fully backward compatible

### [0.6.2] - 2025-07-03

See [sdk-users/6-reference/changelogs/releases/v0.6.2-2025-07-03.md](sdk-users/6-reference/changelogs/releases/v0.6.2-2025-07-03.md) for full details.

**Key Features:** LLM integration enhancements with Ollama backend_config support, 100% test coverage across all tiers, comprehensive documentation updates

### [0.6.1] - 2025-01-26

See [sdk-users/6-reference/changelogs/releases/v0.6.1-2025-01-26.md](sdk-users/6-reference/changelogs/releases/v0.6.1-2025-01-26.md) for full details.

**Key Features:** Critical middleware bug fixes, standardized test environment, massive CI performance improvements (10min → 40sec)

### [0.6.0] - 2025-01-24

See [sdk-users/6-reference/changelogs/releases/v0.6.0-2025-01-24.md](sdk-users/6-reference/changelogs/releases/v0.6.0-2025-01-24.md) for full details.

**Key Features:** User Management System, Enterprise Admin Infrastructure

### [0.5.0] - 2025-01-19

See [sdk-users/6-reference/changelogs/releases/v0.5.0-2025-01-19.md](sdk-users/6-reference/changelogs/releases/v0.5.0-2025-01-19.md) for full details.

**Key Features:** Major Architecture Refactoring, Performance Optimization, API Standardization

### [0.4.2] - 2025-06-18

See [sdk-users/6-reference/changelogs/releases/v0.4.2-2025-06-18.md](sdk-users/6-reference/changelogs/releases/v0.4.2-2025-06-18.md) for full details.

**Key Features:** Circular Import Resolution, Changelog Organization

### [0.4.1] - 2025-06-16

See [sdk-users/6-reference/changelogs/releases/v0.4.1-2025-06-16.md](sdk-users/6-reference/changelogs/releases/v0.4.1-2025-06-16.md) for full details.

**Key Features:** Alert Nodes System, AI Provider Vision Support

### [0.4.0] - 2025-06-15

See [sdk-users/6-reference/changelogs/releases/v0.4.0-2025-06-15.md](sdk-users/6-reference/changelogs/releases/v0.4.0-2025-06-15.md) for full details.

**Key Features:** Enterprise Middleware Architecture, Test Excellence Improvements

### [0.3.2] - 2025-06-11

See [sdk-users/6-reference/changelogs/releases/v0.3.2-2025-06-11.md](sdk-users/6-reference/changelogs/releases/v0.3.2-2025-06-11.md) for full details.

**Key Features:** PythonCodeNode Output Validation Fix, Manufacturing Workflow Library

### [0.3.1] - 2025-06-11

See [sdk-users/6-reference/changelogs/releases/v0.3.1-2025-06-11.md](sdk-users/6-reference/changelogs/releases/v0.3.1-2025-06-11.md) for full details.

**Key Features:** Complete Finance Workflow Library, PythonCodeNode Training Data

### [0.3.0] - 2025-06-10

See [sdk-users/6-reference/changelogs/releases/v0.3.0-2025-06-10.md](sdk-users/6-reference/changelogs/releases/v0.3.0-2025-06-10.md) for full details.

**Key Features:** Parameter Lifecycle Architecture, Centralized Data Management

For complete release history, see [changelogs/README.md](changelogs/README.md).
