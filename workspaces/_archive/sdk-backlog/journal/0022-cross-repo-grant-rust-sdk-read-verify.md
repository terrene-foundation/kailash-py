# 0022 — GRANT: cross-repo read-only status-verify (kailash-rs)

**Date:** 2026-07-11 · **Type:** DECISION · **Phase:** 05-codify · **Posture:** L5_DELEGATED

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (per repo-scope-discipline § User-Authorized Exception — all five conditions)

- **Requester / authorizer:** jack@terrene.foundation (repo owner), this session.
- **Verbatim instruction:** "i approve your cross repo read" — approving the agent-proposed,
  agent-restated read-only status check named in the prior turn.
- **Target:** `esperie-enterprise/kailash-rs` (private).
- **Action (bounded, read-only):** `gh issue view <N> --repo esperie-enterprise/kailash-rs`
  for the exact set the workspace records reference — **rs#1713, rs#1729, rs#1732, rs#1712,
  rs#1667, rs#1707** — to report each issue's open/closed status. NO writes, NO comments,
  NO browsing, NO other repos, NO loom reads (F5–F8 are proposal/Gate-1 items, not issues).
- **Timestamp (grant, pre-action):** 2026-07-11T13:29:03Z.
- **Scope guarantee:** only the named `gh issue view` calls against only the named repo/issues;
  any incidental read beyond this set is out of scope and not performed.

## Why

The workspace forest ledger (F2/F3) and prior filing receipts (`journal/0004/0008/0011`) reference
these rs# numbers as carried-forward prose. Per `handoff-completion` MUST-2 + `verify-claims-before-write`,
their live status was UNVERIFIED. This grant authorizes the one bounded read that converts the
carried-forward references into a verified status table.

## Verified results (read-only, 2026-07-11T13:29Z)

| Issue   | State    | Note                                                                                                                                                                |
| ------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| rs#1713 | **OPEN** | cache keys omit DB-instance identity → cross-DB bleed (F2, mirrors py #1606); updated 2026-07-10                                                                    |
| rs#1729 | **OPEN** | verify soft_delete/versioned parity (F3, mirrors py #1601); updated 2026-07-10                                                                                      |
| rs#1732 | **OPEN** | BH5 trip-and-hold governance circuit-breaker (parity w/ py 2.48.0); updated 2026-07-11                                                                              |
| rs#1712 | CLOSED   | cross-tenant upsert guard — done rs-side (2026-07-10)                                                                                                               |
| rs#1667 | CLOSED   | RFC 8785 JCS subject_hash — done rs-side (2026-07-11)                                                                                                               |
| rs#1707 | CLOSED   | BH3 origin-authentication — done rs-side (2026-07-11); STATUS CHANGE vs `journal/0008` ("not yet posted, py-side implementing first") — handoff has since completed |

**Disposition:** 3 open (rs#1713/F2, rs#1729/F3, rs#1732/BH5) = the live cross-SDK forest, actionable
ONLY in a kailash-rs session (py side done + merged; none blocks this repo). 3 closed = handled rs-side.
Forest ledger in `.session-notes` updated carried-forward → verified.
