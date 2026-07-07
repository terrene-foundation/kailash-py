<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: 699b0e20e
migrated_from: .session-notes
---

# Session Notes — 2026-07-07 (session 8)

## Where we are

kailash-dataflow **2.14.2 is redteam-converged, merged, and live on PyPI**
(clean-venv verified `dataflow.__version__ == 2.14.2`). The 6-issue follow-up
cluster from journal 0022 is closed. Repo on `main` @ `699b0e20e`, tree clean
(only untracked `workspaces/mops-onboarding/.session-notes`). No active todos.

## Read first

1. `workspaces/mops-onboarding/.session-notes` — live workspace notes (this repo's session-start surfaces that path; fullest context).
2. `workspaces/mops-onboarding/journal/0024-...-dataflow-2.14.2-released.md` — release receipt (PR #1608, tag, PyPI verify). NOT in git log.
3. `workspaces/mops-onboarding/journal/0023-...-wave1-correctness.md` — Wave-1 G1 convergence + the #1252 leak-refutation lesson.
4. `workspaces/mops-onboarding/04-validate/sweep-2026-07-07.md` — full /sweep (board clean; 15-issue backlog).
5. `packages/kailash-dataflow/CHANGELOG.md` `[2.14.2]` — exactly what shipped.

## Executed this session

- Released **kailash-dataflow 2.14.2** to PyPI (PR #1608 / tag `dataflow-v2.14.2`, publish run all-green, clean-venv verified) — NOT recoverable from git log alone.
- Filed **#1606** (cache-key DB-identity, cross-SDK) + **#1607** (enterprise-doc unbacked-key fiction audit).

## Outstanding ledger (forest)

Authoritative forest = root `.session-notes.shared.md`: F1 (mops-onboarding program, BLOCKED on user cross-repo re-confirm), F13 (SDK backlog #1573/#1526/#1532), F14/FC (SAFR cluster, BLOCKED on user scoping), F19 (#1606), F20 (#1607).

Closed this session: `#1600` `#1603` `#1604` `#1605` `#1599` → PR #1608 (dataflow 2.14.2); `#1252` → test-fix in same PR.

Prior-fragment ledger reconcile (07-04 lineage, superseded): `F2`→ now `F1` (cross-repo); `F-COMPKEY`(#1526) → folded into `F13`; `F-MYSQL`(#1537) `F-LISTSTALE`(#1538) `F-LOGSYNC`(#1534) `F6`(#1503) `F7`(#1504) → CLOSED in interim sessions (absent from the 15 open issues); `F3` (~33 prod TODO markers) → user-baselined "leave as baseline" (2026-06-26).

## Traps

- `bulk.py`: 4 intentional `logger.warning` (2 empty-filter + 2 per-record skip, keys/id only) + a 5th in `_model_has_tenant_field`. Do NOT re-flag.
- DB tests: PG on 5434, no `psql` → asyncpg via ROOT `.venv/bin/python`; `-p no:xdist -o "addopts="`; deselect #1594 hang (`test_bulk_upsert_large_mixed_batch` + `test_v052*`); teardown "Logging error" spam ≠ failure.
- `core_engine/` integration has ~35 PRE-EXISTING local failures (baseline on main; PG-test-manager infra-dependent). NOT from 2.14.2 (set-diff proven). CI is the arbiter.
- A "swept all sites" claim is a code-claim: enumerate → grep-verify → THEN write. Independent adversarial verify + baseline set-diff refuted TWO scary findings this session (a 35-test "regression" and a "cross-tenant leak" — both innocent).
- PyPI/uv lag: `/<ver>/json` 200 + install works but `uv pip install` unresolvable → `uv pip install --refresh` (or pip `--no-cache-dir`), retry ~60s.

## Unreleased packages

None — dataflow 2.14.2 released + clean-venv-verified this session; all 8 siblings at PyPI parity (checked at release). Post-tag commits are docs/workspace-only (carve-out).

## Recommended next pick (human owns it)

**#1573** (AutoMigrationSystem ignores `__tablename__`) — same subsystem as this session's #1600, warm context. Cross-repo (F1) + SAFR (F14) BLOCKED on a user turn per repo-scope-discipline.
