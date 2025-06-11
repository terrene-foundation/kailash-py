#!/usr/bin/env python3
"""
Team Status Report Generator

Generates text-based team status reports for terminal display.
Integrates with GitHub Projects and local TODO files.
"""

import argparse
import json
import logging
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TeamStatus:
    """Generate team status reports."""

    def __init__(self, project_number: int = 1):
        self.project_number = project_number
        self.todo_dir = Path("# contrib (removed)/project/todos")
        self.active_dir = self.todo_dir / "active"
        self.completed_dir = self.todo_dir / "completed"

    def get_github_data(self) -> dict[str, Any]:
        """Fetch data from GitHub Projects and Issues."""
        data = {"issues": [], "prs": [], "project_items": []}

        # Get open issues
        try:
            cmd = [
                "gh",
                "issue",
                "list",
                "--state",
                "open",
                "--json",
                "title,assignees,labels,createdAt,updatedAt,state",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data["issues"] = json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to fetch issues: {e}")

        # Get open PRs
        try:
            cmd = [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--json",
                "title,author,createdAt,updatedAt,state,reviewDecision",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data["prs"] = json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to fetch PRs: {e}")

        # Get project items
        try:
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
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data["project_items"] = json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to fetch project items: {e}")

        return data

    def calculate_workload(self, github_data: dict[str, Any]) -> dict[str, dict]:
        """Calculate workload per team member."""
        workload = defaultdict(
            lambda: {
                "issues": [],
                "prs": [],
                "total_tasks": 0,
                "in_progress": 0,
                "blocked": 0,
                "capacity_percent": 0,
            }
        )

        # Count issues per assignee
        for issue in github_data["issues"]:
            assignees = issue.get("assignees", [])
            for assignee in assignees:
                login = assignee.get("login", "unassigned")
                workload[login]["issues"].append(issue["title"])
                workload[login]["total_tasks"] += 1

                # Check if in progress or blocked
                labels = [line["name"] for line in issue.get("labels", [])]
                if "in-progress" in labels:
                    workload[login]["in_progress"] += 1
                if "blocked" in labels:
                    workload[login]["blocked"] += 1

        # Count PRs per author
        for pr in github_data["prs"]:
            author = pr.get("author", {}).get("login", "unknown")
            workload[author]["prs"].append(pr["title"])

        # Calculate capacity (simple: 3 tasks = 100%)
        for dev, data in workload.items():
            data["capacity_percent"] = min(100, (data["total_tasks"] / 3) * 100)

        return dict(workload)

    def generate_daily_report(self) -> str:
        """Generate daily status report."""
        github_data = self.get_github_data()
        workload = self.calculate_workload(github_data)

        report = []
        report.append("# 📊 Daily Team Status Report")
        report.append(f"\n**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        report.append(f"**Session**: {self._get_current_session()}")

        # Team workload summary
        report.append("\n## 👥 Team Workload\n")
        report.append("| Developer | Tasks | Load % | Status |")
        report.append("|-----------|-------|--------|--------|")

        for dev, data in sorted(workload.items()):
            status = "🟢 OK"
            if data["capacity_percent"] > 85:
                status = "🔴 Overloaded"
            elif data["blocked"] > 0:
                status = "🟡 Blocked"

            report.append(
                f"| {dev} | {data['total_tasks']} | "
                f"{data['capacity_percent']:.0f}% | {status} |"
            )

        # In-progress work
        report.append("\n## 🚀 In Progress\n")
        in_progress_count = 0
        for issue in github_data["issues"]:
            labels = [line["name"] for line in issue.get("labels", [])]
            if "in-progress" in labels:
                assignees = ", ".join([a["login"] for a in issue.get("assignees", [])])
                report.append(f"- {issue['title']} (@{assignees})")
                in_progress_count += 1

        if in_progress_count == 0:
            report.append("*No tasks currently in progress*")

        # Blocked items
        report.append("\n## 🚨 Blocked Items\n")
        blocked_count = 0
        for issue in github_data["issues"]:
            labels = [line["name"] for line in issue.get("labels", [])]
            if "blocked" in labels:
                assignees = ", ".join([a["login"] for a in issue.get("assignees", [])])
                created = datetime.fromisoformat(
                    issue["createdAt"].replace("Z", "+00:00")
                )
                days_old = (datetime.now(created.tzinfo) - created).days
                report.append(f"- {issue['title']} (@{assignees}) - {days_old} days")
                blocked_count += 1

        if blocked_count == 0:
            report.append("*No blocked items* ✅")

        # Open PRs
        report.append("\n## 🔍 Open Pull Requests\n")
        for pr in github_data["prs"][:5]:  # Show top 5
            author = pr.get("author", {}).get("login", "unknown")
            review = pr.get("reviewDecision", "PENDING")
            status_icon = "✅" if review == "APPROVED" else "⏳"
            report.append(f"- {status_icon} {pr['title']} (@{author})")

        if len(github_data["prs"]) > 5:
            report.append(f"*... and {len(github_data['prs']) - 5} more*")

        # Summary metrics
        report.append("\n## 📈 Summary\n")
        total_open = len(github_data["issues"])
        total_prs = len(github_data["prs"])
        avg_capacity = sum(w["capacity_percent"] for w in workload.values()) / max(
            len(workload), 1
        )

        report.append(f"- **Open Issues**: {total_open}")
        report.append(f"- **Open PRs**: {total_prs}")
        report.append(f"- **Team Capacity**: {avg_capacity:.0f}%")
        report.append(f"- **Blocked Items**: {blocked_count}")

        return "\n".join(report)

    def generate_weekly_summary(self) -> str:
        """Generate weekly summary report."""
        github_data = self.get_github_data()

        report = []
        report.append("# 📅 Weekly Team Summary")
        report.append(f"\n**Week Ending**: {datetime.now().strftime('%Y-%m-%d')}")

        # Calculate completion metrics
        datetime.now() - timedelta(days=7)

        # Completed this week (would need to fetch closed issues)
        report.append("\n## ✅ Completed This Week\n")
        report.append("*Note: Run with --include-closed to see completed items*")

        # Velocity metrics
        report.append("\n## 📊 Team Velocity\n")
        workload = self.calculate_workload(github_data)

        for dev, data in sorted(workload.items()):
            report.append(f"**{dev}**:")
            report.append(f"  - Active Tasks: {data['total_tasks']}")
            report.append(f"  - In Progress: {data['in_progress']}")
            report.append(f"  - Blocked: {data['blocked']}")
            report.append("")

        return "\n".join(report)

    def generate_session_progress(self) -> str:
        """Generate session progress report."""
        session = self._get_current_session()

        report = []
        report.append(f"# 🎯 Session {session} Progress Report")
        report.append(f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        # Parse master TODO for goals
        goals = self._parse_session_goals()
        completed = sum(1 for g in goals if g["completed"])
        total = len(goals)

        report.append(
            f"\n## Progress: {completed}/{total} ({(completed/max(total,1)*100):.0f}%)"
        )

        # Progress bar
        progress = int((completed / max(total, 1)) * 20)
        bar = "█" * progress + "░" * (20 - progress)
        report.append(f"\n[{bar}]")

        # Goal status
        report.append("\n## 📋 Session Goals\n")
        for goal in goals:
            status = "✅" if goal["completed"] else "⏳"
            report.append(f"- {status} {goal['title']}")

        return "\n".join(report)

    def _get_current_session(self) -> str:
        """Get current session number from master TODO."""
        master_file = self.todo_dir / "000-master.md"
        if master_file.exists():
            with open(master_file) as f:
                content = f.read()
            import re

            match = re.search(r"Session (\d+)", content)
            if match:
                return match.group(1)
        return "Unknown"

    def _parse_session_goals(self) -> list[dict]:
        """Parse session goals from master TODO."""
        goals = []
        master_file = self.todo_dir / "000-master.md"

        if master_file.exists():
            with open(master_file) as f:
                content = f.read()

            import re

            # Find all checkbox items
            items = re.findall(r"- \[([ x])\] (.+)", content)
            for status, item in items:
                goals.append({"title": item, "completed": status == "x"})

        return goals


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate team status reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "report_type",
        choices=["daily", "weekly", "session", "all"],
        default="daily",
        nargs="?",
        help="Type of report to generate (default: daily)",
    )
    parser.add_argument(
        "--project", type=int, default=1, help="GitHub Project number (default: 1)"
    )
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "plain"],
        default="markdown",
        help="Output format",
    )

    args = parser.parse_args()

    # Generate report
    status = TeamStatus(project_number=args.project)

    if args.report_type == "daily" or args.report_type == "all":
        report = status.generate_daily_report()
    elif args.report_type == "weekly":
        report = status.generate_weekly_summary()
    elif args.report_type == "session":
        report = status.generate_session_progress()
    else:  # all
        reports = []
        reports.append(status.generate_daily_report())
        reports.append("\n" + "=" * 50 + "\n")
        reports.append(status.generate_session_progress())
        report = "\n".join(reports)

    # Convert to plain text if requested
    if args.format == "plain":
        # Simple markdown to plain text conversion
        report = report.replace("**", "")
        report = report.replace("*", "")
        report = report.replace("#", "")
        report = report.replace("|", " ")

    # Output
    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report saved to: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
