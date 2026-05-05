# DISCOVERY: Brief Undercounts BaseTool Override-Mismatch Sites

**Date:** 2026-05-04
**Phase:** /analyze (gate before /todos per `rules/agents.md` MUST: Parallel Brief-Claim Verification)
**Severity:** MEDIUM — wrong count → wrong shard sizing if not corrected

## Context

Issue #814 brief enumerates Category A (BaseTool signature drift) as **7 sites**:

| File                           | Line | Override params |
| ------------------------------ | ---- | --------------- |
| `tools/native/skill_tool.py`   | 96   | 3 + `**kwargs`  |
| `tools/native/process_tool.py` | 365  | 3               |
| `tools/native/process_tool.py` | 478  | 5               |
| `tools/native/search_tools.py` | 64   | 3 + `**kwargs`  |
| `tools/native/search_tools.py` | 227  | 3 + `**kwargs`  |
| `tools/native/task_tool.py`    | 117  | 8 + `**kwargs`  |
| `tools/native/todo_tool.py`    | 278  | 3               |

## Mechanical verification (pyright 1.1.371)

```
$ uv run pyright src/kaizen/tools/native/ src/kaizen/research/ 2>&1 \
  | grep -E '^[ ]+/.*\.py:[0-9]+:[0-9]+ - error: Method' | wc -l
17
```

Full enumeration of override-mismatch sites against current main (HEAD `bb37f0db`):

| #   | File                               | Line | In brief? |
| --- | ---------------------------------- | ---- | --------- |
| 1   | `tools/native/bash_tools.py`       | 125  | **NO**    |
| 2   | `tools/native/file_tools.py`       | 60   | **NO**    |
| 3   | `tools/native/file_tools.py`       | 155  | **NO**    |
| 4   | `tools/native/file_tools.py`       | 225  | **NO**    |
| 5   | `tools/native/file_tools.py`       | 326  | **NO**    |
| 6   | `tools/native/file_tools.py`       | 399  | **NO**    |
| 7   | `tools/native/file_tools.py`       | 569  | **NO**    |
| 8   | `tools/native/file_tools.py`       | 643  | **NO**    |
| 9   | `tools/native/interaction_tool.py` | 246  | **NO**    |
| 10  | `tools/native/notebook_tool.py`    | 105  | **NO**    |
| 11  | `tools/native/process_tool.py`     | 365  | yes       |
| 12  | `tools/native/process_tool.py`     | 478  | yes       |
| 13  | `tools/native/search_tools.py`     | 64   | yes       |
| 14  | `tools/native/search_tools.py`     | 227  | yes       |
| 15  | `tools/native/skill_tool.py`       | 96   | yes       |
| 16  | `tools/native/task_tool.py`        | 117  | yes       |
| 17  | `tools/native/todo_tool.py`        | 278  | yes       |

**Brief undercounted by 10 sites (143% miss).** Files entirely missed: `bash_tools.py`,
`file_tools.py` (8 sites!), `interaction_tool.py`, `notebook_tool.py`.

## Other Brief Inaccuracies Discovered

### Category B (Optional/None safety): brief says 4 sites, pyright shows ~9

Brief enumerated only:

- `task_tool.py:283` — for_specialist on None ✅
- `notebook_tool.py:245` — result possibly unbound ✅ (one of 4 unbound errors at this site)
- `research/parser.py:83` — Search on None ✅
- `research/parser.py:138` — None callable ✅

Brief MISSED:

- `notebook_tool.py:229,230,242` — `result` possibly unbound (3 more sites — same root cause as :245)
- `notebook_tool.py:223,227` — `str | None` to `str` argument-type warnings
- `interaction_tool.py:369` — `Awaitable[List[QuestionAnswer]]` incompatible attribute assignment

### Category D (Type-argument mismatch): brief says "errors", pyright shows warnings

`research/adapter.py:119` issues are `reportArgumentType` **warnings**, not errors. Functionally
the fix is the same (correct call shape), but severity classification was wrong in brief.

### Category C (Missing imports): brief mostly accurate

Brief enumerated 7 missing imports across `__init__.py`, `parser.py`, `search_tools.py`. Pyright
confirms 7 errors + 1 warning (`bs4` is `reportMissingModuleSource` — type-only stub absent —
not a hard `reportMissingImports`).

## Why This Matters (Per Rule)

`rules/agents.md` MUST: Parallel Brief-Claim Verification When Issue Count ≥ 3 says:

> Inaccuracies surfaced by the deep-dive sweep MUST be recorded in the workspace journal AND
> in the architecture plan's "Brief corrections" section AS THE GATE before `/todos`.

The 7→17 site undercount changes shard sizing materially:

- 7 sites = arguably one shard (~150 LOC of mechanical fixes)
- 17 sites = closer to two shards (BaseTool contract design decision + sweep across 8 files)

Without this correction, `/todos` would have produced a one-shard plan that overflows the
≤500 LOC load-bearing logic budget per `rules/autonomous-execution.md` MUST Rule 1, AND would
miss `bash_tools.py` + `file_tools.py` entirely — **the very orphan failure mode
`rules/agents.md` MUST: Reviewer Mechanical AST/Grep Sweep is designed to prevent**.

## Resolution

1. **Architecture plan MUST include corrected counts** (17 / 9 / 8 / 2) — done in
   `02-plans/01-architecture.md` "Brief corrections" section.
2. **Pyright baseline saved** to `01-analysis/00-pyright-baseline.txt` as ground-truth
   reference for /implement and /redteam.
3. **Sharding decision deferred to plan** — recommended split is 3 shards (BaseTool
   contract + sweep / Optional+Unbound safety / dependency declaration), see plan.

## Cross-Reference

- `rules/agents.md` § "Parallel Brief-Claim Verification When Issue Count ≥ 3"
- `rules/autonomous-execution.md` § "Per-Session Capacity Budget"
- `01-analysis/00-pyright-baseline.txt` — full pyright output for grounding
