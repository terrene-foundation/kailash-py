# Cross-Repo Grant (session 3) — post cross-SDK lockstep handoffs to the Rust SDK repo

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** repo owner (this session's user; genuine human turn).
- **Timestamp:** 2026-07-10
- **Verbatim instruction:** "on 1510 and 1590, kailash-rs has done their part, and needs Python re-pin of the two signing pre-images for the former and subject_hash vectors via kailash-py #1590. The corresponding kailash-rs issues are 1707 and 1667. Please update your instructions into these issues and i will get kailash-rs to read them." + explicit confirm-gate selection this session authorizing: rs#1707+rs#1667 handoffs, #1601 rs parity handoff, and #1532 (plan-first).
- **Target repo:** `esperie-enterprise/kailash-rs` (private Rust SDK BUILD repo, per `reference_kailash_rs_repo_location.md` — NOT terrene-foundation/kailash-rs).
- **Exact bounded actions (each body shown to the user + approved BEFORE the write, per `upstream-issue-hygiene.md` MUST-1):**
  1. `gh issue comment 1707 --repo esperie-enterprise/kailash-rs` — the Python-reference signing pre-images for BH3 origin-auth (paired with py #1510). Scrubbed, SDK-public-API-only.
  2. `gh issue comment 1667 --repo esperie-enterprise/kailash-rs` — the RFC 8785 subject_hash golden vectors Python pinned (paired with py #1590). Scrubbed.
  3. `gh issue comment <N> --repo esperie-enterprise/kailash-rs` — soft_delete/versioned parity-verification brief (paired with py #1601). Target issue number resolved at post-time; scrubbed.
- **#1532 disposition:** PLAN-FIRST only this session — no cross-repo read/write until the sharded migration plan + the correct `delegate-connectors` source-repo path are surfaced and approved. The source repo did not resolve under terrene-foundation/ or esperie-enterprise/ on probe; the path is an open question for the user.
- **Scope:** ONLY these issue comments against ONLY this repo, plus paired py-side back-link comments (CWD-repo writes, in-scope). No incidental reads, no source reads, no other writes. Each rs body is verified byte-for-byte against py ground truth (`verify-claims-before-write.md`) and scrubbed of consumer/workspace/finding tokens (`upstream-issue-hygiene.md` MUST-2).
- **Supersedes context of 0001/0002** (prior sessions' grants for the same cross-SDK program; this grant covers the 1510/1590/1601 handoff wave specifically).
