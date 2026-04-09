---
paths:
  - "**/trust/**"
  - "**/eatp/**"
---

# EATP SDK Rules

## Scope

These rules apply when working with EATP trust code.

## SDK Conventions

### Dataclasses

- Use `@dataclass` (NOT Pydantic) for all data types
- Every `@dataclass` MUST have `to_dict()` → `Dict[str, Any]` and `@classmethod from_dict()` → Self
- Enums serialize as `.value`, datetimes as `.isoformat()`

**Why:** Missing `to_dict()`/`from_dict()` makes trust records non-serializable, breaking audit logging, wire transfer, and persistence.

### Module Structure

- `from __future__ import annotations` in every module
- `# Copyright 2026 Terrene Foundation` + `# SPDX-License-Identifier: Apache-2.0` header
- `logger = logging.getLogger(__name__)` in every module
- Explicit `__all__` in every module
- `str`-backed `Enum` classes for JSON-friendly serialization

**Why:** Missing `__all__` exposes internal symbols on `import *`, and non-str Enums produce integer values in JSON that downstream consumers cannot interpret.

### Error Handling

- All errors MUST inherit from `TrustError` (in `eatp.exceptions`)
- All errors MUST include `.details: Dict[str, Any]` parameter

**Why:** Non-`TrustError` exceptions bypass trust-layer catch blocks, causing unhandled crashes instead of structured denial.

- Fail-closed: unknown/error states → deny, NEVER silently permit

**Why:** A fail-open default means any bug in trust evaluation silently grants access, turning errors into security bypasses.

### Cryptography

- Ed25519 is the mandatory signing algorithm
- HMAC is optional overlay (HMAC alone is NEVER sufficient for external verification)
- Constant-time comparison via `hmac.compare_digest()` — NEVER use `==` for signature comparison
- AWS KMS uses ECDSA P-256 (Ed25519 not available in KMS) — document the algorithm mismatch

**Why:** Using `==` for signature comparison leaks timing information, enabling attackers to forge valid signatures byte by byte.

### Trust Model

- Monotonic escalation only: AUTO_APPROVED → FLAGGED → HELD → BLOCKED (never downgrade)

**Why:** Allowing trust level downgrades means a compromised component can reset its own restriction, defeating the entire escalation model.

- Bounded collections: `maxlen=10000`, trim oldest 10% at capacity

**Why:** Unbounded collections cause memory exhaustion in long-running trust services, crashing the entire trust plane.

- `None` role = all-access (backward-compatible, no RBAC enforcement)

### Cross-SDK Alignment

- Both Python and Rust SDKs implement the spec independently (D6)
- Convention names may differ (Python snake_case vs Rust snake_case) but semantics MUST match
- New spec-level concepts require Rust team coordination before implementation

**Why:** Semantic divergence between SDKs means trust records produced by one cannot be verified by the other, breaking cross-language interoperability.
