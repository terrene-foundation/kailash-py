#!/bin/bash
# Setup GitHub Projects for Kailash SDK
# This script creates the project boards and configures initial settings

set -e

echo "🚀 Setting up GitHub Projects for Kailash SDK"
echo "============================================"

# Get repository information
REPO_OWNER=$(gh repo view --json owner -q .owner.login)
REPO_NAME=$(gh repo view --json name -q .name)

echo "Repository: $REPO_OWNER/$REPO_NAME"
echo ""

# Function to create a project if it doesn't exist
create_project() {
    local name="$1"
    local description="$2"

    echo "📋 Checking if project '$name' exists..."

    # Check if project exists (this is a simplified check)
    if gh project list --owner "$REPO_OWNER" --format json | jq -e ".[] | select(.title == \"$name\")" > /dev/null; then
        echo "   ✓ Project already exists"
    else
        echo "   → Creating project '$name'..."
        gh project create --owner "$REPO_OWNER" --title "$name" --body "$description"
        echo "   ✓ Project created"
    fi
}

# Create the three main project boards
create_project "Kailash SDK Development" "Main development tracking board for active work"
create_project "Kailash SDK Releases" "Release planning and milestone tracking"
create_project "Kailash SDK User Experience" "User-facing improvements, documentation, and examples"

echo ""
echo "🏷️  Setting up labels..."
echo ""

# Function to create label if it doesn't exist
create_label() {
    local name="$1"
    local color="$2"
    local description="$3"

    # Check if label exists
    if gh label list --json name | jq -e ".[] | select(.name == \"$name\")" > /dev/null 2>&1; then
        echo "   ✓ Label '$name' already exists"
    else
        echo "   → Creating label '$name'..."
        gh label create "$name" --color "$color" --description "$description"
    fi
}

# Priority labels
echo "Priority labels:"
create_label "P0-critical" "FF0000" "Production blocker"
create_label "P1-high" "FF6B6B" "Current session priority"
create_label "P2-medium" "FFD93D" "Next session candidate"
create_label "P3-low" "6BCB77" "Backlog item"

echo ""
echo "Area labels:"
# Area labels
create_label "area/core" "0052CC" "Core workflow functionality"
create_label "area/mcp" "5319E7" "MCP integration"
create_label "area/api" "E99695" "REST API & Gateway"
create_label "area/quality" "FBCA04" "Testing & CI/CD"
create_label "area/workflows" "84CE84" "Workflow library"
create_label "area/docs" "0075CA" "Documentation"
create_label "area/studio" "D93F0B" "Workflow Studio UI"

echo ""
echo "Type labels:"
# Type labels
create_label "type/feature" "7057FF" "New functionality"
create_label "type/bug" "D73A4A" "Bug fix"
create_label "type/enhancement" "A2EEEF" "Improvement"
create_label "type/docs" "0075CA" "Documentation"
create_label "type/test" "FFD93D" "Testing"
create_label "type/refactor" "D4C5F9" "Code refactoring"

echo ""
echo "Status labels:"
# Status labels
create_label "status/needs-triage" "FFFFFF" "Requires assessment"
create_label "status/ready" "0E8A16" "Ready for development"
create_label "status/blocked" "E11D21" "Blocked by dependency"
create_label "status/needs-review" "FBCA04" "Awaiting review"
create_label "status/stale" "795548" "Inactive item"

echo ""
echo "📝 Creating issue templates..."
echo ""

# Check if issue templates directory exists
if [ ! -d ".github/ISSUE_TEMPLATE" ]; then
    mkdir -p .github/ISSUE_TEMPLATE
    echo "   → Created .github/ISSUE_TEMPLATE directory"
fi

# Create session task template
cat > .github/ISSUE_TEMPLATE/session-task.md << 'EOF'
---
name: Session Task
about: Create a task for development session work
title: '[Session] '
labels: 'status/needs-triage'
assignees: ''
---

## Session Task: [Brief Description]

**Session**: #[number]
**Area**: [core/mcp/api/quality/workflows]
**Priority**: [P0/P1/P2/P3]

### Context
[Link to relevant TODO file or ADR]

### Acceptance Criteria
- [ ] Implementation complete
- [ ] Tests written and passing
- [ ] Example created in `examples/`
- [ ] Documentation updated
- [ ] Mistakes tracked in `shared/mistakes/`

### Related
- Depends on: #[issue]
- Blocks: #[issue]
- Related PR: #[pr]
EOF

# Create user feature request template
cat > .github/ISSUE_TEMPLATE/user-feature.md << 'EOF'
---
name: User Feature Request
about: Suggest a feature for SDK users
title: '[Feature] '
labels: 'type/feature, status/needs-triage'
assignees: ''
---

## Feature: [User-facing feature name]

**User Story**: As a [role], I want to [action] so that [benefit]

### Current Behavior
[What happens now]

### Desired Behavior
[What should happen]

### Example Use Case
```python
# Show desired API usage
```

### Implementation Notes
- [ ] Update skills documentation
- [ ] Create example in `examples/`
- [ ] Add to workflow library if applicable
EOF

echo "   ✓ Created issue templates"

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📚 Next steps:"
echo "   1. Visit https://github.com/$REPO_OWNER/$REPO_NAME/projects to view your project boards"
echo "   2. Configure columns for each board as specified in .github/PROJECT_MANAGEMENT.md"
echo "   3. Set up project automation rules in the project settings"
echo "   4. Review and customize the workflow files in .github/workflows/"
echo ""
echo "📖 Documentation:"
echo "   - Project management guide: .github/PROJECT_MANAGEMENT.md"
echo "   - Migration guide: .github/MIGRATION_TO_PROJECTS.md"
echo "   - Automation workflow: .github/workflows/project-automation.yml"
echo ""
echo "💡 Tip: Run 'gh project list --owner $REPO_OWNER' to see all projects"
