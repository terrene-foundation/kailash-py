#!/usr/bin/env python3
"""
Sync between File TODOs, GitHub Projects, and GitHub Issues.

Enhanced to support natural language parsing from Claude Code responses.

This script maintains synchronization between our three collaboration tools:
- File TODOs: Strategic planning and session management
- GitHub Projects: Visual workflow and story tracking
- GitHub Issues: Atomic tasks and implementation details
"""

import argparse
import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CollaborationSync:
    """Manages synchronization between file TODOs, Projects, and Issues."""

    def __init__(self, project_number: int = 1):
        self.project_number = project_number
        self.todo_dir = Path("# contrib (removed)/project/todos")
        self.active_dir = self.todo_dir / "active"
        self.completed_dir = self.todo_dir / "completed"
        self.team_profiles = self._load_team_profiles()

    def _load_team_profiles(self) -> Dict[str, Dict]:
        """Load team profiles from file."""
        profiles_path = Path(
            "# contrib (removed)/operations/claude-code-workflows/team-profiles.md"
        )
        if not profiles_path.exists():
            logger.warning("Team profiles not found")
            return {}

        # Simple parsing - in production would use more robust parsing
        profiles = {}
        current_dev = None

        with open(profiles_path, "r") as f:
            for line in f:
                if line.startswith("## "):
                    # Extract developer ID
                    match = re.search(r"## (\w+)", line)
                    if match:
                        current_dev = match.group(1)
                        profiles[current_dev] = {
                            "skills": [],
                            "availability": "full",
                            "current_load": 0,
                        }
                elif current_dev and "Skills:" in line:
                    # Parse skills on next lines
                    profiles[current_dev]["skills"] = []
                elif current_dev and "Availability:" in line:
                    match = re.search(r"Availability: (\w+)", line)
                    if match:
                        profiles[current_dev]["availability"] = match.group(1)

        return profiles

    def parse_natural_language_response(self, response: str) -> Dict[str, Any]:
        """Parse Claude Code natural language response into structured data."""
        parsed = {"tasks": [], "assignments": {}, "workload": {}, "actions": []}

        # Parse task breakdowns
        task_pattern = r"(\d+)\.\s+(.+?)(?:\n|$)"
        tasks = re.findall(task_pattern, response, re.MULTILINE)
        for num, task in tasks:
            parsed["tasks"].append(
                {
                    "number": int(num),
                    "description": task.strip(),
                    "complexity": self._extract_complexity(task),
                    "duration": self._extract_duration(task),
                }
            )

        # Parse assignments (Task -> Developer)
        assignment_pattern = r"(.+?)\s*->\s*(\w+)\s*\((\d+)%.*?\)"
        assignments = re.findall(assignment_pattern, response)
        for task, dev, skill_match in assignments:
            parsed["assignments"][task.strip()] = {
                "developer": dev,
                "skill_match": int(skill_match),
            }

        # Parse workload information
        workload_pattern = r"(\w+)\s*\|\s*(\d+)\s*\|\s*(\d+)%"
        workloads = re.findall(workload_pattern, response)
        for dev, tasks, load in workloads:
            parsed["workload"][dev] = {
                "task_count": int(tasks),
                "load_percentage": int(load),
            }

        # Parse action commands
        if "execute the plan" in response.lower():
            parsed["actions"].append("execute_plan")
        if "create github issues" in response.lower():
            parsed["actions"].append("create_issues")
        if "update todos" in response.lower():
            parsed["actions"].append("update_todos")

        return parsed

    def _extract_complexity(self, text: str) -> str:
        """Extract complexity from task description."""
        if re.search(r"\b(simple|trivial|easy)\b", text, re.IGNORECASE):
            return "Simple"
        elif re.search(r"\b(complex|difficult|hard)\b", text, re.IGNORECASE):
            return "Complex"
        return "Medium"

    def _extract_duration(self, text: str) -> int:
        """Extract duration in days from task description."""
        match = re.search(r"(\d+)\s*days?", text)
        if match:
            return int(match.group(1))
        return 3  # Default to 3 days

    def sync_all(self):
        """Run full synchronization between all tools."""
        logger.info("Starting full synchronization...")

        # 1. Parse file TODOs to find session goals
        session_goals = self.parse_session_goals()

        # 2. Ensure Project stories exist for active goals
        self.sync_goals_to_stories(session_goals)

        # 3. Update file TODOs with Project status
        self.sync_stories_to_todos()

        # 4. Generate sync report
        self.generate_sync_report()

        logger.info("Synchronization complete!")

    def parse_session_goals(self) -> List[Dict]:
        """Parse active TODO files to extract session goals."""
        goals = []

        # Parse master TODO
        master_file = self.todo_dir / "000-master.md"
        if master_file.exists():
            with open(master_file, "r") as f:
                content = f.read()

            # Extract current session number
            session_match = re.search(r"Session (\d+)", content)
            session_num = session_match.group(1) if session_match else "Unknown"

            # Extract active work items
            active_section = re.search(
                r"## Active Work.*?(?=##|\Z)", content, re.DOTALL
            )
            if active_section:
                items = re.findall(r"- \[([ x])\] (.+)", active_section.group(0))
                for status, item in items:
                    goals.append(
                        {
                            "session": session_num,
                            "title": item,
                            "completed": status == "x",
                            "source": "master",
                        }
                    )

        # Parse area-specific TODOs
        for todo_file in self.active_dir.glob("*.md"):
            area = todo_file.stem
            with open(todo_file, "r") as f:
                content = f.read()

            # Extract TODOs
            todos = re.findall(r"- \[([ x])\] (.+)", content)
            for status, todo in todos:
                goals.append(
                    {
                        "session": session_num,
                        "title": todo,
                        "completed": status == "x",
                        "area": area,
                        "source": todo_file.name,
                    }
                )

        logger.info(f"Found {len(goals)} session goals")
        return goals

    def sync_goals_to_stories(self, goals: List[Dict]):
        """Ensure GitHub Project stories exist for session goals."""
        # Get existing project items
        existing_stories = self.get_project_stories()
        existing_titles = {story["title"] for story in existing_stories}

        for goal in goals:
            if goal["completed"]:
                continue

            story_title = f"[Session {goal['session']}] {goal['title']}"

            if story_title not in existing_titles:
                # Create new story in Project
                logger.info(f"Creating story: {story_title}")
                self.create_project_story(story_title, goal)

    def get_project_stories(self) -> List[Dict]:
        """Fetch all stories from GitHub Project."""
        cmd = [
            "gh",
            "project",
            "item-list",
            str(self.project_number),
            "--format",
            "json",
            "--limit",
            "100",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            items = json.loads(result.stdout)

            # Filter for story-type items (not individual issues)
            stories = [
                item for item in items if item.get("title", "").startswith("[Session")
            ]

            return stories
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to fetch project items: {e}")
            return []

    def create_project_story(self, title: str, goal: Dict):
        """Create a new story in GitHub Project."""
        # First create as draft issue
        body = f"""
## Session Goal

**Source**: {goal.get('source', 'Unknown')}
**Area**: {goal.get('area', 'General')}

### Description
{goal['title']}

### Acceptance Criteria
- [ ] Implementation complete
- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] Example created if applicable

### Linked Issues
<!-- Issues will be linked here -->

---
*This story was auto-generated from file-based TODOs*
        """

        cmd = [
            "gh",
            "issue",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--label",
            f"area/{goal.get('area', 'general')}",
            "--label",
            "type/story",
            "--project",
            str(self.project_number),
        ]

        if "area" in goal:
            cmd.extend(["--label", f"area/{goal['area']}"])

        try:
            subprocess.run(cmd, check=True)
            logger.info(f"Created story: {title}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create story: {e}")

    def sync_stories_to_todos(self):
        """Update TODO files with current Project status."""
        # Get completed stories from Project
        stories = self.get_project_stories()
        completed_stories = [
            s
            for s in stories
            if s.get("status", "").lower() in ["done", "completed", "released"]
        ]

        # Update master TODO
        if completed_stories:
            self.update_master_todo(completed_stories)

    def update_master_todo(self, completed_stories: List[Dict]):
        """Update master TODO with completed items."""
        master_file = self.todo_dir / "000-master.md"
        if not master_file.exists():
            return

        with open(master_file, "r") as f:
            content = f.read()

        # Mark completed items
        for story in completed_stories:
            # Extract original title without session prefix
            match = re.search(r"\[Session \d+\] (.+)", story["title"])
            if match:
                original_title = match.group(1)
                # Update checkbox
                pattern = rf"- \[ \] {re.escape(original_title)}"
                replacement = f"- [x] {original_title}"
                content = re.sub(pattern, replacement, content)

        with open(master_file, "w") as f:
            f.write(content)

        logger.info(
            f"Updated master TODO with {len(completed_stories)} completed items"
        )

    def generate_sync_report(self):
        """Generate a synchronization report."""
        report_file = self.todo_dir / "sync_report.md"

        # Gather statistics
        stories = self.get_project_stories()
        active_stories = [s for s in stories if s.get("status") == "In Progress"]
        completed_stories = [
            s for s in stories if s.get("status") in ["Done", "Completed"]
        ]

        report = f"""# Collaboration Tools Sync Report

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary

- **Total Project Stories**: {len(stories)}
- **Active Stories**: {len(active_stories)}
- **Completed Stories**: {len(completed_stories)}

## Active Work

### In Progress
"""

        for story in active_stories:
            report += f"- {story['title']}\n"

        report += "\n### Recently Completed\n"
        for story in completed_stories[:5]:
            report += f"- ✅ {story['title']}\n"

        report += "\n## Sync Actions Taken\n"
        report += "- Parsed file TODOs for session goals\n"
        report += "- Created missing Project stories\n"
        report += "- Updated TODO completion status\n"

        with open(report_file, "w") as f:
            f.write(report)

        logger.info(f"Sync report generated: {report_file}")

    def execute_claude_plan(self, claude_response: str):
        """Execute a plan based on Claude Code's natural language response."""
        parsed = self.parse_natural_language_response(claude_response)

        if "execute_plan" in parsed["actions"]:
            logger.info("Executing Claude Code plan...")

            # Create issues for assigned tasks
            for task_desc, assignment in parsed["assignments"].items():
                developer = assignment["developer"]
                skill_match = assignment["skill_match"]

                # Find matching task details
                task_details = next(
                    (t for t in parsed["tasks"] if task_desc in t["description"]), None
                )

                if task_details:
                    self._create_issue_from_task(task_details, developer, skill_match)

            # Update TODO files
            self._update_todos_from_plan(parsed)

            # Generate execution report
            self._generate_execution_report(parsed)

    def _create_issue_from_task(self, task: Dict, developer: str, skill_match: int):
        """Create GitHub issue from task details."""
        session = self._get_current_session()
        title = f"[Session {session}] {task['description']}"

        body = f"""
## Task Details

**Complexity**: {task['complexity']}
**Estimated Duration**: {task['duration']} days
**Assigned to**: @{developer}
**Skill Match**: {skill_match}%

## Acceptance Criteria
- [ ] Implementation complete
- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] Example created if applicable

---
*Auto-created from Claude Code plan*
        """

        cmd = [
            "gh",
            "issue",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--assignee",
            developer,
            "--label",
            f"complexity/{task['complexity'].lower()}",
            "--label",
            f"session-{session}",
            "--project",
            str(self.project_number),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            issue_url = result.stdout.strip()
            logger.info(f"Created issue: {issue_url}")
            return issue_url
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create issue: {e}")
            return None

    def _get_current_session(self) -> str:
        """Get current session number from master TODO."""
        master_file = self.todo_dir / "000-master.md"
        if master_file.exists():
            with open(master_file, "r") as f:
                content = f.read()
            match = re.search(r"Session (\d+)", content)
            if match:
                return match.group(1)
        return "Unknown"

    def _update_todos_from_plan(self, parsed: Dict):
        """Update TODO files based on executed plan."""
        # Update master TODO with new tasks
        master_file = self.todo_dir / "000-master.md"
        if master_file.exists():
            with open(master_file, "r") as f:
                content = f.read()

            # Add new tasks to active section
            active_section = content.find("## Active Work")
            if active_section != -1:
                # Find end of active section
                next_section = content.find("##", active_section + 1)
                if next_section == -1:
                    next_section = len(content)

                # Insert new tasks
                new_tasks = []
                for task in parsed["tasks"]:
                    assigned_to = None
                    for desc, assignment in parsed["assignments"].items():
                        if desc in task["description"]:
                            assigned_to = assignment["developer"]
                            break

                    task_line = f"- [ ] {task['description']}"
                    if assigned_to:
                        task_line += f" (@{assigned_to})"
                    new_tasks.append(task_line)

                if new_tasks:
                    insert_pos = content.rfind("\n", active_section, next_section)
                    new_content = (
                        content[:insert_pos]
                        + "\n"
                        + "\n".join(new_tasks)
                        + content[insert_pos:]
                    )

                    with open(master_file, "w") as f:
                        f.write(new_content)

                    logger.info(f"Updated master TODO with {len(new_tasks)} new tasks")

    def _generate_execution_report(self, parsed: Dict):
        """Generate report of plan execution."""
        report = []
        report.append("# Claude Code Plan Execution Report")
        report.append(
            f"\n**Executed at**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        report.append("\n## Tasks Created")
        for task in parsed["tasks"]:
            report.append(
                f"- {task['description']} ({task['complexity']}, {task['duration']} days)"
            )

        report.append("\n## Assignments")
        for task_desc, assignment in parsed["assignments"].items():
            report.append(
                f"- {task_desc} → @{assignment['developer']} ({assignment['skill_match']}% match)"
            )

        report.append("\n## Workload Summary")
        for dev, workload in parsed["workload"].items():
            report.append(
                f"- @{dev}: {workload['task_count']} tasks, {workload['load_percentage']}% capacity"
            )

        report_content = "\n".join(report)
        logger.info("\n" + report_content)

        # Save report
        report_file = (
            self.todo_dir
            / f"execution_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        )
        with open(report_file, "w") as f:
            f.write(report_content)

        logger.info(f"Execution report saved to: {report_file}")


def main():
    """Run the synchronization."""
    parser = argparse.ArgumentParser(
        description="Sync between file TODOs, GitHub Projects, and Issues"
    )
    parser.add_argument(
        "--project", type=int, default=1, help="GitHub Project number (default: 1)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--execute-claude-response",
        type=str,
        help="Execute a plan from Claude Code response (provide response text or file path)",
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="Only parse Claude response without executing",
    )

    args = parser.parse_args()

    # Initialize sync
    sync = CollaborationSync(project_number=args.project)

    if args.execute_claude_response:
        # Handle Claude Code response execution
        response = args.execute_claude_response

        # Check if it's a file path
        if Path(response).exists():
            with open(response, "r") as f:
                response = f.read()

        if args.parse_only:
            # Just parse and show the result
            parsed = sync.parse_natural_language_response(response)
            print(json.dumps(parsed, indent=2))
        else:
            # Execute the plan
            sync.execute_claude_plan(response)
    else:
        # Run normal sync
        sync.sync_all()


if __name__ == "__main__":
    main()
