---
name: wrapup
description: "Write session notes before ending. Captures context for next session."
---

Write session notes to preserve context for the next session. The next session starts from zero — these notes are its only link to your work.

## Workspace Resolution

1. If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
2. Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
3. If no workspace exists, write `.session-notes` at the repo root

## Journal Check

Before writing session notes, review this session's work and create journal entries for anything un-journaled:

- Significant decisions without DECISION entries?
- Technical findings without DISCOVERY entries?
- Risks identified without RISK entries?

Create entries for anything missing, then proceed.

## Write `.session-notes`

The file MUST contain these sections. The next session agent reads this to get full context — be specific, not vague.

### Section 1: Context Files (CRITICAL)

List the exact files the next session MUST read to understand the current state. Order matters — list foundation files first, then specifics.

```markdown
### Read These Files First (in order)

1. `path/to/file` — what it is and why to read it
2. `path/to/file` — what it is and why to read it
```

**Why**: CO Principle 2 (Brilliant New Hire) — every session starts from zero. Without this list, the next session wastes time discovering what you already know. Be explicit about file paths. "Read the docs" is useless; "`docs/00-authority/CLAUDE.md` — preloaded architecture context" is useful.

### Section 2: Accomplished

What was completed. Focus on outcomes, not activity.

### Section 3: Outstanding

What remains to be done. Be specific — include file paths, line numbers, exact issues. This is NOT a wish list; it's the next session's work queue.

```markdown
### Outstanding

- [ ] `rules/testing.md` missing from USE template — coc-sync Gate 2 should create softened version
- [ ] 19 BUILD-internal path refs in USE template agents — list: eatp-expert, framework-advisor, ...
```

### Section 4: Oversight Checklist

Verification steps the next session should perform BEFORE and AFTER its main work. This prevents regressions and ensures quality.

```markdown
### Oversight — Verify Before Starting

- [ ] Check: `file` still has expected content (hasn't been reverted)
- [ ] Confirm: feature X is still working (run command Y)

### Oversight — Verify After Completing

- [ ] Zero contamination: `grep -rl "pattern" path/` returns empty
- [ ] All tests pass: `pytest tests/ -x`
- [ ] Sync marker updated: `.coc-sync-marker` has current timestamp
```

**Why**: Without an oversight layer, the next session trusts the current state blindly. Verification catches regressions from hooks, other sessions, or manual edits between sessions.

### Section 5: Blockers (if any)

Decisions needed from the human, external dependencies, or unresolved questions.

## Rules

- **Overwrite** existing `.session-notes` — only the latest matters
- **Be specific** — file paths, line numbers, exact commands. Vague notes are useless to a blank-slate session.
- **Context files section is mandatory** — this is the single most important part. Without it, the next session has no starting point.
- **Oversight checklist is mandatory** — verification prevents blind trust in stale state.
- Keep under 80 lines. If you need more, the outstanding items should be in the todo system instead.
