"""
Basic Pipeline Example - Composable Multi-Step Workflow

Demonstrates:
1. Creating a custom Pipeline with multi-step processing
2. Converting Pipeline to BaseAgent with .to_agent()
3. Using the pipeline-agent in other contexts

Pattern: Pipeline → Agent conversion for composability
"""

from typing import Any, Dict

from kaizen.orchestration.pipeline import Pipeline


class DataProcessingPipeline(Pipeline):
    """
    Multi-step data processing pipeline.

    Steps:
    1. Clean data (remove nulls, normalize)
    2. Transform data (apply business rules)
    3. Enrich data (add metadata)
    4. Validate data (quality checks)
    """

    def run(self, **inputs) -> Dict[str, Any]:
        """Execute the pipeline steps."""
        raw_data = inputs.get("data", "")

        # Step 1: Clean
        cleaned = self._clean_data(raw_data)
        print(
            f"✅ Step 1/4: Cleaned data (removed {len(raw_data) - len(cleaned)} chars)"
        )

        # Step 2: Transform
        transformed = self._transform_data(cleaned)
        print("✅ Step 2/4: Transformed data (applied business rules)")

        # Step 3: Enrich
        enriched = self._enrich_data(transformed)
        print("✅ Step 3/4: Enriched data (added metadata)")

        # Step 4: Validate
        validation = self._validate_data(enriched)
        print(
            f"✅ Step 4/4: Validated data (quality score: {validation['quality_score']})"
        )

        return {
            "original": raw_data,
            "cleaned": cleaned,
            "transformed": transformed,
            "enriched": enriched,
            "validation": validation,
            "status": "success",
        }

    def _clean_data(self, data: str) -> str:
        """Clean the data by removing extra whitespace and normalizing."""
        return " ".join(data.split())

    def _transform_data(self, data: str) -> str:
        """Apply business rules transformation."""
        # Example: Convert to title case
        return data.title()

    def _enrich_data(self, text: str) -> Dict[str, Any]:
        """Enrich with metadata."""
        return {
            "data": text,
            "word_count": len(text.split()),
            "char_count": len(text),
            "language": "en",
        }

    def _validate_data(self, enriched: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data quality."""
        quality_score = min(1.0, enriched["word_count"] / 100)  # Arbitrary scoring

        return {
            "is_valid": True,
            "quality_score": quality_score,
            "checks_passed": ["length", "format", "content"],
        }


def main():
    """Demonstrate basic pipeline usage."""
    print("=" * 60)
    print("Basic Pipeline Example")
    print("=" * 60)

    # Create pipeline
    pipeline = DataProcessingPipeline()

    # Use pipeline directly
    print("\n📋 Option 1: Execute pipeline directly")
    print("-" * 60)
    result = pipeline.run(data="  hello   world  from   kaizen   pipeline  ")

    print("\n📊 Results:")
    print(f"  Status: {result['status']}")
    print(f"  Quality Score: {result['validation']['quality_score']:.2f}")
    print(f"  Word Count: {result['enriched']['word_count']}")

    # Convert to agent for composability
    print("\n📋 Option 2: Convert to BaseAgent")
    print("-" * 60)

    try:
        agent = pipeline.to_agent(
            name="data_processor", description="Processes and validates data"
        )

        print(f"✅ Created agent: {agent.agent_id}")
        print(f"   Description: {agent.description}")
        print(f"   Type: {type(agent).__name__}")

        # Now the pipeline can be used anywhere a BaseAgent is expected:
        # - In multi-agent patterns (SupervisorWorkerPattern)
        # - In other pipelines (nested composition)
        # - In workflows (integration with Core SDK)

        print("\n✅ Pipeline successfully converted to agent!")
        print("   Can now be used in:")
        print("   - SupervisorWorkerPattern (as a worker)")
        print("   - Other pipelines (nested composition)")
        print("   - Workflows (Core SDK integration)")

    except ModuleNotFoundError:
        print("⚠️  Optional observability dependencies not installed (opentelemetry)")
        print("   Pipeline execution works, .to_agent() requires:")
        print(
            "   pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc"
        )
        print("\n   Pipeline can still be used:")
        print("   - Direct execution: pipeline.run(...)")
        print("   - Nested in other pipelines")
        print("   - Composed with SequentialPipeline")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
