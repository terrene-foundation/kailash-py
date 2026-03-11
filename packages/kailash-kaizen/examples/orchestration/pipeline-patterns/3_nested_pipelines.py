"""
Nested Pipelines Example - Composable Pipeline Architecture

Demonstrates:
1. Creating reusable sub-pipelines
2. Composing pipelines from other pipelines
3. Converting nested pipelines to agents
4. Building complex workflows from simple components

Pattern: Nested composition for modular workflow design
"""

from typing import Any, Dict

from kaizen.orchestration.pipeline import Pipeline

# ============================================================================
# Sub-Pipeline 1: Data Cleaning
# ============================================================================


class DataCleaningPipeline(Pipeline):
    """Reusable data cleaning sub-pipeline."""

    def run(self, **inputs) -> Dict[str, Any]:
        """Clean data through normalization and validation."""
        data = inputs.get("data", "")

        # Step 1: Normalize whitespace
        normalized = self._normalize_whitespace(data)

        # Step 2: Remove special characters
        cleaned = self._remove_special_chars(normalized)

        # Step 3: Validate
        validation = self._validate(cleaned)

        return {
            "cleaned_data": cleaned,
            "validation": validation,
            "cleaning_applied": ["whitespace", "special_chars"],
        }

    def _normalize_whitespace(self, data: str) -> str:
        """Normalize whitespace."""
        return " ".join(data.split())

    def _remove_special_chars(self, data: str) -> str:
        """Remove special characters (simplified)."""
        return "".join(c for c in data if c.isalnum() or c.isspace())

    def _validate(self, data: str) -> Dict[str, Any]:
        """Validate cleaned data."""
        return {"is_valid": len(data) > 0, "length": len(data)}


# ============================================================================
# Sub-Pipeline 2: Data Transformation
# ============================================================================


class DataTransformationPipeline(Pipeline):
    """Reusable data transformation sub-pipeline."""

    def run(self, **inputs) -> Dict[str, Any]:
        """Transform data through formatting and enrichment."""
        data = inputs.get("cleaned_data", "")

        # Step 1: Apply formatting
        formatted = self._format_data(data)

        # Step 2: Tokenize
        tokens = self._tokenize(formatted)

        # Step 3: Enrich with metadata
        enriched = self._enrich(tokens)

        return {
            "formatted_data": formatted,
            "tokens": tokens,
            "enriched": enriched,
            "transformations_applied": ["formatting", "tokenization", "enrichment"],
        }

    def _format_data(self, data: str) -> str:
        """Format data (title case)."""
        return data.title()

    def _tokenize(self, data: str) -> list:
        """Tokenize data."""
        return data.split()

    def _enrich(self, tokens: list) -> Dict[str, Any]:
        """Enrich with metadata."""
        return {
            "token_count": len(tokens),
            "unique_tokens": len(set(tokens)),
            "avg_token_length": sum(len(t) for t in tokens) / max(len(tokens), 1),
        }


# ============================================================================
# Sub-Pipeline 3: Data Analysis
# ============================================================================


