---
id: "COC-SYNC-LANDING"
paths: [".claude/**"]
---

# COC Sync Landing — BUILD-Side Discipline

See `.claude/guides/rule-extracts/coc-sync-landing.md` for BLOCKED-rationalizations, extended bash examples, origin post-mortem, MUST NOT clauses, and cross-rule relationships.

Loom's `/sync-to-build` delivery MUST land on `main` BEFORE any other session work. Pairs with `.claude/hooks/multi-operator-sessionstart.js` (SessionStart). Under Directive 1 (`artifact-flow.md` § "Exact Gate-1 / Gate-2 Tracking"), that delivery now lands as a loom-authored PR against the target repo, opened from an isolated worktree-from-remote-main — not an uncommitted working-tree overlay a later BUILD session must land — so the sync path no longer OPENS the uncommitted-delivery window MUST-1 guards; MUST-1 still fires on any OTHER uncommitted COC drift found at session start.

## MUST Rules

### 1. COC Drift Lands as PR #1

When the SessionStart hook reports uncommitted COC drift — the `Working-tree drift: <n> own-WIP, <n> claimed-WIP` line `.claude/hooks/multi-operator-sessionstart.js` emits into the session's additional context — land it FIRST. Non-COC-PR workarounds BLOCKED. Cross-session carry BLOCKED.

**Why:** Uncommitted deliveries appear available on disk but vanish on first non-main commit — new commands disappear, new agents become invisible.

### 2. Stage Explicit Paths

Stage `.claude/` and `scripts/hooks/` explicitly. `git add -u` / `-A` / `.` BLOCKED for COC-sync PRs.

**Why:** Bulk staging sweeps unrelated workspace drift into the PR. PR #753 (2026-05-01) wasted ~15 min recovering from this exact failure.

### 3. Admin-Merge Per Owner Workflow

After CI green or path-filter auto-skip, run `gh pr merge <N> --admin --merge --delete-branch`. `REVIEW_REQUIRED` parking BLOCKED.

**Why:** `--admin` is the owner-class bypass for chore PRs; without it the PR drifts open across sessions and the failure mode resumes.

Origin: 2026-05-02 — `/autonomize` unknown at session start despite prior `/sync-to-build` delivery. See guide.
