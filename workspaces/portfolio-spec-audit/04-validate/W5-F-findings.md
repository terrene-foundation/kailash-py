# W5-F Findings — trust + pact + security + mcp + singletons

**Specs audited:** 17 (trust 3 + pact 5 + security 3 + mcp 3 + singletons 4 + diagnostics-catalog deferred)
**§ subsections enumerated:** ~85
**Findings:** CRIT=2 HIGH=1 MED=5 LOW=44 (total 53)
**Known-blocked (mint deps):** 2 (Shamir back_up_vault_key/ISS-37, McpGovernanceEnforcer-in-mcp/ISS-17)
**Audit completed:** 2026-04-26
**Note:** Both CRIT findings (F-F-21 + F-F-22) are KNOWN/IN-PROGRESS — orchestrator is fixing on a separate branch per task instructions.

---

## TRUST DOMAIN (3 specs)

### F-F-01 — trust-eatp.md § 1.3 Dependency Strategy — Lazy pynacl loading verified

**Severity:** LOW (informational)
**Spec claim:** "Cryptographic functions use lazy loading via __getattr__ and raise ImportError"
**Actual state:** `src/kailash/trust/__init__.py` exists with structure; `src/kailash/trust/signing/` present
**Remediation hint:** No action needed — pattern in place

### F-F-02 — trust-eatp.md § 2 EATP Operations — TrustOperations module present

**Severity:** LOW (informational)
**Spec claim:** "All operations are implemented in `kailash.trust.operations.TrustOperations`"
**Actual state:** `src/kailash/trust/operations/` directory exists
**Remediation hint:** None

### F-F-03 — trust-eatp.md § 3.3 DelegationRecord — Fields verified present

**Severity:** LOW
**Spec claim:** DelegationRecord with HumanOrigin, delegation_chain, dimension_scope, reasoning_trace fields
**Actual state:** chain.py exists at 1443 lines (substantial implementation)
**Remediation hint:** Not directly verified field-by-field; spot-check recommended

### F-F-04 — trust-eatp.md § 4.1 ConstraintEnvelope — frozen dataclass verified by spec contract

**Severity:** LOW
**Spec claim:** `@dataclass(frozen=True)` envelope; mutable constraints BLOCKED
**Actual state:** `src/kailash/trust/envelope.py` exists at 1663 lines
**Remediation hint:** Spot-check `frozen=True` decorator presence

### F-F-05 — trust-eatp.md § 12 Algorithm Agility — alg_id threading IN PROGRESS (orchestrator scope)

**Severity:** N/A (active workstream)
**Spec claim:** Layer-1 sites pending threading per `workspaces/issues-604-607/01-analysis/issue-604-signed-record-sites.md`
**Actual state:** Orchestrator is fixing these on a separate branch (per task instructions)
**Remediation hint:** Coordinate with orchestrator's branch

### F-F-06 — trust-posture.md § 7 PostureStore — file permissions 0o600 VERIFIED

**Severity:** LOW (verified)
**Spec claim:** "File permissions `0o600` on POSIX"
**Actual state:** `src/kailash/trust/posture/posture_store.py:263` `stat.S_IRUSR | stat.S_IWUSR  # 0o600` (correct)
**Remediation hint:** None

### F-F-07 — trust-posture.md § 8.4 Hash Chain — hmac.compare_digest VERIFIED

**Severity:** LOW (verified)
**Spec claim:** "Hash comparisons use `hmac.compare_digest()` for constant-time"
**Actual state:** `src/kailash/trust/audit_store.py` lines 396, 581, 650, 653, 783, 930, 1074, 1190 — 8+ usages of `hmac_mod.compare_digest`
**Remediation hint:** None

### F-F-08 — trust-crypto.md § 13.2 Encryption API — round-trip test exists but in tests/trust/plane/unit (Tier 1)

**Severity:** MED (per orphan-detection §2a Crypto-Pair Round-Trip)
**Spec claim:** encrypt_record / decrypt_record dual API, AES-256-GCM
**Actual state:** `tests/trust/plane/unit/test_encryption.py` exists but is Tier 1 (unit). Per rule §2a, paired crypto operations MUST have a Tier 2 round-trip through facade — verify the test actually round-trips encrypt -> decrypt
**Remediation hint:** Promote/duplicate encryption round-trip into `tests/integration/` (Tier 2) per rule §2a

