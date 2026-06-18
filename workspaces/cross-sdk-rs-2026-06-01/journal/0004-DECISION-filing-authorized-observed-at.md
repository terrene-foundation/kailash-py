---
type: DECISION
slug: filing-authorized-action-envelope-observed-at
created: 2026-06-02T02:20:00Z
---

# Cross-Repo FILING authorized — write-envelope observed_at parity (esperie-enterprise/kailash-rs)

cross-repo-authorized: esperie-enterprise/kailash-rs

A per-issue FILING grant (sibling of 0002/0003), for the #1209 cross-SDK parity issue.

## Per-issue gate (repo-scope-discipline § User-Authorized Exception — all five conditions) — satisfied this session

- **Requester:** repo co-owner (this session's user).
- **User directive (verbatim):** "approved the 2 things you surfaced" — where surfaced item #1 was, verbatim from my prior turn: _"the Rust SDK likely has the same write-envelope asymmetry. Filing against `kailash-rs` needs your explicit cross-repo authorization … Want me to prepare that filing next?"_
- **Confirmed:** the specific action + target were stated in my prior turn and the user approved them; this entry restates them before execution.
- **Target:** `esperie-enterprise/kailash-rs` (PRIVATE; existence verified this session via `gh repo view` — `terrene-foundation/kailash-rs` does NOT exist).
- **Action:** `gh issue create --repo esperie-enterprise/kailash-rs` — ONE issue: the write-action envelope's signed timestamp should be exposed as a first-class field (symmetric with the read-receipt's), so a write envelope is independently verifiable from the envelope object alone (Rust equivalent of the kailash-py #1209 fix shipped in `kailash 2.29.0`).
- **Scrub (upstream-issue-hygiene Rule 2/3):** body scoped to the SDK API surface + cross-SDK parity contract only. NO kailash-py internal paths, NO workspace ids, NO finding tags, NO session timestamps tied to consumer work. The py issue number is cited only as the cross-SDK alignment reference (cross-sdk-inspection Rule 2 mandates the cross-reference).
- **Accuracy (feedback_verify_claims_before_durable_write):** the py-side gap is verified (it was the #1209 fix this session, in `delegate.dispatch.SignedActionEnvelope`). The rs-side gap is framed as a parity INQUIRY ("does the Rust write-envelope shape expose the signed timestamp the way the read-receipt does?") — NOT asserted as confirmed, because rs source was not read (repo-scope-discipline: no incidental cross-repo reads).
- **Scope (condition 5):** this ONE filing only. No further rs writes, no rs source reads, without a new gate.

## Outcome receipt

- **Filed:** `esperie-enterprise/kailash-rs#1204` (2026-06-02) — "feat(delegate): write-action envelope should expose observed_at as a first-class field (cross-SDK of kailash-py#1209)", label `cross-sdk`.
- Scope honored: ONE issue, no rs source reads, no further rs writes.
