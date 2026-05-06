---
type: CONNECTION
date: 2026-05-04
author: agent
project: dataflow-engine-pyright-cleanup
topic: 22 of 56 warnings (W1+W3) collapse to one fix class — Optional → typed parameter narrowing
phase: analyze
tags: [pyright, warning-taxonomy, sharding, autonomous-execution-rule-2]
---

# CONNECTION: 22 of 56 warnings collapse to one fix class (Optional → typed parameter narrowing)

**Surfaced by:** Warning categorization (W1 + W3 grouping)

## The connection

Two warning classes from `02-warning-categorization.md` look superficially distinct:

- **W1 (12 warnings):** `Argument of type "Any | None" cannot be assigned to parameter "X" of type "str"/"int" in function "build_connection_string"`
- **W3 (10 warnings):** `Expression of type "None" cannot be assigned to parameter of type "str"/"Dict[str, List[str]]"`

Both are the same root cause at different surfaces: caller has an `Optional[T]` value, callee declares non-`Optional[T]`. The 12 W1 warnings happen at `build_connection_string` call sites; the 10 W3 warnings happen at other typed-helper call sites.

Together: **22 of 56 warnings (39% of the warning surface)** close with one mechanical fix pass.

## Why this collapses to one shard

Per `rules/autonomous-execution.md` MUST Rule 2 (Size By Complexity, Not LOC Alone), boilerplate-shape work scales 5× further than logic-shape work before sharding triggers. W1 + W3 are pure boilerplate:

- Pattern: at every call site, narrow Optional values before passing to typed param.
- Mechanism: `value or default`, `assert value is not None`, or extracting to a typed helper that raises if None.
- LOC: ~80 modifications across ~22 sites.
- Invariants held: 1 (every passed value matches the callee's typed signature).

A single shard can absorb all 22 sites. The original plan in `02-plans/01-cleanup-architecture.md` reflected this — S5 is the merged shard.

## Why surfacing this connection matters

Without recognizing the collapse, the plan would split W1 + W3 into two shards (one per warning class). That would:

- Double the worktree count for trivial gain.
- Force the orchestrator to coordinate ordering of two PRs that touch overlapping files.
- Ship the same fix logic twice (the second PR copies the first's pattern).

The collapse is the cheaper, lower-coordination shape. The plan already adopted it; this journal entry documents the rationale so a future reviewer doesn't try to re-split the shards.

## Generalized signal

When `/redteam` later mechanically sweeps for additional warnings post-cleanup, the audit MUST partition by ROOT CAUSE, not by pyright rule code. Pyright groups by rule code (`reportArgumentType`, `reportOptionalMemberAccess`, etc.); warnings sharing a rule code can have different root causes (W1 vs W3 share `reportArgumentType` but emerge from different surfaces), and warnings with different rule codes can share a root cause (W1's `reportArgumentType` and W2's `reportOptionalMemberAccess` both stem from "lazily-initialized Optional values used without narrowing" at scale).

The taxonomy in `02-warning-categorization.md` is the disposition the cleanup actually uses; the rule-code grouping is the input to that disposition, not a substitute for it.

## Disposition

Incorporated into `02-plans/01-cleanup-architecture.md` § "Decision log" implicitly (S5 already merges W1+W3) and stated explicitly here for future-session reference.
