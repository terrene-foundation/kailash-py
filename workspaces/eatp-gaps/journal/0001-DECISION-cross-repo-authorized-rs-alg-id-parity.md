---
type: DECISION
slug: cross-repo-authorized-rs-alg-id-parity
created: 2026-06-13T07:16:53Z
---

# Cross-Repo Authorization — kailash-rs EATP-08 alg_id parity READ

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (repo-scope-discipline § User-Authorized Exception — all 5 conditions)

1. **User-initiated:** genuine user turn this session (2026-06-13) — the user
   asked "can you run a cross-sdk parity check? it has been some time since we
   ran one", then explicitly authorized the read.
2. **Explicit + specific:** target repo `esperie-enterprise/kailash-rs` (local
   checkout `~/repos/loom/kailash-rs`); bounded action: **READ-only** cross-SDK
   parity check of the EATP-08 v1.1 algorithm-identifier implementation — compare
   registry tokens, top-level `alg_id` wire shape, JCS canonical-byte ordering,
   dispatch semantics (`unsupported-algorithm` / no fall-through), and
   conformance vectors against kailash-py `feat/eatp08-v1.1-conformance`.
3. **Confirmed:** agent restated the bounded read action + asked for the repo
   location; user replied "approved read, its ~/repos/loom/kailash-rs".
4. **Journaled before acting:** THIS receipt lands before any kailash-rs access.
5. **Scoped exactly:** READ-only. No writes, no branches, no `gh issue create`
   against kailash-rs. Any cross-SDK issue filing would need its own per-issue
   human gate (upstream-issue-hygiene Rule 1) — NOT covered by this grant.

## Verbatim user grant

> "approved read, its ~/repos/loom/kailash-rs"
> (in reply to: "Where is kailash-rs on this machine? … I'll journal the
>  authorized read first, then run the parity check.")
