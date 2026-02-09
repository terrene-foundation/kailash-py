# Trust Security Hardening (CARE Phase 1)

This guide documents the security fixes applied to Kaizen's EATP trust subsystem. These are foundational hardening measures that underpin the trust integration system.

## Per-Instance Salt (CARE-001)

Key derivation now uses per-instance cryptographic salt instead of a static hardcoded value.

```python
from kaizen.trust.crypto import generate_salt, derive_key_with_salt

# Generate unique salt per deployment
salt = generate_salt()  # 32 bytes, cryptographically random

# Derive key with unique salt (PBKDF2-HMAC-SHA256, 100k iterations)
derived_key, salt_used = derive_key_with_salt(master_key=b"my-key", salt=salt)
```

**SecureKeyStorage** auto-generates salt per instance. For consistent encryption across restarts, set the `{MASTER_KEY_SOURCE}_SALT` environment variable.

## Delegation Signature Verification (CARE-002)

Delegation records are now cryptographically verified using Ed25519 signatures. Previously, signature verification was skipped.

```python
# Full chain verification (all delegations from human origin)
result = await trust_ops.verify_delegation_chain("agent-C")
assert result.valid  # All signatures in the chain verified

# Verifies: delegation ID, task, capabilities, constraint subset
# Detects: tampering, wrong-key signing, replay attacks
```

## Delegation Cycle Detection (CARE-003)

The delegation graph now detects cycles before they cause infinite loops or DoS.

```python
from kaizen.trust.graph_validator import DelegationGraph, DelegationGraphValidator
from kaizen.trust.exceptions import DelegationCycleError

# Build graph and validate
all_delegations = await trust_store.list_delegations()
graph = DelegationGraph.from_delegations(all_delegations)
validator = DelegationGraphValidator(graph)

# Check before adding new delegation
if not validator.validate_new_delegation("agent-C", "agent-A"):
    # Would create cycle: A -> B -> C -> A
    raise DelegationCycleError(["agent-A", "agent-B", "agent-C", "agent-A"])

# Self-delegation always rejected
validator.validate_new_delegation("agent-A", "agent-A")  # Returns False
```

## Maximum Delegation Depth (CARE-004)

Delegation chains are bounded to prevent unbounded depth (resource exhaustion, accountability loss).

```python
from kaizen.trust.operations import TrustOperations, MAX_DELEGATION_DEPTH
from kaizen.trust.chain import DelegationLimits

# Default: max 10 levels of agent-to-agent delegation
trust_ops = TrustOperations(registry, key_manager, store)

# Custom limit
trust_ops = TrustOperations(registry, key_manager, store, max_delegation_depth=5)

# Advanced configuration
limits = DelegationLimits(
    max_depth=5,
    max_chain_length=20,
    require_expiry=True,
    default_expiry_hours=24,
)
```

Attempting to delegate beyond the max depth raises `DelegationError` with details about the current depth and limit.

## Node-Level Trust Verification (CARE-039)

Fixed critical security gap where `_verify_node_trust()` was defined in `base.py` but never called during runtime execution. This created a privilege escalation vector where agents could execute any node type regardless of trust settings.

**Fix**: Wired `_verify_node_trust()` into all 4 execution paths in `LocalRuntime` and `AsyncLocalRuntime`. Trust verification now happens BEFORE each node executes. Trust denial errors are treated as "must stop" conditions that bypass error swallowing.

## Adversarial Security Test Suite (CARE-040)

Created 127 adversarial tests verifying trust framework security properties under active attack scenarios. Tests use real cryptographic operations (NO MOCKING).

**Test categories**:

| Category                   | Tests | What It Verifies                                                      |
| -------------------------- | ----- | --------------------------------------------------------------------- |
| Key extraction resistance  | 26    | Private keys never leak via str/repr/dict/logs/exceptions             |
| Delegation manipulation    | 23    | Tampered signatures, injected delegations, hash chain integrity       |
| Constraint gaming          | 42    | Boundary conditions, type confusion, null constraints, temporal drift |
| Revocation race conditions | 10    | Immediate invalidation, cascade atomicity, concurrent revocations     |
| Cross-org boundaries       | 13    | Foreign org rejection, federation requirements, replay detection      |
| Audit integrity            | 13    | Modified/deleted/injected entries, timestamp manipulation             |

**Run security tests**:

```bash
python -m pytest apps/kailash-kaizen/tests/security/ -v --timeout=120
```

## CI/CD Workflows (CARE-041)

Two GitHub Actions workflows for automated regression and security testing:

- **`.github/workflows/trust-tests.yml`**: Runs all trust unit tests (Core SDK, Kaizen, DataFlow, Nexus) on PRs and weekly (Monday).
- **`.github/workflows/security-tests.yml`**: Runs adversarial security tests on PRs and weekly (Wednesday). 30-day artifact retention.

## Test Coverage

| Fix                    | Tests         | Coverage                                                   |
| ---------------------- | ------------- | ---------------------------------------------------------- |
| Per-Instance Salt      | 25 tests      | Salt uniqueness, key derivation, backward compat           |
| Signature Verification | 13 tests      | Valid/tampered/wrong-key/replay/chain verification         |
| Cycle Detection        | 19 tests      | Direct/indirect/deep cycles, graph validation, performance |
| Max Depth              | 14 tests      | Limits validation, depth calculation, enforcement          |
| Node Trust Gates       | 35 tests      | All execution paths, 6 high-risk types, backward compat    |
| Adversarial Security   | 127 tests     | 6 attack categories, real crypto, NO MOCKING               |
| **Total**              | **233 tests** | Comprehensive security coverage                            |
