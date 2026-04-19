# DECISION — /codify extracted #498 + #462 knowledge into a new Kaizen wire-layer skill

**Date:** 2026-04-19
**Workspace:** issue-498-llm-deployment (knowledge spans #498, #462; #480 also in window but DataFlow-scoped)
**Scope:** Sessions since last codify 2026-04-16 (3-day window, 41 commits)

## Decision

Extract the `kaizen.llm.LlmClient` wire-layer knowledge into a single new skill file `skills/04-kaizen/kaizen-llm-deployment.md` rather than scattering it across `kaizen-multi-provider.md` (Delegate-focused) or adding to `kaizen-specialist.md` (would exceed 400-line cap).

## Alternatives considered

1. **Inline in `kaizen-specialist.md`.** Rejected — specialist would cross 300 lines with detail that most Kaizen work doesn't need (this is a lower-level surface beneath Delegate).
2. **Append to `kaizen-multi-provider.md`.** Rejected — that file documents the `kaizen_agents.Delegate` + `StreamingChatAdapter` surface, which is a distinct higher-level abstraction. Mixing the wire layer there would conflate two API surfaces.
3. **New rule file instead of skill file.** Rejected — the wire-layer patterns are domain-specific recipes ("how to add embed for Mistral", "how to wire complete() when it lands"), not universal MUST rules. Rules would over-generalize.

## What was NOT codified (and why)

- **Redteam HIGH: remove `NotImplementedError` stub on `complete()`** — already covered by `rules/zero-tolerance.md` Rule 2 + `rules/orphan-detection.md` Rule 3. Commit `8dbb6e1c` is cited in the new skill for evidence.
- **Multi-round redteam convergence (#498 rounds 1 → 2 → 5)** — natural output of the `/redteam` gate; existing rule already captures.
- **Kaizen agent budget exhaustion mid-implementation (today)** — one occurrence; premature. Journaled for recurrence.
- **`isolation: worktree` edits landing in main (today)** — root cause unclear, one occurrence; insufficient data.
- **Cross-SDK byte-identical wire shapers** — `rules/cross-sdk-inspection.md` D6 covers "semantics match"; the byte-identical tightening is wire-shaper-specific, captured in the new skill.

## Proposal append

Per `rules/artifact-flow.md` append-not-overwrite protocol: `.claude/.proposals/latest.yaml` had status `pending_review` from the 2026-04-16 codify. Three new change entries appended (skill create + SKILL.md link + specialist cross-ref). Status stays `pending_review`. Prior 4 entries from 2026-04-16 preserved intact.

## Verification

- `kaizen-llm-deployment.md` created — 140 LOC
- `skills/04-kaizen/SKILL.md` edited — new "LLM Wire Layer" section added
- `agents/frameworks/kaizen-specialist.md` edited — cross-reference added, still 201 LOC (under 400 cap)
- `.claude/.proposals/latest.yaml` — 3 entries appended, status unchanged
- `.claude/learning/learning-codified.json` — rewritten with 2026-04-19 window, 3 actions, 6 not-codified decisions logged

## Next action

Human at `loom/` runs `/sync` Gate 1 to classify the 7 pending entries (4 from 2026-04-16 + 3 from 2026-04-19) as global vs variant, then Gate 2 distributes to USE templates.
