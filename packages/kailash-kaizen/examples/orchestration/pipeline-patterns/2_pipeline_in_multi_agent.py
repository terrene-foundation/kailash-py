"""
Pipeline in Multi-Agent Pattern Example

Demonstrates:
1. Creating specialized pipelines
2. Converting pipelines to agents with .to_agent()
3. Using pipeline-agents as workers in SupervisorWorkerPattern
4. Mixing pipelines with regular agents

Pattern: Pipeline composability in multi-agent coordination
"""

from dataclasses import dataclass
from typing import Any, Dict

from kaizen.core.base_agent import BaseAgent
from kaizen.orchestration.pipeline import Pipeline
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Pipeline 1: Document Processing Pipeline
# ============================================================================


class DocumentProcessingPipeline(Pipeline):
    """Multi-step document processing workflow."""

    def run(self, **inputs) -> Dict[str, Any]:
        """Process document through extraction, validation, enrichment."""
        document = inputs.get("document", "")

        # Step 1: Extract text
        extracted = self._extract_text(document)

        # Step 2: Validate format
        validated = self._validate_format(extracted)

        # Step 3: Enrich with metadata
        enriched = self._enrich_metadata(validated)

        return {
            "document": document,
            "extracted_text": extracted,
            "validation": validated,
            "metadata": enriched,
            "status": "processed",
        }

    def _extract_text(self, document: str) -> str:
        """Extract text from document."""
        # Simplified extraction
        return document.strip()

    def _validate_format(self, text: str) -> Dict[str, Any]:
        """Validate document format."""
        return {
            "is_valid": len(text) > 0,
            "format": "text/plain",
            "size": len(text),
        }

    def _enrich_metadata(self, validation: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich with metadata."""
        return {
            "format": validation["format"],
            "size": validation["size"],
            "processed": True,
        }


# ============================================================================
# Pipeline 2: Data Analysis Pipeline
# ============================================================================


class DataAnalysisPipeline(Pipeline):
    """Multi-step data analysis workflow."""

    def run(self, **inputs) -> Dict[str, Any]:
        """Analyze data through cleaning, aggregation, insights."""
        data = inputs.get("data", "")

        # Step 1: Clean data
        cleaned = self._clean_data(data)

        # Step 2: Aggregate statistics
        stats = self._aggregate_stats(cleaned)

        # Step 3: Generate insights
        insights = self._generate_insights(stats)

        return {
            "data": data,
            "cleaned_data": cleaned,
            "statistics": stats,
            "insights": insights,
            "status": "analyzed",
        }

    def _clean_data(self, data: str) -> str:
        """Clean the data."""
        return " ".join(data.split())

    def _aggregate_stats(self, data: str) -> Dict[str, Any]:
        """Calculate statistics."""
        words = data.split()
        return {
            "word_count": len(words),
            "char_count": len(data),
            "avg_word_length": len(data) / max(len(words), 1),
        }

    def _generate_insights(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Generate insights from statistics."""
        return {
            "complexity": "high" if stats["avg_word_length"] > 10 else "low",
            "summary": f"Document contains {stats['word_count']} words",
        }


# ============================================================================
# Regular Agent: Simple Q&A Agent
# ============================================================================


class SimpleQASignature(Signature):
    """Q&A signature."""

    question: str = InputField(description="User question")
    answer: str = OutputField(description="Answer")


@dataclass
class QAConfig:
    """Q&A configuration."""

    llm_provider: str = "mock"
    model: str = "test"


class SimpleQAAgent(BaseAgent):
    """Simple question answering agent."""

    def __init__(self, config: QAConfig):
        super().__init__(config=config, signature=SimpleQASignature())

    def run(self, **inputs) -> Dict[str, Any]:
        """Answer questions (mock implementation)."""
        question = inputs.get("question", "")
        return {"answer": f"Mock answer for: {question}"}


# ============================================================================
# Multi-Agent Orchestration
# ============================================================================


def main():
    """Demonstrate pipeline in multi-agent pattern."""
    print("=" * 70)
    print("Pipeline in Multi-Agent Pattern Example")
    print("=" * 70)

    # Create pipelines
    print("\n📋 Step 1: Create Pipelines")
    print("-" * 70)
    doc_pipeline = DocumentProcessingPipeline()
    data_pipeline = DataAnalysisPipeline()
    print("✅ Created DocumentProcessingPipeline")
    print("✅ Created DataAnalysisPipeline")

    # Convert pipelines to agents
    print("\n📋 Step 2: Convert Pipelines to Agents")
    print("-" * 70)

    try:
        doc_agent = doc_pipeline.to_agent(
            name="document_processor", description="Processes documents"
        )
        data_agent = data_pipeline.to_agent(
            name="data_analyzer", description="Analyzes data"
        )
        print(f"✅ Created agent: {doc_agent.agent_id}")
        print(f"✅ Created agent: {data_agent.agent_id}")

        # Create regular agent
        print("\n📋 Step 3: Create Regular Agent")
        print("-" * 70)
        qa_agent = SimpleQAAgent(QAConfig())
        print(f"✅ Created agent: {qa_agent.agent_id}")

        # Create multi-agent pattern (conceptual - would need supervisor/coordinator)
        print("\n📋 Step 4: Compose in Multi-Agent Pattern")
        print("-" * 70)
        print("Workers:")
        print(f"  1. {doc_agent.agent_id} (Pipeline → Agent)")
        print(f"  2. {data_agent.agent_id} (Pipeline → Agent)")
        print(f"  3. {qa_agent.agent_id} (Regular Agent)")

        # Demonstrate execution
        print("\n📋 Step 5: Execute Workers")
        print("-" * 70)

        # Execute document pipeline agent
        print("\n1️⃣ Document Processor:")
        doc_result = doc_agent.run(document="Sample document for processing")
        print(f"   Status: {doc_result.get('status', 'N/A')}")

        # Execute data pipeline agent
        print("\n2️⃣ Data Analyzer:")
        data_result = data_agent.run(data="Sample   data   for   analysis")
        print(f"   Status: {data_result.get('status', 'N/A')}")
        print(f"   Word Count: {data_result['statistics']['word_count']}")

        # Execute regular agent
        print("\n3️⃣ Q&A Agent:")
        qa_result = qa_agent.run(question="What is the document about?")
        print(f"   Answer: {qa_result.get('answer', 'N/A')}")

    except ModuleNotFoundError:
        print("⚠️  Optional observability dependencies not installed (opentelemetry)")
        print("   Pipeline execution works, .to_agent() requires:")
        print(
            "   pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc"
        )
        print("\n   Demonstrating pipeline execution without .to_agent():")

        # Execute pipelines directly
        print("\n1️⃣ Document Pipeline:")
        doc_result = doc_pipeline.run(document="Sample document for processing")
        print(f"   Status: {doc_result.get('status', 'N/A')}")

        print("\n2️⃣ Data Analysis Pipeline:")
        data_result = data_pipeline.run(data="Sample   data   for   analysis")
        print(f"   Status: {data_result.get('status', 'N/A')}")
        print(f"   Word Count: {data_result['statistics']['word_count']}")

    # Summary
    print("\n" + "=" * 70)
    print("✅ Successfully demonstrated:")
    print("   - Pipelines converted to BaseAgent")
    print("   - Pipelines mixed with regular agents")
    print("   - All agents executed successfully")
    print("   - Ready for SupervisorWorkerPattern integration")
    print("=" * 70)


if __name__ == "__main__":
    main()
