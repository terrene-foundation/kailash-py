---
type: AMENDMENT
date: 2026-07-07
author: agent
project: kailash-py / kailash-dataflow
topic: kailash-dataflow 2.14.2 RELEASED to PyPI — 6-issue follow-up cycle converged + published + clean-venv verified
phase: redteam
tags: [dataflow, release, pypi, redteam, 2.14.2, convergence]
relates_to: 0023-AMENDMENT-dataflow-2.14.2-followups-wave1-correctness
---

# 0024 — AMENDMENT: kailash-dataflow 2.14.2 released + verified

Closes the 2.14.2 follow-up cycle (journal 0023 = Wave 1 receipt). NOT recoverable
from git log alone: the PyPI publish + clean-venv verification.

## Released

- **PR #1608** (`fix/dataflow-2.14.2-followups`, 10 commits) admin-merged to main — merge `82290389f`.
- **CI:** 24 checks, 20 pass + 4 skipping, 0 non-green on the pinned head `6ca96dbc5`
  (Python 3.11–3.14 matrix, DataFlow Postgres/Redis infra regression, Tier-1, PACT).
- **Tag `dataflow-v2.14.2`** pushed (first push hit a transient SSH read error; retry succeeded)
  → `publish-pypi.yml` run `28871781204` all-green (Build + Publish to PyPI success; TestPyPI
  skipped per patch-release exemption; GitHub Release created).
- **PyPI verified:** `kailash-dataflow==2.14.2` (`kailash_dataflow-2.14.2-py3-none-any.whl`);
  clean-venv `uv pip install --refresh` (attempt 2, after the known index lag) →
  `dataflow.__version__ == 2.14.2` (installable + importable).
- **Sibling-drift sweep:** all packages at PyPI parity (the dataflow `info.version` line lags to
  2.14.1 briefly — metadata cache, not real drift; 2.14.2 confirmed live by JSON endpoint + install).

## What shipped (6 issues)

| Issue | Disposition                                                                                                                                                                                                                                       |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #1600 | FIX — auto-migrate ALTER-ADDs new columns to existing tables (reconciler on async + eager-sync paths; additive; fails-open; PG+SQLite). Hot-path non-regression proven via core_engine set-diff (37→35 failed, 0 new failing test IDs, +2 fixed). |
| #1603 | FIX — quote every SET/WHERE/table identifier across all bulk verbs + upsert builders (defense-in-depth; values already bound).                                                                                                                    |
| #1604 | FEAT — `express.find_one(include_deleted=)` (+ sync); cache-key partitioned; tenant dimension preserved.                                                                                                                                          |
| #1599 | FEAT — non-breaking `UserWarning` on unrecognized `__dataflow__` keys (tight allowlist; evidence-grounded "no effect" message).                                                                                                                   |
| #1605 | REMOVE — fictional `versioned`/optimistic-locking/`RetryNode` from ~18 test sites + docs; RetryNode doc reframed to the verified-real `RetryConfig`/`retry_config` API.                                                                           |
| #1252 | TEST — refuted the "cross-tenant leak" (test-harness cache artifact, not a real leak; bulk_upsert isolates on PG+SQLite); fixed via `cache_enabled=False` in the mt_db fixture.                                                                   |

## Redteam convergence (posture-invariant, L5)

- **G1** (correctness wave): reviewer + security-reviewer, 0 CRIT/0 HIGH; MED-1 (async/sync fail-disposition
  asymmetry) + LOWs fixed (`ca14ad72b`); non-regression proven by set-diff.
- **G2** (hygiene wave): reviewer + security-reviewer, 0 CRIT/0 HIGH/0 MED; LOWs fixed (`46bd2084f`) or filed;
  RetryConfig doc-replacement verified real; #1599 allowlist verified complete (no spurious-warning false positive).
- Consolidated new-tests + soft_delete lifecycle: 63 passed; bulk_operations: 46 passed; collect-only: 6776, exit 0.

## Follow-ups filed (deferred, value-anchored)

- **#1606** — express+query cache keys omit a database-instance identity → cross-DB same-tenant bleed on a
  shared Redis (narrow prod hazard + test-hermeticity). Cross-SDK keyspace lockstep (v2 pinned to Rust-SDK parity) → out of cycle scope.
- **#1607** — enterprise-doc `__dataflow__` fiction audit (`encryption`/`access_control`/`partitioning` documented
  but unconsumed; #1599's warning now surfaces them). Extends #1605's purge to `docs/enterprise/**`.

## Institutional lesson

Two alarming findings — a 35-test "regression" and a "cross-tenant leak" — were both REFUTED on decoded
evidence (evidence-first-claims): the reconciler is innocent (set-diff: it fixes tests), and bulk_upsert
isolates correctly (the failing test was a shared-Redis cache-key artifact). Independent adversarial verify +
baseline set-diff are load-bearing; the scary label was wrong both times.
