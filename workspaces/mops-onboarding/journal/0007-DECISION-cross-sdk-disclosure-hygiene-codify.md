---
type: DECISION
date: 2026-07-02
display_id: esperie
---

# DECISION — cross-SDK disclosure-hygiene codify (2026-07-02)

## What was updated and why

**Rule change (global, proposed for loom):** `.claude/rules/cross-sdk-inspection.md`

- **Repo-path correction** (PR #1487): the rule filed cross-SDK issues at `terrene-foundation/kailash-rs`, which does not exist. Corrected to the real private `esperie-enterprise/kailash-rs` (Rule 1 + Example). Sibling fixes: `guides/rule-extracts/git.md` protection table + `guides/deterministic-quality/08-cross-sdk-parity.md` workflow. Root cause: I parroted the wrong path from the rule's own examples + issue #1483's body, ignoring my persisted `reference-kailash-rs-repo-location` memory which already carried the correction.
- **New MUST Rule 6** — public-published artifacts (CHANGELOG/README/docs/package-metadata) MUST NOT name the private Rust SDK repo/org/versions/issues/crate-paths/architecture (disclosure + Foundation Independence, Directive 0). 8-field trust-posture wiring, trigger `public_artifact_private_repo_disclosure`.

**Same-class fixes (autonomous-execution Rule 4), landed BUILD-side:**

- `CHANGELOG.md` — 27 private-Rust-SDK references removed/genericized (PR #1488).
- `README.md` (PyPI long_description) — 3 bare `kailash-rs` refs genericized (codify PR).

**Feature work merged this session (issues #1480/#1481/#1482/#1483):** PACT authz-root re-validation (#1480, PR #1484), hold-resolution disclosure-binding (#1483, PR #1485), ConsentAttestation + disclosure-trace primitives (#1481/#1482, PR #1486). Cross-SDK transparency filed on `esperie-enterprise/kailash-rs`: comment on #1551 (ConsentAttestation), new #1592 (disclosure-trace), under journaled authorization (0006).

## Redteam

reviewer + security-reviewer + cc-architect (parallel) on Rule 6 → MERGE-WITH-FIXES; all applied. Corrected a false "self-referential" premise (cross-sdk-inspection.md is NOT on the allowlist; my earlier `grep | head && echo` check was a shell-logic false positive).

## Anchor

`learning-codified.json::last_codified` advanced to 2026-07-02. The 287 telemetry observations in the backlog are auto-captured test-pattern noise, not codified.
