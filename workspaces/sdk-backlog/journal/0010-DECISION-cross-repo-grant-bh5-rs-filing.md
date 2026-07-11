# DECISION — Cross-repo grant: file BH5 mirror issue(s) on the Rust SDK

**Date:** 2026-07-11
**Phase:** 05-codify
**Type:** DECISION

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (repo-scope-discipline User-Authorized Exception)

- **Requester:** user (esperie / Jack Hong), in-session.
- **Target:** `esperie-enterprise/kailash-rs` (the private Rust SDK BUILD repo; resolver key `build.rs`).
- **Action:** file (or update) a GitHub issue mirroring the kailash-py BH5 governance
  circuit-breaker + the prune-when-unset signed-model discipline, for cross-SDK parity
  (EATP D6). Verify whether `rs#1714` already exists and covers BH5 before filing new.
- **Timestamp:** 2026-07-11.
- **Verbatim instruction:** "i already authorize you, if you don't specifically ask for
  it and just leave your notes locally and expect it to be magically done at kailash-rs
  or expect me to fill in the gaps for you, that's very irresponsible! please codify this
  unacceptable behavior and NEVER LET IT HAPPEN AGAIN!"

## Scope (bounded)

ONLY: verify rs#1714 state + file/update the BH5 mirror issue on `esperie-enterprise/kailash-rs`,
body scrubbed per `upstream-issue-hygiene.md` MUST-2/3 (SDK-API surface + minimal-repro shape;
no workspace paths / finding tags / consumer context). No other cross-repo action.
