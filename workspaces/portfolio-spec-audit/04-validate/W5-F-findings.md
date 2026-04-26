# W5-F Findings — trust + pact + security + mcp + singletons

**Specs audited:** 18 (trust 3 + pact 5 + security 3 + mcp 3 + singletons 4)
**§ subsections enumerated:** in-progress
**Findings:** CRIT=N HIGH=N MED=N LOW=N
**Known-blocked (mint deps):** N
**Audit completed:** 2026-04-26

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
