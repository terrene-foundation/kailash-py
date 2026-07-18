---
type: DECISION
date: 2026-07-05
author: human
display_id: esperie
person_id: esperie
project: dataflow-driver-error-sanitization-1552
topic: cross-repo authorization — kailash-rs READ inspection + cross-SDK issue FILING for the #1552 DML driver-error leak class
phase: codify
---

# AUTHORIZATION — kailash-rs inspection + cross-SDK filing for the #1552 leak class

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (repo-scope-discipline.md User-Authorized Exception — all 5 conditions)

- **Requester:** esperie (user), genuine user turn (2026-07-05).
- **Verbatim instruction:** _"approved, authorize kailash-rs read for cross-SDK inspection, then file to kailash-rs"_
- **Target repo:** `esperie-enterprise/kailash-rs` (private; the Rust SDK — per the
  `reference_kailash_rs_repo_location` memory, NOT `terrene-foundation/kailash-rs`).
  Local clone confirmed at `build/kailash-rs` (git remote =
  `git@github.com:esperie-enterprise/kailash-rs.git`).
- **Bounded action (TWO parts, both explicitly authorized this turn):**
  1. **READ** — inspect the Rust SDK's DataFlow-equivalent for the same bug class
     as kailash-py #1552: raw DB-driver-error VALUES (PG `DETAIL: Key(col)=(value)`
     / `Failing row contains(...)`, MySQL `Duplicate entry 'value'`) rendered
     verbatim into logs / returned errors / raised messages / persisted audit on
     reachable write/DML paths, without a `sanitize_db_error`-equivalent redactor.
  2. **FILE** — open ONE cross-SDK GitHub issue on `esperie-enterprise/kailash-rs`
     if the class is present (per `cross-sdk-inspection.md` Rule 1-2: `cross-sdk`
     label + cross-reference to kailash-py#1552). This satisfies
     `upstream-issue-hygiene.md` MUST-1's same-session human gate.
- **Timestamp:** 2026-07-05 (this session).

## Scope fence (condition 5 — exactly the named actions, nothing more)

- READ is inspection-only: NO writes, NO branches, NO edits to kailash-rs source.
- FILE is exactly ONE cross-SDK issue on the named repo; body scrubbed per
  `upstream-issue-hygiene.md` MUST-2/3 (no consumer/workspace/finding-tag/internal-path
  leakage; scoped to the Rust SDK API surface + minimal repro + cross-ref).
- No incidental reads of other repos; no fix PRs against kailash-rs (a fix is a
  separate dedicated kailash-rs session).

## Disposition

Findings recorded here + surfaced to the user; the cross-SDK issue number recorded
on completion. Any rs REMEDIATION (code fix) is deferred to a dedicated kailash-rs
session — this grant covers inspect + file only.
