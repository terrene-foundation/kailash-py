# GitHub Project Board Setup for MVR

**Created**: 2025-10-24
**Status**: Ready for manual setup (requires project scope authentication)

---

## Overview

This document provides step-by-step instructions for setting up the GitHub Project board to track the Kailash MVR execution across 5 phases and 67 tasks.

## Current GitHub Setup Status

### Completed Setup
- [x] **5 Milestones Created**
  - MVR Phase 0: Prototype Validation (Due: 2025-11-21)
  - MVR Phase 1: Foundation Complete (Due: 2025-12-19)
  - MVR Phase 2: Framework & CLI Complete (Due: 2026-02-13)
  - MVR Phase 3: Components Complete (Due: 2026-03-27)
  - MVR Phase 4: MVR Beta Launch (Due: 2026-05-08)

- [x] **21 Labels Created**
  - **Phase labels**: mvr-phase-0-prototype, mvr-phase-1-foundation, mvr-phase-2-framework, mvr-phase-3-components, mvr-phase-4-integration
  - **Priority labels**: P0-critical, P1-high, P2-medium, P3-low
  - **Team labels**: team-dataflow, team-nexus, team-kaizen, team-all
  - **Type labels**: type-template, type-component, type-enhancement, type-testing, type-documentation
  - **Status labels**: mvr-blocked, mvr-decision-gate

- [x] **15 Phase 0 Issues Created**
  - Issue #458: [MVR TODO-001] Build SaaS Template Structure (8h)
  - Issue #468: [MVR TODO-002] Build SaaS Auth Models (8h)
  - Issue #469: [MVR TODO-003] Build SaaS Auth Workflows (12h)
  - Issue #470: [MVR TODO-004] Deploy SaaS Template with Nexus (6h)
  - Issue #471: [MVR TODO-005] Write SaaS Customization Guide (6h)
  - Issue #472: [MVR TODO-006] Create Golden Patterns Top 3 (12h)
  - Issue #473: [MVR TODO-007] Build Golden Patterns Embedding System (8h)
  - Issue #474: [MVR TODO-008] Create DataFlow Utils UUID Field (6h)
  - Issue #475: [MVR TODO-009] Create DataFlow Utils Timestamp Fields (6h)
  - Issue #476: [MVR TODO-010] Create DataFlow Utils Email Field (4h)
  - Issue #477: [MVR TODO-011] Test DataFlow Utils Package (4h)
  - Issue #478: [MVR TODO-012] Recruit Beta Testers (4h)
  - Issue #479: [MVR TODO-013] Conduct Beta Testing Sessions (12h)
  - Issue #480: [MVR TODO-014] Analyze Beta Testing Results (4h)
  - Issue #481: [MVR TODO-015] Go/No-Go Decision (2h) - DECISION GATE

### Pending Setup (Requires Manual Action)
- [ ] **GitHub Project Board** (requires project scope authentication)
- [ ] **Automation Rules** (requires project board)

---

## Step 1: Refresh GitHub Authentication with Project Scopes

GitHub CLI needs additional scopes to manage GitHub Projects:

```bash
gh auth refresh -h github.com -s read:project,write:project,project
```

Follow the browser authentication flow to grant the required scopes.

---

## Step 2: Create GitHub Project Board

### Option A: Using GitHub CLI (Recommended)

```bash
# Create project
gh project create \
  --owner terrene-foundation \
  --title "Kailash MVR Execution" \
  --description "Track MVR execution across 5 phases (67 tasks, 30-36 weeks)"

# Get project number (will be output from previous command)
# Example: Project created: https://github.com/orgs/terrene-foundation/projects/5
# PROJECT_NUMBER=5 (extract from URL)
```

### Option B: Using GitHub Web UI (Alternative)

1. Go to: https://github.com/orgs/terrene-foundation/projects
2. Click "New project"
3. Select "Board" template
4. Project name: "Kailash MVR Execution"
5. Description: "Track MVR execution across 5 phases (67 tasks, 30-36 weeks)"
6. Click "Create project"

---

## Step 3: Configure Project Views

Create 4 views to track MVR progress from different perspectives:

### View 1: Board View (Kanban)

**Purpose**: Track daily task status

**Setup**:
1. Rename default "View 1" to "Board View"
2. Layout: Board
3. Columns:
   - Backlog (status: Todo)
   - In Progress (status: In Progress)
   - In Review (status: In Review)
   - Blocked (label: mvr-blocked)
   - Done (status: Done)
4. Sort: Priority (P0-critical first), then Timeline
5. Group by: Status

**Filters**:
- Labels: Contains any of `mvr-phase-0-prototype`, `mvr-phase-1-foundation`, `mvr-phase-2-framework`, `mvr-phase-3-components`, `mvr-phase-4-integration`

### View 2: Timeline View (Gantt)

**Purpose**: Visualize dependencies and critical path

