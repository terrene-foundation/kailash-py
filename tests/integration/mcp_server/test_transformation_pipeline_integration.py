"""Integration tests for server-side transformation pipeline with real infrastructure."""

import asyncio
from datetime import datetime
from typing import Any, Dict

import pytest
import pytest_asyncio
from kailash.mcp_server.server import MCPServer
from kailash.mcp_server.subscriptions import (
    AggregationTransformer,
    DataEnrichmentTransformer,
    FormatConverterTransformer,
    ResourceChange,
    ResourceChangeType,
    ResourceSubscriptionManager,
)
from kailash.middleware.gateway.event_store import EventStore

from tests.integration.docker_test_base import DockerIntegrationTestBase


class TestTransformationPipelineIntegration(DockerIntegrationTestBase):
    """Integration tests for transformation pipeline with real infrastructure."""

    @pytest_asyncio.fixture
    async def subscription_manager(self, postgres_conn):
        """Create subscription manager with real event store."""
        event_store = EventStore(postgres_conn)

        manager = ResourceSubscriptionManager(event_store=event_store)

        await manager.initialize()

        yield manager

        await manager.shutdown()

    @pytest_asyncio.fixture
    async def mcp_server(self, postgres_conn):
        """Create MCP server with real infrastructure."""
        event_store = EventStore(postgres_conn)

        server = MCPServer(
            "transformation_test_server",
            event_store=event_store,
            enable_subscriptions=True,
        )

        # Initialize subscription manager manually
        server.subscription_manager = ResourceSubscriptionManager(
            event_store=event_store
        )
        await server.subscription_manager.initialize()

        yield server

        if server.subscription_manager:
            await server.subscription_manager.shutdown()

    @pytest.mark.asyncio
    async def test_enrichment_transformer_integration(self, subscription_manager):
        """Test data enrichment transformer with real infrastructure."""
        # Set up notification capture
        notifications = []

        async def capture_notifications(
            connection_id: str, notification: Dict[str, Any]
        ):
            notifications.append((connection_id, notification))

        subscription_manager.set_notification_callback(capture_notifications)

        # Add enrichment transformer
        enrichment = DataEnrichmentTransformer()

        # Add sync enrichment function
        def compute_word_count(data):
            content = data.get("content", "")
            return len(content.split())

        # Add async enrichment function
        async def compute_hash(data):
            await asyncio.sleep(0.01)  # Simulate async operation
            import hashlib

            content = str(data.get("content", ""))
            return hashlib.md5(content.encode()).hexdigest()

        enrichment.add_enrichment("word_count", compute_word_count)
        enrichment.add_enrichment("content_hash", compute_hash)

        subscription_manager.transformation_pipeline.add_transformer(enrichment)

        # Create subscription with field selection
        subscription_id = await subscription_manager.create_subscription(
            connection_id="enrichment_conn",
            uri_pattern="file:///document.txt",
            fields=["uri", "content", "word_count", "content_hash"],
        )

        # Mock resource data
        async def mock_get_resource_data(uri: str):
            return {
                "uri": uri,
                "name": "document.txt",
                "content": "Hello world from transformation pipeline",
                "size": 39,
                "type": "text",
            }

        subscription_manager._get_resource_data = mock_get_resource_data

        # Process resource change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///document.txt",
            timestamp=datetime.utcnow(),
        )

        await subscription_manager.process_resource_change(change)

        # Verify transformation was applied
        assert len(notifications) == 1
        connection_id, notification = notifications[0]

        assert connection_id == "enrichment_conn"
        filtered_data = notification["params"]["data"]

        # Check original data is preserved
        assert filtered_data["uri"] == "file:///document.txt"
        assert filtered_data["content"] == "Hello world from transformation pipeline"

        # Check enriched fields
        assert (
            filtered_data["word_count"] == 5
        )  # "Hello world from transformation pipeline"
        assert "content_hash" in filtered_data
        assert len(filtered_data["content_hash"]) == 32  # MD5 hash length

        # Verify other fields were filtered out by field selection
        assert "name" not in filtered_data
        assert "size" not in filtered_data
        assert "type" not in filtered_data

    @pytest.mark.asyncio
    async def test_format_converter_integration(self, subscription_manager):
        """Test format converter transformer with real infrastructure."""
        notifications = []

        async def capture_notifications(
            connection_id: str, notification: Dict[str, Any]
        ):
            notifications.append((connection_id, notification))

        subscription_manager.set_notification_callback(capture_notifications)

        # Add format converter transformer
        converter = FormatConverterTransformer()

        # Add conversions
        converter.add_conversion("title", str.title)
        converter.add_conversion("metadata.author", str.upper)
        converter.add_conversion(
            "content.text", lambda text: text.replace("old", "new")
        )

        subscription_manager.transformation_pipeline.add_transformer(converter)

        # Create subscription
        subscription_id = await subscription_manager.create_subscription(
            connection_id="converter_conn",
            uri_pattern="config:///settings",
            fragments={
                "titleInfo": ["title"],
                "authorInfo": ["metadata.author"],
                "contentInfo": ["content.text"],
            },
        )

        # Mock resource data with nested structure
        async def mock_get_resource_data(uri: str):
            return {
                "uri": uri,
                "title": "configuration settings",
                "content": {
                    "text": "This is the old configuration format",
                    "type": "json",
                },
                "metadata": {
                    "author": "john doe",
                    "created": "2024-01-01",
                    "version": "1.0",
                },
            }

        subscription_manager._get_resource_data = mock_get_resource_data

        # Process resource change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="config:///settings",
            timestamp=datetime.utcnow(),
        )

        await subscription_manager.process_resource_change(change)

        # Verify transformations were applied
        assert len(notifications) == 1
        connection_id, notification = notifications[0]

        filtered_data = notification["params"]["data"]

        # Check fragment structure with transformed data
        assert "__titleInfo" in filtered_data
        assert (
            filtered_data["__titleInfo"]["title"] == "Configuration Settings"
        )  # Title case

        assert "__authorInfo" in filtered_data
        assert (
            filtered_data["__authorInfo"]["metadata"]["author"] == "JOHN DOE"
        )  # Upper case

        assert "__contentInfo" in filtered_data
        assert (
            filtered_data["__contentInfo"]["content"]["text"]
            == "This is the new configuration format"
        )  # Text replacement

    @pytest.mark.asyncio
    async def test_aggregation_transformer_integration(self, subscription_manager):
        """Test aggregation transformer with real infrastructure."""
        notifications = []

        async def capture_notifications(
            connection_id: str, notification: Dict[str, Any]
        ):
            notifications.append((connection_id, notification))

        subscription_manager.set_notification_callback(capture_notifications)

        # Add aggregation transformer
        aggregator = AggregationTransformer()

        # Add data sources (simulating external services)
        def fetch_stats(uri):
            return {"views": 150, "downloads": 45, "rating": 4.5}

        async def fetch_related_files(uri):
            await asyncio.sleep(0.01)  # Simulate async API call
            return ["related_file_1.txt", "related_file_2.txt"]

        aggregator.add_data_source("stats", fetch_stats)
        aggregator.add_data_source("related_files", fetch_related_files)

        subscription_manager.transformation_pipeline.add_transformer(aggregator)

        # Create subscription
        subscription_id = await subscription_manager.create_subscription(
            connection_id="aggregation_conn",
            uri_pattern="file:///report.pdf",
            fields=["uri", "name", "__aggregated"],
        )

        # Mock resource data
        async def mock_get_resource_data(uri: str):
            return {"uri": uri, "name": "report.pdf", "size": 2048, "type": "pdf"}

        subscription_manager._get_resource_data = mock_get_resource_data

        # Process resource change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///report.pdf",
            timestamp=datetime.utcnow(),
        )

        await subscription_manager.process_resource_change(change)

        # Verify aggregation was applied
        assert len(notifications) == 1
        connection_id, notification = notifications[0]

        filtered_data = notification["params"]["data"]

        # Check original data
        assert filtered_data["uri"] == "file:///report.pdf"
        assert filtered_data["name"] == "report.pdf"

        # Check aggregated data
        assert "__aggregated" in filtered_data
        aggregated = filtered_data["__aggregated"]

        assert "stats" in aggregated
        assert aggregated["stats"]["views"] == 150
        assert aggregated["stats"]["downloads"] == 45
        assert aggregated["stats"]["rating"] == 4.5

        assert "related_files" in aggregated
        assert len(aggregated["related_files"]) == 2
        assert "related_file_1.txt" in aggregated["related_files"]

    @pytest.mark.asyncio
    async def test_multiple_transformers_pipeline_integration(
        self, subscription_manager
    ):
        """Test multiple transformers working together with real infrastructure."""
        notifications = []

        async def capture_notifications(
            connection_id: str, notification: Dict[str, Any]
        ):
            notifications.append((connection_id, notification))

        subscription_manager.set_notification_callback(capture_notifications)

        # Add multiple transformers to pipeline

        # 1. Enrichment transformer
        enrichment = DataEnrichmentTransformer()
        enrichment.add_enrichment(
            "processing_timestamp", lambda data: datetime.utcnow().isoformat()
        )
        enrichment.add_enrichment(
            "content_length", lambda data: len(data.get("content", ""))
        )

        # 2. Format converter
        converter = FormatConverterTransformer()
        converter.add_conversion("title", str.upper)
        converter.add_conversion("content", lambda text: f"[PROCESSED] {text}")

        # 3. Aggregation transformer
        aggregator = AggregationTransformer()
        aggregator.add_data_source("metadata", lambda uri: {"processed_by": "pipeline"})

        # Add transformers in order
        subscription_manager.transformation_pipeline.add_transformer(enrichment)
        subscription_manager.transformation_pipeline.add_transformer(converter)
        subscription_manager.transformation_pipeline.add_transformer(aggregator)

        # Create subscription
        subscription_id = await subscription_manager.create_subscription(
            connection_id="pipeline_conn",
            uri_pattern="file:///complex.txt",
            fields=["uri", "title", "content", "content_length", "__aggregated"],
        )

        # Mock resource data
        async def mock_get_resource_data(uri: str):
            return {
                "uri": uri,
                "title": "complex document",
                "content": "This is complex content",
                "author": "test author",
            }

        subscription_manager._get_resource_data = mock_get_resource_data

        # Process resource change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///complex.txt",
            timestamp=datetime.utcnow(),
        )

        await subscription_manager.process_resource_change(change)

        # Verify all transformations were applied
        assert len(notifications) == 1
        connection_id, notification = notifications[0]

        filtered_data = notification["params"]["data"]

        # Check enriched fields (from enrichment transformer)
        assert "content_length" in filtered_data
        assert filtered_data["content_length"] == 23  # Length of original content

        # Check format conversions (from format converter)
        assert filtered_data["title"] == "COMPLEX DOCUMENT"  # Uppercase conversion
        assert (
            filtered_data["content"] == "[PROCESSED] This is complex content"
        )  # Text prefix

        # Check aggregated data (from aggregation transformer)
        assert "__aggregated" in filtered_data
        assert "metadata" in filtered_data["__aggregated"]
        assert filtered_data["__aggregated"]["metadata"]["processed_by"] == "pipeline"

    @pytest.mark.asyncio
    async def test_transformation_error_handling_integration(
        self, subscription_manager
    ):
        """Test error handling in transformation pipeline with real infrastructure."""
        notifications = []

        async def capture_notifications(
            connection_id: str, notification: Dict[str, Any]
        ):
            notifications.append((connection_id, notification))

        subscription_manager.set_notification_callback(capture_notifications)

        # Add transformer that will cause an error
        enrichment = DataEnrichmentTransformer()

        # Add function that will raise an error
        def error_function(data):
            raise ValueError("Intentional test error")

        # Add good function
        def good_function(data):
            return "processed_successfully"

        enrichment.add_enrichment("error_field", error_function)
        enrichment.add_enrichment("good_field", good_function)

        subscription_manager.transformation_pipeline.add_transformer(enrichment)

        # Create subscription with field selection that includes transformation metadata
        subscription_id = await subscription_manager.create_subscription(
            connection_id="error_conn",
            uri_pattern="file:///error_test.txt",
            fields=["uri", "good_field", "__transformation"],
        )

        # Mock resource data
        async def mock_get_resource_data(uri: str):
            return {"uri": uri, "content": "test content"}

        subscription_manager._get_resource_data = mock_get_resource_data

        # Process resource change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///error_test.txt",
            timestamp=datetime.utcnow(),
        )

        await subscription_manager.process_resource_change(change)

        # Verify error handling worked
        assert len(notifications) == 1
        connection_id, notification = notifications[0]

        filtered_data = notification["params"]["data"]

        # Check that good processing continued despite error
        assert filtered_data["good_field"] == "processed_successfully"

        # Check transformation metadata includes error information but no error field
        assert "__transformation" in filtered_data
        transformation_meta = filtered_data["__transformation"]

        # The error should not cause a pipeline-level error since it was handled at the enrichment level
        # The enrichment transformer handles errors internally and continues processing
        assert "good_field" in transformation_meta.get("enriched_fields", [])
        assert "error_field" not in filtered_data  # Error field should not be present

    @pytest.mark.asyncio
    async def test_disabled_pipeline_integration(self, subscription_manager):
        """Test that disabled pipeline doesn't transform data."""
        notifications = []

        async def capture_notifications(
            connection_id: str, notification: Dict[str, Any]
        ):
            notifications.append((connection_id, notification))

        subscription_manager.set_notification_callback(capture_notifications)

        # Add transformer but disable pipeline
        enrichment = DataEnrichmentTransformer()
        enrichment.add_enrichment("test_field", lambda data: "should_not_appear")

        subscription_manager.transformation_pipeline.add_transformer(enrichment)
        subscription_manager.transformation_pipeline.disable()

        # Create subscription
        subscription_id = await subscription_manager.create_subscription(
            connection_id="disabled_conn",
            uri_pattern="file:///disabled_test.txt",
            fields=["uri", "content"],
        )

        # Mock resource data
        async def mock_get_resource_data(uri: str):
            return {"uri": uri, "content": "original content"}

        subscription_manager._get_resource_data = mock_get_resource_data

        # Process resource change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///disabled_test.txt",
            timestamp=datetime.utcnow(),
        )

        await subscription_manager.process_resource_change(change)

        # Verify no transformation was applied
        assert len(notifications) == 1
        connection_id, notification = notifications[0]

        filtered_data = notification["params"]["data"]

        # Should only have original data, no transformations
        assert filtered_data["uri"] == "file:///disabled_test.txt"
        assert filtered_data["content"] == "original content"
        assert "test_field" not in filtered_data
        assert "__transformation" not in filtered_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
