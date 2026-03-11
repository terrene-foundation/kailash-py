"""
Performance benchmarking for memory storage backends.

Measures latency characteristics (p50, p95, p99) for FileStorage and SQLiteStorage
with varying dataset sizes to verify performance targets.

Targets:
- Retrieval: <50ms (p95)
- Storage: <100ms (p95)
"""

import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Tuple

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from kaizen.memory.storage.base import MemoryEntry, MemoryType
from kaizen.memory.storage.file_storage import FileStorage
from kaizen.memory.storage.sqlite_storage import SQLiteStorage


def percentile(data: List[float], p: float) -> float:
    """Calculate percentile of data."""
    sorted_data = sorted(data)
    index = int(len(sorted_data) * p)
    return sorted_data[min(index, len(sorted_data) - 1)]


def benchmark_storage_operations(storage_class, dataset_sizes: List[int]) -> dict:
    """
    Benchmark storage operations with varying dataset sizes.

    Args:
        storage_class: Storage backend class (FileStorage or SQLiteStorage)
        dataset_sizes: List of dataset sizes to test

    Returns:
        Dictionary with benchmark results
    """
    results = {
        "backend": storage_class.__name__,
        "datasets": {},
    }

    for size in dataset_sizes:
        print(f"\n  Testing {storage_class.__name__} with {size} entries...")

        # Create temporary storage
        with tempfile.TemporaryDirectory() as tmpdir:
            if storage_class == FileStorage:
                storage_path = Path(tmpdir) / "benchmark.jsonl"
            else:  # SQLiteStorage
                storage_path = Path(tmpdir) / "benchmark.db"

            storage = storage_class(str(storage_path))

            # Create test entries
            entries = [
                MemoryEntry(
                    content=f"Benchmark entry {i} with some content to make it realistic",
                    memory_type=MemoryType.LONG_TERM,
                    metadata={"benchmark": True, "index": i},
                    importance=0.5 + (i % 10) / 20,
                )
                for i in range(size)
            ]

            # Benchmark: Storage (write)
            storage_times = []
            for entry in entries:
                start = time.perf_counter()
                storage.store(entry)
                end = time.perf_counter()
                storage_times.append((end - start) * 1000)  # Convert to ms

            # Benchmark: Retrieval (read)
            retrieval_times = []
            for entry in entries:
                start = time.perf_counter()
                retrieved = storage.retrieve(entry.id)
                end = time.perf_counter()
                retrieval_times.append((end - start) * 1000)  # Convert to ms
                assert retrieved is not None

            # Benchmark: Search
            search_times = []
            search_queries = ["Benchmark", "entry", "content", "realistic"]
            for query in search_queries:
                start = time.perf_counter()
                results_list = storage.search(query, limit=10)
                end = time.perf_counter()
                search_times.append((end - start) * 1000)

            # Benchmark: List entries
            start = time.perf_counter()
            listed = storage.list_entries(limit=100)
            end = time.perf_counter()
            list_time = (end - start) * 1000

            # Benchmark: Count
            start = time.perf_counter()
            count = storage.count()
            end = time.perf_counter()
            count_time = (end - start) * 1000

            # Calculate statistics
            dataset_results = {
                "size": size,
                "storage": {
                    "mean": statistics.mean(storage_times),
                    "median": statistics.median(storage_times),
                    "p50": percentile(storage_times, 0.50),
                    "p95": percentile(storage_times, 0.95),
                    "p99": percentile(storage_times, 0.99),
                    "min": min(storage_times),
                    "max": max(storage_times),
                },
                "retrieval": {
                    "mean": statistics.mean(retrieval_times),
                    "median": statistics.median(retrieval_times),
                    "p50": percentile(retrieval_times, 0.50),
                    "p95": percentile(retrieval_times, 0.95),
                    "p99": percentile(retrieval_times, 0.99),
                    "min": min(retrieval_times),
                    "max": max(retrieval_times),
                },
                "search": {
                    "mean": statistics.mean(search_times),
                    "median": statistics.median(search_times),
                    "p95": percentile(search_times, 0.95),
                },
                "list": list_time,
                "count": count_time,
            }

            results["datasets"][size] = dataset_results

            # Print quick summary
            print(f"    Storage p95: {dataset_results['storage']['p95']:.2f}ms")
            print(f"    Retrieval p95: {dataset_results['retrieval']['p95']:.2f}ms")
            print(f"    Search p95: {dataset_results['search']['p95']:.2f}ms")

    return results


