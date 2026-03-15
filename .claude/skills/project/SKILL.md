# TrustPlane Project Skills

Skills specific to the TrustPlane EATP reference implementation (`packages/trust-plane/`).

## Available Skills

| Skill | File | Description |
|-------|------|-------------|
| Store Backend Implementation | [store-backend-implementation.md](store-backend-implementation.md) | Step-by-step guide for adding new TrustPlaneStore backends with 6-requirement security contract |
| Security Patterns | [trust-plane-security-patterns.md](trust-plane-security-patterns.md) | 11 hardened security patterns validated through 14 rounds of red teaming |
| Enterprise Features | [trust-plane-enterprise-features.md](trust-plane-enterprise-features.md) | RBAC, OIDC, SIEM, Dashboard, Archive, Shadow mode, Cloud KMS reference |

## When to Use

- **Adding a new store backend** → Store Backend Implementation
- **Reviewing security-sensitive trust-plane code** → Security Patterns
- **Working with enterprise features** → Enterprise Features
- **Understanding the EATP protocol** → See `skills/26-eatp-reference/` instead

## Cross-References

- `packages/trust-plane/CLAUDE.md` — Full authoritative reference (loaded automatically)
- `skills/26-eatp-reference/` — EATP protocol and SDK reference
- `agents/standards/eatp-expert.md` — EATP expert agent
