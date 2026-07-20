# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.58.0] - 2026-07-20

### Added (EATP Trust Plane)

- **Cross-SDK canonical delegation-signing pre-image engine (#1841).** New
  `kailash.trust.signing.delegation_payload` module: `SigningPayloadVersion`
  enum (`v1-legacy` / `v2-complete` / `v3-complete` — wire tokens matching the
  Rust SDK's `delegation.rs::SigningPayloadVersion`) plus
  `delegation_signing_payload()`, the version-gated canonical pre-image
  builder shared across the V1 (legacy), V2 (complete-constraint), and V3
  (multi-sig) signing shapes. `DelegationRecord` gains a new
  `signing_payload_version: str` field (default `"legacy-python-v0"`,
  excluded from the signing pre-image itself) — every existing record signs
  and verifies byte-identically to before this release.
  `kailash.trust.signing.delegation_record_signing` adds the SINGLE shared
  sign/verify dispatch (`delegation_canonical_payload_str()`) every
  delegation call site routes through: it returns the legacy pre-image for a
  `legacy-python-v0` record and fails closed
  (`UnsupportedSigningPayloadVersionError`) for any other declared version —
  **the record-persisted `v2-complete`/`v3-complete` sign/verify path is NOT
  wired yet** (a later shard, S2b, once the structured constraint /
  resource-limit / scope data those pre-images need is persisted on the
  record). The v2/v3 engine itself IS usable today via the additive bridge
  `build_delegation_signing_input()` / `delegation_record_signing_payload()`,
  which maps a record's existing fields plus caller-supplied structured data
  onto the engine pre-image directly — exercised now for cross-SDK
  conformance, not yet reachable by setting a record's
  `signing_payload_version` field.

- **Signed revocation ledger + owner-signed anti-rollback anchor (#1842).**
  Three new modules under `kailash.trust.revocation`: `signed_ledger.py`
  (`SignedRevocationEvent`, `RevocationLedger`, `revocation_ledger_tip()` —
  a signed, append-only revocation event log with a foldable tip hash),
  `head_commitment.py` (`HeadCommitment`, `HeadCommitmentAnchor` — an
  owner-signed epoch anchor giving the ledger durable anti-rollback /
  same-epoch equivocation protection), and `verify.py`
  (`SignedRevocationVerifier`, `SignedRevocationStore`,
  `DurableHighWaterStore` — the authoritative verify path that now consults
  the signed ledger instead of trusting an unsigned revocation list).
  `TrustOperations` gains an optional `revocation_verifier:
SignedRevocationVerifier | None = None` constructor parameter; the default
  `None` preserves the pre-existing (unsigned) revocation-check behavior
  exactly, with a one-time `WARN`-level log noting the authoritative
  signed-ledger path is available but not configured. Passing a configured
  `SignedRevocationVerifier` makes ledger consultation authoritative and
  fail-closed.

### Changed

- **`kailash.trust.pact.governance_posture` coverage docstring extended
  (#1803).** Documentation-only change describing the additional kaizen
  provider/backend egress chokepoints (Azure AI Foundry, document-extraction
  vision providers, multi-modal adapters, the legacy standalone Ollama
  provider) now gated by `enforce_governance_posture` — see the
  `kailash-kaizen` 2.38.0 CHANGELOG entry for the actual enforcement change.
  No functional or public-API change to `kailash` itself.

## [2.57.0] - 2026-07-20

### Added (Security)

- **PKCE (S256) + `id_token` nonce enforcement primitives land on
  `BaseSSOProvider`; the SSO provider suite adopts them (#1834).**
  `generate_pkce_pair()` (RFC 7636 `code_verifier`/`code_challenge` pair) and
  a `supports_id_token` flag are now available on every SSO provider in
  `kailash.trust.auth.sso`. The google/azure/apple providers enforce the OIDC
  `nonce` claim against JWKS-verified id_token claims (`_enforce_nonce`,
  built on the JWKS-backed verifier from #1835); GitHub — which issues no
  OIDC id_token — sets `supports_id_token = False` and adopts PKCE only.
  `SSOAuthenticationNode`'s azure/google/okta initiators now mint and cache a
  nonce per authorization request, activating #1835's callback-side nonce
  enforcement for the node-based SSO flow.

## [2.56.0] - 2026-07-19

### Security

- **SSO `id_token` is now cryptographically verified via JWKS before its
  `nonce` claim is trusted (#1835).** `SSOAuthenticationNode` previously read
  the OIDC `nonce` claim from an id_token decoded with base64url only — no
  signature, audience, issuer, or expiry check — so a forged id_token
  carrying the expected nonce was trusted at the callback (#1815 added nonce
  enforcement + PKCE but compared the nonce against claims that were never
  cryptographically verified). A new JWKS-backed verifier (RS256/ES256 +
  `aud`/`iss`/expiry) now runs before the nonce comparison; the base64url
  decode is retained only as a display-only helper and is no longer on the
  trust path. Fail-closed: a missing JWKS/issuer/client_id config, an
  unreachable JWKS endpoint, or any verification failure (including
  network/library errors outside PyJWT's own exception hierarchy) raises a
  typed `ValueError` and rejects the login — there is no fallback to the
  unverified read.
  **Migration:** deployments using the id_token-nonce SSO flow MUST now
  provide `jwks_uri` + `issuer` + `client_id` in `oauth_settings`; without
  them the callback fails closed (rejects) rather than trusting an
  unverified token.

### Added

- **`kailash.utils.url_credentials.mask_error_text` — a DOTALL-aware
  credential scrubber for opaque exception text (#1840).** `mask_url` masks
  a URL value in hand; an exception rendered into `f"...{e}"` is an opaque
  string that may embed a credential-bearing URL anywhere inside it, so it
  cannot route through `mask_url`'s `urlparse`-based path. The new helper
  scrubs `user:pass@host` userinfo and sensitive query params
  (`?token=`/`&password=`/...) out of arbitrary strings via a `re.DOTALL`
  regex — drivers/providers render an embedded newline in a credential value
  literally into error text, and a naive `\S`/`[^\s]` value class stops at
  the first `\n` and leaks the credential tail; the userinfo class used here
  includes `\n` (bounded by real URL host delimiters) and backtracks to the
  last `@` before the host, so a password with an embedded newline or a raw
  `@` is masked whole, never split. This is the one shared credential-helper
  module (`security.md` § "No secrets in logs") — no per-adapter copies.
  Companion fixes routing through this helper: `kailash-mcp` 0.4.1
  (SSE/StreamableHTTP/WebSocket transport connect/send/receive logs +
  server-session close / read-loop error logs) and `kailash-kaizen` 2.37.2
  (Ollama provider exception logs).

## [2.55.0] - 2026-07-19

### Added (Security)

- **OIDC SSO enforces PKCE S256 + `nonce` validation on the authorization-code
  flow (#1815).** `kailash.nodes.auth.sso` now generates an RFC 7636
  `code_verifier` / `code_challenge` (S256) pair for every authorization
  request and sends `code_challenge_method=S256`, closing the authorization-code
  interception gap on public/native clients. A random `nonce` is minted at
  authorization time and cached alongside the PKCE verifier; on token exchange,
  the returned `id_token`'s `nonce` claim MUST be present and MUST match the
  minted value via a constant-time comparison (`hmac.compare_digest`) — a
  missing `id_token` or a `nonce` mismatch rejects the login. Closes the OIDC
  id_token replay/injection defense gap.

## [2.54.0] - 2026-07-18

### Added

- **`governance_required` posture for direct LLM egress (#1779, EATP D6 parity;
  kailash 2.54.0 / kailash-kaizen 2.35.0 / kaizen-agents 0.10.0).** An opt-OUT
  process/env posture that makes ungoverned direct-LLM egress fail-closed.
  New core API: `kailash.is_governance_required()` / `kailash.set_governance_required()`
  (resolution: programmatic override → `KAILASH_GOVERNANCE_REQUIRED` env truthy
  in `{1,true,yes,on}` → default OFF; unrecognized env → OFF, byte-identical to
  today) and the typed `kailash.UngovernedEgressRefused` error (naming both
  remedies). When ACTIVE, a bare un-governed client/agent that would make REAL
  egress is refused at construction (and, defense-in-depth, at real-transport
  binding) unless the caller passes `ungoverned=True`; mock/deterministic paths
  are exempt by class identity, never a network probe. Enforced from Kaizen at
  every egress chokepoint: the four-axis `LlmClient` (all constructors + lazy
  re-check), `Agent`, `LLMAgentNode` (both node-config builders + the legacy
  provider-chat fallback), `EmbeddingGeneratorNode` (four-axis + ollama
  fallback), `BaseAgent`, and the `kaizen-agents` orchestration subsystem
  (`kaizen_agents.llm.LLMClient` chokepoint). `ungoverned=True` is available on
  every one of those construction surfaces. OFF by default → zero back-compat
  break to adopt.

### Deprecated

- **kailash-kaizen: legacy `from_env()` per-provider-key auto-detect tier
  (#1721/#1720).** `LlmClient.from_env()` resolves through three tiers —
  `KAILASH_LLM_DEPLOYMENT` URI > `KAILASH_LLM_PROVIDER` preset selector >
  legacy per-provider `*_API_KEY` auto-detect (`OPENAI_API_KEY`,
  `AZURE_OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`,
  `DEEPSEEK_API_KEY`). The legacy tier is a backward-compat layer preserving
  the old `autoselect_provider()` behavior, and is where the #1721 cross-SDK
  key-list divergence lives (this SDK's 5 legacy keys including Azure vs.
  the Rust SDK's 10, without Azure) — the canonical URI/selector surface is
  already cross-SDK-aligned, so the root-cause fix retires the legacy tier
  rather than reconciling the two key-lists. Resolving via the legacy tier
  ALONE (no URI, no selector configured) now emits a `DeprecationWarning`
  plus a structured `llm_client.migration.legacy_key_autodetect_deprecated`
  `WARNING` log line naming the detected env var and the canonical migration
  path (`KAILASH_LLM_PROVIDER=<preset>`, e.g. `openai` / `anthropic` /
  `google` / `deepseek` / `azure_openai`, or a `KAILASH_LLM_DEPLOYMENT` URI).
  This is the start of the deprecation cycle only (zero-tolerance.md Rule
  6a) — resolution behavior is unchanged this release; the legacy tier still
  resolves and will be removed in a future release. The pre-existing
  `llm_client.migration.legacy_and_deployment_both_configured` coexistence
  warning (a legacy key set alongside a URI/selector) is unchanged.
  `kaizen.llm.from_env.LEGACY_KEY_ORDER` (the 5-entry key list) is
  unmodified — this is a deprecation of the tier, not a reconciliation of
  the key lists.

## [2.53.0] - 2026-07-15

### Security

- **Fail-closed MCP local-server spawn allowlist in the core transports**
  (#1712). The `channels/mcp` `StdioTransport` and the `middleware/mcp` client
  now reject an unlisted spawn command by default (previously fail-open), per
  the MCP 2025-11-25 local-server spawn-safety requirement, with an
  `allow_arbitrary_commands` opt-out.

### Fixed

- **Trust-plane MCP server (`EATPMCPServer`) negotiates `protocolVersion`**
  instead of returning a hardcoded `2024-11-05` (#1712) — echoes a supported
  requested version, else the newest supported.

## [2.52.0] - 2026-07-15

### Security

- **Fail-closed resource bounds on the BH3 origin-digest trust ingress
  (DoS) (#1713).** The shared canonicalization ingress
  (`kailash.trust._jcs.jcs_encode`) previously ran two unbounded recursive
  passes plus a SHA-256 digest over attacker-shaped `Any` input **before**
  any authentication check — an unauthenticated caller could trigger
  unbounded CPU/memory via deep nesting (uncaught `RecursionError`) or
  wide/large payloads (huge lists, multi-GB strings). A new iterative,
  non-recursive bounds guard (`_check_digest_bounds`) rejects over-limit
  input (traversal depth, node count, child count, cumulative string
  bytes) with a typed `ValueError` before any unbounded work begins.
  Placed at the shared ingress, the guard covers every
  attacker-influenceable caller in one pass — the BH3 origin digest, the
  Audit-Anchor `subject_hash` path, and the weft/bilateral/attestation
  content-hash paths. In-bounds input digests byte-identically; no
  cross-SDK byte change.

- **Chain-integrity, expiry, and genesis verification before
  capability/lineage mint (#1710).** `delegate()` and `audit()` — the two
  surfaces that mint a signed, portable artifact from a _stored_ trust
  chain — previously checked expiry inconsistently (`audit()` checked
  nothing at all) and never re-verified chain integrity before signing,
  so a relying party trusting the signed artifact off-chain could be
  handed a mint produced from a tampered chain or an already-expired
  grant. Both surfaces now route through one shared fail-closed pre-sign
  gate that requires a verifiable genesis issuer, rejects an expired
  grant, and re-verifies the Ed25519 signature chain before any signature
  is produced. Valid, unexpired, genesis-anchored chains mint
  byte-identically — this is a cross-SDK-aligned fix (independent
  implementation, matching semantics) with the Rust SDK.

## [2.51.0] - 2026-07-14

### Added

- **Core-SDK per-connection credential callback for token-based DB auth
  (#1741).** `kailash.nodes.data.async_sql.DatabaseConfig` now accepts an
  optional `credential_provider: Optional[Callable[[], str]]` — a zero-arg
  callable that mints a fresh password/token on **every** physical connection
  the core `AsyncSQLDatabaseNode` / `PostgreSQLAdapter` pool opens (initial
  fill, recycle, overflow, reconnect). This is the pool the `db.express` /
  `db.transactions` CRUD hot path actually opens — DataFlow rides the callback
  in through `_get_or_create_async_sql_node`. New shared helper
  `kailash.nodes.data.credential_provider.build_asyncpg_credential_connect`
  installs asyncpg's per-connection `connect` hook; it is fail-closed (a
  raising / non-str provider raises `NodeExecutionError` and NEVER falls back
  to a stale token), never logs the token, sets it as the driver `password`
  param (never re-encoded into a DSN — tokens containing `&=/%` need no
  percent-encoding), and severs the provider-exception cause chain. Absent the
  callback, behavior is unchanged. Companion to kailash-dataflow 2.18.0, which
  extends the same callback across every DataFlow connection path.

Observability program (#1708) — a coordinated 5-package release. Configures
the previously-inert OpenTelemetry provider layer, unifies every server's
`/metrics` exposition onto one Prometheus endpoint, and closes a set of
unbounded-cardinality metric labels found across the runtime, pool, and ML
observability code.

### Added

- **OTLP + Prometheus provider bootstrap (#1708 W1a).** New
  `kailash.observability.otlp.configure_observability()` installs the global
  OTel `MeterProvider` / `TracerProvider` / `LoggerProvider` — the SDK already
  created OTel metric instruments (the workflow `MetricsBridge`, trust, and ML
  observability code) and tracer spans, but nothing configured the global
  providers, so every instrument recorded into the default no-op provider and
  exported nowhere. `configure_observability()` installs a `Resource`
  (`service.name`/`service.version` on every signal), a Prometheus exposition
  reader (bridges OTel metrics into the `prometheus_client` registry so one
  `/metrics` scrape exports both OTel-emitted and `prometheus_client`-native
  metrics), and an OTLP exporter for metrics + traces (+ optional logs) gated
  on `OTEL_EXPORTER_OTLP_ENDPOINT`. Degrades to a documented no-op when the
  `kailash[telemetry]` extra is absent — never raises. Adds
  `opentelemetry-exporter-prometheus` to the `[telemetry]` extra.
- **Canonical workflow RED metrics via the OTel `MetricsBridge` (#1708 W1f).**
  `LocalRuntime` and `AsyncLocalRuntime` now emit a real workflow-execution
  Rate/Errors/Duration histogram (`workflow.duration`, bounded labels) through
  the OTel bridge instead of the previous ad-hoc counters.
- **Real connection-pool acquire-wait histogram (#1708 W1c).** Pool
  acquire-wait latency is now a real histogram reachable from the production
  `/metrics` endpoint (`connection_metrics_router`), closing a USE-completeness
  gap where the metric existed but was never wired to a scrape target.

### Changed

- **Unified server `/metrics` exposition (#1708 W1b).** `workflow_server` and
  `enterprise_workflow_server` now expose ONE Prometheus endpoint aggregating
  every metric source (OTel bridge, connection pool, ML observability)
  instead of each server maintaining its own partial exposition.
- **Pool idle/exhaustion counters reach the production `/metrics` endpoint
  (#1708 G1).** Previously computed but not exposed on the
  `enterprise_workflow_server` production path.

### Fixed

- **Unbounded metric-label cardinality closed across the runtime, ML, and
  OTLP surfaces (#1708 W1d/W1e/G1/redteam).** Several metric label
  dimensions could grow without bound under real traffic, each capable of
  exhausting a Prometheus scrape target's memory over time:
  - Dropped the unbounded `workflow_id` label from the workflow-execution
    metric (W1d) — cardinality now scales with workflow _definitions_, not
    every run.
  - Bounded non-tenant ML observability labels (W1e) and the ML drift
    _severity_ label to a fixed whitelist (G1).
  - Bounded `workflow.name` cardinality and fixed node-histogram bucket
    boundaries (G1).
  - Bounded the internal working set of the top-N label bucketer itself
    (G1) — the bucketer used to track cardinality was, itself, unbounded.
  - Masked embedded credentials before logging the configured OTLP endpoint
    (redteam finding) — a credential-bearing `OTEL_EXPORTER_OTLP_ENDPOINT`
    no longer appears verbatim in logs.

### Removed

- **Orphaned enterprise-monitoring adapter deleted (#1708 G1).**
  `LocalRuntime.enterprise_monitoring` (a property that lazily constructed an
  `EnterpriseMonitoringManager`) and the `PrometheusAdapter` /
  `DataDogAdapter` / `MockMetric` / `EnterpriseMonitoringManager` classes in
  `kailash.runtime.monitoring.runtime_monitor` are deleted. This subsystem had
  zero production callers and was never wired to any real metrics backend —
  `EnterpriseMonitoringManager.record_workflow_execution` /
  `record_resource_usage` were unreachable dead code, and nothing in `src/`
  ever read the `enterprise_monitoring` property. The real workflow RED
  metrics now ship via the OTel `MetricsBridge` (W1f) and unified `/metrics`
  (W1b) instead. **Migration note:** if any downstream code accessed
  `runtime.enterprise_monitoring` directly, it must migrate to the OTel-based
  metrics described above — the property is gone, not deprecated. The
  `enable_enterprise_monitoring` constructor flag on `LocalRuntime` is
  unaffected and still drives auto-enabling resource/retry defaults.

### Dependencies

- Sub-package floors (`kailash-nexus`, `kailash-dataflow`, `kailash-kaizen`,
  `kailash-mcp`) bump their `kailash` dependency floor to `>=2.50.0` — each
  sub-package's #1708 metric now reaches this release's unified `/metrics`
  exposition, and the floor bump makes that a resolvable install-time
  guarantee rather than an implicit assumption.

## [2.49.0] - 2026-07-13

### Fixed

- **Delegate conformance vectors now ship in the wheel — `load_canonical()`
  works for pip-installed consumers (#1532 RC1).** The canonical conformance
  vector set was located at `tests/fixtures/delegate-conformance/canonical.json`
  — under `tests/`, which is never packaged into the wheel — so
  `kailash.delegate.conformance.ConformanceVectorLoader.load_canonical()` raised
  `FileNotFoundError` for every `pip install`ed consumer (it resolved the fixture
  by walking up from `__file__` for a `tests/` path that only exists in a source
  checkout). The vectors now ship as package data at
  `kailash/delegate/conformance/data/canonical.json` and `load_canonical()`
  resolves them via `importlib.resources`, working identically from a source
  checkout and an installed wheel. Digest-integrity (tamper-evidence) and the 5
  canonical vectors (DV-3/5/7/9/10) are unchanged.

### Changed

- **Connector-authoring surface consolidated onto `kailash.delegate` (#1532
  RC2).** Ten connector-authoring symbols previously exported only from
  `kailash.delegate.dispatch` are now re-exported from the top-level
  `kailash.delegate` package: `Principal`, `SignedActionEnvelope`,
  `AttestedReadReceipt`, `RevocationChannel`, `KnowledgeLedger`, `AuthVerifier`,
  `SignatureContract`, `LegacyInvokeConnector`, `DispatchSignatureError`,
  `DispatchSignerError`. A connector now depends on one stable import surface
  (`kailash.delegate`) instead of importing from `.dispatch` directly. Purely
  additive — no existing import path changes.

## [2.48.1] - 2026-07-12

Security patch — trust-plane default-verification hardening (#1695).

### Fixed

- **Default verification level now detects tampered stored capability grants
  (#1695).** At the default `VerificationLevel.STANDARD`, `TrustOperations.verify()`
  matched a capability by name + expiry only — the per-`CapabilityAttestation`
  Ed25519 signature covering the grant _content_ was verified only at `FULL`. An
  actor able to tamper the persisted trust chain could mutate a stored grant's
  content (e.g. widen `read` → `delete`, or loosen constraints) while preserving
  its `id`, and every enforcement surface — all default to `STANDARD` — authorized
  it. The default level now verifies the matched capability's content signature
  (shared `_verify_capability_signature` helper; `FULL`'s full-chain check reuses
  it), failing closed with a warning when the signing authority is unresolved or
  the signature is malformed.
  - The store-only MCP verification path (`EATPMCPServer` without a
    `TrustOperations` instance) previously matched capabilities with no signature
    verification; it now **fails closed** on positive authorization, since it has
    no cryptographic material to detect tampering.
  - `QUICK` is documented as expiry-only and must not be used as an enforcement
    level over untrusted or persisted chains.
  - Regression coverage: `tests/regression/test_issue_1695_tampered_grant_default_verify.py`.
  - Cross-SDK parity inspection tracked on the Rust SDK.

## [2.48.0] - 2026-07-11

SAFR governance-hardening: BH5 circuit-breaker (#1510) — completes the SAFR
BH1–BH5 primitive set on the Python side.

### Added

- **BH5 governance circuit-breaker for the PACT verdict path (#1510).** A
  first-class trip-and-hold anti-runaway control, evaluated per `(role, action)`
  at `verify_action` Step 3.7. A `(role, action)` that repeatedly breaches
  (held/blocked underlying outcome) TRIPS the breaker, which then HOLDS the key
  blocked for a cooldown before admitting a single probe — the guarantee a rate
  **limiter** cannot give (a limiter re-admits the instant its window slides).
  The verdict is composed monotonically (tighten-only): the breaker can only
  escalate a verdict, never relax one.
  - New per-role configuration on `OperationalConstraintConfig`:
    `circuit_failure_threshold`, `circuit_window_seconds`,
    `circuit_cooldown_seconds` (all optional; all three set → breaker active).
  - New classes on `kailash.trust.pact.circuit_breaker`: `PactCircuitBreaker`,
    `CircuitBreakerConfig`, `CircuitDecision`.
  - **Fail-closed** on non-finite config (`NaN`/`Inf` → BLOCKED); bounded memory
    that never evicts a tripped key (which would silently reset a breaker);
    thread-safe.
  - **Enforcement-surface parity:** the monotonic-tightening validator learns
    the breaker dimension, so a re-registration that strips or loosens a parent
    breaker is rejected as a widening (closes the privilege-escalation class the
    fix would otherwise introduce).
  - **Signed-envelope backward compatibility:** an unset breaker field is pruned
    from the `SignedEnvelope` signing pre-image, so a breaker-less envelope signs
    **byte-identically** to the pre-BH5 form and pre-existing / cross-SDK signed
    envelopes verify unchanged; a configured breaker keeps its fields
    (cryptographically bound).
  - Cross-SDK conformance vectors `circuit_breaker.json` +
    `rate_limit_enforcement.json` (the rate enforcer was previously
    vector-less); the Rust SDK mirrors these exact semantics (matching
    semantics, EATP D6).

## [2.47.0] - 2026-07-10

SAFR governance-hardening: BH3 origin-authentication (#1510).

### Added

- **BH3 origin-authentication for the EATP trust plane (#1510).** Binds an agent-declared action-trace to its **originating instruction** so a fabricated trace fails authentication even with a valid Ed25519 signature — closing the SAFR BH3 gap (a signature proves integrity, not that the trace came from the instruction that authorized it). New public surface on `kailash.trust`: `OriginBoundTrace`, `compute_origin_digest`, `origin_signing_payload`, `sign_origin_bound_trace`, `verify_origin_bound_trace`.
  - Two signed pre-image forms: **origin-unbound** is byte-identical to the pre-BH3 trace signing pre-image (existing anchors verify unchanged), and **origin-bound** extends it with a JCS-canonical (RFC 8785) `origin` digest of the originating instruction. A discriminator is excluded from the signing pre-image and fail-closed: stripping/flipping it forces a shape mismatch and verification rejects.
  - The verifier holds the authoritative instruction out-of-band, recomputes the digest and constant-time-compares it — so a key-holding attacker who re-signs a fabricated trace still fails the origin comparison. Fail-closed on every ambiguous path (missing instruction, absent digest, downgrade-to-unbound-when-origin-demanded).
  - The two pre-image byte forms are pinned as conformance vectors for cross-SDK byte-parity; the Rust SDK mirrors these exact bytes as an independent implementation (matching semantics, EATP D6).

## [2.46.0] - 2026-07-10

EATP v3 + SAFR governance-hardening epic.

### Added

- **Extensible risk-factor disposition calibration** (#1514 BH1).
- **Stateful sliding-window rate-limit enforcer** in `verify_action` (#1516 leg a).
- **Confidence/evidence-quality threshold routing** (#1516 leg b).
- **Configurable HITL timeout** with a fail-safe DENY-on-expiry disposition.
- **Pluggable identity resolver** — local + external DID (#1517 leg a).
- **RFC 8785 JCS canonical encoder** + conditional `subject_hash` audit anchor (#1590).
- **Citable WEFT provenance event schema** + conformance vectors (#1591).
- **EATP v3 additive elements** — bilateral delegation, clearance attestation, verify-chain, revocation modes, guarantee tiers (#1592).
- **Universal outbound-effect governance interceptor core** (#1517 leg-b).
- **Fail-closed HITL reviewer authority + capacity gate** (#1510 BH2 legs 2-3) — `ReviewerDecision` (APPROVE/MODIFY/DECLINE, monotonic-tightening), `apply_review_decision`, `max_pending_holds` admission control, cross-surface expire/review lifecycle under a lock.

### Fixed

- **Ancestor-verify bypass + risk-factor fail-closed hardening** (#1514 review).

### Security

- **Rate-limit eviction now fails CLOSED** (rate-limit reset bypass, #1516).
- **WAL/SHM sidecar permission hardening** + fail-closed corrupt-row expiry (#1515).
- **`did:key` self-certification hardening** (#1517 leg a).
- **EATP/outbound trust dataclasses frozen** + HTTP audit-target credential redaction + governance-verdict immutability (redteam M1/L1/L2).
- **Consolidated + expanded credential-bearing URL query-key masking across 4 sites** (#1655) — single canonical `is_sensitive_query_key`, plus presigned/SAS/STS signature keys.
- **HITL reviewer-authority multi-round redteam hardening** (#1510 BH2) — closed a CRITICAL expire/queue-desync resurrection, a HIGH corrupt-sentinel reconcile miss, and forged-row-denial/audit-poisoning/`reviewer_id`-validation gaps.

## [2.45.6] - 2026-07-07

### Fixed

- **Conditional-execution performance and fallback metrics are now recorded.** `ConditionalExecutionMixin._track_conditional_execution_performance` and `_track_fallback_usage` called `_record_execution_metrics()` with a single metrics dict, but the real `LocalRuntime._record_execution_metrics` signature is `(workflow, execution_time, node_count, skipped_nodes, execution_mode)`. The arity mismatch raised a `TypeError` that the surrounding `except` swallowed, so `conditional_execution="skip_branches"` runs and fallback events silently recorded no metrics. Both call sites now pass the correct 5-argument signature; a regression test asserts the fallback metric lands.

## [2.45.5] - 2026-07-06

### Added

- **`AsyncSQLDatabaseNode` is transaction-scope aware (#1581).** `_AdapterTransactionScope` gained a `.transaction` property exposing the raw driver transaction handle, and `async_run` now reads `inputs.get("transaction")` and threads it through `_execute_with_retry` → `_execute_with_transaction` (and the batch path `execute_many_async` → `_execute_many_with_transaction`). When a transaction handle is supplied, a new leading borrow-don't-own branch runs `adapter.execute(..., transaction=...)` with NO begin/commit/rollback — the enclosing scope owns the lifecycle — so a statement issued inside a `TransactionScopeNode` participates in that transaction instead of autocommitting on its own connection. The handle is param-threaded, never stored on the (shared, cached) node instance, so concurrent operations cannot leak one scope's transaction into another.

### Fixed

- **Uniform `adapter.transaction()` contract + pool-safe commit/rollback (#1580).** The PostgreSQL, MySQL, and SQLite adapters now expose a single consistent `transaction()` async-context contract; commit/rollback return the borrowed connection to the pool exactly once (the prior double-release and begin-orphan paths are closed), and the SQLite terminal-close path is quiet so it cannot mask the underlying driver error. This is the core half of the adapter-transaction correctness work that #1581's DataFlow transaction-awareness builds on.

## [2.45.4] - 2026-07-05

### Added

- **`kailash.utils.loop_pool_registry`** — a per-loop connection-pool drain registry for DataFlow's sync→async bridge (#1572). Adapter pools (aiomysql/asyncpg) created on a transient bridge loop (`async_safe_run` / `_run_in_thread_pool`) previously had their transports bound to that loop with no way to drain them before the loop closed — `close_async()` could not help because once the loop is closed the transports belong to a dead loop. Pool-creation sites now call `register_pool_drain_on_current_loop(drain)`, gated on a `BRIDGE_LOOP_ATTR` marker the bridge stamps onto loops it creates; persistent application loops (FastAPI, Jupyter) never carry the marker and are never registered, so a live app pool is never touched. The bridge calls `drain_loop_pools(loop)` in its `finally` block, before task cancellation and loop close, bounding each drain to 5s and never raising. Core owns the registry (not DataFlow) because `dataflow -> kailash` is the only legal import direction, so both a DataFlow adapter pool and a core `EnterpriseConnectionPool` pool (covered transitively via its inner adapter's `connect()`) register through the same path.

### Fixed

- **`AsyncSQL` PostgreSQL/MySQL adapter `connect()` now registers its pool for bridge-loop drain, and `disconnect()` is idempotent (#1572).** `PostgreSQLAdapter.connect()` / `MySQLAdapter.connect()` call `register_pool_drain_on_current_loop(self.disconnect)` immediately after pool creation (a no-op off the transient bridge loop); `disconnect()` now nulls `self._pool` after closing so a later `cleanup()` / bridge-drain double-close is a guarded no-op instead of a double-close error. This closes the core half of the ~10 GC-time `RuntimeError: Event loop is closed` / `ResourceWarning: Unclosed connection` reports that surfaced after `await db.close_async()` on DataFlow's bridge; see kailash-dataflow 2.13.19 for the bridge-side half (`dataflow.core.async_utils`).

## [2.45.3] - 2026-07-03

### Fixed

- **SQLite shared-cache `:memory:` cross-thread support for `SQLDatabaseNode` (#1502).** For a SQLite **memory** connection string only, `SQLDatabaseNode` now uses `StaticPool` + `check_same_thread=False` (and normalizes a `file:` shared-cache URI to `sqlite:///file:...&uri=true`) so the sync model-registry path executed in a thread pool no longer raises `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`. File-backed SQLite, PostgreSQL, and MySQL keep `QueuePool` byte-for-byte (the branch is guarded on `mode=memory`/`:memory:`).
- **Added `SQLDatabaseNode.dispose_pools_for(connection_string)`** — a targeted, per-connection-string pool dispose (vs the global `cleanup_pools`) so a caller can release exactly its own shared pools at teardown without disturbing other live instances (used by DataFlow's `:memory:` teardown to prevent a leaked shared-cache DB + `id()`-reuse cross-instance aliasing).

## [2.45.2] - 2026-07-03

### Fixed

- **SQLite adapter no longer discards `RETURNING` rows (#1498).** `AsyncSQLDatabaseNode`'s SQLite path short-circuited every `INSERT`/`UPDATE`/`DELETE` to `[{"rows_affected": N}]` on a leading-keyword check, never fetching the `RETURNING` result set — so a `... RETURNING *` insert/update came back as a row-count summary with the returned columns silently dropped (surfaced as DataFlow SQLite upsert returning `{"record": {"rows_affected": 0}}`). Added a `"RETURNING" not in query` guard to both SQLite DML short-circuits so RETURNING queries fall through to the fetch, matching the guard the PostgreSQL adapter already had. Non-RETURNING DML is unchanged.

## [2.45.0] - 2026-07-02

Trust-plane hardening plus two new trust primitives.

### Added

- **`ConsentAttestation`** (`kailash.trust`) — first-class affirmative-human-acceptance
  record: `human_origin_id`, `document_hash` (SHA-256 of the exact rendered bytes),
  `document_version`, `typed_name`, `assent_signals`, Ed25519 signature (+ optional HMAC
  overlay), head-anchored `ConsentLedger` chain (analog of `CapabilityAttestation`). The
  engine ships the signed/chained primitive only; domain/legal wording stays app-side.
  (#1481)
- **Per-recipient disclosure-trace tokens** (`kailash.trust`) — a `disclosure` audit event
  deriving a deterministic per-`(recipient, resource, session)` trace token via keyed
  HMAC-SHA256 from an injected server key (fail-closed on an absent key), bound to the audit
  record, with keyed reverse-lookup (`trace_token -> recipient`, not HMAC inversion).
  Watermark rendering stays app-side. (#1482)

### Fixed

- **Hold resolution now cryptographically binds the reviewed disclosure**
  (`kailash.trust.plane.holds`). `HoldManager.resolve()` signs an Ed25519 payload over the
  reviewed hold's decision-relevant disclosure (submitter/caller, reason, capability)
  _before_ the durable write; `verify_resolution()` recomputes the payload from the stored
  hold, so an approval/rejection signed over a disclosure differing from the queued hold
  fails verification and the hold survives for a correct decision. Fail-closed on
  unsigned/pending. (#1483)
- **Persisted PACT authorization root is re-validated on load**
  (`kailash.trust.pact.stores.SqliteOrgStore`). `_deserialize_org` now re-runs the D/T/R
  grammar + structural-consistency checks on every reconstructed org node and fails closed
  with a typed `DeserializationError` on a tampered / grammar-invalid / dropped-key persisted
  org, rather than yielding an unvalidated authorization root. `Address` / `AddressSegment`
  gain `__post_init__` validators so every construction path validates. (#1480)

## [2.44.1] - 2026-06-22

Closes the three implementable public-reachable gaps from the Production/Stable
stub-marker inventory (#1406, PR #1420). Each was a documented feature the code
did not actually perform.

### Fixed

- **Edge monitoring `active_count` no longer always equals the total alert
  count** (`kailash.nodes.edge.edge_monitoring_node`). The `active_count` field
  of the `get_alerts` action used `[a for a in alerts if active_only or True]` —
  the `or True` made the comprehension a no-op, so `active_count` reported the
  full alert count regardless of how many alerts were actually active. A new
  `EdgeMonitor.is_alert_active()` predicate (the cooldown-window check, extracted
  from the inline logic in `get_alerts`) now drives `active_count`. Note:
  `EdgeMonitor.get_alerts(active_only=True)` now also treats an alert with no
  cooldown-history entry as inactive (previously kept) — unifying the filter and
  the count on one predicate; unreachable on the normal alert path (every
  generated alert records its cooldown entry at creation).
- **`ImportPathValidator.validate_directory(...)` honours `include_tests`**
  (`kailash.runtime.validation`, `kailash.cli.validate_imports`). The
  `--include-tests` CLI flag was parsed but never forwarded to the validator, so
  test files were always skipped. `validate_directory` now accepts
  `include_tests: bool = False` and the CLI forwards `--include-tests`.

### Changed

- Removed a stale, misleading commented-out `max_pages` line in
  `kailash.nodes.api.rest._handle_pagination`. The `max_pages` pagination cap was
  already read and enforced in the page-fetch loop; only the dead comment
  implied otherwise. No behaviour change; a regression test now pins the cap.

## [2.44.0] - 2026-06-22

Replaces the never-functional `FetchMode.ITERATOR` on `AsyncSQLDatabaseNode` with a
real, memory-bounded streaming API and closes a silent-fallback bug class in the
async-SQL fetch dispatch (PR #1416, #1417). Resolves the top public-reachable gaps
(#1/#2) of the Production/Stable stub-marker inventory (#1406).

### Added

- **Memory-bounded SQL streaming — `AsyncSQLDatabaseNode.stream()` (+ adapter
  `stream()`)** (`kailash.nodes.data.async_sql`; PR #1417). An async-context-manager
  that pulls rows lazily via server-side cursors — asyncpg cursor inside a
  transaction (PostgreSQL), unbuffered `SSCursor` (MySQL), chunked `fetchmany`
  (SQLite) — so large result sets do not materialize in memory:

  ```python
  async with node.stream(query="SELECT * FROM big_table", batch_size=1000) as cursor:
      async for row in cursor:        # peak memory bounded by batch_size
          process(row)                # each row already converted, masked if access-controlled
  ```

  The connection (and, for PostgreSQL, its transaction) is held open for the entire
  iteration and released on every exit path (completion, early `break`, exception).
  Streamed rows are byte-identical to `fetch_mode="all"` rows; access-control masking
  and query validation apply on the stream path exactly as on the materialized path.
  New module constant `DEFAULT_STREAM_BATCH_SIZE = 1000` (distinct from `fetch_size`).

### Removed

- **BREAKING — `FetchMode.ITERATOR` removed** (`kailash.nodes.data.async_sql.FetchMode`;
  PR #1416). The member never produced a working result on any dialect — it raised
  `NotImplementedError` on PostgreSQL and silently returned `None` (MySQL) / `[]`
  (SQLite). A lazily-yielding stream cannot be a materializing fetch _return value_
  the way `ONE`/`ALL`/`MANY` are, so it was a category error. **Migration:** for
  streaming, use the new `node.stream()` async-context-manager (see Added); for
  bounded batches, use `fetch_mode="many"` with `fetch_size`. No working code breaks —
  the member never returned usable data. `fetch_mode="iterator"` is now rejected at
  node validation with `Invalid fetch_mode: iterator. Must be one of: one, all, many`.

### Fixed

- **Silent-fallback in async-SQL fetch dispatch** (`kailash.nodes.data.async_sql`;
  PR #1416). An unrecognized fetch mode previously fell through the MySQL/SQLite
  dispatch to `None`/`[]` instead of raising; every adapter dispatch now ends in a
  typed `ValueError("Unsupported fetch_mode: …")` so a wrong-but-plausible empty
  result can never again be returned silently.
- **MySQL streaming connection leak** (`kailash.nodes.data.async_sql`; PR #1417).
  An unbuffered `SSCursor` left an open read transaction holding a table metadata
  lock, deadlocking subsequent DDL; the cursor is now closed and the read
  transaction rolled back on every exit path before the connection returns to the
  pool.

## [2.43.1] - 2026-06-21

Cross-SDK canonical-encoder conformance plus a trust-plane-wide NaN/Inf signing
pre-image sweep. Brings Python's audit-chain canonical hash into lockstep with the
cross-SDK canonical form and closes an RFC-8259 cross-SDK
re-verification hazard at every trust-plane signing/hash pre-image (PR #1411, #1412).

### Changed

- **BREAKING (audit-chain byte-shape) — audit-chain canonical hash now uses fixed
  6-digit microseconds for cross-SDK conformance** (`kailash.trust` audit-chain
  canonical encoder; issue #1400 via PR #1411). The Python audit-chain canonical
  pre-image now matches the cross-SDK canonical form so a Python-anchored audit
  chain re-verifies across implementations and vice-versa. **Migration:** audit
  anchors created under ≤2.43.0 whose timestamps differ in microsecond representation
  (e.g. whole-second timestamps, previously emitted without a trailing `.000000`)
  recompute to a different integrity hash under 2.43.1 — re-anchor persisted chains
  after upgrade. This is a byte-shape change to the canonical pre-image, not a
  public-API change.

### Security

- **Reject NaN/Inf at every trust-plane signing / hash / cross-SDK pre-image**
  (`allow_nan=False`; PR #1411, #1412). A `json.dumps` over a signing or
  integrity-hash pre-image that omitted `allow_nan=False` emitted RFC-8259-invalid
  `NaN` / `Infinity` literals: Python signs and hashes them, but a strict cross-SDK
  parser (Rust `serde_json`) rejects them, so a Python-signed artifact whose
  pre-image carried a non-finite float could not be re-verified cross-SDK. Every
  pre-image now rejects NaN/Inf at serialization (fail-closed), and the change is
  byte-neutral on all finite input. Covers: envelope HMAC, audit-chain Merkle digest,
  selective-disclosure witness export/verify, A2A JWT, interop tokens
  (Biscuit / SD-JWT / UCAN), delegation execution-context state hash,
  multi-signature, verification-bundle + archive integrity, PACT SQLite audit/policy,
  and the cross-SDK delegate-conformance digest. A durable AST-invariant regression
  guard now locks every signing/hash pre-image module to carry `allow_nan=False`.

## [2.43.0] - 2026-06-20

Wires the binding-owned CL-02a tenant/domain scoping and CL-04 cooling-off
suspension (the existing `kailash.trust.vault.clearance.evaluate_clearance` gate)
into the two KEK-commitment registry-mutating operations — `recommit_vault_kek`
and `retire_vault_kek_alg`. This closes the clearance-gate-scoping sub-part of the
SLIP-0039 vault-binding follow-up (#630) that the 2.42.0 deploy record flagged as
capability-presence-only on these two surfaces (the separate §3.4 KEK
re-establishment / encryption-hierarchy gap is unchanged). `retire_vault_kek_alg`
gains a required `resolver` parameter — hence the minor bump.

### Changed

- **BREAKING — `retire_vault_kek_alg` now requires a `resolver` and enforces
  CL-02a tenant/domain scoping** (`kailash.trust.vault.registry_ops`). The retire
  gate named `clearance-tenant-domain` previously checked the `vault:retire-alg`
  capability PRESENCE only; it now runs the full `evaluate_clearance` gate
  (tenant → domain → token, fail-closed order) against the vault's RESOLVED
  tenant/domain. Because `VaultKeyHandle` carries no tenant/domain, the operation
  gains a REQUIRED keyword-only `resolver: VaultKeyResolver` (the only trusted
  source), making it symmetric with `recommit_vault_kek`. The resolved KEK is
  materialized solely to read the trusted tenant/domain and is `zeroize()`-d in a
  `finally` (N12-IN-05) — it crosses no return value, anchor payload, or log line.
  **Migration:** pass `resolver=<your VaultKeyResolver>` to `retire_vault_kek_alg`.
  A retire whose clearance tenant/domain does not match/cover the vault's — and
  that previously resolved to ALLOW — now resolves to DENY (`missing-clearance`);
  same-tenant, covered-domain retires are unaffected.

### Security

- **`recommit_vault_kek` + `retire_vault_kek_alg` enforce tenant/domain isolation
  and (recommit) post-recovery cooling-off** (`kailash.trust.vault.registry_ops`).
  Both registry-mutating operations now perform the binding-owned CL-02a
  tenant/domain scoping the gate label always advertised, closing the gap where a
  `vault:backup` (recommit) or `vault:retire-alg` (retire) token granted in
  tenant/domain A could mutate a vault's commitment registry in tenant/domain B.
  `recommit_vault_kek` additionally honors the N12-CL-04 7-day post-recovery
  cooling-off suspension (it rides `vault:backup`, a cooling-off-suspended
  capability) via new optional `posture_store` / `trust_anchored_now` /
  `approver_configured` parameters (absent → no cooling-off check, the documented
  no-receipt default); `retire_vault_kek_alg` is a spec-faithful cooling-off no-op
  (`vault:retire-alg` is not a suspended capability). The audit-before-mutation
  (AU-02b) ordering and the recoverability-preserved guard are unchanged.

## [2.42.0] - 2026-06-20

A holistic post-multi-wave redteam of the trust-plane surface (beyond the
2.41.1 PACT KSP/Bridge + cascade scope) surfaced ten confirmed defects across
`kailash.trust.{pact,plane,operations,signing,enforce,revocation,vault}`. Nine
are non-breaking correctness/security fixes; one (`nda_signed` enforcement) is a
behavior change to knowledge-access control — hence the minor bump.

### Changed

- **BREAKING — `nda_signed` is now ENFORCED for SECRET / TOP_SECRET knowledge
  access** (`kailash.trust.pact.access.can_access`). `RoleClearance.nda_signed`
  is documented "Required for SECRET and TOP_SECRET clearance" and is
  parsed/stored/serialized across the YAML loader, SQLite store, and backup
  paths — but no access-decision path ever consulted it, so a role with
  `nda_signed=False` (the field default) was granted SECRET/TOP_SECRET access.
  `can_access` now denies SECRET+ items when `nda_signed` is `False` (fail-closed
  with `deny detail="nda_not_signed"`). **Migration:** any `RoleClearance`
  granting SECRET or TOP_SECRET access MUST set `nda_signed=True` (the value the
  conformance vector + canonical fixtures already use); a default-`False` SECRET
  clearance that previously resolved to ALLOW now resolves to DENY. CONFIDENTIAL
  and below are unaffected.

### Security

- **Rotation `revoke_old_key` now invalidates the key**
  (`kailash.trust.signing.rotation` + `kailash.trust.operations.TrustKeyManager`).
  `revoke_old_key` emitted a `rotation_key_revoked` audit event and cleared
  grace-period tracking but never removed the key from the key manager — so the
  "revoked" key kept signing while the audit trail asserted revocation. A new
  `TrustKeyManager.remove_key` tombstones the private material and
  `revoke_old_key` now calls it.
- **`TrustProject.verify` rejects a decision record missing its `content_hash`**
  (`kailash.trust.plane.project`). The tamper check was guarded by
  `if stored_hash and …`, so a decision record whose `content_hash` was stripped
  (the field is a computed property, not a required deserialization field) slipped
  past verification — even in `strict=True` mode. A missing/empty `content_hash`
  is now a verification failure (strict: raises `ChainHashMismatchError`;
  non-strict: `chain_valid=False` + integrity issue).
- **Corrupted persisted trust posture now fails closed to PSEUDO**
  (`kailash.trust.plane.project`). An unrecognized persisted `trust_posture` was
  swallowed by `except (ValueError, Exception): pass`, silently downgrading the
  agent to the permissive `SUPERVISED` constructor default. The handler now
  narrows to `ValueError`, logs a WARN, and restores the most-restrictive posture
  (`PSEUDO`) — never a silent autonomy widening (legacy aliases remain handled by
  `TrustPosture._missing_`).
- **Proximity scanning fails closed on non-finite usage**
  (`kailash.trust.enforce.proximity`). A `NaN`/`Inf` usage value bypassed every
  `>=` threshold comparison (`NaN >= x` is always `False`), so a corrupt budget
  reading produced NO proximity alert. Non-finite usage now escalates to `HELD`,
  and a non-finite limit is treated as unmeasurable (skipped, not crashed).

### Fixed

- **`AuditChain.from_dict` now raises on a corrupted chain**
  (`kailash.trust.pact.audit`). The docstring promised "Raises PactError if the
  chain is corrupted" (the P-H10 contract), but the code only logged a warning and
  returned the corrupted chain — silently accepting a tampered audit chain as
  valid. It now raises `PactError` with the integrity errors in `details`.
- **Revocation broadcaster routes async-subscriber failures to the dead-letter
  queue** (`kailash.trust.revocation.broadcaster`). Async subscriber callbacks
  were scheduled via `ensure_future` with no done-callback, so an exception raised
  inside the coroutine body surfaced only as an "unretrieved task exception"
  warning — bypassing the dead-letter accounting that captures delivery failures.
  A done-callback now records async failures the same as synchronous ones.
- **`CredentialRotationManager` docstring reconciled to its real best-effort
  contract** (`kailash.trust.signing.rotation`). The class advertised "atomic
  updates to prevent partial rotations", but `rotate_key` commits the authority's
  new key before re-signing chains and does not roll back on a re-sign failure
  (the registry exposes no transaction primitive). The docstring now documents the
  non-atomic, partial-rotation-possible behavior surfaced via `RotationError`.
- **Vault retire/recommit gate labels corrected to match enforcement**
  (`kailash.trust.vault.errors` + `registry_ops`). The `clearance-tenant-domain`
  gate labels asserted tenant/domain scoping (CL-02a), cooling-off (CL-04), and a
  governance-HELD action; the gates enforce capability-presence ONLY (the
  tenant/domain + cooling-off wiring is deferred). Labels + the retire gate now
  honestly disclose the capability-only scope and the deferred check.
- **`GovernanceContext.effective_envelope` None docstring corrected**
  (`kailash.trust.pact.context`). It read "maximally restrictive interpretation",
  contradicting `compute_effective_envelope` ("maximally permissive") and the
  engine's enforced auto-approve-on-None behavior. Corrected to the enforced
  permissive semantics (the opt-in governance default).

## [2.41.1] - 2026-06-20

### Fixed

- **YAML envelope `confidentiality_clearance` and `max_delegation_depth` are no
  longer silently dropped** (issue #1393, `kailash.trust.pact`). A constraint
  envelope authored in a unified YAML org file may carry two top-level governance
  fields beyond the five CARE dimension dicts: `confidentiality_clearance` (the
  data-classification ceiling) and `max_delegation_depth` (the delegation-depth
  cap). `EnvelopeSpec` had no slot for them, `_parse_envelopes` never read them,
  and `yaml_resolvers.resolve_envelope` never forwarded them into
  `ConstraintEnvelopeConfig` — so a YAML-authored `max_delegation_depth: 1` (cap
  delegation to one level) silently became `None` (UNLIMITED) at enforcement, and
  an authored confidentiality ceiling never applied, with no error. Both fields
  are now parsed (fail-closed on an invalid clearance level or a non-positive-int
  depth — including unhashable list/dict values — via a shared `_is_valid_level`
  guard) and forwarded to the runtime envelope config, where they participate in
  monotonic-tightening validation end-to-end (a widening child envelope is
  rejected with `MonotonicTighteningError`).
- **`cascade_revoke` reports the true set of revoked agents on a rollback-restore
  failure** (issue #1394, `kailash.trust.revocation.cascade`). On a partial
  failure, `cascade_revoke` returned `RevocationResult(success=False,
revoked_agents=[])` even when the best-effort rollback could NOT restore an
  already-soft-deleted chain — so the audit result claimed "no agents revoked"
  while chains remained deleted in the store (store state and result diverged).
  `_rollback_chains` now returns the agents it could not restore (instead of
  swallowing the failure) and `revoked_agents` reflects store ground truth: any
  chain that remains soft-deleted (revoked) is reported, with a WARN naming it.
  The module/function docstrings that over-claimed transaction-backed "atomic
  chain invalidation" — which the code never performed and the InMemory
  transaction context cannot provide (it snapshots only active chains, so a
  soft-delete cannot be rolled back) — are reconciled to the real
  best-effort-rollback (non-transactional) contract.

## [2.41.0] - 2026-06-19

### Added

- **YAML governance specs now take effect at enforcement** (issue #1386,
  `kailash.trust.pact`). `load_org_yaml` / the new `load_org_from_dict` parsed
  `clearances` / `envelopes` / `bridges` / `ksps` from a unified YAML org file,
  but the engine consumed only the org definition — the four governance-spec
  lists were silently dropped, so a YAML-authored `shared_paths`, `min_clearance`,
  bridge, or clearance had zero effect on `check_access`. The new
  `kailash.trust.pact.yaml_resolvers` module resolves each spec to its runtime
  type and applies it to the `GovernanceEngine` (the "engine-application layer"
  the `KspSpec` docstring referenced). Application order: clearances → envelopes
  (topologically parent-before-child, since `set_role_envelope` validates each
  child against the defining role's effective envelope) → bridges (a
  YAML-authored bridge is the org designer's LCA approval, so the loader records
  that approval before `create_bridge`) → KSPs.
- `kailash.trust.pact.yaml_loader.load_org_from_dict` — applies the same parse +
  governance-spec application from an in-memory mapping (the dict construction
  path previously dropped the spec lists).
- `CompiledOrg.get_node_by_unit_id` — resolves a config department/team id to its
  positional unit address (for KSP source/target resolution).

### Changed

- Resolution is fail-closed throughout: an unresolvable unit/role reference, an
  invalid classification level, a `..` path-traversal pattern, a non-finite
  (NaN/Inf) constraint, an envelope monotonic-tightening violation, or a bridge
  with no common ancestor aborts engine construction rather than yielding a
  silently under-enforcing engine. YAML-resolved clearances/KSPs record
  `"yaml-org-definition"` as the grantor/creator for an attributable audit trail.

## [2.40.1] - 2026-06-19

### Fixed

- `KspDenyDetail` (the F9 KSP-deny observability type) is now importable from
  the `kailash.trust.pact` package facade, matching its siblings
  (`AccessDecision`, `KnowledgeSharePolicy`, `PactBridge`). It was present in
  `kailash.trust.pact.access.__all__` but never lifted into the package
  `__init__`, so `from kailash.trust.pact import KspDenyDetail` raised
  `ImportError`. Surfaced by the epic #1375 holistic post-multi-wave redteam
  (orphan-detection Rule 6). A structural parity regression test now pins
  every `access.__all__` symbol importable from both facades.

## [2.40.0] - 2026-06-19

### Added

- **KSP YAML DSL scope-field expressiveness** (`kailash.trust.pact.yaml_loader`,
  part of #1375). The YAML `ksps:` block now accepts the full narrowing
  scope-field set the runtime `KnowledgeSharePolicy` enforces — `compartments`,
  `shared_paths` (#1369), `shared_types` (#1370), `shared_classifications`
  (#1371), `min_clearance` (#1368), and `conditions` (#1374, e.g. a
  `time_window`). Previously a YAML-defined org could express only
  `max_classification`, so the scoping features the engine enforces were
  unreachable from configuration. Every new field is optional and defaults to
  empty/`None` (no narrowing = broad grant), so existing YAML is unchanged.
  `KspSpec` carries the values verbatim as a frozen DTO; the fail-closed
  semantic checks (`..` path traversal, condition-key validity, level-string →
  `ConfidentialityLevel`, raw id → resolved address) remain owned by
  `KnowledgeSharePolicy` and the engine-application layer.

- **Structured, SIEM-queryable KSP-deny observability** (`kailash.trust.pact`,
  part of #1375). A KSP deny now emits a `deny_code` discriminator
  (`compartment_scope` / `path_scope` / `type_scope` / `classification_ceiling`
  / `classification_set` / `min_clearance` / `condition`) plus
  condition-specific discrete fields (e.g. `missing_compartments`, `item_path`,
  `ksp_shared_types`) as top-level `AccessDecision.audit_details` keys — parity
  with the step-3 clearance-deny audit shape — while keeping the human
  `deny_reason` string for backward compatibility. `/explain` surfaces the
  `deny_code` and the denying KSP id. Deny-precedence (#1372) and fail-closed
  behaviour are unchanged. New public type `KspDenyDetail`
  (`kailash.trust.pact.access`), whose discrete-field keys are guarded
  fail-closed against collision with the reserved audit keys.

## [2.39.1] - 2026-06-19

### Fixed

- **PACT `KnowledgeSharePolicy.compartments` now enforced** (`kailash.trust.pact`,
  #1375 follow-up). The documented `compartments` field was accepted but never
  applied — a silent over-grant (zero-tolerance 3c). It is now evaluated as the
  7th KSP narrowing condition at step 4d: an item is shareable under a KSP only
  if every compartment it carries is authorized by the KSP's compartment set
  (`item.compartments` ⊆ `ksp.compartments`); empty `ksp.compartments` = no
  narrowing (all compartments allowed), consistent with `shared_paths` /
  `shared_types`. The filter narrows the individual KSP and composes under KSP
  deny-precedence (#1372) — a sibling KSP that affirmatively grants still wins —
  and does NOT replace the step-3 clearance compartment ceiling, which
  independently bounds SECRET/TOP_SECRET items regardless of KSP composition.

## [2.39.0] - 2026-06-18

### Added

- **PACT KSP/Bridge access-control scoping & precedence** (`kailash.trust.pact`,
  epic #1375 — closes #1368–#1374). Per-policy narrowing controls that were
  previously inexpressible, so policies over-granted:
  - `KnowledgeSharePolicy` gains `min_clearance` (recipient clearance floor,
    #1368), `shared_paths` (path-prefix scope, #1369), `shared_types`
    (knowledge-type scope, #1370), `shared_classifications` (allowed-level SET
    beyond the `max_classification` ceiling, #1371), and `conditions`
    (request-context `time_window`/`environment`, #1374).
  - `KnowledgeItem` gains `path` and `knowledge_type` (#1369/#1370).
  - `PactBridge` gains `shared_paths` with a `..` traversal guard, fail-closed
    at construction AND enforcement (#1373).
  - `can_access` / `GovernanceEngine.check_access` / `explain_access` accept
    keyword-only `now` and `environment` for time/context-conditioned policies
    (#1374). Unknown condition keys and malformed (non-`HH:MM`) time windows
    fail closed.

### Changed

- **Deny-precedence in `can_access` Step 4d** (#1372): a `KnowledgeSharePolicy`
  that matches the source/target addressing but fails a narrowing condition now
  DENIES and suppresses the bridge fallback. Previously a deliberate KSP deny
  was bypassable via a more permissive bridge (over-grant). A granting sibling
  KSP still wins; absence of any applicable KSP still leaves the bridge path
  available. All new scope fields default to "match-all", so the change is
  backward-compatible.
- `SqliteAccessPolicyStore` schema advanced to v2 with an additive, in-place
  `v1→v2` column migration; backup/restore preserves every new scope field.

## [2.38.3] - 2026-06-18

### Added

- **`MiddlewareAuthManager` token revocation** (sibling of #1356). The legacy
  nodes-based JWT verifier (`kailash.middleware.auth.MiddlewareAuthManager`) had
  no revocation capability at all — no `jti` claim, no revocation-store
  consultation in `verify_token`, and no `revoke_token` method, so an issued
  token could never be invalidated before its natural expiry. It now reuses the
  SAME pluggable `TokenRevocationStore` introduced for `JWTAuthManager` in
  #1356: tokens carry a `jti` claim, `verify_token` rejects revoked tokens
  (HTTP 401 `Token has been revoked`), and a new `async revoke_token(token)`
  records the revocation. Inject a SHARED backend via
  `MiddlewareAuthManager(revocation_store=...)` so revocation propagates across
  every worker; the default `InMemoryTokenRevocationStore` is process-local
  (`enable_blacklist=True` by default). Purely additive — existing token claims
  are unchanged and pre-2.38.3 tokens (no `jti`) still verify. The
  decode-failure revoke path is TTL-bounded at `token_expiry_hours` so an
  attacker cannot grow the store with unique invalid strings.

### Fixed

- **`MiddlewareAuthManager.verify_token` / `verify_api_key` returned an internal
  error instead of HTTP 401 on an invalid token.** The security-event log calls
  passed `severity="warning"`, which is not a valid `SeverityLevel`
  (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`/`INFO`), so `SecurityEventNode` raised
  `ValueError` — meaning every invalid or expired token escaped `verify_token`
  as an unhandled exception rather than a clean 401. The severity is now
  `MEDIUM`, and security-event logging is best-effort (a logging-backend failure
  can no longer convert an auth rejection into a 500).

## [2.38.2] - 2026-06-18

### Fixed

- **(#1356) `JWTAuthManager` token revocation is now propagatable across workers.**
  Revocation was backed by a per-instance in-memory `set`, so a token revoked on
  one worker stayed valid on every other worker in any multi-worker / multi-pod
  deployment — the revocation security control silently failed to take effect.
  Token revocation now routes through a pluggable `TokenRevocationStore`
  (exported from `kailash.middleware.auth`): inject a SHARED backend
  (Redis / database / distributed cache) via `JWTAuthManager(revocation_store=...)`
  and revocation propagates to every worker that shares it. The default
  `InMemoryTokenRevocationStore` preserves the original process-local behavior
  (single-process deployments are unaffected); the class docstring documents the
  process-local default + the multi-worker shared-store guidance. `verify_token`
  / `revoke_token` remain synchronous (no API break) and the revoked-token
  exception is unchanged. The decode-failure revocation path is TTL-bounded so it
  cannot grow the store without limit.

### Added

- **`TokenRevocationStore` / `InMemoryTokenRevocationStore`** in
  `kailash.middleware.auth` — the synchronous pluggable revocation-backend
  contract and its process-local default implementation (#1356).

## [2.38.1] - 2026-06-17

### Changed

- **(Behavior change)** `EmbeddingNode` no longer returns `np.random.randn`
  random placeholder vectors presented as real embeddings (meaningless for any
  similarity search). It now raises a clear typed `NodeExecutionError` — the
  node bundles no real embedding model. Provide real embeddings from an
  embedding provider upstream, or use `RelevanceScorerNode` with
  `similarity_method="bm25"` / `"tfidf"` for embedding-free retrieval.

## [2.38.0] - 2026-06-17

### Added

- **Real in-memory vector backend for `VectorDatabaseNode`**: `provider="memory"`
  is now a working backend with real `upsert`/`query`/`delete`/`fetch`,
  cosine/euclidean/dot similarity ranking, metadata storage + equality
  filtering, and an optional `max_vectors` capacity cap. Previously every
  operation returned fabricated results (`doc_0..doc_4`, invented scores,
  `[0.1]*dimension` fetches).
- **Real Okapi BM25 and TF-IDF scoring for `RelevanceScorerNode`**: the `bm25`
  and `tfidf` similarity methods now compute real lexical relevance over chunk
  text via a new optional `query` text parameter. Previously both returned a
  constant `0.5` for every chunk.

### Changed

- **(Behavior change)** `VectorDatabaseNode` external providers
  (`pinecone`/`weaviate`/`milvus`/`qdrant`/`chroma`) now raise a clear typed
  `NodeConfigurationError` directing users to `provider="memory"` instead of
  silently returning fabricated search results.
- `RelevanceScorerNode` `bm25`/`tfidf` without a `query` text input now raise a
  clear `ValueError` instead of returning a constant score.

### Fixed

- **Fabricated connection-pool metrics** in `WorkflowConnectionPool`:
  `get_pool_statistics()` / `_get_pool_status()` returned hardcoded
  `avg_query_time_ms=50.0`, `avg_latency_ms=0.0`, `queue_depth=0`, and
  `capabilities=["read","write"]` — `avg_latency_ms` and `capabilities` fed
  `query_router` routing decisions. Now real query-time tracking, real queue
  depth, and honest omission where no real signal exists.
- Latent `VectorDatabaseNode.configure()` `AttributeError` (it called a
  non-existent base `configure()`); the documented `configure()` → `execute()`
  flow now works.
- `RelevanceScorerNode` removed a hardcoded fallback query string and all
  `print()` debug output.

## [2.37.0] - 2026-06-17

### Added

- **Tenant-scoped event bus (#1338, cross-SDK parity)**:
  new `kailash.events.TenantScopedEventBus` (also re-exported as
  `kailash.TenantScopedEventBus`) gives multi-tenant pub/sub isolation over a
  shared `EventBus`. It prefixes every topic with the tenant id
  (`"acme:order.created"` vs `"globex:order.created"`); because both backends
  dispatch by exact `event_type` (in-memory dict key, Redis one-stream-per-type),
  a publish on one tenant fans out **only** within that tenant — isolation is
  structural, not a runtime filter. The wrapper keeps the same
  `publish` / `subscribe` / `subscribe_events` shape as `EventBus`; handlers
  receive the original payload, and `subscribe_events` delivers a `DomainEvent`
  whose `event_type` is the logical (un-prefixed) type. Isolation-integrity
  guards: `tenant_id` MUST NOT contain the separator; every wrapper sharing one
  bus MUST use the same separator (a mismatched separator is refused — it could
  otherwise map two distinct tenants onto the same topic); and bus-construction
  kwargs are rejected (not silently dropped) when a shared bus is passed. Works
  unchanged over the Redis Streams backend, where prefixing is the only way to
  isolate tenants sharing one broker. Runnable example at
  `examples/eventbus_tenant_isolation.py`.

## [2.36.0] - 2026-06-17

### Added

- **Session sliding-TTL + remaining-TTL accessor (#1336, gateway parity #1349)**:
  `kailash.channels.CrossChannelSession` gains a `remaining_ttl(timeout=3600)`
  accessor returning the seconds left before expiry, mirroring the two-mode logic
  of `is_expired` exactly (absolute-deadline branch when `expires_at` is set, idle
  branch otherwise) so the two always agree. Sessions may now opt into **sliding
  expiration** via `SessionManager.create_session(sliding_ttl=<seconds>)`: the
  deadline re-slides forward to `now + ttl` on every activity (`touch()`, any
  mutator, or `get_session` access). Sliding is strictly opt-in via a new `ttl`
  field — fixed-deadline sessions created with `timeout=` keep their existing
  non-sliding behavior unchanged, and `timeout` / `sliding_ttl` are mutually
  exclusive (passing both raises `ValueError`).

## [2.35.0] - 2026-06-16

### Added

- **`DistributedLock` / `Lease` primitive (#1339)**: a first-class distributed
  lock with two interchangeable backends behind one seam (`LockBackend`). The
  load-bearing safety mechanism is the **fencing token** — a strictly-monotonic
  per-key integer returned by `acquire` and verified by `release`/`extend`,
  never reset across release/expiry/steal — so a protected resource can reject
  any write carrying a stale token (the Kleppmann critique of TTL-only locks).
  New public surface on `kailash.infrastructure`: `DistributedLock`, `Lease`,
  `LockBackend`, `DBLockBackend`, `RedisLockBackend`, `LockAcquireError`.
  - `DBLockBackend` — dialect-portable SQL backend via `ConnectionManager`
    (SQLite at Level 0, PostgreSQL/MySQL at Level 1+), mirroring
    `DBIdempotencyStore`. A single `kailash_locks` table holds one persistent
    row per key; `release`/`reap` _tombstone_ the row (`owner`/`expires_at`
    set to `NULL`) rather than deleting it, so the `fencing_token` is preserved
    and stays strictly monotonic across release/expiry/steal. Acquire is
    single-winner under concurrency via `INSERT ... ON CONFLICT DO NOTHING`
    (seed the row) + `SELECT ... FOR UPDATE` (row-lock; SQLite serializes via
    `BEGIN IMMEDIATE`, so `dialect.for_update()` returns `""` there) — correct
    under PostgreSQL's default READ COMMITTED isolation.
  - `RedisLockBackend` — single-instance Redis lock behind the `[redis]` extra
    (lazy `redis.asyncio` import; typed `ImportError` if the extra is absent).
    `SET NX PX` + `INCR` for the fence, Lua compare-owner-then-DEL/PEXPIRE for
    release/extend, native PX expiry. Not multi-master Redlock; safety rests on
    the fencing token, not Redis timing.
  - `DistributedLock` facade owns `acquire` (non-blocking + bounded
    blocking-with-backoff) and an `async with lock.lease(key, ttl)`
    contextmanager that auto-releases on normal AND exception exit.
  - `StoreFactory.create_lock_store()` selects Redis when `REDIS_URL` is set
    else SQL, with an explicit `backend=` override.

## [2.34.2] - 2026-06-15

### Fixed

- **RFC-3161 `verify_timestamp` correctness — `digest=` binding** (#1332
  follow-up): the 2.34.1 fix passed the token's pre-computed message imprint to
  `rfc3161ng.check_timestamp` as `data=`, which the library **re-hashes** before
  comparison — so with `rfc3161ng` actually installed, every _valid_ token was
  rejected (the verification was fail-closed/safe but non-functional). It now
  passes the imprint as `digest=` (compared directly), so a genuine TSA-signed
  token verifies `True` while a tampered imprint or untrusted certificate is
  rejected. Surfaced by a new live-binding regression test that runs against a
  real `rfc3161ng` + a real `openssl ts`-minted token/cert fixture — the offline
  stub used in 2.34.1 could not catch the data-vs-digest semantics. The
  `rfc3161` extra is now installed in the trust-tests CI job so the real-library
  binding is verified on every trust-touching PR.

## [2.34.1] - 2026-06-15

### Fixed

- **Security: RFC-3161 `verify_timestamp` no longer fails open** (#1332):
  `RFC3161TimestampAuthority.verify_timestamp` previously returned `True` with
  **no cryptographic verification** whenever `rfc3161ng` was importable — the
  docstring promised "full ASN.1 verification" but the body was a bare
  `return True`, so a forged or tampered token whose `source`/`authority`
  metadata matched the configured TSA was accepted as valid. It now performs
  real verification: the raw DER `TimeStampToken` (carried on
  `TimestampResponse.raw_response`, now threaded through `verify_anchor`) is
  checked against a configured trusted TSA `certificate` and the token's hashed
  message imprint via `rfc3161ng.check_timestamp`. The method returns `True`
  **only** on cryptographic success and **fails closed** (returns `False`) when
  any verification material is missing (`rfc3161ng` not installed, no raw DER
  token, no trusted certificate) or the check fails — per the EATP fail-closed
  discipline. `RFC3161TimestampAuthority.__init__` gains an optional
  `certificate` trust-anchor argument; `verify_timestamp` /
  `verify_timestamp_token` gain an optional `raw_token` argument
  (backward-compatible additions). A new `rfc3161` optional extra
  (`pip install 'kailash[rfc3161]'`, included in `[all]`) installs `rfc3161ng`
  to enable verification.

## [2.34.0] - 2026-06-15

### Added

- **EATP-08 D2c signed-marker verification** (#1316): the D2d legacy-acceptance
  witness is now verified-not-trusted. `D2dWitness` gains the §4.3.1 signed-core
  fields (`first_seen`, `marker_sig`) plus `expires_at` and `witness_id`; new
  `D2dVerifierKeys` (exported from `kailash.trust.signing.algorithm_id`) holds the
  trusted Ed25519 public keys that `assert_d2d_witness_pre_adoption` verifies
  `marker_sig` against — over the canonical `{principal, first_seen}` core.
  Acceptance now requires five fail-closed checks (missing / signature / first_seen
  corroboration / expiry / temporal boundary), each rejecting with
  `implicit-v1-witness-failure`. `verifier_keys` is threaded through every
  signed-record `from_dict` consumer (`SignedEnvelope`, `TimestampToken`,
  `TimestampResponse`, `CRLMetadata`, `SecureMessageEnvelope`). The strict
  post-adoption path (`witness=None`) is unchanged.
- **EATP-08 §4.5.3 monotonic-upgrade enforcement** (#1316): once a
  principal-chain has emitted a registry-form (v2 / `eatp-v1`) record, a
  subsequent absent-`alg_id` or pre-registry explicit form is rejected with the
  new `monotonic-upgrade-violation` error code — taking precedence over D2a/D2d
  acceptance and over `missing-alg-id-post-adoption`. `D2dWitness` gains the
  optional signed-marker field `first_v2_seen` (the §4.3.1 monotonic boundary;
  included in the `marker_sig` pre-image only when set, so existing two-field
  `{principal, first_seen}` markers verify unchanged). `decode_wire_alg_id` and
  `AlgorithmIdentifier.from_dict` gain the `prior_registry_form_seen: bool`
  parameter (the verifier-supplied prior-v2 signal), threaded through every
  signed-record `from_dict` consumer. A conformant registry token and a bare
  unregistered string are unaffected. Marker persistence (the write side that
  sets the signal) is verifier-integration, not SDK-owned — consistent with the
  §4.3 implementation-defined marker transport.
- **EATP-08 §6 conformance vectors V1–V9** (#1316): the canonical cross-SDK
  vector file (`tests/test-vectors/eatp08-alg-id-canonical.json`) gains a named
  `conformance_vectors` coverage map (V-id, conformance `level`, spec ref,
  per-vector test mapping), with behavioral regression tests for the full
  acceptance bar (V4–V7 + V9, plus V6 sub-cases i/ii/iii). V7 is Conformance
  level **Complete**; the rest are **Conformant**.

## [2.33.1] - 2026-06-15

### Fixed

- **`get_namespace_annotations` now resolves class-body annotations on Python 3.14 final (PEP 749) (#1318).** PEP 749 (Python 3.14 final) renamed the lazy class-namespace annotate callable from the 3.14-beta `__annotate__` to `__annotate_func__` (and added the eager cache `__annotations_cache__`). `kailash.utils.annotations.get_namespace_annotations` read only `__annotations__` then `__annotate__`, so both lookups missed on 3.14 final and it fell through to `{}` — every class-based `kaizen.signatures.core.Signature` silently lost its declared fields and raised `ValueError: Either define fields as class attributes or provide inputs/outputs` at first instantiation. The helper now also reads `__annotate_func__` and `__annotations_cache__`, resolving on every 3.14 pre-release and the final. HIGH severity on Python 3.14; no effect on ≤3.13 (those interpreters set `__annotations__` eagerly, which is why the bug shipped unseen). Regression tests simulate the 3.14-final namespace shape so they assert the fix on every interpreter, plus a real metaclass-namespace test that exercises the native PEP 749 namespace on the 3.14 CI leg.

## [2.33.0] - 2026-06-15

### Added

- **EATP-12 v1.0 Trust Vault Key-Binding in `kailash.trust.vault` (#1312).** A new vault sub-package binds Key-Encryption-Key (KEK) backup and recovery to an audited, commitment-anchored trust substrate. Top-level entry points: `back_up_vault_key` / `restore_vault_key` (SLIP-39 shard backup + reconstruction of a resolved KEK) and `back_up_raw_vault_key`. The 63-symbol `kailash.trust.vault.__all__` surface exports the KEK-class + generation substrate (`VaultKeyResolver`, `ResolvedKek`, `VaultKeyHandle`, `current_generation_from_chain`), commitment binding (`kek_identity_commitment`, `key_check_value`, `verify_commitment`, `verify_kcv`, `CommitmentRegistry`), audited dispatch (`AuditDispatcher`, `AuditTier`, `DispatchReceipt`, `require_receipt_or_abort`), holder governance (`HolderRegistry`, `wrap_shard_for_holder` / `unwrap_shard_for_holder`, `revoke_holder_for_cause`, `rotate_vault_holders`), Complete-level ceremony gates (`GovernanceApproval`, `CeremonyWitness`, `verify_governance_approval`, `verify_ceremony_witness`, `ConformanceLevel`), generation rotation + for-cause advance (`recommit_vault_kek`, `retire_vault_kek_alg`, `CompromisedGenerationDenylist`), clearance + cooling-off gates (`ClearanceContext`, `evaluate_clearance`, `is_in_cooling_off`), and the typed error surface (`VaultBindingError`, `N12FT01Code`). The master secret never crosses the audit boundary — only one-way commitments / KCV + the SLIP-39 bit-length parameter are anchored (N12-AU-01 contents-exclusion); resolved key material is zeroized after use.

### Security

- **EATP-12 audited fail-closed dispatch + zeroization (#1312).** Vault anchors emit a signed, per-tier audit receipt BEFORE the operation is considered complete (AU-02b fail-closed ordering interlock — a dispatch failure raises and no receipt is produced). Resolved KEK bytes are consumed inside the trusted module and `del`-ed in a `finally` block (N12-IN-05). Converged through a holistic R3–R5 redteam cycle: KEK residency-leak zeroization, four orphaned-control gates wired into the hot path, side-channel-hardening rejection, and key-check-value gating.

## [2.32.0] - 2026-06-14

### Added

- **EATP-08 v1.1 algorithm-registry public API in `kailash.trust.signing` (#1315).** The signing surface now exports a first-class algorithm registry: `ALGORITHM_REGISTRY` (the `eatp-v1` / `eatp-v1.1` / `eatp-v2` / `eatp-v2.ml-dsa` / `eatp-v2.slh-dsa` entries), `RegistryEntry`, `AlgorithmStatus`, `DEPRECATED_PRE_REGISTRY_LITERAL` (`"ed25519+sha256"`), `D2dWitness`, `UnsupportedAlgorithmError`, and the resolution helpers `decode_wire_alg_id`, `resolve_dispatch`, `is_active`, `is_registered`, `is_pre_registry_form`, `assert_d2d_witness_pre_adoption`. These give callers a single source of truth for which signing algorithms are dispatchable and which are deprecated / pre-registry forms. Purely additive to `kailash.trust.signing.__all__`.

### Security

- **EATP-08 ISS-32 (v1.1.1 / mint#26): a bare top-level-string `alg_id` equal to the deprecated literal `ed25519+sha256` now rejects with `unsupported-algorithm` and MUST NOT dispatch (#1315).** Previously a bare top-level literal could be mistaken for a D2d pre-registry form and rescued by a sibling `algorithm` key; it is now treated as an unsupported algorithm at the verification boundary (§3.3 / §5.1 step 2), never rescued by a witness. A latent `from_dict` bypass is closed in the same change: a **present `alg_id` key is authoritative** — a sibling `algorithm` key cannot rescue a bare deprecated literal. The two legitimate D2d forms remain the nested-object `alg_id` value and unsigned `algorithm` metadata. The change reworks the alg-id verification path across `trust/signing/algorithm_id.py`, `trust/envelope.py`, `trust/messaging/{envelope,signer,verifier}.py`, and `trust/pact/envelopes.py`, with a new canonical vector set at `tests/test-vectors/eatp08-alg-id-canonical.json`.

### Documentation

- **EATP-08 §32.3 spec prose synced to the v1.1.1 bare-literal ruling (#1317).** `specs/trust-crypto.md` updated so the documented contract matches the `unsupported-algorithm` rejection behavior shipped in #1315.

## [2.31.0] - 2026-06-13

### Added

- **`OnlineStoreUnavailableError` in `kailash.ml.errors`** (a `FeatureStoreError` subclass), supporting the kailash-ml 2.2.0 online feature-store adapter (FM2 Wave 3, #693). Raised when the Redis-backed online store is unreachable so online-serving call sites can `except OnlineStoreUnavailableError` and degrade to the offline read path. Purely additive — the canonical ML error taxonomy (`kailash.ml.errors`) remains the single source the `kailash-ml` package re-exports from. kailash-ml 2.2.0 floors `kailash>=2.31.0` because it imports this class.

## [2.30.0] - 2026-06-13

### Added

- **Five ML feature-store exception classes in `kailash.ml.errors`** (all `FeatureStoreError` subclasses), supporting the kailash-ml 2.1.0 feature-store M2 authoring/registry/materialize surfaces (FM2, #1302): `FeatureGroupNotFoundError`, `FeatureVersionImmutableError`, `FeatureVersionNotFoundError`, `FeatureEvolutionError`, `CrossTenantReadError`. Purely additive — the canonical ML error taxonomy (`kailash.ml.errors`) is the single source the `kailash-ml` package re-exports from. kailash-ml 2.1.0 floors `kailash>=2.30.0` because it imports these.

## [2.29.4] - 2026-06-12

### Fixed

- **`register_node` no longer erases decorated node subclasses to `type[Node]` (#1286).** The inner decorator was annotated `decorator(node_class: type[Node])` with no generic return type, so static checkers inferred every `@register_node()`-decorated class as `type[Node]` and emitted an `attr-defined` diagnostic at every subclass-specific classmethod call site (e.g. `PythonCodeNode.from_function`). `register_node` is now a generic decorator (`Callable[[type[_NodeT]], type[_NodeT]]`, `_NodeT` bound to `Node`). **Typing-only — zero runtime/behavior change** (`register_node()(cls) is cls` still holds; `NodeRegistry.register` path untouched).
- **`WorkflowServer` / `WorkflowAPIGateway` now release per-workflow runtimes on teardown (#1285, core half).** `WorkflowServer.register_workflow` builds a `WorkflowAPI` per workflow, each constructing its own `AsyncLocalRuntime`; these were never tracked or closed, leaking one runtime per registered workflow until GC. `WorkflowServer` now tracks the wrappers and gains a `close()` that releases them; `EnterpriseWorkflowServer.close()` cascades via `super().close()` (so closing the gateway releases both its acquired runtime reference and every per-workflow runtime); the legacy `WorkflowAPIGateway` carrying the same bug class is fixed in tandem (track + release on shutdown/`close()`). Pairs with the Nexus-side fix in kailash-nexus 2.9.1.

## [2.29.3] - 2026-06-06

### Documentation

- **Canonical-encoder divergence contract documented + byte-vectors pinned (#1258).** The two canonical-JSON encoders carry **intentionally opposite** `ensure_ascii` settings: `kailash.trust._json.canonical_json_dumps` (the `kailash.delegate.*` cross-SDK encoder) emits raw UTF-8 (`ensure_ascii=False`) to match Rust `serde_json`'s default, while the trust-plane signing family (`kailash.trust.signing.crypto.serialize_for_signing` + the selective-disclosure / PACT-audit signers) emits ASCII-escaped `\uXXXX` (`ensure_ascii=True`) to match the pinned `trust-plane-canonical.json` fixture (#959). Both encoders' docstrings now state the full canonical contract (`ensure_ascii`, `sort_keys`, separators, no-Unicode-normalization) and explain why unifying them is a breaking cross-SDK signing-format migration (tracked in #1258, decision: do not unify). Cross-SDK byte-vectors pinned at `tests/test-vectors/delegate-canonical.json` + `tests/test-vectors/trust-plane-canonical.json`. **Documentation + test-vector only — zero runtime/API/behavior change** (both encoders behave exactly as in 2.29.2).

## [2.29.2] - 2026-06-04

### Security

- **Connection-pool keys no longer leak credentials into logs, metrics, or diagnostic return values (#1260)** — `AsyncSQLDatabaseNode` pool keys embed a raw connection string (`postgresql://user:pass@host/db`) in their third `|`-segment (per `_generate_pool_key`); Redis pool keys are `redis://:pass@host/dbN`. Pool-lifecycle log lines (disposal, cleanup, the per-pool lock manager, the idle-pool reaper, the fallback-pool path) interpolated the **full key at WARN/ERROR level** — which ships to log aggregators that typically have broader access than the database itself — leaking the credential. The Prometheus metrics layer (`kailash.monitoring.asyncsql_metrics`) used the raw key as a metric **label value** (same aggregator exposure, plus an unbounded-cardinality hazard), `PoolExhaustedError` embedded it in its message and `.pool_key` attribute, and several public diagnostic surfaces returned it verbatim (`AsyncSQLDatabaseNode.get_pool_info` / `get_pool_metrics` / `pool_keys` / `get_lock_metrics`; `RedisPoolManagerNode` pool-status / health-report / exec-result / cleanup return values). A new shared helper `kailash.utils.url_credentials.redact_pool_key` masks **only** the credential-bearing connection-URL segment via the canonical `mask_url` (`postgresql://***@host`), preserving the loop-id / db-type / pool-size segments (and the Redis db index) for forensic correlation; redaction is deterministic, so log/metric correlation still works and Prometheus label cardinality is now bounded. Every log line, metric label, exception, and diagnostic return value across `async_sql.py`, `exceptions.py`, `redis_pool_manager.py`, and `asyncsql_metrics.py` routes through the helper. The helper reconstructs the connection-string field from the middle `|`-segments so a literal `|` inside a password cannot leak the password tail. Pre-existing — gated to disposal / error / diagnostic paths, and connection strings often use env-var / `.pgpass` passwords; severity LOW-MEDIUM. Follow-up from the #1248 security review.

## [2.29.1] - 2026-06-04

### Fixed

- **Canonical-JSON signing encoders reject `NaN`/`Infinity` + non-string object keys (#1243)** — both canonical-JSON signing encoders silently emitted the non-JSON tokens `NaN`/`Infinity` (they omitted `allow_nan=False`) and silently stringified non-string object keys, producing signing pre-images that the paired decoder, Rust `serde_json`, and W3C-VC verifiers cannot read back — breaking cross-implementation signature verification. `kailash.trust._json.canonical_json_dumps` (the delegate/SPEC-09 cross-SDK encoder) now passes `allow_nan=False` (symmetric with `canonical_json_loads`) and rejects non-string object keys via a recursive producer-side guard with `json.dumps`-style cycle detection (a cyclic payload raises `ValueError`, caught by the call sites' `except (TypeError, ValueError)` taxonomy, rather than an uncaught `RecursionError`); shared DAG substructures are still accepted. The live Ed25519/HMAC signing pre-image `kailash.trust.signing.crypto.serialize_for_signing` (used across the trust plane, W3C-VC interop, multi-sig, rotation, PACT envelopes, reasoning traces) had the identical `allow_nan` hole and now passes `allow_nan=False` too. Large integers outside the JS-safe range are intentionally NOT rejected (the parity scope is Python ↔ Rust, both lossless on 64-bit+ ints; e.g. nanosecond-timestamp signing payloads). Follow-up #1258 tracks the `ensure_ascii` divergence + non-ASCII cross-SDK byte-vector pinning between the two encoders.
- **`LocalRuntime` / `AsyncLocalRuntime` teardown no longer disposes async-SQL pools owned by other live event loops (#1248)** — `LocalRuntime`'s sync-bridge teardown (`_execute_sync.run_in_thread`) and `_cleanup_event_loop`, plus `AsyncLocalRuntime.cleanup`, called `AsyncSQLDatabaseNode.clear_shared_pools(graceful=True)` unconditionally — disposing _every_ pool in the process-wide registry, including connection pools created on, and still owned by, a different, _live_ event loop. The owning loop then hit `RuntimeWarning: ... attached to a different loop`, was forced to re-initialize its pool (churn), and saw intermittent query failures under concurrent load — affecting any app that runs `LocalRuntime` in a worker thread (or `AsyncLocalRuntime` in a request handler) while async `AsyncSQLDatabaseNode` / DataFlow express pools are live on another loop. `clear_shared_pools` gains an optional keyword-only `loop_id` filter (pool keys begin with `f"{loop_id}|"` per `_generate_pool_key`); all three teardown paths now pass `loop_id=id(loop)`, disposing only their own loop's pools and leaving other live loops' pools intact. A loop-scoped clear also skips the blanket `_PROCESS_POOL_REGISTRY.clear()` so cap accounting for other loops' pools is preserved. `loop_id=None` (default) keeps the original dispose-everything behavior for `cleanup_all_pools` / test teardown — backward compatible. Follow-up #1260 tracks pre-existing pool-key-in-logs credential masking.
- **SQLite trust stores close every per-thread connection on `close()` (#1245)** — `SQLitePostureStore.close()`, `SqliteTrustStore._sync_close()`, and `SqliteTrustPlaneStore.close()` closed only the _calling thread's_ SQLite connection. Connections are cached per-thread via `threading.local`, so any connection opened on a worker thread (e.g. when a caller runs the synchronous store methods off the event loop via `asyncio.to_thread`) was never closed — leaking the SQLite connection / file descriptor until GC, surfacing as `ResourceWarning: unclosed database` and preventing downstreams from enabling `-W error::ResourceWarning`. Each store now tracks every per-thread connection in a lock-guarded `_all_conns` set and closes them all on close(); connections are opened with `check_same_thread=False` so the teardown can close them cross-thread (each connection is still _used_ only on its creating thread; the sole cross-thread access is the close-all at shutdown). The closed flag is flipped before the close sweep to close the close-vs-operate race window.

## [2.29.0] - 2026-06-02

### Added

- **`delegate.SignedActionEnvelope` now exposes `observed_at` as a first-class field (#1209)** — a write envelope's signed timestamp was committed inside `canonical_bytes` (so verification was cryptographically sound) but was not exposed as a field, so verifying a write envelope required the caller to supply `observed_at` out-of-band; it could not be re-derived from the envelope the way the read path re-derives it from `AttestedReadReceipt.observed_at`. `SignedActionEnvelope` now carries `observed_at: datetime` (placed before the defaulted `payload` field), symmetric with `AttestedReadReceipt`, so a write envelope is independently verifiable from the envelope object alone — the verifier reconstructs `canonical_bytes` from `envelope.observed_at` + `envelope.payload` with no out-of-band timestamp. Regression: `tests/regression/test_issue_1209_action_envelope_observed_at.py` (structural symmetry with `AttestedReadReceipt`; verify-from-envelope-alone round-trip; tampered-`observed_at` fails re-derived verification; `observed_at` is required-no-default).

### Changed

- **BREAKING (`delegate` module, new in 2.26.0): `SignedActionEnvelope` constructor now requires `observed_at` (#1209)** — the new field is required (no default), symmetric with `AttestedReadReceipt`; a default would let an envelope ship without the committed timestamp, defeating independent verifiability. New-shape `Connector.write` implementations that construct `SignedActionEnvelope` directly MUST pass `observed_at`. **Migration:** add `observed_at=datetime.now(timezone.utc)` (or the action's actual observation time, matching the timestamp committed into `canonical_bytes`) to each `SignedActionEnvelope(...)` call. Scoped to the `delegate` module; no other public surface is affected.

## [2.28.4] - 2026-06-01

### Fixed

- **Gateway `/workflows/{name}/execute` now honors a typed HTTP status raised by a workflow node (#1218)** — the `WorkflowAPI` execute route (`src/kailash/api/workflow_api.py`, mounted by `create_gateway` / `WorkflowServer`) collapsed every workflow-execution exception to a generic HTTP 500, discarding a typed status carried by the exception. A node raising a typed-status error (the `nexus.extractors.NexusHandlerError` contract: an `int` `status_code` in 100-599 **and** a `body`) over this path was reported to operators as an internal 5xx bug instead of the intended 4xx. The fix walks the exception `__cause__`/`__context__` chain (cycle-guarded — the async runtime wraps node exceptions in `WorkflowExecutionError(...) from e`) and, when it finds a link carrying **both** `status_code` (100-599) and a `body` attribute, maps that status + body to the HTTP response; everything else still collapses to the canonical `{"detail": "Internal server error"}` 500 with the raw error logged server-side and never echoed. The typed branch requires the `body` attribute (not `status_code` alone) so a stray `HTTPException(404, detail)` raised in a node does not surface `str(exc)` to the client. Regression: `packages/kailash-nexus/tests/integration/nexus/test_workflow_execute_typed_status_wiring.py` (typed 422 → typed body; genuine `RuntimeError` → 500 no-leak; `HTTPException`-status-only → 500 no-leak).

## [2.28.3] - 2026-06-01

### Fixed

- **Runtimes no longer drop `contextvars.Context` across their thread boundaries (#1200)** — `AsyncLocalRuntime`, `LocalRuntime`, `ParallelRuntime`, and `ParallelCyclicRuntime` dispatched sync node execution across a thread boundary (`loop.run_in_executor`, a raw `threading.Thread`, and `ThreadPoolExecutor.submit`) without propagating the caller's `contextvars.Context`. A `ContextVar` set before `execute()` / `execute_workflow_async()` was invisible inside a node's `run()` — the node saw the variable's default instead of the caller-set value, unlike the stdlib `asyncio.to_thread` convention. The fix snapshots `contextvars.copy_context()` in the caller frame and dispatches the thread-boundary callable through `ctx.run(...)` at all six affected sites (`async_local.py` ×2 `run_in_executor`, `local.py` raw `threading.Thread` + sync-in-async `ThreadPoolExecutor`, `parallel.py` `run_in_executor`, `parallel_cyclic.py` `submit`). Parallel paths use a fresh `ctx.copy()` per concurrent dispatch so a single `Context` is never entered concurrently. The distributed-worker path (`distributed.py`) is intentionally excluded: it reconstructs the workflow from a Redis-queued task in a separate process, so the original caller's context is already gone across the queue boundary. Regression: `tests/integration/runtime/test_contextvars_propagation.py` (8 tests — propagation across all five in-process dispatch paths + negative no-leak-when-unset cases).

## [2.28.2] - 2026-06-01

### Fixed

- **Node init-param-capture no longer crashes on a typed `self.config`** — `Node.__init_with_capture` merged init params into `self.config` by iterating `name in self.config` and assigning `self.config[name]`, assuming the dict that `Node.__init__` creates. A `Node` subclass that deliberately replaces `self.config` with a typed config object (e.g. kaizen's `BaseAgentConfig`, as many `kaizen_agents` pattern nodes do) raised `TypeError: argument of type '<Config>' is not iterable` at construction, breaking ~93 `kaizen_agents` Pipeline orchestration tests. The capture is a dict-only convenience and now skips (rather than crashes) when `self.config` is not a mapping. Regression: `tests/regression/test_node_init_capture_non_dict_config.py`.

## [2.28.1] - 2026-05-29

### Fixed

- **Durable gateway no longer serves stale cached GETs (#937)** — the request deduplicator cached responses for ALL HTTP methods with a 1-hour TTL, so a second identical GET returned a stale body (e.g. a schedule still showing `enabled` after a disable). Deduplication is meaningful only for mutating methods (idempotent retry of POST/PUT/PATCH/DELETE); GET/HEAD/OPTIONS are safe reads that must reflect current state. Both `DurableWorkflowServer` and `DurableAPIGateway` now gate the dedup cache check + response store on a `_should_deduplicate(request)` predicate (`request.method not in {GET, HEAD, OPTIONS}`). Durability tracking (audit events, checkpoints) still applies to all methods — only the dedup cache is skipped for safe reads. Regression: `tests/regression/test_issue_937_safe_method_dedup.py`.

## [2.28.0] - 2026-05-28

### Fixed

- **`delegate` audit-chain sign/verify contract is now satisfiable (HIGH, #1182)** — `AuditChainEngine.emit_event`'s prior signature contract was structurally unsatisfiable, blocking `DelegateRuntime.execute()` end-to-end under any real (non-`NullVerifier`) verifier. The sign-site signed the payload alone while the verify-site verified against the full pre-signature dict (`sequence` + `previous_hash` + `event_type` + `event_payload` + `signer_delegate_id` + `signed_at`), and the engine assigns `sequence` / `previous_hash` / `signed_at` AFTER receiving the signature — so no caller could ever produce a matching signature; `AuditChainSignatureError` raised at `sequence=0`. The `NullVerifier` masked the bug. The fix introduces a single shared `content_signing_bytes(event_type, event_payload, signer_delegate_id)` helper routed through `canonical_json_dumps`; both sign-sites (`runtime._emit_phase_audit`, `runtime`'s `with_posture` rotation emit, `dispatch` audit-event emit) AND the engine verify-site now produce the identical byte-string via this single helper. `AuditChainEntry` gains `to_content_signing_bytes()` delegating to it; `to_signing_bytes()` is unchanged (the cross-SDK full-entry canonical-shape contract + conformance vectors still depend on it). **Tamper-evidence is preserved, not weakened:** authorship (Ed25519 over `event_type` + `event_payload` + `signer_delegate_id`, defeating cross-signer substitution) and ordering (hash-chain via `previous_hash` = SHA-256 of prior entry's full canonical dict including sequence + prior signature, anchored by the substrate `AuditAnchor`) remain orthogonal defenses; excluding engine-assigned fields from the signature does not open a tamper hole because those fields were never the signature's job. Regression coverage: `tests/regression/` modules tagged `test_issue_1182_*` (real Ed25519, no mocking, no `NullVerifier`) — sign/verify byte-equality, `emit_event` accepts a content-pre-image signature, `DelegateRuntime.execute()` reaches `COMPLETED` under `Ed25519Verifier` with a real no-op connector, hash-chain detects payload/sequence tampering; payload-only signature (pre-fix behavior) is rejected.

- **Async durable resume short-circuits completed nodes (HIGH, #1185)** — `AsyncLocalRuntime._execute_node_async` / `_execute_sync_node_async` previously invoked `node.execute_async()` / `execute()` unconditionally, so resuming a durable workflow with the same `idempotency_key` re-executed every node already completed and checkpointed on the prior run — firing side effects twice and breaking the "exactly once on resume" guarantee the sync `LocalRuntime` already honors. The fix adds `_w1_resume_short_circuit`, the async sibling of the sync gate: it reads the W1 `ExecutionTracker` that `execute_workflow_async` rehydrates from the prior checkpoint blob onto `context._w1_execution_tracker`; when a node is already completed it feeds the cached output into the per-run `AsyncExecutionTracker` via `record_result` (so dependents receive the restored output through the same `node_outputs` path a fresh execution populates), re-records completion into the W1 tracker (idempotent, keeps the checkpoint consistent), and returns `True` so the caller skips `execute_async` and the re-save/re-dispatch. Wired at the top of both per-node entry points. Reuses the inherited `LocalRuntime` checkpoint machinery (same `ExecutionTracker.is_completed` / `get_output` / `record_completion`) — no parallel notion of "completed". The sync runtime path is unchanged.

### Changed

- **CI: `python-no-eval` pre-commit hook now excludes 18 false-positive paths (#972 → PR #1190)** — extends the `python-no-eval` regex hook's exclude list to clear 18 documented false-positive matches across `src/kailash/`, `packages/kailash-dataflow/`, and tests. The hook continues to flag genuine `eval()` / `exec()` usage on user input per `rules/security.md` § "No eval() on user input"; this commit narrows the regex scope to test scaffolding that calls `model_validator(...)` / `eval_metric=...` / `.evaluate(...)` (none of which are the dangerous `eval` builtin). No behavior change at runtime; pre-commit CI is now clean across all repository paths.

- **DataFlow test helper rename — eliminate shadowed inner-function on `pyright` (#1131 → PR #1193)** — `tests/integration/dataflow/test_mcp_integration.py` renamed an inner helper that shadowed a module-scope identifier, restoring `pyright --level error` to zero diagnostics across the dataflow integration suite. No production source change.

- **Codify proposal landing — three pending sessions appended atomically (#1189)** — `.claude/.proposals/latest.yaml` codify-cycle proposal landing per `rules/artifact-flow.md` § "Append, Never Overwrite Unprocessed Proposals". Internal artifact-flow only; no consumer-visible API change.

### Migration

- No breaking changes. `pip install --upgrade kailash` from 2.27.x → 2.28.0 is drop-in. The audit-chain contract fix in #1182 changes signed-bytes content, but the prior contract was structurally unsatisfiable under real verifiers — no working downstream caller can have depended on it. The async durable resume fix in #1185 is purely additive: behavior changes only when the same `idempotency_key` is replayed against an already-completed node, which previously double-fired and now correctly short-circuits.

### Notes

- Six PRs land in this release: #1189 (codify proposal), #1190 (CI `python-no-eval` exclude), #1191 (#1185 async durable resume fix), #1192 (#1182 delegate audit-chain fix), #1193 (#1131 pyright rename), #1194 (#1012 nexus instance-API warning — shipped via `kailash-nexus 2.6.4`).
- Companion `kailash-nexus 2.6.4` release ships the #1012 nexus instance-API `UserWarning` elimination (`@app.handler` registration no longer pollutes startup logs).
- Framework SDK pins in `packages/kailash-{dataflow,nexus,kaizen}/pyproject.toml` advanced to `kailash>=2.28.0`. Existing framework wheels on PyPI keep their prior pins (admit 2.28.0 via minor backward-compat); the new pins ship with the next respective framework release.

## [2.27.0] - 2026-05-27

### Added

- **`from_brief()` — natural-language brief → executable framework primitive** via an LLM-mediated `scrub → reason → validate → allowlist → realize` pipeline (closes #1125). Part of a platform-wide family spanning 5 framework surfaces; the surfaces in this `kailash` core wheel:
  - `Workflow.from_brief(brief, **kwargs)` — Core SDK classmethod; returns a `WorkflowBuilder` (`.build()` → `LocalRuntime.execute()` runs end-to-end).
  - `kailash.workflow.workflow_from_brief(brief, *, model=None, confidence_threshold=0.6, allowed_node_types=None)` — the underlying module-level function the classmethod delegates to.
  - `kailash.bootstrap(brief, *, profile="dev", model=None, confidence_threshold=0.6)` — returns a `BootstrapConfig` (db / model / runtime / target).
  - `WorkflowPlan` + `WorkflowPlanSignature` typed plan contract exported from `kailash.workflow.from_brief`.
  - The remaining 3 surfaces ship in their own packages: `DataFlow.from_brief(...)` (kailash-dataflow), `Kaizen.signature_from_brief(...)` (kailash-kaizen), `kailash_ml.from_brief(...)` (kailash-ml).
  - **Lazy-kaizen contract**: LLM reasoning flows through Kaizen, imported only when actually needed. `import kailash` and `Workflow.from_brief` do not pay for kaizen at import time; on a bare slim-core install (no kaizen), reaching the kaizen-backed surface (e.g. `WorkflowPlanSignature`) raises a clear `ModuleNotFoundError: No module named 'kaizen'` at the call site rather than at `import kailash`.

### Security

- **`from_brief()` defaults to a positive safe-node allowlist** (default-deny). Replaces the prior "all registered nodes minus a denylist" model, which was unsound by construction — any new node type registered between releases was implicitly trusted. The new model:
  - **Allowlist**: 43 vetted node types (CSV/JSON/SQL readers + writers, HTTP request/response, validation primitives, transform, filter, merge, switch, etc.). `kailash.workflow.from_brief._SAFE_NODE_TYPES` is the canonical list. Any node type NOT in it is rejected — including every code-execution / SSRF / arbitrary-import surface (`PythonCodeNode`, `AsyncPythonCodeNode`, `SharePointGraphReader` / `SharePointGraphWriter`, etc.), which are excluded both by absence from the allowlist AND, for the highest-risk subset, by the explicit denylist floor below.
  - **Enforcement at the choke point**: `_realize()` enforces the allowlist at `add_node` time — `validate_plan()` is no longer the sole gate, closing the prior bypass where a `WorkflowPlan` (which nests `node_type` inside `plan.nodes[i]` instead of the top-level shape `validate_plan` expected) could realize disallowed nodes.
  - **Denylist floor**: a hardcoded `_DANGEROUS_NODE_TYPES` set of 12 explicitly-dangerous types (`PythonCodeNode`, `AsyncPythonCodeNode`, `DataTransformer`, `BatchProcessorNode`, `CodeValidationNode`, `ConvergenceCheckerNode`, `MultiCriteriaConvergenceNode`, `ValidationTestSuiteExecutorNode`, `WorkflowValidationNode`, `WorkflowNode`, `SharePointGraphReader`, `SharePointGraphWriter`) is subtracted BEFORE the allowlist applies, so any future allowlist expansion still cannot accidentally re-admit these surfaces.
  - **Inverse-completeness test**: `tests/unit/workflow/test_from_brief_safe_allowlist.py` walks the MRO of every allowlisted node type and AST-scans every source path for `exec` / `eval` / `compile` / `import_module` / `__import__` / unsafe-deserialization (`pickle.loads`, `marshal.loads`, `dill.loads`, `cloudpickle.loads`, `yaml.load`) / `CodeExecutor` references — so a future code-executing node added under a familiar-looking name fails the allowlist test, not production.
  - **NaN/inf rejection at plan-construction**: `BriefPlan` (`kailash._from_brief.validator`) now uses `model_config = ConfigDict(extra="forbid", allow_inf_nan=False)` AND `check_confidence` rejects non-finite or out-of-range values with `BriefInterpretationError(..., malformed=True)`. Closes a class of confidence-bypass attacks where a brief could ship a `NaN`/`inf` confidence to pass downstream thresholds.
  - Together these close the 2 CRITICAL findings + 1 MEDIUM (SharePoint SSRF class) + 1 confidence-gate-bypass finding surfaced across 6 redteam rounds during the #1125 review cycle.

### Changed (breaking, delegate substrate)

- **`Connector.authenticate` / `.write` / `.read` default implementations now raise `NotImplementedError`** via `_legacy_unsupported(name)` instead of returning empty-crypto envelopes / `Principal(tenant_id=None)`. Closes GH #1177 (empty-crypto orphan defaults on write/read — downstream verifiers that did not explicitly check `len(signature) > 0` / `len(attestation) > 0` would treat the prior defaults as authenticated/attested) + GH #1178 (`Principal(tenant_id=None)` from the prior `authenticate` default silently slipped through tenant-scoped authorization checks in multi-tenant deployments). The inline defaults were a transitional convenience carried over from the pre-2.26.0 `__init_subclass__` proxy era and were never part of the documented audit-grade contract — `LegacyInvokeConnector` and direct legacy `invoke()`-only subclasses MUST use `.invoke()` for all dispatch; reaching for `.authenticate()` / `.write()` / `.read()` now gets a clear refusal rather than a silent unverifiable envelope. The 3 newer ACCESSOR defaults (`.revocation` / `.ledger` / `.auth_verifier`) already raised via `_legacy_unsupported` since 2.26.0; this change extends the same defense-in-depth pattern to the 3 primitives.

### Migration

- Connector subclasses that need `.authenticate()` / `.write()` / `.read()` MUST implement them explicitly (override with the real cryptographic exchange). The prior inline-default behavior (empty signature / empty attestation / `Principal(tenant_id=None)`) was security-defense-in-depth unsafe and is removed without a deprecation shim — the prior return values were structurally indistinguishable from a real authenticated/attested envelope at the type level, so a `DeprecationWarning` shim would have continued to ship the same defense-in-depth gap during the deprecation window. New-shape connectors that already override the 3 primitives are unaffected.
- Consumers calling the 3 primitives on a `LegacyInvokeConnector` (or any subclass that does not override them) will now receive `NotImplementedError: Connector primitive 'write' not implemented by this legacy invoke()-only connector — use connector.invoke(...) or migrate the connector to the 4-primitive shape`. Route those call sites through `.invoke(...)`.

## [2.26.2] - 2026-05-25

### Fixed

- **`kailash.delegate` security-hardening sweep — three follow-ups from the 2.26.0 known-issues list** — closes the M1/M3/M4 defense-in-depth gaps the v2.26.0 entry flagged as non-blocking:
  - **M1 — `DelegateRuntime._consumed` TOCTOU window.** Concurrent `execute()` calls on the same runtime instance both observed `_consumed=False` before either set it, silently violating the §7 TAOD phase monotonicity ("runtime is single-shot per receipt"). Fix: `async with self._consume_lock: asyncio.Lock()` wraps both the check and the set; lock is per-instance, freshly created in `__init__`, and `with_posture()` returns a fresh runtime with a fresh lock (Invariant 5 preserved). Regression test exercises N=10 concurrent `execute()` under `asyncio.gather` and asserts exactly one success; revert-probe verified.
  - **M3 — `_check_payload_depth` only enumerated `dict` / `list` / `tuple`.** Custom container subclasses (`UserDict`, `UserList`, classes deriving from `collections.abc.Mapping`/`Sequence`/`Set`, frozenset-of-frozensets) bypassed the C6-1 DoS recursion-depth defense — an attacker-crafted payload triggered O(depth) recursion in `canonical_json_dumps` downstream. Fix: replace concrete `isinstance` with `collections.abc.Mapping` + `Sequence` (excluding `str`/`bytes`/`bytearray`) + `Set` (covers `frozenset`, `set`, `dict_keys`, `MappingView`). Regression tests cover UserDict, UserList, abstract Mapping, frozenset, plain set, memoryview exclusion, plain-dict/list regression guards (14 tests total).
  - **M4 — `_tenant_id_hash` used unsalted SHA-256.** Short tenant IDs (UUIDs, account-ID integers, organization slugs) were rainbow-reversible by log-readers who knew the tenant ID space; the hash leaked into `CascadeTenantIsolationError` messages that surface to cross-tenant error returns and log aggregators. Fix: HMAC-SHA-256 keyed by a per-process salt (`_TENANT_HASH_SALT = secrets.token_bytes(32)`, eager module-init so the import-lock guarantees thread-safety). Salt is per-process (cross-process correlation broken by design, per-process audit correlation preserved); `fork()` workers inherit the parent salt (same-deployment correlation in-scope); `importlib.reload()` rotates (test-infrastructure only); chroot/jail entropy-starved deployments must provision `/dev/urandom` or equivalent (documented). Regression tests include subprocess cross-process unpredictability + `ThreadPoolExecutor(10)` concurrent first-call witness (7 tests total).

### Notes

- Test count: 487 baseline → 512 passed + 1 skipped (+25 new regression tests). Pyright `src/kailash/delegate/ --level error` = 0 errors. `pytest -W error` clean (no DeprecationWarning / ResourceWarning / RuntimeWarning).
- Convergence: 3-round `/redteam` across 6 parallel agent verdicts (reviewer + security-reviewer + closure-parity in Round 1, security-reviewer + closure-parity in Round 2, security-reviewer + reviewer in Round 3); 2 consecutive clean rounds achieved (R2 + R3). Full receipt: `workspaces/issue-1035-delegate-py/04-validate/10-cycle2-convergence.md`.
- All three fixes are non-breaking. `DelegateRuntime.execute()` semantics unchanged for single-shot use (the lock only contests concurrent callers). `_check_payload_depth` still raises the same `DispatchValidationError`; coverage now strictly broader. `_tenant_id_hash` still returns an 8-char hex prefix; the value is now non-deterministic across processes by design.
- Delivered via PR #1170 (cycle-2 hardening + R1 MED follow-ups, 18 commits) — closes the "Known follow-ups" called out in the 2.26.0 release notes for M1 (`_consumed` TOCTOU), M3 (payload-depth subclass coverage), and M4 (unsalted tenant hash).

## [2.26.1] - 2026-05-25

### Fixed

- **`from kailash.delegate import ...` now works on a bare `pip install kailash`** — 2.26.0 shipped `kailash.delegate.verifier` with a module-scope `from cryptography...` import. Because the delegate package is inside the slim-core import closure and `cryptography` lives in the `[trust]`/`[server]` extras (NOT core dependencies), a bare install raised `ModuleNotFoundError: No module named 'cryptography'` on the documented #1035 import line. The cryptography import is now lazy inside `Ed25519Verifier.__init__` — `NullVerifier` (the default) needs no cryptography; `Ed25519Verifier` raises a clear `ModuleNotFoundError` at construction if the `[trust]`/`[server]` extra is absent (the established "loud failure at call site" pattern; matches the #1154 lazy-`filelock` precedent that defends slim-core). Behavioral regression tests (`tests/regression/test_issue_1035_delegate_slim_core_import.py`) assert the slim-core import invariant via subprocess + `sys.modules` introspection.

### Notes

- Corrective patch for 2.26.0 (yanked from PyPI). All 2.26.0 functionality is unchanged — only the cryptography import timing moved from module-scope to lazy. 489 delegate tests pass (487 + 2 new regression).

## [2.26.0] - 2026-05-25

### Added

- **Delegate signature verification — `kailash.delegate.verifier`** — new `Verifier` Protocol, fail-closed `NullVerifier` (rejects all signatures), and `cryptography`-backed `Ed25519Verifier`. Wired into `AuditChainEngine` (verification inside the `_emit_lock` critical section before substrate-anchor append), `TenantScopedCascade` (`cascade_child` + `register_root_grantee` now require a cryptographically-verified `grant_proof`; new `CascadeSignatureError`), and `DelegateRuntime`. Before this release the substrate stored per-event Ed25519 signatures but validated them for hex-shape only — verification is now real. Goes **beyond** the v2.25.x disclosed limitation (issue #1147, which was closed via README disclosure): `PrincipalDirectory` now carries a `verification_keys` registry + `public_key_for()` accessor binding signer IDs to public keys in-primitive.
- **`Connector` 4-primitive ABC** — `kailash.delegate.dispatch.Connector` rebuilt from a single `invoke()` to the audit-grade shape: required primitives `authenticate` / `write` / `read` plus required accessors `revocation` / `ledger` / `auth_verifier`. Backwards-compatible: existing `invoke()`-only connectors keep working via the `LegacyInvokeConnector` adapter + an `__init_subclass__` auto-proxy.
- **`LifecycleState.advance_to`** — enforces the single linear delegate lifecycle chain `PROPOSED → INSTANTIATED → POSTURE_GRADED → ACTIVE → RETIRED → ARCHIVED`; illegal edges (skips, backward transitions, post-`ARCHIVED`) raise `LifecycleError`.
- **#1035 acceptance-gate aliases** — `Delegate`, `ConstraintEnvelope`, `GenesisRecord`, `PostureState`, `AuditChain` exposed as aliases of the disambiguated canonical names (`DelegateRuntime`, `DelegateConstraintEnvelope`, `DelegateGenesisRecord`, `Posture`, `AuditChainEngine`). The literal #1035 import line `from kailash.delegate import Delegate, ConstraintEnvelope, PrincipalDirectory, GenesisRecord, PostureState, AuditChain, Connector` now resolves. Both forms are the same class object at runtime; new code should prefer the prefixed names to avoid collision with `kaizen_agents.delegate.Delegate`.

### Notes

- **Backwards-compatible (minor).** No existing public import or connector breaks. `DispatchSurface(verifier=...)` defaults to `None` (verification skipped) to preserve existing callers — strict-security deployments MUST bind `NullVerifier` or `Ed25519Verifier` explicitly. A future major may flip the default to fail-closed once callers migrate.
- **Cross-implementation byte-match receipts are DEFERRED** per `cross-sdk-inspection.md` Rule 4 — the cross-SDK Ed25519 library is unconfirmed in-tree; ≥3 byte-vector test cases will be pinned when the cross-SDK canonical is published. The comparator-behavior contract (`receipts_agree`) is exercised end-to-end today; only the cross-SDK byte canonical is pending.
- **Known follow-ups (non-blocking, tracked):** `DelegateRuntime.advance_lifecycle` runtime wrapper is defined but unwired pending the `Delegate.compose()` composer (the production hot path uses the separate, fully-wired TAOD `state` axis); `_tenant_id_hash` is unsalted SHA-256; `DispatchSurface._consumed` has a narrow concurrent-execute TOCTOU window.
- Delivered via PR #1164 (3-shard parallel `/redteam`-to-convergence cycle — Round 1: 6 CRITICAL + 5 HIGH; two consecutive clean verification rounds) plus PR #1165 (R1 reconciliation — docstring accuracy, signer-contract tightening, `verifier.py` import-safety). 487 delegate tests pass (+69 over the v2.25.2 baseline).

## [2.25.2] - 2026-05-23

### Documentation

- **CHANGELOG correction for v2.25.0 (continued, 4th inaccuracy) — audit-chain forensic key-registry gap NOT closed in 2.25.0** — the v2.25.1 entry corrected three inaccuracies in the v2.25.0 prose; a fourth was missed. The v2.25.0 entry (lines 37 + 45) claims "the audit-chain forensic gap was the only deferred item that flipped status this release (PR #1155)" and "With 2.25.0, the audit-chain forensic key-registry gap (previously deferred) is closed." Both statements are **incorrect**:
  - PR #1146 closed the H1 **grantee** registry gap (`TenantScopedCascade.__grantees` + `register_root_grantee()`), not the audit-chain forensic key registry. The two gaps are distinct.
  - The audit-chain forensic key-registry gap remains **open**, tracked at [issue #1147](https://github.com/terrene-foundation/kailash-py/issues/1147). `README.md` § "Delegate composition primitive — Pre-Pledge v0" correctly discloses this: `AuditChainEntry` stores per-event Ed25519 signatures, but the primitive does NOT bind signer keys to a public-key registry, fingerprint, or key-rotation epoch. Out-of-band identity-to-key binding is required; operators MUST provide their own attestation surface.
  - Per `git.md` no-amend rule, the v2.25.0 prose is preserved in git history; this entry corrects the public-facing disclosure record. The v2.25.1 corrections for `PrincipalKind`-type, valid-values, and `UnregisteredGranteeError` stand.

### Notes

This is a structural follow-up patch correcting the public-facing release-notes record for v2.25.0. No code changes; no public API changes; no behavior change. All v2.25.0 functionality (`PrincipalKind` discrimination, grantee-registry enforcement, audit-chain E2E tests) ships unchanged from v2.25.1.

## [2.25.1] - 2026-05-23

### Fixed

- **Slim-core install budget — lazy-import `filelock` in `trust/_locking.py` (#1154)** — `kailash.trust._locking::file_lock()` is now the sole filelock consumer and lazy-imports `from filelock import FileLock, Timeout` inside the function body. This breaks the `kailash.delegate.types → kailash.trust._locking → filelock` eager-import chain that the 2.24.1 hotfix worked around by promoting `filelock>=3.0` into slim-core `[project.dependencies]`. With #1154 landed, `filelock>=3.0` is removed from slim-core and returned to the `[trust]` extra. `pip install kailash` (bare) no longer pulls filelock; `pip install kailash[trust]` continues to install it as before. `validate_id` is still the canonical path-traversal guard (`trust-plane-security.md` Rule 2). 3 regression tests pin the invariants: (a) `from kailash.trust._locking import validate_id` does not load filelock into `sys.modules`; (b) `import kailash.delegate.types` does not load filelock; (c) `file_lock(...)` still works end-to-end when filelock is installed.

### Documentation

- **CHANGELOG correction for v2.25.0** — the 2.25.0 entry has three inaccuracies in its prose (the shipped code IS correct; only the release notes mis-described it). For accurate reference:
  - `PrincipalKind` is a `typing.Literal["sovereign", "service_account", "delegate"]` type alias — NOT a `Python Enum`.
  - The valid `principal_kind` values are `"sovereign"`, `"service_account"`, `"delegate"` — NOT `"human"`, `"agent"`, `"service"`.
  - H1 grantee-registry enforcement raises the **pre-existing** `DispatchCascadeViolationError` — no new `UnregisteredGranteeError` class was added. The H1 wave added `TenantScopedCascade.grantees` (property) and `TenantScopedCascade.register_root_grantee()` (method); the error class itself was already part of the public surface in 2.24.0.

### Notes

This is a structural follow-up patch closing #1154 (queued from 2.24.1 hotfix). The slim-core size budget is restored to its pre-2.24.0 baseline. No public API changes; all 2.25.0 functionality (PrincipalKind discrimination, grantee-registry enforcement, audit-chain E2E tests) ships unchanged.

## [2.25.0] - 2026-05-23

### Added

- **`kailash.delegate.types.PrincipalKind` — §10 G1 principal-kind discrimination (#1143)** — new `PrincipalKind` enum (`Enum["human", "agent", "service"]`) added to `DelegateIdentity` + `Role` discriminator on the public API. `DispatchSurface.bind()` and `dispatch()` now cross-validate `principal_kind` at construction (capability snapshot) AND at dispatch time (re-check on rebind) per the §10 G1 conformance vector DV-10-001. `PrincipalKind` is exported in `kailash.delegate.__all__` and pinned by count tests. DV-10-001 vector is no longer xfail-strict — it runs natively (PR #1157).
- **`TenantScopedCascade` grantee registry — H1 forensic key-tracking gap closure (#1146)** — `TenantScopedCascade` now carries a name-mangled `__grantees` registry (accessed via `_TenantScopedCascade__grantees`) of every grantee identity bound through `grant_to(...)`. `DispatchSurface.dispatch()` enforces the registry: a dispatch whose grantee identity was not previously enrolled raises `UnregisteredGranteeError` at gate order position 3 (lifecycle → principal_kind → grantee → capability). Closes the H1 holistic-/redteam follow-up disclosed in v2.24.0 README § "Pre-Pledge v0 status". Trust-boundary documented in class docstring; access is structurally guarded by Python name-mangling so external mutation requires the mangled form, never plain `cascade._grantees` (which raises `AttributeError`) (PR #1158).
- **D2 audit-chain hash-linkage E2E replay + D3 DV-5-001 runtime-end-to-end vector test (#1149, #1150)** — `tests/e2e/delegate/test_delegate_e2e_flows.py` extended with audit-chain hash-linkage replay assertions (D2: every emitted audit row chains to the prior row's hash byte-identically across replay) and DV-5-001 runtime end-to-end vector test exercising the full TAOD lifecycle through cascade-layer dispatch (D3). E2E flow A (happy path) now asserts cascade-layer redaction firing on widening reads (PR #1156).

### Documentation

- **S5 capability re-check site + audit-chain forensic key registry gap disclosure (#1147, #1148)** — README § "Delegate composition primitive — Pre-Pledge v0" clarified to name the S5 capability re-check site as `DispatchSurface.dispatch()` (the per-call re-check that catches post-construction state mutations) AND disclose the audit-chain forensic key-registry gap as a deferred item (now closed in 2.25.0 via #1146). README's "deferred items" enumeration updated; the audit-chain forensic gap was the only deferred item that flipped status this release (PR #1155).

### Notes

This release closes 6 of the holistic-/redteam follow-up issues filed at v2.24.0 (#1143, #1146, #1147, #1148, #1149, #1150 — six issues across four PRs). Two follow-ups remain tracked for future patches: #1086 (cross-SDK rs parity for `PrincipalKind` + grantee registry — blocked on cross-repo authorization per `repo-scope-discipline.md`) and #1154 (slim-core install budget restoration — lazy-import `filelock` in `trust/_locking.py`). Semver minor because `PrincipalKind` is a new public symbol in `kailash.delegate.__all__` and `UnregisteredGranteeError` extends the public exception surface; no breaking changes to existing public API.

### Pre-Pledge v0 status

`kailash.delegate` remains at pre-pledge v0. With 2.25.0, the audit-chain forensic key-registry gap (previously deferred) is closed; the 8 enforced invariants from 2.24.0 expand to include §10 G1 principal-kind discrimination and H1 grantee-registry enforcement. Two items remain explicitly deferred: cross-SDK byte-determinism conformance for vectors DV-3/DV-7/DV-9 (py-leads through 2.25.0; rs leadership pending), and the slim-core install budget restoration (#1154). Three explicit non-promises continue: no implicit retries, no shadow audit chains, no posture auto-upgrade. See README § "Delegate composition primitive — Pre-Pledge v0" for the full updated disclosure.

## [2.24.1] - 2026-05-22

### Fixed

- **`import kailash.delegate` failed on clean-venv install of 2.24.0 (CRITICAL)** — `kailash.delegate.types:46` eagerly imports `from kailash.trust._locking import validate_id` (the canonical path-traversal guard mandated by `trust-plane-security.md` Rule 2); `kailash.trust._locking:38` has a module-scope `from filelock import FileLock, Timeout`; `filelock` was declared only in the `[trust]` optional extra, not in core dependencies. Result: `pip install kailash==2.24.0` → `from kailash import delegate` → `ModuleNotFoundError: No module named 'filelock'`. Fixed by promoting `filelock>=3.0` to slim-core `[project.dependencies]` (duplicates the `[trust]` declaration so a bare install resolves delegate cleanly). Same failure class as `build-repo-release-discipline.md` Rule 2 "clean-venv installability is the done gate" + `deployment.md` "MUST: Eagerly-Imported Transitive Dependencies Are Declared By The Importing Package".

## [2.24.0] - 2026-05-22

### Added

- **`kailash.delegate` composition primitive — pre-pledge v0 (#1035)** — new public top-level module shipping the (Connector × Signature × ConstraintEnvelope × Executor) composition substrate under EATP audit. 8-shard build (S1-S8 over PRs #1130-#1144 + L1 cleanup #1145):
  - **S1 fences** — module + `kailash.delegate` namespace, Apache-2.0 license declaration, zero-engine-deps pre-commit fence (#1130).
  - **S2 + S2.5 canonical types** — substrate dataclasses, F5 type-state monotonic envelope (#1136 + #1131).
  - **S3 trust cascade** — `TenantScopedCascade`, `GrantMoment`, signed cascade chain (#1137).
  - **S4 audit chain** — `AuditChainEngine`, `WitnessedCrossAnchor`, signed audit row emission (#1137).
  - **S5 dispatch + Connector ABC** — `Connector` abstract base, `DispatchSurface`, `DispatchResult`, capability snapshot at construction, strict-type guard, 32-depth + 1MiB payload limits (#1138).
  - **S6 runtime spine** — `DelegateRuntime`, `TAODState`/`TAODTransition` (Think-Act-Observe-Decide lifecycle), `Posture` enum (L1-L5 + HALT) with rank ladder, `R2Composition` validator with `is`-identity checks, `RuntimeExecutionResult` with lossy `to_dict`/`from_dict` (commits `bdc89a9b4`, `5fcf935db`, `e9626a223` for S6 R1 audit-emit-before-state-advance + no-recurse `_advance_to_failed_no_audit` helper).
  - **S7 conformance schema** — `ConformanceVector`, `ConformanceVectorLoader.load_canonical()` with SHA-256 integrity check, `ConformanceVectorIntegrityError` tamper detection, `ConformanceReceipt` with `to_dict`/`from_dict`, `receipts_agree(rs, py)` cross-impl comparator with timestamp-exclusion, `assert_receipts_agree()`. 5 canonical vectors at `tests/fixtures/delegate-conformance/canonical.json` (DV-3-001, DV-5-001, DV-7-001, DV-9-001, DV-10-001). DV-5-001 + DV-10-001 vendored byte-for-byte per cross-SDK fixture-vendoring discipline. §7 TAOD phase monotonicity enforced at runtime via `self._consumed` guard + try/finally (commit `d4ad6a9b3`).
  - **S8 E2E + cross-impl receipts + pre-pledge README** — 8 end-to-end flows (Flow A happy path, B posture HALT, C tenant violation, C2 surface invariant, D signer failure no-recurse, E §7 single-shot, F ConformanceVectorLoader, G receipts_agree_dict identity); 3 Tier-2 cross-impl tests; README § "Delegate composition primitive — Pre-Pledge v0" disclosure enumerating 8 enforced invariants + 3 deferred items + 3 non-promises + how-to-verify + status.
- **Holistic post-multi-wave /redteam** across all 8 shards on main caught 1 L1 (workspace-path-leakage scrub in module docstrings, PR #1145) + 5 cross-shard follow-ups filed as #1146-#1150 — none blocking v2.24.0.

### Pre-Pledge v0 status

`kailash.delegate` is shipped at pre-pledge v0 per the README disclosure section. Users may rely on the 8 enforced invariants (signed audit chain, capability snapshot at construction, posture ladder, single-shot §7 phase monotonicity, etc.) at this version. Three items remain explicitly deferred to a future minor: cross-SDK byte-determinism conformance for vectors DV-3/DV-7/DV-9 (py-leads at v2.24.0; rs leadership pending). Three explicit non-promises: no implicit retries, no shadow audit chains, no posture auto-upgrade. See README § "Delegate composition primitive — Pre-Pledge v0" for the full disclosure.

### Notes

This release ships a brand-new public top-level module (`kailash.delegate`), warranting SemVer minor. No breaking changes to existing public surfaces. The 6 holistic-/redteam follow-up issues (#1143, #1146-#1150) are tracked separately and will close as their respective fixes land in v2.24.x patches.

## [2.23.0] - 2026-05-19

### Changed

- **Node-registry cross-module collision guard (#891)** — `NodeRegistry.register`
  now raises `NodeConfigurationError` when a node name is re-registered by a
  class from a different source file. Previously such collisions only emitted an
  INFO log and the last import silently won, so `add_node("<name>")` resolved
  import-order-dependently. Same-module re-registration (DataFlow model
  decoration regenerating CRUD node classes per `@db.model`) stays non-fatal
  per ADR-002.
- **`BulkUpsertNode` renamed to `SQLBulkUpsertNode` (#891)** — the core bulk
  upsert node registered the same global name as kailash-dataflow's
  `BulkUpsertNode`. Migration: `add_node("BulkUpsertNode", ...)` →
  `add_node("SQLBulkUpsertNode", ...)`.

## [2.22.1] - 2026-05-18

### Fixed

- **`import kailash` failed on clean-venv install of 2.22.0 (CRITICAL)** — an `EventPublishNode` circular import surfaced on every fresh `pip install kailash==2.22.0`; resolved by an isort-driven split of the import block in `src/kailash/__init__.py`. No API change. Catch-up patch for a fix that landed on `main` after the 2.22.0 release tag (`build-repo-release-discipline.md` Rule 2 — clean-venv installability is the done gate).

## [2.22.0] - 2026-05-18

### Added

- **`kailash.EventBus` domain-event primitive with pluggable backends (#1054)** — new public surface for in-process and broker-backed event publication. Exports: `EventBus`, `Subscription`, `DomainEvent`, `EventPublishNode`. Backends: `InMemoryEventBackend` (default, zero external dep) and `RedisStreamsEventBackend` (behind the existing `[redis]` optional extra). Backend selectable via constructor `backend=` arg or `KAILASH_EVENTBUS_BACKEND` env var (closed-list lookup, no arbitrary-import vector). `publish` + `subscribe` API supports `correlation_id` for trace propagation (auto-generated via `uuid.uuid4()` when omitted, round-trips to subscriber). `EventPublishNode` integrates publication into `WorkflowBuilder` steps. Type stub (`.pyi`) + `py.typed` marker shipped. Tier-2 round-trip suite at `tests/integration/events/test_eventbus_wiring.py` (16 passed + 1 documented xfail for live Redis). Fixes #1054.

### Fixed

- **`@app.handler()` decorator no longer emits the SDK's own instance-API advisory (#1071 Gap B)** — the decorator's internal `make_handler_workflow` registers via `WorkflowBuilder.add_node_instance`, which historically warned the consumer about instance-API misuse — once per registered handler, scaling to hundreds of spurious `UserWarning`s per process for correct decorator use. Added keyword-only `_internal: bool = False` flag to `_add_node_instance` and `add_node_instance`; `make_handler_workflow` passes `_internal=True`. Genuine consumer instance-API misuse never sets the flag and still warns. `_internal` is keyword-only (after `*`) so a positional `True` cannot accidentally suppress the warning. Fixes #1071 Gap B.

## [2.21.3] - 2026-05-18

### Fixed

- **`SQLiteAdapter` transaction state not reset on aborted `begin_transaction()` (#1070)** — `asyncio.CancelledError` is a `BaseException`, not an `Exception`; the auto-transaction wrappers caught `except Exception:`, so a coroutine cancelled between `begin_transaction()` and `commit_transaction()` skipped `rollback_transaction()`, leaving `_transaction_depth` unreset. The next `begin_transaction()` on the shared `:memory:` connection then took a poisoned SAVEPOINT branch (reproduced: an aborted transaction's uncommitted row leaked into the next transaction). Added `_abort_begin()` (resets depth/savepoint-counter + `ROLLBACK`, never closes the `:memory:` connection) and switched both auto-transaction wrappers to `except BaseException:`. Fixes #1070.

### Documentation

- Documented the constant-time-comparison expectation for caller-supplied `JWTConfig.api_key_validator` (docstring + `specs/security-auth.md` §2.2; no behavior change). Fixes #1068.

## [2.21.2] - 2026-05-18

### Fixed

- **aiosqlite `:memory:` connection leaked on `DataFlow`/`ProtectedDataFlow` `close()` (#1051)** — multi-sited fix: untracked per-query `:memory:` connection is now reused and closed; `ProductionSQLiteAdapter.disconnect` handles both branches; node `_owned_adapters` teardown; engine cached-node teardown resolved `cleanup()` vs the dead `hasattr(close)` guard. Fixes #1051.

## [2.21.1] - 2026-05-16

### Fixed

- **`verify_envelope` premature `DeprecationWarning` (trust)** — `verify_envelope`
  emitted a `DeprecationWarning` on the `alg_id=None` path, but that is the ONLY
  supported calling convention (a non-default `alg_id` raises `NotImplementedError`
  — the ISS-31 wire-format gate). Deprecating the only working path is incorrect;
  the warning had no migration target and referenced now-closed #604. It was also
  asymmetric with `sign_envelope` (quiet via `coerce_algorithm_id`). `verify_envelope`
  now mirrors `sign_envelope` — unconditional `coerce_algorithm_id(alg_id)`, quiet on
  the default, `NotImplementedError` on non-default, before any HMAC work. The HMAC
  verification path (`hmac.compare_digest`), fail-closed semantics, and the ISS-31
  gate are unchanged (verified by security-reviewer gate-review — no findings above
  LOW). Removed the now-dead `_LEGACY_HMAC_ENVELOPE_WARNED` global, the orphaned
  `import warnings as _warnings`, the unused `ALGORITHM_DEFAULT` import, and synced
  the `verify_envelope` docstring to the no-warning behavior. This warning was
  self-inflicted (the project's own `test_envelope_round_trip.py` triggered it) and
  failed `-W error`, blocking the Tier-1 pre-commit gate for every kailash-dataflow
  PR. The `alg_id` wire format remains tracked by ISS-31, unchanged.

## [2.21.0] - 2026-05-13

### Added — issue #953: LocalRuntime-owned AsyncSQL pool tracking

`LocalRuntime` now tracks AsyncSQL connection pools it instantiates, enabling
deterministic cleanup at runtime teardown. Pools created via `LocalRuntime`
register with the runtime instance; `runtime.cleanup()` (and `__aexit__` in
async contexts) drains the registered pools before returning. This closes the
class of leaks where AsyncSQL pools survived runtime teardown and held
connections open against the database.

`src/kailash/runtime/local.py` grew the pool-tracking machinery; `src/kailash/runtime/async_local.py` and `src/kailash/edge/resource/resource_pools.py` received
small adjustments to honor the new ownership contract.

### Fixed — issue #942 sibling: orphaned `wait_for` + `clear_shared_pools` coroutines

`AsyncLocalRuntime._execute_sync` and the shared-pools cleanup path no longer
leak `wait_for` coroutines on shutdown. Previously, an exception during
`wait_for` could leave the underlying coroutine pending, surfacing as
`RuntimeWarning: coroutine '...' was never awaited` in CI and in production
process-exit logs. Both paths now explicitly close orphaned coroutines on
cleanup.

### CI / DataFlow test repairs

Test-only / CI-only changes since 2.20.3 (no consumer-visible behavior change,
included in this release for completeness because they ship in the wheel's
sdist alongside the runtime fixes above):

- DataFlow unit test repairs: inspector workflow analysis + error handling
  tests aligned to current API, express_cache v2 key format, migration impact
  reporter tests repaired, SaaS API key ListNode response shape unwrapped,
  MongoDB connection tests gated on optional `motor` driver.
- CI: `[security]` extra installed for cryptography in test_signed_audit
  collection; DataFlow test step timeout raised to 15 min; pytest-timeout
  flag removed.

## [2.20.3] - 2026-05-11

### Changed — issue #959: trust-plane canonical bytes are now byte-stable

`DecisionRecord.content_hash`, `ReasoningTrace.content_hash`, and
`plane.models.ConstraintEnvelope.envelope_hash` now use
`kailash.trust.signing.crypto.serialize_for_signing()` to produce
canonical bytes for SHA-256 hashing. The prior `json.dumps(..., default=str)`
canon serialized datetimes, Decimals, and UUIDs via Python's `str()` form,
which is implementation-defined and not byte-stable across Python versions
or cross-SDK boundaries. The replacement is an
explicit-type whitelist: `datetime`/`date`/`time` → `.isoformat()`,
`Decimal` → `str()` with full precision preserved (e.g. `Decimal("1.50")`
serializes as `"1.50"` not `"1.5"`), `UUID` → 8-4-4-4-12 hex,
`Enum` → `.value`, `bytes` → base64. Unsupported types now raise
`TypeError` at signing time rather than silently coercing via `str()`.

`TrustProject.verify(strict=True)` now raises
`kailash.trust.plane.exceptions.ChainHashMismatchError` on the first
decision-record hash mismatch (typed `.details` carries `record_id`,
`stored_hash`, `computed_hash`, `record_type="decision"`). Default mode
(`strict=False`, backward-compatible) continues to populate
`integrity_issues` and set `chain_valid=False` in the returned report, AND
now emits a structured WARN log line (`trust_chain.hash_mismatch`) per the
log-triage gate. Both modes are exercised by the new Tier 2 regression
test at `tests/regression/test_issue_959_trust_canonical_bytes.py`.

### Migration — re-anchor existing audit chains on upgrade

Audit chains signed by kailash 2.20.2 or earlier MAY fail re-verification
after upgrading because the canonical-bytes serializer changed. This is
loud-and-actionable behavior:

- In default `verify()` mode, the returned report shows `chain_valid=False`
  with `integrity_issues` listing every mismatched record. Operators see
  the issue and decide whether to re-anchor (re-sign the chain with the
  new canon) or accept the audit-trail break.
- In `verify(strict=True)` mode, the first mismatch raises
  `ChainHashMismatchError` immediately with full record context in
  `.details`.

There is intentionally no `legacy_default_str_fallback` flag — perpetuating
the broken canon ships the problem forward and breaks cross-SDK byte
parity. Re-anchoring is the safe disposition for any chain that may
have been signed with the implementation-defined prior canon.

Records containing only native JSON primitives (str, int, float, bool,
None, list, dict) are unaffected. Records containing custom classes that
previously relied on `default=str` to coerce them now raise `TypeError`
at signing time — declare a `to_dict()` method or serializer on those
dataclasses.

### Added — cross-SDK fixture

A new cross-SDK byte-pin fixture lives at
`tests/test-vectors/trust-plane-canonical.json` per `cross-sdk-inspection.md`
Rule 4a so cross-SDK implementations both reproduce the same canonical bytes
and SHA-256 hex
for the eight pinned vectors (ASCII payload, UTC datetime, non-UTC
datetime, Decimal precision, UUID, Unicode BMP, above-BMP emoji,
empty-dict sentinel).

### Out of scope for this release — deferred no-verifier `default=str` sites

The audit at workspace-time identified five additional `default=str`
signing-shape sites under `src/kailash/trust/` that have NO active
re-verifier consuming the canonical bytes. They produce SHA-256 digests
that are stored or used as audit/dedup sentinels but are not subsequently
re-derived for chain-integrity verification. These sites are byte-stable
within a single Python version but are NOT guaranteed cross-SDK or
cross-version stable; cross-SDK forensic correlation will be added in a
follow-up issue:

- `src/kailash/trust/enforce/selective_disclosure.py:47` — `_hash_value`
  redaction sentinel.
- `src/kailash/trust/enforce/selective_disclosure.py:279` —
  `_compute_chain_hash` (compact canon already symmetric with verifier).
- `src/kailash/trust/enforce/selective_disclosure.py:341` —
  `export_for_witness` sign payload.
- `src/kailash/trust/enforce/selective_disclosure.py:385` — mirror of
  `:341` in `verify_signature`.
- `src/kailash/trust/enforce/decorators.py:305` — `_hash_result` for the
  `@verified` decorator's integrity hash (audit-log dedup only).

Touching these sites is non-load-bearing for #959's primary scope
(silent verification failure) — the change is cross-SDK parity hygiene
only. A cross-SDK follow-up issue will land per
`cross-sdk-inspection.md` Rule 1 with user gate per
`upstream-issue-hygiene.md`.

## [2.20.2] - 2026-05-11

### Fixed — issue #950: LocalRuntime cleanup-race coroutine leak

`LocalRuntime` cleanup path no longer leaks coroutines when the cleanup
runs concurrently with the workflow loop's tail. The race window was
that the synchronous cleanup spawned an asyncio.run on a coroutine the
running loop still owned references to — surfacing as `coroutine was
never awaited` warnings at GC under load. The fix gates the cleanup on
event-loop state and awaits the residual coroutines in-loop when the
loop is still alive. Residual sync-then-async pool-leak constraint is
documented at `src/kailash/runtime/local.py`.

### Fixed — issue #882: DurableExecutionEngine routing test — mock-kwarg drift

`_FakeRuntime.execute_workflow_async` in
`tests/regression/test_issue_882_durable_execution_mode.py` was missing
the `soft_time_limit` and `time_limit` keyword-only kwargs that
`DurableExecutionEngine.execute` now forwards (added by the #876 / #912
plumbing in `durable.py`). The mock now mirrors the canonical
`AsyncLocalRuntime.execute_workflow_async` signature and records both
kwargs in `execute_calls`. A new behavioral regression test asserts
the engine forwards the kwargs to the runtime — structural defense
against the silent-fallback failure mode in
`rules/zero-tolerance.md` Rule 3c (Documented Kwargs Accepted But
Unused).

### Fixed — issue #876 follow-on: actionable error on optional-extra imports

Every module-scope import of an optional-extra package (FastAPI /
Starlette / Uvicorn / aiohttp / aiohttp-cors / bcrypt / PyJWT) in
production source now raises an actionable `ImportError` naming the
correct `pip install 'kailash[<extra>]'` recipe — instead of a bare
`ModuleNotFoundError` that gave clean-install users no signal. 25
sites swept in total (3 in the first wave, 22 in the second sibling
sweep), with a structural invariant test
(`tests/regression/test_optional_extra_import_guards.py`) AST-walking
every Python module in `src/kailash/` to gate future regressions.

The `_KNOWN_VIOLATIONS` allowlist is now empty — going forward, any
new module-scope optional-extra import without a `try/except
ImportError` guard surfaces as a test failure, not silently absorbed.

### Test — issue #912: widen time-limit Tier-2 elapsed bound for cold-start

Tier-2 time-limit tests at `tests/integration/runtime/test_local_
runtime_time_limits.py` had a tight elapsed-time bound that
intermittently failed on cold-start CI runners (slow first-import
penalty pushing elapsed past the original threshold). Bound widened
with explicit rationale in the test comment; no behaviour change in
the runtime.

### Test — issues #948, #949: pre-existing test infrastructure fixes

- `#948`: drop orphan `_patch_worker_execute_skip_roundtrip` call in
  the distributed-runtime suite — the helper had been deleted in a
  prior refactor but one call site survived, blocking collection.
- `#949`: fix tuple-unpack on `execute_workflow_async` return value
  plus ListNode key in `tests/regression/`. The runtime started
  returning `(results, run_id)` two-tuple in 2.16.0; the regression
  test still used the pre-tuple return shape.

### Added — issue #876: hashing-symmetry across history_store.\* log emissions + metric counters

Every `history_store.*` log emission at WARN level or higher now hashes
record-level identifiers (`run_id`, `workflow_id`, `node_id`,
`sample_run_id`) via the 8-char SHA-256 prefix helper `_hash_short`,
and pairs the emission with a metric counter increment on the
`MetricsBridge` singleton (`kailash.runtime.metrics::get_metrics_bridge`).
Four sites covered: `record_event.dropped` (the
`MissingRunIdError`-observed WARN line),
`get_run_events.payload_decode_failed`, `per_tenant_cap.evicted`,
`retention.swept`. Closes the asymmetry where `run_id` /
`sample_run_id` shipped raw while siblings (`tenant_id_hash`,
`node_id_hash`) were already hashed. Log aggregators
(Datadog / Splunk / CloudWatch) typically carry broader read access than
the audit database; the hashing-symmetry contract closes that
information-leak gradient per `rules/observability.md` Rule 8.

### Added — issue #876: typed MissingRunIdError + tenant-scoped delete_runs_older_than

`kailash.sdk_exceptions::MissingRunIdError` is now raised by
`WorkflowHistoryStore.record_event` when the incoming event has no
`run_id`. The runtime subscriber-error handler
(`durable.NodeCompletionSubscribers.dispatch_async`) observes the typed
cause specifically — before the generic `Exception` fallback —
converts it into a WARN log line
(`history_store.record_event.dropped`, `mode="missing_run_id"`)
plus a metric counter (`record_history_store_dropped`), and preserves
the forward-progress invariant.

`WorkflowHistoryStore.delete_runs_older_than` accepts a new
keyword-only `tenant_id: Optional[str] = None` kwarg. When set, the
sweep is scoped to one tenant via `_tenant_partition(tenant_id)`. When
`None` (default), the cross-tenant default is preserved — no behaviour
change for existing callers.

The sweep is now statement-count-bounded: one transaction containing
exactly two batched `DELETE` statements (events first, runs second) for
both `delete_runs_older_than` AND `_enforce_per_tenant_cap`. Was
previously `1 SELECT + 2N DELETEs` per expired/excess run; the new
shape is constant in `N`.

### Changed — issue #876: audit-log payload type whitelist (replaces default=str)

`WorkflowHistoryStore.record_event` now serializes payloads via the
explicit-type whitelist `_audit_safe_default` (`history_store.py`).
`default=str` is gone.

Supported types: `dict`, `list`, native JSON scalars (`str` / `int` /
`float` / `bool` / `None`), `datetime` / `date` / `time` (ISO-8601),
`Decimal` (string via `str(obj)`; reader applies `Decimal(value)`),
`UUID` (canonical hyphenated form).

**Migration — behaviour change for downstream consumers:** nodes that
previously returned `set` / `frozenset` / `bytes` / `bytearray` /
`memoryview` / custom-class instances in their `outputs` or
`metadata` and silently round-tripped as Python's `str()` repr now
raise `TypeError` at audit-write time. Fix at the node boundary:

```python
# Before — silently round-tripped as repr
return {"items": my_set}

# After — explicit conversion at node boundary
return {"items": list(my_set)}
```

The `TypeError` propagates to the subscriber-error handler, which
logs `durable.on_node_complete.subscriber_failed` with the callback
name and error type. See `specs/core-runtime.md` §4.7.5 for the full
type contract table.

### Changed — issue #876: retention sweep throttle (30s default; sweep_interval_seconds=0.0 restores per-event behavior)

`WorkflowHistoryStore.__init__` accepts a new keyword-only
`sweep_interval_seconds: float = 30.0` kwarg. The retention sweep +
per-tenant-cap check (triggered by every `record_event` call) are now
throttled: consecutive invocations within the interval short-circuit
BEFORE any SQL round-trip. The retention sweep is throttled globally;
the per-tenant-cap check is throttled per-tenant (a busy tenant does
NOT starve another tenant's cap check).

`time.monotonic()` is used (NOT wall-clock) so system-clock changes
cannot skew the throttle.

**Migration — back-compat escape hatch:** users who require strict
retention semantics (every `record_event` sweeps immediately) MUST
pass `sweep_interval_seconds=0.0` at construction time:

```python
store = PostgresHistoryStore(
    conn,
    retention_days=30,
    sweep_interval_seconds=0.0,  # per-event sweep (pre-#876 behaviour)
)
```

Trade-off: events that expire BETWEEN sweeps remain in the DB up to
`sweep_interval_seconds` longer. The retention sweep is "best-effort"
per the docstring contract — 30s slack is within the spirit of that
contract.

## [2.20.1] - 2026-05-10

### Fixed — issue #941: retry/final lifecycle hooks on leaf-node failures

`Worker._execute_workflow_sync` now re-raises when `LocalRuntime`
silently records a leaf-node failure in its `results` dict. The
underlying runtime's `_should_stop_on_error` returns `False` when
the failed node has no downstream dependents (the typical 1-node
distributed task shape), so the runtime records `failed: True` and
returns NORMALLY — meaning the Worker's retry/final classification
at `_execute_task` never fired and `on_task_retry` /
`on_task_failure` handlers never ran.

The user-meaningful exception type now survives past SDK wrappers.
The new private `_unwrap_node_failure` helper walks `__cause__` then
`__context__`, with cycle detection, so `failure_event.exception`
carries the user's original error type (`ZeroDivisionError`,
`ValueError`, …) rather than the bookkeeping `NodeExecutionError`.

`LocalRuntime` now stores the actual exception object under a
private `_exception` key in the recorded failure payload so the
worker can introspect the chain. Older callers that JSON-serialize
the result dict are unaffected — the helper falls back to
reconstructing by name when `_exception` is absent.

Surfaced by /redteam Round 2 against PR #940 (the #929 round-trip
serialization fix). Pre-#940 the lifecycle-hooks Tier-2 contract
test failed at workflow construction (Class G); post-#940 the
leaf-failure gap (Class H) became visible.

PR #945 (merged at `48a41ed1`).

## [2.20.0] - 2026-05-10

### Added — issue #913: WorkflowScheduler runtime admin API

`kailash.runtime.scheduler_admin.SchedulerAdminAPI` is a thin admin
surface wrapping a started `WorkflowScheduler`. Operators can now
list / enable / disable / update-cron / delete schedules at runtime
without redeploying.

- `admin.list_schedules()` / `admin.get_schedule(schedule_id)` return
  JSON-friendly `ScheduleAdminView` dicts suitable for HTTP / CLI / RPC.
- `admin.disable_schedule(sid, actor=...)` pauses; `admin.enable_schedule`
  resumes; both idempotent.
- `admin.update_cron(sid, "0 7 * * *", actor=...)` swaps the cron and
  recomputes `next_run_time` atomically — APScheduler's running
  `AsyncIOScheduler` picks up the new schedule on its next tick.
- `admin.delete_schedule(sid, actor=...)` removes the schedule and
  raises typed `ScheduleNotFound` for unknown IDs (replacing the
  underlying `KeyError`).
- Every mutation requires a non-empty `actor` string and writes a
  structured INFO audit log entry on the
  `kailash.runtime.scheduler_admin` logger.
- Admin views surface `retry_spec` (#910 pass-through) and
  `time_limits` (#912 pass-through) so operators inspecting a schedule
  see its retry budget and per-fire deadlines without re-implementing
  the kwarg plumbing.
- `tenant_scope` parameter declares the admin's logical scope (defaults
  to `"default"`); the single-tenant assumption is explicit, and the
  multi-tenant extension hook lives in `_visible_ids` so future
  tenant-aware schedulers can filter without breaking the contract.

Authentication is the caller's responsibility — `SchedulerAdminAPI`
performs no identity check on the supplied `actor`. Wrap with the
`packages/kailash-nexus/` auth middleware when exposing over HTTP.

`specs/scheduling.md` §11 documents the admin surface in full.

### Fixed — issue #911 Shard 2 followup: multi-queue correctness

Redteam round 1 against the 2.19.0 multi-queue release surfaced same-bug-class
gaps in the Worker / DistributedRuntime surface. Multi-queue users now see
correct per-queue processing counts, per-queue observability for queue-status
snapshots, released Redis clients on shutdown, and validated queue names at
the scheduler-dispatcher boundary.

- **Per-queue processing isolation** — every named queue now owns its own
  Redis processing list (`kailash:tasks:processing:<name>`). Pre-fix every
  named queue shared `kailash:tasks:processing`, so per-queue stale-task
  recovery rolled up across queues and `Worker.get_status()["queues"]` reported
  identical aggregate processing counts for every queue. The default queue
  still resolves to the legacy bare key for byte-identical back-compat with
  single-queue deployments. (R1-001 / R1-002)
- **`DistributedRuntime.get_queue_status()` reports every queue** — the
  response now includes a `"queues"` map with per-queue pending / processing
  counts for every cached named queue. The top-level `pending` / `processing`
  fields keep reporting the default queue for back-compat with single-queue
  dashboards. Pre-fix multi-queue producers had zero observability into named
  queues. (R1-003)
- **`TaskQueue.close()` releases the lazily-created Redis client** —
  `DistributedRuntime.close()` now actually frees the Redis client every named
  queue lazily constructed. Pre-fix multi-queue runtimes leaked one client per
  named queue on shutdown. (R1-005)
- **`dispatcher.Task` validates `queue_name` at construction** — the
  scheduler-dispatcher path now uses the same canonical validator as the
  distributed-runtime path, closing the silent bypass a
  scheduler→dispatcher→distributed-runtime bridge could carry. (R1-006)

### Fixed — issue #929: workflow round-trip serialization

`Workflow.to_dict() → Workflow.from_dict()` previously stripped any
constructor parameter consumed as a named arg by a Node subclass
(`code` on `PythonCodeNode`, plus 43 other subclasses with the same
gap). The reconstructed workflow had the node but its parameters were
gone — silent data loss on cluster checkpoint/resume, distributed task
replay, and `WorkflowScheduler` snapshots.

- **Base-class fix at `Node.__init_subclass__`** — every Node subclass
  now installs an `__init__` wrapper that captures bound parameters into
  `self.config` after the subclass's own init runs, so `to_dict()`
  serializes the full set of constructor inputs.
- Audited 44 Node subclasses; all had the gap pre-fix; all are
  protected by the base-class wrapper post-fix. Future Node subclasses
  inherit the protection automatically.
- 7 new regression tests in
  `tests/integration/workflow/test_workflow_round_trip_serialization.py`
  exercise round-trip + reconstruction + execution against real Redis
  / DataFlow surfaces.
- 3 of 4 pre-existing lifecycle-hooks tests now pass; the 4th surfaces
  a separate retry-event classification gap tracked as #941.
- Removes the `_patch_worker_execute_skip_roundtrip` workaround from
  `tests/integration/runtime/test_worker_multi_queue.py` (the multi-queue
  Tier-2 tests now exercise real round-trip).

## [2.19.0] - 2026-05-10

### Added — issue #911 Shard 1: multi-queue routing producer surface

`DistributedRuntime.execute(queue=...)` now accepts an optional logical
queue name and routes the task to the corresponding Redis list. The
canonical queue-name → Redis-list-key mapping lives in a new shared
helper module (`src/kailash/runtime/_queue_keys.py`) so the producer
and (Shard 2) consumer cannot drift out of byte-shape agreement.

- `DistributedRuntime(default_queue="...")` sets the runtime's default
  queue (defaults to `"default"`).
- `runtime.execute(workflow, queue="fast")` enqueues to
  `kailash:tasks:pending:fast`.
- `runtime.execute(workflow)` enqueues to the legacy single-queue key
  `kailash:tasks:pending` — byte-identical to pre-#911 deployments.
- `TaskMessage.queue_name` round-trips through JSON; older-SDK messages
  without the field deserialize as `"default"`. The default-queue wire
  format omits `queue_name` so a worker on a pre-#911 SDK reads the
  message unchanged.
- `validate_queue_name` rejects empty / > 64-char / colon / slash /
  whitespace / control-char / null-byte / non-str inputs at the entry
  point, not deep in the dispatch path.

Worker-side multi-queue dequeue is Shard 2 (below).

### Added — issue #911 Shard 2: Worker multi-queue dequeue

`Worker(queues={"fast": 8, "slow": 2})` now declares a multi-queue
worker that dequeues from each named queue with its own concurrency
cap. Per the issue's acceptance criterion 3, a slow-queue task running
does NOT block fast-queue pickup — each queue gets its own asyncio
dequeue loop and per-queue semaphore.

- Bare-int form: `queues={"fast": 8}` sets concurrency=8 with
  default visibility_timeout=300.
- Dict form: `queues={"slow": {"concurrency": 2, "visibility_timeout": 1800}}`
  overrides per-queue visibility_timeout for legitimate long-running
  workloads.
- `queue=` and `queues=` are mutually exclusive at construction
  (raises `ValueError`).
- Heartbeat JSON now includes `"queues": {"fast": 8, "slow": 2}` so
  operators see exactly which queues each worker consumes.
- `get_status()` reports per-queue pending/processing counts under
  `queues` while preserving the legacy `queue_pending` / `queue_processing`
  fields for the primary queue.
- `TaskEvent.queue_name` is populated on every lifecycle hook
  (`on_task_prerun` / `_postrun` / `_success` / `_retry` / `_failure`)
  so per-queue alerting (e.g. `slow_queue_failure_rate` dashboards)
  can route on the queue.
- Stale-task recovery sweeps every queue this worker consumes from,
  not just the primary.

Legacy `Worker(concurrency=N)` and `Worker(queue=tq)` paths remain
externally indistinguishable from `Worker(queues={"default": N})` —
same Redis list key, same heartbeat shape minus the `queues` field.

## [2.18.1] - 2026-05-10

### Fixed — issue #917 LocalRuntime cleanup-path coroutine leak

`LocalRuntime._cleanup_event_loop` (also reached via `__exit__` and
`close()`) constructed `AsyncSQLDatabaseNode.clear_shared_pools(graceful=True)`
inline as the first argument to `asyncio.wait_for(...)`. Under any path
where `wait_for` raises before its body awaits the inner coroutine
(timeout, cancel-before-start race during shutdown), the coroutine was
GC'd un-awaited and Python emitted::

    RuntimeWarning: coroutine 'AsyncSQLDatabaseNode.clear_shared_pools'
    was never awaited

Fixed by capturing the coroutine in a local variable and adding a
`finally` block that explicitly closes it — a no-op when `wait_for`
ran the coroutine to completion or cancellation, but a structural
guarantee that cancel-before-start cannot leak.

Tier-2 regression at
`tests/integration/runtime/test_local_runtime_exit_cleanup.py` runs
under `python -W error::RuntimeWarning` and includes a deterministic
repro of the cancel-before-start race that pre-fix flips a
`RuntimeWarning` into a typed test failure.

### Hardened — issue #912 corrective gate (Shard 6)

The /redteam Round 1 audit on the merged #912 wave (PRs #921-#925) caught
two ship-blocking failure modes that this corrective shard fixes:

#### Fixed — In-process runtime enforcement was missing

Five in-process runtimes — `LocalRuntime`, `AsyncLocalRuntime`,
`ParallelRuntime`, `ParallelCyclicRuntime`, `DockerRuntime` — accepted
`soft_time_limit` / `time_limit` kwargs in their public signatures,
called `_validate_limits()`, and then dropped the kwargs on the floor
without ever arming `arm_time_limits`. The README quickstart::

    runtime = LocalRuntime()
    runtime.execute(workflow.build(), soft_time_limit=2)

silently never raised `SoftTimeLimitExceeded` against a 5-second
workflow. Same fake-dispatch failure mode as `zero-tolerance.md`
Rule 2 § "Fake dispatch": the docstring promised the contract; the
code did not deliver.

Wired in this shard:

- `LocalRuntime.execute` — `arm_time_limits` (sync threading.Timer)
  layered on a fresh `CancellationToken`, classifier on
  `WorkflowCancelledError`, post-completion poll for hard-deadline-
  fired-after-success.
- `AsyncLocalRuntime.execute_workflow_async` — `arm_time_limits_async`
  (asyncio task) with the same pattern. Typed `SoftTimeLimitExceeded`
  / `HardTimeLimitExceeded` exceptions added above the broad
  `except Exception` re-wrap so they propagate untouched.
- `ParallelRuntime.execute` — `arm_time_limits_async` around the
  parallel-DAG path; typed exception passthrough.
- `ParallelCyclicRuntime.execute` — `arm_time_limits` around all three
  execution paths (cyclic / parallel-DAG / LocalRuntime fallback);
  typed kwargs forwarded to `LocalRuntime` for defense-in-depth.
- `DockerRuntime.execute` — `arm_time_limits` around the per-node
  container loop. Per-node-boundary poll: between containers, check
  if the hard timer fired during the previous container and raise.
  Documented constraint: long-running single-node Docker workflows
  cannot be interrupted mid-container (the timer cannot inject into
  a running `docker run` subprocess); multi-node workflows DO get
  the full deadline contract at every node boundary.
- `AccessControlledRuntime.execute` and `DurableExecutionEngine.execute`
  required NO changes — both already forward typed kwargs by name
  to their inner runtime's execute call, so the in-process wiring
  above fires automatically through them.

#### Fixed — Input-validation bypass at the Worker dequeue boundary

Three security findings were paired with the in-process gap:

1. **NaN / Inf bypass `_validate_limits`** — `float('inf') > 0` is
   True; `float('nan') <= 0` is False. Both slipped through the
   original sign-check and would arm `Timer(inf, ...)` (sleeps
   forever, workflow uncancellable) or `Timer(nan, ...)` (raises
   from a daemon thread with no traceback to the caller).
   `_validate_limits` now rejects non-finite values via
   `math.isfinite()` at every entry point.
2. **Worker accepts arbitrary `execution_limits` dict shape** — a
   malicious or mis-coded producer could send arbitrary shapes on
   the wire (`{"soft": "DROP TABLE"}`, `{"soft": [1, 2, 3]}`,
   `{"hard": -1}`). Without dequeue-side validation, the bad value
   flowed to `arm_time_limits` and surfaced as TypeError /
   ValueError from a daemon thread. Added
   `Worker._validate_execution_limits_dict` static helper, called
   from `Worker._effective_time_limits` at dequeue. Validates dict-
   or-None, key types (rejects bool because Python's bool subclasses
   int), then delegates to `_validate_limits` for finite + sign +
   ordering. Unknown keys silently ignored for forward-compat.
3. **`grace_seconds` was unvalidated** — negative grace fires the
   hard kill BEFORE the soft signal (inverting the celery
   contract); NaN crashes the daemon thread. `_validate_limits`
   now accepts an optional `grace_seconds` parameter and validates
   it; `arm_time_limits` / `arm_time_limits_async` /
   `Worker.__init__` all forward the value so caller error raises
   at the entry point.

#### Tests

- `tests/unit/test_time_limits_validation.py` — 12 new finite-check
  - grace_seconds cases.
- `tests/integration/runtime/test_local_runtime_time_limits.py` (new)
  — 8 Tier-2 cases covering soft/hard enforcement on real
  `LocalRuntime` plus all entry-point validation paths.
- `tests/integration/runtime/test_async_local_runtime_time_limits.py`
  (new) — 7 Tier-2 cases mirroring the LocalRuntime suite for the
  async path.
- `tests/integration/runtime/test_distributed_time_limits.py` — 11
  new Worker dequeue-validation cases (no Redis required for the
  validation surface).

Full #912 regression suite: 149 passed; Tier-1 sweep matching CI:
3915 passed, 4 skipped, 0 failures.

### Added — Per-Task Soft / Hard Time Limits (#912)

`runtime.execute(workflow.build(), soft_time_limit=2.0, time_limit=5.0)`
now bounds every workflow with a celery-style two-stage deadline contract:
the soft limit raises a catchable exception so user code can save partial
work and exit cleanly; the hard limit unconditionally aborts after a
short grace window so operators can bound runaway resource consumption.

#### New typed kwargs (additive — `**kwargs` retained one deprecation cycle)

- **Every `BaseRuntime` subclass** — `LocalRuntime.execute`,
  `AsyncLocalRuntime.execute` / `.execute_workflow_async`,
  `DistributedRuntime.execute`, `DockerRuntime.execute`,
  `ParallelRuntime.execute`, `ParallelCyclicRuntime.execute`,
  `AccessControlledRuntime.execute`, `DurableExecutionEngine.execute` —
  accept `soft_time_limit: float | None = None` and
  `time_limit: float | None = None` as KEYWORD_ONLY parameters. Validated
  at the entry point: negative values, non-finite values, and `soft >= hard`
  raise `ValueError` immediately rather than later from a timer thread.
- **`WorkflowScheduler.__init__`** — operator-level
  `default_soft_time_limit: Optional[float] = None` and
  `default_time_limit: Optional[float] = None` apply when a per-fire value
  is unset. Per-fire value ALWAYS wins.
- **`WorkflowScheduler.schedule_cron` / `.schedule_interval` / `.schedule_once`** —
  per-fire `soft_time_limit` / `time_limit` KEYWORD_ONLY kwargs flow
  through `RetrySpec` integration so retryable typed exceptions
  re-classify correctly.
- **`Worker.__init__`** — operator-level
  `default_soft_time_limit: float | None = None`,
  `default_time_limit: float | None = None`, and
  `hard_time_limit_grace_seconds: float = 1.0` apply when a task's
  `TaskMessage.execution_limits` does NOT specify the corresponding
  limit. Per-task value ALWAYS wins. The `Worker` arms timers at
  DEQUEUE (not enqueue) so queue wait time does NOT consume the task's
  budget.

#### New typed exceptions

- `kailash.sdk_exceptions.SoftTimeLimitExceeded` — subclass of
  `RuntimeException`. Catch to save partial work / write a checkpoint /
  exit cleanly before the hard deadline fires.
- `kailash.sdk_exceptions.HardTimeLimitExceeded` — subclass of
  `RuntimeException`. Operator-facing path for runaway-task abort.
  On the distributed worker path, triggers requeue (NOT immediate
  dead-letter) when `attempts < max_attempts`; dead-letters only after
  the attempt budget is exhausted.

Both are exported from `kailash.sdk_exceptions` and importable as:

```python
from kailash.sdk_exceptions import SoftTimeLimitExceeded, HardTimeLimitExceeded
```

#### Distributed wire format — forward-compat

`TaskMessage` (in `kailash.runtime.distributed`) gained an optional
`execution_limits: Optional[Dict[str, float]] = None` field with shape
`{"soft": <float>, "hard": <float>}` (either key may be omitted when the
corresponding limit is None). Wire format is ONE optional field — workers
running pre-2.19 SDK silently ignore the unknown payload key (forward
compatible). Workers running 2.19 or newer read the field and arm timers
at dequeue.

#### `RetrySpec` integration

`SoftTimeLimitExceeded` and `HardTimeLimitExceeded` flow through the
`RetrySpec` retry classifier so a scheduled job that exceeds its soft
limit can be retried with backoff per the spec, while a hard-limit kill
goes to dead-letter (or requeue, on the distributed worker path).

#### Migration

Pure-additive scope — no breaking changes. Existing callers continue to
work without passing the new kwargs. The wrapper layer is OFF by default
(both kwargs default to None) so no implicit deadlines apply unless the
caller explicitly opts in. The semantics are celery-style: soft limit
warns and raises a catchable exception; hard limit is an unconditional
abort after a short grace window.

```python
# Quickstart — opt-in per call:
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import SoftTimeLimitExceeded

runtime = LocalRuntime()
try:
    results, run_id = runtime.execute(
        workflow.build(),
        soft_time_limit=2.0,   # advisory; raises catchable exception
        time_limit=5.0,         # hard kill (after grace)
    )
except SoftTimeLimitExceeded:
    # Save partial work, write a checkpoint, return early.
    ...
```

## [2.18.0] - 2026-05-08

### Changed — BREAKING (slim core, #890)

`pip install kailash` now ships a slim default of **13 packages** (down from
~89). The full pre-#890 install experience is preserved via
`pip install kailash[all]` (back-compat umbrella).

#### Migration table — extras renamed

| Old extra       | New extra                                        |
| --------------- | ------------------------------------------------ |
| `[postgres]`    | `[db-postgres]`                                  |
| `[mysql]`       | `[db-mysql]`                                     |
| `[database]`    | `[db-postgres,db-mysql,db-sqlite]`               |
| `[http]`        | `[http-client]`                                  |
| `[mfa]`         | `[auth]` (folded — bcrypt/pyotp/qrcode together) |
| `[otel]`        | `[telemetry]`                                    |
| `[distributed]` | `[redis]`                                        |
| `[cli]`         | (removed — `click` is now core)                  |
| `[files]`       | (folded into `[server]`)                         |

#### New extras

`[server]` (fastapi+uvicorn+aiohttp+bcrypt+PyJWT+sqlalchemy+cryptography for
the full WorkflowServer stack), `[trust]` (cryptography+PyJWT+pynacl+filelock
for the EATP signing layer), `[auth-azure]` (msal for SharePoint Graph),
`[scheduler]` (apscheduler), `[mcp]` (mcp[cli]), `[data]` (numpy+pandas).

#### Loud-failure behavior

Lazy-loaded server surfaces (`from kailash import WorkflowServer`,
`create_gateway`, `EnterpriseWorkflowServer`) raise `ImportError` with the
specific install hint when the `[server]` extra is missing. Trust
(`kailash.trust.auth.jwt`) raises with `pip install 'kailash[trust]'`.
SharePoint nodes raise on construction with
`pip install 'kailash[http-client,auth-azure]'`.

#### Sub-package cleanup

13 hard orphans deleted across sub-package manifests (zero source imports
anywhere):

- `kailash-dataflow`: `alembic`, `dnspython`, `passlib[bcrypt]`, `flask`,
  `flask-jwt-extended`, `uvicorn[standard]`. Core 22 → 5 deps. Per-DB
  drivers behind `[postgres-sync]`/`[mysql]`/`[sqlite]`/`[mongo]`/`[redis]`;
  `cryptography` → `[security]`; `PyJWT[crypto]` + `pydantic` →
  `[templates]` (SaaS / API gateway scaffolds).
- `kailash-kaizen`: `bcrypt`, `packaging`. Core 29 → 9 deps. Provider
  SDKs behind `[providers-azure]`/`[providers-google]`/`[providers-tokens]`;
  prometheus+opentelemetry+structlog → `[observability]`; aiosqlite+asyncpg
  → `[db]`; numpy+Pillow → `[rag]`; GitPython → `[research-validator]`.
- `kailash-mcp`: `pydantic` (mcp[cli] declares it transitively).
- `kailash-pact`: `psycopg[binary]`, `psycopg_pool`. Core 7 → 2 deps.
  `fastapi`+`slowapi` → `[api]`; `kailash-kaizen` → `[execution]`.
- `kaizen-agents`: `kailash-pact` (semantics reach via `kailash.trust.pact.*`
  in core), `python-dotenv`, `structlog`. Core 7 → 4 deps.

`kailash-nexus` declares the server middleware stack directly so
`pip install kailash-nexus` continues to work against PyPI's pre-#890
`kailash` releases without relying on the new `[server]` extra.

#### Migration cheatsheet

```bash
# Before #890
pip install kailash

# After #890 — equivalent (back-compat)
pip install kailash[all]

# After #890 — slim (recommended; install only what you use)
pip install kailash[server]                   # Web API / gateway
pip install kailash[server,db-postgres,redis] # Web app on Postgres + Redis
pip install kailash[trust]                    # EATP / signing
pip install kailash[mcp]                      # MCP-only consumers
```

Closes #890.

## [2.17.0] - 2026-05-08

### Added

- **`DurableExecutionEngine.workflow_blob` JSON serialization contract (#881)** — `DurableExecutionEngine._enqueue_for_run` previously enqueued `Task(workflow_blob=b"", ...)` because the engine had no built-in serializer for arbitrary workflow objects, leaving cross-process workers (subscribers to the underlying `SQLTaskQueue` running on a separate host) unable to reconstruct the workflow without out-of-band registry access. The engine now routes through the new `kailash.runtime._workflow_blob.serialize_workflow_to_blob` helper — the same helper `WorkflowScheduler` uses — so both producer surfaces emit byte-identical JSON-encoded UTF-8 bytes for the same workflow. Workers reconstruct via `Workflow.from_dict(json.loads(blob.decode("utf-8")))`. Producer-boundary `MAX_WORKFLOW_BLOB_BYTES` cap (default 8 MiB) prevents oversized payloads from reaching the queue and OOMing dequeueing workers. The contract is additive for plain dispatch: workers using the prior local-registry convention keep working (they ignore `workflow_blob`); workers needing reconstruction-from-blob now have a documented JSON shape to parse. As a side benefit, the W6 redaction consumer (`SQLTaskQueueDispatcher(classification_policy=…)`) now actually sees per-node config dicts to redact — pre-fix the `b""` payload made `json.loads("")` raise inside `_redact_workflow_blob` (caught non-fatally, but redaction never ran for engine-dispatched tasks). 6 Tier-1 unit tests in `tests/unit/runtime/test_workflow_blob_helper.py` (round-trip, discriminator dispatch, size cap, determinism); 3 regression tests in `tests/regression/test_issue_881_workflow_blob_serializer.py` (blob-populated invariant, byte-parity with the canonical helper, worker-visible topology). Closes #881.

## [2.16.1] - 2026-05-08

### Fixed

- **`DurableExecutionEngine.execute()` enqueue/in-process race documented + caller-controlled (#882)** — the pre-fix engine always enqueued a fire-time `Task` BEFORE running the workflow in-process when both a dispatcher and a runtime were configured. The class docstring claimed "task_id idempotency prevents double-execution by the worker" — but `task_id` PRIMARY KEY idempotency only prevents duplicate ENQUEUE; it does not prevent two different actors (the in-process engine and a worker polling the queue) from each running the same enqueued task once. Between enqueue and the in-process path emitting its first checkpoint, a worker that picks up the task can start executing nodes that the in-process path will then re-execute. The in-tree `SQLTaskQueueDispatcher` worker + W1 checkpoint resume contain the blast radius (the second runner short-circuits via the checkpoint store), but the docstring misframed which defense was load-bearing and there was no caller-explicit way to opt out of the race. New `DurableExecutionEngineBuilder.execution_mode("in_process_only" | "dispatch_only" | "both")` setter is the explicit caller-intent surface. Default behaviour is preserved: omitting `.execution_mode(...)` auto-detects `"both"` when a dispatcher is configured and `"in_process_only"` otherwise, so every pre-2.16.1 call site continues to work without modification. New public read-only property `engine.execution_mode` surfaces the resolved mode. Explicit `"both"` and `"dispatch_only"` raise `ValueError` at `.build()` time when no dispatcher is configured (was previously a runtime surprise at the first `execute()` call). Class + `execute()` docstrings rewritten to correctly describe the layered defense (`task_id` PK idempotency = duplicate-enqueue prevention; W1 checkpoint resume = duplicate-execution short-circuit; race window between the two). 12 Tier-1 regression tests in `tests/regression/test_issue_882_durable_execution_mode.py`. Closes #882.

## [2.16.0] - 2026-05-07

### Fixed

- **Checkpoint write-path redaction (W6)** — the `runtime.on_node_complete` hook contract shipped in v2.15.0 ("no subscriber ever observes a classified PK or a redacted field's raw value") was broken at the checkpoint write-path: the runtime dispatched a redacted event to hooks but persisted the RAW `execution_tracker.to_dict()` to the checkpoint store. Anyone using `LocalRuntime(checkpoint_store=…, checkpoint_after_each_node=True)` with a classification policy was silently writing raw classified field values to the `kailash_checkpoints.data` column. New helper `kailash.runtime.durable.redacted_tracker_state_for_checkpoint` is now invoked from both `LocalRuntime` (`local.py:2731-2785`) and `AsyncLocalRuntime` (`async_local.py:640-682`) before `encode_checkpoint_payload`, so the persisted blob carries `[REDACTED]` / `pk:<digest>` sentinels for every classified field. Same `redact_event_for_persistence` helper as the hook surface — divergence between sync and async paths is structurally impossible. **W6 round-2 (security-reviewer Findings 1+2+3)**: `redact_event_for_persistence` now walks nested `Mapping` and `Sequence` values recursively, joining the field path with `.` separators (e.g. `customer.ssn`, `items.0.password`) so a classified leaf inside a nested dict or list is redacted independently of its wrapper. Pre-fix the helper iterated only top-level keys, so node outputs like `{"customer": {"ssn": "..."}}` could not have `customer.ssn` tagged independently of `customer` — silent leak class. `_redact_workflow_blob` automatically inherits the recursive walk because it consumes the same primitive. `_extract_context_from_schedule_id` parses the W4 `engine.{tenant_id}.{fingerprint[:12]}.{idempotency_key}` schedule_id format and propagates `tenant_id` + `idempotency_key` into the dispatcher's synthetic events, so per-tenant classification policies see the right scope. Non-engine schedule_ids fall through to `(None, None)` per back-compat. Wrapper-level tagging behavior is preserved — tagging the outer field still replaces the entire subtree, locked by `test_redact_event_persistence_nested_dict_wrapper_redacted`.
- **Breaking (Postgres-only) — `kailash_task_queue.created_at` / `updated_at` change from `REAL` to `DOUBLE PRECISION` (W6).** The `SQLTaskQueue` schema previously declared timestamp columns as `REAL`. PostgreSQL's `REAL` is 4-byte single-precision and silently truncates `time.time()` Unix epoch values by ~50 seconds; `requeue_stale`'s `now - updated_at` comparison therefore went negative on every fresh row, breaking the visibility-timeout contract entirely on Postgres. The schema now routes through `dialect.double_precision_type()` which emits `DOUBLE PRECISION` on PostgreSQL, `DOUBLE` on MySQL, and `REAL` on SQLite (SQLite's `REAL` IS 8-byte and was unaffected). **Migration for Postgres deployments on kailash 2.15.0:** before upgrading, run `ALTER TABLE kailash_task_queue ALTER COLUMN created_at TYPE DOUBLE PRECISION USING created_at::DOUBLE PRECISION; ALTER TABLE kailash_task_queue ALTER COLUMN updated_at TYPE DOUBLE PRECISION USING updated_at::DOUBLE PRECISION;` against the queue table. Without the migration, `requeue_stale` continues to silently return zero rows. SQLite and MySQL deployments need no migration.

### Added

- **`kailash.runtime.durable.DurableExecutionEngine` (W4)** — first-party durable execution engine that composes the runtime-integration-trio primitives (W1 per-node checkpointing, W2 persistent workflow history, W3 task dispatch) into a single facade. Construct via the fluent `DurableExecutionEngine.builder().checkpoint_store(...).history_store(...).dispatch_via(...).idempotency_key_default(...).build()` chain; each primitive is opt-in. The composition contract encodes correct wiring once: `history_store` flows via the runtime constructor (which auto-subscribes `record_event`), `checkpoint_store` requires `checkpoint_after_each_node=True` (set by default when the store is configured), and `dispatcher.enqueue` runs BEFORE in-process execution so the queue row is the durable record of intent. `engine.history` exposes the underlying `WorkflowHistoryStore` directly for native `list_runs` / `get_run` / `get_run_events` queries (tenant_id mandatory). Deterministic `schedule_id` is derived from `(tenant_id, compute_workflow_fingerprint(workflow)[:12], idempotency_key)` — same-tenant repeats collapse to one queue row via the dispatcher's idempotency gate, while cross-tenant idempotency-key reuse (e.g. per-user `"user-42-prewarm"`) yields distinct `schedule_id`s so one tenant's task cannot silently drop another tenant's enqueue. Mirrors the tenant partitioning of `build_checkpoint_key` per `rules/tenant-isolation.md` MUST Rule 5. ~510 LOC, 25 Tier-1 unit tests + 7 Tier-2 wiring tests against real Postgres. See `specs/core-runtime.md` §4.6.9 for the full surface.
- **`SQLTaskQueueDispatcher(classification_policy=…)` (W6)** — opt-in keyword-only constructor kwarg on `kailash.infrastructure.task_queue.SQLTaskQueueDispatcher`. When set, every `enqueue` routes `task.kwargs` AND the parsed `task.workflow_blob`'s per-node config dicts through the same `redact_event_for_persistence` helper used by the runtime's checkpoint write-path. Default `None` preserves back-compat — existing callers see the same payload they had before this kwarg was introduced. Closes the dispatcher payload leak gap surfaced by the W5 tier-3 redaction sweep.

## [2.15.0] - 2026-05-07

Minor release shipping Wave 2 of the runtime-integration-trio: first-party persistent workflow history. Subscribes to v2.14.x's `runtime.on_node_complete` hook and persists per-node `NodeCompletionEvent` records to a queryable, tenant-isolated audit log. Closes #861.

### Added

- **`kailash.infrastructure.history_store` (PR #875)** — new public module exporting `WorkflowHistoryStore` (ABC) + `PostgresHistoryStore` + `SQLiteHistoryStore` + `DowngradeRefusedError`. Dialect-portable schema (`workflow_runs` + `workflow_run_events`), write-time redaction via `redact_event_for_persistence`, 30-day retention TTL on `terminal_at` (NOT `started_at`), per-tenant cap (default 10,000) with WARN log on oldest-row eviction, and `delete_runs_older_than(*, force_downgrade=True)` destructive-confirmation gate per `rules/schema-migration.md` Rule 7. ~895 LOC, 29 Tier-1 unit tests + 6 Tier-2 wiring tests (real Postgres) + 1 Tier-3 redaction E2E.
- **`LocalRuntime(history_store=...)` auto-subscribe (PR #875)** — `LocalRuntime.__init__` accepts a non-None `history_store=` and registers `history_store.record_event` against the W1 hook registry at construction time. `AsyncLocalRuntime` inherits the wiring via `super().__init__(**kwargs)`. A history store lacking a callable `record_event` raises a typed `TypeError` at construction (per `rules/zero-tolerance.md` Rule 3a).

### Security

- **Tenant isolation, defense-in-depth (PR #875)** — `get_run_events` events fetch JOINs `workflow_runs` with `WHERE r.tenant_id = ?` predicate at the data-fetch level (not just an existence pre-check). Cross-tenant reads are BLOCKED at the store layer.
- **Concurrent record_event serialisation (PR #875)** — per-run `asyncio.Lock` LRU cache (mirroring W1's `_checkpoint_locks` pattern at `kailash/runtime/local.py:843-909`) serialises concurrent writers per `run_id`. Closes the `MAX(event_seq) + 1` race under READ COMMITTED isolation that would otherwise collide with the `UNIQUE(run_id, event_seq)` constraint under future parallel-branch dispatch surfaces or shared-store deployments. Bound `_MAX_RUN_LOCKS = 10_000` per `rules/infrastructure-sql.md` Rule 7.

### Notes

- Six lower-severity audit findings (M-2 sample_run_id hashing, M-3 None run_id disposition, L-1 cross-tenant retention scope, L-2 batch DELETEs, L-3 sweep throttling, L-4 json.dumps coercion) are tracked in #876 — none are blockers per security-reviewer agreement.
- All 7 framework packages (kailash-dataflow, kailash-kaizen, kailash-nexus, kailash-mcp, kailash-pact, kailash-ml, kailash-align) bump their `kailash>=` dependency-pin floor from `2.14.0` to `2.15.0` even though their own source is unchanged this cycle, per the SDK-dependency-pin-update rule in `deploy/deployment-config.md`. No sibling drift — all 7 framework packages were AT-PARITY with PyPI at release-time enumeration.

## [2.14.1] - 2026-05-07

Patch release shipping the #871 SQLite job-store security hardening that landed on `main` (commit `597d4736`, PR #873) after v2.14.0 was cut earlier the same day. No other changes since v2.14.0.

### Security

- **HIGH:** SQLite job-store TOCTOU + WAL/SHM 0o600 hardening (#871, PR #873). The prior open-then-chmod sequence in `WorkflowScheduler` left a window where the job-store DB existed on disk with default 0o644 perms before chmod tightened it to 0o600 — observable to other local processes during scheduler init. The fix introduces `_secure_init_sqlite_jobstore()` (`src/kailash/runtime/scheduler.py`) which creates the file with `os.O_CREAT | os.O_WRONLY` + explicit `mode=0o600` via `os.open` BEFORE handing the path to APScheduler's `SQLAlchemyJobStore`, and applies the same 0o600 mode to the WAL/SHM sidecars on first commit. Six regression tests at `tests/regression/test_issue_871_sqlite_jobstore_security.py` cover all four #871 acceptance criteria. Closes #871.

## [2.14.0] - 2026-05-07

Minor bump shipping two new public APIs on the runtime + scheduler surface — durable execution checkpoints and pluggable scheduler dispatch — plus a series of W1/W3 hardening fixes from the parallel implementation work.

### Added

- **`LocalRuntime` / `AsyncLocalRuntime` checkpoint hook (#860, PR #869)** — both runtimes now expose `runtime.on_node_complete` (callable) and route every node completion through the durable-execution wiring at `src/kailash/runtime/durable.py`. Workflows can opt into per-node checkpoint persistence by configuring an `ExecutionTracker`; sync workflows route through the same hook path as async, so checkpoint behavior is identical across both runtimes. 33 new Tier-2 integration tests cover the wiring end-to-end.
- **`WorkflowScheduler` dispatch_via= parameter (#859, PR #870)** — `WorkflowScheduler` accepts an optional `dispatch_via=Dispatcher` parameter to route scheduled workflow firings through a pluggable dispatcher. Ships `Dispatcher` ABC + `Task` frozen dataclass + `compute_task_id` helper at `src/kailash/runtime/dispatcher.py`, and a built-in `SQLTaskQueueDispatcher` adapter that bridges to `src/kailash/infrastructure/task_queue.py` for distributed dispatch. APScheduler integration uses `scheduled_run_times[-1]` (real event API) + `EVENT_JOB_SUBMITTED` listener for accurate `planned_fire_time`. 47 new Tier-2 integration tests (32 baseline + 15 security-hardening regressions).

### Fixed

- **W1 — `_checkpoint_locks` bounded LRU (PR #869)** — replaced unbounded dict with `OrderedDict` LRU eviction so long-lived runtimes do not leak lock objects per workflow_id.
- **W1 — narrowed `resolve_tenant_id` exception handling (PR #869)** — now catches only `ImportError` and `AttributeError` (the legitimate optional-dependency failure modes) and emits a WARN-once on first miss, instead of swallowing all exceptions.
- **W1 — `_hash_pk` handles unhashable `__str__` (PR #869)** — sentinel-based fallback for objects whose `__str__` raises, avoiding crashes on poisoned primary keys.
- **W1 — fail-CLOSED in `redact_event_for_persistence` on policy lookup errors (PR #869)** — security-relevant path now refuses to persist when the classification policy cannot be resolved, rather than persisting unredacted.
- **W3 — security hardening (PR #870, commits `66e76106`, `ff63504d`)** — JSON workflow_blob serialization, bounded `_fire_times` queue, frozen dataclasses on Task, multi-tenant queue isolation documented, payload size bounds, dispatcher discriminator validation.

### Tests

- 33 Tier-2 integration tests for durable execution wiring (sync + async runtimes).
- 47 Tier-2 integration tests for scheduler dispatch (32 baseline + 15 Round 2 security regressions).

## [2.13.5] - 2026-05-06

### Security

- **HIGH:** `MultiFactorAuthNode` verify-failure path now returns `success=False` in lockstep with `verified=False` (previously returned `success=True`, allowing callers gating on `success` alone to grant access on invalid TOTP codes). Fixed in both sync and async dispatch paths. (#803, #848)
- **HIGH:** Re-enabled commented-out rate-limit dispatch on `action="verify"` — brute-force protection on TOTP/SMS/email/backup-code verify is now functional. (#803, #848)

### Fixed

- `MultiFactorAuthNode` responses now echo `user_id` on verify, status, and disable. (#803)
- `status` action returns both `enrolled_methods` and `enabled_methods` aliases. (#803)
- `disable` action returns `disabled_methods: list[str]`. (#803)
- `action="reset"` implemented (clears state + re-runs setup). (#803)
- Empty/whitespace `user_id` now rejected with typed `user_id is required` error. (#803)
- `_setup_totp` debug `print` replaced with `logger.debug` per observability rules. (#803)

## [2.13.4] — 2026-05-03 — issue #781 hygiene release (T4 + T5)

Patch release cutting PyPI for T4 (core/runtime + nexus TODO-NNN comment-strip) and T5 (CI gate + regression test) of the issue #781 cleanup workstream.

### Changed (T4 of #781 — comment-only, src/kailash/)

- Stripped 18 `TODO-NNN` markers in `src/kailash/runtime/local.py` + `runtime/{pause,shutdown}.py` + `trust/plane/key_managers/manager.py` per the ratified disposition catalog. Class 1a banner with `v0.12.0` paired tracker → `(SHIPPED-v0.12.0)`; all other inline-shipped markers drop the parenthetical entirely.

### Added (T5 of #781 — CI gate)

- `.pre-commit-config.yaml::no-untracked-todo-nnn` hook + `scripts/check_no_untracked_todo_nnn.sh` shared script + `tests/regression/test_no_untracked_todo_nnn.py` regression test. Three-layer gate prevents future PRs from reintroducing untracked `TODO-NNN` markers in `src/` + `packages/*/src/`. Synthetic-PR validation (recorded in PR #808): inserting `# TODO-999: synthetic` fails both hook + test; appending `(tracked: gh#999)` passes both. Closes #781.

## [2.13.3] — 2026-05-02 — auth Rule 2 cleanup release (#779)

Patch release cutting PyPI for the auth-stub Rule 2 cleanup that landed in
PR #779 (commit `9364027b`, merged 2026-05-01) without a same-PR version bump.
No new code in this release; the bump catches PyPI up to main per
`rules/build-repo-release-discipline.md` Rule 5 (sub-package src changes
require same-PR version bump — when the bump is missed, a follow-up
release-prep PR closes the gap).

### Fixed (recap from #779)

- **7 `raise NotImplementedError` stubs eliminated across `src/kailash/{nodes,middleware}/auth/`** per `rules/zero-tolerance.md` Rule 2 § "Fake dispatch" and `rules/orphan-detection.md` Rule 3. Default-config users previously hit `NotImplementedError` from documented public APIs (`SSOAuthenticationNode(provider="saml")`, `EnterpriseAuthProviderNode(method="passwordless")`, the unconditional `_assess_behavior_risk` call). Each surface now either raises a typed `ValueError` naming the override path, returns a documented no-op default, or — for orphan helpers with zero production callers — was deleted outright.
- Locked by `tests/regression/test_auth_stub_rule2_cleanup.py` (11 tests, all passing), including a structural sweep that fails if `raise NotImplementedError` re-appears anywhere in `src/kailash/{nodes,middleware}/auth/`.

## [2.13.2] — 2026-05-01 — `durability_middleware` passes through SSE / `StreamingResponse` (#767)

Patch release closing issue #767. `DurableWorkflowServer._add_durability_middleware` (the durability middleware that `EnterpriseWorkflowServer` and `Nexus()` mount on every 2xx response) drained `response.body_iterator` before forwarding any bytes. For `StreamingResponse` (SSE, chunked transfer, file streams, gRPC streaming) this destroyed streaming semantics on the first request and replayed the captured stream as a JSON envelope on every cache hit, breaking every SSE / `EventSource` client.

### Fixed

- **#767 — `durability_middleware` short-circuits before drain when the response is streaming.** Detects `isinstance(response, StreamingResponse)` AND `content-type: text/event-stream` so a bare `Response(content=..., media_type="text/event-stream")` (used by some handlers) is also handled correctly. The completion event still fires (with `streaming=true`) so request lifecycle observability is preserved; only the body drain and the dedup cache step are skipped, since neither is meaningful for an open-ended stream.

### Tests

- `tests/regression/test_issue_767_durability_sse_passthrough.py` — 4 tests: (1) first SSE request keeps `text/event-stream` content-type and full SSE body; (2) bare `Response` with `content-type: text/event-stream` also passes through; (3) cache-hit replay keeps streaming semantics — pre-fix the second identical SSE GET returned `JSONResponse(content={"content": ..., "status_code": 200, ...})` at `application/json`, breaking every SSE client; (4) JSON / non-streaming responses retain the original drain + dedup-cache behaviour. Pre-fix verification: cache-replay test asserts `application/json` on second GET (failure mode); post-fix all 4 pass.

## [2.13.1] — 2026-04-30 — TraceEvent timestamp microsecond padding (#731)

Patch — pins the `TraceEvent` timestamp string to a fixed-width microsecond field so cross-tool log correlation no longer drifts when sub-millisecond events are emitted.

### Fixed

- **#731 — TraceEvent timestamp microsecond padding** — `TraceEvent` formatted timestamps with variable-width microseconds (e.g. `2026-04-30T12:34:56.7Z` for tenths-of-millisecond events), breaking lexical ordering and downstream parsers that assumed fixed-width ISO-8601. Timestamps now pad microseconds to six digits (`2026-04-30T12:34:56.700000Z`).

## [2.13.0] — 2026-04-30 — `kailash.utils.lifespan` shared FastAPI helpers (the v2.13.0 cluster: closes #712)

Minor bump — ships the cross-FastAPI-site lifespan helper module that drives `app.router.on_startup` / `on_shutdown` from any custom `FastAPI(lifespan=...)` and patches three sibling sites that historically dropped router hooks silently.

### Added

- **`kailash.utils.drive_router_lifespan_startup` / `drive_router_lifespan_shutdown` (#712 / S1)** — shared async helpers that iterate `app.router.on_startup` / `app.router.on_shutdown` (the same lists Starlette's default `_DefaultLifespan` walks) from inside any custom FastAPI lifespan. Both sync (`def`) and async (`async def`) handlers are accepted; per-handler exceptions are isolated and logged at WARN per `rules/observability.md` Rule 7. The first captured exception is re-raised when `propagate_errors=True` (the default for startup, preserves uvicorn fail-fast); shutdown callers typically pass `propagate_errors=False` for best-effort cleanup. Drives the data structure FastAPI's own internal dispatcher walks rather than calling `app.router.startup()` / `.shutdown()` by name — version-stable per `rules/framework-first.md` § "Drive The Data, Not The Dispatch" (the dispatch method names drift across FastAPI / Starlette versions; the registration lists do not).

### Fixed

- **#712 — three sibling FastAPI lifespan sites silently drop router-registered handlers (S2)** — `KailashAPIGateway`, `WorkflowAPIGateway`, and `WorkflowAPI` each constructed `FastAPI(lifespan=...)` without iterating `app.router.on_startup` / `app.router.on_shutdown`, so every handler registered via `@app.on_event("startup")` or `app.router.on_startup.append(...)` was silently dropped (the #500 silent-drop bug pattern at three additional sites). All three now route through `drive_router_lifespan_startup` / `drive_router_lifespan_shutdown` so router-registered hooks fire correctly.

### Tests

- `tests/regression/test_issue_712_sibling_fastapi_sites.py` — Tier 2 regression suite verifying every sibling site drives its router hooks through the shared helper.
- `tests/regression/test_issue_712_consumer_startup_patterns.py` — Tier 2 regression for the canonical consumer patterns (`Nexus.add_startup_handler` + DataFlow async DDL); cross-references kailash-nexus 2.5.0.

## [2.12.0] — 2026-04-28 — Pool lifecycle hardening (DPI-B: closes #697, #698)

Minor bump — ships the process-pool lifecycle management surface that was missing from the
async SQL adapter, closing the silent pool-leak class surfaced by the dataflow-prod-incident
postmortem.

### Added

- **`_PROCESS_POOL_REGISTRY`** — module-level `dict` keying all active `AsyncSQLitePool` /
  `AsyncProcessPool` instances by pool key for introspection, LRU eviction, and reaper access.
- **`set_pool_defaults(max_size, idle_timeout_sec)`** — process-level default overrides for
  newly created pools; lets the operator tune pool size and idle expiry without modifying
  every call site.
- **`pool_count() -> int`** — returns the number of currently registered live pool instances;
  used by tests and monitoring to assert pool bounds after repeated DDL-fail cycles.
- **`pool_keys() -> list[str]`** — returns a snapshot of registered pool keys for diagnostic
  enumeration.
- **`PoolExhaustedError`** — typed exception raised when a new pool cannot be allocated because
  the process-level registry has reached `max_pool_count`; previously the adapter fell back
  silently to an unbounded allocation.
- **Idle-timeout reaper task** — background `asyncio.Task` that fires every `idle_timeout_sec`
  seconds and closes idle pools; controlled via `set_pool_defaults`.
- **`cleanup_all_pools()`** — drains the registry and closes all open pools; safe to call from
  test teardown or process shutdown hooks.

### Fixed

- **#697 — Silent pool leak on `_get_adapter` fallback** — the broad `except Exception` catch
  in `_get_adapter` previously swallowed adapter-init errors and re-entered the factory,
  leaking a new unregistered pool on every retry. Narrowed to a typed catch-list; failed
  adapters now surface with a typed error rather than accumulating dead pool handles.
- **#698 — Idle-timeout and LRU pool eviction not configurable** — pools older than the idle
  threshold are now reaped automatically; the registry enforces a configurable LRU cap so
  long-running processes do not accumulate unbounded pool instances.

### Changed (BREAKING)

- `_get_adapter` fallback path now raises `PoolExhaustedError` (or the narrowed adapter-init
  error) instead of silently returning a new adapter; callers that relied on the silent
  fallback will see a typed exception with a descriptive message.

## [2.11.3] — 2026-04-27 — Patch: ML error classes missed in v2.11.2 wheel (W6-014, W6-020)

Patch bump — ships two `kailash.ml.errors` additions that were committed to main after
the `v2.11.2` tag and therefore absent from the published wheel. Required by `kailash-ml
1.4.2` at import time.

### Added

- **`LineageNotImplementedError(TrackingError)`** — raised by `km.lineage(...)` while the
  cross-engine LineageGraph surface is deferred to Wave 6.5b. Typed error allows callers
  to distinguish "not yet implemented" from generic failure. Added in commit `56fe3f7a`
  (W6-014).
- **`MigrationRequiredError(MLError)`** — raised by an engine's hot path when a required
  schema object (table/column/index) is absent, indicating the operator has not run the
  corresponding numbered migration. Distinct from `MigrationFailedError` and
  `MigrationImportError`. Added in commit `f5127b15` (W6-020).

## [2.11.2] — 2026-04-26 — JWT security hardening (#635 + #636, Wave 5 audit)

Patch bump — closes two security findings surfaced by Wave 5 portfolio spec audit (workspace `portfolio-spec-audit/04-validate/W5-C-findings.md`).

### Security

- **CRIT (closes #636)** — Remove hardcoded default JWT secret `"api-gateway-secret"` (18 chars) from `src/kailash/middleware/communication/api_gateway.py`. `APIGateway(enable_auth=True)` without an explicit `auth_manager=` now requires `KAILASH_API_GATEWAY_SECRET` environment variable (≥32 bytes per RFC 7518 §3.2). Missing env var raises typed `RuntimeError`; under-length raises typed `ValueError`. Aligns with `rules/env-models.md` (.env source-of-truth) and `rules/security.md` (no hardcoded secrets). Regression tests at `tests/regression/test_issue_636_api_gateway_default_secret.py` cover all paths including a structural invariant that greps the source for the hardcoded literal.
- **HIGH (closes #635)** — Require `iss` claim presence when issuer is configured at `src/kailash/trust/auth/jwt.py::JWTValidator.verify_token`. PyJWT's `verify_iss` only enforces value equality WHEN the claim is present; tokens forged WITHOUT `iss` were silently accepted. Layered `options={"require": ["iss"]}` (and `aud` when audience is configured) closes the bypass. Cross-SDK companion to #625 (kailash-mcp 0.2.10). Regression tests at `tests/regression/test_issue_635_trust_jwt_iss_required.py` cover missing-iss-rejected, missing-iss-allowed-when-no-issuer, present-iss-validated, present-iss-matched, and missing-aud-rejected paths.

### Cross-SDK alignment

- #625 (kailash-mcp 0.2.10) — MCP layer iss-claim fix; this PR completes the same fix at the underlying trust JWT validator the MCP layer delegates to

## [2.11.1] — 2026-04-26 — Complete alg_id Layer-1 threading (#604 Wave 4)

Patch bump — closes Wave 3 `/redteam` HIGH findings H1 + H2 on the `AlgorithmIdentifier` scaffold. Threads `alg_id` through the four remaining Layer-1 sites that PR #627 (kailash 2.11.0) deferred, and re-exports the canonical scaffold symbols from `kailash.trust` and `kailash.trust.signing`. Wire format remains gated on mint ISS-31 + cross-SDK align; until then, all Layer-1 sites enforce `ed25519+sha256` only and raise `NotImplementedError` on any non-default value.

### Security

- **HIGH (closes Wave 3 redteam H1)** — Thread `AlgorithmIdentifier` through the four remaining Layer-1 signed-record dataclasses + producers + verifiers per inventory at `workspaces/issues-604-607/01-analysis/issue-604-signed-record-sites.md`. Closes the multi-site kwarg plumbing gap from PR #627.
  - **`src/kailash/trust/envelope.py`** — `sign_envelope` / `verify_envelope` accept `alg_id` keyword (asymmetric kwarg-only pair; HMAC `ConstraintEnvelope` payload signing forbids embedded `algorithm` field — would break wire compat).
  - **`src/kailash/trust/signing/timestamping.py`** — `TimestampToken` + `TimestampResponse` storage gain `algorithm` field with `to_dict`/`from_dict` round-trip; `LocalTimestampAuthority.get_timestamp` (and abstract / RFC3161 variants) accept `alg_id`; `TimestampAnchorManager.verify_anchor` runs the canonical three-branch guard (empty → DeprecationWarning, default → proceed, non-default → `NotImplementedError`).
  - **`src/kailash/trust/signing/crl.py`** — `CRLMetadata.algorithm` storage field; `CertificateRevocationList.sign` accepts `alg_id`; `verify_signature` runs the three-branch guard.
  - **`src/kailash/trust/messaging/{envelope,signer,verifier}.py`** — `SecureMessageEnvelope.algorithm` field added alongside legacy `signature_algorithm` (distinct semantics: legacy field names the crypto primitive, new field is the agility-scaffold version-tag); `MessageSigner.sign_message` accepts `alg_id`; `MessageVerifier._verify_signature` runs the three-branch guard.
- **HIGH (closes Wave 3 redteam H2)** — Re-export scaffold symbols (`AlgorithmIdentifier`, `ALGORITHM_DEFAULT`, `coerce_algorithm_id`) from canonical namespaces:
  - `kailash.trust.signing` (the home namespace per `specs/trust-crypto.md` § 21.1)
  - `kailash.trust` (top-level convenience)
  - Existing `kailash.trust.pact.envelopes` re-export retained for backward compatibility.

### Cross-SDK

- Wire format remains gated on mint ISS-31 + cross-SDK align. All Layer-1 sites enforce `"ed25519+sha256"` only.

### Origin

- Wave 3 `/redteam` findings H1 + H2: `workspaces/issues-604-607/04-validate/02-security-review.md`.
- Inventory: `workspaces/issues-604-607/01-analysis/issue-604-signed-record-sites.md` § "Threading scope for this PR".

## [2.11.0] — 2026-04-25 — Algorithm-agility scaffold (#604) + SLIP-0039 Shamir wrapper (#606)

Minor bump — two new public modules in `kailash.trust`. Ships alongside `kailash-dataflow 2.3.0` (#607 SecurityDefinerBuilder) and `kailash-pact 0.11.0` (#605 PACT N4/N5 conformance runner). All three are additive; lockstep dep pins updated to `kailash>=2.11.0` across every framework package.

### Added

- **`kailash.trust.signing.algorithm_id`** (#604) — new module exposing the `AlgorithmIdentifier` frozen dataclass + `ALGORITHM_DEFAULT = "ed25519+sha256"` constant + `coerce_algorithm_id(alg_id)` canonical helper. Threaded through `SignedEnvelope` (storage record + `to_dict`/`from_dict`/`verify` triplet) so the algorithm metadata survives JSON round-trip on the wire. Legacy records (pre-#604, no `algorithm` key) are accepted with a one-time `DeprecationWarning` per process containing the literal substring `"scaffold for #604; wire format pending mint ISS-31"`. Non-default values raise `NotImplementedError` until mint ISS-31 stabilises the canonical wire format. Other Layer-1 sites (timestamping, CRL, message envelopes) tracked in inventory at `workspaces/issues-604-607/01-analysis/issue-604-signed-record-sites.md`.
- **`kailash.trust.vault`** (#606) — new package with the SLIP-0039 Shamir secret-sharing wrapper for Trust Vault key backup. Public surface: `ShamirRitual` frozen dataclass + `generate` / `reconstruct` / `serialize_shard` / `deserialize_shard` / `rotate_holders` lazy-import helpers + `back_up_vault_key` stub raising `NotImplementedError("Trust Vault Shamir binding awaits mint ISS-37")`. Lazy-import contract: module imports cleanly without the optional dep; call site raises `RuntimeError` with `pip install kailash[shamir]` install hint when absent.
- **New optional extra `[shamir]`** in root `pyproject.toml` pinning `shamir-mnemonic>=0.3` (latest published: 0.3.0). Install via `pip install kailash[shamir]`.
- **Tier 1 + Tier 2 regression tests** — `tests/regression/test_issue_604_alg_id_threading.py` (13 cases) + `tests/regression/test_issue_606_shamir_wrapper.py` (12 cases) + `tests/integration/trust/test_shamir_round_trip.py` (7 cases against real `shamir-mnemonic`).
- **Spec updates**: `specs/trust-crypto.md` § 21 (algorithm agility) + § 30 (SLIP-0039 wrapper); `specs/trust-eatp.md` § 12 (SignedEnvelope.algorithm field); `specs/security-data.md` (Trust Vault backup posture).

### Related

- Spec gates: `terrene-foundation/mint` ISS-31 (alg_id wire format), ISS-37 (Trust Vault binding).
- Issues: closes part of #604 (SignedEnvelope only — Layer-1 follow-up shards pending), closes #606 (scaffold; binding gated on ISS-37).

## [2.10.0] — 2026-04-25 — MCP transports (#600) + BudgetTracker threshold callback (#603)

Minor bump — two new public API surfaces in kailash core. Ships with `kailash-nexus 2.3.0` (#618 per-connection unicast) and `kailash-kaizen 2.13.0` (#598 PlanSuspension + #602 OrchestrationRuntime parity).

### Added

- **`BudgetTracker.set_threshold_callback(threshold_pct, callback)`** at `src/kailash/trust/constraints/budget_tracker.py` — public API for registering a one-shot callback that fires when budget utilization first reaches a caller-supplied fraction of allocated budget. Distinct from the existing `on_threshold()` (which fires only at hardcoded 80/95/100% marks). Callback fires when `(committed + reserved) / allocated >= threshold_pct` after a successful `reserve()` or `record()` call. Multiple callbacks may be registered at the same threshold (registration order preserved); each (threshold, handle) fires AT MOST ONCE per BudgetTracker instance. Returns an integer handle for symmetric removal via `unregister_threshold_callback(handle)`. Thread-safe under existing `self._lock`; predicate evaluated under lock, callbacks dispatched outside the lock to prevent re-entrancy deadlock. Callback exceptions are logged at WARNING via `logger.exception` and never propagate to `record()`/`reserve()` callers. Motivation: Envoy Phase 01 Grant Moment trigger — operator wires "you've used 80% of your budget" notification to drive escalation. Cross-SDK alignment.
- **`BudgetEvent` payload extended** with optional `threshold_pct: Optional[float]`, `committed_microdollars: Optional[int]`, `reserved_microdollars: Optional[int]` fields. Custom-threshold events carry the registered fraction; legacy `threshold_80` / `threshold_95` / `exhausted` events now also carry their corresponding fraction (0.80 / 0.95 / 1.00) for cross-callback uniformity. `to_dict()` / `from_dict()` are backward-compatible — older payloads without these keys deserialize cleanly with the new fields set to `None`.
- **Tier 1 unit tests** at `tests/trust/unit/test_budget_tracker_callbacks.py` (27 tests) covering happy path, registration order, multi-threshold ordering, exception isolation, once-only firing, threshold-pct validation (NaN/Inf/0/1/boundary), claimed-amount predicate, unregister semantics, allocated-zero edge case, and `_max_callbacks` limit.
- **Tier 2 integration tests** at `tests/trust/integration/test_budget_tracker_callbacks.py` (5 tests) exercising callback dispatch under concurrent `reserve()`/`record()` workers (16-thread + 50-thread scenarios), callback-exception isolation under load, multi-threshold independence under load, and end-to-end Grant Moment scenario. NO mocking — all tests use real `threading` primitives.

### Related

## Note: Changelog Reorganized

The changelog has been reorganized into individual files for better management. Please see:

- **[sdk-users/6-reference/changelogs/](sdk-users/6-reference/changelogs/)** - Main changelog directory
- **[sdk-users/6-reference/changelogs/unreleased/](sdk-users/6-reference/changelogs/unreleased/)** - Unreleased changes
- **[sdk-users/6-reference/changelogs/releases/](sdk-users/6-reference/changelogs/releases/)** - Individual release changelogs

## Recent Releases

### kailash 2.10.0 — 2026-04-25 — MCP transport primitives (stdio / SSE / HTTP) (#600)

**Added** — closes #600

- **`kailash.channels.mcp.Transport`** — abstract base for MCP client transports. Three concrete implementations ship in this module:
  - **`StdioTransport`** — bidirectional JSON-RPC over a local subprocess (LSP-style `Content-Length` framing). Allowlist gate on the spawned command; `allowed_commands=` parameter enforces explicit allowlist; spawning falls back to `TransportError` if the executable is not in the list.
  - **`SseTransport`** — HTTP POST + Server-Sent Events stream. Connects to a remote SSE-exposed MCP server. POSTs requests to `{base}/message`; reads inline JSON OR `data: <json>` SSE events. Per-message reply path supported.
  - **`HttpTransport`** — single-shot request/response. POSTs the JSON-RPC body and parses the JSON response inline. `receive()` raises `NotImplementedError` because HTTP has no unsolicited server-push.
- **`validate_url(raw_url, *, allow_private=False)`** — SSRF guard shared across all HTTP-class transports. Rejects non-`http`/`https` schemes; rejects loopback, link-local, multicast, and RFC-1918 private hosts unless `allow_private=True` is passed (intended for trusted internal endpoints). Raises `TransportError`.
- **Exception hierarchy:** `TransportError` (base) and `ProtocolError` (framing/format errors). All transport methods raise these — never bare `Exception`.

**Tier 1 + Tier 2 coverage:**

- 35 unit tests at `tests/unit/channels/test_mcp_transports.py` cover URL validation, exception hierarchy, transport construction guards, and per-transport contract.
- 4 integration tests at `tests/integration/channels/test_mcp_transports_real.py` execute against real infrastructure (subprocess echo for stdio, `aiohttp` test server for sse + http) — NO mocking per `rules/testing.md` § 3-Tier Testing.

**Cross-SDK parity:** mirrors the cross-SDK MCP transport semantic shape for parity (EATP D6).

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

**Cross-SDK orphan-check.** `src/kailash/trust/immutable_audit_log.py` defined `ImmutableAuditLog` (541 LOC) as a deque-based append-only log with SHA-256 hash chaining. Grep across `src/` + `packages/*/src/` + `tests/` + `packages/*/tests/` returned zero production or test consumers — the module was a pure facade per `rules/orphan-detection.md` §1, never wired into any call site. The canonical audit-storage surface is `kailash.trust.audit_store` (`InMemoryAuditStore` + `AuditStoreProtocol`), which has real production consumers.

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

Four-axis LLM deployment abstraction: 24 preset factories spanning direct providers (OpenAI, Anthropic, Google, 13 others), AWS Bedrock (5 families), GCP Vertex (Claude + Gemini), and Azure OpenAI — all with cross-SDK byte-parity. Additive API: existing `kaizen.providers.registry` continues to work unchanged (39 consumer files verified via regression test).

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

- Workspace: `workspaces/issue-498-llm-deployment/` (ADR-0001, 8 session todos, redteam amendments).

---

## Recent Releases

### kailash 2.8.7 / kailash-kaizen 2.7.5 / kailash-dataflow 2.0.9 / kaizen-agents 0.9.3 — 2026-04-15 — Python 3.14 compatibility (#477) + DataFlow internal LocalRuntime warning (#478)

#### Fixed

- **Python 3.14 (PEP 649 / PEP 749) lazy annotations** (`kailash`, `kailash-kaizen`, `kailash-dataflow`, `kaizen-agents`) — fixes #477: every Kaizen agent built from a class-based `Signature` failed to register on Python 3.14 because the `SignatureMeta.__new__` metaclass read `namespace.get("__annotations__", {})` directly. PEP 649 stops populating that dict and emits a lazy `__annotate__` callable instead, so the metaclass produced signatures with zero input/output fields and every dependent `BaseAgent` refused to construct.
- **DataFlow `LocalRuntime` deprecation warning leaked from internal code** (`kailash-dataflow 2.0.9`, `kailash 2.8.7`) — fixes #478: long-lived `LocalRuntime` instances owned by DataFlow internals were triggering Core SDK's "use context manager" deprecation warning on every call from `model_registry.py:173` and seven other framework-owned construction sites (eight sites total across DataFlow). Core SDK 2.8.7 now exposes a public `LocalRuntime.mark_externally_managed()` opt-out; each DataFlow owner invokes it on the runtime immediately after construction so Core SDK suppresses both the ad-hoc-usage deprecation warning AND the fallback `atexit` cleanup registration — the owning framework is responsible for calling `runtime.close()` at its own shutdown. The prior iteration of this fix set the private `_cleanup_registered` flag directly; that workaround has been removed in favour of the public API so the contract is documented and survives Core SDK refactors. Without this fix the warning would become a hard error in Core SDK v0.12.0.

#### Added

- **`kailash.utils.annotations` shared helper** (`kailash 2.8.7`): single source of truth for annotation introspection across the SDK — `get_namespace_annotations(namespace)` for metaclass `__new__`, `get_class_annotations(cls)` for raw introspection, and `get_resolved_type_hints(cls)` for callers that need fully resolved types (e.g. DataFlow `@db.model` SQL generation). The `get_resolved_type_hints` path mirrors the cross-SDK handler — on Python 3.14 it falls back to `annotationlib.get_annotations(cls, format=FORWARDREF)` and raises a clear per-field error naming the class, the field, and the unresolvable forward reference, instead of the bare `NameError` that raw `cls.__annotations__` access produces.
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

- **Integer record ID coercion for PostgreSQL** (`kailash-dataflow 2.0.7`): `express_sync.update/read/delete` rejected string IDs for integer primary key models on PostgreSQL because type coercion compared raw annotations (`Optional[int]`) against `int` directly. Additionally, the `conditions["id"]` path (used by update's filter dict) had zero type coercion. Extracted `_coerce_record_id()` helper that normalizes type annotations and applied at all 9 record ID paths. Express API type hints updated to accept `Union[str, int]`. Fixes #439.

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
- **Classification fail-closed** (`kailash-dataflow 2.0.6`): `ClassificationPolicy.classify()` changed default from `PUBLIC` (fail-open) to `HIGHLY_CONFIDENTIAL` (fail-closed) for unclassified fields, matching cross-SDK semantics per EATP D6 (cross-SDK alignment #418). A WARN log is emitted when the default is applied.
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

- **Arbor #3 — Nexus workflow metadata** (kailash-nexus 2.0.1): `Nexus.register()` now accepts a `metadata=` kwarg. Metadata is JSON-validated (64 KiB cap) before mutating the workflow and stored as a shallow copy so caller post-register mutations don't leak through. `@handler` decorator and `register_handler()` also accept metadata.
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
