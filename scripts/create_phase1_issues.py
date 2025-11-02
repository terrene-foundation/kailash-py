#!/usr/bin/env python3
"""
GitHub Issues Creator for DataFlow DX Improvement - Phase 1

This script creates 64 GitHub issues from Phase 1 task files.
Each issue includes:
- Proper title with phase prefix
- Detailed description with deliverables, acceptance criteria, tests
- Assigned labels (phase, component, priority, type)
- Assigned milestone
- Developer assignment
- Dependencies referenced

Usage:
    python3 scripts/create_phase1_issues.py [--dry-run]

Requirements:
    - gh CLI installed and authenticated
    - Repository: terrene-foundation/kailash-py
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO = "terrene-foundation/kailash-py"
TASK_DIR = Path(
    "./repos/dev/kailash_dataflow/# contrib (removed)/project/todos/active"
)

# Milestone mapping (milestone number from GitHub)
MILESTONES = {
    "Week 2 Checkpoint": 10,
    "Week 2.5 Checkpoint": 11,
    "Week 4 Gate": 12,
    "Week 5 Checkpoint": 13,
    "Week 6 Gate": 14,
    "Week 8 Checkpoint": 15,
    "Week 9 Checkpoint": 16,
    "Week 10 Gate": 17,
}


def parse_task_section(content: str, task_pattern: str) -> List[Dict]:
    """Parse tasks from markdown content."""
    tasks = []

    # Find all task sections
    task_matches = re.finditer(
        r"### (Task \d+\.\d+): (.+?)\n"
        r"- \*\*Status\*\*: (.+?)\n"
        r"- \*\*Estimate\*\*: (.+?)\n"
        r"(?:- \*\*Developer\*\*: (.+?)\n)?"
        r"- \*\*Dependencies\*\*: (.+?)\n"
        r"- \*\*Deliverables\*\*:\n(.+?)"
        r"- \*\*Acceptance Criteria\*\*:\n(.+?)"
        r"(?:- \*\*File Output\*\*: (.+?)\n|"
        r"- \*\*File Modification\*\*: (.+?)\n|"
        r"- \*\*File Creation\*\*: (.+?)\n|"
        r"- \*\*File Analysis\*\*: (.+?)\n)?"
        r"- \*\*Tests\*\*:\n(.+?)\n"
        r"- \*\*Notes\*\*: (.+?)(?=\n###|\n---|\nZ)",
        content,
        re.DOTALL,
    )

    for match in task_matches:
        task_id = match.group(1)
        title = match.group(2)
        status = match.group(3)
        estimate = match.group(4)
        developer = match.group(5) if match.group(5) else "Both"
        dependencies = match.group(6)
        deliverables = match.group(7).strip()
        acceptance = match.group(8).strip()

        # Get file info (can be in multiple groups)
        file_info = None
        for i in range(9, 13):
            if match.group(i):
                file_info = match.group(i)
                break

        tests = match.group(13) if match.lastindex >= 13 else "None"
        notes = match.group(14) if match.lastindex >= 14 else ""

        tasks.append(
            {
                "id": task_id,
                "title": title,
                "status": status,
                "estimate": estimate,
                "developer": developer,
                "dependencies": dependencies,
                "deliverables": deliverables,
                "acceptance": acceptance,
                "file_info": file_info,
                "tests": tests,
                "notes": notes,
            }
        )

    return tasks


def create_issue_body(task: Dict, phase: str, component: str) -> str:
    """Create GitHub issue body from task data."""
    body = f"""## Task: {task['title']}

**Phase**: {phase}
**Component**: {component}
**Estimate**: {task['estimate']}
**Developer**: {task['developer']}
**Dependencies**: {task['dependencies']}

### Deliverables

{task['deliverables']}

### Acceptance Criteria

{task['acceptance']}
"""

    if task["file_info"]:
        body += f"""
### File Output

{task['file_info']}
"""

    body += f"""
### Tests

{task['tests']}

### Notes

{task['notes']}

---

