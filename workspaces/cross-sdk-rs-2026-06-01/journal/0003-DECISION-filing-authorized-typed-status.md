---
type: DECISION
slug: filing-authorized-typed-status-gateway
created: 2026-06-01T13:25:20Z
---

# Cross-Repo FILING authorized — typed-status gateway parity (esperie-enterprise/kailash-rs)

cross-repo-authorized: esperie-enterprise/kailash-rs

A second explicit per-issue FILING grant (sibling of 0002), for the #1218 cross-SDK parity issue.

## Per-issue gate (upstream-issue-hygiene Rule 1) — satisfied this session

- **Requester:** repo co-owner (this session's user).
- **User directive (verbatim):** "please file it for me as gh issue in kailash-rs"
- **Target:** `esperie-enterprise/kailash-rs` (PRIVATE; existence verified this session via `gh repo view` — `terrene-foundation/kailash-rs` does NOT exist).
- **Action:** `gh issue create --repo esperie-enterprise/kailash-rs` — ONE issue: gateway-execute path should honor a handler-raised typed HTTP status instead of collapsing to 500 (Rust equivalent of the kailash-py #1218 fix shipped in `kailash 2.28.4`).
- **Scrub (upstream-issue-hygiene Rule 2/3):** body scoped to the SDK API surface + cross-SDK parity contract only. NO kailash-py internal paths, NO workspace ids, NO finding tags, NO session timestamps tied to consumer work. The py issue number is cited only as the cross-SDK alignment reference (cross-sdk-inspection Rule 2 mandates the cross-reference).
- **Accuracy (feedback_verify_claims_before_durable_write):** the py-side gap is verified (it was the #1218 fix this session, in `WorkflowAPI`). The rs-side gap is framed as a parity INQUIRY ("does the Rust gateway-execute path have the equivalent?") — NOT asserted as confirmed, because rs source was not read (repo-scope-discipline: no incidental cross-repo reads).
- **Scope (condition 5):** this ONE filing only. No further rs writes, no rs source reads, without a new gate.