def verify_targets(results: dict) -> Tuple[bool, List[str]]:
    """
    Verify that performance targets are met.

    Targets:
    - Retrieval: <50ms (p95)
    - Storage: <100ms (p95)

    Args:
        results: Benchmark results dictionary

    Returns:
        (all_passed, violations) tuple
    """
    violations = []

    for size, dataset in results["datasets"].items():
        # Check retrieval target
        retrieval_p95 = dataset["retrieval"]["p95"]
        if retrieval_p95 > 50.0:
            violations.append(
                f"{results['backend']} retrieval p95 ({retrieval_p95:.2f}ms) "
                f"exceeds 50ms target for {size} entries"
            )

        # Check storage target
        storage_p95 = dataset["storage"]["p95"]
        if storage_p95 > 100.0:
            violations.append(
                f"{results['backend']} storage p95 ({storage_p95:.2f}ms) "
                f"exceeds 100ms target for {size} entries"
            )

    return len(violations) == 0, violations


def print_benchmark_report(all_results: List[dict]):
    """Print comprehensive benchmark report."""
    print("\n" + "=" * 80)
    print("STORAGE LAYER PERFORMANCE BENCHMARK REPORT")
    print("=" * 80)
    print("\nPerformance Targets:")
    print("  • Retrieval p95: <50ms")
    print("  • Storage p95: <100ms")

    for results in all_results:
        backend = results["backend"]
        print(f"\n{'-' * 80}")
        print(f"{backend} Performance Results")
        print(f"{'-' * 80}")

        for size, dataset in results["datasets"].items():
            print(f"\nDataset Size: {size:,} entries")
            print("\n  Storage Operations:")
            print(f"    Mean:   {dataset['storage']['mean']:>8.2f}ms")
            print(f"    Median: {dataset['storage']['median']:>8.2f}ms")
            print(f"    p50:    {dataset['storage']['p50']:>8.2f}ms")
            print(
                f"    p95:    {dataset['storage']['p95']:>8.2f}ms {'✅' if dataset['storage']['p95'] < 100 else '❌ TARGET MISS'}"
            )
            print(f"    p99:    {dataset['storage']['p99']:>8.2f}ms")
            print(f"    Min:    {dataset['storage']['min']:>8.2f}ms")
            print(f"    Max:    {dataset['storage']['max']:>8.2f}ms")

            print("\n  Retrieval Operations:")
            print(f"    Mean:   {dataset['retrieval']['mean']:>8.2f}ms")
            print(f"    Median: {dataset['retrieval']['median']:>8.2f}ms")
            print(f"    p50:    {dataset['retrieval']['p50']:>8.2f}ms")
            print(
                f"    p95:    {dataset['retrieval']['p95']:>8.2f}ms {'✅' if dataset['retrieval']['p95'] < 50 else '❌ TARGET MISS'}"
            )
            print(f"    p99:    {dataset['retrieval']['p99']:>8.2f}ms")
            print(f"    Min:    {dataset['retrieval']['min']:>8.2f}ms")
            print(f"    Max:    {dataset['retrieval']['max']:>8.2f}ms")

            print("\n  Search Operations:")
            print(f"    Mean:   {dataset['search']['mean']:>8.2f}ms")
            print(f"    Median: {dataset['search']['median']:>8.2f}ms")
            print(f"    p95:    {dataset['search']['p95']:>8.2f}ms")

            print("\n  Other Operations:")
            print(f"    List (100):  {dataset['list']:>8.2f}ms")
            print(f"    Count:       {dataset['count']:>8.2f}ms")

    # Verify targets
    print(f"\n{'=' * 80}")
    print("TARGET VERIFICATION")
    print(f"{'=' * 80}")

    all_passed = True
    for results in all_results:
        passed, violations = verify_targets(results)
        all_passed = all_passed and passed

        if passed:
            print(f"\n✅ {results['backend']}: All targets met")
        else:
            print(f"\n❌ {results['backend']}: Target violations found:")
            for violation in violations:
                print(f"   - {violation}")

    # Overall result
    print(f"\n{'=' * 80}")
    if all_passed:
        print("✅ ALL PERFORMANCE TARGETS MET")
    else:
        print("❌ SOME PERFORMANCE TARGETS MISSED")
    print(f"{'=' * 80}\n")

    return all_passed


def main():
    """Run storage backend benchmarks."""
    print("Starting Memory Storage Layer Performance Benchmarks...")
    print("This will test FileStorage and SQLiteStorage with dataset sizes:")
    print("  • 100 entries")
    print("  • 500 entries")
    print("  • 1,000 entries")

    dataset_sizes = [100, 500, 1000]

    # Benchmark FileStorage
    print("\n" + "=" * 80)
    print("Benchmarking FileStorage")
    print("=" * 80)
    file_results = benchmark_storage_operations(FileStorage, dataset_sizes)

    # Benchmark SQLiteStorage
    print("\n" + "=" * 80)
    print("Benchmarking SQLiteStorage")
    print("=" * 80)
    sqlite_results = benchmark_storage_operations(SQLiteStorage, dataset_sizes)

    # Print comprehensive report
    all_results = [file_results, sqlite_results]
    all_passed = print_benchmark_report(all_results)

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
