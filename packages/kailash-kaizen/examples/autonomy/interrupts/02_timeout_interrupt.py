"""
Example: Auto-stop autonomous agent after timeout.

This example demonstrates:
1. TimeoutHandler for automatic interruption
2. Configurable timeout duration
3. Graceful shutdown on timeout

Requirements:
- Ollama with llama3.2 model installed

Usage:
    python 02_timeout_interrupt.py
"""

import asyncio
from pathlib import Path

from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent
from kaizen.core.autonomy.interrupts.handlers import TimeoutInterruptHandler
from kaizen.core.autonomy.interrupts.manager import InterruptManager
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.core.autonomy.state.storage import FilesystemStorage
from kaizen.signatures import InputField, OutputField, Signature


class TaskSignature(Signature):
    """Task signature for autonomous agent."""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result of task")


async def main():
    """Main execution function."""

    # Setup checkpoint directory
    checkpoint_dir = Path(".kaizen/checkpoints/timeout_example")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Create interrupt manager
    interrupt_manager = InterruptManager()

    # Add timeout handler (10 seconds)
    TIMEOUT_SECONDS = 10
    timeout_handler = TimeoutInterruptHandler(
        interrupt_manager=interrupt_manager, timeout_seconds=TIMEOUT_SECONDS
    )

    print(f"⏱️  Timeout handler configured: {TIMEOUT_SECONDS} seconds\n")

    # Create autonomous agent
    config = AutonomousConfig(
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        temperature=0.7,
        max_cycles=100,  # High limit, timeout will stop first
        checkpoint_frequency=1,
    )

    storage = FilesystemStorage(base_dir=str(checkpoint_dir))
    state_manager = StateManager(storage=storage)

    agent = BaseAutonomousAgent(
        config=config,
        signature=TaskSignature(),
        state_manager=state_manager,
    )

    # Inject interrupt manager
    agent._interrupt_manager = interrupt_manager

    # Start timeout timer in background
    import asyncio

    asyncio.create_task(timeout_handler.start())
    print("🚀 Starting autonomous execution with timeout...\n")
    print(f"ℹ️  Agent will automatically stop after {TIMEOUT_SECONDS} seconds.\n")

    # Run autonomous loop (long-running task that will timeout)
    task = "Count from 1 to 1000, showing progress every 10 numbers"

    try:
        result = await agent._autonomous_loop(task)

        # Check if timeout occurred
        if result["status"] == "interrupted":
            reason = interrupt_manager.get_interrupt_reason()

            if reason and "timeout" in reason.message.lower():
                print(f"\n⏱️  Timeout reached after {TIMEOUT_SECONDS} seconds!")
                print("   Graceful shutdown completed and checkpoint saved.\n")

                # Show interrupt details
                print(f"   Source: {reason.source.value}")
                print(f"   Mode: {reason.mode.value}")
                print(f"   Message: {reason.message}")
                print(f"   Timestamp: {reason.timestamp}\n")

                # Show checkpoint info
                checkpoints = list(checkpoint_dir.glob("*.jsonl"))
                if checkpoints:
                    print(f"   Checkpoint: {checkpoints[0].name}")
                    print(f"   Cycles completed: {result.get('cycle_count', 'N/A')}\n")
            else:
                print(f"\n⚠️  Interrupted for other reason: {reason.message}\n")

        elif result["status"] == "completed":
            print("\n✅ Task completed before timeout! (Very efficient agent)\n")
            print(f"   Cycles: {result.get('cycle_count', 'N/A')}")
            print(f"   Result: {result.get('result', 'N/A')}\n")

        else:
            print(f"\n⚠️  Unknown status: {result['status']}\n")

    finally:
        # Stop timeout handler
        await timeout_handler.stop()
        print("   Timeout handler stopped.\n")


if __name__ == "__main__":
    asyncio.run(main())
