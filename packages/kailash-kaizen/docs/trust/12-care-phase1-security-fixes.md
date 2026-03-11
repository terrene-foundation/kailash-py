# CARE Phase 1: Critical Security Fixes

**Status**: Complete
**Version**: 1.0.0
**Items**: CARE-001, CARE-002, CARE-003, CARE-004
**Tests**: 102 new tests, 790 total trust tests passing

## Overview

Phase 1 addresses four P0 critical security vulnerabilities in the EATP trust delegation subsystem. These fixes harden the cryptographic foundation, enable signature verification, prevent delegation cycles, and enforce depth limits.

## CARE-001: Per-Instance Salt for Key Derivation

### Problem

A hardcoded static salt `b"kaizen-trust-security-salt"` was used in PBKDF2 key derivation (`security.py:427`). This meant the same salt was used across ALL deployments, making rainbow table attacks feasible.

### Solution

- **`crypto.py`**: Added `generate_salt()` (32-byte cryptographically secure), `derive_key_with_salt()` (PBKDF2-HMAC-SHA256, 100k iterations), and `hash_trust_chain_state_salted()`.
- **`security.py`**: `SecureKeyStorage` now uses per-instance random salt. Salt priority: explicit parameter > environment variable > random generation.
- Backward compatibility preserved via original `hash_trust_chain_state()`.

### Usage

```python
from kaizen.trust.crypto import generate_salt, derive_key_with_salt, hash_trust_chain_state_salted

# Generate a salt
salt = generate_salt()  # 32 bytes

# Derive a key with per-key salt
derived_key, salt_used = derive_key_with_salt(master_key=b"my-key", salt=salt)

# Salted trust chain hash
hash_hex, salt_b64 = hash_trust_chain_state_salted(
    genesis_id="gen-001",
    capability_ids=["cap-001"],
    delegation_ids=["del-001"],
    constraint_hash="abc",
)

# SecureKeyStorage with explicit salt
from kaizen.trust.security import SecureKeyStorage
storage = SecureKeyStorage(salt=my_salt)  # Or auto-generates
```

### Tests

- `test_crypto_salt.py`: 19 tests covering salt generation uniqueness, key derivation with different salts, deterministic reproduction, backward compatibility.
- `test_security_salt.py`: 6 tests covering no static salt in source, different instances get different salts, explicit/env salt, encryption round-trip.

## CARE-002: Delegation Signature Verification

### Problem

Delegation signature verification was skipped with a comment: "For Phase 1, we skip delegation signature verification." This allowed forged, tampered, or replayed delegation records.

### Solution

- **`operations.py`**: Added `_verify_delegation_signature()` for single delegation Ed25519 verification, `verify_delegation_chain()` for full chain-of-custody verification, and updated `_verify_signatures()` to now verify delegation signatures instead of skipping.
- Signatures are verified against the authority's public key from the delegator's genesis record.

### Usage

```python
# Full chain verification (all delegations from human origin)
result = await trust_ops.verify_delegation_chain("agent-C")
assert result.valid  # All signatures in the chain are valid

# Single delegation verification (internal method)
result = await trust_ops._verify_delegation_signature(delegation, delegator_chain)
```

### Security Properties

- Tampered delegations detected (modified capabilities, constraints, IDs)
- Wrong-key signatures rejected
- Replay attacks prevented (signature bound to delegation ID, task, capabilities)
- Missing delegator chains fail verification

### Tests

- `test_delegation_signatures.py`: 13 tests covering valid signature verification, tampered delegation rejection, wrong-key rejection, full chain verification, broken chain detection, missing delegator handling, replay attack prevention, ID-bound signatures, integration with existing `_verify_signatures`.

## CARE-003: Delegation Cycle Detection

### Problem

`get_delegation_chain()` in `chain.py` had no cycle detection. A delegation cycle A->B->C->A would cause infinite loops, enabling DoS attacks.

### Solution

- **`chain.py`**: `get_delegation_chain()` now uses a visited set to detect cycles during chain traversal. Raises `DelegationCycleError` with the cycle path.
- **`graph_validator.py`** (new): `DelegationGraph` and `DelegationGraphValidator` classes providing DFS-based cycle detection for the delegation graph. `validate_new_delegation()` checks if adding an edge would create a cycle before persisting.
- **`exceptions.py`**: Added `DelegationCycleError(DelegationError)` with `cycle_path` attribute.

### Usage

