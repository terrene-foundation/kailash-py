"""
Performance Benchmarking

Simple performance comparison across providers.
"""

import os
import tempfile
import time

from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)


def benchmark_provider(provider_name: str, doc_path: str, iterations: int = 3):
    """Benchmark single provider."""
    config = DocumentExtractionConfig(
        provider=provider_name,
        landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
        openai_key=os.getenv("OPENAI_API_KEY"),
    )
    agent = DocumentExtractionAgent(config=config)

    if not agent.provider.is_available():
        return None

    times = []
    for i in range(iterations):
        start = time.time()
        result = agent.extract(doc_path, extract_tables=False, chunk_for_rag=False)
        elapsed = time.time() - start
        times.append(elapsed)

    return {
        "avg_time": sum(times) / len(times),
        "min_time": min(times),
        "max_time": max(times),
        "cost": result["cost"],
    }


def main():
    """Run performance benchmarks."""
    # Create test document
    content = "Test document " * 100  # ~1200 characters
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(content)
        doc_path = tmp.name

    print("=" * 70)
    print("Performance Benchmarking (3 iterations)")
    print("=" * 70)

    providers = ["ollama_vision", "openai_vision", "landing_ai"]

    for provider in providers:
        print(f"\n{provider}:")
        result = benchmark_provider(provider, doc_path, iterations=3)

        if result:
            print(f"  Avg time: {result['avg_time']:.3f}s")
            print(f"  Min time: {result['min_time']:.3f}s")
            print(f"  Max time: {result['max_time']:.3f}s")
            print(f"  Cost: ${result['cost']:.3f}")
        else:
            print("  NOT AVAILABLE")

    os.unlink(doc_path)

    print("\n" + "=" * 70)
    print("Note: OpenAI Vision typically fastest, Ollama is free")
    print("=" * 70)


if __name__ == "__main__":
    main()
