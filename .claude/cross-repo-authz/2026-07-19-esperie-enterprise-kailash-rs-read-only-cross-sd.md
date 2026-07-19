---
type: cross-repo-authorization-receipt
date: 2026-07-19
timestamp: 2026-07-19T11:04:30.664Z
requester: jack-hong
target: esperie-enterprise/kailash-rs
action: READ-ONLY cross-SDK inspection for the #1844/#1845 cost gaps: hardcoded obsolete-model defaults (gpt-4/gpt-3.5-turbo) in agent configs / pattern factories / provider adapters / node param defaults, and whether the test harness severs the prod LLM key from a default cargo test run. Read agent/provider/LLM-client source + test setup only.
mode: read
---

# Cross-Repo Authorization Receipt

cross-repo-authorized: esperie-enterprise/kailash-rs read

## Bounded action

- **Target repo:** esperie-enterprise/kailash-rs
- **Action (read):** READ-ONLY cross-SDK inspection for the #1844/#1845 cost gaps: hardcoded obsolete-model defaults (gpt-4/gpt-3.5-turbo) in agent configs / pattern factories / provider adapters / node param defaults, and whether the test harness severs the prod LLM key from a default cargo test run. Read agent/provider/LLM-client source + test setup only.
- **Requester (display_id):** jack-hong
- **Authorized at:** 2026-07-19T11:04:30.664Z

## Verbatim user instruction

> i want you to also investigate kailash-rs to see if it has your same gaps. alert me and file if so.

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
