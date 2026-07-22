---
type: cross-repo-authorization-receipt
date: 2026-07-22
timestamp: 2026-07-22T09:44:56.296Z
requester: jack-hong
target: esperie-enterprise/kailash-rs
action: file the #1912-equivalent trust subject-binding + chain-state signing issue (scrubbed, SDK-API-surface only)
mode: write
---

# Cross-Repo Authorization Receipt

cross-repo-authorized: esperie-enterprise/kailash-rs write

## Bounded action

- **Target repo:** esperie-enterprise/kailash-rs
- **Action (write):** file the #1912-equivalent trust subject-binding + chain-state signing issue (scrubbed, SDK-API-surface only)
- **Requester (display_id):** jack-hong
- **Authorized at:** 2026-07-22T09:44:56.296Z

## Verbatim user instruction

> User authorized via AskUserQuestion ('Authorize the filing' — file the Rust-SDK-equivalent subject-binding issue, SDK-API-surface-only) and confirmed 'approved'.

## Five-condition attestation (repo-scope-discipline.md § User-Authorized Exception)

- condition_1_user_initiated: REQUIRED — a genuine user turn (see verbatim below)
- condition_2_explicit_specific: REQUIRED — names the target repo AND the exact bounded action
- condition_3_confirmed: REQUIRED — the ceremony restated action+target and the user confirmed yes/no BEFORE this write
- condition_4_receipt_before_acting: SATISFIED — THIS receipt is the durable witness, written BEFORE the command runs
- condition_5_scoped_exactly: REQUIRED — only the named action against only the named repo

<!--
  This receipt is the ONLY distinguisher between an authorized and an
  unauthorized cross-repo action. It is written by
  .claude/bin/cross-repo-authorize.mjs AFTER the user confirmed the restated
  action+target in chat, and BEFORE the action runs. The hook
  (violation-patterns.js::hasCrossRepoAuthorizationReceipt) greps this file's
  marker line within its mtime window; commit it for durable team audit.
-->