**Setup**:
1. Create new view: "Timeline View"
2. Layout: Timeline
3. Group by: Epic (manual grouping by EPIC-001, EPIC-002, etc.)
4. Show dependencies: Yes
5. Start date: Today (2025-10-24)
6. End date: Week 28 (2026-05-08)

**Custom Fields Needed**:
- Start Date (Date field)
- Due Date (Date field)
- Dependencies (Text field, comma-separated issue numbers)

### View 3: Team View (By Assignee)

**Purpose**: Track work by team member

**Setup**:
1. Create new view: "Team View"
2. Layout: Board
3. Group by: Assignee
4. Columns:
   - DataFlow Dev (label: team-dataflow)
   - Nexus Dev (label: team-nexus)
   - Kaizen Dev (label: team-kaizen)
   - All Team (label: team-all)
5. Sort: Priority, then Timeline

### View 4: Phase View (By Milestone)

**Purpose**: Track progress by phase/milestone

**Setup**:
1. Create new view: "Phase View"
2. Layout: Table
3. Group by: Milestone
4. Show columns:
   - Title
   - Status
   - Assignee
   - Labels
   - Estimated Effort (custom field)
   - Dependencies (custom field)
5. Sort: Milestone (Phase 0 → Phase 4)

---

## Step 4: Add Issues to Project

### Add All 15 Phase 0 Issues

```bash
# Get project number from Step 2 (example: 5)
PROJECT_NUMBER=5

# Add Phase 0 issues (458, 468-481)
for issue_num in 458 468 469 470 471 472 473 474 475 476 477 478 479 480 481; do
  gh project item-add $PROJECT_NUMBER \
    --owner terrene-foundation \
    --url "https://github.com/terrene-foundation/kailash-py/issues/$issue_num"
done
```

### Add Future Phase Issues (As They Are Created)

When creating issues for Phases 1-4, automatically add them:

```bash
# Example for a new issue
gh issue create --repo terrene-foundation/kailash-py \
  --title "[MVR TODO-016] SaaS Template Refinement (10h)" \
  --milestone "MVR Phase 1: Foundation Complete" \
  --label "mvr-phase-1-foundation,P0-critical,team-dataflow,type-template" \
  --body "..." | \
  xargs -I {} gh project item-add $PROJECT_NUMBER --owner terrene-foundation --url {}
```

---

## Step 5: Set Up Automation Rules

GitHub Projects supports automation rules to reduce manual updates:

### Rule 1: Auto-Move to "In Progress" When Assigned

**Trigger**: Item is assigned
**Action**: Set status to "In Progress"

```
When: assignees changed
Then: Set Status to "In Progress"
```

### Rule 2: Auto-Move to "In Review" When PR Created

**Trigger**: Pull request linked
**Action**: Set status to "In Review"

```
When: pull request linked
Then: Set Status to "In Review"
```

### Rule 3: Auto-Close When Merged

**Trigger**: Pull request merged
**Action**: Set status to "Done", close issue

```
When: pull request merged
Then:
  - Set Status to "Done"
  - Close issue
```

### Rule 4: Mark as Blocked When Label Added

**Trigger**: Label "mvr-blocked" added
**Action**: Move to "Blocked" column

```
When: label "mvr-blocked" added
Then: Set Status to "Blocked"
```

---

## Step 6: Create Custom Fields

Add custom fields to track MVR-specific metadata:

### Custom Field 1: Estimated Effort

- **Type**: Number
- **Name**: Estimated Effort (hours)
- **Description**: Estimated hours to complete task
- **Default**: (empty)

**Populate from issue titles** (e.g., "(8h)" → 8)

### Custom Field 2: Epic

- **Type**: Single Select
- **Name**: Epic
- **Options**:
  - EPIC-001: Minimal SaaS Template Prototype
  - EPIC-002: Golden Patterns Prototype
  - EPIC-003: DataFlow Utils Package Prototype
  - EPIC-004: Beta Testing & Validation
  - EPIC-005: SaaS Template Complete
  - EPIC-006: Golden Patterns Complete
  - EPIC-007: DataFlow Enhancements
  - EPIC-008: Nexus Enhancements
  - EPIC-009: Core SDK Telemetry
  - EPIC-010: CLI Development
  - EPIC-011: kailash-dataflow-utils Complete
  - EPIC-012: kailash-rbac Component
  - EPIC-013: kailash-sso Component
  - EPIC-014: Quick Mode Validation
  - EPIC-015: Integration Testing
  - EPIC-016: Documentation Complete
  - EPIC-017: Beta Launch

### Custom Field 3: Timeline Week

- **Type**: Text
- **Name**: Timeline Week
- **Description**: Week number(s) when task is scheduled
- **Example**: "Week 1 (Days 1-2)"

---

## Step 7: Configure Project Settings

### General Settings

