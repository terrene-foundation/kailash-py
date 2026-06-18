---
type: DECISION
slug: filing-authorized-preset-parity
created: 2026-06-01T06:58:03Z
---

# Cross-Repo FILING authorized — kaizen preset parity (esperie-enterprise/kailash-rs)

cross-repo-authorized: esperie-enterprise/kailash-rs

Extends the read/draft grant in 0001 to an explicit FILING for ONE issue.

## Per-issue gate (upstream-issue-hygiene Rule 1) — satisfied this session

- **User directive (verbatim):** "1. please file cross-sdk parity issue into kailash-rs as required."
- **Action:** `gh issue create --repo esperie-enterprise/kailash-rs` — ONE issue:
  kaizen `<provider>_from_env` preset family (12) missing from the Rust catalog.
- **Scrub (Rule 2/3):** body scoped to the Rust API surface + the cross-SDK parity
  contract only. NO kailash-py internal paths, NO workspace ids, NO finding tags
  (F39/F25), NO py issue numbers, NO session timestamps tied to consumer work.
- **Accuracy (feedback_verify_claims_before_durable_write):** gap verified —
  py has 12 `*_from_env` presets; `grep -E '_from_env'` over rs presets.rs = 0
  matches. rs confirmed to ALREADY have azure_openai/bedrock_*/vertex_*/`*_compatible`/
  ollama_default (NOT over-claimed as gaps).
- **Scope (condition 5):** this ONE filing only. No further rs writes without a new gate.
