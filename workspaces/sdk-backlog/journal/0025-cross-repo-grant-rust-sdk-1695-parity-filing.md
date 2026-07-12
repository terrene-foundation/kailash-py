# 0025 — GRANT: cross-repo issue filing (Rust SDK #1695 parity)

**Date:** 2026-07-12 · **Type:** DECISION · **Phase:** 05-codify · **Posture:** L5_DELEGATED

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (per repo-scope-discipline § User-Authorized Exception + upstream-issue-hygiene MUST-1)

- **Requester / authorizer:** jack@terrene.foundation (repo owner), this session.
- **Verbatim instruction:** "approved both" — approving (a) the 2.48.1 security release and
  (b) filing the cross-SDK parity issue on the Rust SDK for the #1695 class.
- **Target:** `esperie-enterprise/kailash-rs` (private Rust SDK BUILD repo).
- **Action (bounded WRITE):** ONE `gh issue create` filing the #1695 default-verification-level
  parity gap, `cross-sdk`-labelled. Body scrubbed per `upstream-issue-hygiene.md` MUST-2 —
  SDK-public-API-surface ONLY (no downstream/workspace/finding-tag context); references the PUBLIC
  Foundation SDK issue kailash-py#1695 by number only. Plus ONE back-link comment on py #1695.
  NO other writes, NO other repos, NO other issues.
- **Timestamp (grant, pre-action):** 2026-07-12T11:22:56Z.
- **Scope guarantee:** only the named issue-create + back-link against only the named repo.

## Why

Both gate reviewers (security-reviewer + reviewer) on the py #1695 fix flagged that the same
two-surface shape (default-level verify that checks capability CONTENT signatures only at the
full level, PLUS an ops-less/lightweight verify path that skips signature verification entirely)
plausibly exists in the Rust SDK trust plane. Per `cross-sdk-inspection.md` Rule 1 this parity gap
MUST be inspected on the sibling SDK. The issue is filed at the SDK-contract level (the Rust team
maps it to their code — the py fix explicitly did NOT copy the Rust implementation and vice versa).

## Executed (this session)

- **Filed rs#1765** on `esperie-enterprise/kailash-rs` (`cross-sdk` label): the #1695 default-verification
  parity inspection, SDK-contract level, scrubbed (no downstream context; references public py#1695 by number).
  URL: `https://github.com/esperie-enterprise/kailash-rs/issues/1765`.
- **Back-linked on py#1695** (public repo → Rust SDK referenced by ROLE only, "their #1765", no private slug
  per `cross-sdk-inspection.md` Rule 6).
