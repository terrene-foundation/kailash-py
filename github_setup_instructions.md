# GitHub Issues and Project Board Setup Instructions

## Step-by-Step Guide

### 1. Authenticate with GitHub CLI

First, make sure you're authenticated:

```bash
gh auth login
```

### 2. Create Labels

Before creating issues, create the necessary labels:

```bash
./create_labels.sh
```

This will create:
- Priority labels: high-priority, medium-priority, low-priority
- Status labels: completed, in-progress
- Type labels: testing, documentation, enhancement

### 3. Create Issues

Now create all the issues:

```bash
./create_github_issues_fixed.sh
```

This will create issues for all tasks with:
- Detailed descriptions
- Links to relevant ADRs and PRD
- Acceptance criteria
- Appropriate labels

### 4. Create and Update Project Board

After creating issues, set up the project board:

```bash
./update_project_board.sh
```

## Troubleshooting

If you get errors about labels not being found:
1. Run `./create_labels.sh` to create the missing labels
2. Then run `./create_github_issues_fixed.sh` again

If you get errors about unknown flags:
- The fixed script now uses the correct `gh project create` syntax without the --description flag

## Scripts Overview

1. **`create_labels.sh`** - Creates all necessary labels
2. **`create_github_issues_fixed.sh`** - Creates issues without 'pending' label
3. **`update_project_board.sh`** - Links issues to project board

## What Gets Created

- **48 GitHub Issues**:
  - 41 completed high-priority tasks
  - 7 pending medium-priority tasks
- **Project Board**: "Kailash Python SDK Development"
- **Labels**: priority levels, status indicators, and type labels

All issues include references to the relevant Architecture Decision Records (ADRs) and Product Requirements Document (PRD).