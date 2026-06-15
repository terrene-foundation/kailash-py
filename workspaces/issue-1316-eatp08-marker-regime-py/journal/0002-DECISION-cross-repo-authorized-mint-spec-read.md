# 0002 — DECISION: cross-repo authorized read of mint spec

**Phase**: /analyze · **Date**: 2026-06-15 · **Issue**: #1316

cross-repo-authorized: terrene-foundation/mint

- **Requester**: user (this session, genuine user turn).
- **Verbatim instruction**: "check ~/repos/terrene/mint"
- **Target**: `~/repos/terrene/mint` (the EATP standards tracker repo).
- **Action (bounded)**: READ-ONLY — locate + read `08-algorithm-identifier.md`
  §4.3.1/§4.3.2 (signed-marker shape) and §4.5/§4.6 (monotonic-upgrade semantics) to lock
  Shard 1's marker field shape and size Shard 3's `monotonic-upgrade-violation` enforcer.
- **Scope**: read only the EATP-08 algorithm-identifier spec (+ adjacent conformance refs if
  cited). No writes, no `gh`, no edits to the mint repo.
- **Rule basis**: `repo-scope-discipline.md` § User-Authorized Exception — user-initiated +
  explicit + journaled-before-acting. Receipt lands BEFORE the read command runs.
