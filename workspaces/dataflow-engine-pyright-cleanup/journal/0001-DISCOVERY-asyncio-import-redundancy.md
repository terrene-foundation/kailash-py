---
type: DISCOVERY
date: 2026-05-04
author: agent
project: dataflow-engine-pyright-cleanup
topic: 4 redundant local `import asyncio` statements in engine.py shadow module-scope import
phase: analyze
tags: [pyright, asyncio, import-discipline, engine-py]
---

# DISCOVERY: 4 redundant local `import asyncio` statements in engine.py

**Surfaced by:** Class C error investigation (E4, E5 — `"asyncio" is possibly unbound`)

## What was discovered

`engine.py` already imports `asyncio` at module scope (L7). It then re-imports it locally in 4 method bodies:

| Line | Context                              |
| ---- | ------------------------------------ |
| 4455 | Inside `discover_schema()` try block |
| 6073 | Inside another method                |
| 7783 | Inside another method                |
| 9823 | Inside another method                |

The local imports are functionally redundant — the module-scope import is in scope at every call site. They were likely added defensively when methods were extracted from a larger context, or copy-pasted from another file with no cleanup.

## Why this matters

The local `import asyncio` at L4455 is the proximate cause of pyright errors E4 (L4496) and E5 (L4504). Pyright sees `asyncio` imported only INSIDE the try block; on the path where the outer try fails before L4455 executes, the except handlers reference an unbound name. (Realistically unreachable — the import is the first statement inside the try — but pyright is conservative.)

Deleting all 4 local imports is a no-behavior-change cleanup that:

1. Closes pyright errors E4 + E5 directly.
2. Removes 4 lines of dead code.
3. Documents intent more clearly (asyncio is used throughout the module; the module-level import is the canonical declaration).

## Connection to plan

This finding informs shard **S3** (`discover-schema-flow`):

- Originally scoped as just "init `discovered_schema = None`" + "typed guard."
- Expanded to also "delete redundant local `import asyncio` at L4455" — closes E4/E5 in the same shard at zero marginal cost.
- Sibling shards may pick up L6073/L7783/L9823 deletions as opportunistic cleanup IF they touch those line ranges; otherwise carried as a "trivial follow-up" note in the S3 PR body.

## Disposition

Incorporated into `02-plans/01-cleanup-architecture.md` § "Architecture > Sharding (S3)" and `01-analysis/01-research/03-engine-py-shape.md` § "Verified `import asyncio` redundancy."

No standalone follow-up issue needed; the cleanup is part of S3.
