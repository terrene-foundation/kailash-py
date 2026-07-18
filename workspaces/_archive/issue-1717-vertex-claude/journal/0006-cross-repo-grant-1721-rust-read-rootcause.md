---
type: DECISION
date: 2026-07-14
author: human
project: issue-1717-vertex-claude
topic: "Cross-repo READ grant — Rust SDK from_env/legacy + four-axis design, for #1721 root-cause analysis"
phase: redteam
tags:
  [cross-sdk, "1721", "1720", cross-repo-grant, from-env, four-axis, root-cause]
relates_to: 0005-DISCOVERY-1721-rust-legacy-precedence-read
---

# Cross-repo READ grant (session 2026-07-14) — #1721 root-cause

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (verbatim user directive)

User turn (2026-07-14), re: my #1721 recommendation "accept the legacy-tier
divergence + document it":

> "2. why legacy-tier? why not make it pristine? what is the long term optimal
> root-cause fix? I authorize you to cross-repo read."

## Restated scope (agent restatement — condition 3)

- **Target repo:** `esperie-enterprise/kailash-rs` (Rust SDK), local clone at
  `/Users/esperie/repos/kailash/build/kailash-rs`.
- **Action:** READ-ONLY. No writes, no branches, no issues, no PRs on the Rust repo.
- **Bounded to:** the LLM env-based configuration surface only — the Rust
  equivalents of Python's `from_env.py` (`LEGACY_KEY_ORDER` / legacy auto-detect
  if-let chain), the four-axis `LlmClient` / deployment-resolution design, and
  the preset registry — sufficient to answer: why does a per-SDK legacy
  auto-detect tier exist, what is the pristine/canonical design, and what is the
  long-term root-cause fix (its relationship to #1720's legacy-layer retirement).
- **No incidental reads** outside that surface.

## Why journaled first

Per `repo-scope-discipline.md` User-Authorized Exception (all five conditions):
user-initiated ✓, explicit+specific ✓ (restated above), confirmed ✓ (user's
direct authorization this turn), journaled-before-acting ✓ (this entry, written
BEFORE the read), scoped-exactly ✓ (LLM env-config surface only). This receipt
is the audit trail distinguishing an authorized read from an unauthorized one.

## For Discussion

1. Is the legacy per-SDK auto-detect tier a genuine feature users depend on, or
   an organic accretion that the four-axis `from_deployment`/`from_env` canonical
   path should subsume (making #1721 a symptom of #1720, not a separate bug)?
2. If the pristine design is a single canonical env-resolution shared across both
   SDKs, what is the migration/deprecation path for the Azure + 6-provider
   divergence without a hard break (`zero-tolerance.md` Rule 6a)?
