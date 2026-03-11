"""
Batch Document Processing Demo

Demonstrates:
1. Sequential vs. parallel batch processing
2. Progress tracking and monitoring
3. Error handling in batch operations
4. Cost tracking across batches
5. Performance benchmarking

This example shows production-ready batch processing patterns.
"""

import asyncio
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)


@dataclass
class BatchResult:
    """Result of batch processing."""

    total_documents: int
    successful: int
    failed: int
    total_cost: float
    total_time: float
    documents: List[Dict[str, Any]]


def create_test_documents(count: int = 5) -> List[str]:
    """Create test documents for batch processing."""

    templates = [
        "# Financial Report\n\nRevenue: $1M\nExpenses: $700K\nProfit: $300K",
        "# Meeting Notes\n\nAttendees: 10\nAction items: 5\nFollow-ups: 3",
        "# Project Status\n\nProgress: 75%\nBudget: On track\nDeadline: Met",
        "# Customer Feedback\n\nSatisfaction: 4.8/5\nComplaints: 2\nPraise: 45",
        "# Sales Summary\n\nDeals: 15\nRevenue: $500K\nConversion: 30%",
    ]

    docs = []
    for i in range(count):
        template = templates[i % len(templates)]
        content = f"{template}\n\nDocument #{i+1}\nTimestamp: {time.time()}"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write(content)
            docs.append(tmp.name)

    return docs


class BatchDocumentProcessor:
    """Batch document processor with monitoring."""

    def __init__(self, config: DocumentExtractionConfig):
        """Initialize batch processor."""
        self.agent = DocumentExtractionAgent(config=config)
        self.results: List[Dict[str, Any]] = []
        self.total_cost = 0.0

    def process_sequential(self, file_paths: List[str]) -> BatchResult:
        """
        Process documents sequentially (one at a time).

        Pros:
        - Simple implementation
        - Easy error handling
        - Predictable resource usage

        Cons:
        - Slower for large batches
        - Underutilizes resources
        """
        print("\n" + "=" * 80)
        print("📝 SEQUENTIAL PROCESSING")
        print("=" * 80)

        start_time = time.time()
        results = []
        successful = 0
        failed = 0

        for i, file_path in enumerate(file_paths, 1):
            print(
                f"\n📄 Processing document {i}/{len(file_paths)}: {Path(file_path).name}"
            )

            try:
                result = self.agent.extract(
                    file_path=file_path,
                    extract_tables=False,
                    chunk_for_rag=False,
                )

                self.total_cost += result["cost"]
                successful += 1

                results.append(
                    {
                        "file_path": file_path,
                        "status": "success",
                        "cost": result["cost"],
                        "text_length": len(result["text"]),
                    }
                )

                print(
                    f"   ✅ Success: {len(result['text'])} chars, ${result['cost']:.3f}"
                )

            except Exception as e:
                failed += 1
                results.append(
                    {
                        "file_path": file_path,
                        "status": "failed",
                        "error": str(e),
                    }
                )
                print(f"   ❌ Failed: {str(e)}")

        total_time = time.time() - start_time

        print("\n📊 Sequential Processing Summary:")
        print(f"   Total documents: {len(file_paths)}")
        print(f"   Successful: {successful}")
        print(f"   Failed: {failed}")
        print(f"   Total time: {total_time:.2f}s")
        print(f"   Average time/doc: {total_time/len(file_paths):.2f}s")
        print(f"   Total cost: ${self.total_cost:.3f}")

        return BatchResult(
            total_documents=len(file_paths),
            successful=successful,
            failed=failed,
            total_cost=self.total_cost,
            total_time=total_time,
            documents=results,
        )

    async def process_parallel(
        self, file_paths: List[str], max_concurrent: int = 3
    ) -> BatchResult:
        """
        Process documents in parallel with concurrency limit.

        Pros:
        - Much faster for large batches
        - Better resource utilization
        - Scalable

        Cons:
        - More complex error handling
        - Requires async support
        - Higher peak resource usage
        """
        print("\n" + "=" * 80)
        print(f"⚡ PARALLEL PROCESSING (max {max_concurrent} concurrent)")
        print("=" * 80)

        start_time = time.time()
        results = []
        successful = 0
        failed = 0

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_one(file_path: str, index: int) -> Dict[str, Any]:
            """Process single document with semaphore."""
            async with semaphore:
                print(
                    f"\n📄 Starting document {index}/{len(file_paths)}: {Path(file_path).name}"
                )

                try:
                    # Note: In production, use async extraction if available
                    # For now, run sync extraction in executor
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None,
                        lambda: self.agent.extract(
                            file_path=file_path,
                            extract_tables=False,
                            chunk_for_rag=False,
                        ),
                    )

                    print(
                        f"   ✅ Completed {index}: {len(result['text'])} chars, ${result['cost']:.3f}"
                    )

                    return {
                        "file_path": file_path,
                        "status": "success",
                        "cost": result["cost"],
                        "text_length": len(result["text"]),
                    }

                except Exception as e:
                    print(f"   ❌ Failed {index}: {str(e)}")
                    return {
                        "file_path": file_path,
                        "status": "failed",
                        "error": str(e),
                    }

        # Create tasks for all documents
        tasks = [process_one(file_path, i) for i, file_path in enumerate(file_paths, 1)]

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successes and failures
        for result in results:
            if isinstance(result, Exception):
                failed += 1
            elif result["status"] == "success":
                successful += 1
                self.total_cost += result["cost"]
            else:
                failed += 1

        total_time = time.time() - start_time

        print("\n📊 Parallel Processing Summary:")
        print(f"   Total documents: {len(file_paths)}")
        print(f"   Successful: {successful}")
        print(f"   Failed: {failed}")
        print(f"   Total time: {total_time:.2f}s")
        print(f"   Average time/doc: {total_time/len(file_paths):.2f}s")
        print(f"   Total cost: ${self.total_cost:.3f}")
        print(
            f"   Speedup: {len(file_paths) / (total_time/len(file_paths)):.1f}x vs sequential"
        )

        return BatchResult(
            total_documents=len(file_paths),
            successful=successful,
            failed=failed,
            total_cost=self.total_cost,
            total_time=total_time,
            documents=[r for r in results if isinstance(r, dict)],
        )


