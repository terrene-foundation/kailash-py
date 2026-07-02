# CONNECTION — Gate productionizes spec-compliance SKILL.md; converges 4 rule families

**Date:** 2026-04-26
**Phase:** /analyze
**Workspace:** spec-drift-gate

## Connection

The Spec Drift Gate is the executable form of `.claude/skills/spec-compliance/SKILL.md`. The skill documents the protocol; the gate is the runnable enforcement. This is the second time COC has produced a "skill → executable form" pair — the first was `skills/16-validation-patterns/orphan-audit-playbook.md` → `/redteam` mechanical sweeps. The pattern: protocol-level documentation in skills/, executable enforcement in scripts/ + pre-commit + CI.

The gate also unifies four cross-cutting rule families that were previously enforced agent-side only:

| Rule family                                  | What it requires                                                                 | Gate FR              |
| -------------------------------------------- | -------------------------------------------------------------------------------- | -------------------- |
| `rules/specs-authority.md` § 5, § 5b, § 5c   | First-instance updates; full-sibling re-derivation; orchestrator amend-at-launch | FR-1..FR-8           |
| `rules/orphan-detection.md` MUST 6           | Module-scope public imports appear in `__all__`                                  | FR-6                 |
| `rules/facade-manager-detection.md` MUST 1+2 | Manager-shape classes have a Tier-2 wiring test at predictable path              | FR-7                 |
| `rules/zero-tolerance.md` Rule 3a            | Typed-guard pattern for None-backing delegates → reusable as fix-hint format     | ADR-6 fix-hint shape |

Each rule, in isolation, was enforced via `/redteam` mechanical sweeps (agent-driven, run only when audits convene). The gate converges them at PR time, mechanically, without an agent in the loop.

## Why this matters

Skills are the COC layer for institutional knowledge that scales linearly with documentation effort. Executable forms are the layer for institutional knowledge that scales O(1) — once shipped, every future PR benefits. The skill→executable pattern is how high-value protocols escape the agent-driven audit cadence and become permanent infrastructure.

## Implication for future work

When a `/redteam` mechanical sweep is run by hand more than 3 times across audit cycles, that's the signal it should become an executable form. Today: the orphan-audit-playbook + spec-compliance skills are the two clear candidates that have been productionized. Likely future candidates: cross-CLI parity drift audit (`rules/cross-cli-parity.md`), worktree isolation enforcement (`rules/worktree-isolation.md`), facade-manager wiring (already in scope at FR-7).

## References

- `01-analysis/02-requirements-and-adrs.md` § 10 Cross-References — explicit gate→skill linkage
- `specs/spec-drift-gate.md` § 9 Cross-References — bidirectional linkage
- `.claude/skills/spec-compliance/SKILL.md` — the protocol the gate productionizes
- `.claude/skills/16-validation-patterns/orphan-audit-playbook.md` — sibling skill, M2 audit pattern
