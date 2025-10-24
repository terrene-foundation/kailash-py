# GitHub ↔ Local Todo Bidirectional Sync Process

**Created**: 2025-10-24
**Status**: Active
**Maintainer**: gh-manager subagent

---

## Overview

This document defines the bidirectional synchronization process between GitHub Issues and the local todo system for MVR execution. The goal is to maintain a **single source of truth** while enabling both GitHub-centric and local development workflows.

## Synchronization Principles

### Source of Truth

- **GitHub Issues** = Source of truth for:
  - Requirements and acceptance criteria
  - Task status (Open, In Progress, Blocked, Done)
  - Comments and discussions
  - Milestone assignments
  - Labels and metadata

- **Local Todos** = Source of truth for:
  - Implementation progress and subtasks
  - Developer notes and implementation details
  - Code snippets and references
  - Time tracking (hours spent)

### Conflict Resolution

When GitHub and local todos diverge:

1. **Requirements conflicts**: GitHub wins (requirements are managed centrally)
2. **Status conflicts**: Most recent update wins (with conflict notification)
3. **Implementation conflicts**: Local wins (implementation details are developer-owned)
4. **Metadata conflicts** (labels, milestones): GitHub wins

---

## Sync Trigger Points

### 1. Issue → Todo (GitHub to Local)

**When**: Developer starts working on a GitHub issue

**Trigger**: Developer explicitly starts work (not automatic)

