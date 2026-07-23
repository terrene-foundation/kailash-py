---
type: cross-repo-authorization-receipt
date: 2026-07-23
timestamp: 2026-07-23T11:35:46.856Z
requester: jack-hong
target: esperie-enterprise/kailash-rs
action: read-only inspection: does the Rust SDK autonomous-agent equivalent create a checkpoint/state directory in the caller's cwd on construction (Rust analog of the kaizen-agents checkpoint-dir cwd-litter defect); grep/read only, no writes, no issue filing
mode: read
---

# Cross-Repo Authorization Receipt

cross-repo-authorized: esperie-enterprise/kailash-rs read

## Bounded action

- **Target repo:** esperie-enterprise/kailash-rs
- **Action (read):** read-only inspection: does the Rust SDK autonomous-agent equivalent create a checkpoint/state directory in the caller's cwd on construction (Rust analog of the kaizen-agents checkpoint-dir cwd-litter defect); grep/read only, no writes, no issue filing
- **Requester (display_id):** jack-hong
- **Authorized at:** 2026-07-23T11:35:46.856Z

## Verbatim user instruction

> user approved the cross-SDK inspection of kailash-rs for the checkpoint-dir analog (session cont-15, restated + approved)

## Five-condition attestation (repo-scope-discipline.md § User-Authorized Exception)

- condition_1_user_initiated: REQUIRED — a genuine user turn
- condition_2_explicit_specific: REQUIRED — names the target repo AND the exact bounded READ
- condition_3_confirmed: REQUIRED — the ceremony restated action+target and the user confirmed yes/no BEFORE this write
- condition_4_receipt_before_acting: DOWNGRADED (READ tier) — one-line affordance receipt; a read leaves no durable trace in the target
- condition_5_scoped_exactly: REQUIRED — only the named read against only the named repo

<!--
  This receipt is the ONLY distinguisher between an authorized and an
  unauthorized cross-repo action. It is written by
  .claude/bin/cross-repo-authorize.mjs AFTER the user confirmed the restated
  action+target in chat, and BEFORE the action runs. The hook
  (violation-patterns.js::hasCrossRepoAuthorizationReceipt) greps this file's
  marker line within its mtime window; commit it for durable team audit.
-->
