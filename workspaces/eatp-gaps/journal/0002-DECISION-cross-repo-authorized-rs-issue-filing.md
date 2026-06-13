---
type: DECISION
slug: cross-repo-authorized-rs-issue-filing
created: 2026-06-13T07:50:55Z
---

# Cross-Repo Authorization — file EATP-08 v1.1 sibling issue on kailash-rs

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (repo-scope-discipline § User-Authorized Exception — all 5 conditions)

1. **User-initiated:** genuine user turn (2026-06-13) — the user replied "file
   and vendor" to the agent's offer "Want me to draft the Rust sibling issue
   body for your review?".
2. **Explicit + specific:** target repo `esperie-enterprise/kailash-rs`;
   bounded action: file ONE GitHub issue — the cross-SDK sibling of #1304 (EATP-08
   v1.1 alg_id adoption: advance rs `crates/eatp/src/algorithm.rs` from the
   `ed25519+sha256` scaffold to the `eatp-v1` registry + top-level `alg_id`
   string wire shape + dispatch + D2d witnessed legacy path). One issue, no PRs,
   no code writes to rs.
3. **Confirmed:** user said "file and vendor" — explicit approval to file.
4. **Journaled before acting:** THIS receipt lands before `gh issue create`.
5. **Scoped exactly:** ONE issue filing only. The body is scrubbed per
   upstream-issue-hygiene MUST-2/3 (BUILD→BUILD; no consumer names, no workspace
   paths, no finding tags — pure SDK-API + spec surface). No code writes; any
   follow-up PR against rs needs its own grant.

## Verbatim user grant

> "file and vendor"
> (in reply to: "Want me to draft the Rust sibling issue body for your review?")
