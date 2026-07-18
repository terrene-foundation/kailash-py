# Cross-Repo Grant — file 2 cross-SDK issues on the Rust SDK BUILD repo

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** repo owner (this session's user)
- **Timestamp:** 2026-07-10
- **Verbatim instruction:** "approved" (approving my offer to file the two drafted cross-SDK-parity issues on the Rust SDK BUILD repo; prior turn: "Want me to draft the two cross-SDK issues for your approval" → "approved" to draft; this turn "approved" to file).
- **Target repo:** `esperie-enterprise/kailash-rs` (the private Rust SDK BUILD repo; per reference memory `reference_kailash_rs_repo_location.md` — NOT terrene-foundation/kailash-rs).
- **Exact bounded action:** `gh issue create` x2 ONLY — the two paired cross-SDK-parity issues drafted this session:
  1. `bug(dataflow): cache keys omit database-instance identity — cross-DB bleed (cross-SDK keyspace lockstep)` (#1606 pair)
  2. `feat(eatp): origin-authentication — bind agent-declared trace to originating instruction (cross-SDK signing-payload lockstep)` (#1510/E pair)
- **Scope:** ONLY these two issue-creates against ONLY this repo. No incidental reads, no source reads, no other writes. Issue bodies are SDK-behavior/contract-scoped, minimal-repro shape, no consumer/downstream tokens (upstream-issue-hygiene MUST-2/3), reference the py origin by bare number.
- **Cross-reference back:** after filing, add a comment on the py-side #1606 / #1510 linking the rs issue numbers (a WRITE on the CWD repo — in-scope).
</content>
