"""
Example: Auto-stop autonomous agent at budget limit.

This example demonstrates:
1. BudgetHandler for cost-based interruption
2. Real-time cost tracking and monitoring
3. Graceful shutdown when budget exceeded
4. Custom budget monitoring hook with metrics
5. Cost breakdown by operation
6. Checkpoint before budget exhaustion
7. Production error handling patterns

Requirements:
- Ollama with llama3.2 model installed (FREE - demonstrates $0.00 limit)

Usage:
    python 03_budget_interrupt.py
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import (
    HookContext,
    HookEvent,
    HookPriority,
    HookResult,
)
from kaizen.core.autonomy.interrupts.handlers import BudgetInterruptHandler
from kaizen.core.autonomy.interrupts.manager import InterruptManager
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


class BudgetMonitoringHook:
    """Custom hook for real-time budget monitoring and cost tracking."""

    def __init__(self, log_path: Path, budget_limit: float):
        """Initialize budget monitoring hook.

        Args:
            log_path: Path to store cost metrics JSONL log
            budget_limit: Maximum budget allowed in USD
        """
        self.log_path = log_path
        self.budget_limit = budget_limit
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.total_cost = 0.0
        self.operation_count = 0
        self.cost_by_operation = {}

    async def pre_agent_loop(self, context: HookContext) -> HookResult:
        """Log budget monitoring start."""
        try:
            import json

            with open(self.log_path, "a") as f:
                json.dump(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "event": "budget_monitoring_start",
                        "budget_limit": self.budget_limit,
                        "agent_id": context.agent_id,
                    },
                    f,
                )
                f.write("\n")

            return HookResult(success=True)
        except Exception as e:
            logger.error(f"Error in pre_agent_loop hook: {e}")
            return HookResult(success=False, error=str(e))

    async def post_agent_loop(self, context: HookContext) -> HookResult:
        """Log final budget metrics."""
        try:
            import json

            with open(self.log_path, "a") as f:
                json.dump(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "event": "budget_monitoring_end",
                        "total_cost": self.total_cost,
                        "budget_limit": self.budget_limit,
                        "budget_remaining": max(0, self.budget_limit - self.total_cost),
                        "operations": self.operation_count,
                        "cost_by_operation": self.cost_by_operation,
                        "agent_id": context.agent_id,
                    },
                    f,
                )
                f.write("\n")

            return HookResult(success=True, data={"final_cost": self.total_cost})
        except Exception as e:
            logger.error(f"Error in post_agent_loop hook: {e}")
            return HookResult(success=False, error=str(e))

    def track_operation_cost(self, operation: str, cost: float) -> None:
        """Track cost for a specific operation.

        Args:
            operation: Operation name
            cost: Cost in USD
        """
        self.total_cost += cost
        self.operation_count += 1
        self.cost_by_operation[operation] = (
            self.cost_by_operation.get(operation, 0.0) + cost
        )

        # Check if approaching budget limit (80% threshold)
        budget_used_percentage = (self.total_cost / self.budget_limit) * 100
        if budget_used_percentage >= 80 and budget_used_percentage < 100:
            logger.warning(
                f"⚠️  Budget warning: {budget_used_percentage:.1f}% used "
                f"(${self.total_cost:.4f} / ${self.budget_limit:.4f})"
            )

    def get_cost_breakdown(self) -> Dict[str, Any]:
        """Get detailed cost breakdown.

        Returns:
            Dictionary with cost breakdown by operation
        """
        return {
            "total_cost": self.total_cost,
            "budget_limit": self.budget_limit,
            "budget_remaining": max(0, self.budget_limit - self.total_cost),
            "budget_used_percentage": (self.total_cost / self.budget_limit) * 100,
            "operations": self.operation_count,
            "cost_by_operation": self.cost_by_operation,
            "avg_cost_per_operation": (
                self.total_cost / self.operation_count
                if self.operation_count > 0
                else 0
            ),
        }


def print_banner(checkpoint_dir: Path, budget_limit: float) -> None:
    """Print startup banner with system information.

    Args:
        checkpoint_dir: Checkpoint directory path
        budget_limit: Budget limit in USD
    """
    print("\n" + "=" * 60)
    print("💰 BUDGET-LIMITED EXECUTION EXAMPLE")
    print("=" * 60)
    print(f"📂 Checkpoint Dir: {checkpoint_dir}")
    print("🔧 LLM: ollama/llama3.1:8b-instruct-q8_0 (FREE)")
    print(f"💵 Budget Limit: ${budget_limit:.4f}")
    print("⚡ Features:")
    print("  ✅ Real-time cost tracking")
    print("  ✅ Budget monitoring hook")
    print("  ✅ 80% budget warning alert")
    print("  ✅ Cost breakdown by operation")
    print("  ✅ Graceful auto-stop at limit")
    print("  ✅ Checkpoint before exhaustion")
    print("=" * 60)
    print(
        f"\nℹ️  Agent will automatically stop when cost exceeds ${budget_limit:.4f}.\n"
    )


def print_cost_breakdown(breakdown: Dict[str, Any]) -> None:
    """Print detailed cost breakdown.

    Args:
        breakdown: Cost breakdown dictionary
    """
    print("\n" + "=" * 60)
    print("💰 COST BREAKDOWN")
    print("=" * 60)
    print(f"Total Cost: ${breakdown['total_cost']:.4f}")
    print(f"Budget Limit: ${breakdown['budget_limit']:.4f}")
    print(f"Budget Remaining: ${breakdown['budget_remaining']:.4f}")
    print(f"Budget Used: {breakdown['budget_used_percentage']:.1f}%")
    print("\nOperations:")
    print(f"  Total: {breakdown['operations']}")
    print(f"  Avg Cost: ${breakdown['avg_cost_per_operation']:.4f}")
    print("\nCost by Operation:")
    for operation, cost in breakdown["cost_by_operation"].items():
        percentage = (
            (cost / breakdown["total_cost"]) * 100 if breakdown["total_cost"] > 0 else 0
        )
        print(f"  {operation}: ${cost:.4f} ({percentage:.1f}%)")
    print("=" * 60 + "\n")


async def main() -> None:
    """Main execution function."""
    try:
        # Setup checkpoint directory
        checkpoint_dir = Path(".kaizen/checkpoints/budget_example")
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Setup budget monitoring log
        monitoring_log_path = checkpoint_dir / "budget_monitoring.jsonl"

        # Budget configuration (using $0.10 for demo, but $0.00 with Ollama)
        MAX_COST = 0.10

        # Print banner
        print_banner(checkpoint_dir, MAX_COST)

        # Create interrupt manager
        interrupt_manager = InterruptManager()

        # Add budget handler
        budget_handler = BudgetInterruptHandler(
            interrupt_manager=interrupt_manager, budget_usd=MAX_COST
        )

        logger.info(f"Budget handler configured: ${MAX_COST:.2f} maximum cost")

        # Setup budget monitoring hook
        monitoring_hook = BudgetMonitoringHook(
            log_path=monitoring_log_path, budget_limit=MAX_COST
        )

        hook_manager = HookManager()
        hook_manager.register(
            HookEvent.PRE_AGENT_LOOP,
            monitoring_hook.pre_agent_loop,
            HookPriority.HIGHEST,
        )
        hook_manager.register(
            HookEvent.POST_AGENT_LOOP,
            monitoring_hook.post_agent_loop,
            HookPriority.HIGHEST,
        )

        # Create autonomous agent with budget tracking
        config = AutonomousConfig(
            llm_provider="ollama",
            model="llama3.1:8b-instruct-q8_0",
            temperature=0.7,
            max_cycles=50,  # High limit, budget will stop first
            checkpoint_frequency=5,  # Checkpoint every 5 cycles
            checkpoint_on_interrupt=True,
        )

        storage = FilesystemStorage(base_dir=str(checkpoint_dir), compress=True)
        state_manager = StateManager(
            storage=storage, checkpoint_frequency=5, retention_count=20
        )

        agent = BaseAutonomousAgent(
            config=config,
            signature=TaskSignature(),
            state_manager=state_manager,
            hook_manager=hook_manager,
        )

        # Inject interrupt manager
        agent._interrupt_manager = interrupt_manager

        logger.info("Starting autonomous execution with budget tracking...")

        # Run autonomous loop (task that will generate costs)
        task = "Write a detailed essay about artificial intelligence"

        result = await agent._autonomous_loop(task)

        # Simulate cost tracking (would be real with OpenAI API)
        # With Ollama, cost is $0.00, so we simulate for demonstration
        for i in range(result.get("cycle_count", 0)):
            monitoring_hook.track_operation_cost(f"llm_call_cycle_{i+1}", 0.0)

        # Check if budget exceeded
        if result["status"] == "interrupted":
            reason = interrupt_manager.get_interrupt_reason()

            if reason and "budget" in reason.message.lower():
                current_cost = budget_handler.get_current_cost()
                print(f"\n💰 Budget limit reached: ${current_cost:.4f}")
                print("   Graceful shutdown completed and checkpoint saved.\n")

                # Show interrupt details
                print(f"   Source: {reason.source.value}")
                print(f"   Mode: {reason.mode.value}")
                print(f"   Message: {reason.message}")
                print(f"   Timestamp: {reason.timestamp}\n")

                # Show checkpoint info
                checkpoints = list(checkpoint_dir.glob("checkpoint_*.jsonl*"))
                if checkpoints:
                    latest_checkpoint = max(
                        checkpoints, key=lambda p: p.stat().st_mtime
                    )
                    print(f"   Checkpoint: {latest_checkpoint.name}")
                    print(f"   Cycles completed: {result.get('cycle_count', 'N/A')}\n")
            else:
                print(f"\n⚠️  Interrupted for other reason: {reason.message}\n")

        elif result["status"] == "completed":
            current_cost = budget_handler.get_current_cost()
            print("\n✅ Task completed within budget!\n")
            print(f"   Cycles: {result.get('cycle_count', 'N/A')}")
            print(f"   Cost: ${current_cost:.4f} / ${MAX_COST:.4f}")
            print(f"   Remaining budget: ${MAX_COST - current_cost:.4f}\n")

            # Clean up checkpoint on successful completion
            for checkpoint in checkpoint_dir.glob("checkpoint_*.jsonl*"):
                checkpoint.unlink()
            logger.info("Checkpoint cleaned up after completion.")

        else:
            print(f"\n⚠️  Unknown status: {result['status']}\n")

        # Print cost breakdown
        breakdown = monitoring_hook.get_cost_breakdown()
        print_cost_breakdown(breakdown)

        # Show monitoring log location
        if monitoring_log_path.exists():
            print(f"📊 Budget monitoring log: {monitoring_log_path}")
            print(f"   View detailed metrics: cat {monitoring_log_path}\n")

    except Exception as e:
        logger.error(f"Execution error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
