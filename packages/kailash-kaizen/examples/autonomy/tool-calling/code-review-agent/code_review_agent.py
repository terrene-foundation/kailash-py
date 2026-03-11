"""
Code Review Agent - Automated code review with file tools.

This example demonstrates:
1. Reading multiple files with read_file tool
2. Permission policies (ALLOW reads, ASK for writes)
3. Error handling with graceful fallback
4. Progress reporting via Control Protocol

Requirements:
- Ollama with llama3.1:8b-instruct-q8_0 model installed (FREE)
- Python 3.8+

Usage:
    python code_review_agent.py /path/to/codebase

    The agent will:
    - Read all Python files
    - Analyze code quality
    - Report findings with line numbers
    - Suggest improvements
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, List

from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import MemoryTransport
from kaizen.core.autonomy.permissions import (
    ExecutionContext,
    PermissionMode,
    PermissionRule,
    PermissionType,
)
from kaizen.signatures import InputField, OutputField, Signature


class CodeReviewSignature(Signature):
    """Signature for code review task."""

    codebase_path: str = InputField(description="Path to codebase to review")
    review_report: str = OutputField(description="Code review report with findings")
    issues_found: int = OutputField(description="Number of issues found")
    suggestions: List[str] = OutputField(description="List of improvement suggestions")


class CodeReviewAgent(BaseAutonomousAgent):
    """Autonomous agent for automated code review."""

    def __init__(
        self,
        config: AutonomousConfig,
        control_protocol: ControlProtocol = None,
    ):
        super().__init__(
            config=config,
            signature=CodeReviewSignature(),
            control_protocol=control_protocol,
        )

        # Setup permission policies
        self._setup_permissions()

    def _setup_permissions(self):
        """Configure permission rules for code review operations."""
        # Create execution context with safe defaults
        self.exec_context = ExecutionContext(
            mode=PermissionMode.DEFAULT,
            budget_limit=10.0,  # $10 maximum for review
        )

        # Define permission rules (priority-ordered)
        self.permission_rules = [
            # High priority: Allow read operations (safe)
            PermissionRule(
                pattern="(read_file|list_directory|file_exists)",
                permission_type=PermissionType.ALLOW,
                reason="Read operations are safe for code review",
                priority=100,
            ),
            # Medium priority: Ask before write operations
            PermissionRule(
                pattern="(write_file|delete_file)",
                permission_type=PermissionType.ASK,
                reason="Write operations require user approval",
                priority=50,
            ),
            # Low priority: Deny dangerous bash commands
            PermissionRule(
                pattern="bash_command",
                permission_type=PermissionType.DENY,
                reason="Bash commands not allowed during code review",
                priority=10,
            ),
        ]

    async def check_permission(self, tool_name: str) -> bool:
        """Check if tool is allowed by permission rules."""
        # Check execution context
        if not self.exec_context.can_use_tool(tool_name):
            print(f"⚠️  Tool {tool_name} denied by execution context")
            return False

        # Find matching rule (highest priority first)
        matching_rule = None
        for rule in sorted(
            self.permission_rules, key=lambda r: r.priority, reverse=True
        ):
            if rule.matches(tool_name):
                matching_rule = rule
                break

        if not matching_rule:
            # No rule found, default to DENY for safety
            print(f"⚠️  No permission rule for {tool_name}, defaulting to DENY")
            return False

        # Apply permission decision
        if matching_rule.permission_type == PermissionType.ALLOW:
            return True
        elif matching_rule.permission_type == PermissionType.DENY:
            print(f"⚠️  Tool {tool_name} denied: {matching_rule.reason}")
            return False
        elif matching_rule.permission_type == PermissionType.ASK:
            # Request user approval via Control Protocol
            if self.control_protocol:
                try:
                    approved = await self.control_protocol.request_approval(
                        action=tool_name,
                        details={
                            "tool": tool_name,
                            "reason": matching_rule.reason,
                        },
                    )
                    return approved
                except Exception as e:
                    print(f"⚠️  Failed to request approval: {e}")
                    return False
            else:
                # No control protocol, default to DENY
                print(
                    f"⚠️  Tool {tool_name} requires approval but no Control Protocol available"
                )
                return False

        return False

    async def review_codebase(self, codebase_path: str) -> Dict:
        """Execute code review on codebase."""
        print(f"\n🔍 Starting code review of: {codebase_path}\n")

        # Find all Python files
        path = Path(codebase_path)
        if not path.exists():
            return {
                "review_report": f"Error: Path {codebase_path} does not exist",
                "issues_found": 0,
                "suggestions": [],
            }

        python_files = list(path.rglob("*.py"))
        print(f"📂 Found {len(python_files)} Python files\n")

        if not python_files:
            return {
                "review_report": "No Python files found",
                "issues_found": 0,
                "suggestions": [],
            }

        # Report progress
        if self.control_protocol:
            await self.control_protocol.report_progress(
                message=f"Analyzing {len(python_files)} Python files",
                percentage=0,
            )

        # Read and analyze files
        findings = []
        for i, file_path in enumerate(python_files[:10]):  # Limit to 10 files for demo
            try:
                # Check permission before reading
                if not await self.check_permission("read_file"):
                    findings.append(f"⚠️  Permission denied to read {file_path}")
                    continue

                # Read file
                content = file_path.read_text(encoding="utf-8", errors="ignore")

                # Simple analysis
                issues = []
                lines = content.split("\n")

                # Check for common issues
                for line_num, line in enumerate(lines, 1):
                    # Long lines
                    if len(line) > 100:
                        issues.append(
                            f"Line {line_num}: Line too long ({len(line)} chars)"
                        )

                    # Missing docstrings for functions
                    if line.strip().startswith("def ") and (
                        line_num >= len(lines) or '"""' not in lines[line_num]
                    ):
                        issues.append(f"Line {line_num}: Function missing docstring")

                    # Bare except clauses
                    if "except:" in line:
                        issues.append(
                            f"Line {line_num}: Bare except clause (use specific exceptions)"
                        )

                if issues:
                    findings.append(f"\n📄 {file_path.relative_to(path)}:")
                    findings.extend(
                        [f"  - {issue}" for issue in issues[:5]]
                    )  # Limit to 5 per file

                # Report progress
                progress = int((i + 1) / len(python_files[:10]) * 100)
                if self.control_protocol:
                    await self.control_protocol.report_progress(
                        message=f"Analyzed {i + 1}/{len(python_files[:10])} files",
                        percentage=progress,
                    )

            except Exception as e:
                findings.append(f"⚠️  Error reading {file_path}: {e}")

        # Generate report
        review_report = "\n".join(findings) if findings else "✅ No issues found!"
        issues_count = len([f for f in findings if not f.startswith("⚠️")])

        # Generate suggestions
        suggestions = [
            "Follow PEP 8 style guide (line length < 100 chars)",
            "Add docstrings to all functions and classes",
            "Use specific exception types instead of bare except",
            "Add type hints for better code clarity",
            "Run pylint or flake8 for comprehensive analysis",
        ]

        result = {
            "review_report": review_report,
            "issues_found": issues_count,
            "suggestions": suggestions,
        }

        print("\n" + "=" * 60)
        print("📊 CODE REVIEW REPORT")
        print("=" * 60)
        print(review_report)
        print(f"\n📈 Issues Found: {issues_count}")
        print("\n💡 Suggestions:")
        for suggestion in suggestions:
            print(f"  - {suggestion}")
        print("=" * 60 + "\n")

        return result