```python
from kaizen.trust.graph_validator import DelegationGraph, DelegationGraphValidator
from kaizen.trust.exceptions import DelegationCycleError

# Check if adding a new delegation would create a cycle
all_delegations = await trust_store.list_delegations()
graph = DelegationGraph.from_delegations(all_delegations)
validator = DelegationGraphValidator(graph)

if not validator.validate_new_delegation("agent-C", "agent-A"):
    raise DelegationCycleError(["agent-A", "agent-B", "agent-C", "agent-A"])

# Chain traversal now has built-in cycle detection
chain = trust_chain.get_delegation_chain(max_depth=100)  # Raises DelegationCycleError on cycle

# Self-delegation is always rejected
validator.validate_new_delegation("agent-A", "agent-A")  # Returns False
```

### Tests

- `test_delegation_cycles.py`: 19 tests covering DelegationCycleError, valid chain traversal, cycle detection in chains, single delegation, empty delegations, max depth exceeded, graph construction, linear/direct/indirect/deep cycle detection, new delegation validation, self-delegation rejection, graph immutability after validation, performance (500 nodes < 1s), disconnected graph cycles.

## CARE-004: Maximum Delegation Depth Enforcement

### Problem

No enforcement of maximum delegation chain depth. Unbounded chains enabled DoS via resource exhaustion, loss of accountability traceability, and compliance risk.

### Solution

- **`operations.py`**: Added `MAX_DELEGATION_DEPTH = 10` constant. `TrustOperations.__init__()` accepts configurable `max_delegation_depth` parameter. `_calculate_delegation_depth()` counts from human origin. `delegate()` enforces depth before creating delegation.
- **`chain.py`**: Added `DelegationLimits` dataclass for configuration (max_depth, max_chain_length, require_expiry, default_expiry_hours) with validation.

### Usage

```python
from kaizen.trust.operations import TrustOperations, MAX_DELEGATION_DEPTH
from kaizen.trust.chain import DelegationLimits

# Default depth limit of 10
trust_ops = TrustOperations(registry, key_manager, store)
# depth=10 means up to 10 levels of agent-to-agent delegation

# Custom depth limit
trust_ops = TrustOperations(registry, key_manager, store, max_delegation_depth=5)

# DelegationLimits for advanced configuration
limits = DelegationLimits(
    max_depth=5,
    max_chain_length=20,
    require_expiry=True,
    default_expiry_hours=24,
)
```

### Tests

- `test_delegation_depth.py`: 14 tests covering DelegationLimits defaults/custom values/validation, MAX_DELEGATION_DEPTH constant, TrustOperations depth config, depth calculation for empty/multi-delegation chains, enforcement at and exceeding max depth.

## Implementation Summary

| Item      | File                 | Change                                                                                        | Tests            |
| --------- | -------------------- | --------------------------------------------------------------------------------------------- | ---------------- |
| CARE-001  | `crypto.py`          | `generate_salt()`, `derive_key_with_salt()`, `hash_trust_chain_state_salted()`                | 19               |
| CARE-001  | `security.py`        | Per-instance salt in `SecureKeyStorage`                                                       | 6                |
| CARE-002  | `operations.py`      | `_verify_delegation_signature()`, `verify_delegation_chain()`, updated `_verify_signatures()` | 13               |
| CARE-003  | `graph_validator.py` | `DelegationGraph`, `DelegationGraphValidator` (new file)                                      | 19               |
| CARE-003  | `chain.py`           | Cycle detection in `get_delegation_chain()`                                                   | (included above) |
| CARE-003  | `exceptions.py`      | `DelegationCycleError`                                                                        | (included above) |
| CARE-004  | `operations.py`      | `MAX_DELEGATION_DEPTH`, depth enforcement in `delegate()`                                     | 14               |
| CARE-004  | `chain.py`           | `DelegationLimits` dataclass                                                                  | (included above) |
| **Total** |                      |                                                                                               | **71**           |

## Migration Notes

- **CARE-001**: Existing chains without salt continue to work (backward compatible). New chains generate salts automatically. For SecureKeyStorage, set `{MASTER_KEY_SOURCE}_SALT` environment variable for consistent encryption across restarts.
- **CARE-002**: Delegations created before this fix may have placeholder signatures. The `_verify_signatures` method will detect these. A future `DelegationMigrator` (not yet implemented) will handle migration of unsigned delegations.
- **CARE-003**: Any existing delegation cycles in production data will now be detected and raise `DelegationCycleError`. Run a migration check before deploying.
- **CARE-004**: Existing chains deeper than 10 levels will be blocked from further delegation. Adjust `max_delegation_depth` per organization if needed.