*This issue is part of the DataFlow DX Improvement - Phase 1 project*
"""

    return body


def get_milestone_for_task(task_id: str, week: str) -> int:
    """Determine milestone based on task timing."""
    # Parse week number from task
    if "Week 1" in week or "Week 2" in week and "2.5" not in week:
        return MILESTONES["Week 2 Checkpoint"]
    elif "Week 2.5" in week or "Week 3" in week:
        return MILESTONES["Week 2.5 Checkpoint"]
    elif "Week 4" in week:
        return MILESTONES["Week 4 Gate"]
    elif "Week 5" in week:
        return MILESTONES["Week 5 Checkpoint"]
    elif "Week 6" in week:
        return MILESTONES["Week 6 Gate"]
    elif "Week 7" in week or "Week 8" in week:
        return MILESTONES["Week 8 Checkpoint"]
    elif "Week 9" in week:
        return MILESTONES["Week 9 Checkpoint"]
    elif "Week 10" in week:
        return MILESTONES["Week 10 Gate"]
    else:
        return MILESTONES["Week 4 Gate"]  # Default


def get_labels_for_task(
    phase: str, component: str, priority: str, task_type: str
) -> List[str]:
    """Get labels for a task."""
    labels = ["dataflow-dx"]

    # Phase label
    phase_map = {
        "Phase 1A": "phase-1a-quick-wins",
        "Phase 1B": "phase-1b-validation",
        "Phase 1C": "phase-1c-enhancements",
    }
    labels.append(phase_map.get(phase, "phase-1a-quick-wins"))

    # Component label
    component_map = {
        "ErrorEnhancer": "component-errorenhancer",
        "Inspector": "component-inspector",
        "Documentation": "component-documentation",
        "Validation": "component-validation",
        "CLI": "component-cli",
        "Knowledge Base": "component-knowledge-base",
        "Core Errors": "component-core-errors",
        "Strict Mode": "component-strict-mode",
        "AI Agent": "component-ai-agent",
    }
    labels.append(component_map.get(component, "component-errorenhancer"))

    # Priority label
    labels.append(f"priority-{priority}")

    # Type label
    if "Test" in task_type or "Testing" in task_type:
        labels.append("type-testing")
    elif "Documentation" in task_type or "Doc" in task_type:
        labels.append("type-documentation")
    elif "Gate" in task_type or "Validation Gate" in task_type:
        labels.append("type-validation-gate")
    else:
        labels.append("type-implementation")

    return labels


def create_github_issue(
    title: str, body: str, labels: List[str], milestone: int, dry_run: bool = False
) -> Tuple[bool, str]:
    """Create a GitHub issue using gh CLI."""
    if dry_run:
        print(f"[DRY RUN] Would create issue: {title}")
        print(f"  Labels: {', '.join(labels)}")
        print(f"  Milestone: {milestone}")
        return True, "dry-run-url"

    # Build gh command
    cmd = [
        "gh",
        "issue",
        "create",
        "--repo",
        REPO,
        "--title",
        title,
        "--body",
        body,
        "--milestone",
        str(milestone),
    ]

    # Add labels
    for label in labels:
        cmd.extend(["--label", label])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issue_url = result.stdout.strip()
        return True, issue_url
    except subprocess.CalledProcessError as e:
        return False, str(e)


def main():
    """Main execution function."""
    dry_run = "--dry-run" in sys.argv

    print("=" * 80)
    print("DataFlow DX Improvement - Phase 1: GitHub Issue Creator")
    print("=" * 80)
    if dry_run:
        print("\n*** DRY RUN MODE - No issues will be created ***\n")
    print()

    # Track created issues
    created_issues = []
    failed_issues = []

    # Phase 1A: ErrorEnhancer (15 tasks)
    print("Phase 1A: ErrorEnhancer - Processing 15 tasks...")
    task_file = TASK_DIR / "phase-1a-errorenhancer.md"
    if task_file.exists():
        content = task_file.read_text()
        tasks = parse_task_section(content, r"### Task (\d+\.\d+):")

        for i, task in enumerate(tasks, 1):
            title = f"[Phase 1A] ErrorEnhancer - {task['title']}"
            body = create_issue_body(task, "Phase 1A", "ErrorEnhancer")
            labels = get_labels_for_task(
                "Phase 1A", "ErrorEnhancer", "p0-critical", task["title"]
            )

            # Determine milestone based on task number
            if i <= 6:
                milestone = MILESTONES["Week 2 Checkpoint"]
            elif i <= 10:
                milestone = MILESTONES["Week 2.5 Checkpoint"]
            else:
                milestone = MILESTONES["Week 4 Gate"]

            success, result = create_github_issue(
                title, body, labels, milestone, dry_run
            )

            if success:
                created_issues.append((title, result))
                print(f"  ✓ Created: {title}")
            else:
                failed_issues.append((title, result))
                print(f"  ✗ Failed: {title} - {result}")

    # Phase 1A: Inspector (8 tasks)
    print("\nPhase 1A: Inspector - Processing 8 tasks...")
    task_file = TASK_DIR / "phase-1a-inspector.md"
    if task_file.exists():
        content = task_file.read_text()
        tasks = parse_task_section(content, r"### Task (\d+\.\d+):")

        for i, task in enumerate(tasks, 1):
            title = f"[Phase 1A] Inspector - {task['title']}"
            body = create_issue_body(task, "Phase 1A", "Inspector")
            labels = get_labels_for_task(
                "Phase 1A", "Inspector", "p0-critical", task["title"]
            )

            if i <= 4:
                milestone = MILESTONES["Week 2 Checkpoint"]
            else:
                milestone = MILESTONES["Week 2.5 Checkpoint"]

            success, result = create_github_issue(
                title, body, labels, milestone, dry_run
            )

            if success:
                created_issues.append((title, result))
                print(f"  ✓ Created: {title}")
            else:
                failed_issues.append((title, result))
                print(f"  ✗ Failed: {title} - {result}")

    # Phase 1A: Documentation (8 tasks)
    print("\nPhase 1A: Documentation - Processing 8 tasks...")
    task_file = TASK_DIR / "phase-1a-documentation.md"
    if task_file.exists():
        content = task_file.read_text()
        tasks = parse_task_section(content, r"### Task (\d+\.\d+):")

        for task in tasks:
            title = f"[Phase 1A] Documentation - {task['title']}"
            body = create_issue_body(task, "Phase 1A", "Documentation")
            labels = get_labels_for_task(
                "Phase 1A", "Documentation", "p0-critical", task["title"]
            )
            milestone = MILESTONES["Week 4 Gate"]

            success, result = create_github_issue(
                title, body, labels, milestone, dry_run
            )

            if success:
                created_issues.append((title, result))
                print(f"  ✓ Created: {title}")
            else:
                failed_issues.append((title, result))
                print(f"  ✗ Failed: {title} - {result}")

    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Issues Created: {len(created_issues)}")
    print(f"Issues Failed: {len(failed_issues)}")

    if failed_issues:
        print("\nFailed Issues:")
        for title, error in failed_issues:
            print(f"  - {title}: {error}")

    if not dry_run and created_issues:
        print("\nNext Steps:")
        print("1. Go to GitHub Project and add these issues")
        print("2. Set custom field values (Phase, Week, Component, etc.)")
        print("3. Link dependencies between issues")
        print("4. Assign Developer 1 and Developer 2")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
