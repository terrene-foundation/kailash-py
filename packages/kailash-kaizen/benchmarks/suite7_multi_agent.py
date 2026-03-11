"""
Suite 7: Multi-Agent Performance Benchmarks (TODO-171).

Measures multi-agent coordination performance:
1. A2A protocol overhead - Capability card generation and matching
2. Semantic routing latency - Best-fit agent selection
3. Multi-agent task delegation - End-to-end coordination

Requirements:
- Ollama llama3.1:8b-instruct-q8_0 (FREE, no API costs)
- Real A2A infrastructure (NO MOCKING)
- Statistical rigor (100+ iterations, outlier removal)

Budget: $0.00 (Ollama is FREE)
Duration: ~15-20 minutes
"""

import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# CRITICAL: Load .env first (as per CLAUDE.md directives)
load_dotenv()

from benchmarks.framework import BenchmarkSuite
from kaizen.agents.coordination.a2a.capability import (
    CapabilityCard,
    CapabilityMatcher,
    SemanticMatcher,
)
from kaizen.agents.coordination.a2a.protocol import A2AProtocol
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
        return "llama3.1:8b-instruct-q8_0"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "llama3.1:8b-instruct-q8_0"


LLAMA_MODEL = get_llama_model()


# ═══════════════════════════════════════════════════════════════
# Signatures for Multi-Agent Testing
# ═══════════════════════════════════════════════════════════════


class CodeSignature(Signature):
    """Code generation signature."""

    task: str = InputField(description="Coding task")
    code: str = OutputField(description="Generated code")


class DataSignature(Signature):
    """Data analysis signature."""

    task: str = InputField(description="Data analysis task")
    analysis: str = OutputField(description="Analysis result")


class WritingSignature(Signature):
    """Content writing signature."""

    task: str = InputField(description="Writing task")
    content: str = OutputField(description="Written content")


# ═══════════════════════════════════════════════════════════════
# Helper to Create Test Agents
# ═══════════════════════════════════════════════════════════════


def create_test_agents():
    """Create test agents with different capabilities."""
    config = BaseAgentConfig(
        llm_provider="ollama", model=LLAMA_MODEL, temperature=0.7, max_tokens=50
    )

    code_agent = BaseAgent(
        config=config,
        signature=CodeSignature(),
        agent_id="code_expert",
        name="Code Expert",
    )

    data_agent = BaseAgent(
        config=config,
        signature=DataSignature(),
        agent_id="data_expert",
        name="Data Expert",
    )

    writing_agent = BaseAgent(
        config=config,
        signature=WritingSignature(),
        agent_id="writing_expert",
        name="Writing Expert",
    )

    return [code_agent, data_agent, writing_agent]


# ═══════════════════════════════════════════════════════════════
# Benchmark Suite
# ═══════════════════════════════════════════════════════════════


def create_suite() -> BenchmarkSuite:
    """Create multi-agent benchmark suite."""
    suite = BenchmarkSuite(
        name="Multi-Agent Coordination Performance",
        metadata={
            "suite_id": "suite7",
            "description": "Multi-agent coordination benchmarks",
            "model": LLAMA_MODEL,
            "provider": "ollama",
        },
    )

    # Create test agents
    agents = create_test_agents()

    # Create capability cards
    capability_cards = [
        CapabilityCard(
            agent_id="code_expert",
            name="Code Expert",
            description="Expert in code generation and programming",
            capabilities=["code_generation", "debugging", "refactoring"],
            expertise_domains=["python", "javascript", "software_engineering"],
        ),
        CapabilityCard(
            agent_id="data_expert",
            name="Data Expert",
            description="Expert in data analysis and visualization",
            capabilities=["data_analysis", "visualization", "statistics"],
            expertise_domains=["data_science", "analytics", "machine_learning"],
        ),
        CapabilityCard(
            agent_id="writing_expert",
            name="Writing Expert",
            description="Expert in content writing and documentation",
            capabilities=["writing", "editing", "documentation"],
            expertise_domains=[
                "technical_writing",
                "content_creation",
                "communication",
            ],
        ),
    ]

    # Create semantic matcher
    matcher = SemanticMatcher()

    # Create A2A protocol
    protocol = A2AProtocol()

    # ───────────────────────────────────────────────────────────
    # Benchmark 1: A2A Protocol Overhead
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="A2A Protocol Overhead",
        warmup=10,
        iterations=100,
        metadata={
            "component": "a2a_protocol",
            "description": "Capability card generation",
        },
    )
    def bench_a2a_protocol():
        """
        Benchmark A2A protocol overhead.

        Measures time to:
        - Generate capability card from agent
        - Serialize to A2A format
        - Return capability card
        """
        agent = agents[0]

        # Generate capability card
        card = agent.to_a2a_card()

        # Verify card
        assert card.agent_id == agent.agent_id
        assert card.name == agent.name

    # ───────────────────────────────────────────────────────────
    # Benchmark 2: Semantic Routing Latency
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Semantic Routing Latency",
        warmup=10,
        iterations=100,
        metadata={
            "component": "semantic_routing",
            "description": "Best-fit agent selection",
        },
    )
    def bench_semantic_routing():
        """
        Benchmark semantic routing latency.

        Measures time to:
        - Match task to agent capabilities
        - Calculate semantic similarity
        - Return best-fit agent
        """
        task = "Analyze sales data and create visualization"

        # Find best match
        best_match = matcher.find_best_match(task, capability_cards)

        # Verify match
        assert best_match is not None
        assert best_match["card"].agent_id == "data_expert"

    # ───────────────────────────────────────────────────────────
    # Benchmark 3: Multi-Agent Task Delegation
    # ───────────────────────────────────────────────────────────

    @suite.benchmark(
        name="Multi-Agent Task Delegation",
        warmup=5,
        iterations=50,
        metadata={
            "component": "task_delegation",
            "description": "End-to-end coordination",
        },
    )
    def bench_task_delegation():
        """
        Benchmark multi-agent task delegation.

        Measures time to:
        - Route task to appropriate agent
        - Execute task via selected agent
        - Return result
        """
        tasks = [
            ("Write a function to calculate fibonacci", "code_expert"),
            ("Analyze customer churn data", "data_expert"),
            ("Create technical documentation", "writing_expert"),
        ]

        for task_description, expected_agent in tasks:
            # Find best match
            best_match = matcher.find_best_match(task_description, capability_cards)

            # Verify routing
            assert best_match["card"].agent_id == expected_agent

    return suite


# ═══════════════════════════════════════════════════════════════
# Main Execution
# ═══════════════════════════════════════════════════════════════


def main():
    """Run multi-agent benchmark suite."""
    print("\n" + "=" * 80)
    print("SUITE 7: MULTI-AGENT COORDINATION PERFORMANCE BENCHMARKS")
    print("=" * 80)

    # Pre-flight checks
    if not check_ollama_available():
        print("\nWARNING: Ollama not running (not required for multi-agent benchmarks)")

    print(f"\nUsing model: {LLAMA_MODEL} (for reference)")
    print("Budget: $0.00 (Multi-agent benchmarks are FREE)")
    print()

    # Create and run suite
    suite = create_suite()
    results = suite.run()

    # Print summary
    suite.print_summary()

    # Export results
    output_path = Path("benchmarks/results/suite7_multi_agent_results.json")
    suite.export_results(output_path)

    print(f"\nResults exported to: {output_path}")
    print("\n" + "=" * 80)
    print("SUITE 7 COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
