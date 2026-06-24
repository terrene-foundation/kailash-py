# 0002 — DECISION: Cross-repo authorization to file ONE GH issue into loom

**Date:** 2026-06-23 (UTC)
**Author:** agent (recording a user-directed cross-repo authorization)
**Workspace:** mops-onboarding (Phase 2-loom)

cross-repo-authorized: esperie-enterprise/loom

## Authorization record (per `rules/repo-scope-discipline.md` § User-Authorized Exception)

- **Requester:** the user (genesis owner esperie), this kailash-py session.
- **Target repo:** `esperie-enterprise/loom` (resolved from the loom checkout's `origin`
  remote: `git@github.com:esperie-enterprise/loom.git`).
- **Authorized action (scoped exactly):** file ONE scrubbed GitHub issue recommending loom
  distribute the genesis-bootstrap runbook (`guides/co-setup/11-genesis-ceremony.md`) — or the
  new `45-genesis-bootstrap` skill from the pending BUILD→loom proposal — downstream to BUILD/USE
  repos, and `/sync-to-use` the onboarding suite to ALL downstream USE templates. No other loom
  writes; no loom source edits; no PRs.
- **Verbatim instructions:**
  - Program (approved 2026-06-23, `workspaces/mops-onboarding/00-PROGRAM.md`): _"file 2 into loom
    as gh issue."_ + _"the proposal for loom should remind it to roll out to all downstream use as
    well."_
  - This session — user answered the Phase-2 scope question _"Both targets now"_, then approved
    the drafted issue body with _"file it, /wrapup for fresh session"_.
- **Confirmation:** the agent restated the action + target + presented the full issue body; the
  user confirmed with _"file it"_ BEFORE execution.
- **Timestamp:** 2026-06-23T16:25Z (receipt landed before the `gh issue create` command).
- **Disclosure scrub:** issue body carries NO operator key material / person_id / verified_id;
  `terrene-foundation` / `esperie-enterprise` / canonical guide paths are legitimate Foundation
  paths (not templated) per the program's scrub note + `upstream-issue-hygiene.md`.

## Scope boundary

This authorization covers the single loom issue ONLY. The paired Phase-2 target
(`esperie-enterprise/kailash-rs` enrollment + suite rollout) is separately authorized by the
same _"Both targets now"_ answer but is DEFERRED to a fresh session per the user's
_"/wrapup for fresh session"_ — its own `cross-repo-authorized: esperie-enterprise/kailash-rs`
receipt MUST be landed in that session before its first command.
