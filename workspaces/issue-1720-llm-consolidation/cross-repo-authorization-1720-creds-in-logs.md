# Cross-Repo Authorization Receipt — #1720 creds-in-logs cross-SDK sibling

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** user (jack@integrum.global), in-session turn — verbatim
  instruction "approved" in direct response to the agent's specific offer:
  "To close the cross-SDK loop I need to file an issue on the Rust SDK BUILD
  repo. … May I file it? (yes → I'll journal the grant and file the scrubbed
  issue …)". The agent restated target + action before the user confirmed.
- **Target repo:** esperie-enterprise/kailash-rs (Rust SDK BUILD repo; private).
  Existence + slug verified THIS session via
  `gh repo view esperie-enterprise/kailash-rs` (isPrivate=true), consistent with
  `reference_kailash_rs_repo_location.md` and the prior #1720 authorization
  receipts in this workspace (byok → rs#1881).
- **Action:** file ONE `cross-sdk` GitHub issue requesting the Rust four-axis LLM
  client + provider/MCP error handlers sanitize credential-bearing exception logs
  and connection/webhook URL logs (drop the source-chain backtrace on
  credential-bearing error paths; mask userinfo + path + query on URLs). Mirrors
  the kailash-py #1720 creds-in-logs sweep (kaizen 2.34.1). No code write; a
  single issue only.
- **Timestamp:** 2026-07-17T10:42:14Z.
- **Scope:** exactly one issue on esperie-enterprise/kailash-rs; body scoped to
  the SDK API surface only — no consumer/downstream context, internal paths,
  workspace IDs, or finding tags (upstream-issue-hygiene.md MUST-2). Cross-ref to
  kailash-py #1720 by bare number. No incidental reads of that repo; no code
  changes. Body-of-record: `cross-sdk-creds-in-logs-draft-UNFILED.md`.
- **Filed issue:** esperie-enterprise/kailash-rs#1908
  (https://github.com/esperie-enterprise/kailash-rs/issues/1908), filed
  2026-07-17. Advisory `repo-scope-discipline/MUST-NOT-1` tripwire fired
  post-hoc on the cross-repo `gh` write (it flags ALL cross-repo writes and
  cannot see this grant); adjudicated IN-SCOPE — all five User-Authorized
  Exception conditions met + this receipt (with the `cross-repo-authorized:`
  marker) present BEFORE the command ran. Same disposition as the sibling byok
  filing (rs#1881) earlier this cycle.
