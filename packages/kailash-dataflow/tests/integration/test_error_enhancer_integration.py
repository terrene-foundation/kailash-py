"""
Integration tests for ErrorEnhancer.

Tests error enhancement in production-like scenarios with real error catalog.
Following 3-tier testing strategy: Tier 2 (Integration) - NO MOCKING.
"""

import time

import pytest


@pytest.mark.integration
class TestErrorEnhancerCatalogIntegration:
    """Test ErrorEnhancer with real error catalog loading."""

    def test_catalog_loads_successfully_in_production_context(self):
        """Test that error catalog loads successfully."""
        from dataflow.platform.errors import ErrorEnhancer

        # Force fresh load
        ErrorEnhancer._error_catalog = None
        ErrorEnhancer._catalog_loaded = False

        catalog = ErrorEnhancer._load_error_catalog()

        assert isinstance(catalog, dict)
        assert len(catalog) >= 50, "Catalog should have at least 50 error definitions"
        assert ErrorEnhancer._catalog_loaded is True

    def test_catalog_contains_all_error_categories(self):
        """Test that catalog contains errors from all categories."""
        from dataflow.platform.errors import ErrorEnhancer

        catalog = ErrorEnhancer._load_error_catalog()

        # Check for errors from each category
        categories = set()
        for error_def in catalog.values():
            if "category" in error_def:
                categories.add(error_def["category"])

        expected_categories = {
            "parameter",
            "connection",
            "migration",
            "configuration",
            "runtime",
        }
        assert expected_categories.issubset(
            categories
        ), f"Missing categories: {expected_categories - categories}"

    def test_all_catalog_entries_have_complete_structure(self):
        """Test that all catalog entries have required fields."""
        from dataflow.platform.errors import ErrorEnhancer

        catalog = ErrorEnhancer._load_error_catalog()

        required_fields = ["title", "causes", "solutions", "docs_url"]

        for error_code, error_def in catalog.items():
            for field in required_fields:
                assert field in error_def, f"Error {error_code} missing field: {field}"

            # Verify causes and solutions are not empty
            assert len(error_def["causes"]) > 0, f"Error {error_code} has no causes"
            assert (
                len(error_def["solutions"]) > 0
            ), f"Error {error_code} has no solutions"

            # Verify at least one solution has a description
            assert any(
                sol.get("description") for sol in error_def["solutions"]
            ), f"Error {error_code} has no solution descriptions"

    def test_catalog_caching_works_correctly(self):
        """Test that catalog is cached after first load."""
        from dataflow.platform.errors import ErrorEnhancer

        # Clear cache
        ErrorEnhancer._error_catalog = None
        ErrorEnhancer._catalog_loaded = False

        # First load
        catalog1 = ErrorEnhancer._load_error_catalog()
        assert ErrorEnhancer._catalog_loaded is True

        # Second load (should use cache)
        catalog2 = ErrorEnhancer._load_error_catalog()

        # Should be same instance
        assert catalog1 is catalog2, "Catalog should be cached"


@pytest.mark.integration
class TestErrorEnhancerWithRealExceptions:
    """Test ErrorEnhancer with real Python exceptions."""

    def test_enhancement_with_real_keyerror(self):
        """Test enhancement with real KeyError exception."""
        from dataflow.platform.errors import ErrorEnhancer

        try:
            data = {}
            value = data["missing_key"]
        except KeyError as e:
            enhanced = ErrorEnhancer.enhance_missing_data_parameter(
                node_id="test_node",
                parameter_name="missing_key",
                node_type="TestNode",
                original_error=e,
            )

            # Verify exception context extraction
            assert enhanced.original_error is e
            assert "exception_type" in enhanced.context
            assert enhanced.context["exception_type"] == "KeyError"
            assert "exception_message" in enhanced.context

    def test_enhancement_with_real_typeerror(self):
        """Test enhancement with real TypeError exception."""
        from dataflow.platform.errors import ErrorEnhancer

        try:
            result = "string" + 123
        except TypeError as e:
            enhanced = ErrorEnhancer.enhance_type_mismatch_error(
                node_id="type_node",
                parameter_name="value",
                expected_type="str",
                received_type="int",
                received_value=123,
                original_error=e,
            )

            # Verify enhancement
            assert enhanced.original_error is e
            assert enhanced.context["expected_type"] == "str"
            assert enhanced.context["received_type"] == "int"

    def test_enhancement_with_real_valueerror(self):
        """Test enhancement with real ValueError exception."""
        from dataflow.platform.errors import ErrorEnhancer

        try:
            int("not_a_number")
        except ValueError as e:
            enhanced = ErrorEnhancer.enhance_parameter_validation_failed(
                node_id="validation_node",
                parameter_name="number_field",
                validation_rule="integer format",
                received_value="not_a_number",
                original_error=e,
            )

            # Verify enhancement
            assert enhanced.original_error is e
            assert "validation_rule" in enhanced.context
            assert enhanced.context["validation_rule"] == "integer format"


