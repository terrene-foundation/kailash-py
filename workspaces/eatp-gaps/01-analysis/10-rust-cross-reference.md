# Cross-SDK Gap Analysis: Rust Red Team vs Python EATP

**Date**: 2026-03-15
**Source**: Rust team red team report cross-referenced against Python EATP implementation
**Scope**: All findings from Rust red team evaluated against Python EATP codebase
**Outcome**: 2 findings fixed in Python, 2 Python-specific findings also fixed; all others CLEAN

---

## Summary

The Rust team conducted a red team of the EATP specification and their SDK implementation. Their findings were cross-referenced against the Python EATP SDK. Most Rust findings are CLEAN in Python (different implementation, same spec). Four issues were either confirmed and fixed or identified as Python-specific variants.

---

## Rust Red Team Findings — Python Status

### F1 — Wrong CARE/EATP Acronym

**Rust finding**: Usage of incorrect acronym in documentation and code comments.
**Python status**: CLEAN — already fixed during TM1/TM2 terminology work in TODO-15. All CARE/EATP terminology in Python EATP is aligned with the current spec vocabulary.

---

### F2 — MultiSig Deserialization Bypass

**Rust finding**: `MultiSigPolicy` could be mutated after deserialization, bypassing multi-signature requirements.
**Python status**: FOUND AND FIXED

`MultiSigPolicy` in `packages/eatp/src/eatp/multi_sig.py` was not frozen. A caller could deserialize a `MultiSigPolicy` and then mutate the `required_signers` or `threshold` fields in place, lowering the signature requirement without triggering any validation.

**Fix applied**: `@dataclass(frozen=True)` added to `MultiSigPolicy` class. Post-construction mutation now raises `FrozenInstanceError`. All tests pass.

**File modified**: `packages/eatp/src/eatp/multi_sig.py`

---

### F3 — Hook Exception Propagation

**Rust finding**: Exceptions raised inside hooks could propagate and crash the caller rather than being contained.
**Python status**: CLEAN

`hooks.py` lines 319-331 contains a try/except block that catches all exceptions from hook execution, logs them, and returns a safe failure result. Hook exceptions are properly contained and do not propagate to callers. The Python implementation handles this correctly.

---

### F4 — Key Material Not Zeroized

**Rust finding**: Private key material remains in memory after revocation, accessible via memory inspection.
**Python status**: FOUND AND FIXED

Two issues were identified:

1. `revoke_key()` in `packages/eatp/src/eatp/key_manager.py` marked keys as revoked in metadata but did not remove the key bytes from `self._keys`. The raw key material remained in the dict indefinitely after revocation.

2. In the trust-plane integration code (`packages/trust-plane/src/project.py` and `packages/trust-plane/src/migrate.py`), `register_key()` was called with a `private_key` variable that was not deleted from local scope after the call completed, leaving key material on the call stack longer than necessary.

**Fix applied**:

- `revoke_key()` now clears key material from `self._keys` when revoking: `del self._keys[key_id]`
- `project.py` and `migrate.py` now execute `del private_key` immediately after `register_key()` returns

**Files modified**: `packages/eatp/src/eatp/key_manager.py`, `packages/trust-plane/src/project.py`, `packages/trust-plane/src/migrate.py`

---

### F5 — Circuit Breaker TOCTOU

**Rust finding**: Time-of-check to time-of-use race in circuit breaker state evaluation.
**Python status**: CLEAN

The Python circuit breaker implementation uses `asyncio.Lock()` (for async paths) and `threading.Lock()` (for sync paths, fixed in F-06/TODO-12) to protect state reads and writes atomically. The TOCTOU window identified in the Rust SDK does not exist in the Python implementation due to proper lock usage throughout the state check and update sequence.

---

### F6 — Unbounded Circuit Breaker Registry

**Rust finding**: The circuit breaker registry grows without bound as new agents are registered.
**Python status**: CLEAN — already fixed in G1 work (TODO-13). The Python `PostureCircuitBreaker._failures` per-agent structure is bounded at `maxlen=10000` with oldest-10% trim at capacity. The fix was applied before this cross-reference was conducted.

---

### F7 — Tautological Assertions

**Rust finding**: Test assertions that always pass regardless of the code under test (e.g., `assert x == x`).
**Python status**: CLEAN

Audit of Python EATP test files found no tautological assertions. All test assertions compare the result of the function under test against an independently computed expected value.

---

### F10 — Shadow Enforcer TOCTOU

**Rust finding**: Shadow enforcer reads posture state and then applies enforcement in separate steps without holding a lock across both operations.
**Python status**: CLEAN

The Python shadow enforcer implementation holds its lock across the read-check-apply sequence. The TOCTOU window present in the Rust implementation is not present in Python due to the lock scope being wider.

---

