---
type: DECISION
date: 2026-06-18
author: human
project: issue-1356-jwt-revocation
topic: User-authorized cross-repo READ of kailash-rs for revocation-parity (F2)
phase: redteam
tags: [cross-sdk, authorization, kailash-rs, jwt, revocation, "F2"]
relates_to: 0003-DECISION-middleware-auth-revocation-redteam-convergence
---

# AUTHORIZATION — cross-repo READ of kailash-rs (F2 revocation parity)

Pre-action receipt per `repo-scope-discipline.md` § User-Authorized Exception
(all five conditions). This entry lands BEFORE any kailash-rs command runs.

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** the user (co-owner), in-session.
- **Verbatim instruction:** "approved, do the cross-repo read and verify
  kaialsh-rs and F3 too. /wrapup for fresh session."
- **Target repo:** `esperie-enterprise/kailash-rs` (private Rust SDK; per the
  standing reference memory — NOT `terrene-foundation/kailash-rs`).
- **Bounded action (READ-ONLY):** locate the JWT-middleware auth verifier
  equivalent to kailash-py `MiddlewareAuthManager` and determine whether it has
  the SAME token-revocation gap F1 just closed — i.e. whether its token verifier
  consults a revocation store / carries a `jti` / exposes a revoke method, or
  whether (like the pre-2.38.3 kailash-py manager) it has no revocation at all.
  Cross-SDK inspection per `cross-sdk-inspection.md` MUST-1.
- **Timestamp:** 2026-06-18 (this session, continued).
- **Scope fence:** READ ONLY. No writes, branches, commits, issues, or PRs
  against kailash-rs. Any cross-SDK issue filing remains separately human-gated
  per `upstream-issue-hygiene.md` MUST-1 (draft-and-present, never auto-file).
  No incidental reads beyond the JWT/auth revocation surface.

## For Discussion

1. If kailash-rs has the same gap, the disposition is a human-gated cross-SDK
   issue (scrubbed minimal-repro) — NOT a fix from this kailash-py session
   (cross-repo writes need their own kailash-rs session). Confirm at report time.
2. If kailash-rs has NO equivalent manager (different auth architecture), the
   cross-SDK obligation is discharged with a negative result recorded here.
