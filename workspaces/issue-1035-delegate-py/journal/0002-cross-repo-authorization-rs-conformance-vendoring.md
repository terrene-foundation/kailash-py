# Cross-repo authorization — kailash-rs conformance fixture vendoring (S7)

cross-repo-authorized: terrene-foundation/kailash-rs

## Requester

User (jack@researchroom.sg) via AskUserQuestion turn, 2026-05-22.

## Target

`terrene-foundation/kailash-rs` (resolver logical key: `build.rs`).

## Bounded action

READ-only operations on `terrene-foundation/kailash-rs` working tree to locate

- copy conformance fixture files for the kailash.delegate composition primitive
  (issue #1035). Specifically:

* Locate conformance fixture files under `bindings/kailash-rs/test-vectors/`,
  `specs/delegate-conformance/`, or equivalent directory containing JSON byte-
  shape pin vectors for: TAOD transitions, DispatchResult, ConnectorInvocation
  Result, AuditChainEntry, RuntimeExecutionResult round-trip.
* Read those files (via `cat`, `Read`, or `grep` against the rs working tree).
* Vendor (copy byte-for-byte) the canonical fixture files into kailash-py at
  `tests/fixtures/delegate-conformance/` per `cross-sdk-inspection.md` Rule 4a
  (Sibling-Canonical Fixtures MUST Be Vendored, Not Re-Authored).

## Explicitly excluded

- NO writes to kailash-rs working tree
- NO `gh pr create` / `gh issue create` against kailash-rs
- NO `gh issue comment` / `gh pr comment` against kailash-rs
- NO incidental reads of kailash-rs source beyond the conformance fixtures
  enumerated above
- NO modifications to rs branches

## Verbatim user instruction (AskUserQuestion 2026-05-22)

> "Yes — READ-only on terrene-foundation/kailash-rs conformance fixtures
> (Recommended)"
>
> Bounded action: READ-only. Target: terrene-foundation/kailash-rs. Scope:
> locate + copy conformance fixture files (likely under
> bindings/kailash-rs/test-vectors/ or specs/delegate-conformance/) for TAOD
> transitions, Dispatch byte-shapes, RuntimeExecutionResult round-trip,
> AuditChainEntry hashes. NO writes, NO PRs, NO comments on rs side. Journal
> entry lands BEFORE first gh/cat/grep command per User-Authorized Exception
> condition 4. Repo registered via bin/lib/loom-links.mjs::resolveRepo per
> cross-repo.md MUST-1.

## Five-condition compliance (repo-scope-discipline.md User-Authorized Exception)

1. **User-initiated** ✅ — AskUserQuestion turn 2026-05-22 (not agent-suggested)
2. **Explicit + specific** ✅ — named target repo + bounded READ action
3. **Confirmed** ✅ — restated by agent + user answered selected option
4. **Journaled before acting** ✅ — this file lands BEFORE first cross-repo
   command (verified by grep `cross-repo-authorized: terrene-foundation/kailash-rs`
   in `journal/.pending/` or committed journal entries pre-dating any rs read)
5. **Scoped exactly** ✅ — only READ on the named repo; no scope creep

## Receipt

Journal entry committed to `workspaces/issue-1035-delegate-py/journal/` at
`0002-cross-repo-authorization-rs-conformance-vendoring.md` BEFORE first
cross-repo command. Greppable marker line above: `cross-repo-authorized:
terrene-foundation/kailash-rs`.

## Disposition for S7 worktree-isolated agent

The agent operates in a worktree at `.claude/worktrees/delegate-s7`. The
authorization extends to that agent for the bounded READ action only. The
agent's prompt MUST include this journal entry by reference + the
five-condition compliance reminder.

## Timestamp

2026-05-22 (session in progress).
