---
name: sweep
description: "Comprehensive outstanding-work audit across kailash-py — workspaces, GH issues, spec compliance, drift, and process hygiene. End-of-cycle gate before /wrapup."
---

## Purpose

A `/sweep` is the structural defense against "I think we're done." Before declaring a session converged or starting fresh work, this command surfaces every class of outstanding item: in-flight todos, open issues, spec-vs-code drift, sibling-package drift, deferred-codify items, stale workspace state, and process-hygiene gaps. Findings are categorized by ACTIONABLE-NOW vs DEFERRED-TO-NEXT-SESSION vs CROSS-SESSION-LIFECYCLE so the human can decide scope.

Distinct from `/redteam` (which scopes to ONE workspace's spec compliance) — `/sweep` is repo-wide.

## Execution Model

Autonomous — runs every check sequentially, accumulates findings into a single report. The agent MAY fix trivial gaps inline (per `rules/zero-tolerance.md` Rule 1: "if you found it, you own it") but MUST surface every finding with its disposition.

## Workflow

Run all 11 sweeps. Aggregate findings into a single report at the end with severity (CRIT / HIGH / MED / LOW), disposition (FIX-NOW / FILE-ISSUE / DEFER-WITH-REASON / FALSE-POSITIVE), and pointer (file:line, PR#, issue#).

### Sweep 1: Active todos across all workspaces

```bash
find workspaces/*/todos/active/ -name "*.md" -not -name "*-milestone-tracker.md" 2>/dev/null
```

For each: read frontmatter (`status`, `priority`, `wave`). Group by workspace. Surface stale (>7d) workspaces' todos with explicit "is this still relevant?" flag.

### Sweep 2: Pending journal entries (auto-generated, awaiting promotion)

```bash
find workspaces/*/journal/.pending/ -name "*.md" 2>/dev/null
```

For each: read source-commit SHA. Decision tree per `rules/journal.md`:

- High-value commit body → promote to numbered journal entry
- Bare merge commit → discard
- Already-codified rule/skill → discard with note

### Sweep 3: GitHub open issues — kailash-py

```bash
gh issue list --repo terrene-foundation/kailash-py --state open --limit 50 \
  --json number,title,labels,createdAt,updatedAt,comments
```

Categorize each:

- **Stale** (no activity ≥30d) — flag for triage
- **Has `cross-sdk` label** — verify counterpart issue exists at kailash-rs
- **Has `deferred` label** — verify Rule 1b 4-condition body (runtime-safety proof + tracking issue + release PR link + signoff per `rules/zero-tolerance.md`)
- **Closeable with delivered-code reference** — code already shipped per `rules/git.md` § Issue Closure Discipline
- **Genuinely actionable** — needs scoping or implementation

### Sweep 4: GitHub open issues — kailash-coc-claude-py (USE template)

```bash
gh issue list --repo terrene-foundation/kailash-coc-claude-py --state open --limit 50 \
  --json number,title,labels,createdAt
```

Most should be sync-related (mismatch with loom or upstream artifact drift). Flag any that imply a kailash-py source change.

### Sweep 5: Open PRs and stale feature branches

```bash
gh pr list --repo terrene-foundation/kailash-py --state open --limit 50 \
  --json number,title,headRefName,isDraft,createdAt,statusCheckRollup
git branch -r --no-merged origin/main 2>&1 | grep -v "HEAD ->"
```

Surface:

- Draft PRs older than 7d (decide: ready for review OR close)
- PRs with red CI (per `feedback_ci_discipline` — never merge with red CI; fix in same branch)
- Remote branches with no PR (orphan work; decide salvage OR delete)
- Local branches not pushed (work-in-progress; decide push OR rebase to main)

### Sweep 6: Spec-vs-code gap analysis

This is the core of `/redteam` re-derived as a spec-wide sweep, not workspace-scoped. Use `skills/spec-compliance/SKILL.md` protocol — AST/grep verification, never file existence.

```bash
# Enumerate all spec files
ls specs/*.md

# Per spec file, for each MUST clause / contract / public symbol:
# - grep production source for the symbol → verify it exists
# - inspect.signature() → verify the contract holds
# - grep tests/ for the symbol → verify Tier 2 coverage exists
```

Categorize findings:

- **Orphan** — spec promises symbol; source has no implementation (`rules/orphan-detection.md` § 1)
- **Drift** — spec says X; source does Y (`rules/specs-authority.md` § 6 silent deviation)
- **Coverage gap** — symbol exists; tests/ has no Tier 2 wiring test (`rules/facade-manager-detection.md` § 2)
- **Stub** — `NotImplementedError` / `TODO` / `pass` in production paths (`rules/zero-tolerance.md` Rule 2)

### Sweep 7: Sibling-package drift (main vs PyPI)

Per `rules/build-repo-release-discipline.md` § 1 + § 3:

```bash
for pkg in kailash kailash-dataflow kailash-nexus kailash-kaizen kailash-mcp \
           kailash-ml kailash-align kailash-pact; do
  if [ -f "packages/$pkg/pyproject.toml" ]; then
    main_v=$(grep '^version' packages/$pkg/pyproject.toml | head -1 | cut -d'"' -f2)
  else
    main_v=$(grep '^version' pyproject.toml | head -1 | cut -d'"' -f2)
  fi
  pypi_v=$(curl -s "https://pypi.org/pypi/$pkg/json" 2>/dev/null \
    | .venv/bin/python -c 'import sys,json; print(json.load(sys.stdin).get("info",{}).get("version","?"))')
  [ "$main_v" != "$pypi_v" ] && echo "DRIFT: $pkg main=$main_v pypi=$pypi_v"
done
```

Any DRIFT line = release obligation per § 1. Surface as actionable.

### Sweep 8: Codify proposal lifecycle

```bash
cat .claude/.proposals/latest.yaml | grep -E "^(status|codify_date|submitted_date)"
```

States and dispositions per `rules/artifact-flow.md`:

- `pending_review` >7d old — flag (loom-side Gate 1 stalled?)
- `reviewed` >7d old — flag (loom-side Gate 2 stalled?)
- `distributed` — verify the locally-scoped artifacts (rules/agents/skills) reflect the distributed state via `wc -l` comparison loom vs kailash-py

### Sweep 9: Deferred-codify items

```bash
cat .claude/learning/learning-codified.json | jq '.deferred_to_next_cycle'
```

For each entry: re-evaluate. Items become actionable when:

- A 2nd-occurrence pattern emerges (was: one anecdote → now: codify)
- A blocking dependency lands (was: awaiting upstream → now: actionable)
- Time elapses past acceptance criteria (was: deferred this session → now: this session)

### Sweep 10: Workspace + worktree hygiene

```bash
# Stale session notes
find workspaces/*/.session-notes -mtime +30 2>/dev/null

# Stale worktrees (orphaned after merge)
git worktree list

# Stale .pending journal entries (>14d)
find workspaces/*/journal/.pending/*.md -mtime +14 2>/dev/null
```

Surface:

- Workspaces with `.session-notes` >30d (archive candidate)
- Worktrees not at HEAD or with no commits (cleanup per `rules/worktree-isolation.md`)
- `.pending` entries >14d (promote OR discard; the agent that generated them is gone)

### Sweep 11: Cross-SDK alignment with kailash-rs

Per `rules/cross-sdk-inspection.md` MUST Rule 1, every fix at kailash-py MUST have been inspected for kailash-rs applicability.

```bash
# Last 14d of kailash-py merged PRs whose label contains "cross-sdk" OR diff
# touched shared-architecture domains (DataFlow trust, EATP, governance)
gh pr list --repo terrene-foundation/kailash-py --state merged --limit 30 \
  --json number,title,labels,mergedAt --jq '.[] | select(.mergedAt > (now - 1209600 | todate))'

# For each: check if a counterpart issue/PR exists at esperie/kailash-rs
gh issue list --repo esperie/kailash-rs --state all --search "<keyword>" --limit 5
```

Surface uninspected PRs as cross-SDK-followup candidates.

## Output format

Write findings to `workspaces/<project>/04-validate/sweep-<date>.md` (if a workspace context is active) OR to a fresh top-level `SWEEP-<date>.md` (root) if no workspace. Format:

```markdown
# /sweep findings — <date>

## Summary

- CRIT: N
- HIGH: N
- MED: N
- LOW: N
- INFORMATIONAL: N

## Findings (ordered by severity)

### [CRIT/HIGH/MED/LOW] [Sweep N: name] <one-line title>

**Location:** file:line OR PR#NNN OR issue#NNN OR specs/foo.md § N
**Disposition:** FIX-NOW / FILE-ISSUE / DEFER-WITH-REASON / FALSE-POSITIVE
**Evidence:** command output OR grep result OR PR body excerpt
**Why this matters:** 2-sentence rationale
**Action taken (if FIX-NOW):** commit SHA OR "no action — orchestrator dispatch needed"

## Cross-cutting observations

(Patterns spanning multiple findings — e.g., "5 of 7 findings trace to incomplete codify-proposal lifecycle")

## Recommended next session scope

(2-5 items, ranked by impact, that the human can choose to take on)
```

## Closure

Before reporting `/sweep` complete:

1. ALL Sweep 1-11 outputs accumulated into the report
2. Trivial fixes applied inline (per `feedback_drive_to_completion`); their findings reclassified `FIXED` with commit SHA
3. Non-trivial fixes filed as workspace todos OR GitHub issues with delivered-code references when applicable
4. Report committed to the repo (`git add` + `git commit`)
5. Optional: human authorization for the recommended next-session scope

The report is the deliverable. The agent does NOT decide what to do next from the report — that's a human call.
