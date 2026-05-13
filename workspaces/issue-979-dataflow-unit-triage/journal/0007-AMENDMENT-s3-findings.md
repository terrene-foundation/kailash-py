---
type: DISCOVERY
date: 2026-05-14
created_at: 2026-05-14T00:00:00Z
author: co-authored
session_id: s3-fabric-shard
session_turn: 2
project: issue-979-dataflow-unit-triage
topic: S3 same-class sweep amends Layer C "MOVE strategy clean" claim
phase: implement
tags: [s3, fabric, tier-1, integration, sweep, amendment]
---

# 0007 DISCOVERY — S3 Same-Class Sweep Findings Amend Journal 0001 Layer C

## Why this entry

Journal `0001-DISCOVERY-brief-verification.md` Layer C recorded the OPTION-C′
MOVE strategy as "verified clean" — i.e., moving the 21 fabric tests from
`tests/unit/fabric/` to `tests/integration/fabric/` would close the
Tier-1 Rule 1 violation without same-class collateral. During S3
implementation (this session) verification surfaced two same-class gaps
that the Layer C claim did not anticipate. Both fit within S3's remaining
shard budget; both were resolved in-shard per `rules/autonomous-execution.md`
MUST Rule 4 (fix-immediately when review surfaces same-class gap within
shard budget).

The user authorized both dispositions explicitly in the same session
(this turn). This entry is the durable receipt per
`rules/verify-resource-existence.md` MUST-4 + `rules/journal.md`
naming/format.

## Findings

### Finding A — Sibling Tier-1 violation outside the moved subdir

`packages/kailash-dataflow/tests/unit/adapters/test_file_adapter.py`
imports `from dataflow.fabric.config import FileSourceConfig` at module
top (1 hit per `grep -c "^from dataflow.fabric\|^import dataflow.fabric"`).
This is the SAME bug class S3 was created to close (Tier-1 Rule 1:
top-imports MUST NOT require optional extras) but the file lives outside
the `fabric/` subdir, so the OPTION-C′ MOVE did not catch it.

**File self-classifies as tier-2** in its module docstring:
`"Tests for FileSourceAdapter — Tier 2 (real temp files, no mocking)."`
(line 4). 563 LOC of real-infra tests (tempfile, no mocks).

**Disposition (user-authorized):** `git mv` to integration tier.

```bash
git mv packages/kailash-dataflow/tests/unit/adapters/test_file_adapter.py \
       packages/kailash-dataflow/tests/integration/adapters/test_file_adapter.py
```

Commit: `2d19af912ce4296471b69fd7fc8f6e87cf0fac2e` —
`test(dataflow): wip(s3-4) move test_file_adapter.py to integration tier (same-class sweep)`

### Finding B — Integration-tier NO-MOCKING hook rejects a moved file

After the S3-1 git mv, `pytest packages/kailash-dataflow/tests/integration/fabric --collect-only`
INTERNALERROR'd with:
> `NO MOCKING POLICY VIOLATION (Tier 2): integration/fabric/test_express_pagination.py
> imports unittest.mock. Integration tests must use real infrastructure.
> Move mock-based tests to tests/unit/ or rewrite against real backends
> (see rules/testing.md § Tier 2).`

Independent inspection: `test_express_pagination.py` has exactly 3
imports — `from __future__`, `from unittest.mock import AsyncMock, MagicMock, patch`,
`import pytest`. ZERO `dataflow.fabric.*` imports (the fabric subdir hosted
it only by historical placement, not by dependency). ~25+ MagicMock /
AsyncMock / patch references in test bodies. 175 LOC.

The AC#3 OR-clause is satisfied trivially — no `[fabric]` extra to gate.
The file's proper home is tier-1 (mock-heavy unit), not integration
(NO MOCKING). The integration-tier hook is correctly rejecting it.

**Disposition (user-authorized):** revert-move to `tests/unit/features/`.

```bash
git mv packages/kailash-dataflow/tests/integration/fabric/test_express_pagination.py \
       packages/kailash-dataflow/tests/unit/features/test_express_pagination.py
```

Commit: `c096a8fb9a4e65847dfe088af0a30089810e514d` —
`test(dataflow): wip(s3-5) revert-move test_express_pagination to tier-1 features (zero fabric deps)`

## Layer C amendment

Journal `0001` Layer C should be read together with this entry:

- **Original claim:** OPTION-C′ MOVE strategy is verified clean — 21 fabric tests
  move; the integration tier has `[fabric]` available; no same-class collateral.
- **Amended claim:** The OPTION-C′ MOVE strategy is clean ONLY for the 20 of
  21 files that genuinely depend on `dataflow.fabric.*`. One file
  (`test_express_pagination.py`) had no fabric dependency and required
  revert-move to tier-1 to satisfy the integration tier's NO-MOCKING
  contract. Separately, one sibling outside the `fabric/` subdir
  (`tests/unit/adapters/test_file_adapter.py`) carried the same Tier-1
  Rule 1 violation and required a same-class move.

This is not a falsification of Layer C — the strategy IS sound; the
verification was incomplete. The amendment closes the gap.

## Verification commands (receipts)

```bash
# Invariant — zero dataflow.fabric.* top-imports in unit tier:
grep -rln "^from dataflow.fabric\|^import dataflow.fabric" \
    packages/kailash-dataflow/tests/unit/
# Expected: zero hits (test_file_adapter.py moved; fabric subdir gone)

# Invariant — integration/fabric collects cleanly (no mock-policy violations):
pytest packages/kailash-dataflow/tests/integration/fabric --collect-only -q

# Invariant — test_express_pagination.py is in tier-1 features:
ls packages/kailash-dataflow/tests/unit/features/test_express_pagination.py
```

(See commit log + verification output in the implementing session for
literal command outputs.)

## For Discussion

1. **Counterfactual:** Had the integration-tier conftest NOT had the
   NO-MOCKING enforcement hook, would `test_express_pagination.py` have
   landed quietly in `tests/integration/fabric/` and silently degraded
   the integration tier's contract? If yes, the hook is doing real work
   and the "Layer C clean" claim was load-bearing on a defense we
   didn't credit.
2. **Specific-data:** S3's brief stated "OPTION-C′ MOVE strategy:
   verified clean per `journal/0001` Layer C." Should `/redteam` round
   verification have caught Findings A + B before `/todos` shipped the
   shard plan, or are these the kind of collateral that ONLY surfaces
   during the move itself (integration-tier conftest fires only on the
   moved files)?
3. **Process:** Should the workspace `briefs/` enforce a step where
   every "MOVE-to-tier-N" plan is verified by running the destination
   tier's collect-only sweep against the source files BEFORE the move,
   not after? That would convert Finding B from in-shard discovery to
   pre-shard plan refinement.

## Consequences + follow-up

- S3 PR will be amended (one push) to include S3-4 + S3-5 commits before
  orchestrator opens the PR.
- S6 (smoke invariants for SSRF / fabric-integrity coverage signal) is
  unchanged — Findings A + B do not affect S6's scope.
- `briefs/00-brief.md` AC#3 remains the value-anchor; the brief's OR-clause
  (`[fabric]` extra OR `pytest.importorskip`) covered Finding B's
  disposition implicitly (zero fabric deps = no OR-clause needed at all,
  the file belongs in tier-1).
