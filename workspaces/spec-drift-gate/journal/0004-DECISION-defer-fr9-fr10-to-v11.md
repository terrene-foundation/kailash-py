# DECISION — Defer FR-9 (MOVE shim) + FR-10 (sibling re-derivation) to v1.1

**Date:** 2026-04-26
**Phase:** /todos
**Workspace:** spec-drift-gate

## Decision

FR-9 (MOVE shim verification) and FR-10 (cross-spec sibling re-derivation advisory) are deferred from v1.0 to v1.1 of the spec-drift-gate. The 18-atomic-todo plan covers FR-1 through FR-8 + FR-11 + FR-12 + FR-13. FR-9 + FR-10 move to spec § 11.7 + § 11.8 (Deferred to M2 milestone — but sub-numbered for v1.1, not M2 proper).

## Why

Three reasons converged on the deferral:

1. **Audit-pattern coverage:** the W5 portfolio audit + W6.5 spec realignment surfaced 13 of 36 HIGH findings via FR-1, FR-2, FR-4, FR-7. Zero findings of these audits were FR-9-class (MOVE shim) or FR-10-class (sibling drift advisory). v1.0 catches the patterns the gate's existence is justified by; FR-9 + FR-10 catch a different, less-prevalent class.
2. **S2 capacity budget:** including FR-9 (~30 LOC) + FR-10 (~50 LOC) pushes S2 from 250 → 330 LOC, still within autonomous budget but reducing focus on the day-1 CRIT (B1 `__getattr__` resolution) — the load-bearing risk per failure-points Top-5.
3. **Advisory-class:** FR-10 is explicitly advisory (WARN, not block) per `02-requirements-and-adrs.md` § 1 FR-10. Advisory checks defer cleanly without weakening the gate's blocking enforcement.

## Alternatives considered

- **Ship in v1.0 anyway:** extends S2 to 330 LOC. Reviewer flagged as the equally-valid alternative. Rejected because the marginal coverage of 2 advisory FRs doesn't justify the focus dilution on day-1 CRIT mitigation.
- **Spec → drop, plan → drop, never ship:** rejected because both are real disciplines from `rules/specs-authority.md` § 5b; deferring keeps them on the roadmap.

## Consequences

- v1.0 ships covering 80% of the audit-pattern surface (8/8 day-1-critical FRs).
- FR-9 + FR-10 land in v1.1 once v1.0 has stabilized (~3 months post-v1.0 ship).
- Failure-points § Top-5 D5 (gate vs /redteam authority) remains an /redteam concern in v1.0 — sibling re-derivation runs at audit time, not PR time.

## Verification at /implement complete

After SDG-602 ships, verify:

- `grep FR-9 specs/spec-drift-gate.md` shows entries only in § 4 row (deferred-marker) and § 11.7 (deferred section)
- `grep FR-10 specs/spec-drift-gate.md` shows entries only in § 4 row (deferred-marker) and § 11.8

## References

- Plan: `02-plans/01-implementation-plan.md` § 3 S2 (deferred section)
- Redteam: `04-validate/00-analyze-redteam.md` § 4 PLAN-CRIT-1 disposition
- Spec: `specs/spec-drift-gate.md` § 11.7, § 11.8
