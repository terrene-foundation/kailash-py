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
