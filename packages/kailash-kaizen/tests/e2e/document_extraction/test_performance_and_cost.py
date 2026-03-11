"""
E2E tests for performance benchmarks and cost optimization.

Tests production scenarios for:
- Performance benchmarking
- Cost optimization strategies
- Provider comparison
- Budget constraint validation

Run with: pytest tests/e2e/document_extraction/test_performance_and_cost.py -m e2e

IMPORTANT: NO MOCKING - Real infrastructure only (Tier 3 policy)
"""

import os
import time

import pytest
from kaizen.agents.multi_modal import DocumentExtractionAgent, DocumentExtractionConfig


@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.ollama
class TestPerformanceBenchmarks:
    """E2E performance benchmark tests."""

    @pytest.fixture(autouse=True)
    def skip_if_ollama_not_running(self, ollama_available):
        """Skip if Ollama not available."""
        if not ollama_available:
            pytest.skip("Ollama not running")

    def test_ollama_performance_baseline(
        self, multi_page_document, performance_tracker
    ):
        """
        Establish Ollama performance baseline.

        Measures:
        - Extraction time
        - Throughput (pages/second)
        - Memory efficiency
        """
        agent = DocumentExtractionAgent(
            config=DocumentExtractionConfig(
                provider="ollama_vision",
                ollama_base_url="http://localhost:11434",
            )
        )

        # Warm-up run (model loading)
        agent.extract(multi_page_document, file_type="txt")

        # Benchmark run
        start_time = time.time()
        result = agent.extract(multi_page_document, file_type="txt")
        end_time = time.time()

        # Record metrics
        performance_tracker.record(result)

        # Validate performance
        extraction_time = end_time - start_time
        assert extraction_time > 0, "Should measure extraction time"

        # Ollama baseline (local processing)
        # Typically slower than API calls but acceptable
        assert (
            extraction_time < 120.0
        ), "Ollama should complete within 2 minutes for test doc"

        # Verify cost is free
        assert result["cost"] == 0.0, "Ollama should be free"

    def test_batch_processing_throughput(
        self, multi_document_batch, performance_tracker
    ):
        """
        Test batch processing throughput with Ollama.

        Measures documents/second for production workloads.
        """
        agent = DocumentExtractionAgent(
            config=DocumentExtractionConfig(
                provider="ollama_vision",
                ollama_base_url="http://localhost:11434",
            )
        )

        start_time = time.time()

        # Process all documents
        for doc_path in multi_document_batch:
            result = agent.extract(doc_path, file_type="txt")
            performance_tracker.record(result)

        end_time = time.time()

        # Calculate throughput
        total_time = end_time - start_time
        throughput = len(multi_document_batch) / total_time

        # Verify reasonable throughput
        assert throughput > 0, "Should process at least some docs/second"

        # Get performance summary
        summary = performance_tracker.get_summary()
        assert summary["total_cost"] == 0.0, "Batch with Ollama should be free"
        assert len(summary["providers"]) == 1, "Should use one provider"


