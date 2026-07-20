---
type: cross-repo-authorization-receipt
date: 2026-07-20
timestamp: 2026-07-20T12:56:14.238Z
requester: Jack Hong
target: esperie-enterprise/kailash-rs
action: file 2 cross-SDK issues: (1) broader V3Complete delegation signing-payload reference vectors (real-value domains, >=3 cases + sentinels per domain) to unblock kailash-py #1841-S2b; (2) matching fail-closed non-ASCII guard on RevocationEvent delegation_id (cross-SDK lockstep for kailash-py #1842 revocation-ledger fix)
mode: write
---

# Cross-Repo Authorization Receipt

cross-repo-authorized: esperie-enterprise/kailash-rs write

## Bounded action

- **Target repo:** esperie-enterprise/kailash-rs
- **Action (write):** file 2 cross-SDK issues: (1) broader V3Complete delegation signing-payload reference vectors (real-value domains, >=3 cases + sentinels per domain) to unblock kailash-py #1841-S2b; (2) matching fail-closed non-ASCII guard on RevocationEvent delegation_id (cross-SDK lockstep for kailash-py #1842 revocation-ledger fix)
- **Requester (display_id):** Jack Hong
- **Authorized at:** 2026-07-20T12:56:14.238Z

## Verbatim user instruction

> approved — explicit yes to the restated cross-repo write ceremony: file the 2 cross-SDK issues on esperie-enterprise/kailash-rs with the drafted bodies

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
