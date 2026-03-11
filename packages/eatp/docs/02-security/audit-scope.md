# EATP Security Audit Scope

**Document purpose**: Define the scope, materials, and focus areas for a
third-party security audit of the EATP SDK. This document is intended to be
shared with prospective audit firms as part of the engagement process.

| Field      | Value                          |
| ---------- | ------------------------------ |
| Protocol   | EATP v2.0                      |
| SDK        | `eatp` Python package (v0.1.0) |
| License    | Apache 2.0                     |
| Language   | Python 3.11+                   |
| Crypto lib | PyNaCl (libsodium bindings)    |
| Maintainer | Terrene Foundation             |

---

## 1. Scope of Audit

The audit should cover the following areas in order of priority.

### 1.1 Cryptographic Primitives (`eatp.crypto`)

| Area                   | File                                         | What to verify                                                                                                 |
| ---------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Ed25519 key generation | `src/eatp/crypto.py`                         | Keys are generated via `nacl.signing.SigningKey.generate()` with no seed reuse                                 |
| Signing                | `crypto.py::sign()`                          | Payload canonicalization (`serialize_for_signing`) is deterministic and injection-free                         |
| Verification           | `crypto.py::verify_signature()`              | Uses `nacl.signing.VerifyKey.verify()`, returns `False` on `BadSignatureError` rather than leaking timing info |
| Key derivation         | `crypto.py::derive_key_with_salt()`          | PBKDF2-HMAC-SHA256 with 100k iterations and 32-byte random salt                                                |
| Hash chain             | `crypto.py::hash_chain()`                    | SHA-256 over canonical JSON; verify no truncation or weak alternatives                                         |
| Salted state hash      | `crypto.py::hash_trust_chain_state_salted()` | Per-chain random salt prevents rainbow table attacks                                                           |

### 1.2 Challenge-Response Protocol (`eatp.enforce.challenge`)

| Area                    | What to verify                                                                           |
| ----------------------- | ---------------------------------------------------------------------------------------- |
| Nonce generation        | 32-byte `secrets.token_hex()` -- sufficient entropy                                      |
| Nonce replay protection | `_used_nonces` dict with time-based eviction and hard cap (100k)                         |
| Challenge expiration    | Time-bound challenges; `is_expired()` uses UTC                                           |
| Rate limiting           | Per-agent rate limiting with configurable window                                         |
| Constant-time checks    | `hmac.compare_digest()` used for challenge ID, agent ID, capability matching             |
| Payload binding         | Signed payload includes `nonce:timestamp:challenger_id` to prevent cross-challenge reuse |

### 1.3 Constraint Evaluation (`eatp.constraint_validator`)

| Area                          | What to verify                                                                                         |
| ----------------------------- | ------------------------------------------------------------------------------------------------------ |
| Tightening invariant          | Child constraints can never exceed parent constraints                                                  |
| Numeric limits                | `cost_limit`, `rate_limit`, `budget_limit`, `max_delegation_depth`, `max_api_calls` -- child <= parent |
| Resource glob matching        | `_glob_match()` uses regex conversion (not `fnmatch`) to prevent `*` matching `/`                      |
| Time window parsing           | `_parse_time_window()` validates HH:MM format and range                                                |
| Forbidden action preservation | Parent's `forbidden_actions` cannot be removed by child                                                |
| Nested constraint validation  | Recursive validation of arbitrarily nested dict constraints                                            |
| Data scope subsetting         | `data_scopes` and `communication_targets` must be strict subsets                                       |

### 1.4 Trust Store Implementations

| Store                | File                           | What to verify                                                                |
| -------------------- | ------------------------------ | ----------------------------------------------------------------------------- |
| InMemoryTrustStore   | `src/eatp/store/memory.py`     | No injection vectors; transaction rollback correctness                        |
| FileSystemTrustStore | `src/eatp/store/filesystem.py` | Path traversal prevention; atomic writes                                      |
| ESA Database Store   | `src/eatp/esa/registry.py`     | SQL injection prevention (parameterized queries only); connection pool safety |

### 1.5 Messaging & Replay Protection (`eatp.messaging`)

