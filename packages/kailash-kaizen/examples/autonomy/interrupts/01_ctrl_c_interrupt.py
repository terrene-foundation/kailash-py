"""
Example: Handle Ctrl+C gracefully during autonomous agent execution.

This example demonstrates:
1. Signal handler registration for SIGINT (Ctrl+C)
2. Graceful shutdown with checkpoint saving
3. Resume capability after interrupt
4. Custom interrupt metrics hook
5. Budget tracking visualization
6. Production error handling patterns

Requirements:
- Ollama with llama3.2 model installed

Usage:
    python 01_ctrl_c_interrupt.py

    Press Ctrl+C during execution to trigger graceful shutdown.
    Run again to resume from checkpoint.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import (
    HookContext,
    HookEvent,
    HookPriority,
    HookResult,
)
from kaizen.core.autonomy.interrupts.manager import (
    InterruptManager,
    InterruptMode,
    InterruptReason,
    InterruptSource,
)
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.core.autonomy.state.storage import FilesystemStorage
from kaizen.signatures import InputField, OutputField, Signature

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TaskSignature(Signature):
    """Task signature for autonomous agent."""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result of task")


class InterruptMetricsHook:
    """Custom hook for tracking interrupt events."""

    def __init__(self, log_path: Path):
        """Initialize interrupt metrics hook.

        Args:
            log_path: Path to store interrupt metrics JSONL log
        """
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.interrupt_count = 0
        self.graceful_count = 0
        self.immediate_count = 0

    async def pre_interrupt(self, context: HookContext) -> HookResult:
        """Track interrupt initiation."""
        try:
            reason = context.data.get("reason")
            if reason:
                self.interrupt_count += 1
                if reason.mode == InterruptMode.GRACEFUL:
                    self.graceful_count += 1
                elif reason.mode == InterruptMode.IMMEDIATE:
                    self.immediate_count += 1

                # Log interrupt event
                import json

                with open(self.log_path, "a") as f:
                    json.dump(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "event": "interrupt_initiated",
                            "source": reason.source.value,
                            "mode": reason.mode.value,
                            "message": reason.message,
                            "agent_id": context.agent_id,
                        },
                        f,
                    )
                    f.write("\n")

            return HookResult(success=True, data={"tracked": True})
        except Exception as e:
            logger.error(f"Error in pre_interrupt hook: {e}")
            return HookResult(success=False, error=str(e))

    async def post_interrupt(self, context: HookContext) -> HookResult:
        """Track interrupt completion."""
        try:
            checkpoint_id = context.data.get("checkpoint_id")

            # Log completion event
            import json

            with open(self.log_path, "a") as f:
                json.dump(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "event": "interrupt_completed",
                        "checkpoint_id": checkpoint_id,
                        "agent_id": context.agent_id,
                        "total_interrupts": self.interrupt_count,
                        "graceful_interrupts": self.graceful_count,
                        "immediate_interrupts": self.immediate_count,
                    },
                    f,
                )
                f.write("\n")

            return HookResult(
                success=True,
                data={
                    "checkpoint_saved": checkpoint_id is not None,
                    "metrics": {
                        "total": self.interrupt_count,
                        "graceful": self.graceful_count,
                        "immediate": self.immediate_count,
                    },
                },
            )
        except Exception as e:
            logger.error(f"Error in post_interrupt hook: {e}")
            return HookResult(success=False, error=str(e))


def setup_signal_handlers(interrupt_manager: InterruptManager) -> None:
    """Setup signal handlers for graceful shutdown.

    Args:
        interrupt_manager: Interrupt manager instance to signal
    """

    def sigint_handler(signum: int, frame: Any) -> None:
        """Handle SIGINT (Ctrl+C).

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        if interrupt_manager.is_interrupted():
            # Second Ctrl+C - immediate shutdown
            print("\n\n⚠️  Second Ctrl+C! Immediate shutdown...\n")
            interrupt_manager.request_interrupt(
                InterruptReason(
                    source=InterruptSource.USER,
                    mode=InterruptMode.IMMEDIATE,
                    message="User requested immediate shutdown (double Ctrl+C)",
                )
            )
        else:
            # First Ctrl+C - graceful shutdown
            print("\n\n⚠️  Ctrl+C detected! Initiating graceful shutdown...")
            print("   Finishing current cycle and saving checkpoint...")
            print("   Press Ctrl+C again for immediate shutdown.\n")
            interrupt_manager.request_interrupt(
                InterruptReason(
                    source=InterruptSource.USER,
                    mode=InterruptMode.GRACEFUL,
                    message="User requested graceful shutdown (Ctrl+C)",
                )
            )

    signal.signal(signal.SIGINT, sigint_handler)


def print_banner(checkpoint_dir: Path, has_checkpoint: bool) -> None:
    """Print startup banner with system information.

    Args:
        checkpoint_dir: Checkpoint directory path
        has_checkpoint: Whether existing checkpoint was found
    """
    print("\n" + "=" * 60)
    print("🤖 CTRL+C INTERRUPT HANDLING EXAMPLE")
    print("=" * 60)
    print(f"📂 Checkpoint Dir: {checkpoint_dir}")
    print("🔧 LLM: ollama/llama3.1:8b-instruct-q8_0 (FREE)")
    print("⚡ Features:")
    print("  ✅ Graceful shutdown on Ctrl+C")
    print("  ✅ Checkpoint preservation")
    print("  ✅ Resume from latest checkpoint")
    print("  ✅ Interrupt metrics tracking")
    print("  ✅ Budget visualization ($0.00 with Ollama)")
    if has_checkpoint:
        print("\n📂 EXISTING CHECKPOINT FOUND - Resuming previous session")
    else:
        print("\n🚀 NEW SESSION - Starting fresh execution")
    print("=" * 60)
    print("\nℹ️  Press Ctrl+C at any time to trigger graceful shutdown.")
    print("ℹ️  Press Ctrl+C twice for immediate shutdown.\n")