- **Visibility**: Private (visible to terrene-foundation organization members only)
- **README**: Add project description from master todo
- **Short description**: "MVR Execution: 5 phases, 67 tasks, 30-36 weeks"

### Access Control

- **Admin**: Project leads
- **Write**: All 3 developers (DataFlow, Nexus, Kaizen)
- **Read**: Stakeholders

### Notifications

- **Enable notifications for**:
  - Task assigned to me
  - Task blocked
  - Task completed
  - Phase milestone reached
  - Quality gate assessment

---

## Step 8: Initialize Project Dashboard

Create a project README with key information:

```markdown
# Kailash MVR Execution

**Timeline**: 30-36 weeks (2025-10-24 to 2026-05-08)
**Total Effort**: 815 hours (527 core + 288 overhead)
**Team**: 3 developers (DataFlow, Nexus, Kaizen)

## Current Phase: Phase 0 - Prototype Validation

**Goal**: Build and validate minimal prototype with 10 beta testers
**Duration**: 4 weeks (2025-10-24 to 2025-11-21)
**Tasks**: 15 (TODO-001 to TODO-015)
**Decision Gate**: Week 4 - Go/No-Go for full MVR

## Success Criteria (Phase 0)
- NPS 35+ from beta testers
- 80% achieve working app in <30 minutes
- 60% successfully customize template

## Links
- Master Todo: `apps/kailash-nexus/todos/000-master.md`
- Requirements: `.claude/improvements/repivot/adr/ADR-003-mvr-requirements-breakdown.md`
- Timeline Analysis: `.claude/improvements/repivot/adr/ADR-002-mvr-timeline-analysis.md`
- Phase 0 Milestone: https://github.com/terrene-foundation/kailash-py/milestone/4

## Phase Overview
- **Phase 0**: Prototype Validation (Weeks 0-4, 80h, 15 tasks)
- **Phase 1**: Foundation (Weeks 1-8, 135h, 12 tasks)
- **Phase 2**: Framework & CLI (Weeks 9-16, 92h, 11 tasks)
- **Phase 3**: Components (Weeks 13-22, 120h, 17 tasks)
- **Phase 4**: Integration & Launch (Weeks 21-28, 160h, 12 tasks)
```

---

## Step 9: Verify Setup

Run verification checks:

```bash
# 1. Verify milestones
gh api repos/terrene-foundation/kailash-py/milestones --jq '.[] | select(.title | startswith("MVR")) | {title: .title, due_on: .due_on, open_issues: .open_issues}'

# Expected: 5 milestones (Phase 0-4) with due dates

# 2. Verify labels
gh label list --repo terrene-foundation/kailash-py --json name --jq '.[] | select(.name | startswith("mvr-") or startswith("P") or startswith("team-") or startswith("type-")) | .name'

# Expected: 21 MVR-related labels

# 3. Verify Phase 0 issues
gh issue list --repo terrene-foundation/kailash-py --label "mvr-phase-0-prototype" --json number,title,milestone

# Expected: 15 issues (458, 468-481) with Phase 0 milestone

# 4. Verify project (after creation)
gh project list --owner terrene-foundation --json title,number

# Expected: "Kailash MVR Execution" project listed
```

---

## Step 10: Share Project with Team

Once project is set up:

1. **Share project URL** with team:
   - Format: `https://github.com/orgs/terrene-foundation/projects/{PROJECT_NUMBER}`

2. **Create bookmarks** for each view:
   - Board View: `{PROJECT_URL}?view=1`
   - Timeline View: `{PROJECT_URL}?view=2`
   - Team View: `{PROJECT_URL}?view=3`
   - Phase View: `{PROJECT_URL}?view=4`

3. **Add to team communication**:
   - Slack/Discord: Pin project URL
   - Daily standup: Reference Board View
   - Weekly review: Reference Timeline View
   - Sprint planning: Reference Phase View

---

## Troubleshooting

### Issue: "error: your authentication token is missing required scopes [read:project]"

**Solution**: Refresh authentication with project scopes:
```bash
gh auth refresh -h github.com -s read:project,write:project,project
```

### Issue: "could not add to milestone '4': '4' not found"

**Solution**: Use milestone name instead of number:
```bash
gh issue edit ISSUE_NUM --milestone "MVR Phase 0: Prototype Validation"
```

### Issue: Project not showing issues

**Solution**: Manually add issues using web UI:
1. Go to project board
2. Click "Add item"
3. Search for issue number (e.g., #458)
4. Click to add

---

## Next Steps

After completing this setup:

1. Review with team (ensure everyone has access)
2. Start work on TODO-001 (first task)
3. Update GitHub issue status when starting work
4. Set up bidirectional sync (see `github-sync-process.md`)

---

## References

- GitHub Projects Docs: https://docs.github.com/en/issues/planning-and-tracking-with-projects
- GitHub CLI Projects: https://cli.github.com/manual/gh_project
- Master Todo: `apps/kailash-nexus/todos/000-master.md`