| Area              | File                                 | What to verify                                                  |
| ----------------- | ------------------------------------ | --------------------------------------------------------------- |
| Signed envelopes  | `messaging/signer.py`, `verifier.py` | Envelope signature covers all fields; no field omission attacks |
| Replay protection | `messaging/replay_protection.py`     | Nonce tracking, timestamp validation, window enforcement        |
| Channel security  | `messaging/channel.py`               | Channel establishment and teardown                              |

### 1.6 Interoperability Security

| Area                      | File                          | What to verify                                                     |
| ------------------------- | ----------------------------- | ------------------------------------------------------------------ |
| JWT algorithm restriction | `src/eatp/interop/sd_jwt.py`  | Only Ed25519 (`EdDSA`) accepted; no `alg: none` or RS256 downgrade |
| W3C VC signatures         | `src/eatp/interop/w3c_vc.py`  | `Ed25519Signature2020` proof type correctly generated and verified |
| UCAN token validation     | `src/eatp/interop/ucan.py`    | Token chain validation, expiry, audience restriction               |
| Biscuit token security    | `src/eatp/interop/biscuit.py` | Authority block validation, attenuation rules                      |

### 1.7 Trust Operations (`eatp.operations`)

| Area                 | What to verify                                                                  |
| -------------------- | ------------------------------------------------------------------------------- |
| ESTABLISH            | Genesis record signed correctly; capability attestations bound to genesis       |
| DELEGATE             | Tightening invariant enforced; delegation depth limit (MAX_DELEGATION_DEPTH=10) |
| VERIFY               | All three levels (BASIC, STANDARD, FULL) check appropriate properties           |
| AUDIT                | Audit anchors are hash-linked; signatures cover complete anchor data            |
| Authority validation | Inactive authorities rejected; permission checks enforced                       |

---

## 2. Materials to Provide Auditors

### 2.1 Source Code

- **Repository root**: `packages/eatp/` in the Kailash Python SDK monorepo
- **Core modules**: `src/eatp/` (all `.py` files)
- **Test suite**: `tests/` (unit, integration, and adversarial tests)
- **JSON schemas**: `schemas/` (validation schemas for chain elements)
- **Branch**: Auditors should receive a tagged release branch (e.g., `audit/v0.1.0`)

### 2.2 Test Suite Results

Provide auditors with:

- Full `pytest` output including all tiers:
  - **Tier 1**: Unit tests (no external dependencies)
  - **Tier 2**: Integration tests with InMemoryTrustStore
  - **Tier 3**: End-to-end tests with PostgreSQL (if ESA store is in scope)
- **Adversarial test results**: Tests in `tests/test_adversarial_*.py` and
  `tests/test_constraint_validator.py` that specifically target security
  properties (widening attacks, replay attacks, timing attacks)
- **Hypothesis property-based test results**: Fuzzing of constraint
  validation, serialization, and crypto functions
- **Coverage report**: `htmlcov/` output from `coverage run -m pytest`

### 2.3 Architecture Documentation

- [Specification Index](../01-specification/00-index.md) -- protocol overview
- [Trust Chain spec](../spec/trust-chain.md) -- data structure definitions
- [Operations spec](../spec/operations.md) -- operation semantics
- [Constraints spec](../spec/constraints.md) -- tightening invariant details
- [Enforcement spec](../spec/enforcement.md) -- enforcement mode details
- [Wire Format spec](../spec/wire-format.md) -- serialization format

---

## 3. Known Hardened Areas

The following security measures are already in place. Auditors should verify
their correctness and completeness, not merely their existence.

### 3.1 SQL Injection Prevention (ESA Database)

The ESA database store (`eatp.esa.registry`) uses parameterized queries
exclusively. No string interpolation or concatenation is used in SQL
construction. The store layer uses SQLAlchemy Core with bound parameters.

### 3.2 Nonce Eviction with Hard Cap

The challenge-response protocol (`eatp.enforce.challenge.ChallengeProtocol`)
maintains a nonce replay cache with:

- Time-based eviction: nonces older than `challenge_timeout + 60s` are purged
- Hard cap: maximum 100,000 tracked nonces; oldest 25% evicted when cap is hit
- This prevents memory exhaustion attacks via rapid challenge creation

### 3.3 Constant-Time Comparisons

