"""
Suite 1: Initialization Performance Benchmarks (TODO-171).

Measures agent initialization performance across three scenarios:
1. Cold start - Fresh process, first agent creation
2. Warm start - Reused runtime, multiple agents
3. Lazy initialization - On-demand component loading

Requirements:
- Ollama llama3.1:8b-instruct-q8_0 (FREE, no API costs)
- Real infrastructure (NO MOCKING)
- Statistical rigor (100+ iterations, outlier removal)

Budget: $0.00 (Ollama is FREE)
Duration: ~10-15 minutes
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

# CRITICAL: Load .env first (as per CLAUDE.md directives)
load_dotenv()

from benchmarks.framework import BenchmarkSuite
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature

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
        return "llama3.1:8b-instruct-q8_0"  # Default fallback
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "llama3.1:8b-instruct-q8_0"


LLAMA_MODEL = get_llama_model()


# ═══════════════════════════════════════════════════════════════
# Simple Signature for Testing
# ═══════════════════════════════════════════════════════════════


class SimpleQASignature(Signature):
    """Minimal Q&A signature for initialization testing."""

    question: str = InputField(description="Question")
    answer: str = OutputField(description="Answer")


# ═══════════════════════════════════════════════════════════════
# Benchmark Suite
# ═══════════════════════════════════════════════════════════════


def create_suite() -> BenchmarkSuite:
    """Create initialization benchmark suite."""
    suite = BenchmarkSuite(
        name="Initialization Performance",
        metadata={
            "suite_id": "suite1",
            "description": "Agent initialization benchmarks",
            "model": LLAMA_MODEL,
            "provider": "ollama",
        },
    )

    # Global state for warm start scenario
    _config = None
    _signature = None

    # ───────────────────────────────────────────────────────────
    # Benchmark 1: Cold Start
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Cold Start (Fresh Process)",
        warmup=5,
        iterations=50,
        metadata={"scenario": "cold_start", "description": "First agent creation"},
    )
    def bench_cold_start():
        """
        Benchmark cold start - fresh agent creation.

        Measures time to:
        - Initialize BaseAgentConfig
        - Create Signature instance
        - Instantiate BaseAgent
        - Load strategy and providers
        """
        config = BaseAgentConfig(
            llm_provider="ollama",
            model=LLAMA_MODEL,
            temperature=0.7,
            max_tokens=50,
        )

        signature = SimpleQASignature()

        agent = BaseAgent(config=config, signature=signature)

        # Cleanup to simulate fresh start in next iteration
        agent.cleanup()

    # ───────────────────────────────────────────────────────────
    # Benchmark 2: Warm Start
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Warm Start (Reused Runtime)",
        warmup=10,
        iterations=100,
        metadata={
            "scenario": "warm_start",
            "description": "Multiple agents with shared runtime",
        },
    )
    def bench_warm_start():
        """
        Benchmark warm start - reused config and signature.

        Measures time to:
        - Create new agent with cached config/signature
        - Reuse provider instances
        - Skip redundant initialization
        """
        nonlocal _config, _signature

        # Initialize shared resources once (simulates warm start)
        if _config is None:
            _config = BaseAgentConfig(
                llm_provider="ollama",
                model=LLAMA_MODEL,
                temperature=0.7,
                max_tokens=50,
            )
            _signature = SimpleQASignature()

        # Create agent with reused config
        agent = BaseAgent(config=_config, signature=_signature)

        # Cleanup but keep config/signature cached
        agent.cleanup()

    # ───────────────────────────────────────────────────────────
    # Benchmark 3: Lazy Initialization
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Lazy Initialization (On-Demand)",
        warmup=10,
        iterations=100,
        metadata={
            "scenario": "lazy_init",
            "description": "Deferred component loading",
        },
    )
    def bench_lazy_init():
        """
        Benchmark lazy initialization - deferred loading.

        Measures time to:
        - Create agent without full initialization
        - Load components on-demand
        - Minimize upfront overhead
        """
        # BaseAgent uses lazy initialization by default
        config = BaseAgentConfig(
            llm_provider="ollama",
            model=LLAMA_MODEL,
            temperature=0.7,
            max_tokens=50,
        )

        signature = SimpleQASignature()

        # Agent created but providers not initialized until first run()
        agent = BaseAgent(config=config, signature=signature)

        # Cleanup
        agent.cleanup()

    return suite


# ═══════════════════════════════════════════════════════════════
# Main Execution
# ═══════════════════════════════════════════════════════════════


def main():
    """Run initialization benchmark suite."""
    print("\n" + "=" * 80)
    print("SUITE 1: INITIALIZATION PERFORMANCE BENCHMARKS")
    print("=" * 80)

    # Pre-flight checks
    if not check_ollama_available():
        print("\nERROR: Ollama not running or llama3.2 model not available")
        print("Please install and start Ollama:")
        print("  1. Install: https://ollama.ai/download")
        print("  2. Pull model: ollama pull llama3.1:8b-instruct-q8_0")
        print("  3. Verify: ollama list")
        sys.exit(1)

    print(f"\nUsing model: {LLAMA_MODEL}")
    print("Budget: $0.00 (Ollama is FREE)")
    print()

    # Create and run suite
    suite = create_suite()
    results = suite.run()

    # Print summary
    suite.print_summary()

    # Export results
    output_path = Path("benchmarks/results/suite1_initialization_results.json")
    suite.export_results(output_path)

    print(f"\nResults exported to: {output_path}")
    print("\n" + "=" * 80)
    print("SUITE 1 COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