@pytest.mark.integration
class TestErrorEnhancerMessageQuality:
    """Test error message quality in production scenarios."""

    def test_all_enhanced_errors_have_actionable_messages(self):
        """Test that all error enhancement methods produce actionable messages."""
        from dataflow.platform.errors import ErrorEnhancer

        # Test multiple error types
        test_cases = [
            {
                "method": ErrorEnhancer.enhance_missing_data_parameter,
                "kwargs": {
                    "node_id": "test_node",
                    "parameter_name": "data",
                    "node_type": "TestNode",
                },
            },
            {
                "method": ErrorEnhancer.enhance_auto_managed_field_conflict,
                "kwargs": {
                    "node_id": "test_node",
                    "field_name": "created_at",
                    "operation": "CREATE",
                },
            },
            {
                "method": ErrorEnhancer.enhance_invalid_database_url,
                "kwargs": {
                    "database_url": "invalid://url",
                    "error_message": "Unsupported scheme",
                },
            },
            {
                "method": ErrorEnhancer.enhance_missing_connection,
                "kwargs": {
                    "source_node": "input",
                    "target_node": "output",
                    "required_parameter": "data",
                },
            },
        ]

        for test_case in test_cases:
            enhanced = test_case["method"](**test_case["kwargs"])

            # Every error should have:
            assert len(enhanced.message) > 0, "Message should not be empty"
            assert len(enhanced.causes) > 0, "Should have at least one cause"
            assert len(enhanced.solutions) > 0, "Should have at least one solution"
            assert enhanced.docs_url, "Should have documentation URL"

    def test_error_messages_contain_context_information(self):
        """Test that error messages include relevant context."""
        from dataflow.platform.errors import ErrorEnhancer

        enhanced = ErrorEnhancer.enhance_missing_data_parameter(
            node_id="user_create", parameter_name="email", node_type="UserCreateNode"
        )

        # Context should be preserved
        assert enhanced.context["node_id"] == "user_create"
        assert enhanced.context["parameter_name"] == "email"
        assert enhanced.context["node_type"] == "UserCreateNode"

    def test_formatted_error_messages_are_readable(self):
        """Test that formatted errors are human-readable."""
        from dataflow.platform.errors import ErrorEnhancer

        enhanced = ErrorEnhancer.enhance_type_mismatch_error(
            node_id="processor",
            parameter_name="input_data",
            expected_type="dict",
            received_type="str",
            received_value="invalid",
        )

        # Test formatting with colors
        formatted_with_color = enhanced.enhanced_message(color=True)
        assert len(formatted_with_color) > 0
        assert "processor" in formatted_with_color
        assert "input_data" in formatted_with_color

        # Test formatting without colors
        formatted_no_color = enhanced.enhanced_message(color=False)
        assert len(formatted_no_color) > 0
        assert "\033[" not in formatted_no_color  # No ANSI codes

    def test_all_solutions_have_code_examples_or_descriptions(self):
        """Test that solutions are actionable."""
        from dataflow.platform.errors import ErrorEnhancer

        enhanced = ErrorEnhancer.enhance_missing_data_parameter(
            node_id="test_node", parameter_name="data"
        )

        # Every solution should have either code example or description
        for solution in enhanced.solutions:
            assert (
                solution.description or solution.code_example
            ), "Solution should have description or code example"


