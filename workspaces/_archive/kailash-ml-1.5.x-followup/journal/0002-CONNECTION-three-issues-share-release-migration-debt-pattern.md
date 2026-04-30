# 0002 — CONNECTION — Three Issues Share One Failure Pattern: 1.5.x Release Migration Debt

**Type:** CONNECTION
**Date:** 2026-04-28
**Phase:** /analyze
**Workstream:** kailash-ml-1.5.x-followup

## The pattern

Issues #699, #700, #701 surfaced same day from MLFP M5 notebook smoke-test against kailash-ml 1.5.1. They look like three independent bugs. They are three faces of one failure pattern:

> The 1.5.x release shipped a public-API restructure without preserving the migration discipline that the prior releases had implicitly relied on. Three different parts of the same release each lost a different invariant.

| Issue | Lost invariant                                                             | Symptom                                                            |
| ----- | -------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| #699  | DDL lives in migrations, NOT inline application code                       | Two writers, two schemas, IF-NOT-EXISTS no-op masks the failure    |
| #700  | Public-API removal requires deprecation cycle with shim + CHANGELOG path   | Hard `TypeError` on every 1.1.x callsite, no migration hint        |
| #701  | Documented kwarg has effect; documented `kind` literal has dispatch branch | Silent-drop `data=`; 4 `kind` literals fall through to DL silently |

Each invariant is encoded somewhere in the rules family:

- #699 → `rules/schema-migration.md` Rule 1 (DDL outside migrations BLOCKED) + `rules/zero-tolerance.md` Rule 4 (no workarounds)
- #700 → no current rule encodes deprecation discipline (codify candidate)
- #701 → `rules/zero-tolerance.md` Rule 3 (silent fallbacks) + Rule 2 (stubs / fake X)

**The connection:** none of the three rules fired during 1.5.0 / 1.5.1 release because no `/redteam` audit ran the mechanical sweeps that would have caught them. Per `rules/agents.md` MUST § "Reviewer Prompts Include Mechanical AST/Grep Sweep", the audit needs to grep:

- `CREATE TABLE` outside `migrations/` directories (catches #699 class)
- public-symbol removals without a `DeprecationWarning` shim added in same PR (catches #700 class)
- `Literal[...]`-typed parameters whose dispatcher misses branches (catches #701 + bonus class)

Each grep is bounded (≤4 seconds); each catches a class of bug that LLM-judgment review will miss because it scans the diff, not the absolute state.

## Connection to prior workstreams

This is the **third Azure-class / production-incident workstream in 16 days** — but viewed through the migration-debt lens, it's the second of TWO migration-debt workstreams:

| Date       | Workstream             | Pattern                                                   |
| ---------- | ---------------------- | --------------------------------------------------------- |
| 2026-04-12 | arbor-upstream-fixes   | Multi-tenant DataFlow + Azure (lifecycle + tenant fork)   |
| 2026-04-19 | issue #525             | Cross-SDK execute_raw + Postgres bind (signature drift)   |
| 2026-04-28 | dataflow-prod-incident | DDL retry storm + pool fallback leak (lifecycle + Rule 3) |
| 2026-04-28 | **kailash-ml-1.5.x**   | **Release migration debt (this workspace)**               |

The `dataflow-prod-incident` codify cycle (closed today, before this workspace opened) introduced `rules/zero-tolerance.md` Rule 3b "bounded + tracked + surfaced" — a 3-axis test for ANY framework method that continues past an error condition. The Rule 3b grid would have caught #701's silent `data=` drop AND the 4 unhandled `kind` literals immediately: bounded? NO (no validation). tracked? NO (no metric on dispatch). surfaced? NO (no log). Three NOs = same failure pattern.

## Implications

1. **Rule 3b just-shipped is already paying off** — it would have caught #701 if it had been live in 1.5.0. Confidence the 3-axis test is the right shape goes up.
2. **The mechanical-sweep gap is the structural root cause**. Rules exist; sweeps to enforce them at /redteam don't. Codify candidate § 2 (audit protocol extension) is the highest-leverage codification.
3. **This is the third dispatch-grid bug in 6 months** (#699 schema, #701 kind dispatch, #525 execute_raw signature). Different surfaces, same fault: a public surface accepts something it cannot fulfill, and the failure is silent. Worth a meta-rule cross-reference.

## Codify implications

The connection above maps directly to codify candidates 1–5 (`02-plans/03-codify-candidates.md`). The CONNECTION lens makes the grouping coherent: candidate 1 (deprecation discipline) + candidate 2 (DDL-outside-migrations grep) + candidate 5 (fake-dispatch grep) are three facets of one institutional learning — **mechanical sweeps as the structural defense against release migration debt**.

## References

- `02-plans/01-architecture-plan.md` (three ADRs)
- `02-plans/03-codify-candidates.md` (5 codify candidates)
- `workspaces/dataflow-prod-incident/journal/0007-DECISION-codify-cycle-rule-extensions.md` (Rule 3b origin, 2026-04-28 sibling workstream)
- `rules/zero-tolerance.md` Rule 3b (bounded + tracked + surfaced — just shipped)
- `rules/agents.md` MUST § Mechanical AST/Grep Sweep (the missing /redteam piece)
