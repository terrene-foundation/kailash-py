"""
Production Monitoring

Demonstrates cost tracking, metrics collection, and monitoring patterns.
"""

import tempfile
from dataclasses import dataclass, field
from typing import Dict, List

from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)


@dataclass
class ExtractionMetrics:
    """Production metrics tracker."""

    total_documents: int = 0
    total_cost: float = 0.0
    provider_usage: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def record(self, result: dict):
        """Record extraction result."""
        self.total_documents += 1
        self.total_cost += result["cost"]
        provider = result["provider"]
        self.provider_usage[provider] = self.provider_usage.get(provider, 0) + 1

    def report(self):
        """Generate metrics report."""
        return {
            "total_documents": self.total_documents,
            "total_cost": self.total_cost,
            "avg_cost": (
                self.total_cost / self.total_documents
                if self.total_documents > 0
                else 0
            ),
            "provider_usage": self.provider_usage,
            "error_count": len(self.errors),
        }


def main():
    """Demonstrate production monitoring."""
    print("=" * 70)
    print("Production Monitoring Demo")
    print("=" * 70)

    # Initialize with cost tracking
    config = DocumentExtractionConfig(
        provider="ollama_vision",  # Free for demo
    )
    agent = DocumentExtractionAgent(config=config)
    metrics = ExtractionMetrics()

    # Process documents
    print("\nProcessing documents with monitoring...")
    for i in range(3):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write(f"Document #{i+1} content here")
            doc_path = tmp.name

        try:
            result = agent.extract(doc_path, extract_tables=False, chunk_for_rag=False)
            metrics.record(result)
            print(f"  ✅ Document {i+1}: ${result['cost']:.3f}")
        except Exception as e:
            metrics.errors.append(str(e))
            print(f"  ❌ Document {i+1}: {str(e)}")

        import os

        os.unlink(doc_path)

    # Show metrics
    print("\n" + "=" * 70)
    print("Production Metrics")
    print("=" * 70)

    report = metrics.report()
    print(f"\nDocuments processed: {report['total_documents']}")
    print(f"Total cost: ${report['total_cost']:.3f}")
    print(f"Average cost: ${report['avg_cost']:.3f}")
    print(f"Errors: {report['error_count']}")
    print("\nProvider usage:")
    for provider, count in report["provider_usage"].items():
        print(f"  {provider}: {count} documents")

    print("\n" + "=" * 70)
    print("Monitor these metrics in production dashboards")
    print("=" * 70)


if __name__ == "__main__":
    main()