All security-sensitive string comparisons use `hmac.compare_digest()`:

- Challenge ID matching
- Agent ID matching in challenge responses
- Capability proof matching
  This prevents timing side-channel attacks on verification.

### 3.4 JWT Algorithm Restriction

The SD-JWT interop module restricts accepted algorithms to EdDSA (Ed25519).
The `alg: none` and symmetric algorithms are explicitly rejected. This
prevents algorithm confusion attacks.

### 3.5 Resource Glob Matching Fix

The constraint validator's `_glob_match()` method converts glob patterns to
regex with path-aware semantics:

- `*` matches only within a single path segment (does not match `/`)
- `**` matches across segments
- `?` matches a single non-`/` character

This prevents resource expansion attacks where `invoices/*` would incorrectly
match `invoices/../../secrets/api-key` if using `fnmatch.fnmatch()` (which
treats `*` as matching `/`).

### 3.6 Delegation Depth Limit

`TrustOperations` enforces `MAX_DELEGATION_DEPTH = 10` to prevent:

- Denial-of-service via deep delegation chains
- Accountability loss through excessive indirection
- Stack overflow in recursive chain validation

### 3.7 Payload Canonicalization

`serialize_for_signing()` produces deterministic JSON by:

- Sorting dictionary keys recursively
- Converting datetimes to ISO 8601
- Converting enums to their `.value`
- Using compact separators (`(",", ":")`)

This ensures the same logical payload always produces the same bytes for
signing, preventing canonicalization confusion attacks.

---

## 4. Recommended Audit Firm Categories

The following categories of firms are recommended for this engagement.
Specific firm names are intentionally omitted to avoid conflicts of interest.

### 4.1 Cryptographic Protocol Auditors

Firms specializing in:

- Applied cryptography review (Ed25519, hash chains, key management)
- Protocol-level analysis (challenge-response, delegation chains)
- Formal verification of security properties

**Why**: EATP's core value proposition is cryptographic trust. The signing,
verification, and hash chain integrity must be correct.

### 4.2 Application Security Firms

Firms specializing in:

- Python application security
- Injection prevention (SQL, path traversal, command injection)
- Authentication and authorization protocol review
- API security (for the MCP server and A2A endpoints)

**Why**: The SDK includes database stores, file system stores, and network
endpoints that are typical targets for application-level attacks.

### 4.3 Smart Contract / Token Auditors

Firms with experience in:

- Token-based authorization systems (JWT, UCAN, Biscuit, Macaroons)
- Delegation chain analysis
- Capability-based security models

**Why**: EATP's delegation model with tightening invariants is conceptually
similar to capability token systems. Auditors experienced with these systems
will understand the attack surface intuitively.

### 4.4 Combined Engagement

For a comprehensive audit, engage:

1. A **cryptographic protocol auditor** for the core crypto and chain integrity
2. An **application security firm** for the store implementations, API surface,
   and interop modules
3. Optionally, a **formal methods** consultant to model-check the tightening
   invariant and delegation depth properties

---

## 5. Estimated Audit Timeline

| Phase                    | Duration      | Focus                                            |
| ------------------------ | ------------- | ------------------------------------------------ |
| Kickoff & code delivery  | 1 week        | Repository access, architecture walkthrough      |
| Core crypto review       | 2 weeks       | `eatp.crypto`, `eatp.enforce.challenge`          |
| Trust operations review  | 2 weeks       | `eatp.operations`, `eatp.constraint_validator`   |
| Store & interop review   | 1-2 weeks     | Store implementations, JWT/VC/UCAN interop       |
| Report drafting          | 1 week        | Findings, severity ratings, remediation guidance |
| Remediation verification | 1 week        | Verify fixes for critical/high findings          |
| **Total**                | **8-9 weeks** |                                                  |

---

## 6. Out of Scope

The following are explicitly out of scope for this audit:

- **Kailash Core SDK**: The parent monorepo's orchestration framework
- **Frontend applications**: Any UI built on top of EATP
- **Deployment infrastructure**: Cloud hosting, CI/CD pipelines
- **Performance**: Benchmarking is not a security audit concern
- **Rust SDK**: Not yet implemented; will require a separate audit
