---
id: W6-008
title: JWTValidator.from_nexus_config() — implement OR delete from spec
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-C-25
severity: HIGH
spec: specs/nexus-ml-integration.md
domain: nexus-ml
specialist: nexus-specialist
wave: W3
---

## Why

W5-C finding F-C-25: `JWTValidator.from_nexus_config()` classmethod is named in `specs/nexus-ml-integration.md` but absent from `kailash.trust.auth.jwt::JWTValidator`. Public-API divergence.

## What changes

**Audit step:**
- `grep -rn "from_nexus_config" packages/`
- Determine: does any production code (Nexus presets, ml-endpoints mount) attempt to call this?

**If YES:**
- Implement the classmethod with the spec-described signature
- Add Tier-2 test exercising via Nexus config

**If NO:**
- Remove from spec § JWTValidator construction patterns
- Document in spec that JWTValidator is constructed directly with `JWTConfig`

## Capacity check

- LOC: ~150 (impl path) or ~50 (spec-update path)
- Invariants: 3 (signature match, secret-source precedence, spec compliance)
- Call-graph hops: 2
- Describable: "Audit nexus consumers of from_nexus_config; either implement or strip from spec."

## Spec reference

- `specs/nexus-ml-integration.md`
- `specs/security-auth.md` § JWTValidator

## Acceptance

- [ ] Audit findings documented in PR body
- [ ] Spec + code aligned
- [ ] If implemented: Tier-2 test in `packages/kailash/tests/integration/test_jwt_from_nexus_config.py`
- [ ] CHANGELOG entry if behavior change

## Dependencies

- None

## Related

- Finding detail: `04-validate/W5-C-findings.md` F-C-25
