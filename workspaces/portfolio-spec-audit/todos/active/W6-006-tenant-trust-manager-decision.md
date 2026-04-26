---
id: W6-006
title: TenantTrustManager — wire OR delete (orphan-detection §3)
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-B-05
severity: HIGH
spec: specs/dataflow-core.md
domain: dataflow
specialist: dataflow-specialist
wave: W2
---

## Why

W5-B finding F-B-05: `TenantTrustManager` is exposed publicly but has no production hot-path call site. This is `rules/orphan-detection.md` § 1 — a public-surface manager class that the framework never invokes is dead code that misleads consumers.

## What changes

**Audit step (specialist runs first):**
- `grep -rn "TenantTrustManager\|tenant_trust_manager\|trust_executor"` in `packages/kailash-dataflow/src/dataflow/`
- Determine: does ANY production hot-path (`express.list`, `express.read`, etc.) reach this class?

**If YES (call site exists, just untested):**
- Add Tier-2 wiring test per `rules/facade-manager-detection.md` MUST 1
- Update spec to cite the verified call site

**If NO (true orphan):**
- DELETE the public-surface attribute (`db.tenant_trust_manager` or wherever it's exposed)
- DELETE the manager class itself
- Sweep imports per `rules/orphan-detection.md` Rule 4
- Update spec to remove the claim

## Capacity check

- LOC: ~200 (deletion-heavy if delete; ~150 if wire)
- Invariants: 5 (orphan-detection §1 compliance, audit, classification, redaction, tenant_id)
- Call-graph hops: 3
- Describable: "Audit TenantTrustManager call sites; either wire+test or delete."

## Spec reference

- `specs/dataflow-core.md`
- `rules/orphan-detection.md` § 1, § 3
- `rules/facade-manager-detection.md` § 1

## Acceptance

- [ ] Decision documented in PR body with grep evidence
- [ ] If wire: Tier-2 wiring test exists, spec cites call site
- [ ] If delete: file removed, imports swept, spec claim removed
- [ ] CHANGELOG entry

## Dependencies

- None

## Related

- Finding detail: `04-validate/W5-B-findings.md` F-B-05
