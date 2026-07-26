<!-- .session-notes.d fragment — per-operator, single-writer (Shard M6 D §5.1 + #743).
     last_reconciled_sha below is the incorporation-guard lag anchor (C3.2);
     a missing/empty value is treated as coherent (I10), not an error.
     Read-only aggregate view: .session-notes.aggregate.md (gitignored, regenerable). -->

---

last_reconciled_sha: 1a0b5d372
migrated_from: .session-notes
---

# Session Notes — 2026-07-26 (five-issue forest drained; 2 redteam rounds; NOTHING committed)

## Where we are

Workspace issue-1720-llm-consolidation, phase 05-codify. All five forest issues
(#1970/#1971/#1972/#1974/#1981) are CODE-COMPLETE IN THE WORKING TREE and UNCOMMITTED.
Two redteam rounds ran; neither converged. User approved at close: land the verified work,
cut nexus as a MINOR (not patch), resolve the `_tools` guard contradiction.

## Read first

1. `workspaces/issue-1720-llm-consolidation/04-validate/launch-ledger.md` — AUTHORITATIVE.
   The 2026-07-25c/26 sections at the END carry every finding with its reproduction.
2. `git status` + `git diff` — ~80 uncommitted files; the diff IS the deliverable.
3. `04-validate/find-unsanitized-provider-errors.py` — sweep-completeness enumerator built
   this session. Run before trusting #1970 coverage; its HIGH count is an upper bound.
4. `packages/kailash-kaizen/src/kaizen/nodes/ai/error_sanitizer.py` — three URL rules,
   ORDER-DEPENDENT, plus a documented accepted-residual. Read the comments before editing.

## In-flight state

- Nothing committed. Version anchors deliberately UNTOUCHED — nexus needs the MINOR bump.
- `black` applied to 9 wave files; pre-commit runs black, so this was a commit-blocker.
- kaizen + nexus CHANGELOG `[Unreleased]` rewritten (both previously contradicted shipped
  code). DataFlow `[Unreleased]` still empty though #1971 changes generated table names.

## Executed this session

None — no external actions. No PRs opened, no releases cut, no cross-repo issues filed.

## Wave tracker

→ `.wave-tracker.d/esperie.md` — no waves in flight; all shards + both redteam rounds idle.
Resume: read the tracker BEFORE launching anything (`rules/wave-loop.md` MUST-6).

## Outstanding ledger (forest)

Root `.session-notes.shared.md` (F1/F13/F14-FC/F23/F24) is a DIFFERENT program — untouched
this session. Rows below are the workspace #1970–#1981 forest carried from its prior notes.

| ID  | Item                                                     | Value-anchor (MUST-1 source)                                                                       | Status                     |
| --- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | -------------------------- |
| W1  | #1970 kaizen credential-sanitize sweep                   | user: "/redteam to convergence"; "approved all" → land                                             | code complete, UNCOMMITTED |
| W2  | #1971 dialect identifier limits                          | same                                                                                               | code complete, UNCOMMITTED |
| W3  | #1972 nexus MCP port + BREAKING `register()` validation  | same; user approved MINOR bump                                                                     | code complete, UNCOMMITTED |
| W5  | #1974 error_sanitizer pattern gaps                       | same                                                                                               | code complete, UNCOMMITTED |
| W6  | #1981 A2A degraded-judgment contract                     | same                                                                                               | code complete, UNCOMMITTED |
| W7  | core SDK `db/dialect.py`: 128-default + fail-open scheme | user "approved all" on scope; #1971's own bug inside the file the wave made single source of truth | queued                     |
| W8  | 2nd scrubber `kaizen/llm/errors.py` never learned #1974  | same security class as W1/W5; leaks all 8 shapes, zero coverage                                    | queued                     |
| W9  | sweep-completeness CI ratchet (enumerator exists)        | user: "/redteam to convergence" — review unbounded without it                                      | queued                     |

Closed this session: none — no durable receipt exists while the work is uncommitted.

## Traps

- ALWAYS `.venv/bin/python -m pytest`; bare python dies at conftest `ImportError: Node`.
- `pytest.ini` sets `--maxfail=10` — pass `--maxfail=200` or BOTH pass and fail counts truncate.
- Run pytest with `-rs`: a test written here silently SKIPPED and looked like coverage.
- MySQL :3306 / Postgres :5433 refuse credentials — those failures are infra, not code.
- Run heavy suites SERIALLY; concurrent runs cause disk-I/O + perf-threshold false failures.
- Agents go idle WITHOUT reporting (6× this session). Resume via message — recovered 3 of 4.
- `packages/*/build/lib/` are stale duplicate source trees; edits inert, greps hit them.
- Scope `black --check` to changed files; repo-wide reports ~61, mostly pre-existing.
