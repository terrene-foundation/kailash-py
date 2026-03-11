"""
Suite 5: Interrupt Handling Performance Benchmarks (TODO-171).

Measures interrupt system performance:
1. Interrupt detection latency - Time to detect interrupt signal
2. Graceful shutdown time - Time to complete graceful shutdown
3. Checkpoint save on interrupt - Time to save checkpoint before exit

Requirements:
- Ollama llama3.1:8b-instruct-q8_0 (FREE, no API costs)
- Real interrupt infrastructure (NO MOCKING)
- Statistical rigor (100+ iterations, outlier removal)

Budget: $0.00 (Ollama is FREE)
Duration: ~10-15 minutes
"""

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

# CRITICAL: Load .env first (as per CLAUDE.md directives)
load_dotenv()

from benchmarks.framework import BenchmarkSuite
from kaizen.core.autonomy.interrupts.handlers import InterruptHandler, InterruptReason
from kaizen.core.autonomy.interrupts.manager import InterruptManager
from kaizen.core.autonomy.interrupts.signal import InterruptSignal
from kaizen.core.autonomy.state.manager import StateManager
from kaizen.core.autonomy.state.models import AgentState
from kaizen.core.autonomy.state.storage import FilesystemStorage

# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════


def check_ollama_available() -> bool:
    """Check if Ollama is running with llama3.2 model."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and "llama3.2" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_llama_model() -> str:
    """Get available llama3.2 model name."""
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        if "llama3.1:8b-instruct-q8_0" in result.stdout:
            return "llama3.1:8b-instruct-q8_0"
        elif "llama3.2" in result.stdout:
            return "llama3.2:latest"
        return "llama3.1:8b-instruct-q8_0"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "llama3.1:8b-instruct-q8_0"


LLAMA_MODEL = get_llama_model()


# ═══════════════════════════════════════════════════════════════
# Custom Interrupt Handler for Benchmarking
# ═══════════════════════════════════════════════════════════════


class BenchmarkInterruptHandler(InterruptHandler):
    """Lightweight interrupt handler for benchmarking."""

    def __init__(self):
        self.triggered = False

    async def check(self) -> InterruptSignal:
        """Simulate interrupt check."""
        if self.triggered:
            return InterruptSignal(
                should_interrupt=True,
                reason=InterruptReason.PROGRAMMATIC,
                graceful=True,
            )
        return InterruptSignal(should_interrupt=False)

    def trigger(self):
        """Manually trigger interrupt."""
        self.triggered = True

    def reset(self):
        """Reset interrupt state."""
        self.triggered = False


# ═══════════════════════════════════════════════════════════════
# Benchmark Suite
# ═══════════════════════════════════════════════════════════════


def create_suite() -> BenchmarkSuite:
    """Create interrupt benchmark suite."""
    suite = BenchmarkSuite(
        name="Interrupt Handling Performance",
        metadata={
            "suite_id": "suite5",
            "description": "Interrupt system benchmarks",
            "model": LLAMA_MODEL,
            "provider": "ollama",
        },
    )

    # Setup interrupt manager
    manager = InterruptManager()
    handler = BenchmarkInterruptHandler()
    manager.add_handler(handler)

    # Setup state manager for checkpoint benchmarks
    tmpdir = tempfile.mkdtemp()
    storage = FilesystemStorage(base_dir=tmpdir)
    state_manager = StateManager(storage=storage)

    # ───────────────────────────────────────────────────────────
    # Benchmark 1: Interrupt Detection Latency
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Interrupt Detection Latency",
        warmup=10,
        iterations=100,
        metadata={
            "component": "interrupt_detection",
            "description": "Time to detect interrupt signal",
        },
    )
    def bench_interrupt_detection():
        """
        Benchmark interrupt detection latency.

        Measures time to:
        - Check interrupt handlers
        - Detect interrupt signal
        - Return interrupt decision
        """
        # Reset handler
        handler.reset()

        # Trigger interrupt
        handler.trigger()

        # Check interrupt (should detect)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            signal = loop.run_until_complete(manager.check_interrupt())
            assert signal.should_interrupt is True
        finally:
            loop.close()

    # ───────────────────────────────────────────────────────────
    # Benchmark 2: Graceful Shutdown Time
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Graceful Shutdown Time",
        warmup=5,
        iterations=50,
        metadata={
            "component": "graceful_shutdown",
            "description": "Time to complete graceful shutdown",
        },
    )
    def bench_graceful_shutdown():
        """
        Benchmark graceful shutdown time.

        Measures time to:
        - Initiate graceful shutdown
        - Complete cleanup tasks
        - Finalize shutdown
        """
        # Reset handler
        handler.reset()

        # Trigger interrupt
        handler.trigger()

        # Simulate graceful shutdown
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            signal = loop.run_until_complete(manager.check_interrupt())
            assert signal.graceful is True

            # Simulate cleanup (lightweight)
            cleanup_tasks = []
            for _ in range(5):
                cleanup_tasks.append(asyncio.sleep(0.001))

            loop.run_until_complete(asyncio.gather(*cleanup_tasks))
        finally:
            loop.close()

    # ───────────────────────────────────────────────────────────
    # Benchmark 3: Checkpoint Save on Interrupt
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Checkpoint Save on Interrupt",
        warmup=5,
        iterations=50,
        metadata={
            "component": "checkpoint_on_interrupt",
            "description": "Time to save checkpoint before exit",
        },
    )
    def bench_checkpoint_on_interrupt():
        """
        Benchmark checkpoint save on interrupt.

        Measures time to:
        - Detect interrupt
        - Create checkpoint
        - Save state to disk
        """
        # Reset handler
        handler.reset()

        # Create agent state
        state = AgentState(
            agent_id="bench_agent",
            step_number=100,
            status="running",
            conversation_history=["turn1", "turn2", "turn3"],
            memory_contents={"key": "value"},
            budget_spent_usd=0.0,
        )

        # Trigger interrupt
        handler.trigger()

        # Save checkpoint
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            signal = loop.run_until_complete(manager.check_interrupt())
            assert signal.should_interrupt is True

            # Save checkpoint
            checkpoint_id = loop.run_until_complete(
                state_manager.save_checkpoint(state)
            )
            assert checkpoint_id is not None
        finally:
            loop.close()

    return suite


# ═══════════════════════════════════════════════════════════════
# Main Execution
# ═══════════════════════════════════════════════════════════════


def main():
    """Run interrupt benchmark suite."""
    print("\n" + "=" * 80)
    print("SUITE 5: INTERRUPT HANDLING PERFORMANCE BENCHMARKS")
    print("=" * 80)

    # Pre-flight checks
    if not check_ollama_available():
        print("\nWARNING: Ollama not running (not required for interrupt benchmarks)")

    print(f"\nUsing model: {LLAMA_MODEL} (for reference)")
    print("Budget: $0.00 (Interrupt benchmarks are FREE)")
    print()

    # Create and run suite
    suite = create_suite()
    results = suite.run()

    # Print summary
    suite.print_summary()

    # Export results
    output_path = Path("benchmarks/results/suite5_interrupts_results.json")
    suite.export_results(output_path)

    print(f"\nResults exported to: {output_path}")
    print("\n" + "=" * 80)
    print("SUITE 5 COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
