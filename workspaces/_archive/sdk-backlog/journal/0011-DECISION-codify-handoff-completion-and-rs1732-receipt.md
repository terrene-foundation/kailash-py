# DECISION — Codify handoff-completion + rs#1732 filing receipt

**Date:** 2026-07-11
**Phase:** 05-codify
**Type:** DECISION

## Receipt — cross-repo action executed (grant journal/0010)

Filed **rs#1732** on `esperie-enterprise/kailash-rs` (BH5 trip-and-hold governance
circuit-breaker — cross-SDK parity with kailash-py 2.48.0), body scrubbed to the SDK-API
surface per `upstream-issue-hygiene.md` MUST-2/3. Discovered the rs side had scoped BH5 to
rate-limit enforcement (rs#1629, closed); the trip-and-hold breaker + the prune-when-unset
signed-model byte contract are the genuine parity gap. Back-linked py #1510 (bare rs number,
role-only per `cross-sdk-inspection.md` Rule 6) AND corrected the earlier misreference (rs#1714
is BH3 origin-auth, NOT BH5). Verified rs#1713 (#1606 mirror) + rs#1729 (#1601 mirror) already
open from prior sessions. Handoff doc renamed `rs-1714-…` → `rs-1732-circuit-breaker.md`.

## What was codified

NEW baseline rule **`rules/handoff-completion.md`** (priority:0, scope:baseline):

- **MUST-1** — a downstream-required action (cross-repo issue/PR, upstream handoff) is done
  only when EXECUTED or EXPLICITLY surfaced as a pending action naming target + action +
  authorization; a local note left implied-done is BLOCKED.
- **MUST-2** — a cross-repo artifact is referenced as existing ONLY after created/verified
  this session (the cross-repo sibling of `verify-claims-before-write.md`).
- **MUST-3** — needs-authorization means ASK specifically (restate target + action), never
  stop at a local note.

## Rule-10 named-rationale (baseline addition)

`rule-authoring.md` Rule 10 fires on new priority:0 content. Path (b) named-rationale: this
codifies a trust-eroding failure the co-owner flagged with "NEVER LET IT HAPPEN AGAIN"; the
three MUST clauses are ONE non-decomposable behavioral contract (delivered-or-surfaced +
verified-reference + specific-ask); authored tight (98 lines, minimal load-bearing clauses,
depth in the DO/DO-NOT). Not on the self-referential-codify allowlist → no mandatory
multi-agent redteam. Distribution: BUILD→loom proposal append (change 25, global); loom
Gate-1 evaluates per-CLI proximity-band at distribution.

## Why (provenance)

The BH5 session prepared a LOCAL Rust-SDK handoff doc + referenced rs#1714 as the BH5 tracker
(wrong — BH3) + reported "handoff prepared" without filing any rs issue — leaving the human to
infer and drive the cross-SDK completion. Verbatim directive in `journal/0010`. Sibling of
`build-repo-release-discipline.md` ("done means released, not merged") extended to cross-repo
handoffs.
