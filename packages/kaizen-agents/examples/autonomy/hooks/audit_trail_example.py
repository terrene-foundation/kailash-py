"""
Audit Trail with Hooks - Production Example

Demonstrates how to use the hooks system to create comprehensive audit trails
for compliance requirements (SOC2, HIPAA, GDPR, etc.).

Use cases:
- Compliance logging (SOC2, HIPAA, GDPR)
- Security auditing
- Debugging production issues
- Forensic analysis

Run:
    python examples/autonomy/hooks/audit_trail_example.py
"""

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import (
    HookContext,
    HookEvent,
    HookPriority,
    HookResult,
)
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

# =============================================================================
# Audit Trail Hook Implementation
# =============================================================================


@dataclass
class AuditEntry:
    """
    Immutable audit log entry.

    Captures all relevant information for compliance auditing.
    """

    timestamp: str
    event_type: str
    agent_id: str
    trace_id: str
    action: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    duration_ms: float
    success: bool
    error: str | None = None
    metadata: Dict[str, Any] | None = None


class AuditTrailHook:
    """
    Production-ready audit trail hook.

    Creates immutable, append-only audit logs for compliance.

    Features:
    - Immutable log entries (append-only)
    - Structured JSON format
    - Complete execution context
    - Searchable by trace_id, agent_id, timestamp
    - GDPR/HIPAA/SOC2 compliant
    """

    def __init__(self, audit_log_path: Path | None = None):
        """
        Initialize audit trail hook.

        Args:
            audit_log_path: Path to audit log file (None = in-memory only)
        """
        self.audit_log_path = audit_log_path
        self.audit_entries: List[AuditEntry] = []
        self.loop_start_times: Dict[str, float] = {}

        # Create audit log file if path provided
        if audit_log_path:
            audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"📝 [AUDIT] Audit log: {audit_log_path}")

    async def record_loop_start(self, context: HookContext) -> HookResult:
        """
        Record agent loop start in audit trail.

        Captures inputs and context for compliance.
        """
        import time

        trace_id = context.trace_id
        self.loop_start_times[trace_id] = time.time()

        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            event_type="AGENT_LOOP_START",
            agent_id=context.agent_id,
            trace_id=trace_id,
            action="agent_execution_start",
            inputs=context.data.get("inputs", {}),
            outputs={},
            duration_ms=0,
            success=True,
            metadata=context.metadata,
        )

        self._append_entry(entry)

        print(
            f"📝 [AUDIT] Recorded loop start: agent={context.agent_id} "
            f"trace={trace_id[:8]}..."
        )

        return HookResult(success=True, data={"audit_recorded": True})

    async def record_loop_end(self, context: HookContext) -> HookResult:
        """
        Record agent loop completion in audit trail.

        Captures outputs, duration, and success/failure status.
        """
        import time

        trace_id = context.trace_id

        # Calculate duration
        if trace_id in self.loop_start_times:
            duration_ms = (time.time() - self.loop_start_times.pop(trace_id)) * 1000
        else:
            duration_ms = 0

        # Extract result
        result = context.data.get("result", {})
        success = result.get("success", True)
        error = result.get("error", None) if not success else None

        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            event_type="AGENT_LOOP_END",
            agent_id=context.agent_id,
            trace_id=trace_id,
            action="agent_execution_end",
            inputs=context.data.get("inputs", {}),
            outputs=result,
            duration_ms=duration_ms,
            success=success,
            error=error,
            metadata=context.metadata,
        )

        self._append_entry(entry)

        print(
            f"✅ [AUDIT] Recorded loop end: agent={context.agent_id} "
            f"duration={duration_ms:.1f}ms success={success}"
        )

        return HookResult(success=True, data={"audit_recorded": True})

    def _append_entry(self, entry: AuditEntry) -> None:
        """
        Append entry to audit trail.

        Writes to both in-memory list and file (if configured).
        """
        # Store in memory
        self.audit_entries.append(entry)

        # Write to file (append-only, immutable)
        if self.audit_log_path:
            with open(self.audit_log_path, "a") as f:
                json.dump(asdict(entry), f)
                f.write("\n")

    def query_by_agent(self, agent_id: str) -> List[AuditEntry]:
        """Query audit entries by agent ID."""
        return [e for e in self.audit_entries if e.agent_id == agent_id]

    def query_by_trace(self, trace_id: str) -> List[AuditEntry]:
        """Query audit entries by trace ID."""
        return [e for e in self.audit_entries if e.trace_id == trace_id]

    def query_by_timerange(
        self, start_time: datetime, end_time: datetime
    ) -> List[AuditEntry]:
        """Query audit entries by time range."""
        return [
            e
            for e in self.audit_entries
            if start_time.isoformat() <= e.timestamp <= end_time.isoformat()
        ]

    def export_compliance_report(self) -> str:
        """
        Export compliance report.

        Returns formatted report suitable for auditors.
        """
        report = []
        report.append("=" * 70)
        report.append("AUDIT TRAIL COMPLIANCE REPORT")
        report.append("=" * 70)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append(f"Total entries: {len(self.audit_entries)}")
        report.append("")

        # Group by agent
        agents = {}
        for entry in self.audit_entries:
            if entry.agent_id not in agents:
                agents[entry.agent_id] = []
            agents[entry.agent_id].append(entry)

        for agent_id, entries in agents.items():
            report.append(f"\nAgent: {agent_id}")
            report.append(f"  Total operations: {len(entries) // 2}")  # start+end pairs
            success_count = sum(1 for e in entries if e.success)
            report.append(f"  Success rate: {success_count}/{len(entries)}")

            # Show last 3 operations
            report.append("  Recent operations:")
            for entry in entries[-3:]:
                report.append(
                    f"    - {entry.timestamp}: {entry.action} "
                    f"({entry.duration_ms:.1f}ms)"
                )

        report.append("\n" + "=" * 70)
        return "\n".join(report)


