# GRANT — cross-repo Rust SDK cross-SDK handoff filings (#1779 + #1727)

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** operator (jack@terrene.foundation), this session.
- **Target repo:** esperie-enterprise/kailash-rs (verified existing via `gh repo view`, 2026-07-18).
- **Action (scoped exactly):** file EXACTLY two GitHub issues via `gh issue create` —
  1. `#1727` cross-SDK defect: openai chat four-axis shaper must emit `max_completion_tokens` for GPT-5/o-series.
  2. `#1779` cross-SDK parity-verification: confirm `governance_required` posture semantics align (per-deployment Rust vs process/env Python) for EATP D6.
     No other cross-repo reads, writes, comments, or PRs.
- **Timestamp:** 2026-07-18 (Asia/Singapore).
- **Verbatim instruction:** operator selected "File both (drafts in workspace)" to the question
  "The two Rust cross-SDK handoffs (#1727 concrete defect; #1779 posture parity-verification)
  are still authorized and independent of the provider-layer decision. File them now?"
  (AskUserQuestion, this session). Earlier in the session the operator also selected
  "Authorize both Rust issues".
- **Scrubbed bodies:** `workspaces/issue-1720-llm-consolidation/04-validate/rust-handoff-drafts.md`
  (SDK-API-surface only; no consumer/internal-path/finding-tag leakage per upstream-issue-hygiene.md).
- **Conditions (repo-scope-discipline.md User-Authorized Exception):** user-initiated ✓,
  explicit+specific ✓, confirmed ✓, journaled-before-acting ✓ (this entry precedes the gh commands),
  scoped-exactly ✓.

---

## Fresh confirmation receipt (execution session, 2026-07-18)

Per `handoff-completion.md` MUST-3 + `repo-scope-discipline.md` condition 3, a
FRESH in-session confirmation was obtained before acting (the original grant
predated a context boundary):

- **Restated ask:** "File two cross-SDK issues on esperie-enterprise/kailash-rs
  — (A) #1727 max_completion_tokens defect; (B) #1779 posture parity-verification."
- **User response (AskUserQuestion, this session):** "File both now".
- **Existence check:** `gh repo view esperie-enterprise/kailash-rs` → exists, private (2026-07-18).
- **Scope:** EXACTLY the two `gh issue create` calls below; no other cross-repo action.

### Filed (execution receipt, 2026-07-18)

Both issues created this session (verified by `gh issue create` return URLs):

- **Issue A (#1727 equiv):** esperie-enterprise/kailash-rs#1932 — openai chat shaper max_completion_tokens for GPT-5/o-series.
- **Issue B (#1779 equiv):** esperie-enterprise/kailash-rs#1933 — governance_required posture parity (EATP D6).

Cross-SDK loop CLOSED. Scope honoured exactly (two issues, no other cross-repo action).
