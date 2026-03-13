"""
Production overhead validation with real LLM calls.

Validates observability system overhead using actual OpenAI/Anthropic API calls
with realistic agent workloads (500ms+ operations).

Budget: $1-5 for 100 API requests
"""

import asyncio
import os
import statistics
import time
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

# CRITICAL: Load .env first (as per CLAUDE.md directives)
load_dotenv()

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.single_shot import SingleShotStrategy


class QASignature(Signature):
    """Q&A signature for validation testing."""

    question: str = InputField(description="Question")
    answer: str = OutputField(description="Answer")


@dataclass
class ValidationResult:
    """Results from overhead validation."""

    baseline_avg_ms: float
    observability_avg_ms: float
    overhead_ms: float
    overhead_percent: float
    sample_size: int
    provider: str
    model: str


class ProductionOverheadValidator:
    """Validates observability overhead with real LLM calls."""

    def __init__(self, provider: str = "openai", model: str = "gpt-3.5-turbo"):
        self.provider = provider
        self.model = model

    async def run_baseline_test(self, num_requests: int = 50) -> List[float]:
        """Run baseline test WITHOUT observability."""
        print(f"\n{'='*80}")
        print(f"BASELINE: {num_requests} requests WITHOUT observability")
        print(f"Provider: {self.provider}, Model: {self.model}")
        print(f"{'='*80}\n")

        config = BaseAgentConfig(
            llm_provider=self.provider,
            model=self.model,
            temperature=0.7,
            max_tokens=100,
        )

        # Use synchronous strategy to avoid event loop issues
        strategy = SingleShotStrategy()
        agent = BaseAgent(config=config, signature=QASignature(), strategy=strategy)

        latencies = []
        questions = [
            "What is AI?",
            "Explain machine learning.",
            "What is Python?",
            "Define neural networks.",
            "What is NLP?",
        ]

        for i in range(num_requests):
            question = questions[i % len(questions)]
            print(f"Request {i+1}/{num_requests}: {question[:30]}...")

            start = time.perf_counter()
            result = agent.run(question=question)
            latency_ms = (time.perf_counter() - start) * 1000

            latencies.append(latency_ms)
            print(f"  Latency: {latency_ms:.2f}ms")
            print(f"  Answer: {result.get('answer', 'ERROR')[:50]}...")

            # Small delay to avoid rate limits
            await asyncio.sleep(0.5)

        agent.cleanup()

        print("\nBaseline Statistics:")
        print(f"  Average: {statistics.mean(latencies):.2f}ms")
        print(f"  Median:  {statistics.median(latencies):.2f}ms")
        print(f"  Min:     {min(latencies):.2f}ms")
        print(f"  Max:     {max(latencies):.2f}ms")

        return latencies

    async def run_observability_test(self, num_requests: int = 50) -> List[float]:
        """Run test WITH full observability enabled."""
        print(f"\n{'='*80}")
        print(f"WITH OBSERVABILITY: {num_requests} requests WITH full observability")
        print(f"Provider: {self.provider}, Model: {self.model}")
        print(f"{'='*80}\n")

        config = BaseAgentConfig(
            llm_provider=self.provider,
            model=self.model,
            temperature=0.7,
            max_tokens=100,
        )

        # Use synchronous strategy to avoid event loop issues
        strategy = SingleShotStrategy()
        agent = BaseAgent(config=config, signature=QASignature(), strategy=strategy)

        # Enable full observability
        obs = agent.enable_observability(
            service_name="production-validation",
            enable_metrics=True,
            enable_logging=True,
            enable_tracing=True,
            enable_audit=True,
        )

        latencies = []
        questions = [
            "What is AI?",
            "Explain machine learning.",
            "What is Python?",
            "Define neural networks.",
            "What is NLP?",
        ]

        for i in range(num_requests):
            question = questions[i % len(questions)]
            print(f"Request {i+1}/{num_requests}: {question[:30]}...")

            start = time.perf_counter()
            result = agent.run(question=question)
            latency_ms = (time.perf_counter() - start) * 1000

            latencies.append(latency_ms)
            print(f"  Latency: {latency_ms:.2f}ms")
            print(f"  Answer: {result.get('answer', 'ERROR')[:50]}...")

            # Record custom metric
            await obs.record_metric(
                "validation_request_duration_ms", latency_ms, type="histogram"
            )

            # Small delay to avoid rate limits
            await asyncio.sleep(0.5)

        agent.cleanup()

        print("\nWith Observability Statistics:")
        print(f"  Average: {statistics.mean(latencies):.2f}ms")
        print(f"  Median:  {statistics.median(latencies):.2f}ms")
        print(f"  Min:     {min(latencies):.2f}ms")
        print(f"  Max:     {max(latencies):.2f}ms")

        return latencies

    def remove_outliers(self, data: List[float], threshold: float = 3.0) -> List[float]:
        """
        Remove outliers using the IQR (Interquartile Range) method.

        Args:
            data: List of measurements
            threshold: Number of IQRs beyond which a point is considered an outlier

        Returns:
            Filtered list with outliers removed
        """
        if len(data) < 4:
            return data  # Not enough data for meaningful outlier detection

        # Calculate Q1, Q3, and IQR
        sorted_data = sorted(data)
        q1_idx = len(sorted_data) // 4
        q3_idx = (3 * len(sorted_data)) // 4
        q1 = sorted_data[q1_idx]
        q3 = sorted_data[q3_idx]
        iqr = q3 - q1

        # Define outlier bounds
        lower_bound = q1 - (threshold * iqr)
        upper_bound = q3 + (threshold * iqr)

        # Filter outliers
        filtered = [x for x in data if lower_bound <= x <= upper_bound]

        # Report removed outliers
        removed = [x for x in data if x < lower_bound or x > upper_bound]
        if removed:
            print("\n  Outliers detected and removed:")
            for outlier in removed:
                print(
                    f"    {outlier:.2f}ms (bounds: {lower_bound:.2f}-{upper_bound:.2f}ms)"
                )

        return filtered

    def calculate_overhead(
        self, baseline: List[float], observability: List[float]
    ) -> ValidationResult:
        """Calculate overhead from baseline and observability tests."""
        # Remove outliers from both datasets
        print("\nCleaning baseline data...")
        baseline_clean = self.remove_outliers(baseline)

        print("\nCleaning observability data...")
        obs_clean = self.remove_outliers(observability)

        # Calculate statistics on cleaned data
        baseline_avg = statistics.mean(baseline_clean)
        obs_avg = statistics.mean(obs_clean)
        overhead_ms = obs_avg - baseline_avg
        overhead_percent = (overhead_ms / baseline_avg) * 100

        print("\nCleaned sample sizes:")
        print(f"  Baseline: {len(baseline_clean)}/{len(baseline)} samples")
        print(f"  Observability: {len(obs_clean)}/{len(observability)} samples")

        return ValidationResult(
            baseline_avg_ms=baseline_avg,
            observability_avg_ms=obs_avg,
            overhead_ms=overhead_ms,
            overhead_percent=overhead_percent,
            sample_size=len(baseline_clean),  # Report cleaned sample size
            provider=self.provider,
            model=self.model,
        )

    async def validate(self, num_requests: int = 50) -> ValidationResult:
        """Run complete validation test."""
        print(f"\n{'#'*80}")
        print("# Production Overhead Validation")
        print(f"# Provider: {self.provider}, Model: {self.model}")
        print(
            f"# Requests: {num_requests} baseline + {num_requests} with observability"
        )
        print(f"{'#'*80}\n")

        # Run baseline
        baseline_latencies = await self.run_baseline_test(num_requests)

        # Wait between tests
        print("\nWaiting 5 seconds before observability test...")
        await asyncio.sleep(5)

        # Run with observability
        obs_latencies = await self.run_observability_test(num_requests)

        # Calculate results
        result = self.calculate_overhead(baseline_latencies, obs_latencies)

        # Print final results
        print(f"\n{'='*80}")
        print("FINAL RESULTS")
        print(f"{'='*80}")
        print(f"Baseline Average:           {result.baseline_avg_ms:.2f}ms")
        print(f"With Observability Average: {result.observability_avg_ms:.2f}ms")
        print(f"Overhead (absolute):        {result.overhead_ms:.2f}ms")
        print(f"Overhead (percentage):      {result.overhead_percent:.2f}%")
        print(f"Sample Size:                {result.sample_size} requests per test")
        print(f"{'='*80}")

        # Evaluate against targets
        target_percent = 10.0  # <10% total overhead target
        if result.overhead_percent <= target_percent:
            print(
                f"\n✅ PASS: Overhead {result.overhead_percent:.2f}% <= {target_percent}% target"
            )
        else:
            print(
                f"\n❌ FAIL: Overhead {result.overhead_percent:.2f}% > {target_percent}% target"
            )

        return result


