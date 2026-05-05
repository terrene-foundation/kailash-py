# RISK: PR-Sequencing Constraint Anchors `specs/kaizen-tools.md` Creation Timing

**Date:** 2026-05-04
**Phase:** /todos
**Severity:** MEDIUM — sequencing-violation cost is one PR rewind + one re-review cycle

## Context

The architecture plan splits Issue #814 into two PRs:

- **PR A** = Shard 1 (type-safety sweep — todos 1.1–1.5)
- **PR B** = Shard 2 (orphan + dep cleanup + release-prep — todos 2.1–2.6)

Todo 2.3 creates `specs/kaizen-tools.md` documenting the BaseTool override conformance
pattern (`async def execute(self, *, ..., **kwargs: Any)`). The spec MUST sequence AFTER
PR A merges to main, per `rules/spec-accuracy.md` Rule 5 ("Incremental Spec Extension Is
The Workflow" — spec content describes only behavior already shipped on `main`).

## The Risk

If `/implement` opens PR B before PR A merges:

- 17 of 18 BaseTool subclasses are still non-conformant on main.
- `specs/kaizen-tools.md` § "Subclass Conformance Pattern" cites the conforming pattern
  as the contract.
- Per `rules/spec-accuracy.md` Rule 1 (citation resolution against working code), the
  spec contains phantom citations — at least 17 subclasses' `execute()` signatures do
  NOT match the spec's claimed pattern.
- The /redteam audit protocol from `rules/spec-accuracy.md` § Audit Protocol would
  surface the drift as CRITICAL → block PR B.
- Recovery: amend PR A first, wait for merge, then rebase PR B → 1+ PR rewind.

## Mitigation Already Applied

The risk is structurally mitigated in three places in the workspace:

1. **Architecture plan § Specs** (`02-plans/01-architecture.md`) explicitly notes:

   > "Spec creation is deferred to a follow-up PR after Shard 1 lands"
   > AND
   > "Writing `specs/kaizen-tools.md` now would document a contract that 17 of 18
   > subclasses violate today."

2. **Todo 2.3 § Sequencing constraint (CRITICAL)** spells out the exact dependency:

   > "If PR B opens before PR A merges, this todo is BLOCKED. The orchestrator MUST
   > sequence: 1) PR A merges to main, 2) PR B opens."

3. **Todo 2.6 § Dependencies** restates the constraint at the closing PR-management todo:
   > "PR A must already have merged (sequencing constraint per `rules/spec-accuracy.md`
   > Rule 5)."

The triple-redundancy is intentional — `/implement` reads the architecture plan + the
specific todo + the closing todo. If the sequencing requirement is missed in any one
location, the next two surfaces should catch it.

## Why This Is Worth Journaling

Cross-PR sequencing constraints are the highest-cost-to-recover-from class of /todos
oversights. Capacity-budget violations surface mid-implement and shard-rebase is cheap;
sequencing violations surface at red-team and force a PR rewind. The `kailash-ml-audit
2026-04-23` W32-32b amend-at-launch evidence in `rules/specs-authority.md` Rule 5c
documents the same failure mode in a different form (todo claims version that already
shipped → agent burns budget on a stale-amendment cycle).

The general lesson — "if a todo describes spec content, it implicitly depends on the
code-completion of every cited symbol" — applies to every /analyze that produces both
typing-fix shards AND a spec extension. Future workstreams that follow this pattern
should bake in the same triple-redundancy.

## Cross-Reference

- `rules/spec-accuracy.md` Rule 5 (Incremental Spec Extension Is The Workflow)
- `rules/specs-authority.md` Rule 5c (Amend-At-Launch protocol — extends this risk to
  todo claims about version + symbol counts)
- `02-plans/01-architecture.md` § Specs
- `todos/active/2.3-create-spec-kaizen-tools.md` § Sequencing constraint (CRITICAL)
- `todos/active/2.6-pr-b-open-and-merge.md` § Dependencies
