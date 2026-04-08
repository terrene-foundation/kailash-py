---
name: wrapup
description: "Write session notes before ending. Captures context for next session."
---

Write session notes to preserve context for the next session. The next session starts from zero — these notes are its only link to your work.

## Deploy State Check (MUST run first)

Before writing session notes, classify `deploy/deployment-config.md` into one of four states and act accordingly:

### State A: File exists with YAML frontmatter declaring `deploy.type: application`

1. Run `/deploy --check` (or directly: read `deploy/.last-deployed`, compare to `git rev-parse HEAD`, run `git diff <last_deployed> HEAD -- <production_paths>`)
2. If drift is detected on production paths:
   - **STOP** — do NOT write session notes yet
   - Present the drift: which commits, which files, how many production-touching changes
   - Require one of:
     - **Run `/deploy` now** to actually ship the code (preferred)
     - **Explicit deferral** with documented reason in session notes (`Deploy deferred: <why>`)
3. Only after deploy runs OR deferral is documented, proceed.

### State B: File exists with YAML frontmatter declaring `deploy.type: sdk`

This is a BUILD repo / SDK. `/deploy` is not the right command here — `/release` is. Note in session notes: `Deploy state check skipped: SDK repo (use /release for publishing).` Proceed to write session notes.

### State C: File exists but lacks YAML frontmatter (legacy prose-only config)

The file is human-readable documentation but not machine-parseable. The agent cannot run `/deploy --check` or determine `type:`.

- Note in session notes: `[ ] Migrate deploy/deployment-config.md to YAML frontmatter (currently legacy prose-only). Run /deploy --onboard to regenerate.`
- Do NOT block wrapup, but DO flag this prominently.
- If git diff against `git log -1 --format=%H deploy/deployment-config.md` shows the prose has been hand-edited recently, that further suggests the project is using a manual deploy workflow that loom's automation cannot verify — flag it explicitly.

### State D: File does NOT exist

- Note in session notes: `[ ] Run /deploy --onboard to create deployment config (no config exists, deploy state cannot be checked).`
- Do NOT block wrapup — onboarding is a first-time setup, not a session blocker.

**Why:** See `rules/deploy-hygiene.md`. The single most common failure mode is ending a session with committed-but-not-deployed production code, which makes the next session inherit unverifiable state. The four-state classification prevents two false positives: SDK repos that legitimately use /release (State B), and legacy prose configs that fall through both "exists" and "missing" branches (State C — exactly the kailash-py situation).

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

**Why:** CO Principle 2 (Brilliant New Hire) — every session starts from zero. Without this list, the next session wastes time discovering what you already know. Be explicit about file paths. "Read the docs" is useless; "`docs/00-authority/CLAUDE.md` — preloaded architecture context" is useful.

### Section 2: Accomplished

What was completed. Focus on outcomes, not activity.

### Section 3: Outstanding

What remains to be done. Be specific — include file paths, line numbers, exact issues. This is NOT a wish list; it's the next session's work queue.

```markdown
### Outstanding

- [ ] `rules/testing.md` missing from USE template — coc-sync Gate 2 should create softened version
- [ ] BUILD-internal path refs in USE template agents — check for stale agent/skill references
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

**Why:** Without an oversight layer, the next session trusts the current state blindly. Verification catches regressions from hooks, other sessions, or manual edits between sessions.

### Section 5: Blockers (if any)

Decisions needed from the human, external dependencies, or unresolved questions.

## Red Team Verification (MANDATORY)

After drafting the `.session-notes`, BEFORE writing the final version, run a self-audit. This prevents the next session from inheriting stale assumptions.

### Verify Outstanding Items

For EVERY item in the Outstanding section (if >10 items, verify top 5 individually + one bulk grep for the rest):

1. **Run a concrete check** (grep, file read, `gh issue view`, count) — the tool call is the verification, not your memory
2. **Include the evidence inline**: e.g., `(verified: grep -rl "pattern" path/ returned 3 files)` or `(verified: ls todos/active/ | wc -l returned 27)`
3. If the item references a GitHub issue, check its current state (`gh issue view`). If network fails, note `(skipped: network error)`
4. If the item claims "N todos remaining", count the actual active todos and state the count
5. **Remove or correct** any item that is already resolved — do NOT carry forward stale items

For artifact-only sessions (no code changes), verification means reading the files you claim are incomplete/missing and confirming their actual state.

**Why:** Without tool-call evidence, an agent can write "verified" from memory — the same memory that produced stale claims in the first place. Requiring inline evidence makes the verification auditable by the next session.

### Verify Accomplished Claims

For the top 3 most significant accomplishments:

1. **Spot-check** that the claimed change actually exists (read the file, check git log)
2. If a commit was claimed, verify it exists (`git log --oneline -5`)
3. If a PR was merged, verify (`gh pr view N --json state`)

### Verify Oversight Commands

For every command in the Oversight Checklist:

1. **Run it now** and record the actual output
2. If the output doesn't match expectations, investigate before writing the notes
3. Include the actual values in the notes (e.g., "FastAPI grep: 0 matches" not just "should be 0")

### Final Coherence Check

- If any Outstanding item was corrected or removed, re-read the full notes for coherence
- The final `.session-notes` MUST reflect verified reality, not session memory

## Rules

- **Overwrite** existing `.session-notes` — only the latest matters
- **Be specific** — file paths, line numbers, exact commands. Vague notes are useless to a blank-slate session.
- **Context files section is mandatory** — this is the single most important part. Without it, the next session has no starting point.
- **Oversight checklist is mandatory** — verification prevents blind trust in stale state.
- **Red team verification is mandatory** — claims MUST be checked against codebase reality before writing.
- Keep under 100 lines. If you need more, the outstanding items should be in the todo system instead.
