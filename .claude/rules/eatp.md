# EATP SDK Rules

## Scope

These rules apply when editing `src/kailash/trust/**` files (excluding `plane/`)

## SDK Conventions

### Dataclasses

- Use `@dataclass` (NOT Pydantic) for all data types
- Every `@dataclass` MUST have `to_dict()` → `Dict[str, Any]` and `@classmethod from_dict()` → Self
- Enums serialize as `.value`, datetimes as `.isoformat()`

### Module Structure

- `from __future__ import annotations` in every module
- `# Copyright 2026 Terrene Foundation` + `# SPDX-License-Identifier: Apache-2.0` header
- `logger = logging.getLogger(__name__)` in every module
- Explicit `__all__` in every module
- `str`-backed `Enum` classes for JSON-friendly serialization

### Error Handling

- All errors MUST inherit from `TrustError` (in `eatp.exceptions`)
- All errors MUST include `.details: Dict[str, Any]` parameter
- Fail-closed: unknown/error states → deny, NEVER silently permit

### Cryptography

- Ed25519 is the mandatory signing algorithm
- HMAC is optional overlay (HMAC alone is NEVER sufficient for external verification)
- Constant-time comparison via `hmac.compare_digest()` — NEVER use `==` for signature comparison
- AWS KMS uses ECDSA P-256 (Ed25519 not available in KMS) — document the algorithm mismatch

### Trust Model

- Monotonic escalation only: AUTO_APPROVED → FLAGGED → HELD → BLOCKED (never downgrade)
- Bounded collections: `maxlen=10000`, trim oldest 10% at capacity
- `None` role = all-access (backward-compatible, no RBAC enforcement)

### Cross-SDK Alignment

- Both Python and Rust SDKs implement the spec independently (D6)
- Convention names may differ (Python snake_case vs Rust snake_case) but semantics MUST match
- New spec-level concepts require Rust team coordination before implementation
