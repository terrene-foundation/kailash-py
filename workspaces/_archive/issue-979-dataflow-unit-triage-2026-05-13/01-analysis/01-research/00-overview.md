# Research Overview — DataFlow Unit Suite Triage (#979)

## Documents in this directory

1. `00-overview.md` (this file) — reader index + reading order
2. `01-tier1-contract.md` — the canonical tier-1 contract from
   `packages/kailash-dataflow/tests/unit/CLAUDE.md`
3. `02-failure-layers.md` — per-layer state with verified
   file:line citations (sourced from parallel verification agents,
   `journal/0001`)
4. `03-violations-inventory.md` — every file currently violating
   the tier-1 contract, with categorized failure mode
5. `04-history-reconciliation.md` — corrected PR #968/#976/#977
   chronology and what landed vs what didn't
6. `05-recovery-plan-mapping.md` — mapping from PR #977's recovery
   plan to #979's acceptance criteria, with gap notes

## Reading order

For implementers: 01 → 02 → 03 → 04 → 05.
For reviewers: 04 first (chronology), then 02, then 03.
For shard authors at /todos: 02 + 03 + 05.
