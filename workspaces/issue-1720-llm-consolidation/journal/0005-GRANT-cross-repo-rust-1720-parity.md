# GRANT — cross-repo Rust SDK #1720 legacy-provider + BYOK parity filing

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** operator, this session (AskUserQuestion answer, 2026-07-18).
- **Target repo:** esperie-enterprise/kailash-rs (verified existing this session via `gh repo view`).
- **Action (scoped exactly):** file EXACTLY ONE GitHub issue via `gh issue create` —
  cross-SDK inspection of the Rust SDK's legacy LLM-provider layer for the same
  retirement (#1720) + the BYOK header-injection parity surface flagged in the
  Wave-2 /analyze scoping. No cross-repo reads, no other writes, no PRs.
- **Restated + confirmed:** the AskUserQuestion "#1720 is cross-sdk labeled … Authorize
  it?" → operator selected "Authorize — file it" (fresh in-session confirmation naming
  target + action).
- **Timestamp:** 2026-07-18 (Asia/Singapore).
- **Body:** scrubbed to the SDK-API surface per upstream-issue-hygiene.md (no consumer
  names / internal paths / finding tags); Rust SDK referenced by role; `cross-sdk` label.
- **Conditions (repo-scope-discipline User-Authorized Exception):** user-initiated ✓,
  explicit+specific ✓, confirmed ✓, journaled-before-acting ✓ (this entry precedes the
  gh command), scoped-exactly ✓.

### Filed (execution receipt, 2026-07-18)

Issue created this session (verified by `gh issue create` return URL):
- **esperie-enterprise/kailash-rs#1945** — retire redundant legacy LLM-provider layer
  + verify BYOK header-injection parity (cross-SDK of py #1720).

Scope honoured exactly (one issue, no cross-repo reads/other writes). Loop closed.