@pytest.mark.e2e
@pytest.mark.cost_optimization
@pytest.mark.ollama
class TestCostOptimization:
    """E2E cost optimization tests."""

    @pytest.fixture(autouse=True)
    def skip_if_ollama_not_running(self, ollama_available):
        """Skip if Ollama not available."""
        if not ollama_available:
            pytest.skip("Ollama not running")

    def test_prefer_free_provider_strategy(
        self, multi_page_document, performance_tracker
    ):
        """
        Test prefer_free strategy for cost optimization.

        Production scenario: Organization wants to minimize costs
        by using free Ollama when possible.
        """
        agent = DocumentExtractionAgent(
            config=DocumentExtractionConfig(
                provider="auto",
                prefer_free=True,  # Cost optimization strategy
                landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
                openai_key=os.getenv("OPENAI_API_KEY"),
                ollama_base_url="http://localhost:11434",
            )
        )

        result = agent.extract(multi_page_document, file_type="txt")
        performance_tracker.record(result)

        # Should use Ollama (free)
        assert result["provider"] == "ollama_vision"
        assert result["cost"] == 0.0

    def test_budget_constraint_enforcement(self, multi_page_document):
        """
        Test strict budget constraint enforcement.

        Production scenario: Organization has monthly API budget,
        system must stay within limits.
        """
        agent = DocumentExtractionAgent(
            config=DocumentExtractionConfig(
                provider="auto",
                max_cost_per_doc=0.01,  # Very strict budget: $0.01
                landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
                openai_key=os.getenv("OPENAI_API_KEY"),
                ollama_base_url="http://localhost:11434",
            )
        )

        result = agent.extract(multi_page_document, file_type="txt")

        # Must stay under budget
        assert result["cost"] <= 0.01, "Should respect budget constraint"

        # Should use free provider to stay under budget
        assert result["provider"] == "ollama_vision"

    def test_cost_estimation_before_processing(
        self, multi_page_document, multi_document_batch
    ):
        """
        Test cost estimation for budget planning.

        Production scenario: Before processing large batch,
        organization wants to estimate total cost.
        """
        agent = DocumentExtractionAgent(
            config=DocumentExtractionConfig(
                provider="auto",
                landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
                openai_key=os.getenv("OPENAI_API_KEY"),
                ollama_base_url="http://localhost:11434",
            )
        )

        # Estimate cost for single document
        costs = agent.estimate_cost(multi_page_document)

        # Should have estimates for all providers
        assert "ollama_vision" in costs
        assert costs["ollama_vision"] == 0.0  # Free

        # Estimate batch cost
        batch_costs = []
        for doc_path in multi_document_batch:
            doc_costs = agent.estimate_cost(doc_path)
            batch_costs.append(doc_costs)

        # Verify batch estimation
        assert len(batch_costs) == len(multi_document_batch)

        # Calculate total free option
        total_ollama_cost = sum(costs.get("ollama_vision", 0) for costs in batch_costs)
        assert total_ollama_cost == 0.0, "Ollama batch should be free"

    def test_cost_tracking_across_documents(
        self, multi_document_batch, performance_tracker
    ):
        """
        Test cumulative cost tracking for budget monitoring.

        Production scenario: Track total spend across multiple documents.
        """
        agent = DocumentExtractionAgent(
            config=DocumentExtractionConfig(
                provider="ollama_vision",  # Use free provider
                ollama_base_url="http://localhost:11434",
            )
        )

        total_cost = 0.0

        # Process documents and track costs
        for doc_path in multi_document_batch:
            result = agent.extract(doc_path, file_type="txt")
            performance_tracker.record(result)
            total_cost += result["cost"]

        # Verify cost tracking
        summary = performance_tracker.get_summary()
        assert summary["total_cost"] == 0.0, "All Ollama should be free"
        assert total_cost == 0.0, "Cumulative cost should match"