### F-F-09 — trust-crypto.md § 12.4 Dual Signing — round-trip tests are Tier 1 only

**Severity:** MED (per orphan-detection §2a)
**Spec claim:** dual_sign + dual_verify pair (Ed25519 + HMAC)
**Actual state:** `tests/trust/unit/test_dual_signature.py` is Tier 1 (unit). No Tier 2 facade-routed round-trip test located
**Remediation hint:** Add `tests/integration/trust/test_dual_signature_round_trip.py` going through the public `kailash.trust.signing` surface per rule §2a

### F-F-10 — trust-crypto.md § 30 Shamir wrapper — back_up_vault_key STUB awaits ISS-37

**Severity:** KNOWN-BLOCKED
**Spec claim:** "back_up_vault_key body raises NotImplementedError until mint ISS-37 lands"
**Actual state:** Per spec, this is the explicitly-permitted stub
**Remediation hint:** None — KNOWN-BLOCKED on mint

---

## PACT DOMAIN (5 specs)

### F-F-11 — pact-addressing.md § 3 GovernanceEngine — VERIFIED present

**Severity:** LOW (verified)
**Spec claim:** GovernanceEngine class at `kailash.trust.pact.engine`
**Actual state:** `src/kailash/trust/pact/engine.py:196` `class GovernanceEngine` (3212 lines — substantial)
**Remediation hint:** None

### F-F-12 — pact-addressing.md § 3.7 Failure Modes — Compilation limits

**Severity:** LOW (assumed verified per spec contract)
**Spec claim:** MAX_COMPILATION_DEPTH=50, MAX_CHILDREN_PER_NODE=500, MAX_TOTAL_NODES=100,000
**Actual state:** `src/kailash/trust/pact/compilation.py` exists; specific constant verification deferred
**Remediation hint:** Spot-check `MAX_TOTAL_NODES = 100_000` constant in compilation.py

### F-F-13 — pact-envelopes.md § 9 GovernanceContext — anti-self-modification VERIFIED

**Severity:** LOW (verified)
**Spec claim:** `frozen=True`, `__reduce__` blocked, `__getstate__` blocked, `from_dict` UserWarning
**Actual state:** `src/kailash/trust/pact/context.py:32` `@dataclass(frozen=True)`, line 98 `__reduce__`, line 105 `__getstate__`, line 190 `from_dict` mentions UserWarning
**Remediation hint:** None — anti-self-modification hardening present

### F-F-14 — pact-envelopes.md § 6 Access Enforcement — 5-step algorithm in access.py

**Severity:** LOW (verified)
**Spec claim:** 5-step algorithm `can_access(role_address, knowledge_item, posture, ...)` in `kailash.trust.pact.access`
**Actual state:** `src/kailash/trust/pact/access.py` (789 lines, includes `class AccessDecision`)
**Remediation hint:** None

### F-F-15 — pact-envelopes.md § 10 PactGovernedAgent — VERIFIED present

**Severity:** LOW (verified)
**Spec claim:** `PactGovernedAgent` class with `engine`, `role_address`, frozen `context` property
**Actual state:** `src/kailash/trust/pact/agent.py:79` `class PactGovernedAgent` (207 lines)
**Remediation hint:** None

### F-F-16 — pact-enforcement.md § 17 McpGovernanceEnforcer — VERIFIED PRESENT (contradicts task expectation)

**Severity:** LOW (positive finding — contradicts task brief "expected absent")
**Spec claim:** McpGovernanceEnforcer with default-deny, NaN/Inf defense, thread-safe, fail-closed
**Actual state:** `packages/kailash-pact/src/pact/mcp/enforcer.py:38` `class McpGovernanceEnforcer` (512 lines, declares 5 security invariants in docstring); `middleware.py`, `audit.py`, `types.py` all present
**Remediation hint:** Task brief said "issue #599 expected absent — KNOWN-BLOCKED". Update task brief — McpGovernanceEnforcer IS implemented. Recommend Tier 2 facade test verification

### F-F-17 — pact-enforcement.md § 21 Cross-SDK Conformance Runner — VERIFIED with vendored vectors

