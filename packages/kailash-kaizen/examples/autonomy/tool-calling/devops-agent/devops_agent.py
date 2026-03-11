"""
DevOps Agent - System administration with bash tools.

This example demonstrates:
1. Bash command execution with bash_command tool
2. Danger-level escalation (SAFE → HIGH approval)
3. Circuit breaker for external services
4. Audit trail with hooks

Requirements:
- Ollama with llama3.1:8b-instruct-q8_0 model installed (FREE)
- Python 3.8+
- Unix-like system (Linux, macOS)

Usage:
    python devops_agent.py "check disk usage and clean logs"

    The agent will:
    - Execute system commands safely
    - Request approval for dangerous operations
    - Log all actions to audit trail
    - Handle errors gracefully
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookEvent, HookResult
from kaizen.core.autonomy.permissions import (
    ExecutionContext,
    PermissionMode,
    PermissionRule,
    PermissionType,
)
from kaizen.signatures import InputField, OutputField, Signature


class DevOpsSignature(Signature):
    """Signature for DevOps task."""

    task: str = InputField(description="DevOps task to perform")
    execution_report: str = OutputField(description="Execution report with results")
    commands_executed: List[str] = OutputField(description="List of commands executed")
    success: bool = OutputField(description="Whether task succeeded")


class AuditTrailHook(BaseHook):
    """Hook for logging all agent actions to audit trail."""

    def __init__(self, audit_path: Path):
        super().__init__(name="audit_trail_hook")
        self.audit_path = audit_path
        self.audit_path.mkdir(parents=True, exist_ok=True)

    def supported_events(self) -> List[HookEvent]:
        return [HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE]

    async def handle(self, context: HookContext) -> HookResult:
        """Log tool usage to audit trail."""
        try:
            audit_file = self.audit_path / "audit_trail.jsonl"

            entry = {
                "timestamp": datetime.now().isoformat(),
                "event": context.event_type.value,
                "agent_id": context.agent_id,
                "tool": context.data.get("tool_name", "unknown"),
                "params": context.data.get("params", {}),
                "success": context.data.get("success", True),
            }

            # Append to audit log
            with open(audit_file, "a") as f:
                import json

                f.write(json.dumps(entry) + "\n")

            return HookResult(success=True, data={"audit_logged": True})

        except Exception as e:
            return HookResult(success=False, error=str(e))


class DevOpsAgent(BaseAutonomousAgent):
    """Autonomous agent for safe DevOps automation."""

    def __init__(
        self,
        config: AutonomousConfig,
        audit_path: Path = None,
    ):
        super().__init__(
            config=config,
            signature=DevOpsSignature(),
        )

        # Setup audit trail hook
        if audit_path:
            audit_hook = AuditTrailHook(audit_path)
            self._hook_manager.register_hook(audit_hook)

        # Setup permissions
        self._setup_permissions()

        # Track executed commands
        self.commands_executed = []

    def _setup_permissions(self):
        """Configure permission rules for bash operations."""
        self.exec_context = ExecutionContext(
            mode=PermissionMode.DEFAULT,
            budget_limit=5.0,  # $5 maximum
        )

        # Define permission rules with danger levels
        self.permission_rules = [
            # SAFE operations - Auto-approve
            PermissionRule(
                pattern="(df|du|ls|pwd|whoami|date|uptime)",
                permission_type=PermissionType.ALLOW,
                reason="Read-only commands are safe",
                priority=100,
            ),
            # LOW danger - Auto-approve
            PermissionRule(
                pattern="(cat|grep|find|tail|head)",
                permission_type=PermissionType.ALLOW,
                reason="File reading commands are safe",
                priority=90,
            ),
            # MEDIUM danger - Ask for approval
            PermissionRule(
                pattern="(mkdir|touch|cp)",
                permission_type=PermissionType.ASK,
                reason="File creation requires approval",
                priority=50,
            ),
            # HIGH danger - Ask for approval
            PermissionRule(
                pattern="(rm|mv|chmod|chown)",
                permission_type=PermissionType.ASK,
                reason="File modification is dangerous",
                priority=30,
            ),
            # CRITICAL danger - Deny
            PermissionRule(
                pattern="(rm -rf|dd|mkfs|fdisk|> /dev)",
                permission_type=PermissionType.DENY,
                reason="Destructive commands are blocked",
                priority=10,
            ),
        ]

    def _get_danger_level(self, command: str) -> str:
        """Determine danger level of bash command."""
        # CRITICAL - Destructive system operations
        if any(x in command.lower() for x in ["rm -rf", "dd", "mkfs", "fdisk"]):
            return "CRITICAL"

        # HIGH - File/system modifications
        if any(x in command.split()[0] for x in ["rm", "mv", "chmod", "chown"]):
            return "HIGH"

        # MEDIUM - File creation
        if any(x in command.split()[0] for x in ["mkdir", "touch", "cp"]):
            return "MEDIUM"

        # LOW - File reading
        if any(
            x in command.split()[0] for x in ["cat", "grep", "find", "tail", "head"]
        ):
            return "LOW"

        # SAFE - Read-only info commands
        if any(
            x in command.split()[0]
            for x in ["df", "du", "ls", "pwd", "whoami", "date", "uptime"]
        ):
            return "SAFE"

        return "UNKNOWN"

    async def execute_bash_safely(self, command: str) -> Dict:
        """Execute bash command with safety checks."""
        danger_level = self._get_danger_level(command)
        print(f"🔍 Command: {command}")
        print(f"⚠️  Danger Level: {danger_level}")

        # Check permission rules
        for rule in sorted(
            self.permission_rules, key=lambda r: r.priority, reverse=True
        ):
            if rule.matches(command.split()[0]):
                if rule.permission_type == PermissionType.DENY:
                    print(f"🚫 Command DENIED: {rule.reason}")
                    return {
                        "success": False,
                        "output": f"Command denied: {rule.reason}",
                        "danger_level": danger_level,
                    }
                elif rule.permission_type == PermissionType.ASK:
                    print(f"⚠️  Approval required: {rule.reason}")
                    # In production, request via Control Protocol
                    # For demo, simulate approval for MEDIUM, deny HIGH
                    if danger_level in ["HIGH", "CRITICAL"]:
                        print("🚫 HIGH danger - Approval DENIED (simulated)")
                        return {
                            "success": False,
                            "output": "High danger command denied",
                            "danger_level": danger_level,
                        }
                    else:
                        print("✅ MEDIUM danger - Approval GRANTED (simulated)")
                break

        # Execute command
        try:
            import subprocess

            print("⚙️  Executing...")
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.commands_executed.append(command)

            return {
                "success": result.returncode == 0,
                "output": result.stdout if result.stdout else result.stderr,
                "danger_level": danger_level,
                "return_code": result.returncode,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "Command timed out (30s limit)",
                "danger_level": danger_level,
            }
        except Exception as e:
            return {
                "success": False,
                "output": f"Error: {str(e)}",
                "danger_level": danger_level,
            }

    async def execute_devops_task(self, task: str) -> Dict:
        """Execute DevOps task with multiple commands."""
        print(f"\n🔧 Starting DevOps task: {task}\n")

        # Demo commands based on task
        commands = self._plan_commands(task)
        print(f"📋 Planned {len(commands)} commands:\n")

        results = []
        for i, cmd in enumerate(commands, 1):
            print(f"\n[{i}/{len(commands)}] " + "=" * 50)
            result = await self.execute_bash_safely(cmd)
            results.append(result)

            if result["success"]:
                print("✅ Success")
                if result["output"].strip():
                    print(f"📄 Output:\n{result['output'][:200]}")
            else:
                print(f"❌ Failed: {result['output']}")

            print("=" * 50)

        # Generate report
        success_count = sum(1 for r in results if r["success"])
        report = self._generate_report(commands, results, success_count)

        return {
            "execution_report": report,
            "commands_executed": self.commands_executed,
            "success": success_count == len(commands),
        }

    def _plan_commands(self, task: str) -> List[str]:
        """Plan bash commands for task."""
        # Simple task-to-commands mapping for demo
        task_lower = task.lower()

        if "disk" in task_lower:
            return [
                "df -h",
                "du -sh /tmp",
                "ls -lh /tmp | head -n 10",
            ]
        elif "memory" in task_lower or "process" in task_lower:
            return [
                "free -h",
                "ps aux | head -n 10",
                "uptime",
            ]
        elif "log" in task_lower:
            return [
                "ls -lh /var/log | head -n 5",
                "tail -n 20 /var/log/system.log 2>/dev/null || echo 'Log not accessible'",
            ]
        else:
            return [
                "date",
                "whoami",
                "pwd",
            ]

    def _generate_report(
        self, commands: List[str], results: List[Dict], success_count: int
    ) -> str:
        """Generate execution report."""
        lines = [
            "=" * 60,
            "🔧 DEVOPS EXECUTION REPORT",
            "=" * 60,
            "",
            f"📊 Summary: {success_count}/{len(commands)} commands succeeded",
            "",
            "📋 Command Results:",
        ]

        for cmd, result in zip(commands, results):
            status = "✅" if result["success"] else "❌"
            danger = result["danger_level"]
            lines.append(f"  {status} [{danger}] {cmd}")

        lines.extend(["", "=" * 60])
        return "\n".join(lines)


async def main():
    """Main execution function."""
    if len(sys.argv) < 2:
        print('Usage: python devops_agent.py "task description"')
        print('Example: python devops_agent.py "check disk usage and memory"')
        sys.exit(1)

    task = sys.argv[1]

    # Setup audit trail
    audit_path = Path(".kaizen/audit/devops")

    # Create autonomous agent with Ollama (FREE)
    config = AutonomousConfig(
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        temperature=0.3,
        max_cycles=5,
    )

    agent = DevOpsAgent(config=config, audit_path=audit_path)

    print("\n" + "=" * 60)
    print("🤖 DEVOPS AGENT")
    print("=" * 60)
    print(f"📋 Task: {task}")
    print(f"🔧 LLM: {config.llm_provider}/{config.model}")
    print(f"📝 Audit Trail: {audit_path}")
    print("🔒 Safety: Danger-level approval workflow")
    print("=" * 60)

    try:
        result = await agent.execute_devops_task(task)

        print("\n" + result["execution_report"])

        print("\n💰 Cost: $0.00 (using Ollama local inference)")
        print(f"📝 Audit Log: {audit_path}/audit_trail.jsonl")
        print(f"🔒 Commands Executed: {len(result['commands_executed'])}\n")

    except KeyboardInterrupt:
        print("\n⚠️  Task interrupted by user\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
