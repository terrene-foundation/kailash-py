---
priority: 10
scope: path-scoped
paths:
  - "journal/**"
  - "**/journal/**"
---

# Journal Rules

<!-- slot:neutral-body -->

## Naming & Format

Sequential naming: `NNNN-TYPE-topic.md`. Check highest existing number before creating.

```yaml
---
type: DECISION | DISCOVERY | TRADE-OFF | RISK | CONNECTION | GAP
date: YYYY-MM-DD
created_at: [ISO-8601]
author: human | agent | co-authored
session_id: [session ID]
session_turn: [turn number]
project: [project name]
topic: [brief description]
phase: analyze | todos | implement | redteam | codify | deploy
tags: [list]
---
```

**Author decision tree**: `human` — user stated conclusion before AI. `agent` — AI surfaced unprompted. `co-authored` — evolved through exchange (default when uncertain).

## Entry Types

| Type           | When                                                     |
| -------------- | -------------------------------------------------------- |
| **DECISION**   | Architectural, design, strategic, or scope choices       |
| **DISCOVERY**  | Research/analysis reveals new understanding              |
| **TRADE-OFF**  | Balancing competing concerns                             |
| **RISK**       | Stress-testing reveals vulnerabilities                   |
| **CONNECTION** | Cross-referencing reveals relationships                  |
| **GAP**        | Missing data, untested assumptions, unresolved questions |

## Requirements

- Every entry MUST include `## For Discussion` with 2-3 probing questions (at least one counterfactual, at least one referencing specific data)

**Why:** Without discussion questions, journal entries become write-only artifacts that capture decisions but never challenge them.

- Entries MUST be self-contained — readable without other context

**Why:** Entries referenced months later by a different agent are useless if they depend on session context that no longer exists.

- DECISION entries SHOULD include alternatives and rationale
- Entries SHOULD include consequences and follow-up actions

## MUST NOT

- Overwrite existing entries — immutable once created. New entry references the original.

**Why:** Overwriting destroys the audit trail of how decisions evolved, making it impossible to understand why a position changed.

- Create entries without frontmatter

**Why:** Entries without frontmatter cannot be filtered by type, phase, or date, making the journal unsearchable at scale.

## SessionEnd Auto-Capture & Pending-Journal Hygiene

The SessionEnd hook auto-captures commit bodies into a workspace's `journal/.pending/` staging area. These two clauses govern where those entries land and how they are kept out of git.

### 1. Workspace `journal/.pending/` MUST Be Gitignored At Repo Root

Every repo that runs the SessionEnd auto-capture hook MUST carry a `**/journal/.pending/` ignore pattern in the repo-root `.gitignore`. Relying on per-workspace `.gitignore` files or on manual `git add` discipline is BLOCKED.

```gitignore
# DO — repo-root .gitignore carries the pattern once, covers every workspace
**/journal/.pending/

# DO NOT — rely on per-workspace .gitignore or manual staging discipline
# (every new workspace re-creates an un-ignored journal/.pending/; the next
#  /wrapup then stages dozens of session-local auto-capture files into the PR)
```

**BLOCKED rationalizations:**

- "The workspace already has its own `.gitignore`"
- "Manual `git add` of only the curated files is fine"
- "We will add the pattern when `.pending/` first appears"
- "`.pending/` is empty right now, the pattern is premature"

**Why:** `.pending/` entries are SessionEnd-hook auto-captures, not curated journal entries — they are triaged and promoted-or-discarded on the next workspace visit. Without the root ignore pattern, every `/wrapup` sweeps them into the working tree and they leak as dirty-tree noise into unrelated PRs.

### 2. SessionEnd Auto-Capture Routes By The Commit's Issue Trailer, Not The CWD Workspace

The SessionEnd auto-capture hook MUST write a commit's `.pending/` entry into the workspace whose issue number matches the commit's `Closes #N` / `Refs #N` trailer — NOT the workspace that happened to be the session's working directory. A commit with no issue trailer MUST write to a shared `_unrouted/` staging area, never to an arbitrary CWD workspace.

```text
# DO — route by the commit's own issue trailer
commit `Closes #912`   → workspaces/issue-912-*/journal/.pending/
commit with no trailer → workspaces/_unrouted/journal/.pending/

# DO NOT — route by session CWD
session CWD = issue-835 workspace; commit closes #912
  → .pending/ entry lands in issue-835's journal  ← wrong workspace;
    #912's institutional value is now buried under an unrelated issue
```

**BLOCKED rationalizations:**

- "The CWD workspace is close enough — the operator was working there"
- "Parsing the commit's `Closes/Refs #N` trailer is more work than writing to CWD"
- "The next triage pass will sort out which entries belong where"
- "Most commits in a session relate to the CWD workspace anyway"

**Why:** A commit's institutional value belongs to the issue it closes, not the directory the session happened to run in. CWD-routing concentrates triage cost in whichever workspace was the CWD — the triage of issue-835's 33 `.pending/` entries discarded 28 as unrelated auto-captures — while diffusing the value away from the issue that earned it.

**Trust Posture Wiring (clauses 1 + 2):**

- **Severity:** `advisory`. Clause 1 is a one-line repo-setup check; clause 2 is hook behavior whose enforcement IS the hook (issue #1086 candidate 3, loom-side). Neither is a PreToolUse structural signal, so neither carries `block`.
- **Grace period:** 7 days from this clause landing.
- **Cumulative:** contributes to `trust-posture.md` MUST Rule 4 cumulative math.
- **Regression-within-grace:** a `/wrapup` within 7 days that ships `.pending/` files into a PR (clause 1), or an auto-capture written to a CWD-mismatched workspace (clause 2), = emergency downgrade per `trust-posture.md` MUST Rule 4.
- **Receipt requirement:** SessionStart MUST require `[ack: pending-journal-hygiene]` in the agent's first response IF `posture.json::pending_verification` includes this rule_id.
- **Detection:** clause 1 — mechanical: `git check-ignore <workspace>/journal/.pending/x` MUST exit 0. clause 2 — implemented by the SessionEnd hook's `Closes/Refs #N` parser (issue #1086 candidate 3, lands loom-side; audit fixtures attach there per `cc-artifacts.md` Rule 9). First-violation id: none yet.
- **Origin:** 2026-05-18 — issue #1086 candidates 2 + 4; originating evidence `workspaces/_hygiene-2026-05-18/02-issue-835-journal-triage.md`.

<!-- /slot:neutral-body -->