def demonstrate_progress_tracking():
    """Demonstrate progress tracking in batch processing."""

    print("\n" + "=" * 80)
    print("📈 PROGRESS TRACKING DEMO")
    print("=" * 80)

    # Create test documents
    docs = create_test_documents(count=10)

    config = DocumentExtractionConfig(
        provider="ollama_vision",  # Use free provider for demo
    )

    agent = DocumentExtractionAgent(config=config)

    print(f"\n📄 Processing {len(docs)} documents with progress tracking...")

    start_time = time.time()
    processed = 0

    for i, doc_path in enumerate(docs, 1):
        # Process document
        result = agent.extract(doc_path, extract_tables=False, chunk_for_rag=False)

        processed += 1
        elapsed = time.time() - start_time
        avg_time = elapsed / processed
        remaining = (len(docs) - processed) * avg_time

        # Show progress bar
        progress = int((i / len(docs)) * 40)
        bar = "█" * progress + "░" * (40 - progress)

        print(
            f"\r   [{bar}] {i}/{len(docs)} ({i/len(docs)*100:.0f}%) | "
            f"Elapsed: {elapsed:.1f}s | Remaining: {remaining:.1f}s | "
            f"Avg: {avg_time:.2f}s/doc",
            end="",
            flush=True,
        )

    print("\n   ✅ All documents processed!")

    # Cleanup
    for doc in docs:
        os.unlink(doc)


def compare_batch_strategies():
    """Compare sequential vs. parallel batch processing."""

    print("\n" + "=" * 80)
    print("⚖️  BATCH STRATEGY COMPARISON")
    print("=" * 80)

    # Create test documents
    doc_count = 5
    print(f"\n📄 Creating {doc_count} test documents...")
    docs = create_test_documents(count=doc_count)

    config = DocumentExtractionConfig(
        provider="ollama_vision",  # Use free provider for fair comparison
    )

    # Test 1: Sequential processing
    processor_seq = BatchDocumentProcessor(config)
    result_seq = processor_seq.process_sequential(docs)

    # Test 2: Parallel processing
    processor_par = BatchDocumentProcessor(config)
    result_par = asyncio.run(processor_par.process_parallel(docs, max_concurrent=3))

    # Comparison
    print("\n" + "=" * 80)
    print("📊 COMPARISON RESULTS")
    print("=" * 80)

    speedup = (
        result_seq.total_time / result_par.total_time
        if result_par.total_time > 0
        else 0
    )

    print("\nSequential Processing:")
    print(f"   Time: {result_seq.total_time:.2f}s")
    print(
        f"   Throughput: {result_seq.total_documents/result_seq.total_time:.2f} docs/second"
    )

    print("\nParallel Processing:")
    print(f"   Time: {result_par.total_time:.2f}s")
    print(
        f"   Throughput: {result_par.total_documents/result_par.total_time:.2f} docs/second"
    )
    print(f"   Speedup: {speedup:.2f}x faster")

    print("\n💡 Recommendation:")
    if speedup > 1.5:
        print(f"   ✅ Use parallel processing for {doc_count}+ documents")
        print(f"   ✅ {speedup:.1f}x speedup justifies added complexity")
    else:
        print("   ⚠️  Sequential sufficient for small batches")
        print(f"   ⚠️  Parallel overhead not justified for {doc_count} documents")

    # Cleanup
    for doc in docs:
        os.unlink(doc)


def main():
    """Run all batch processing demonstrations."""

    print("=" * 80)
    print("🚀 BATCH DOCUMENT PROCESSING DEMO")
    print("=" * 80)

    # Demo 1: Progress tracking
    demonstrate_progress_tracking()

    # Demo 2: Strategy comparison
    compare_batch_strategies()

    print("\n" + "=" * 80)
    print("✨ BATCH PROCESSING DEMO COMPLETE")
    print("=" * 80)

    print("\n💡 Key Takeaways:")
    print("   1. Sequential: Simple, predictable, best for <10 documents")
    print("   2. Parallel: Faster, scalable, best for 10+ documents")
    print("   3. Progress tracking: Essential for user experience")
    print("   4. Error handling: Critical in batch operations")
    print("   5. Cost tracking: Monitor spending across batches")

    print("\n📚 Related Examples:")
    print("   - advanced_rag.py: Multi-document RAG workflows")
    print("   - cost_estimation_demo.py: Cost estimation patterns")
    print("   - workflow_integration.py: Async Core SDK patterns")


if __name__ == "__main__":
    main()