**Process**:
1. Developer identifies next GitHub issue to work on (e.g., #458)
2. Developer creates local todo file: `todos/active/TODO-001-saas-template-structure.md`
3. Local todo references GitHub issue: `**GitHub Issue**: #458`
4. Developer comments on GitHub issue: "Started implementation"
5. gh-manager updates issue status to "In Progress"

**Example**:
```bash
# Developer command
cd apps/kailash-nexus/todos/active
cp ../template.md TODO-001-saas-template-structure.md

# Fill in details from GitHub issue #458
# Add: **GitHub Issue**: #458

# Notify GitHub
gh issue comment 458 --repo terrene-foundation/kailash-py \
  --body "🔄 Implementation started in local todo system (TODO-001)"

# Update issue status (if project board is set up)
# This will be done manually via project board or labels
```

### 2. Todo → Issue (Local to GitHub)

**When**: Developer makes significant progress on local todo

**Triggers**:
- Todo status: PENDING → IN_PROGRESS
- Todo status: IN_PROGRESS → BLOCKED
- Todo status: IN_PROGRESS → COMPLETED
- Todo progress: 50% milestone reached
- Todo requires clarification

**Process** (for each trigger):

#### Trigger A: Todo Status = IN_PROGRESS
```bash
# Add comment to GitHub issue
gh issue comment 458 --repo terrene-foundation/kailash-py \
  --body "🔄 Implementation started

**Local Todo**: TODO-001-saas-template-structure.md
**Developer**: DataFlow dev
**Started**: $(date +%Y-%m-%d)

Implementation in progress. Will update at 50% completion milestone."
```

#### Trigger B: Todo Status = BLOCKED
```bash
# Add "mvr-blocked" label and comment
gh issue edit 458 --repo terrene-foundation/kailash-py \
  --add-label "mvr-blocked"

gh issue comment 458 --repo terrene-foundation/kailash-py \
  --body "⚠️ **BLOCKED**

**Blocker**: [Brief description of blocker]
**Impact**: [High/Medium/Low]
**Blocking since**: $(date +%Y-%m-%d)

**Details**:
[Detailed explanation of what is blocking progress]

**Action needed**:
[What needs to happen to unblock]

**Local Todo**: TODO-001-saas-template-structure.md"
```

#### Trigger C: Todo Status = COMPLETED
```bash
# Close GitHub issue with completion comment
gh issue close 458 --repo terrene-foundation/kailash-py \
  --comment "✅ **COMPLETED**

**Completed**: $(date +%Y-%m-%d)
**Total time**: [hours] hours (estimated: 8h)
**Local Todo**: TODO-001-saas-template-structure.md

## Summary
[Brief summary of what was implemented]

## Deliverables
- [x] All acceptance criteria met
- [x] Tests pass
- [x] Code reviewed

## Links
- Commit: [commit SHA or PR link]
- Related todos: TODO-002, TODO-006

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude <noreply@anthropic.com>"

# Move local todo to completed
mv todos/active/TODO-001-saas-template-structure.md \
   todos/completed/TODO-001-saas-template-structure.md

# Add completion metadata to todo
echo "" >> todos/completed/TODO-001-saas-template-structure.md
echo "**Completed**: $(date +%Y-%m-%d)" >> todos/completed/TODO-001-saas-template-structure.md
echo "**GitHub Issue**: Closed #458" >> todos/completed/TODO-001-saas-template-structure.md
```

#### Trigger D: Todo Progress = 50%
```bash
# Add progress comment
gh issue comment 458 --repo terrene-foundation/kailash-py \
  --body "📊 **Progress Update: 50% Complete**

**Local Todo**: TODO-001-saas-template-structure.md
**Updated**: $(date +%Y-%m-%d)

## Completed So Far
- [x] Subtask 1
- [x] Subtask 2

## Remaining Work
- [ ] Subtask 3
- [ ] Subtask 4

**Estimated completion**: [date or "on track" / "delayed"]

Implementation notes:
[Brief notes on any challenges or decisions made]"
```

#### Trigger E: Todo Requires Clarification
```bash
# Add "needs-clarification" label and comment with questions
gh issue edit 458 --repo terrene-foundation/kailash-py \
  --add-label "needs-clarification"

gh issue comment 458 --repo terrene-foundation/kailash-py \
  --body "❓ **Clarification Needed**

**Local Todo**: TODO-001-saas-template-structure.md
**Asked**: $(date +%Y-%m-%d)

## Questions
1. [Question 1]
2. [Question 2]

## Context
[Why clarification is needed]

## Impact if Not Clarified
[What will be blocked or at risk]

**Implementation paused** until clarification received."
```

### 3. Issue Update → Todo (GitHub to Local)

**When**: GitHub issue is updated externally (comments, label changes, status changes)

**Triggers**:
- New comment added by someone else
- Label changed (e.g., "mvr-blocked" added/removed)
- Milestone changed
- Acceptance criteria updated
- Issue closed externally

**Process**: Developer manually checks GitHub for updates (no automatic sync)

**Recommended workflow**:
```bash
# Daily check for updates to active todos
# Developer runs this command each morning

cd apps/kailash-nexus/todos/active

# For each active todo, check corresponding GitHub issue for updates
# Example for TODO-001 (issue #458)
gh issue view 458 --repo terrene-foundation/kailash-py --comments

# If there are new comments or changes:
# 1. Read the updates
# 2. Update local todo file with relevant information
# 3. Adjust implementation plan if needed
# 4. Reply to GitHub comments if action is required
```

---

## Sync Frequency

### Real-Time Sync (Immediate)
- Todo status: PENDING → IN_PROGRESS
- Todo status: IN_PROGRESS → BLOCKED
- Todo status: IN_PROGRESS → COMPLETED

### Hourly Sync (Every Hour)
- Progress updates for in-progress items (if significant progress made)

### Daily Sync (Every Morning)
- Check all active todos for GitHub updates
- Update local todos with new comments/changes from GitHub

### Weekly Sync (Every Monday)
- Full reconciliation check (ensure no divergence)
- Generate sync status report
- Identify and resolve conflicts

### Sprint Boundaries (Phase Transitions)
- Complete sync validation before moving to next phase
- Archive completed todos
- Update project board with phase completion status

---

## Automated Sync Commands

### Command 1: Start Work (Issue → Todo)

```bash
# Usage: ./start-work.sh 458 TODO-001-saas-template-structure
#!/bin/bash

ISSUE_NUM=$1
TODO_ID=$2

# Notify GitHub
gh issue comment $ISSUE_NUM --repo terrene-foundation/kailash-py \
  --body "🔄 Implementation started in local todo system ($TODO_ID)"

echo "✅ Work started on issue #$ISSUE_NUM"
echo "Local todo: todos/active/$TODO_ID.md"
```

### Command 2: Block Task (Todo → Issue)

```bash
# Usage: ./block-task.sh 458 "Missing API credentials"
#!/bin/bash

ISSUE_NUM=$1
BLOCKER_REASON=$2

gh issue edit $ISSUE_NUM --repo terrene-foundation/kailash-py \
  --add-label "mvr-blocked"

gh issue comment $ISSUE_NUM --repo terrene-foundation/kailash-py \
  --body "⚠️ **BLOCKED**: $BLOCKER_REASON

Blocked on: $(date +%Y-%m-%d)
Action needed: [Developer to fill in]"

echo "⚠️  Issue #$ISSUE_NUM marked as BLOCKED"
```

### Command 3: Complete Task (Todo → Issue)

```bash
# Usage: ./complete-task.sh 458 TODO-001-saas-template-structure "All acceptance criteria met"
#!/bin/bash

ISSUE_NUM=$1
TODO_ID=$2
SUMMARY=$3

gh issue close $ISSUE_NUM --repo terrene-foundation/kailash-py \
  --comment "✅ **COMPLETED**

Summary: $SUMMARY

Completed: $(date +%Y-%m-%d)
Local Todo: $TODO_ID.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
Co-Authored-By: Claude <noreply@anthropic.com>"

# Move todo to completed
mv "todos/active/$TODO_ID.md" "todos/completed/$TODO_ID.md"

echo "✅ Issue #$ISSUE_NUM completed and closed"
echo "Local todo moved to: todos/completed/$TODO_ID.md"
```

### Command 4: Progress Update (Todo → Issue)

```bash
# Usage: ./update-progress.sh 458 50 "Directory structure complete, working on boilerplate"
#!/bin/bash

ISSUE_NUM=$1
PROGRESS_PCT=$2
UPDATE_MSG=$3

gh issue comment $ISSUE_NUM --repo terrene-foundation/kailash-py \
  --body "📊 **Progress Update: ${PROGRESS_PCT}% Complete**

Updated: $(date +%Y-%m-%d)

$UPDATE_MSG"

echo "📊 Progress updated for issue #$ISSUE_NUM (${PROGRESS_PCT}%)"
```

### Command 5: Request Clarification (Todo → Issue)

```bash
# Usage: ./request-clarification.sh 458 "Should we use UUID v4 or v7?"
#!/bin/bash

ISSUE_NUM=$1
QUESTION=$2

gh issue edit $ISSUE_NUM --repo terrene-foundation/kailash-py \
  --add-label "needs-clarification"

gh issue comment $ISSUE_NUM --repo terrene-foundation/kailash-py \
  --body "❓ **Clarification Needed**

Question: $QUESTION

Asked: $(date +%Y-%m-%d)

Implementation paused until clarification received."

echo "❓ Clarification requested for issue #$ISSUE_NUM"
```

### Command 6: Daily Sync Check (Issue → Todo)

```bash
# Usage: ./daily-sync-check.sh
#!/bin/bash

echo "🔄 Checking for updates on active todos..."

# Get all active todos
cd apps/kailash-nexus/todos/active

for todo_file in TODO-*.md; do
  # Extract issue number from todo file
  ISSUE_NUM=$(grep "GitHub Issue" "$todo_file" | grep -oE '#[0-9]+' | tr -d '#')

  if [ -n "$ISSUE_NUM" ]; then
    echo ""
    echo "Checking TODO: $todo_file (Issue #$ISSUE_NUM)"

    # Check for new comments since yesterday
    gh issue view $ISSUE_NUM --repo terrene-foundation/kailash-py \
      --json comments --jq '.comments[] | select(.createdAt > (now - 86400 | todate)) | "\(.author.login): \(.body)"'
  fi
done

echo ""
echo "✅ Daily sync check complete"
```

---

## Sync Status Tracking

### Status Report Format

Generate weekly sync status reports:

```markdown
## GitHub ↔ Todo Sync Status Report

**Report Date**: 2025-10-24
**Phase**: Phase 0 - Prototype Validation

### Sync Summary
- ✅ Synced: 12 items (both systems aligned)
- ⚠️ Pending Sync: 2 items (local changes not pushed)
- ❌ Conflicts: 1 item (divergent state)

### Items Needing Sync

#### TODO-003 (Issue #469): Local marked 50% complete, GitHub not updated
- **Action**: Update GitHub with progress comment
- **Command**: `./update-progress.sh 469 50 "Registration workflow complete, login in progress"`

#### TODO-007 (Issue #473): GitHub has new comment, local todo not updated
- **Action**: Update local todo with GitHub comment
- **GitHub Comment**: "Consider using pgvector for pattern embedding"

### Conflicts

#### TODO-001 (Issue #458): Status divergence
- **GitHub Status**: In Progress
- **Local Todo Status**: Completed
- **Resolution**: Close GitHub issue (local is correct, work was completed)
- **Command**: `./complete-task.sh 458 TODO-001-saas-template-structure "All acceptance criteria met"`

### Recent Syncs (Last 7 Days)
- 2025-10-23: Updated #458 with progress comment
- 2025-10-22: Closed #455 after todo completion
- 2025-10-21: Added "blocked" label to #456

### Recommendations
1. Run full sync: Reconcile 2 pending items (use commands above)
2. Resolve conflicts: Close #458 to align with local completed status
3. Update project board: Refresh kanban view after syncs
```

### Generate Sync Status Report

```bash
# Usage: ./generate-sync-report.sh
#!/bin/bash

echo "# GitHub ↔ Todo Sync Status Report"
echo ""
echo "**Report Date**: $(date +%Y-%m-%d)"
echo "**Phase**: Phase 0 - Prototype Validation"
echo ""

SYNCED=0
PENDING_SYNC=0
CONFLICTS=0

# Analyze each active todo
cd apps/kailash-nexus/todos/active

for todo_file in TODO-*.md; do
  # Extract issue number
  ISSUE_NUM=$(grep "GitHub Issue" "$todo_file" | grep -oE '#[0-9]+' | tr -d '#')

  if [ -n "$ISSUE_NUM" ]; then
    # Get GitHub issue status
    GH_STATE=$(gh issue view $ISSUE_NUM --repo terrene-foundation/kailash-py --json state --jq '.state')

    # Get local todo status (simplified check)
    if [ -f "$todo_file" ]; then
      LOCAL_STATUS="IN_PROGRESS"
    else
      LOCAL_STATUS="COMPLETED"
    fi

    # Compare statuses (simplified logic)
    if [ "$GH_STATE" = "OPEN" ] && [ "$LOCAL_STATUS" = "IN_PROGRESS" ]; then
      SYNCED=$((SYNCED + 1))
    elif [ "$GH_STATE" = "OPEN" ] && [ "$LOCAL_STATUS" = "COMPLETED" ]; then
      CONFLICTS=$((CONFLICTS + 1))
      echo "- ❌ Conflict: $todo_file (GitHub: OPEN, Local: COMPLETED)"
    else
      PENDING_SYNC=$((PENDING_SYNC + 1))
    fi
  fi
done

echo ""
echo "### Sync Summary"
echo "- ✅ Synced: $SYNCED items"
echo "- ⚠️ Pending Sync: $PENDING_SYNC items"
echo "- ❌ Conflicts: $CONFLICTS items"
echo ""
echo "Run daily-sync-check.sh for detailed analysis."
```

---

## Best Practices

### For Developers

1. **Start work**: Always comment on GitHub issue when starting (use `start-work.sh`)
2. **Update regularly**: Post progress updates at 25%, 50%, 75% milestones
3. **Block immediately**: If blocked, add label and comment within 1 hour
4. **Complete promptly**: Close GitHub issue within 1 hour of completing local todo
5. **Check daily**: Run `daily-sync-check.sh` every morning before starting work

### For Project Manager / Coordinator

1. **Review weekly**: Generate sync status report every Monday
2. **Resolve conflicts**: Address conflicts within 24 hours
3. **Monitor blockers**: Check "mvr-blocked" label daily, escalate if blocked >2 days
4. **Track milestones**: Ensure milestone progress aligns with timeline
5. **Validate quality gates**: Before phase transitions, ensure all issues closed

### For gh-manager Subagent

1. **Automate when possible**: Use scripts for repetitive sync operations
2. **Notify proactively**: Alert team of divergence or conflicts
3. **Maintain traceability**: Always link GitHub issue ↔ local todo bidirectionally
4. **Document exceptions**: If manual sync needed, document why in both systems
5. **Archive consistently**: Move completed todos to `completed/` directory

---

## Sync Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Issues (Source of Truth)             │
│                     - Requirements                               │
│                     - Status                                     │
│                     - Comments                                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ Issue Created
                         │ Developer starts work
                         ▼
         ┌───────────────────────────────────────┐
         │    Developer Creates Local Todo        │
         │    - Implementation details            │
         │    - Progress tracking                 │
         │    - Code references                   │
         └───────────────┬───────────────────────┘
                         │
                         │ Link: **GitHub Issue**: #XXX
                         │
         ┌───────────────▼───────────────────────┐
         │         Bidirectional Sync             │
         │                                        │
         │  GitHub ← TODO Status Updates          │
         │  (started, progress, blocked, done)    │
         │                                        │
         │  TODO ← GitHub Updates                 │
         │  (comments, label changes)             │
         └───────────────┬───────────────────────┘
                         │
                         │ Work Complete
                         ▼
         ┌───────────────────────────────────────┐
         │  Close GitHub Issue                    │
         │  Move Local Todo to completed/         │
         └───────────────────────────────────────┘
```

---

## Troubleshooting

### Problem: Local todo shows COMPLETED but GitHub issue still OPEN

**Cause**: Sync command not run after completion

**Solution**:
```bash
./complete-task.sh <ISSUE_NUM> <TODO_ID> "Summary of work"
```

### Problem: GitHub issue has new comments but local todo not updated

**Cause**: Daily sync check not run

**Solution**:
```bash
./daily-sync-check.sh
# Review output
# Manually update local todo files with relevant GitHub comments
```

### Problem: Conflict - GitHub and local have different statuses

**Cause**: Updates made to both systems without sync

**Solution**:
1. Determine which system has correct status (usually local for implementation status)
2. Update the other system to match
3. Add comment explaining resolution
4. Document in sync status report

### Problem: Issue marked BLOCKED but no action taken

**Cause**: Blocker not visible or not escalated

**Solution**:
1. Check all issues with "mvr-blocked" label daily:
   ```bash
   gh issue list --repo terrene-foundation/kailash-py --label "mvr-blocked" --json number,title,labels,updatedAt
   ```
2. For blockers >2 days old, escalate to project coordinator
3. Add comment with escalation status

---

## Helper Scripts Location

Save all helper scripts to: `apps/kailash-nexus/scripts/sync/`

```bash
mkdir -p apps/kailash-nexus/scripts/sync

# Create scripts
cd apps/kailash-nexus/scripts/sync
touch start-work.sh block-task.sh complete-task.sh update-progress.sh
touch request-clarification.sh daily-sync-check.sh generate-sync-report.sh

# Make executable
chmod +x *.sh
```

**Usage**:
```bash
# Add to PATH or alias
alias sync-start="apps/kailash-nexus/scripts/sync/start-work.sh"
alias sync-block="apps/kailash-nexus/scripts/sync/block-task.sh"
alias sync-complete="apps/kailash-nexus/scripts/sync/complete-task.sh"
alias sync-progress="apps/kailash-nexus/scripts/sync/update-progress.sh"
alias sync-clarify="apps/kailash-nexus/scripts/sync/request-clarification.sh"
alias sync-check="apps/kailash-nexus/scripts/sync/daily-sync-check.sh"
alias sync-report="apps/kailash-nexus/scripts/sync/generate-sync-report.sh"
```

---

## Next Steps

1. **Implement helper scripts**: Create the 7 helper scripts in `scripts/sync/`
2. **Test sync workflow**: Run through complete cycle with TODO-001
3. **Train team**: Share this document with all developers
4. **Establish routine**: Set up daily sync check as morning routine
5. **Monitor effectiveness**: Track sync issues in first 2 weeks, adjust process as needed

---

## References

- GitHub CLI Manual: https://cli.github.com/manual/
- Master Todo: `apps/kailash-nexus/todos/000-master.md`
- Project Board Setup: `github-project-board-setup.md`
- Phase 0 Issues: https://github.com/terrene-foundation/kailash-py/milestone/4
