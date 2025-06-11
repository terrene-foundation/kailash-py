#!/usr/bin/env python3
"""
Claude Code Helper - Parse and execute Claude Code responses.

This script acts as a bridge between Claude Code natural language responses
and actual system commands, making it easy to pipe Claude output to actions.
"""

import argparse
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ClaudeCodeHelper:
    """Helper to parse and execute Claude Code responses."""

    def __init__(self):
        self.patterns = {
            "create_branch": r"(?:create|checkout) (?:branch|new branch):\s*([^\s]+)",
            "run_command": r"(?:run|execute):\s*`([^`]+)`",
            "create_issue": r'create (?:github )?issue.*?title:\s*"([^"]+)"',
            "update_file": r"update\s+([^\s]+)\s+with:?\s*(.+)",
            "git_commands": r"git\s+(\w+)(?:\s+(.+))?",
            "progress_update": r"progress.*?(\d+)%",
            "status_change": r"status:\s*(pending|in.?progress|completed|blocked)",
        }

    def parse_response(self, response: str) -> dict[str, Any]:
        """Parse Claude Code response to extract actionable items."""
        actions = {
            "branches": [],
            "commands": [],
            "issues": [],
            "file_updates": [],
            "progress": [],
            "status_changes": [],
            "raw_actions": [],
        }

        # Extract branch operations
        for match in re.finditer(
            self.patterns["create_branch"], response, re.IGNORECASE
        ):
            branch_name = match.group(1)
            actions["branches"].append({"action": "create", "name": branch_name})
            actions["raw_actions"].append(f"git checkout -b {branch_name}")

        # Extract commands to run
        for match in re.finditer(self.patterns["run_command"], response):
            command = match.group(1)
            actions["commands"].append(command)
            actions["raw_actions"].append(command)

        # Extract issue creation
        for match in re.finditer(
            self.patterns["create_issue"], response, re.IGNORECASE
        ):
            title = match.group(1)
            actions["issues"].append(
                {"title": title, "body": self._extract_issue_body(response, title)}
            )

        # Extract progress updates
        for match in re.finditer(
            self.patterns["progress_update"], response, re.IGNORECASE
        ):
            percentage = int(match.group(1))
            actions["progress"].append(percentage)

        # Extract status changes
        for match in re.finditer(
            self.patterns["status_change"], response, re.IGNORECASE
        ):
            status = match.group(1).lower().replace(" ", "_")
            actions["status_changes"].append(status)

        # Extract git commands
        for match in re.finditer(self.patterns["git_commands"], response):
            git_cmd = match.group(1)
            git_args = match.group(2) or ""
            actions["raw_actions"].append(f"git {git_cmd} {git_args}".strip())

        return actions

    def _extract_issue_body(self, response: str, title: str) -> str:
        """Extract issue body content after title mention."""
        # Try to find content after the title
        title_pos = response.find(title)
        if title_pos != -1:
            # Look for body content after title
            body_match = re.search(
                r'body:\s*"([^"]+)"',
                response[title_pos : title_pos + 500],
                re.IGNORECASE | re.DOTALL,
            )
            if body_match:
                return body_match.group(1)

        return "Auto-generated from Claude Code response"

    def execute_actions(self, actions: dict[str, Any], dry_run: bool = False):
        """Execute parsed actions."""
        results = []

        # Execute raw commands
        for cmd in actions["raw_actions"]:
            if dry_run:
                print(f"[DRY RUN] Would execute: {cmd}")
                results.append({"command": cmd, "status": "dry_run"})
            else:
                try:
                    logger.info(f"Executing: {cmd}")
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True
                    )
                    results.append(
                        {
                            "command": cmd,
                            "status": "success" if result.returncode == 0 else "failed",
                            "output": result.stdout,
                            "error": result.stderr,
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to execute {cmd}: {e}")
                    results.append({"command": cmd, "status": "error", "error": str(e)})

        # Create GitHub issues
        for issue in actions["issues"]:
            cmd = f'gh issue create --title "{issue["title"]}" --body "{issue["body"]}"'
            if dry_run:
                print(f"[DRY RUN] Would create issue: {issue['title']}")
            else:
                try:
                    logger.info(f"Creating issue: {issue['title']}")
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True
                    )
                    results.append(
                        {
                            "command": cmd,
                            "status": "success" if result.returncode == 0 else "failed",
                            "output": result.stdout,
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to create issue: {e}")

        return results

    def format_for_terminal(self, actions: dict[str, Any]) -> str:
        """Format actions for terminal display."""
        output = []

        if actions["branches"]:
            output.append("📌 Branches to create:")
            for branch in actions["branches"]:
                output.append(f"  - {branch['name']}")

        if actions["commands"]:
            output.append("\n💻 Commands to run:")
            for cmd in actions["commands"]:
                output.append(f"  $ {cmd}")

        if actions["issues"]:
            output.append("\n📝 Issues to create:")
            for issue in actions["issues"]:
                output.append(f"  - {issue['title']}")

        if actions["progress"]:
            output.append(f"\n📊 Progress: {actions['progress'][-1]}%")

        if actions["status_changes"]:
            output.append(f"\n🔄 Status: {actions['status_changes'][-1]}")

        return "\n".join(output)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Parse and execute Claude Code responses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Parse Claude response from stdin
  echo "Create branch feat/new-feature" | claude-code-helper.py

  # Parse from file
  claude-code-helper.py response.txt

  # Execute parsed commands
  claude-code-helper.py --execute response.txt

  # Dry run to see what would happen
  claude-code-helper.py --dry-run --execute response.txt
        """,
    )

    parser.add_argument("input", nargs="?", help="Input file or stdin if not provided")
    parser.add_argument(
        "--execute", "-e", action="store_true", help="Execute the parsed actions"
    )
    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Show what would be executed without doing it",
    )
    parser.add_argument(
        "--json", "-j", action="store_true", help="Output parsed actions as JSON"
    )
    parser.add_argument(
        "--filter",
        "-f",
        choices=["branches", "commands", "issues", "all"],
        default="all",
        help="Filter which actions to show/execute",
    )

    args = parser.parse_args()

    # Read input
    if args.input and Path(args.input).exists():
        with open(args.input) as f:
            response = f.read()
    elif args.input:
        response = args.input
    else:
        response = sys.stdin.read()

    # Parse response
    helper = ClaudeCodeHelper()
    actions = helper.parse_response(response)

    # Filter actions if requested
    if args.filter != "all":
        filtered = {k: [] for k in actions.keys()}
        filtered[args.filter] = actions[args.filter]
        filtered["raw_actions"] = [
            a for a in actions["raw_actions"] if args.filter in a.lower()
        ]
        actions = filtered

    # Output or execute
    if args.execute:
        results = helper.execute_actions(actions, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for result in results:
                status = "✓" if result["status"] == "success" else "✗"
                print(f"{status} {result['command']}")
                if result.get("output"):
                    print(f"  Output: {result['output']}")
                if result.get("error"):
                    print(f"  Error: {result['error']}")
    else:
        if args.json:
            print(json.dumps(actions, indent=2))
        else:
            formatted = helper.format_for_terminal(actions)
            if formatted:
                print(formatted)
            else:
                print("No actionable items found in response")


if __name__ == "__main__":
    main()
