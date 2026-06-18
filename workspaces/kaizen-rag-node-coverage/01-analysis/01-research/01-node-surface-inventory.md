# 01 — Node Surface Inventory (mechanical baseline)

Gathered 2026-05-19 by mechanical enumeration against `main` (`0f906a1e0`),
`packages/kailash-kaizen/src/kaizen/nodes/rag/`.

## Counts (authoritative — supersedes brief's "~53")

| Metric                     | Value |
| -------------------------- | ----- |
| `class X` definitions      | 58    |
| `@register_node` decorated | 55    |
| `__init__.__all__` exports | 56    |
| Modules                    | 17    |

Discrepancy 58 vs 55 vs 56 is itself an analysis target (3 class defs not
`@register_node`-decorated — base/mixin classes? abstract? — and `__all__`
exporting 56 vs 55 registered must be reconciled by the deep-dive).

## Per-module class-def distribution

| Module              | class defs              |
| ------------------- | ----------------------- |
| similarity.py       | 7                       |
| query_processing.py | 6                       |
| strategies.py       | 5                       |
| advanced.py         | 5                       |
| workflows.py        | 4                       |
| optimized.py        | 4                       |
| router.py           | 3                       |
| realtime.py         | 3                       |
| privacy.py          | 3                       |
| multimodal.py       | 3                       |
| graph.py            | 3                       |
| federated.py        | 3                       |
| evaluation.py       | 3                       |
| agentic.py          | 3                       |
| conversational.py   | 2                       |
| registry.py         | 1                       |
| **init**.py         | 0 (public surface only) |

## Current test state

- **Behavioral coverage: 0.** No behavioral test exercises any rag node's
  `run()` / execution contract.
- Only rag test on disk: `packages/kailash-kaizen/tests/regression/
test_rag_resurrection_import_smoke.py` — proves import + registration,
  NOT behavior.
- The "15 `*rag*` test files" from a loose glob are false positives:
  `sto`**`rag`**`e` (storage) contains the substring `rag`.

## `[rag]` optional-dependency extra (kaizen pyproject.toml)

```
rag = ["numpy>=1.24.0", "Pillow>=10.0.0", "networkx>=3.0",
       "requests>=2.32", "aiosqlite>=0.19.0"]
```

**Key gap for testability:** `[rag]` carries NO LLM-provider client and NO
vector-store dependency. Behavioral coverage of retrieval / generation nodes
that need an embedding model, an LLM, or a vector index therefore depends on
how those nodes take their backends (injected client param vs hard import).
This is THE central testability question — feeds shard tiering and the
no-mocking-Tier-2/3 constraint (`rules/testing.md`).

## Implications for sharding

- ~58 classes ≫ single-shard budget (≤500 LOC load-bearing / ≤5–10
  invariants). MUST decompose at `/todos`.
- Natural shard axis = module-cluster × real-infra tier (pure-compute
  numpy/similarity vs LLM/vector vs graph/networkx vs network/federated).
- Per-shard value-anchor required (`rules/value-prioritization.md` MUST-2).