async def main():
    """Main execution function."""
    if len(sys.argv) < 2:
        print("Usage: python code_review_agent.py /path/to/codebase")
        sys.exit(1)

    codebase_path = sys.argv[1]

    # Create control protocol for bidirectional communication
    transport = MemoryTransport()
    await transport.connect()
    control_protocol = ControlProtocol(transport)

    # Create autonomous agent with Ollama (FREE)
    config = AutonomousConfig(
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        temperature=0.3,  # Low temperature for consistent analysis
        max_cycles=5,
    )

    agent = CodeReviewAgent(config=config, control_protocol=control_protocol)

    print("\n" + "=" * 60)
    print("🤖 CODE REVIEW AGENT")
    print("=" * 60)
    print(f"📂 Codebase: {codebase_path}")
    print(f"🔧 LLM: {config.llm_provider}/{config.model}")
    print("🔒 Permissions: Read (ALLOW), Write (ASK), Bash (DENY)")
    print("=" * 60)

    try:
        # Execute code review
        result = await agent.review_codebase(codebase_path)

        # Show cost information
        print("\n💰 Cost: $0.00 (using Ollama local inference)")
        print(f"📊 Budget Used: ${agent.exec_context.budget_used:.3f}")
        print(
            f"📊 Budget Remaining: ${agent.exec_context.budget_limit - agent.exec_context.budget_used:.3f}\n"
        )

    except KeyboardInterrupt:
        print("\n⚠️  Review interrupted by user\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during code review: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