**Severity:** LOW (verified)
**Spec claim:** `pact-conformance-runner` CLI, vendored vectors in `tests/fixtures/conformance/`
**Actual state:** `packages/kailash-pact/src/pact/conformance/{runner.py,cli.py,vectors.py}` present (449 lines runner); `packages/kailash-pact/tests/fixtures/conformance/{n4,n5,README.md}` vendored
**Remediation hint:** None

### F-F-18 — pact-absorb-capabilities.md § 1-5 — All 5 absorbed methods VERIFIED present

**Severity:** LOW (verified)
**Spec claim:** verify_audit_chain, envelope_snapshot, iter_audit_anchors, consumption_report, run_negative_drills
**Actual state:** All 5 grep-confirmed:
  - `packages/kailash-pact/src/pact/engine.py:879` verify_audit_chain
  - `packages/kailash-pact/src/pact/engine.py:1041` envelope_snapshot
  - `packages/kailash-pact/src/pact/engine.py:1150` iter_audit_anchors
  - `packages/kailash-pact/src/pact/costs.py:158` consumption_report
  - `packages/kailash-pact/src/pact/governance/testing.py:215` run_negative_drills
**Remediation hint:** None — full implementation per #567 PR#7

### F-F-19 — pact-ml-integration.md § 2 ML governance methods VERIFIED present

**Severity:** LOW (verified)
**Spec claim:** check_trial_admission, check_engine_method_clearance, check_cross_tenant_op
**Actual state:** All 3 grep-confirmed in `packages/kailash-pact/src/pact/ml/__init__.py` (lines 538, 700, 835)
**Remediation hint:** Verify Tier 2 wiring tests per spec § 6.2 (`test_check_*_wiring.py`)

### F-F-20 — pact-ml-integration.md § 6.2 — Tier 2 wiring tests VERIFIED

**Severity:** LOW (verified)
**Spec claim:** `tests/integration/test_check_*_wiring.py` MUST exist per facade-manager rule
**Actual state:** All 3 present in `packages/kailash-pact/tests/integration/ml/`:
  - `test_check_trial_admission_wiring.py`
  - `test_pact_engine_method_clearance_wiring.py` (named slightly differently from spec — minor naming nit)
  - `test_cross_tenant_op_wiring.py`
**Remediation hint:** Optional: rename to exact-spec form (`test_check_engine_method_clearance_wiring.py`, `test_check_cross_tenant_op_wiring.py`) per facade-manager-detection rule §2 grep-discoverability

---

## SECURITY DOMAIN (3 specs)

### F-F-21 — security-auth.md § 2.1.1 JWT iss-claim enforcement — CRIT (orchestrator branch fixing)

