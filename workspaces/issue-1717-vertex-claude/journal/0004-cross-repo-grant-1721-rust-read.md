---
type: DECISION
date: 2026-07-14
author: human
project: issue-1717-vertex-claude
topic: user-authorized cross-repo READ of the Rust SDK for #1721 deepseek legacy-precedence parity
phase: redteam
verified_id: (solo, un-enrolled public repo)
person_id: (solo)
display_id: (solo)
tags: [cross-repo, grant, "1721", cross-sdk, read-only]
relates_to: 0002-parity-delta-legacy-vs-four-axis
---

# Cross-repo READ grant — Rust SDK, #1721 deepseek legacy precedence

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (repo-scope-discipline § User-Authorized Exception — all five conditions)

- **Requester (user-initiated):** the co-owner, verbatim: _"approved read on 1721"_
  (in direct reply to my surfacing that #1721's remaining item — whether the Rust
  SDK's kaizen from_env legacy precedence includes `DEEPSEEK_API_KEY` — needs a
  cross-repo read).
- **Target repo:** the Rust SDK — resolver key `build.rs`; real path
  `esperie-enterprise/kailash-rs` (private) per the operator memory
  `reference_kailash_rs_repo_location`.
- **Exact bounded action:** READ-ONLY inspection of the Rust kaizen `from_env`
  legacy per-provider-key precedence order (the `crates/kailash-kaizen/src/llm/`
  from_env / deployment source) to determine whether `DEEPSEEK_API_KEY` is present
  in the legacy auto-detect tier. NO write, NO issue filing, NO other file reads.
- **Confirmed:** the user's explicit "approved read on 1721" is the confirmation;
  scope restated here before acting.
- **Journaled before acting:** this entry lands BEFORE any command runs against
  the Rust repo (the receipt that distinguishes an authorized read from an
  unauthorized one).
- **Scoped exactly:** only the deepseek-legacy-precedence question for #1721.

## Disposition after read
- If Rust legacy precedence INCLUDES deepseek → regenerate
  `rust_from_env_precedence.json` with the deepseek key + remove the strict-xfail
  (the divergence is resolved; both SDKs match).
- If Rust legacy precedence EXCLUDES deepseek → the strict-xfail is correct as-is
  (Python-ahead, pending Rust adoption); #1721 stays open on the Rust side.
