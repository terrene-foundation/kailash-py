"""Unit tests for server-side transformation pipeline in MCP resource subscriptions."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from kailash.mcp_server.subscriptions import (
    AggregationTransformer,
    DataEnrichmentTransformer,
    FormatConverterTransformer,
    ResourceChange,
    ResourceChangeType,
    ResourceSubscription,
    ResourceSubscriptionManager,
    ResourceTransformer,
    TransformationError,
    TransformationPipeline,
)


class TestResourceTransformer:
    """Test the abstract ResourceTransformer base class."""

    def test_transformer_is_abstract(self):
        """Test that ResourceTransformer cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ResourceTransformer()


class TestDataEnrichmentTransformer:
    """Test data enrichment transformer."""

    def test_initialization(self):
        """Test transformer initialization."""
        transformer = DataEnrichmentTransformer()
        assert transformer.enrichment_functions == {}

        # Test with initial functions
        functions = {"computed_field": lambda data: "computed_value"}
        transformer = DataEnrichmentTransformer(functions)
        assert transformer.enrichment_functions == functions

    def test_add_enrichment(self):
        """Test adding enrichment functions."""
        transformer = DataEnrichmentTransformer()

        def compute_size(data):
            return len(str(data))

        transformer.add_enrichment("size", compute_size)
        assert "size" in transformer.enrichment_functions
        assert transformer.enrichment_functions["size"] == compute_size

    @pytest.mark.asyncio
    async def test_sync_transform(self):
        """Test transformation with synchronous enrichment functions."""
        transformer = DataEnrichmentTransformer()

        # Add synchronous enrichment functions
        transformer.add_enrichment(
            "total_length", lambda data: len(data.get("content", ""))
        )
        transformer.add_enrichment(
            "is_large", lambda data: len(data.get("content", "")) > 10
        )

        resource_data = {
            "uri": "file:///test.txt",
            "content": "Hello, world!",
            "size": 13,
        }

        context = {"subscription_id": "sub_123"}
        result = await transformer.transform(resource_data, context)

        # Check original data is preserved
        assert result["uri"] == "file:///test.txt"
        assert result["content"] == "Hello, world!"
        assert result["size"] == 13

        # Check enriched fields
        assert result["total_length"] == 13
        assert result["is_large"] is True

        # Check transformation metadata
        assert "__transformation" in result
        assert result["__transformation"]["enriched_fields"] == [
            "total_length",
            "is_large",
        ]
        assert result["__transformation"]["transformer"] == "DataEnrichmentTransformer"

    @pytest.mark.asyncio
    async def test_async_transform(self):
        """Test transformation with asynchronous enrichment functions."""
        transformer = DataEnrichmentTransformer()

        # Add asynchronous enrichment function
        async def async_compute_hash(data):
            await asyncio.sleep(0.01)  # Simulate async operation
            import hashlib

            content = data.get("content", "")
            return hashlib.md5(content.encode()).hexdigest()

        transformer.add_enrichment("content_hash", async_compute_hash)

        resource_data = {"uri": "file:///test.txt", "content": "Hello, world!"}

        context = {"subscription_id": "sub_123"}
        result = await transformer.transform(resource_data, context)

        # Check that async enrichment was applied
        assert "content_hash" in result
        assert len(result["content_hash"]) == 32  # MD5 hash length

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in enrichment functions."""
        transformer = DataEnrichmentTransformer()

        # Add function that raises an error
        def error_function(data):
            raise ValueError("Test error")

        transformer.add_enrichment("error_field", error_function)
        transformer.add_enrichment("good_field", lambda data: "good_value")

        resource_data = {"uri": "file:///test.txt"}
        context = {"subscription_id": "sub_123"}

        result = await transformer.transform(resource_data, context)

        # Should continue processing despite error
        assert "good_field" in result
        assert result["good_field"] == "good_value"
        # Error field should not be present
        assert "error_field" not in result

    def test_should_apply(self):
        """Test should_apply logic."""
        transformer = DataEnrichmentTransformer()
        subscription = ResourceSubscription("sub_123", "conn_123", "file:///*.txt")

        # Should not apply when no enrichment functions
        assert not transformer.should_apply("file:///test.txt", subscription)

        # Should apply when enrichment functions exist
        transformer.add_enrichment("test_field", lambda data: "test")
        assert transformer.should_apply("file:///test.txt", subscription)


class TestFormatConverterTransformer:
    """Test format converter transformer."""

    def test_initialization(self):
        """Test transformer initialization."""
        transformer = FormatConverterTransformer()
        assert transformer.conversions == {}

    def test_add_conversion(self):
        """Test adding conversion functions."""
        transformer = FormatConverterTransformer()

        def uppercase_converter(value):
            return str(value).upper()

        transformer.add_conversion("content", uppercase_converter)
        assert "content" in transformer.conversions

    @pytest.mark.asyncio
    async def test_simple_conversion(self):
        """Test simple field conversion."""
        transformer = FormatConverterTransformer()

        # Add conversion for content field
        transformer.add_conversion("content", lambda value: str(value).upper())

        resource_data = {
            "uri": "file:///test.txt",
            "content": "hello world",
            "size": 11,
        }

        context = {"subscription_id": "sub_123"}
        result = await transformer.transform(resource_data, context)

        # Check conversion was applied
        assert result["content"] == "HELLO WORLD"
        assert result["size"] == 11  # Unchanged
        assert result["uri"] == "file:///test.txt"  # Unchanged

    @pytest.mark.asyncio
    async def test_nested_conversion(self):
        """Test conversion of nested fields."""
        transformer = FormatConverterTransformer()

        # Add conversion for nested field
        transformer.add_conversion("metadata.author", lambda value: str(value).title())
        transformer.add_conversion("content.text", lambda value: str(value).upper())

        resource_data = {
            "uri": "file:///test.txt",
            "content": {"text": "hello world", "type": "plain"},
            "metadata": {"author": "john doe", "created": "2024-01-01"},
        }

        context = {"subscription_id": "sub_123"}
        result = await transformer.transform(resource_data, context)

        # Check nested conversions
        assert result["content"]["text"] == "HELLO WORLD"
        assert result["content"]["type"] == "plain"  # Unchanged
        assert result["metadata"]["author"] == "John Doe"
        assert result["metadata"]["created"] == "2024-01-01"  # Unchanged

    @pytest.mark.asyncio
    async def test_pattern_matching(self):
        """Test pattern matching for conversions."""
        transformer = FormatConverterTransformer()

        # Add pattern-based conversion
        transformer.add_conversion("*.name", lambda value: str(value).title())

        resource_data = {
            "user": {"name": "alice smith"},
            "project": {"name": "test project"},
            "other": {"title": "other field"},
        }

        context = {"subscription_id": "sub_123"}
        result = await transformer.transform(resource_data, context)

        # Check pattern matching worked
        assert result["user"]["name"] == "Alice Smith"
        assert result["project"]["name"] == "Test Project"
        assert result["other"]["title"] == "other field"  # No match

    @pytest.mark.asyncio
    async def test_async_conversion(self):
        """Test asynchronous conversion functions."""
        transformer = FormatConverterTransformer()

        async def async_hash_converter(value):
            await asyncio.sleep(0.01)
            import hashlib

            return hashlib.md5(str(value).encode()).hexdigest()

        transformer.add_conversion("content", async_hash_converter)

        resource_data = {"uri": "file:///test.txt", "content": "hello world"}

        context = {"subscription_id": "sub_123"}
        result = await transformer.transform(resource_data, context)

        # Check async conversion was applied
        assert len(result["content"]) == 32  # MD5 hash length
        assert result["content"] != "hello world"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in conversions."""
        transformer = FormatConverterTransformer()

        # Add conversion that raises error
        def error_converter(value):
            raise ValueError("Conversion error")

        transformer.add_conversion("content", error_converter)
        transformer.add_conversion("title", lambda value: str(value).upper())

        resource_data = {"content": "test content", "title": "test title"}

        context = {"subscription_id": "sub_123"}
        result = await transformer.transform(resource_data, context)

        # Should keep original value on error
        assert result["content"] == "test content"
        # Should apply successful conversion
        assert result["title"] == "TEST TITLE"

    def test_should_apply(self):
        """Test should_apply logic."""
        transformer = FormatConverterTransformer()
        subscription = ResourceSubscription("sub_123", "conn_123", "file:///*.txt")

        # Should not apply when no conversions
        assert not transformer.should_apply("file:///test.txt", subscription)

        # Should apply when conversions exist
        transformer.add_conversion("content", str.upper)
        assert transformer.should_apply("file:///test.txt", subscription)