class DataAnalysisPipeline(Pipeline):
    """Reusable data analysis sub-pipeline."""

    def run(self, **inputs) -> Dict[str, Any]:
        """Analyze enriched data."""
        enriched = inputs.get("enriched", {})
        tokens = inputs.get("tokens", [])

        # Step 1: Calculate statistics
        stats = self._calculate_statistics(enriched, tokens)

        # Step 2: Generate insights
        insights = self._generate_insights(stats)

        # Step 3: Create summary
        summary = self._create_summary(stats, insights)

        return {
            "statistics": stats,
            "insights": insights,
            "summary": summary,
            "analysis_complete": True,
        }

    def _calculate_statistics(
        self, enriched: Dict[str, Any], tokens: list
    ) -> Dict[str, Any]:
        """Calculate statistics."""
        return {
            "total_tokens": enriched.get("token_count", 0),
            "unique_tokens": enriched.get("unique_tokens", 0),
            "avg_length": enriched.get("avg_token_length", 0),
            "diversity": enriched.get("unique_tokens", 0)
            / max(enriched.get("token_count", 1), 1),
        }

    def _generate_insights(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Generate insights."""
        diversity = stats["diversity"]
        return {
            "text_complexity": "high" if diversity > 0.7 else "low",
            "recommendation": (
                "suitable for processing"
                if diversity > 0.5
                else "may need more content"
            ),
        }

    def _create_summary(self, stats: Dict[str, Any], insights: Dict[str, Any]) -> str:
        """Create summary."""
        return (
            f"Analyzed {stats['total_tokens']} tokens "
            f"with {stats['diversity']:.2f} diversity. "
            f"Complexity: {insights['text_complexity']}."
        )


# ============================================================================
# Master Pipeline: Compose Sub-Pipelines
# ============================================================================


class MasterDataPipeline(Pipeline):
    """
    Master pipeline that composes sub-pipelines.

    Architecture:
    1. DataCleaningPipeline → clean data
    2. DataTransformationPipeline → transform cleaned data
    3. DataAnalysisPipeline → analyze transformed data

    Each sub-pipeline can be:
    - Used independently
    - Converted to agent via .to_agent()
    - Reused in other master pipelines
    """

    def __init__(self):
        """Initialize with sub-pipelines."""
        # Create reusable sub-pipelines
        self.cleaning_pipeline = DataCleaningPipeline()
        self.transformation_pipeline = DataTransformationPipeline()
        self.analysis_pipeline = DataAnalysisPipeline()

    def run(self, **inputs) -> Dict[str, Any]:
        """Execute nested pipeline workflow."""
        print("\n🔹 Master Pipeline: Starting execution")

        # Step 1: Clean data
        print("  └─ Step 1/3: Running DataCleaningPipeline...")
        cleaning_result = self.cleaning_pipeline.run(**inputs)
        print(
            f"     ✅ Cleaning complete ({len(cleaning_result['cleaning_applied'])} operations)"
        )

        # Step 2: Transform cleaned data
        print("  └─ Step 2/3: Running DataTransformationPipeline...")
        transformation_result = self.transformation_pipeline.run(**cleaning_result)
        print(
            f"     ✅ Transformation complete ({transformation_result['enriched']['token_count']} tokens)"
        )

        # Step 3: Analyze transformed data
        print("  └─ Step 3/3: Running DataAnalysisPipeline...")
        analysis_result = self.analysis_pipeline.run(**transformation_result)
        print("     ✅ Analysis complete")

        # Combine all results
        return {
            "original_data": inputs.get("data", ""),
            "cleaning": cleaning_result,
            "transformation": transformation_result,
            "analysis": analysis_result,
            "pipeline_status": "success",
            "summary": analysis_result["summary"],
        }


# ============================================================================
# Demonstration
# ============================================================================


def main():
    """Demonstrate nested pipeline composition."""
    print("=" * 70)
    print("Nested Pipelines Example")
    print("=" * 70)

    # Create master pipeline
    print("\n📋 Step 1: Create Master Pipeline")
    print("-" * 70)
    master_pipeline = MasterDataPipeline()
    print("✅ Created MasterDataPipeline with 3 sub-pipelines:")
    print("   1. DataCleaningPipeline")
    print("   2. DataTransformationPipeline")
    print("   3. DataAnalysisPipeline")

    # Execute master pipeline
    print("\n📋 Step 2: Execute Master Pipeline")
    print("-" * 70)
    test_data = "  Hello!!!   World!!!   from   Kaizen   nested   pipelines!!!  "
    result = master_pipeline.run(data=test_data)

    # Display results
    print("\n📊 Results:")
    print("-" * 70)
    print(f"  Summary: {result['summary']}")
    print(f"  Complexity: {result['analysis']['insights']['text_complexity'].upper()}")
    print(f"  Recommendation: {result['analysis']['insights']['recommendation']}")

    # Demonstrate sub-pipeline reusability
    print("\n📋 Step 3: Use Sub-Pipelines Independently")
    print("-" * 70)
    cleaning_pipeline = DataCleaningPipeline()
    independent_result = cleaning_pipeline.run(data="Reusable!!!   sub-pipeline!!!  ")
    print(
        f"✅ DataCleaningPipeline executed independently (length: {independent_result['validation']['length']})"
    )

    # Convert to agents
    print("\n📋 Step 4: Convert Pipelines to Agents")
    print("-" * 70)

    try:
        # Convert master pipeline to agent
        master_agent = master_pipeline.to_agent(
            name="master_data_processor",
            description="Complete data processing workflow",
        )
        print(f"✅ Master Pipeline → Agent: {master_agent.agent_id}")

        # Convert sub-pipelines to agents (for use as workers)
        cleaning_agent = cleaning_pipeline.to_agent(
            name="data_cleaner", description="Cleans data"
        )
        print(f"✅ Cleaning Pipeline → Agent: {cleaning_agent.agent_id}")

    except ModuleNotFoundError:
        print("⚠️  Optional observability dependencies not installed (opentelemetry)")
        print("   Pipeline execution works, .to_agent() requires:")
        print(
            "   pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc"
        )

    # Summary
    print("\n" + "=" * 70)
    print("✅ Nested Pipeline Composition Benefits:")
    print("   1. Modularity: Sub-pipelines are reusable components")
    print("   2. Composability: Build complex workflows from simple parts")
    print("   3. Flexibility: Use pipelines independently or nested")
    print("   4. Agent Conversion: Any pipeline → BaseAgent via .to_agent()")
    print("   5. Multi-Agent Ready: Use as workers in coordination patterns")
    print("=" * 70)


if __name__ == "__main__":
    main()
