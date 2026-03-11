"""Example 3: Batch Error Analysis with Debug Agent

This example demonstrates processing multiple errors from log files for
batch analysis and report generation.

Usage:
    python examples/debug_agent/03_batch_error_analysis.py
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector


def create_sample_error_log():
    """Create sample error log for demonstration."""
    errors = [
        "ValueError: Missing required parameter 'id' in CreateNode",
        "ValueError: Source node 'create_user' not found in workflow",
        "TypeError: expected int, got str '25'",
        "IntegrityError: duplicate key value violates unique constraint 'users_email_key'",
        "OperationalError: no such table: users",
        "ValueError: Missing required parameter 'id' in CreateNode",  # Duplicate
        "RuntimeError: Event loop is closed",
        "ValueError: cannot manually set 'created_at' - auto-managed field",
        "TimeoutError: query canceled due to statement timeout",
        "ValueError: UPDATE request must contain 'filter' field",
    ]

    log_file = Path("sample_errors.log")
    with open(log_file, "w") as f:
        for error in errors:
            f.write(f"[ERROR] {error}\n")

    return log_file


def analyze_error_batch(log_file: Path, output_dir: Path):
    """Analyze batch of errors from log file."""
    # Initialize DataFlow and Debug Agent
    db = DataFlow(":memory:")

    @db.model
    class User:
        id: str
        name: str

    kb = KnowledgeBase(
        "src/dataflow/debug/patterns.yaml", "src/dataflow/debug/solutions.yaml"
    )
    inspector = Inspector(db)
    agent = DebugAgent(kb, inspector)

    # Create output directory
    output_dir.mkdir(exist_ok=True)

    # Parse error log
    print(f"Reading errors from: {log_file}")
    with open(log_file, "r") as f:
        error_lines = [line.strip()[8:] for line in f if "[ERROR]" in line]

    print(f"Found {len(error_lines)} errors")
    print()

    # Analyze each error
    reports = []
    category_counts = Counter()
    total_execution_time = 0

    for i, error_message in enumerate(error_lines, 1):
        print(f"Analyzing error {i}/{len(error_lines)}...")

        # Debug from string
        report = agent.debug_from_string(
            error_message, error_type="RuntimeError", max_solutions=3, min_relevance=0.5
        )

        # Collect statistics
        category_counts[report.error_category.category] += 1
        total_execution_time += report.execution_time

        # Export to JSON
        output_file = output_dir / f"report_{i:03d}.json"
        with open(output_file, "w") as f:
            f.write(report.to_json())

        reports.append(report.to_dict())

        print(f"  Category: {report.error_category.category}")
        print(f"  Confidence: {report.error_category.confidence * 100:.0f}%")
        print(f"  Solutions: {len(report.suggested_solutions)}")
        print()

    # Generate summary report
    summary = {
        "analysis_date": datetime.now().isoformat(),
        "total_errors": len(reports),
        "category_breakdown": dict(category_counts),
        "average_execution_time_ms": total_execution_time / len(reports),
        "total_execution_time_ms": total_execution_time,
        "reports": [
            {
                "error_message": r["captured_error"]["message"],
                "category": r["error_category"]["category"],
                "confidence": r["error_category"]["confidence"],
                "solutions_count": len(r["suggested_solutions"]),
            }
            for r in reports
        ],
    }

    # Save summary
    summary_file = output_dir / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


def main():
    """Batch error analysis example."""
    print("=" * 80)
    print("Example 3: Batch Error Analysis")
    print("=" * 80)
    print()

    # Create sample error log
    log_file = create_sample_error_log()
    print(f"Created sample error log: {log_file}")
    print()

    # Analyze errors
    output_dir = Path("debug_reports")
    summary = analyze_error_batch(log_file, output_dir)

    # Display summary
    print("=" * 80)
    print("Analysis Summary")
    print("=" * 80)
    print(f"Total Errors: {summary['total_errors']}")
    print(f"Average Execution Time: {summary['average_execution_time_ms']:.1f}ms")
    print()

    print("Category Breakdown:")
    for category, count in summary["category_breakdown"].items():
        percentage = (count / summary["total_errors"]) * 100
        print(f"  {category}: {count} ({percentage:.1f}%)")
    print()

    print(f"Output directory: {output_dir}")
    print(f"Summary report: {output_dir / 'summary.json'}")

    # Cleanup
    log_file.unlink()


if __name__ == "__main__":
    main()
