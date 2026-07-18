---
type: DECISION
date: 2026-07-14
author: human
project: issue-1717-vertex-claude
topic: "Cross-repo READ grant EXTENSION — Rust DataFlow credential-callback (rs#1810) for #1737 implementation"
phase: implement
tags:
  [cross-sdk, "1737", cross-repo-grant, dataflow, credential-callback, rs-1810]
relates_to: 0006-cross-repo-grant-1721-rust-read-rootcause
---

# Cross-repo READ grant EXTENSION (session 2026-07-14) — #1737

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (user directive)

The user selected "Implement #1737 now" from an AskUserQuestion whose option text
read: _"A real feature shard — I'd analyze the Rust impl first (needs a grant
extension) then implement + test."_ Selecting that option authorizes the grant
extension below for #1737's Rust read (distinct from the journal/0006 grant,
which is scoped to the LLM env-config surface for #1721).

## Restated scope (agent restatement — condition 3)

- **Target repo:** `esperie-enterprise/kailash-rs`, local clone at
  `/Users/esperie/repos/kailash/build/kailash-rs`.
- **Action:** READ-ONLY. No writes/branches/issues/PRs on the Rust repo.
- **Bounded to:** the DataFlow per-connection credential-callback surface — the
  Rust implementation of rs#1810 (the connection/pool config, the per-physical-
  connection credential/token callback, its invocation points on
  initial/recycled/overflow/reconnect), sufficient to match the SEMANTICS in the
  Python #1737 implementation.
- **No incidental reads** outside that surface. (This is a separate surface from
  the journal/0006 LLM env-config grant; the two are independently scoped.)

## For Discussion

1. Does the Rust callback return a raw password, a resolved DSN, or a typed
   credential object — and does the Python surface (SQLAlchemy `do_connect` /
   asyncpg dynamic-password) map onto the same contract shape?