@pytest.mark.integration
class TestErrorEnhancerPerformance:
    """Test ErrorEnhancer performance characteristics."""

    def test_error_enhancement_performance(self):
        """Test that error enhancement is fast enough for production use."""
        from dataflow.platform.errors import ErrorEnhancer

        iterations = 100
        start = time.perf_counter()

        for i in range(iterations):
            ErrorEnhancer.enhance_missing_data_parameter(
                node_id=f"node_{i}", parameter_name="data", node_type="TestNode"
            )

        end = time.perf_counter()
        duration = end - start
        avg_time = duration / iterations

        # Should be very fast (< 1ms per enhancement on average)
        assert (
            avg_time < 0.001
        ), f"Error enhancement too slow: {avg_time*1000:.2f}ms per enhancement"

    def test_catalog_loading_performance(self):
        """Test that catalog loading is reasonably fast."""
        from dataflow.platform.errors import ErrorEnhancer

        # Clear cache
        ErrorEnhancer._error_catalog = None
        ErrorEnhancer._catalog_loaded = False

        # Measure load time
        start = time.perf_counter()
        catalog = ErrorEnhancer._load_error_catalog()
        end = time.perf_counter()
        load_time = end - start

        # Should load in reasonable time (< 100ms)
        assert load_time < 0.1, f"Catalog loading too slow: {load_time*1000:.2f}ms"
        assert len(catalog) > 0, "Catalog should not be empty"

    def test_catalog_caching_provides_performance_benefit(self):
        """Test that caching significantly improves performance."""
        from dataflow.platform.errors import ErrorEnhancer

        # Clear cache
        ErrorEnhancer._error_catalog = None
        ErrorEnhancer._catalog_loaded = False

        # First load (from file)
        start1 = time.perf_counter()
        catalog1 = ErrorEnhancer._load_error_catalog()
        end1 = time.perf_counter()
        first_load = end1 - start1

        # Second load (from cache)
        start2 = time.perf_counter()
        catalog2 = ErrorEnhancer._load_error_catalog()
        end2 = time.perf_counter()
        cached_load = end2 - start2

        # Cached load should be at least 10x faster
        assert (
            cached_load < first_load / 10
        ), f"Cache not effective: first={first_load*1000:.2f}ms, cached={cached_load*1000:.2f}ms"


@pytest.mark.integration
class TestErrorEnhancerProductionReadiness:
    """Test ErrorEnhancer production readiness."""

    def test_handles_none_original_error_gracefully(self):
        """Test that enhancement works without original error."""
        from dataflow.platform.errors import ErrorEnhancer

        enhanced = ErrorEnhancer.enhance_missing_data_parameter(
            node_id="test_node",
            parameter_name="data",
            original_error=None,  # No original error
        )

        # Should still work
        assert enhanced is not None
        assert enhanced.original_error is None
        assert len(enhanced.causes) > 0
        assert len(enhanced.solutions) > 0

    def test_handles_empty_context_gracefully(self):
        """Test that enhancement works with minimal context."""
        from dataflow.platform.errors import ErrorEnhancer

        enhanced = ErrorEnhancer.enhance_missing_data_parameter(
            node_id="node",
            parameter_name="param",
            # Minimal context
        )

        # Should still provide useful information
        assert enhanced.error_code is not None
        assert len(enhanced.message) > 0
        assert len(enhanced.causes) > 0
        assert len(enhanced.solutions) > 0

    def test_all_error_codes_have_unique_docs_urls(self):
        """Test that all error codes have unique documentation URLs."""
        from dataflow.platform.errors import ErrorEnhancer

        catalog = ErrorEnhancer._load_error_catalog()
        docs_urls = set()

        for error_code, error_def in catalog.items():
            docs_url = error_def.get("docs_url")
            assert docs_url, f"Error {error_code} missing docs_url"
            assert docs_url not in docs_urls, f"Duplicate docs_url: {docs_url}"
            docs_urls.add(docs_url)

    def test_error_enhancement_is_deterministic(self):
        """Test that same inputs produce same outputs."""
        from dataflow.platform.errors import ErrorEnhancer

        # Enhance same error twice
        enhanced1 = ErrorEnhancer.enhance_missing_data_parameter(
            node_id="test_node", parameter_name="data", node_type="TestNode"
        )

        enhanced2 = ErrorEnhancer.enhance_missing_data_parameter(
            node_id="test_node", parameter_name="data", node_type="TestNode"
        )

        # Should produce identical results
        assert enhanced1.error_code == enhanced2.error_code
        assert enhanced1.message == enhanced2.message
        assert len(enhanced1.causes) == len(enhanced2.causes)
        assert len(enhanced1.solutions) == len(enhanced2.solutions)
