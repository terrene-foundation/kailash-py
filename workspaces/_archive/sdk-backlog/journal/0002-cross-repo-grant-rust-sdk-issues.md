# Cross-Repo Grant (session 2) — file cross-SDK issues on the Rust SDK BUILD repo

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** repo owner (this session's user; genuine human turn)
- **Timestamp:** 2026-07-10
- **Verbatim instruction:** "approved, please release and file the issues to kailash-rs then /codify the pattern. after that /wrapup for fresh session"
- **Target repo:** `esperie-enterprise/kailash-rs` (private Rust SDK BUILD repo, per `reference_kailash_rs_repo_location.md` — NOT terrene-foundation/kailash-rs). Existence + ADMIN access verified via `gh repo view` before this grant.
- **Exact bounded action:** `gh issue create` ONLY, for the cross-SDK-parity issues below; plus a back-link comment on the paired py-side issue (a WRITE on the CWD repo — in-scope).
  1. **NEW (this session's finding):** `bug(dataflow): cross-tenant WRITE via upsert ON CONFLICT DO UPDATE — no tenant predicate (cross-SDK parity)` — the cross-tenant row-theft breach fixed py-side in PR #1650. High value; shared DataFlow architecture.
  2. **#1606 pair:** `bug(dataflow): cache keys omit database-instance identity — cross-DB bleed (cross-SDK keyspace lockstep)`.
  3. **#1510/E pair:** `feat(eatp): origin-authentication — bind agent-declared trace to originating instruction (cross-SDK signing-payload lockstep)`.
- **Scope:** ONLY these issue-creates against ONLY this repo + the paired py-side back-link comments. No incidental reads, no source reads, no other writes.
- **Hygiene:** bodies are SDK-behavior/contract-scoped, minimal-repro shape, NO consumer/downstream/workspace tokens or internal paths (upstream-issue-hygiene MUST-2/3); reference py origin by bare number only.
- **Supersedes context of 0001** (same grant, prior session; not filed then due to an account swap without a named target). This grant names the target explicitly.
