"""
Suite 3: Memory Performance Benchmarks (TODO-171).

Measures 3-tier memory system performance:
1. Hot tier access - In-memory buffer (< 1ms target)
2. Warm tier access - Recent database fetch (< 10ms target)
3. Cold tier persistence - Historical data storage (< 100ms target)

Requirements:
- Ollama llama3.1:8b-instruct-q8_0 (FREE, no API costs)
- Real DataFlow backend with SQLite
- Real infrastructure (NO MOCKING)
- Statistical rigor (100+ iterations, outlier removal)

Budget: $0.00 (Ollama is FREE)
Duration: ~15-20 minutes
"""

import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# CRITICAL: Load .env first (as per CLAUDE.md directives)
load_dotenv()

from benchmarks.framework import BenchmarkSuite

try:
    from dataflow import DataFlow

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False

from kaizen.memory.backends.dataflow_backend import DataFlowBackend
from kaizen.memory.persistent_buffer import PersistentBufferMemory

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
# Memory Setup
# ═══════════════════════════════════════════════════════════════


def setup_memory_backend():
    """Create DataFlow backend with unique model."""
    if not DATAFLOW_AVAILABLE:
        raise RuntimeError("DataFlow not installed")

    # Create temp database
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "benchmark_memory.db"
    db_url = f"sqlite:///{db_path}"

    # Create DataFlow instance
    db = DataFlow(db_url=db_url, auto_migrate=True)

    # Create unique model name
    timestamp = str(int(time.time() * 1000000))
    model_name = f"BenchMsg_{timestamp}"

    # Create model class dynamically
    model_class = type(
        model_name,
        (),
        {
            "__annotations__": {
                "id": str,
                "conversation_id": str,
                "sender": str,
                "content": str,
                "metadata": Optional[dict],
                "created_at": datetime,
            },
        },
    )

    # Register model
    db.model(model_class)

    # Create backend
    backend = DataFlowBackend(db=db, model_name=model_name)

    return backend, tmpdir


# ═══════════════════════════════════════════════════════════════
# Benchmark Suite
# ═══════════════════════════════════════════════════════════════


def create_suite() -> BenchmarkSuite:
    """Create memory benchmark suite."""
    suite = BenchmarkSuite(
        name="Memory Performance",
        metadata={
            "suite_id": "suite3",
            "description": "3-tier memory system benchmarks",
            "model": LLAMA_MODEL,
            "provider": "ollama",
        },
    )

    # Setup memory instances
    backend, tmpdir = setup_memory_backend()

    # Hot tier: large buffer, no TTL
    memory_hot = PersistentBufferMemory(
        backend=backend, max_turns=1000, cache_ttl_seconds=None
    )

    # Warm tier: small buffer to force DB reads
    memory_warm = PersistentBufferMemory(
        backend=backend, max_turns=10, cache_ttl_seconds=300
    )

    # Cold tier: large buffer for bulk writes
    memory_cold = PersistentBufferMemory(
        backend=backend, max_turns=2000, cache_ttl_seconds=None
    )

    # Pre-populate for hot tier benchmark
    session_hot = "hot_tier_session"
    for i in range(100):
        turn = {
            "user": f"Question {i}",
            "agent": f"Answer {i}",
            "timestamp": datetime.now().isoformat(),
        }
        memory_hot.save_turn(session_hot, turn)

    # Pre-populate for warm tier benchmark
    session_warm = "warm_tier_session"
    for i in range(50):
        turn = {
            "user": f"Question {i}",
            "agent": f"Answer {i}",
            "timestamp": datetime.now().isoformat(),
        }
        memory_warm.save_turn(session_warm, turn)

    # ───────────────────────────────────────────────────────────
    # Benchmark 1: Hot Tier Access
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Hot Tier Access (< 1ms target)",
        warmup=10,
        iterations=100,
        metadata={
            "tier": "hot",
            "description": "In-memory buffer access",
            "target_ms": 1.0,
        },
    )
    def bench_hot_tier():
        """
        Benchmark hot tier access.

        Measures time to:
        - Retrieve data from in-memory buffer
        - No database queries
        - Target: < 1ms
        """
        context = memory_hot.load_context(session_hot)
        assert len(context["turns"]) == 100

    # ───────────────────────────────────────────────────────────
    # Benchmark 2: Warm Tier Access
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Warm Tier Access (< 10ms target)",
        warmup=5,
        iterations=50,
        metadata={
            "tier": "warm",
            "description": "Recent database fetch",
            "target_ms": 10.0,
        },
    )
    def bench_warm_tier():
        """
        Benchmark warm tier access.

        Measures time to:
        - Retrieve data from database (recent)
        - Cache invalidation forces DB read
        - Target: < 10ms
        """
        # Invalidate cache to force DB read
        memory_warm.invalidate_cache(session_warm)

        context = memory_warm.load_context(session_warm)
        assert len(context["turns"]) == 10  # Cache limit

    # ───────────────────────────────────────────────────────────
    # Benchmark 3: Cold Tier Persistence
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Cold Tier Persistence (< 100ms target)",
        warmup=5,
        iterations=50,
        metadata={
            "tier": "cold",
            "description": "Historical data storage",
            "target_ms": 100.0,
        },
    )
    def bench_cold_tier():
        """
        Benchmark cold tier persistence.

        Measures time to:
        - Persist data to database (cold storage)
        - Historical data writes
        - Target: < 100ms
        """
        session_cold = f"cold_tier_session_{time.time()}"

        turn = {
            "user": "Historical question",
            "agent": "Historical answer",
            "timestamp": datetime.now().isoformat(),
        }

        memory_cold.save_turn(session_cold, turn)

    return suite


# ═══════════════════════════════════════════════════════════════
# Main Execution
# ═══════════════════════════════════════════════════════════════


def main():
    """Run memory benchmark suite."""
    print("\n" + "=" * 80)
    print("SUITE 3: MEMORY PERFORMANCE BENCHMARKS")
    print("=" * 80)

    # Pre-flight checks
    if not DATAFLOW_AVAILABLE:
        print("\nERROR: DataFlow not installed")
        print("Please install: pip install kailash-dataflow")
        sys.exit(1)

    if not check_ollama_available():
        print("\nWARNING: Ollama not running (not required for memory benchmarks)")

    print(f"\nUsing model: {LLAMA_MODEL} (for reference)")
    print("Budget: $0.00 (Memory benchmarks are FREE)")
    print()

    # Create and run suite
    suite = create_suite()
    results = suite.run()

    # Print summary
    suite.print_summary()

    # Export results
    output_path = Path("benchmarks/results/suite3_memory_results.json")
    suite.export_results(output_path)

    print(f"\nResults exported to: {output_path}")
    print("\n" + "=" * 80)
    print("SUITE 3 COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