### M-1 — Public Fields Bypass (MultiSig)

**Rust finding**: Public fields on MultiSig policy objects allow post-construction mutation that bypasses the multi-signature requirement.
**Python status**: FOUND AND FIXED — this is the same root cause as F2 above. Covered by the `frozen=True` fix to `MultiSigPolicy`.

---

### Terrene Naming

**Rust finding**: Internal Terrene Foundation naming in SDK surface (organization-internal names exposed in public API).
**Python status**: CLEAN

Python EATP public API surface uses only EATP-specification terminology. Terrene Foundation references are confined to SPDX license headers (`# Copyright 2026 Terrene Foundation`) which are not part of the SDK API surface.

---

## Python-Specific Findings Fixed

These issues were identified during the Python cross-reference review and are not present in the Rust SDK. They are Python-specific security improvements made alongside the Rust finding review.

### P-H1 — Non-Constant-Time Hash Comparison

**Location**: `packages/trust-plane/src/delegation.py:399`, `packages/trust-plane/src/project.py:935`
**Severity**: HIGH (timing side-channel)

Both locations used `==` for comparing hash or digest values. Per EATP security conventions and `rules/eatp.md`, all signature and digest comparisons must use `hmac.compare_digest()` to prevent timing side-channel attacks.

**Fix applied**: Both occurrences replaced with `hmac.compare_digest()`.

**Files modified**: `packages/trust-plane/src/delegation.py`, `packages/trust-plane/src/project.py`

---

### P-H2 — Private Key Material Not Deleted from Local Scope

**Location**: `packages/trust-plane/src/project.py`, `packages/trust-plane/src/migrate.py`
**Severity**: HIGH (key material exposure)

After calling `register_key()`, the local `private_key` variable was not explicitly deleted. This leaves key material on the Python call stack and in local variable scope until the garbage collector reclaims it, unnecessarily extending the window during which key material is accessible via memory inspection or heap dumps.

**Fix applied**: `del private_key` added immediately after `register_key()` returns in both files. This is documented as a best-effort mitigation — Python does not guarantee immediate memory zeroing — but it closes the obvious leak window.

**Files modified**: `packages/trust-plane/src/project.py`, `packages/trust-plane/src/migrate.py`

**Note**: P-H2 is related to F4 (key material not zeroized) and was fixed in the same pass. The distinction is that F4 covers the key manager's internal storage, while P-H2 covers the caller's local variable scope.

---

## Summary Table

| Finding        | Description                       | Python Status | Action                                                                 |
| -------------- | --------------------------------- | ------------- | ---------------------------------------------------------------------- |
| F1             | Wrong CARE/EATP acronym           | CLEAN         | None (already fixed in TM1/TM2)                                        |
| F2             | MultiSig deserialization bypass   | FIXED         | `frozen=True` on `MultiSigPolicy`                                      |
| F3             | Hook exception propagation        | CLEAN         | None (hooks.py:319-331 correct)                                        |
| F4             | Key material not zeroized         | FIXED         | `revoke_key()` clears `self._keys`; trust-plane adds `del private_key` |
| F5             | Circuit breaker TOCTOU            | CLEAN         | None (asyncio.Lock covers state transitions)                           |
| F6             | Unbounded CB registry             | CLEAN         | None (already fixed in G1 work)                                        |
| F7             | Tautological assertions           | CLEAN         | None                                                                   |
| F10            | Shadow enforcer TOCTOU            | CLEAN         | None (lock scope is wider in Python)                                   |
| M-1            | Public fields bypass              | FIXED         | Same fix as F2 (`frozen=True`)                                         |
| Terrene naming | Internal naming in public API     | CLEAN         | None (SPDX headers only)                                               |
| P-H1           | Non-constant-time hash comparison | FIXED         | `hmac.compare_digest()` in delegation.py, project.py                   |
| P-H2           | Private key scope not cleaned     | FIXED         | `del private_key` in project.py, migrate.py                            |

---

## Test Evidence

All fixes verified against the full test suite: **2715 tests passed, 0 failed** at time of completion (2026-03-15).

The test baseline at the start of the red team phase was 2436 tests. The increase to 2715 reflects new tests added across todos 09-16 (279 new test cases).

---

## Files Modified

- `packages/eatp/src/eatp/multi_sig.py` — F2/M-1: `frozen=True` on `MultiSigPolicy`
- `packages/eatp/src/eatp/key_manager.py` — F4: `revoke_key()` clears key material from `self._keys`
- `packages/trust-plane/src/delegation.py` — P-H1: `hmac.compare_digest()` at line 399
- `packages/trust-plane/src/project.py` — F4, P-H1, P-H2: key material cleanup + constant-time comparison
- `packages/trust-plane/src/migrate.py` — F4, P-H2: `del private_key` after `register_key()`