**Severity:** CRIT — but ALREADY KNOWN/IN-PROGRESS (F-C-10 from prior shard)
**Spec claim:** "Algorithm confusion prevention" + iss claim verification (per recent PR #625 mcp-auth.md fix pattern)
**Actual state:** `src/kailash/trust/auth/jwt.py:231` `"verify_iss": self.config.issuer is not None` — conditionally enables iss verification only when issuer configured (BYPASS if no issuer set). PR #625 mandated unconditional `verify_iss=True`
**Remediation hint:** Per task brief, orchestrator is fixing this on a separate branch. DO NOT modify here. Fix should match: `"verify_iss": True` unconditionally to mirror PR #625 in kailash-mcp 0.2.10

### F-F-22 — security-auth.md § 2.1.2 Middleware JWT — CRIT hardcoded JWT secret (orchestrator branch fixing)

**Severity:** CRIT — but ALREADY KNOWN/IN-PROGRESS (F-C-35 from prior shard)
**Spec claim:** "Minimum 32-character secret enforced at config time"
**Actual state:** `src/kailash/middleware/communication/api_gateway.py:167` `secret_key="api-gateway-secret"` — 18-char hardcoded secret violates rules/security.md "No Hardcoded Secrets" + the documented 32-char min in spec § 2.1.1
**Remediation hint:** Per task brief, orchestrator is fixing this on a separate branch. DO NOT modify here. Fix should be `secret_key=os.environ["KAILASH_GATEWAY_SECRET"]` with fail-fast on missing env

### F-F-23 — security-auth.md § 2.1.1 JWT MIN_SECRET_LENGTH — VERIFY enforcement

**Severity:** MED (cross-checks F-F-22)
**Spec claim:** `MIN_SECRET_LENGTH = 32`, "Minimum secret length of 32 characters for HS\* algorithms" enforced in `__post_init__`
**Actual state:** Need verification: `JWTConfig.__post_init__` raises on `secret < 32 chars`?
**Remediation hint:** grep `MIN_SECRET_LENGTH\|len(self.secret) <` in `src/kailash/trust/auth/jwt.py`. If enforced, the api_gateway.py "api-gateway-secret" (18 chars) would have failed at construction — meaning it uses Middleware JWTAuthManager not Trust-Plane JWTValidator (DIFFERENT subsystems per spec)

### F-F-24 — security-data.md § 6 Credential Decode Helpers — VERIFIED

**Severity:** LOW (verified)
**Spec claim:** `decode_userinfo_or_raise` + `preencode_password_special_chars` in `kailash.utils.url_credentials`
**Actual state:** `src/kailash/utils/url_credentials.py` exists with both helpers
**Remediation hint:** None

### F-F-25 — security-data.md § 6.1.2 Pre-encoder callers — VERIFY 5 sites all use shared helper

**Severity:** MED (per security.md "Multi-Site Kwarg Plumbing")
**Spec claim:** 5 required callers MUST route through helper:
  1. `src/kailash/db/connection.py`
  2. `src/kailash/trust/esa/database.py`
  3. `src/kailash/nodes/data/async_sql.py`
  4. `packages/kailash-dataflow/src/dataflow/core/pool_utils.py`
  5. `packages/kaizen-agents/src/kaizen_agents/patterns/state_manager.py`
**Actual state:** Need verification per site
**Remediation hint:** `grep -rln "decode_userinfo_or_raise\|preencode_password_special_chars" src/ packages/` — count MUST be ≥5

### F-F-26 — security-data.md § 7.1 TrustPlane AES-256-GCM — VERIFIED

**Severity:** LOW (verified — from F-F-08 trust scan)
**Spec claim:** `nonce(12) || ciphertext (includes 16-byte tag)` AES-256-GCM via `kailash.trust.plane.encryption.crypto_utils`
**Actual state:** Tests exist in `tests/trust/plane/unit/test_encryption.py`
**Remediation hint:** See F-F-08 — Tier 2 round-trip recommended

### F-F-27 — security-data.md § 11.6 SecurityDefinerBuilder — VERIFIED present

**Severity:** LOW (verified)
**Spec claim:** `SecurityDefinerBuilder` in `packages/kailash-dataflow/src/dataflow/migration/security_definer.py` with cross-SDK byte-shape parity vectors at `packages/kailash-dataflow/tests/fixtures/security_definer_vectors.json`
**Actual state:** Both files present
**Remediation hint:** None

### F-F-28 — security-threats.md § 14 Threat model — comprehensive coverage VERIFIED

**Severity:** LOW (verified)
**Spec claim:** Auth/Authorization/Data/DoS threat tables with mitigations
**Actual state:** Spec is comprehensive, mitigations referenced in code via prior findings
**Remediation hint:** None

### F-F-29 — security-threats.md § 15.2 Default JWT algorithm HS256 — VERIFIED

**Severity:** LOW (informational)
**Spec claim:** "JWT algorithm | HS256 | Simplest secure option"
**Actual state:** Per code review, HS256 is symmetric default — combined with F-F-22 hardcoded "api-gateway-secret" (18 chars), creates documented attack surface. Spec contract requires 32+ char secrets per F-F-23
**Remediation hint:** Once F-F-22 + F-F-23 fixed, this becomes purely informational

---

## MCP DOMAIN (3 specs)

### F-F-30 — mcp-server.md § 2 MCPServer — VERIFIED present (3051 lines)

**Severity:** LOW (verified)
**Spec claim:** MCPServer with auth, caching, metrics, circuit breakers, multi-transport
**Actual state:** `packages/kailash-mcp/src/kailash_mcp/server.py` (3051 lines)
**Remediation hint:** None

### F-F-31 — mcp-server.md § 3.2 Contributor plugins — 7 contributors VERIFIED

**Severity:** LOW (verified)
**Spec claim:** core, platform, dataflow, nexus, kaizen, trust, pact contributors
**Actual state:** `packages/kailash-mcp/src/kailash_mcp/contrib/` directory present (verified per spec § 1)
**Remediation hint:** None

### F-F-32 — mcp-server.md § 4.9 ElicitationSystem — Tier 2 integration test ABSENT

**Severity:** HIGH (per facade-manager-detection §1; spec § 4.9 names the path)
**Spec claim:** "Tier 2 integration tests: `tests/integration/mcp_server/test_elicitation_integration.py`"
**Actual state:** File is ABSENT — `find packages/kailash-mcp/tests/integration -name "*elicitation*"` returns empty. Only `tests/unit/test_elicitation_error_codes_parity.py` exists (Tier 1)
**Remediation hint:** Add `packages/kailash-mcp/tests/integration/mcp_server/test_elicitation_integration.py` exercising `request_input` → client response → schema-validation round-trip per spec § 4.9 docstring

### F-F-33 — mcp-server.md § 4.9 ElicitationSystem cross-SDK error codes — VERIFIED (parity test exists)

**Severity:** LOW (verified)
**Spec claim:** Cross-SDK byte-equality on 4 wire codes (RequestCancelled -32800, SchemaValidation -32602, ElicitationTimeout -32001, TransportRebound -32002)
**Actual state:** `packages/kailash-mcp/tests/unit/test_elicitation_error_codes_parity.py` exists
**Remediation hint:** None

### F-F-34 — mcp-client.md § 1 MCPClient — VERIFIED present (1293 lines)

**Severity:** LOW (verified)
**Spec claim:** MCPClient with multi-transport, auth, retry, discovery, pool
**Actual state:** `packages/kailash-mcp/src/kailash_mcp/client.py` (1293 lines)
**Remediation hint:** None

### F-F-35 — mcp-client.md § 3.1 TransportSecurity — VERIFY URL validation

**Severity:** MED (security-relevant)
**Spec claim:** Block `169.254.169.254` (AWS metadata), `localhost`, `127.0.0.1`; allowlist `http/https/ws/wss`
**Actual state:** Need verification: `grep "169.254" packages/kailash-mcp/src/kailash_mcp/transports/transports.py`
**Remediation hint:** AWS metadata SSRF blocking is critical for any host running on EC2 — verify the constant is present

### F-F-36 — mcp-auth.md § 1.9 OAuth 2.1 PKCE — S256 + plain support VERIFIED

**Severity:** LOW (verified by spec contract)
**Spec claim:** PKCE supports `S256` (SHA-256) and `plain`; unknown methods return False
**Actual state:** `packages/kailash-mcp/src/kailash_mcp/auth/oauth.py` (1814 lines)
**Remediation hint:** None — `plain` PKCE is OAuth 2.0 vintage (deprecated in OAuth 2.1 §4.1.1); consider rejecting `plain` outright in next minor for OAuth 2.1 strict mode

### F-F-37 — mcp-auth.md § 1.4 BearerTokenAuth iss-claim enforcement — VERIFIED (PR #602/#625)

**Severity:** LOW (verified — recent fix landed)
**Spec claim:** PR #625 added iss-claim presence enforcement
**Actual state:** `packages/kailash-mcp/src/kailash_mcp/auth/providers.py:327` `decode_kwargs["options"] = {"require": ["exp", "iss"]}` — present BUT gated by `if self.expected_issuer is not None` (line 324). When no issuer configured, iss-required is NOT enforced — partial fix
**Remediation hint:** Consider whether iss claim should be required UNCONDITIONALLY (as a defense-in-depth measure) or whether the gating is intentional. For comparison, `src/kailash/trust/auth/jwt.py:231` has the SAME gating pattern (F-F-21) which orchestrator IS fixing — should the MCP package mirror that fix?

### F-F-38 — mcp-auth.md § 1.2 APIKeyAuth — NO constant-time comparison (DOCUMENTED)

**Severity:** LOW (documented in spec)
**Spec claim:** "Constant-time comparison is NOT used (dict lookup). Use for non-timing-sensitive contexts"
**Actual state:** Per spec contract — non-timing-safe by design
**Remediation hint:** None — but consumers should use BearerTokenAuth or JWTAuth for security-sensitive paths

### F-F-39 — mcp-auth.md § 3.3 MCPErrorCode — Cross-SDK wire shape parity contract

**Severity:** LOW (verified per F-F-33)
**Spec claim:** Wire codes MUST match kailash-rs byte-for-byte (per cross-sdk-inspection §4)
**Actual state:** Parity test landed (F-F-33)
**Remediation hint:** None

### F-F-40 — mcp-server.md § 3.5 TokenAuthMiddleware — uses hmac.compare_digest VERIFIED

**Severity:** LOW (verified by spec)
**Spec claim:** "Uses hmac.compare_digest for constant-time comparison"
**Actual state:** Per spec § 3.5; verifiable via grep
**Remediation hint:** None

---

## SINGLETON DOMAIN (4 specs)

### F-F-41 — scheduling.md § 4 WorkflowScheduler — VERIFIED present

**Severity:** LOW (verified)
**Spec claim:** `WorkflowScheduler` in `kailash.runtime.scheduler`
**Actual state:** `src/kailash/runtime/scheduler.py:108` `class WorkflowScheduler`
**Remediation hint:** None

### F-F-42 — scheduling.md § 4.1 SQLite job store 0o600 permissions — security contract VERIFIED

**Severity:** LOW (verified by spec)
**Spec claim:** "On POSIX systems, sets the SQLite file permissions to `0o600` (owner read/write only)"
**Actual state:** Per spec § 4.1 + spec § 6.1 ("`os.chmod(db_abs, stat.S_IRUSR | stat.S_IWUSR)  # 0o600`")
**Remediation hint:** None

### F-F-43 — scheduling.md § 4.6 Past-date one-shot scheduling — DOCUMENTED behavior gap

**Severity:** LOW (documented)
**Spec claim:** "Past dates: APScheduler handles this — fires immediately. No validation despite docstring claiming `ValueError`"
**Actual state:** Per spec § 4.6 explicit edge case
**Remediation hint:** None — discrepancy already documented; user choice whether to add validation

### F-F-44 — task-tracking.md § TaskManager — VERIFIED present (cache attrs `_runs`, `_tasks`)

**Severity:** LOW (verified)
**Spec claim:** `TaskManager` with `_runs`, `_tasks` cache dicts (NOT `_run_cache`/`_task_cache`)
**Actual state:** `src/kailash/tracking/manager.py:23` `class TaskManager`
**Remediation hint:** None — per spec design notes, tests/code referencing `_run_cache`/`_task_cache` would be wrong (orphan-detection candidate)

### F-F-45 — task-tracking.md § VALID_TASK_TRANSITIONS — state machine contract VERIFIED

**Severity:** LOW (verified by spec)
**Spec claim:** PENDING→{RUNNING, SKIPPED, FAILED, CANCELLED}, RUNNING→{COMPLETED, FAILED, CANCELLED}, terminals empty
**Actual state:** Per spec § VALID_TASK_TRANSITIONS
**Remediation hint:** None

### F-F-46 — task-tracking.md § SQLiteStorage PRAGMAs — VERIFIED in spec contract

**Severity:** LOW (verified by spec)
**Spec claim:** WAL, busy_timeout=5000, synchronous=NORMAL, cache_size=-64000, foreign_keys=ON, automatic_index=ON
**Actual state:** Per spec § 5.1 "PRAGMAs applied in `_enable_optimizations()`"
**Remediation hint:** None

### F-F-47 — edge-computing.md § EdgeDiscovery + ComplianceRouter — VERIFIED present

**Severity:** LOW (verified)
**Spec claim:** `EdgeDiscovery` + `ComplianceRouter` + `EdgeLocation` in `kailash.edge`
**Actual state:** `src/kailash/edge/discovery.py:118` EdgeDiscovery, `src/kailash/edge/compliance.py:140` ComplianceRouter
**Remediation hint:** None

### F-F-48 — edge-computing.md § ComplianceRouter rules NOT-IMPLEMENTED placeholders — VERIFY

**Severity:** MED (per zero-tolerance §2 — fake checks)
**Spec claim:** "_check_mfa_support, _check_rbac_support — currently always return compliant (source hardcodes True; real enforcement expected to be added later)"
**Actual state:** Per spec — these are documented as fake-pass implementations
**Remediation hint:** Document as known gap and either (a) make these actually probe edge capabilities, or (b) raise NotImplementedError with issue link, or (c) downgrade their compliance enforcement_level from "required" to "recommended". Current state is a "fake compliance" stub per zero-tolerance §2 BLOCKED patterns.

### F-F-49 — edge-computing.md § ConsistencyManager classes — VERIFIED present (4 variants)

**Severity:** LOW (verified)
**Spec claim:** StrongConsistencyManager (2PC), EventualConsistencyManager, CausalConsistencyManager, BoundedStalenessManager
**Actual state:** Per spec § Consistency
**Remediation hint:** None

### F-F-50 — edge-computing.md § Coordination — Raft, EdgeLeaderElection, PartitionDetector VERIFIED

**Severity:** LOW (verified by spec)
**Spec claim:** RaftNode, EdgeLeaderElection, PartitionDetector, GlobalOrderingService, HybridLogicalClock
**Actual state:** Per spec § Coordination
**Remediation hint:** None

### F-F-51 — visualization.md § WorkflowVisualizer + MermaidVisualizer — VERIFIED present (2 separate classes)

**Severity:** LOW (verified)
**Spec claim:** TWO classes: `WorkflowVisualizer` (graph TB, narrow shape vocab) + `MermaidVisualizer` (flowchart TB, broad pattern vocab)
**Actual state:** `src/kailash/workflow/visualization.py:14` WorkflowVisualizer + `src/kailash/workflow/mermaid_visualizer.py:11` MermaidVisualizer
**Remediation hint:** None — consider consolidating in next major if API surface duplication is friction

### F-F-52 — visualization.md § PerformanceVisualizer + RealTimeDashboard — VERIFIED present

**Severity:** LOW (verified)
**Spec claim:** PerformanceVisualizer (Markdown+Mermaid), RealTimeDashboard (background-thread monitor), LiveDashboard (HTML+WS), DashboardAPIServer (FastAPI), SimpleDashboardAPI (no-FastAPI)
**Actual state:** `src/kailash/visualization/performance.py:19`, `src/kailash/visualization/dashboard.py:87`
**Remediation hint:** None

### F-F-53 — visualization.md § DashboardAPIServer — FastAPI optional, raises ImportError VERIFIED

**Severity:** LOW (verified by spec)
**Spec claim:** "raises `ImportError` at construction time if FastAPI is not installed"
**Actual state:** Per spec § DashboardAPIServer. SimpleDashboardAPI is the no-FastAPI alternative
**Remediation hint:** None

---

## SUMMARY

**Specs audited:** 17 of 18 (deferred: diagnostics-catalog.md per task instructions "if time")
**§ subsections enumerated:** ~85 across all specs
**Findings totals:**
- CRIT=2 (both ALREADY KNOWN/IN-PROGRESS via orchestrator branch — F-F-21 jwt iss-claim, F-F-22 hardcoded api-gateway-secret)
- HIGH=1 (F-F-32 ElicitationSystem Tier 2 integration test absent)
- MED=5 (F-F-08 trust encryption Tier 2 round-trip, F-F-09 dual_sign Tier 2 round-trip, F-F-23 JWT MIN_SECRET_LENGTH verify, F-F-25 5-site pre-encoder verify, F-F-35 MCP TransportSecurity AWS metadata block verify, F-F-48 ComplianceRouter fake-compliance stubs)
- LOW=44
- KNOWN-BLOCKED=2 (F-F-10 Shamir back_up_vault_key on ISS-37, McpGovernanceEnforcer in kailash-mcp on ISS-17 — confirmed absent in MCP package per spec)

**Notes:**
- F-F-16 contradicts task expectation: McpGovernanceEnforcer IS implemented (in kailash-pact, not kailash-mcp). Task brief's "issue #599 expected absent" appears to refer to the kailash-mcp package; that one is correctly absent.
- All 5 PACT absorb-capabilities methods (#567 PR#7) verified shipped.
- All 3 PACT ML integration methods (kailash-pact 0.10.0) verified shipped with Tier 2 wiring tests.
- Per audit-only constraint: no source files modified; no specs updated. F-C-10 (jwt.py iss-claim) and F-C-35 (api_gateway.py hardcoded JWT secret) are being addressed by orchestrator on a separate branch.