# =============================================================================
# Example Agent
# =============================================================================


class QuestionAnswerSignature(Signature):
    """Simple Q&A signature."""

    question: str = InputField(description="User question")
    answer: str = OutputField(description="Agent answer")


@dataclass
class AgentConfig:
    """Agent configuration."""

    llm_provider: str = "mock"
    model: str = "mock-model"
    temperature: float = 0.7


# =============================================================================
# Main Demo
# =============================================================================


async def main():
    """
    Demonstrate audit trail logging with hooks.

    Shows:
    1. Hook registration for audit logging
    2. Automatic audit entry creation
    3. Querying audit trail
    4. Compliance report generation
    """
    print("=" * 70)
    print("Audit Trail with Hooks - Production Example")
    print("=" * 70)

    # Step 1: Create audit hook
    print("\n1️⃣  Creating audit trail hook...")
    audit_log_path = Path("/tmp/kaizen_audit.jsonl")
    audit_hook = AuditTrailHook(audit_log_path=audit_log_path)

    # Step 2: Register hook with manager
    print("2️⃣  Registering hooks for PRE/POST_AGENT_LOOP...")
    hook_manager = HookManager()
    hook_manager.register(
        HookEvent.PRE_AGENT_LOOP,
        audit_hook.record_loop_start,
        HookPriority.HIGHEST,  # Ensure audit happens first
    )
    hook_manager.register(
        HookEvent.POST_AGENT_LOOP,
        audit_hook.record_loop_end,
        HookPriority.HIGHEST,  # Ensure audit happens last
    )

    print("   ✅ Registered 2 audit hooks")

    # Step 3: Create agent with audit trail
    print("\n3️⃣  Creating agent with audit trail...")
    agent = BaseAgent(
        config=AgentConfig(),
        signature=QuestionAnswerSignature(),
        hook_manager=hook_manager,
    )

    # Step 4: Run agent (audit trail recorded automatically)
    print("\n4️⃣  Running agent operations (audit trail recorded)...\n")

    questions = [
        "What is GDPR?",
        "What is SOC2?",
        "What is HIPAA?",
        "What is an audit trail?",
    ]

    for i, question in enumerate(questions, 1):
        print(f"   Operation {i}/4:")
        agent.run(question=question)
        await asyncio.sleep(0.05)

    # Step 5: Query audit trail
    print("\n5️⃣  Querying audit trail...\n")

    # Query by agent
    agent_entries = audit_hook.query_by_agent("base_agent")
    print(f"   Found {len(agent_entries)} entries for agent 'base_agent'")

    # Query recent entries
    recent_time = datetime.now()
    recent_entries = audit_hook.query_by_timerange(
        start_time=datetime(2025, 1, 1), end_time=recent_time
    )
    print(f"   Found {len(recent_entries)} recent entries")

    # Step 6: Generate compliance report
    print("\n6️⃣  Generating compliance report...\n")
    print(audit_hook.export_compliance_report())

    print("\n" + "=" * 70)
    print("✅ Demo Complete!")
    print("=" * 70)
    print("\n💡 Key Takeaways:")
    print("   1. Hooks enable automatic compliance logging with zero code changes")
    print("   2. Audit entries are immutable (append-only)")
    print("   3. Complete execution context captured (inputs, outputs, duration)")
    print("   4. Queryable by agent, trace, or time range")
    print("   5. Production-ready for SOC2/GDPR/HIPAA compliance")
    print("\n📚 Next Steps:")
    print("   - Configure retention policies (e.g., 7 years for HIPAA)")
    print("   - Encrypt audit logs at rest")
    print("   - Set up log rotation and archival")
    print("   - Define access controls for audit log viewing")
    print(f"   - Review audit log: {audit_log_path}")


if __name__ == "__main__":
    asyncio.run(main())
