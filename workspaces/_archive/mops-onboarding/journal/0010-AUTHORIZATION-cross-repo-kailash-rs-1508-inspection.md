---
type: DECISION
date: 2026-07-03
author: human
display_id: esperie
project: dataflow-upsert-1508
topic: cross-repo authorization — read-only kailash-rs inspection for the #1508 bug class
phase: redteam
---

# AUTHORIZATION — read-only kailash-rs inspection for the #1508 upsert bug class

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (repo-scope-discipline.md User-Authorized Exception)

- **Requester:** esperie (user), genuine user turn (2026-07-03).
- **Verbatim instruction:** _"approved, /wrapup for fresh session. also check if kailash-rs needs the same bug resolution"_
- **Target repo:** `esperie-enterprise/kailash-rs` (private; the Rust SDK — per `reference_kailash_rs_repo_location` memory, NOT `terrene-foundation/kailash-rs`).
- **Bounded action:** READ-ONLY inspection — determine whether the Rust SDK's DataFlow-equivalent has the same bug class as kailash-py #1508 (SQLite upsert `conflict_on` on a non-UNIQUE field emits `ON CONFLICT` that requires a constraint) and, opportunistically, #1518 (multi-tenant INSERT tenant-injection mis-map).
- **Timestamp:** 2026-07-03 (this session).

## Scope fence

- READ-ONLY. NO writes, NO branches, NO issue/PR filing against kailash-rs. Filing a cross-SDK issue on rs (per `cross-sdk-inspection.md`) would require a SEPARATE explicit user gate per `upstream-issue-hygiene.md` MUST-1 — NOT covered by this receipt.
- Only the named inspection against only the named repo (condition 5). No incidental writes.
- If rs is not locally accessible, inspection is via `gh` read APIs against `esperie-enterprise/kailash-rs` only.

## Disposition

Findings recorded in the session wrap-up + surfaced to the user. Any rs remediation (fix or issue) is deferred to a dedicated kailash-rs session or a separately-gated filing.
