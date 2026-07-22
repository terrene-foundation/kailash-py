# PACT Changelog

## [0.18.0] — 2026-07-22 — Deprecate the untrusted metadata['tenant_id'] tenant fallback (#1919)

### Changed (Security)

- **The client-asserted `metadata['tenant_id']` tenant fallback is deprecated and no longer honored in ANY mode (#1919).** Issue #1843 shipped MCP tenant isolation with a secure default (`require_caller_identity=True`) and a documented weaker mode (`require_caller_identity=False`) that, as a last-resort fallback, trusted a client-supplied `metadata['tenant_id']` as the effective tenant. Under that documented weaker mode a client could influence a tenant-isolation decision via the request body — the exact impersonation surface first-class tenant isolation exists to close, narrowed to one opt-in mode. The single enforcer decision chokepoint (`_resolve_effective_tenant`) now NO LONGER trusts `metadata['tenant_id']` in the weaker branch: when a caller exercises the now-deprecated path a `DeprecationWarning` fires and the resolution returns `None`, which **fails the tenant-isolation decision CLOSED** (never fail-open). A client-asserted tenant can no longer influence a tenant decision in any mode. Defense-in-depth: `McpGovernanceMiddleware.invoke` / `invoke_resource_read` now scrub `metadata['tenant_id']` at the boundary before building the context (mirroring `from_network_transport`), so the client value never propagates into audit/echo surfaces either.

  - **Behavior change:** a deployment on the weaker mode (`require_caller_identity=False`) that relied on the metadata fallback will see previously-approved calls now BLOCKED (fail-closed) plus a `DeprecationWarning`.
  - **Migration:** provide a trusted caller identity (`McpCallerIdentity.tenant`) or a server-verified context tenant (`McpActionContext.tenant` / `McpResourceContext.tenant`, populated server-side at the network boundary), OR set `McpGovernanceConfig.require_caller_identity=True` (the secure default). The `require_caller_identity=False` mode still exists — only its trust of the client-asserted metadata tenant is removed.
  - **Unchanged:** the secure default (`require_caller_identity=True`) is byte-identical — it never consulted the metadata channel and does not warn. Verified/trusted tenant precedence (verified context tenant > caller identity) is unchanged.

## [0.17.0] — 2026-07-22 — First-class server-verified tenant field on McpActionContext (#1878)

### Added (Security)

- **`McpActionContext` / `McpResourceContext` gain a first-class, server-verified `tenant` field (#1878).** MCP governance tenant isolation previously keyed on a client-body-copyable `metadata['tenant_id']`, letting an authenticated caller assert an arbitrary tenant. The new `tenant` field is populated server-side from the authenticated transport at the network boundary and is excluded from `to_dict`/`from_dict` (the on-the-wire envelope stays byte-identical to 0.16.x — no cross-SDK wire change). `_resolve_effective_tenant` ranks it above caller-identity and metadata; both enforcement surfaces plus the rate-limit re-resolution read the verified field; `from_network_transport` strips any body-supplied `tenant_id`. Fail-closed: tenant isolation active + no verified tenant → DENY.

## [0.16.1] — 2026-07-20 — Export the tenant-isolation types at the `pact` top level

### Fixed

- **`pact.McpCallerIdentity`, `pact.McpTenantGrant`, and `pact.McpResourceContext`
  now import at the top level.** The three tenant-isolation types added in 0.16.0
  (#1843) were exported from `pact.mcp` but omitted from the top-level `pact`
  package's re-export + `__all__`, unlike their sibling `McpActionContext` —
  so `from pact import McpCallerIdentity` raised `ImportError` while
  `from pact.mcp import McpCallerIdentity` worked. Added all three to
  `pact/__init__.py`'s import block and `__all__` for API consistency. No
  behavior change; the `pact.mcp` import path is unaffected.

## [0.16.0] — 2026-07-20 — First-class MCP tenant isolation (#1843)

### Added (Security)

- **`pact.mcp` gains first-class tenant isolation for `tools/call` and
  `resources/read` (#1843).** Prior to this release, MCP governance had no
  tenant isolation at all — a tenant-A caller could reach tenant-B's tools,
  and `resources/read` had no governance layer whatsoever (not even
  default-deny). `McpGovernanceConfig` gains an additive, optional
  `tenant_grants: dict[str, McpTenantGrant]` field (new `McpTenantGrant`
  dataclass: `tenant`, `tools: frozenset[str]`, `resources: frozenset[str]`).
  Two new types round out the surface: `McpCallerIdentity` (a trusted,
  non-serialized identity — resolved by the transport/auth layer before
  governance evaluation — whose `tenant` OVERWRITES any self-asserted
  `metadata["tenant_id"]`, defeating impersonation) and `McpResourceContext`
  (the `resources/read` sibling of `McpActionContext`, consumed by the new
  `McpGovernanceEnforcer.check_resource_read()` /
  `McpGovernanceMiddleware.invoke_resource_read()` entry points). A single
  shared restrictiveness function scopes both `tools/call` (keyed on tool
  name) and `resources/read` (keyed on URI), evaluated at Step 0 — before
  tool registration — so isolation applies even under
  `DefaultPolicy.ALLOW`. Tenant rides the existing free-form
  `metadata["tenant_id"]` channel; no new field was added to the
  wire-serialized `McpActionContext` envelope, so the fix is byte-neutral
  when `tenant_grants` is empty (the default — isolation OFF, both surfaces
  behave exactly as before this release).
  All four new types (`McpCallerIdentity`, `McpTenantGrant`,
  `McpResourceContext`, `McpGovernanceConfig.tenant_grants`) are exported
  from `pact.mcp`.

- **`McpGovernanceConfig.require_caller_identity` defaults to `True`
  (secure-by-default fix, redteam round 1 on #1843).** Ships in the SAME
  release as `tenant_grants` — there was no prior release where the weaker
  default was live, so this is not a behavior change for any existing
  deployment. When `True` (the default), the tenant resolver never
  consults the self-asserted `metadata["tenant_id"]` fallback; a deployment
  that sets `tenant_grants` but never wires `caller_identity` through its
  transport layer fails closed instead of silently trusting the request
  body. Pass `require_caller_identity=False` explicitly to opt into the
  weaker metadata-fallback channel (appropriate only for deployments with
  no transport-level identity resolution).

### Fixed

- **`McpInvocationResult` was missing from `pact.mcp.middleware.__all__`**
  (orphan-detection.md Rule 6 gap, caught by the #1843 redteam) —
  `from pact.mcp.middleware import *` now includes it, matching the
  existing top-level `pact` re-export.

## [0.15.0] — 2026-07-15 — SOC 2 evidence-collection primitives at the governance layer (#1711)

### Added

- **`EvidenceCollector` / `EvidencePackage`** — a governance-layer SOC 2 evidence
  collector deriving CC6 (access control), CC7 (system operations), and CC8
  (change management) evidence from primitives the SDK already emits (hash-chained
  audit log, RBAC/ABAC grants, tenant isolation, governance records). Every
  collector is tenant-scoped and fail-closed (cross-tenant + unattributed records
  excluded); unmeasured controls report `verified=false` with a reason (no
  fabricated passes); a producer↔consumer contract test binds every collector
  filter to a real emitted action-vocabulary name (`PactAuditAction` /
  `AuditEventType`). Exposed via `from pact import EvidenceCollector, EvidencePackage`.

## [0.14.3] — 2026-06-25 — fix: enforce MCP tool clearance fail-closed before the cost flag and at re-registration (#1456)

### Security

- `pact.mcp.McpGovernanceEnforcer` now enforces a tool policy's
  `clearance_required` as a fail-closed Layer-2 authorization gate, evaluated
  BEFORE the cost ladder. A caller with absent, unrecognized, or insufficient
  `caller_clearance` is BLOCKED regardless of cost band — in particular it can
  no longer slip through the `(0.8·max_cost, max_cost]` soft-flag short-circuit.
  `clearance_required` was previously an advertised-but-unread field (any caller
  could invoke a `clearance_required="secret"` tool). The new
  `McpActionContext.caller_clearance` field carries the caller's
  `ConfidentialityLevel`; `clearance_required=None` remains a no-op (backward
  compatible). Cross-SDK parity with kailash-rs#1492 (EATP D6).
- `McpGovernanceEnforcer.register_tool` monotonic-tightening validation now
  covers `clearance_required`, closing a privilege-escalation in the gate above:
  a re-registration could previously DROP (`secret`→`None`) or LOWER
  (`secret`→`public`) a tool's clearance bar and be accepted as "tightening",
  silently stripping the new authorization gate. Re-registration may now only
  KEEP or RAISE the bar; `None` is treated as the widest setting and an
  unrecognized value as the tightest (fail-closed), exactly matching the
  enforcement path (pact-governance Rule 2: monotonic tightening).

## [0.14.2] — 2026-06-24 — fix: evict silent (agent, tool) pairs from the MCP rate-limiter (#1440)

### Security

- `pact.mcp.McpGovernanceEnforcer` now evicts "silent" `(agent_id, tool_name)`
  pairs whose Layer-5 rate-limit sliding window has fully expired, instead of
  retaining them until the 10k size cap forces LRU eviction. A caller rotating
  `agent_id` per request previously accumulated rate-state toward the cap (a
  memory-exhaustion DoS surface against any rate-limited MCP tool), and the LRU
  backstop could evict a still-active pair and reset its counter (weakening
  enforcement under memory pressure). Window-expiry GC is amortized (the hot
  path stays O(1) between sweeps), never evicts an in-window pair, and the size
  cap remains the within-burst hard backstop — so memory is bounded under every
  timestamp pattern. Cross-SDK parity with kailash-rs#1491 (EATP D6).

## [0.14.1] — 2026-06-21 — fix: reject NaN/Inf in the conformance canonical encoder (#1412)

### Security

- `pact.conformance.vectors.canonical_json_dumps` now rejects RFC-8259-invalid
  `NaN` / `Infinity` (`allow_nan=False`), so a PACT conformance vector generated
  with a non-finite float fails closed at serialization instead of emitting
  invalid JSON a strict cross-SDK parser (Rust `serde_json`) cannot re-parse.
  Byte-neutral on all finite input. Part of the trust-plane-wide NaN/Inf
  signing/hash pre-image sweep (kailash 2.43.1, PR #1412).

## [0.14.0] — 2026-06-19 — feat: apply YAML governance specs to the runtime engine (#1386)

### Added

- `PactEngine` construction from a YAML file OR an in-memory dict now applies the
  YAML-authored governance specs (`clearances` / `envelopes` / `bridges` /
  `ksps`) to the runtime `GovernanceEngine`, so governance authored in a unified
  org file actually takes effect at enforcement. Previously the specs were
  parse-validated and then silently dropped (only the org definition was
  consumed). Powered by the new `kailash.trust.pact.yaml_resolvers`
  engine-application layer (requires `kailash>=2.41.0`).

### Changed

- Bumped the `kailash` floor to `>=2.41.0` (the version providing
  `yaml_resolvers.apply_governance_specs`).

## [0.13.1] — 2026-06-19 — fix: re-export KspDenyDetail from the pact facade (#1375)

### Fixed

- `KspDenyDetail` (the F9 KSP-deny observability type) is now importable as
  `from pact import KspDenyDetail`, matching its access-enforcement siblings
  (`AccessDecision`, `KnowledgeSharePolicy`, `PactBridge`). It was declared in
  `kailash.trust.pact.access.__all__` but never re-exported through the package
  facades, so the import raised `ImportError`. Surfaced by the epic #1375
  holistic post-multi-wave redteam (orphan-detection Rule 6). A structural
  parity regression test pins every `access.__all__` symbol importable from
  both the `kailash.trust.pact` and `pact` facades.

## [0.13.0] — 2026-06-18 — feat: KSP/Bridge access-control scoping & precedence (#1368–#1374)

Exposes the new core PACT access-control scoping API (epic #1375) through the
governance REST surface and bumps the SDK floor to the version that provides it.

### Added

- `CreateKSPRequest` accepts `min_clearance`, `shared_paths`, `shared_types`,
  `shared_classifications`, and `conditions`, with validators that reject a
  `..` traversal segment in `shared_paths`, a non-`HH:MM` `time_window` bound,
  and an unrecognized `conditions` key (fail-closed, defense-in-depth atop the
  core enforcement layer).
- `CreateBridgeRequest` accepts `shared_paths` (`..` rejected).
- `CheckAccessRequest` accepts `item_path`, `item_knowledge_type`, and
  `environment`; the check-access handler threads them into the engine.

### Changed

- Requires `kailash>=2.39.0` (the core release providing the
  `KnowledgeSharePolicy`/`PactBridge`/`KnowledgeItem` scope fields and the
  `check_access` `now`/`environment` parameters this package now calls).

## [0.12.1] — 2026-06-18 — chore: release un-bumped comment-only source change

Patch release cutting the previously-unreleased `7abe1a2c2` source commit (reworded
two `# type`-substring comments to dodge the `python-use-type-annotations` pygrep
false positive + removed one verified-dead duplicate local import in
`engine.py::verify_audit_chain`). No runtime behavior change; AST parses unchanged.
Released to keep the package source tree and PyPI in sync.

## [0.12.0] — 2026-05-09 — slim-core decoupling: `[api]` + `[execution]` extras (#890)

Minor release shipping the kailash-pact side of the kailash 2.18.0 / #890 slim-core decoupling. **Install-shape breaking change** — fastapi, slowapi, kailash-kaizen, and psycopg are no longer pulled by the bare `pip install kailash-pact`. Users hitting the governance HTTP API or kaizen-driven supervisor surfaces MUST install the matching extra (or `[all]` for the pre-0.12.0 install shape).

### Migration table

| Surface used                                                | Pre-0.12.0 install         | 0.12.0+ install                                    |
| ----------------------------------------------------------- | -------------------------- | -------------------------------------------------- |
| `import pact` (core: D/T/R, envelopes, clearance, registry) | `pip install kailash-pact` | `pip install kailash-pact` (unchanged — slim core) |
| `from pact.governance.api import ...` (HTTP / FastAPI)      | `pip install kailash-pact` | `pip install 'kailash-pact[api]'`                  |
| Kaizen-driven supervisors (`engine.py` lazy import path)    | `pip install kailash-pact` | `pip install 'kailash-pact[execution]'`            |
| Pre-0.12.0 default install (back-compat — everything)       | `pip install kailash-pact` | `pip install 'kailash-pact[all]'`                  |

### Changed

- **Slim core dependencies** — `pip install kailash-pact` now installs `kailash>=2.16.0` + `click>=8.0` only. Previously also pulled `fastapi`, `slowapi`, `kailash-kaizen`, `psycopg[binary]`, `psycopg_pool`. Audit per #890:
  - **`fastapi` + `slowapi`** — only reachable via `from pact.governance.api`, NOT from `import pact`. Moved to `[api]` extra.
  - **`kailash-kaizen`** — only used via `from kaizen_agents.supervisor`, lazy-loaded inside `engine.py:1216` (governance-engine method body, not module-scope). Moved to `[execution]` extra.
  - **`psycopg` + `psycopg_pool`** — verified ORPHANS (zero import sites across the package source tree). DELETED.
- **`[all]` umbrella extra** — `pip install 'kailash-pact[all]'` resolves to `kailash-pact[api,execution]`, preserving the pre-0.12.0 default install experience for users who do not want to enumerate which surface they consume.
- **`kailash` floor: 2.16.0** (was `2.11.0`) — aligns with the kailash 2.18.0 slim-core layout and the test-deps-fix commit's manifest.
- **Test `[dev]` extras add `fastapi` + `slowapi`** — `tests/unit/governance/test_api_*.py` module-scope imports fastapi/slowapi to test the `[api]` surface; declared explicitly so `pip install kailash-pact[dev]` still collects the API test suite without needing `[api]` separately.

### Notes

- **Bare `from pact.governance.api import ...` raises `ModuleNotFoundError: fastapi` on a slim install.** Users see the standard Python import error, not a typed install hint. The migration table above is the authoritative recovery path; CHANGELOG is the discovery surface.
- This is a **packaging / install-shape change only** — every Python public-API symbol that existed in 0.11.0 still exists in 0.12.0 with the same signature and semantics. Users on `pip install 'kailash-pact[all]'` see no behavior change.

## [0.11.0] — 2026-04-25 — PACT N4/N5 conformance runner (#605)

Cross-SDK parity with `kailash-rs#317`. Minor bump — new public surface; closes Envoy Phase 02 BET-6 gate (cross-SDK contract parity for Python is now falsifiable).

### Added

- **`pact.conformance` subpackage** (#605 shards A–D) — full PACT N4/N5 conformance vector runner. Public surface:
  - `ConformanceVector`, `ExpectedVerdict` dataclasses (vector schema)
  - `load_vectors(vector_dir)` — JSON fixture loader with schema validation
  - `parse_vector(json_obj)` — strict parser; rejects unrecognised contracts at parse-time with `ConformanceVectorError`
  - `ConformanceRunner` — drives a `GovernanceEngine` through every vector; produces `RunnerReport` with per-vector PASSED / FAILED / UNSUPPORTED outcome + canonical-JSON byte-equality diff
  - `render_failure_report(report)` — human-readable diff renderer
- **`pact-conformance-runner` CLI** (shard C) — entry point: `pact-conformance-runner <vector_dir> [--json] [--verbose]`. Exit code 0 if all PASSED, 1 if any FAILED (UNSUPPORTED counts as PASSED). Stdout is JSON with `--json`, human-readable otherwise; stderr for progress.
- **Vendored N4/N5 vectors** (shard D.1) at `tests/fixtures/conformance/{n4,n5}/*.json` — 5 N4 + 2 N5 vectors, byte-identical copies from `kailash-rs` commit `95916caa66d698d2d7c2755a4b5f3e61019af74e` (snapshot 2026-04-25). Refresh procedure documented in `tests/fixtures/conformance/README.md`.
- **65 tests pass** — 26 vector loader + 19 runner Tier 1 cases + 16 CLI Tier 1 + 4 Tier 2 integration (real `GovernanceEngine` + real `PactEngine` against vendored vectors).
- **Specs**: `specs/pact-enforcement.md` § 21 — public surface contract, vendored-vector refresh procedure, BET-6 status.

### BET-6 Phase 02

Python runner validates byte-for-byte against all 7 real Rust conformance vectors. Cross-SDK governance-semantics parity is now falsifiable. Phase 02 BLOCKER cleared.

### Cross-SDK API gaps surfaced

Two known divergences from the cross-SDK contract (documented in PR #624 body for reviewer triage):

1. `kailash.trust.pact.GovernanceVerdict.level: str` uses legacy snake_case; canonical contract is `zone: GradientZone` enum (PascalCase JSON values like `"AutoApproved"`). Runner owns the cross-SDK shape internally.
2. `kailash.trust.posture.TrustPosture` enum values use legacy semantic labels; canonical Rust values are snake_case variant names. Runner uses internal `PactPostureLevel` enum.

### Related

- Cross-SDK: the Rust SDK (#317)
- Issues: closes #605 (all 4 shards landed across PRs #622 + #624)

## [0.10.0] - 2026-04-23

### Added

- **PACT × kailash-ml governance methods (W32.c)** — new `pact.ml`
  module shipping the three governance methods required by the
  kailash-ml 1.0.0 engine surface per `specs/pact-ml-integration.md`:
  - `check_trial_admission(engine, *, tenant_id, actor_id, trial_config,
budget_microdollars, latency_budget_ms, fairness_constraints=None,
...) -> AdmissionDecision` — pre-trial admission gate for
    `AutoMLEngine.run()` / `HyperparameterSearch.search()` / every
    agent-driven tuning sweep. Validates budget / latency against the
    governance envelope, fails CLOSED on probe exception per PACT
    MUST Rule 4, and emits an audit row with a `sha256:<8hex>` payload
    fingerprint (cross-SDK contract per
    `rules/event-payload-classification.md` MUST Rule 2).
  - `check_engine_method_clearance(engine, *, tenant_id, actor_id,
engine_name, method_name, clearance_required, held_dimensions=None,
...) -> ClearanceDecision` — per-method D/T/R clearance gate called
    at every `MLEngine` mutation entry point (`fit` / `predict` /
    `promote` / `delete` / `archive` / `rollback`).
  - `check_cross_tenant_op(engine, *, actor_id, src_tenant_id,
dst_tenant_id, operation, clearance_required, ...) ->
CrossTenantDecision` — v1.0 always-denied contract per spec
    IT-4 / Decision 12. Full bilateral clearance evaluation lands in
    v1.1. The v1.0 always-denied path is a REAL implementation (frozen
    decision, audit row, typed errors for invalid inputs) -- removing
    it would remove the audit trail and fail-open.
- **Frozen decision dataclasses** in `pact.ml`:
  `AdmissionDecision`, `ClearanceDecision`, `CrossTenantDecision`
  (all `frozen=True` per PACT MUST Rule 1).
- **Typed error hierarchy** for programmer-error inputs:
  `GovernanceAdmissionError`, `GovernanceClearanceError`,
  `GovernanceCrossTenantError`. Denials are DATA, not exceptions.
- **`ClearanceRequirement` decorator** and `MLGovernanceContext`
  frozen dataclass — the `ml_context` kwarg plumbed through every
  MLEngine mutation method. Per `rules/security.md` § Multi-Site
  Kwarg Plumbing, the kwarg is security-relevant; silently defaulting
  it would defeat governance, so the decorator raises `PactError` when
  it is missing.
- **Audit row schema** (`specs/pact-ml-integration.md` §5):
  `decision_id`, `method`, `tenant_id` (indexed per
  `rules/tenant-isolation.md` §5), `actor_id`, `admitted_or_cleared`,
  `binding_constraint`, `reason`, `decided_at`, `payload_fingerprint`,
  `audit_correlation_id` (links PACT rows 1:1 with kailash-ml
  `_kml_audit` rows).

### Cross-SDK Parity

- The `sha256:<8hex>` payload fingerprint format is identical to
  kailash-rs `crates/kailash-pact/src/engines/governance.rs` (spec §7).
  Forensic correlation across polyglot deployments relies on this
  stable shape.

## [0.9.0] - 2026-04-20

### Added

- **Absorbed governance capabilities (#567 PR#7 of 7)** — REJECTS the MLFP
  `GovernanceDiagnostics` parallel facade (716 LOC) and ABSORBS four
  capabilities as first-class methods on existing PACT classes:
  - `PactEngine.verify_audit_chain(...) -> ChainVerificationResult` —
    verifies audit chain integrity within tenant / sequence / time
    filters. Acquires `self._submit_lock` before reading. NEVER raises
    on chain break (fail-closed per PACT MUST Rule 4); returns
    `is_valid=False` with `first_break_reason` + `first_break_sequence`.
  - `PactEngine.envelope_snapshot(...) -> EnvelopeSnapshot` — returns a
    frozen point-in-time envelope snapshot by either `envelope_id` or
    `role_address`. Acquires the engine's thread lock via
    `GovernanceEngine.compute_envelope`.
  - `PactEngine.iter_audit_anchors(...) -> Iterator[AuditAnchor]` —
    yields persisted audit anchors filtered by tenant / time / limit.
    Reuses the canonical `kailash.trust.pact.audit.AuditAnchor` (no
    redefinition).
  - `CostTracker.consumption_report(...) -> ConsumptionReport` —
    aggregates `CostTracker._history` with filters, returning totals in
    microdollars (USD × 1_000_000) for integer-math financial safety.
    Acquires `self._lock` during aggregation.
  - `pact.governance.testing.run_negative_drills(engine, drills, *,
stop_at_first_failure=False)` — test-only batch runner for negative
    governance probes. Fail-CLOSED: a drill passes ONLY when it raises
    `GovernanceHeldError`. A drill that returns normally or raises any
    other exception counts as FAILED.

- **Frozen result dataclasses** in `pact.governance.results`:
  `ChainVerificationResult`, `EnvelopeSnapshot`, `ConsumptionReport`,
  `NegativeDrillResult`. All `frozen=True` per PACT MUST Rule 1. Also
  re-exported at the package top-level (`from pact import
ChainVerificationResult`).

### Security

- All new engine / tracker methods acquire `self._submit_lock` (async)
  or `self._lock` (thread) before reading shared state — no bypasses.
- No new raw SQL; all persistence reads go through existing PACT
  surfaces.
- Rejects MLFP's 3 MUST violations: no chain-race (PR#7 holds the
  submit lock); no non-frozen GovernanceContext exposure (results are
  frozen dataclasses, engine handle stays private); no fail-open drills
  (runner treats exceptions as failures, not passes).

## [0.6.0] - 2026-04-02

### Fixed

- **API error sanitization** (P-H6): All mutation endpoints now hide internal exception details
- **Envelope adapter error handling** (P-H7): PactError vs generic Exception handled separately with sanitized messages
- **NaN/Inf on operational rate limits** (P-H8/P-H9): `max_actions_per_day` and `max_actions_per_hour` validated via `math.isfinite()`
- **AuditChain integrity on deserialization** (P-H10): `from_dict()` verifies hash chain after reconstruction
- **grant_clearance D/T/R resolution** (#215): Endpoint resolves D/T/R addresses via `engine.get_node()` before granting
- **get_node non-head role resolution** (#216): Endpoint supports suffix-based address resolution

### Security

- R2 red team converged: 0 CRITICAL, 0 HIGH findings
- 1,257 tests passing, 0 regressions

## [0.5.0] - 2026-03-30

### Added

- **PactEngine facade**: Dual Plane bridge with progressive disclosure (v0.4.0 → v0.5.0)
- **Bridge LCA Approval** (#168): `create_bridge()` requires lowest common ancestor approval with 24h expiry
- **Vacancy Enforcement** (#169): `verify_action()` checks vacancy status before envelope checks
- **Dimension-Scoped Delegation** (#170): `DelegationRecord.dimension_scope` for delegations scoped to specific constraint dimensions
- **CostModel** (#66): Per-model cost rates wired to GovernedSupervisor and `/cost` handler
- **External HELD mechanism** (#61): `GovernanceHeldError` catch, `resolve_hold()`, `asyncio.Event` gate
- **ConstraintEnvelopeConfig** (#59): Pydantic-based configuration replacing raw dataclass
- **DataClassification → ConfidentialityLevel** (#60): CARE terminology alignment across 12+ files
- **22 governance modules** (#63): Moved to `src/kailash/trust/pact/` (api/cli/mcp stay in kailash-pact)
- **/compact and /plan handlers** (#65): Sync message pruning and GovernedSupervisor display

### Fixed

- **internal_only Enforcement** (#179): Only explicitly external actions blocked for internal-only agents
- **Session file permissions** (#68): 0o600/0o700 with atomic writes via `os.open`

### Security

- Red team converged: all HIGH/MEDIUM findings fixed (thread safety, NaN validation, bounded collections, TOCTOU, fuzzy match)
- 189 new tests, 3,243 total passing
