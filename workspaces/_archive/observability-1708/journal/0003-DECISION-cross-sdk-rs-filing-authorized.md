---
type: DECISION
date: 2026-07-13
slug: cross-sdk-rs-filing-authorized
workspace: observability-1708
---

# DECISION — User-authorized cross-SDK issue filing on the Rust SDK

cross-repo-authorized: esperie-enterprise/kailash-rs

## Authorization (repo-scope-discipline.md § User-Authorized Exception — all five)

- **Requester:** user (jack@kailash.ai), genuine user turn.
- **Target repo:** `esperie-enterprise/kailash-rs` (private; existence-checked this
  session via `gh repo view` → accessible).
- **Action (exact, bounded):** file ONE GitHub issue — a cross-SDK alignment /
  code-improvement issue carrying the #1708 metric-registry-orphan +
  cross-tree-test-sweep lessons, scrubbed per `upstream-issue-hygiene.md` MUST-2/3
  (SDK-API-surface only; no kailash-py identifiers, workspace paths, or finding tags).
- **Confirmation:** agent restated the action + target in the prior turn ("authorize
  it and I'll draft a scrubbed, five-section body … for your approval before filing");
  user confirmed.
- **Verbatim instruction:** "approved. then /wrapup. after that I need you to focus
  on issue 1717 in fresh session".
- **Scope:** ONLY this one issue on ONLY this repo; no incidental reads of rs source,
  no other rs writes.

## Content provenance

Cross-SDK alignment from the kailash-py #1708 observability program (5-package PyPI
release, 2026-07-13). Both lessons are language-agnostic; the Rust SDK is a sibling
Foundation BUILD repo with an equivalent metrics + orphan-detection surface.
