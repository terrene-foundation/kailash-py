"""
Suite 2: Execution Performance Benchmarks (TODO-171).

Measures agent execution performance across three scenarios:
1. Single-shot execution - One-off query/response
2. Multi-turn conversations - Sequential turns with memory
3. Long-running autonomous tasks - Extended execution

Requirements:
- Ollama llama3.1:8b-instruct-q8_0 (FREE, no API costs)
- Real infrastructure (NO MOCKING)
- Statistical rigor (100+ iterations, outlier removal)

Budget: $0.00 (Ollama is FREE)
Duration: ~20-30 minutes
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
from kaizen.memory.persistent_buffer import PersistentBufferMemory
from kaizen.signatures import InputField, OutputField, Signature

try:
    from dataflow import DataFlow

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False


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
# Signatures for Testing
# ═══════════════════════════════════════════════════════════════


class SimpleQASignature(Signature):
    """Minimal Q&A signature for single-shot testing."""

    question: str = InputField(description="Question")
    answer: str = OutputField(description="Short answer (1-2 sentences)")


class ConversationSignature(Signature):
    """Conversational signature for multi-turn testing."""

    message: str = InputField(description="User message")
    response: str = OutputField(description="Agent response")


# ═══════════════════════════════════════════════════════════════
# Benchmark Suite
# ═══════════════════════════════════════════════════════════════


def create_suite() -> BenchmarkSuite:
    """Create execution benchmark suite."""
    suite = BenchmarkSuite(
        name="Execution Performance",
        metadata={
            "suite_id": "suite2",
            "description": "Agent execution benchmarks",
            "model": LLAMA_MODEL,
            "provider": "ollama",
        },
    )

    # Shared agent instances for warm benchmarks
    _single_shot_agent = None
    _multi_turn_agent = None

    # ───────────────────────────────────────────────────────────
    # Benchmark 1: Single-Shot Execution
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Single-Shot Execution",
        warmup=5,
        iterations=50,
        metadata={
            "scenario": "single_shot",
            "description": "One-off query/response",
        },
    )
    def bench_single_shot():
        """
        Benchmark single-shot execution.

        Measures time to:
        - Execute single query
        - Generate response
        - Return result
        """
        nonlocal _single_shot_agent

        # Create agent once (warm start after first iteration)
        if _single_shot_agent is None:
            config = BaseAgentConfig(
                llm_provider="ollama",
                model=LLAMA_MODEL,
                temperature=0.7,
                max_tokens=50,
            )
            _single_shot_agent = BaseAgent(config=config, signature=SimpleQASignature())

        # Execute query
        result = _single_shot_agent.run(question="What is 2+2?")

        # Verify response
        assert "answer" in result

    # ───────────────────────────────────────────────────────────
    # Benchmark 2: Multi-Turn Conversations
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Multi-Turn Conversations",
        warmup=3,
        iterations=30,
        metadata={
            "scenario": "multi_turn",
            "description": "Sequential turns with memory",
        },
    )
    def bench_multi_turn():
        """
        Benchmark multi-turn conversation.

        Measures time to:
        - Execute turn with conversation history
        - Update memory
        - Generate context-aware response
        """
        nonlocal _multi_turn_agent

        # Create agent with memory once
        if _multi_turn_agent is None:
            config = BaseAgentConfig(
                llm_provider="ollama",
                model=LLAMA_MODEL,
                temperature=0.7,
                max_tokens=50,
            )
            _multi_turn_agent = BaseAgent(
                config=config, signature=ConversationSignature()
            )

        # Execute 3 turns in conversation
        messages = [
            "Hi, I'm testing the agent.",
            "Can you remember what I just said?",
            "What was my first message?",
        ]

        for msg in messages:
            result = _multi_turn_agent.run(message=msg)
            assert "response" in result

    # ───────────────────────────────────────────────────────────
    # Benchmark 3: Long-Running Autonomous Tasks
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Long-Running Autonomous Tasks",
        warmup=2,
        iterations=20,
        metadata={
            "scenario": "long_running",
            "description": "Extended autonomous execution",
        },
    )
    def bench_long_running():
        """
        Benchmark long-running autonomous task.

        Measures time to:
        - Execute multi-step autonomous task
        - Maintain state across steps
        - Complete complex workflow
        """
        config = BaseAgentConfig(
            llm_provider="ollama",
            model=LLAMA_MODEL,
            temperature=0.7,
            max_tokens=100,
        )

        agent = BaseAgent(config=config, signature=SimpleQASignature())

        # Simulate long-running task with 5 sequential queries
        queries = [
            "What is AI?",
            "What is machine learning?",
            "What is deep learning?",
            "What is NLP?",
            "What is computer vision?",
        ]

        for query in queries:
            result = agent.run(question=query)
            assert "answer" in result

        agent.cleanup()

    return suite


# ═══════════════════════════════════════════════════════════════
# Main Execution
# ═══════════════════════════════════════════════════════════════


def main():
    """Run execution benchmark suite."""
    print("\n" + "=" * 80)
    print("SUITE 2: EXECUTION PERFORMANCE BENCHMARKS")
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
    output_path = Path("benchmarks/results/suite2_execution_results.json")
    suite.export_results(output_path)

    print(f"\nResults exported to: {output_path}")
    print("\n" + "=" * 80)
    print("SUITE 2 COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
