# Cross-Repo Authorization Receipt — #1720 BYOK header-injection cross-SDK sibling

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** user (jack@researchroom.sg), in-session turn — verbatim
  instruction "approved" in direct response to the agent's specific offer:
  "file the cross-SDK draft after you glance at it" (the four-axis BYOK
  header-injection parity issue). The user reviewed/edited the drafted body
  (`cross-sdk-byok-draft-UNFILED.md`) before approving.
- **Target repo:** esperie-enterprise/kailash-rs (Rust SDK BUILD repo; private).
  Existence + slug verified this session via `gh repo view esperie-enterprise/kailash-rs`
  (isPrivate=true), consistent with `reference_kailash_rs_repo_location.md` and the
  prior #1720 / #1727 authorization receipts in this workspace.
- **Action:** file ONE `cross-sdk` GitHub issue requesting the Rust four-axis LLM
  client validate a per-request BYOK `api_key` for control-char/CRLF/non-ASCII
  header-injection at parity across BOTH BYOK entry points (the direct
  completion-override path AND the deployment-resolution path), routing both
  through a single shared validator. Mirrors the kailash-py #1720 fix. No code
  write; a single issue only.
- **Timestamp:** 2026-07-17 (session date).
- **Scope:** exactly one issue on esperie-enterprise/kailash-rs; body scoped to
  the SDK API surface only — no consumer/downstream context, internal paths,
  workspace IDs, or finding tags (upstream-issue-hygiene.md MUST-2). Cross-ref to
  kailash-py #1720 by bare number. No incidental reads of that repo; no code changes.
- **Filed issue:** esperie-enterprise/kailash-rs#1881
  (https://github.com/esperie-enterprise/kailash-rs/issues/1881), filed
  2026-07-17. Advisory `repo-scope-discipline/MUST-NOT-1` tripwire fired
  post-hoc on the cross-repo `gh` write (it flags ALL cross-repo writes and
  cannot see this grant); adjudicated IN-SCOPE — all five User-Authorized
  Exception conditions met + this receipt present before the command ran.
