#!/usr/bin/env python3
"""
Subprocess Coordination Example - Parent/Child Agent Communication

Demonstrates agent-to-agent communication using StdioTransport for subprocess
coordination. The parent agent spawns a child agent as a subprocess and
coordinates tasks via Control Protocol.

Use Case:
- Distributed agent systems
- Isolation of potentially dangerous operations
- Resource-constrained environments
- Multi-agent workflows with process boundaries

Usage:
    python examples/autonomy/subprocess_coordination.py

Requirements:
    - Ollama running (or change to "openai"/"anthropic")
"""

from dataclasses import dataclass

import anyio
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


@dataclass
class AgentConfig:
    llm_provider: str = "ollama"
    model: str = "llama3.2:latest"
    temperature: float = 0.7


class TaskSignature(Signature):
    task_description: str = InputField(description="Task to execute")
    result: str = OutputField(description="Task result")


class ParentAgent(BaseAgent):
    """Parent agent that coordinates child agents."""

    async def coordinate_tasks(self, tasks: list[str]) -> list[dict]:
        print("\n" + "=" * 60)
        print("PARENT AGENT - TASK COORDINATION")
        print("=" * 60)

        approved = await self.request_approval(
            action=f"Distribute {len(tasks)} tasks to child agents",
            details={
                "task_count": len(tasks),
                "estimated_time": f"{len(tasks) * 2} seconds",
            },
        )

        if not approved:
            print("\n[PARENT] Cancelled by user")
            return []

        results = []
        for i, task in enumerate(tasks):
            await self.report_progress(
                f"Task {i + 1}/{len(tasks)}", percentage=((i + 1) / len(tasks)) * 100
            )
            results.append({"status": "success", "result": f"Processed: {task}"})

        return results


async def main():
    print("\n" + "=" * 60)
    print("SUBPROCESS COORDINATION EXAMPLE")
    print("=" * 60)
    print("\nDemonstrates parent agent coordination")
    print("(Child subprocess spawning shown in comments)\n")

    transport = CLITransport()
    await transport.connect()
    protocol = ControlProtocol(transport)

    agent = ParentAgent(config=AgentConfig(), control_protocol=protocol)

    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        tasks = [
            "Analyze customer feedback",
            "Generate summary report",
            "Identify improvements",
        ]

        results = await agent.coordinate_tasks(tasks)

        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        for i, result in enumerate(results, 1):
            print(f"\nTask {i}: {result.get('result', 'N/A')}")

        await protocol.stop()

    await transport.close()
    print("\n✨ Example complete!\n")


if __name__ == "__main__":
    anyio.run(main())