async def main():
    """Run production overhead validation."""
    # Check API keys
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("ERROR: OPENAI_API_KEY not found in environment")
        print("Please set OPENAI_API_KEY in .env file")
        return 1

    print("API keys found. Starting validation...")

    # Run OpenAI validation
    validator = ProductionOverheadValidator(provider="openai", model="gpt-3.5-turbo")

    result = await validator.validate(
        num_requests=30
    )  # Production validation with outlier detection

    # Save results
    results_file = ""
    with open(results_file, "w") as f:
        f.write("# Production Overhead Validation Results\n\n")
        f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Test Configuration\n\n")
        f.write(f"- **Provider**: {result.provider}\n")
        f.write(f"- **Model**: {result.model}\n")
        f.write(f"- **Sample Size**: {result.sample_size} requests per test\n")
        f.write(f"- **Total Requests**: {result.sample_size * 2}\n\n")
        f.write("## Results\n\n")
        f.write("| Metric | Value |\n")
        f.write("|--------|-------|\n")
        f.write(f"| Baseline Average | {result.baseline_avg_ms:.2f}ms |\n")
        f.write(f"| With Observability | {result.observability_avg_ms:.2f}ms |\n")
        f.write(f"| Overhead (absolute) | {result.overhead_ms:.2f}ms |\n")
        f.write(f"| **Overhead (%)** | **{result.overhead_percent:.2f}%** |\n\n")
        f.write("## Evaluation\n\n")
        if result.overhead_percent <= 10.0:
            f.write(
                f"✅ **PASS**: Overhead {result.overhead_percent:.2f}% <= 10% target\n\n"
            )
            f.write(
                "The observability system meets production performance requirements.\n"
            )
        else:
            f.write(
                f"❌ **FAIL**: Overhead {result.overhead_percent:.2f}% > 10% target\n\n"
            )
            f.write(
                "The observability system exceeds acceptable overhead. Review implementation.\n"
            )

    print(f"\nResults saved to: {results_file}")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