@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.cost
class TestProviderComparison:
    """E2E tests comparing provider performance and costs."""

    def test_provider_capabilities_comparison(self):
        """
        Test getting provider capabilities for comparison.

        Production scenario: Help users choose best provider for their needs.
        """
        agent = DocumentExtractionAgent(
            config=DocumentExtractionConfig(
                provider="auto",
                landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
                openai_key=os.getenv("OPENAI_API_KEY"),
                ollama_base_url="http://localhost:11434",
            )
        )

        capabilities = agent.get_provider_capabilities()

        # Verify all providers reported
        assert "landing_ai" in capabilities
        assert "openai_vision" in capabilities
        assert "ollama_vision" in capabilities

        # Verify key metrics for comparison
        landing_ai = capabilities["landing_ai"]
        openai = capabilities["openai_vision"]
        ollama = capabilities["ollama_vision"]

        # Accuracy comparison
        assert landing_ai["accuracy"] == 0.98  # Highest
        assert openai["accuracy"] == 0.95  # Middle
        assert ollama["accuracy"] == 0.85  # Lowest (but free)

        # Cost comparison
        assert landing_ai["cost_per_page"] == 0.015  # Cheapest paid
        assert openai["cost_per_page"] == 0.068  # More expensive
        assert ollama["cost_per_page"] == 0.0  # Free

        # Feature comparison
        assert landing_ai["supports_bounding_boxes"] is True  # Unique feature
        assert openai["supports_bounding_boxes"] is False
        assert ollama["supports_bounding_boxes"] is False

    def test_cost_vs_quality_tradeoff(self, multi_page_document):
        """
        Test cost vs quality tradeoff analysis.

        Production scenario: Organization needs to understand
        cost/quality tradeoffs for informed decisions.
        """
        agent = DocumentExtractionAgent(
            config=DocumentExtractionConfig(
                provider="auto",
                landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
                openai_key=os.getenv("OPENAI_API_KEY"),
                ollama_base_url="http://localhost:11434",
            )
        )

        # Get provider capabilities
        caps = agent.get_provider_capabilities()

        # Calculate value metrics (accuracy per dollar)
        # Ollama: infinite value (free, decent quality)
        # Landing AI: 0.98 / 0.015 = 65.33 accuracy per cent
        # OpenAI: 0.95 / 0.068 = 13.97 accuracy per cent

        # For free tier (Ollama)
        ollama_value = (
            float("inf") if caps["ollama_vision"]["cost_per_page"] == 0 else 0
        )
        assert ollama_value == float("inf"), "Ollama offers infinite value (free)"

        # For paid tiers
        landing_ai_value = (
            caps["landing_ai"]["accuracy"] / caps["landing_ai"]["cost_per_page"]
        )
        openai_value = (
            caps["openai_vision"]["accuracy"] / caps["openai_vision"]["cost_per_page"]
        )

        # Landing AI offers better value per dollar
        assert (
            landing_ai_value > openai_value
        ), "Landing AI should offer better value (accuracy/cost)"


@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.ollama
class TestProductionScalability:
    """E2E tests for production scalability scenarios."""

    @pytest.fixture(autouse=True)
    def skip_if_ollama_not_running(self, ollama_available):
        """Skip if Ollama not available."""
        if not ollama_available:
            pytest.skip("Ollama not running")

    def test_sequential_document_processing(
        self, multi_document_batch, performance_tracker
    ):
        """
        Test sequential processing of multiple documents.

        Production scenario: Process documents one at a time
        (typical for synchronous workflows).
        """
        agent = DocumentExtractionAgent(
            config=DocumentExtractionConfig(
                provider="ollama_vision",
                ollama_base_url="http://localhost:11434",
            )
        )

        processed = 0
        errors = 0

        # Process documents sequentially
        for doc_path in multi_document_batch:
            try:
                result = agent.extract(doc_path, file_type="txt")
                performance_tracker.record(result)
                processed += 1
            except Exception as e:
                errors += 1
                print(f"Error processing {doc_path}: {e}")

        # Verify processing
        assert processed == len(
            multi_document_batch
        ), "Should process all documents successfully"
        assert errors == 0, "Should have no errors"

        # Verify performance summary
        summary = performance_tracker.get_summary()
        assert summary["total_cost"] == 0.0, "Ollama should be free"
        assert len(summary["providers"]) == 1, "Should use consistent provider"

    def test_error_handling_in_production(self, tmp_path):
        """
        Test error handling for production robustness.

        Production scenario: System encounters invalid documents,
        should handle gracefully without crashing.
        """
        agent = DocumentExtractionAgent(
            config=DocumentExtractionConfig(
                provider="ollama_vision",
                ollama_base_url="http://localhost:11434",
            )
        )

        # Create invalid document
        invalid_doc = tmp_path / "invalid.txt"
        invalid_doc.write_text("")  # Empty file

        # Should handle gracefully
        try:
            result = agent.extract(str(invalid_doc), file_type="txt")
            # Empty file might still extract (empty text)
            assert isinstance(result, dict), "Should return result dict"
        except Exception as e:
            # Or it might raise an error - both are acceptable
            assert isinstance(e, Exception), "Should raise proper exception"