def print_statistics(
    result: Dict[str, Any], metrics_hook: InterruptMetricsHook, budget_spent: float
) -> None:
    """Print execution statistics.

    Args:
        result: Execution result dictionary
        metrics_hook: Interrupt metrics hook with counts
        budget_spent: Total budget spent in USD
    """
    print("\n" + "=" * 60)
    print("📊 EXECUTION STATISTICS")
    print("=" * 60)
    print(f"Status: {result['status']}")
    print(f"Cycles: {result.get('cycle_count', 'N/A')}")
    print(f"Budget Spent: ${budget_spent:.4f}")
    print("\nInterrupt Metrics:")
    print(f"  Total Interrupts: {metrics_hook.interrupt_count}")
    print(f"  Graceful: {metrics_hook.graceful_count}")
    print(f"  Immediate: {metrics_hook.immediate_count}")
    print("=" * 60 + "\n")


async def main() -> None:
    """Main execution function."""
    try:
        # Setup checkpoint directory
        checkpoint_dir = Path(".kaizen/checkpoints/ctrl_c_example")
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Setup interrupt metrics log
        metrics_log_path = checkpoint_dir / "interrupt_metrics.jsonl"

        # Create interrupt manager
        interrupt_manager = InterruptManager()

        # Setup signal handlers
        setup_signal_handlers(interrupt_manager)

        # Setup interrupt metrics hook
        metrics_hook = InterruptMetricsHook(log_path=metrics_log_path)

        hook_manager = HookManager()
        hook_manager.register(
            HookEvent.PRE_INTERRUPT, metrics_hook.pre_interrupt, HookPriority.HIGHEST
        )
        hook_manager.register(
            HookEvent.POST_INTERRUPT,
            metrics_hook.post_interrupt,
            HookPriority.HIGHEST,
        )

        # Check for existing checkpoint
        checkpoints = list(checkpoint_dir.glob("*.jsonl"))
        has_checkpoint = len(checkpoints) > 0

        # Print banner
        print_banner(checkpoint_dir, has_checkpoint)

        # Create autonomous agent with checkpoint support
        config = AutonomousConfig(
            llm_provider="ollama",
            model="llama3.1:8b-instruct-q8_0",
            temperature=0.7,
            max_cycles=10,
            checkpoint_frequency=1,  # Checkpoint every cycle
            resume_from_checkpoint=True,
            checkpoint_on_interrupt=True,  # Enable checkpoint on interrupt
        )

        storage = FilesystemStorage(base_dir=str(checkpoint_dir), compress=True)
        state_manager = StateManager(
            storage=storage, checkpoint_frequency=1, retention_count=20
        )

        agent = BaseAutonomousAgent(
            config=config,
            signature=TaskSignature(),
            state_manager=state_manager,
            hook_manager=hook_manager,
        )

        # Inject interrupt manager
        agent._interrupt_manager = interrupt_manager

        # Run autonomous loop
        task = "Count from 1 to 50, showing your progress every 5 numbers"
        budget_spent = 0.0

        logger.info("Starting autonomous execution...")

        result = await agent._autonomous_loop(task)

        # Handle different outcomes
        if result["status"] == "interrupted":
            print("\n✅ Gracefully interrupted and checkpoint saved!")
            print("   Run again to resume from where you left off.\n")

            # Show interrupt details
            reason = interrupt_manager.get_interrupt_reason()
            if reason:
                print(f"   Source: {reason.source.value}")
                print(f"   Mode: {reason.mode.value}")
                print(f"   Message: {reason.message}")
                print(f"   Timestamp: {reason.timestamp}\n")

            # Show checkpoint info
            checkpoints = list(checkpoint_dir.glob("checkpoint_*.jsonl*"))
            if checkpoints:
                latest_checkpoint = max(checkpoints, key=lambda p: p.stat().st_mtime)
                print(f"   Checkpoint: {latest_checkpoint.name}")
                print(f"   Cycles completed: {result.get('cycle_count', 'N/A')}\n")

        elif result["status"] == "completed":
            print("\n✅ Task completed successfully!")
            print(f"   Cycles: {result.get('cycle_count', 'N/A')}")
            print(f"   Result: {result.get('result', 'N/A')}\n")

            # Clean up checkpoint
            for checkpoint in checkpoint_dir.glob("checkpoint_*.jsonl*"):
                checkpoint.unlink()
            logger.info("Checkpoint cleaned up after completion.")

        else:
            print(f"\n⚠️  Unknown status: {result['status']}\n")

        # Print statistics
        print_statistics(result, metrics_hook, budget_spent)

        # Show metrics log location
        if metrics_log_path.exists():
            print(f"📊 Interrupt metrics log: {metrics_log_path}")
            print(f"   View detailed metrics: cat {metrics_log_path}\n")

    except KeyboardInterrupt:
        print("\n⚠️  Immediate shutdown! Checkpoint may be incomplete.\n")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Execution error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
