# 0004 — AUTHORIZATION — Cross-Repo F5 Upstream Issue Filings (kailash-rs)

cross-repo-authorized: terrene-foundation/kailash-rs

## Authorization receipt

- **Requester:** session operator (resolved via `lib/operator-id.js`)
- **Target repo:** `terrene-foundation/kailash-rs`
- **Bounded action:** file two (2) upstream issues for cross-SDK semantic-parity gaps:
  - Issue A: principal-kind taxonomy on `DelegateIdentity` / `Role` / `DispatchSurface`
  - Issue B: grantee registry on `TenantScopedCascade` + dispatch identity-bind validation
- **Timestamp:** 2026-05-24 (session window 02:30Z+)
- **Authority chain:** `repo-scope-discipline.md` § User-Authorized Exception (5-condition test)

## 5-Condition Test (each satisfied)

1. **User-initiated** ✓ — verbatim user turn: "approved, pelase /autonomize in parallel and /redteam to convergence" (responding to recommendation that named target + bounded action explicitly)
2. **Explicit + specific** ✓ — prior session message named target repo `terrene-foundation/kailash-rs` and bounded action (file 2 upstream issues for principal-kind taxonomy + grantee-registry parity)
3. **Confirmed** ✓ — agent presented recommendation A naming target + action; user responded "approved" before any cross-repo command ran
4. **Journaled before acting** ✓ — this entry; this line predates any `gh` invocation against `terrene-foundation/kailash-rs` in this session
5. **Scoped exactly** ✓ — only the named action (2 upstream issue filings) against only the named repo; per-issue gate per `upstream-issue-hygiene.md` MUST-1 still applies before each submission; incidental reads against the rs repo are limited to (a) duplicate-issue existence check (`gh issue list`), (b) public-source verification of named symbols if needed for minimal-repro accuracy

## Stacked discipline

- **`upstream-issue-hygiene.md` MUST-1** — drafting permitted under this authorization; _submission_ of each issue requires its OWN per-issue gate (each draft body presented for explicit y/N approval)
- **`upstream-issue-hygiene.md` MUST-2** — both issue bodies MUST be scrubbed of downstream-context tokens (no `/redteam` references, no kailash-py PR numbers, no workspace shard IDs, no internal rule file paths)
- **`upstream-issue-hygiene.md` MUST-3** — 5-section shape only (Affected API / Minimal repro / Expected vs actual / Severity / Acceptance criteria)
- **`verify-resource-existence.md` MUST-1** — duplicate-issue existence check against `terrene-foundation/kailash-rs` precedes drafting

## Source surfacing context (LOCAL ONLY — does not leak into issue bodies)

The semantic-divergence claims this authorization covers were surfaced via the kailash-py side of the cross-SDK parity contract:

- principal-kind taxonomy: kailash-py issue surfaced + closed via local fix; the rs side remains uncovered (cross-SDK parity is the open work)
- grantee registry: kailash-py issue surfaced + closed via local fix; the rs side `TenantScopedCascade` lacks the corresponding grantee tracking

These surfacing details belong in THIS journal entry (local context); they MUST NOT appear in the upstream issue bodies per `upstream-issue-hygiene.md` MUST-2.

## Closure criteria for this authorization

- (a) two issue bodies drafted, redteam-converged, and presented for per-issue gates; or
- (b) one filed + one declined by user at gate; or
- (c) both declined by user at gate.

Any outcome that proceeds beyond (a) authorization scope (e.g. filing a third issue, opening a PR, commenting on existing rs issues) requires a fresh user-initiated authorization with its own journal entry.

## ⚠ AUTHORIZATION VOID — TARGET DOES NOT EXIST AS NAMED

Per `verify-resource-existence.md` MUST-1 existence check (live `gh api`):

| Repo                            | Exists | Accessibility          | Notes                                                                                                        |
| ------------------------------- | ------ | ---------------------- | ------------------------------------------------------------------------------------------------------------ |
| `terrene-foundation/kailash-rs` | **NO** | 404                    | The org has NO `kailash-rs` repo. Authorization target does NOT exist.                                       |
| `esperie-enterprise/kailash-rs` | YES    | private, gh can access | Described as canonical BUILD repo (esperie-enterprise is private org)                                        |
| `rrps-mtu/kailash-rs`           | YES    | private, gh can access | "verbatim seed of esperie-enterprise/kailash-rs; upstream tracked via git remote, forking disabled upstream" |

Per `repo-scope-discipline.md` User-Authorized Exception condition 2 ("Explicit + specific — names the target repo"), substituting one repo for another would self-extend authorization — BLOCKED. The session HALTS here for user re-authorization with the correct target named.

This authorization (0004) is recorded as voided-at-existence-check. Filing actions did NOT proceed. The cross-repo-authorized marker at the top of this file remains for audit completeness, but no `gh issue create` has been issued.

Outcome: surfaced to user for explicit re-authorization naming the correct target repo.
