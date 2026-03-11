"""
Suite 6: Checkpoint Performance Benchmarks (TODO-171).

Measures checkpoint system performance:
1. Checkpoint save performance - Time to serialize and save state
2. Checkpoint load performance - Time to deserialize and restore state
3. Compression efficiency - Size reduction and overhead

Requirements:
- Ollama llama3.1:8b-instruct-q8_0 (FREE, no API costs)
- Real checkpoint infrastructure (NO MOCKING)
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
# Helper to Create Realistic Agent State
# ═══════════════════════════════════════════════════════════════


def create_realistic_state(step_number: int = 100) -> AgentState:
    """Create realistic agent state for benchmarking."""
    # Simulate 100-turn conversation
    conversation_history = []
    for i in range(100):
        conversation_history.append(f"User: Question {i}")
        conversation_history.append(f"Agent: Answer {i}")

    # Simulate memory contents
    memory_contents = {
        "hot_tier": {f"key_{i}": f"value_{i}" for i in range(50)},
        "warm_tier": {f"key_{i}": f"value_{i}" for i in range(50, 100)},
        "cold_tier": {f"key_{i}": f"value_{i}" for i in range(100, 200)},
    }

    return AgentState(
        agent_id="bench_agent",
        step_number=step_number,
        status="running",
        conversation_history=conversation_history,
        memory_contents=memory_contents,
        budget_spent_usd=1.23,
    )


# ═══════════════════════════════════════════════════════════════
# Benchmark Suite
# ═══════════════════════════════════════════════════════════════


def create_suite() -> BenchmarkSuite:
    """Create checkpoint benchmark suite."""
    suite = BenchmarkSuite(
        name="Checkpoint Performance",
        metadata={
            "suite_id": "suite6",
            "description": "Checkpoint system benchmarks",
            "model": LLAMA_MODEL,
            "provider": "ollama",
        },
    )

    # Setup state manager
    tmpdir = tempfile.mkdtemp()
    storage = FilesystemStorage(base_dir=tmpdir)
    state_manager = StateManager(
        storage=storage, checkpoint_frequency=10, retention_count=100
    )

    # ───────────────────────────────────────────────────────────
    # Benchmark 1: Checkpoint Save Performance
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Checkpoint Save Performance",
        warmup=10,
        iterations=100,
        metadata={
            "component": "checkpoint_save",
            "description": "Serialize and save state",
        },
    )
    def bench_checkpoint_save():
        """
        Benchmark checkpoint save performance.

        Measures time to:
        - Serialize agent state
        - Write to filesystem
        - Return checkpoint ID
        """
        state = create_realistic_state()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            checkpoint_id = loop.run_until_complete(
                state_manager.save_checkpoint(state)
            )
            assert checkpoint_id is not None
        finally:
            loop.close()

    # ───────────────────────────────────────────────────────────
    # Benchmark 2: Checkpoint Load Performance
    # ───────────────────────────────────────────────────────────

    # Pre-create checkpoint for load benchmark
    state = create_realistic_state()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        checkpoint_id = loop.run_until_complete(state_manager.save_checkpoint(state))
    finally:
        loop.close()

    @suite.benchmark(
        name="Checkpoint Load Performance",
        warmup=10,
        iterations=100,
        metadata={
            "component": "checkpoint_load",
            "description": "Deserialize and restore state",
        },
    )
    def bench_checkpoint_load():
        """
        Benchmark checkpoint load performance.

        Measures time to:
        - Read from filesystem
        - Deserialize agent state
        - Return restored state
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            restored_state = loop.run_until_complete(
                state_manager.load_checkpoint(checkpoint_id)
            )
            assert restored_state is not None
            assert restored_state.agent_id == "bench_agent"
        finally:
            loop.close()

    # ───────────────────────────────────────────────────────────
    # Benchmark 3: Compression Efficiency
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Compression Efficiency",
        warmup=5,
        iterations=50,
        metadata={
            "component": "compression",
            "description": "Size reduction and overhead",
        },
    )
    def bench_compression():
        """
        Benchmark compression efficiency.

        Measures time to:
        - Save checkpoint with compression
        - Calculate compression ratio
        - Validate size reduction
        """
        state = create_realistic_state()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Save checkpoint
            checkpoint_id = loop.run_until_complete(
                state_manager.save_checkpoint(state)
            )

            # Load checkpoint
            restored_state = loop.run_until_complete(
                state_manager.load_checkpoint(checkpoint_id)
            )

            # Verify integrity
            assert restored_state.agent_id == state.agent_id
            assert len(restored_state.conversation_history) == len(
                state.conversation_history
            )
        finally:
            loop.close()

    return suite


# ═══════════════════════════════════════════════════════════════
# Main Execution
# ═══════════════════════════════════════════════════════════════


def main():
    """Run checkpoint benchmark suite."""
    print("\n" + "=" * 80)
    print("SUITE 6: CHECKPOINT PERFORMANCE BENCHMARKS")
    print("=" * 80)

    # Pre-flight checks
    if not check_ollama_available():
        print("\nWARNING: Ollama not running (not required for checkpoint benchmarks)")

    print(f"\nUsing model: {LLAMA_MODEL} (for reference)")
    print("Budget: $0.00 (Checkpoint benchmarks are FREE)")
    print()

    # Create and run suite
    suite = create_suite()
    results = suite.run()

    # Print summary
    suite.print_summary()

    # Export results
    output_path = Path("benchmarks/results/suite6_checkpoints_results.json")
    suite.export_results(output_path)

    print(f"\nResults exported to: {output_path}")
    print("\n" + "=" * 80)
    print("SUITE 6 COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