class TestAggregationTransformer:
    """Test aggregation transformer."""

    def test_initialization(self):
        """Test transformer initialization."""
        transformer = AggregationTransformer()
        assert transformer.data_sources == {}

    def test_add_data_source(self):
        """Test adding data sources."""
        transformer = AggregationTransformer()

        def fetch_metadata(uri):
            return {"source": "metadata_service"}

        transformer.add_data_source("metadata", fetch_metadata)
        assert "metadata" in transformer.data_sources

    @pytest.mark.asyncio
    async def test_sync_aggregation(self):
        """Test aggregation with synchronous data sources."""
        transformer = AggregationTransformer()

        # Add sync data sources
        def fetch_stats(uri):
            return {"views": 100, "downloads": 50}

        def fetch_comments(uri):
            return {"count": 5, "latest": "Great file!"}

        transformer.add_data_source("stats", fetch_stats)
        transformer.add_data_source("comments", fetch_comments)

        resource_data = {"uri": "file:///test.txt", "content": "Test content"}

        context = {"subscription_id": "sub_123"}
        result = await transformer.transform(resource_data, context)

        # Check original data preserved
        assert result["uri"] == "file:///test.txt"
        assert result["content"] == "Test content"

        # Check aggregated data
        assert "__aggregated" in result
        assert "stats" in result["__aggregated"]
        assert "comments" in result["__aggregated"]
        assert result["__aggregated"]["stats"]["views"] == 100
        assert result["__aggregated"]["comments"]["count"] == 5

    @pytest.mark.asyncio
    async def test_async_aggregation(self):
        """Test aggregation with asynchronous data sources."""
        transformer = AggregationTransformer()

        async def fetch_remote_data(uri):
            await asyncio.sleep(0.01)  # Simulate network call
            return {"remote_id": "abc123", "status": "active"}

        transformer.add_data_source("remote", fetch_remote_data)

        resource_data = {"uri": "file:///test.txt"}
        context = {"subscription_id": "sub_123"}

        result = await transformer.transform(resource_data, context)

        # Check async aggregation worked
        assert "__aggregated" in result
        assert "remote" in result["__aggregated"]
        assert result["__aggregated"]["remote"]["remote_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in data sources."""
        transformer = AggregationTransformer()

        def error_source(uri):
            raise RuntimeError("Data source error")

        def good_source(uri):
            return {"data": "good"}

        transformer.add_data_source("error_source", error_source)
        transformer.add_data_source("good_source", good_source)

        resource_data = {"uri": "file:///test.txt"}
        context = {"subscription_id": "sub_123"}

        result = await transformer.transform(resource_data, context)

        # Should handle error gracefully
        assert "__aggregated" in result
        assert "error_source" in result["__aggregated"]
        assert "error" in result["__aggregated"]["error_source"]
        assert "good_source" in result["__aggregated"]
        assert result["__aggregated"]["good_source"]["data"] == "good"

    def test_should_apply(self):
        """Test should_apply logic."""
        transformer = AggregationTransformer()
        subscription = ResourceSubscription("sub_123", "conn_123", "file:///*.txt")

        # Should not apply when no data sources
        assert not transformer.should_apply("file:///test.txt", subscription)

        # Should apply when data sources exist
        transformer.add_data_source("test", lambda uri: {"test": True})
        assert transformer.should_apply("file:///test.txt", subscription)


class TestTransformationPipeline:
    """Test transformation pipeline."""

    def test_initialization(self):
        """Test pipeline initialization."""
        pipeline = TransformationPipeline()
        assert pipeline.transformers == []
        assert pipeline.enabled is True

    def test_add_remove_transformers(self):
        """Test adding and removing transformers."""
        pipeline = TransformationPipeline()
        transformer1 = DataEnrichmentTransformer()
        transformer2 = FormatConverterTransformer()

        # Add transformers
        pipeline.add_transformer(transformer1)
        pipeline.add_transformer(transformer2)

        assert len(pipeline.transformers) == 2
        assert transformer1 in pipeline.transformers
        assert transformer2 in pipeline.transformers

        # Remove transformer
        pipeline.remove_transformer(transformer1)
        assert len(pipeline.transformers) == 1
        assert transformer1 not in pipeline.transformers
        assert transformer2 in pipeline.transformers

    def test_clear_transformers(self):
        """Test clearing all transformers."""
        pipeline = TransformationPipeline()
        pipeline.add_transformer(DataEnrichmentTransformer())
        pipeline.add_transformer(FormatConverterTransformer())

        assert len(pipeline.transformers) == 2

        pipeline.clear()
        assert len(pipeline.transformers) == 0

    def test_enable_disable(self):
        """Test enabling and disabling pipeline."""
        pipeline = TransformationPipeline()

        assert pipeline.enabled is True

        pipeline.disable()
        assert pipeline.enabled is False

        pipeline.enable()
        assert pipeline.enabled is True

    @pytest.mark.asyncio
    async def test_empty_pipeline(self):
        """Test pipeline with no transformers."""
        pipeline = TransformationPipeline()
        subscription = ResourceSubscription("sub_123", "conn_123", "file:///*.txt")

        resource_data = {"uri": "file:///test.txt", "content": "test"}
        result = await pipeline.apply(resource_data, "file:///test.txt", subscription)

        # Should return original data unchanged
        assert result == resource_data

    @pytest.mark.asyncio
    async def test_disabled_pipeline(self):
        """Test disabled pipeline."""
        pipeline = TransformationPipeline()
        pipeline.add_transformer(DataEnrichmentTransformer())
        pipeline.disable()

        subscription = ResourceSubscription("sub_123", "conn_123", "file:///*.txt")
        resource_data = {"uri": "file:///test.txt", "content": "test"}

        result = await pipeline.apply(resource_data, "file:///test.txt", subscription)

        # Should return original data unchanged when disabled
        assert result == resource_data

    @pytest.mark.asyncio
    async def test_single_transformer(self):
        """Test pipeline with single transformer."""
        pipeline = TransformationPipeline()

        enrichment = DataEnrichmentTransformer()
        enrichment.add_enrichment("test_field", lambda data: "test_value")
        pipeline.add_transformer(enrichment)

        subscription = ResourceSubscription("sub_123", "conn_123", "file:///*.txt")
        resource_data = {"uri": "file:///test.txt", "content": "test"}

        result = await pipeline.apply(resource_data, "file:///test.txt", subscription)

        # Should apply transformation
        assert result["test_field"] == "test_value"
        assert "__transformation" in result

    @pytest.mark.asyncio
    async def test_multiple_transformers(self):
        """Test pipeline with multiple transformers."""
        pipeline = TransformationPipeline()

        # Add enrichment transformer
        enrichment = DataEnrichmentTransformer()
        enrichment.add_enrichment("computed_field", lambda data: "computed")
        pipeline.add_transformer(enrichment)

        # Add format converter
        converter = FormatConverterTransformer()
        converter.add_conversion("content", str.upper)
        pipeline.add_transformer(converter)

        subscription = ResourceSubscription("sub_123", "conn_123", "file:///*.txt")
        resource_data = {"uri": "file:///test.txt", "content": "hello"}

        result = await pipeline.apply(resource_data, "file:///test.txt", subscription)

        # Should apply both transformations
        assert result["computed_field"] == "computed"
        assert result["content"] == "HELLO"

        # Should have pipeline metadata
        assert "__transformation" in result
        assert "pipeline" in result["__transformation"]
        assert len(result["__transformation"]["pipeline"]["applied_transformers"]) == 2

    @pytest.mark.asyncio
    async def test_transformer_error_handling(self):
        """Test error handling in pipeline."""
        pipeline = TransformationPipeline()

        # Create transformer that will raise error
        class ErrorTransformer(ResourceTransformer):
            async def transform(self, resource_data, context):
                raise RuntimeError("Transformer error")

            def should_apply(self, uri, subscription):
                return True

        # Add error transformer and good transformer
        pipeline.add_transformer(ErrorTransformer())

        enrichment = DataEnrichmentTransformer()
        enrichment.add_enrichment("good_field", lambda data: "good")
        pipeline.add_transformer(enrichment)

        subscription = ResourceSubscription("sub_123", "conn_123", "file:///*.txt")
        resource_data = {"uri": "file:///test.txt"}

        result = await pipeline.apply(resource_data, "file:///test.txt", subscription)

        # Should continue processing despite error
        assert result["good_field"] == "good"

        # Should record error in metadata
        assert "__transformation" in result
        assert "errors" in result["__transformation"]
        assert len(result["__transformation"]["errors"]) == 1
        assert (
            "ErrorTransformer" in result["__transformation"]["errors"][0]["transformer"]
        )

    @pytest.mark.asyncio
    async def test_context_creation(self):
        """Test that proper context is created for transformers."""
        pipeline = TransformationPipeline()

        captured_context = {}

        class ContextCapturingTransformer(ResourceTransformer):
            async def transform(self, resource_data, context):
                captured_context.update(context)
                return resource_data

            def should_apply(self, uri, subscription):
                return True

        pipeline.add_transformer(ContextCapturingTransformer())

        subscription = ResourceSubscription(
            "sub_123",
            "conn_123",
            "file:///*.txt",
            fields=["uri", "content"],
            fragments={"test": ["uri"]},
        )
        resource_data = {"uri": "file:///test.txt"}

        await pipeline.apply(resource_data, "file:///test.txt", subscription)

        # Check context was created properly
        assert captured_context["uri"] == "file:///test.txt"
        assert captured_context["subscription_id"] == "sub_123"
        assert captured_context["connection_id"] == "conn_123"
        assert captured_context["uri_pattern"] == "file:///*.txt"
        assert captured_context["fields"] == ["uri", "content"]
        assert captured_context["fragments"] == {"test": ["uri"]}
        assert "timestamp" in captured_context


class TestSubscriptionManagerIntegration:
    """Test transformation pipeline integration with subscription manager."""

    @pytest.fixture
    def subscription_manager(self):
        """Create subscription manager for testing."""
        return ResourceSubscriptionManager()

    @pytest.mark.asyncio
    async def test_transformation_in_resource_processing(self, subscription_manager):
        """Test that transformations are applied during resource change processing."""
        # Set up notification capture
        notifications = []

        async def capture_notifications(connection_id, notification):
            notifications.append((connection_id, notification))

        subscription_manager.set_notification_callback(capture_notifications)

        # Add transformer to pipeline
        enrichment = DataEnrichmentTransformer()
        enrichment.add_enrichment(
            "processed_by", lambda data: "transformation_pipeline"
        )
        subscription_manager.transformation_pipeline.add_transformer(enrichment)

        # Create subscription
        subscription_id = await subscription_manager.create_subscription(
            connection_id="conn_123",
            uri_pattern="file:///test.txt",
            fields=["uri", "processed_by"],
        )

        # Mock resource data
        async def mock_get_resource_data(uri):
            return {"uri": uri, "name": "test.txt", "content": "original content"}

        subscription_manager._get_resource_data = mock_get_resource_data

        # Process resource change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///test.txt",
            timestamp=datetime.now(UTC),
        )

        await subscription_manager.process_resource_change(change)

        # Verify transformation was applied
        assert len(notifications) == 1
        connection_id, notification = notifications[0]

        filtered_data = notification["params"]["data"]
        # Should include enriched field due to transformation
        assert "processed_by" in filtered_data
        assert filtered_data["processed_by"] == "transformation_pipeline"
        # Should not include other fields due to field selection
        assert "name" not in filtered_data
        assert "content" not in filtered_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
