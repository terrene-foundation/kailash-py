# GitHub Issues and Project Board Setup

This directory contains scripts to create GitHub issues for all tasks in the Kailash Python SDK development and set up a project board for tracking progress.

## Prerequisites

1. Ensure you have the GitHub CLI (`gh`) installed:
   ```bash
   brew install gh  # On macOS
   # Or visit: https://cli.github.com/
   ```

2. Authenticate with GitHub:
   ```bash
   gh auth login
   ```

3. Make sure you're in the correct repository:
   ```bash
   gh repo view
   ```

## Steps to Create Issues and Project Board

### 1. Create All Issues

Run the issue creation script:

```bash
./create_github_issues.sh
```

This will create GitHub issues for all tasks in the todo list, including:
- High priority completed tasks (marked as completed)
- Medium priority pending tasks (marked as pending)

Each issue includes:
- Description
- Links to relevant ADRs and PRD
- Acceptance criteria
- Current status
- Appropriate labels

### 2. Create and Link Project Board

After creating issues, run the project board update script:

```bash
./update_project_board.sh
```

This script will:
1. Create a project board called "Kailash Python SDK Development"
2. Link all issues to the project board
3. Provide a URL to view the project

## Task Categories

### High Priority (Completed) ✅
- Base Node implementation
- Node registry system
- Basic node types (readers)
- Workflow DAG implementation
- Connection and mapping system
- Workflow validation
- Local execution engine
- Data passing mechanism
- Execution monitoring
- Task tracking system
- Storage backends
- Export functionality
- AI/ML nodes
- CLI interface
- Testing utilities
- Project scaffolding

### Medium Priority (Pending) 🔄
- Sample nodes and workflows
- Comprehensive example project
- Unit tests for all components
- License file
- Contributing guide
- Docker runtime
- Example directory structure

## Viewing Progress

Once the scripts have run, you can:

1. View all issues:
   ```bash
   gh issue list --state all
   ```

2. View the project board:
   ```bash
   gh project list
   ```

3. Or visit the project board URL provided by the script

## Notes

- Issues are labeled by priority (high/medium) and status (completed/pending)
- Each issue references the relevant ADR or PRD document
- The project board provides a visual overview of development progress