---
type: DECISION
date: 2026-05-30
topic: Cross-repo authorization — Q5 rs-tracker existence check
cross-repo-authorized: esperie-enterprise/kailash-rs
---

# Cross-repo authorization — Q5 kailash-rs tracker check

Per `rules/repo-scope-discipline.md` § User-Authorized Exception (all five conditions):

1. **User-initiated** — user turn 2026-05-30, verbatim: "can you check Q5, i allow you to".
2. **Explicit + specific** — target repo confirmed via AskUserQuestion: `esperie-enterprise/kailash-rs` (the real private rs repo; `terrene-foundation/kailash-rs` does not exist per prior-session F25 trap — org NOT self-substituted, user-confirmed).
3. **Confirmed** — agent restated action + target; user selected "esperie-enterprise/kailash-rs (recommended)" before execution.
4. **Journaled before acting** — this entry + the `cross-repo-authorized: esperie-enterprise/kailash-rs` marker land BEFORE any `gh` command runs.
5. **Scoped exactly** — READ-ONLY only: `gh issue list` / `gh search issues` against `esperie-enterprise/kailash-rs` to determine whether a Nexus-FastAPI-parity tracker (Depends/Request/dependency_overrides + Multipart/SSE/WebSocket) already exists, to resolve #1174 Q5 (cross-SDK marker). NO writes, NO issue filing, NO source reads beyond issue titles/bodies. Filing any rs issue would require a SEPARATE authorization.

Resolves: #1174 analyze Q5 (cross-SDK alignment marker — provide rs tracker URL OR confirm none-exists).
