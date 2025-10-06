"""MCP server resource subscription implementation."""

import asyncio
import fnmatch
import hashlib
import json
import logging
import uuid
import weakref
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Union

# Optional Redis support
try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False

from .auth import AuthManager
from .auth import PermissionError as PermissionDeniedError
from .protocol import ResourceChange, ResourceChangeType


class SubscriptionError(Exception):
    """Raised when subscription operations fail."""

    pass


class TransformationError(Exception):
    """Raised when resource transformation fails."""

    pass


class ResourceTransformer(ABC):
    """Abstract base class for resource transformations."""

    @abstractmethod
    async def transform(
        self, resource_data: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Transform resource data.

        Args:
            resource_data: The original resource data
            context: Additional context (subscription info, user info, etc.)

        Returns:
            Transformed resource data
        """
        pass

    @abstractmethod
    def should_apply(self, uri: str, subscription: "ResourceSubscription") -> bool:
        """Determine if this transformer should be applied.

        Args:
            uri: Resource URI
            subscription: The subscription requesting the resource

        Returns:
            True if transformer should be applied
        """
        pass


class DataEnrichmentTransformer(ResourceTransformer):
    """Transformer that adds computed fields and metadata."""

    def __init__(
        self, enrichment_functions: Dict[str, Callable[[Dict[str, Any]], Any]] = None
    ):
        self.enrichment_functions = enrichment_functions or {}

    def add_enrichment(
        self, field_name: str, function: Callable[[Dict[str, Any]], Any]
    ):
        """Add an enrichment function for a specific field."""
        self.enrichment_functions[field_name] = function

    async def transform(
        self, resource_data: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Add enriched fields to resource data."""
        enriched_data = resource_data.copy()

        # Add computed fields
        for field_name, function in self.enrichment_functions.items():
            try:
                if asyncio.iscoroutinefunction(function):
                    enriched_data[field_name] = await function(resource_data)
                else:
                    enriched_data[field_name] = function(resource_data)
            except Exception as e:
                # Log error but continue processing
                pass

        # Add transformation metadata
        enriched_data["__transformation"] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "enriched_fields": list(self.enrichment_functions.keys()),
            "transformer": "DataEnrichmentTransformer",
        }

        return enriched_data

    def should_apply(self, uri: str, subscription: "ResourceSubscription") -> bool:
        """Apply to all resources that have enrichment functions."""
        return len(self.enrichment_functions) > 0


class FormatConverterTransformer(ResourceTransformer):
    """Transformer that converts between data formats."""

    def __init__(self, conversions: Dict[str, Callable[[Any], Any]] = None):
        self.conversions = conversions or {}

    def add_conversion(self, field_pattern: str, converter: Callable[[Any], Any]):
        """Add a conversion function for fields matching a pattern."""
        self.conversions[field_pattern] = converter

    async def transform(
        self, resource_data: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply format conversions to matching fields."""
        converted_data = await self._apply_conversions(resource_data, "")

        # Add transformation metadata
        converted_data["__transformation"] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "conversions_applied": list(self.conversions.keys()),
            "transformer": "FormatConverterTransformer",
        }

        return converted_data

    async def _apply_conversions(self, data: Any, path: str) -> Any:
        """Recursively apply conversions to nested data."""
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                field_path = f"{path}.{key}" if path else key

                # Check if this field matches any conversion pattern
                converted_value = value
                for pattern, converter in self.conversions.items():
                    if fnmatch.fnmatch(field_path, pattern):
                        try:
                            if asyncio.iscoroutinefunction(converter):
                                converted_value = await converter(value)
                            else:
                                converted_value = converter(value)
                            break
                        except Exception:
                            # Keep original value on conversion error
                            pass

                # Recursively process nested objects
                result[key] = await self._apply_conversions(converted_value, field_path)
            return result
        elif isinstance(data, list):
            return [
                await self._apply_conversions(item, f"{path}[{i}]")
                for i, item in enumerate(data)
            ]
        else:
            return data

    def should_apply(self, uri: str, subscription: "ResourceSubscription") -> bool:
        """Apply to resources that have format conversions defined."""
        return len(self.conversions) > 0


class AggregationTransformer(ResourceTransformer):
    """Transformer that aggregates data from multiple sources."""

    def __init__(self, data_sources: Dict[str, Callable[[str], Any]] = None):
        self.data_sources = data_sources or {}

    def add_data_source(self, source_name: str, fetcher: Callable[[str], Any]):
        """Add a data source for aggregation."""
        self.data_sources[source_name] = fetcher

    async def transform(
        self, resource_data: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Aggregate data from multiple sources."""
        aggregated_data = resource_data.copy()

        # Fetch data from additional sources
        uri = resource_data.get("uri", "")
        aggregated_sources = {}

        for source_name, fetcher in self.data_sources.items():
            try:
                if asyncio.iscoroutinefunction(fetcher):
                    source_data = await fetcher(uri)
                else:
                    source_data = fetcher(uri)
                aggregated_sources[source_name] = source_data
            except Exception as e:
                # Log error but continue with other sources
                aggregated_sources[source_name] = {"error": str(e)}

        # Add aggregated data
        aggregated_data["__aggregated"] = aggregated_sources

        # Add transformation metadata
        aggregated_data["__transformation"] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "sources": list(self.data_sources.keys()),
            "transformer": "AggregationTransformer",
        }

        return aggregated_data

    def should_apply(self, uri: str, subscription: "ResourceSubscription") -> bool:
        """Apply to resources that have data sources defined."""
        return len(self.data_sources) > 0


class TransformationPipeline:
    """Manages a pipeline of resource transformations."""

    def __init__(self):
        self.transformers: List[ResourceTransformer] = []
        self._enabled = True

    def add_transformer(self, transformer: ResourceTransformer):
        """Add a transformer to the pipeline."""
        self.transformers.append(transformer)

    def remove_transformer(self, transformer: ResourceTransformer):
        """Remove a transformer from the pipeline."""
        if transformer in self.transformers:
            self.transformers.remove(transformer)

    def clear(self):
        """Remove all transformers."""
        self.transformers.clear()

    def enable(self):
        """Enable the transformation pipeline."""
        self._enabled = True

    def disable(self):
        """Disable the transformation pipeline."""
        self._enabled = False

    @property
    def enabled(self) -> bool:
        """Check if pipeline is enabled."""
        return self._enabled

    async def apply(
        self,
        resource_data: Dict[str, Any],
        uri: str,
        subscription: "ResourceSubscription",
    ) -> Dict[str, Any]:
        """Apply all applicable transformations to resource data.

        Args:
            resource_data: Original resource data
            uri: Resource URI
            subscription: Subscription requesting the resource

        Returns:
            Transformed resource data
        """
        if not self._enabled or not self.transformers:
            return resource_data

        # Create transformation context
        context = {
            "uri": uri,
            "subscription_id": subscription.id,
            "connection_id": subscription.connection_id,
            "uri_pattern": subscription.uri_pattern,
            "fields": subscription.fields,
            "fragments": subscription.fragments,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        transformed_data = resource_data

        # Collect pipeline-level transformation metadata
        pipeline_metadata = {"errors": [], "applied_transformers": []}

        # Apply each transformer in sequence
        for transformer in self.transformers:
            if transformer.should_apply(uri, subscription):
                try:
                    new_transformed_data = await transformer.transform(
                        transformed_data, context
                    )

                    # Preserve any existing pipeline errors when merging transformation metadata
                    if (
                        "__transformation" in new_transformed_data
                        and "errors" in pipeline_metadata
                    ):
                        existing_errors = pipeline_metadata["errors"]
                        new_transformation_metadata = new_transformed_data.get(
                            "__transformation", {}
                        )

                        # Merge errors if the new transformer also has transformation metadata
                        if "errors" in new_transformation_metadata:
                            pipeline_metadata["errors"].extend(
                                new_transformation_metadata["errors"]
                            )

                        # Update the new data with preserved errors
                        new_transformed_data["__transformation"]["errors"] = (
                            pipeline_metadata["errors"]
                        )

                    transformed_data = new_transformed_data
                    pipeline_metadata["applied_transformers"].append(
                        transformer.__class__.__name__
                    )

                except Exception as e:
                    # Log transformation error but continue with pipeline
                    transformation_error = {
                        "transformer": transformer.__class__.__name__,
                        "error": str(e),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                    pipeline_metadata["errors"].append(transformation_error)

        # Add pipeline metadata
        if pipeline_metadata["applied_transformers"] or pipeline_metadata["errors"]:
            if "__transformation" not in transformed_data:
                transformed_data["__transformation"] = {}

            # Add pipeline-level errors
            if pipeline_metadata["errors"]:
                transformed_data["__transformation"]["errors"] = pipeline_metadata[
                    "errors"
                ]

            # Add pipeline summary
            transformed_data["__transformation"]["pipeline"] = {
                "applied_transformers": pipeline_metadata["applied_transformers"],
                "total_transformers": len(self.transformers),
                "enabled": self._enabled,
                "errors_count": len(pipeline_metadata["errors"]),
            }

        return transformed_data


@dataclass
class ResourceSubscription:
    """Represents a resource subscription with GraphQL-style field selection."""

    id: str
    connection_id: str
    uri_pattern: str
    cursor: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    # GraphQL-style field selection
    fields: Optional[List[str]] = None  # e.g., ["uri", "content.text", "metadata.size"]
    fragments: Optional[Dict[str, List[str]]] = (
        None  # e.g., {"basicInfo": ["uri", "name"]}
    )

    def matches_uri(self, uri: str) -> bool:
        """Check if URI matches subscription pattern.

        Supports:
        - Single wildcard (*) - matches within directory
        - Double wildcard (**) - matches across directories
        - Extension patterns (*.json, *.md)
        """
        # Convert ** to a pattern that matches across directories
        pattern = self.uri_pattern.replace("**", "|||DOUBLESTAR|||")
        pattern = pattern.replace("*", "|||STAR|||")

        # Escape special characters except our placeholders
        pattern = pattern.replace(".", r"\.")
        pattern = pattern.replace("?", r"\?")
        pattern = pattern.replace("[", r"\[")
        pattern = pattern.replace("]", r"\]")

        # Convert back to regex
        pattern = pattern.replace("|||DOUBLESTAR|||", ".*")
        pattern = pattern.replace("|||STAR|||", "[^/]*")

        # Add anchors
        pattern = f"^{pattern}$"

        import re

        return bool(re.match(pattern, uri))

    def apply_field_selection(self, resource_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply GraphQL-style field selection to resource data.

        Args:
            resource_data: Full resource data

        Returns:
            Filtered resource data based on field selection
        """
        if not self.fields and not self.fragments:
            # No field selection specified, return all data
            return resource_data

        result = {}

        # Process direct field selections
        if self.fields:
            for field_path in self.fields:
                value = self._extract_field_value(resource_data, field_path)
                if value is not None:
                    self._set_nested_value(result, field_path, value)

        # Process fragment selections
        if self.fragments:
            for fragment_name, fragment_fields in self.fragments.items():
                fragment_data = {}
                for field_path in fragment_fields:
                    value = self._extract_field_value(resource_data, field_path)
                    if value is not None:
                        self._set_nested_value(fragment_data, field_path, value)

                if fragment_data:
                    result[f"__{fragment_name}"] = fragment_data

        return result

    def _extract_field_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Extract field value using dot notation (e.g., 'content.text')."""
        parts = field_path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def _set_nested_value(self, data: Dict[str, Any], field_path: str, value: Any):
        """Set nested value using dot notation."""
        parts = field_path.split(".")
        current = data

        # Navigate to parent
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        # Set final value
        current[parts[-1]] = value


class CursorManager:
    """Manages cursor generation and validation for pagination."""

    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._cursors: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def generate_cursor(self) -> str:
        """Generate a unique cursor."""
        cursor_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC)

        cursor_data = f"{cursor_id}:{timestamp.isoformat()}"
        cursor = hashlib.sha256(cursor_data.encode()).hexdigest()[:16]

        self._cursors[cursor] = {"created_at": timestamp, "data": {}}

        return cursor

    def create_cursor_for_position(self, items: List[Any], position: int) -> str:
        """Create cursor for specific position in list."""
        cursor = self.generate_cursor()
        self._cursors[cursor]["data"]["position"] = position
        self._cursors[cursor]["data"]["items_hash"] = hashlib.sha256(
            str(items).encode()
        ).hexdigest()[:8]
        return cursor

    def is_valid(self, cursor: str) -> bool:
        """Check if cursor is valid and not expired."""
        if cursor not in self._cursors:
            return False

        cursor_data = self._cursors[cursor]
        age = datetime.now(UTC) - cursor_data["created_at"]

        if age > timedelta(seconds=self.ttl_seconds):
            # Clean up expired cursor
            del self._cursors[cursor]
            return False

        return True

    def get_cursor_position(self, cursor: str) -> Optional[int]:
        """Get position from cursor if valid."""
        if not self.is_valid(cursor):
            return None

        return self._cursors[cursor]["data"].get("position")

    async def cleanup_expired(self):
        """Remove expired cursors."""
        async with self._lock:
            now = datetime.now(UTC)
            expired = []

            for cursor, data in self._cursors.items():
                age = now - data["created_at"]
                if age > timedelta(seconds=self.ttl_seconds):
                    expired.append(cursor)

            for cursor in expired:
                del self._cursors[cursor]


class ResourceMonitor:
    """Monitors resources for changes."""

    def __init__(self):
        self._resource_states: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def _compute_hash(self, content: Dict[str, Any]) -> str:
        """Compute hash of resource content."""
        # Sort keys for consistent hashing
        sorted_content = json.dumps(content, sort_keys=True)
        return hashlib.sha256(sorted_content.encode()).hexdigest()

    async def register_resource(self, uri: str, content: Dict[str, Any]):
        """Register resource for monitoring."""
        async with self._lock:
            self._resource_states[uri] = {
                "hash": self._compute_hash(content),
                "content": content,
                "last_checked": datetime.now(UTC),
            }

    def is_monitored(self, uri: str) -> bool:
        """Check if resource is being monitored."""
        return uri in self._resource_states

    async def check_for_changes(
        self, uri: str, content: Dict[str, Any]
    ) -> Optional[ResourceChange]:
        """Check if resource has changed."""
        async with self._lock:
            new_hash = self._compute_hash(content)

            if uri not in self._resource_states:
                # New resource
                self._resource_states[uri] = {
                    "hash": new_hash,
                    "content": content,
                    "last_checked": datetime.now(UTC),
                }
                return ResourceChange(
                    type=ResourceChangeType.CREATED,
                    uri=uri,
                    timestamp=datetime.now(UTC),
                )

            old_hash = self._resource_states[uri]["hash"]

            if old_hash != new_hash:
                # Resource updated
                self._resource_states[uri] = {
                    "hash": new_hash,
                    "content": content,
                    "last_checked": datetime.now(UTC),
                }
                return ResourceChange(
                    type=ResourceChangeType.UPDATED,
                    uri=uri,
                    timestamp=datetime.now(UTC),
                )

            # No change
            self._resource_states[uri]["last_checked"] = datetime.now(UTC)
            return None

    async def check_for_deletion(self, uri: str) -> Optional[ResourceChange]:
        """Mark resource as deleted."""
        async with self._lock:
            if uri in self._resource_states:
                del self._resource_states[uri]
                return ResourceChange(
                    type=ResourceChangeType.DELETED,
                    uri=uri,
                    timestamp=datetime.now(UTC),
                )
            return None


class ResourceSubscriptionManager:
    """Manages resource subscriptions."""

    def __init__(
        self,
        auth_manager: Optional[AuthManager] = None,
        event_store=None,
        rate_limiter=None,
    ):
        self.auth_manager = auth_manager
        self.event_store = event_store
        self.rate_limiter = rate_limiter

        # Subscription tracking
        self._subscriptions: Dict[str, ResourceSubscription] = {}
        self._connection_subscriptions: Dict[str, Set[str]] = {}
        self._pattern_index: Dict[str, Set[str]] = {}  # pattern -> subscription IDs

        # Concurrency control
        self._lock = asyncio.Lock()

        # Notification callback
        self._notification_callback: Optional[Callable] = None

        # Resource monitoring
        self.resource_monitor = ResourceMonitor()

        # Cursor management
        self.cursor_manager = CursorManager()

        # Transformation pipeline
        self.transformation_pipeline = TransformationPipeline()

        # Cleanup task
        self._cleanup_task = None

    async def initialize(self):
        """Initialize subscription manager."""
        # Start periodic cleanup
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def shutdown(self):
        """Shutdown subscription manager."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _periodic_cleanup(self):
        """Periodically clean up expired cursors."""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self.cursor_manager.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                # Log error but continue
                pass

    def set_notification_callback(self, callback: Callable):
        """Set callback for sending notifications."""
        self._notification_callback = callback

    async def create_subscription(
        self,
        connection_id: str,
        uri_pattern: str,
        user_context: Optional[Dict[str, Any]] = None,
        cursor: Optional[str] = None,
        fields: Optional[List[str]] = None,
        fragments: Optional[Dict[str, List[str]]] = None,
    ) -> str:
        """Create a new subscription."""
        # Check rate limit
        if self.rate_limiter:
            user_id = user_context.get("user_id") if user_context else connection_id
            if not await self.rate_limiter.check_rate_limit(user_id):
                raise SubscriptionError("Rate limit exceeded")

        # Check permissions
        if self.auth_manager and user_context:
            try:
                # Use authenticate_and_authorize method if available
                if hasattr(self.auth_manager, "authenticate_and_authorize"):
                    await self.auth_manager.authenticate_and_authorize(
                        user_context, required_permission="subscribe"
                    )
                else:
                    # Fallback for mocked auth managers
                    permission_check = await self.auth_manager.check_permission(
                        user_context.get("user_id"),
                        "subscribe",
                        {"resource_pattern": uri_pattern},
                    )
                    if not permission_check.get("authorized", False):
                        raise PermissionDeniedError(
                            "Not authorized to subscribe to resources"
                        )
            except Exception as e:
                raise PermissionDeniedError("Not authorized to subscribe to resources")

        # Create subscription
        sub_id = str(uuid.uuid4())
        subscription = ResourceSubscription(
            id=sub_id,
            connection_id=connection_id,
            uri_pattern=uri_pattern,
            cursor=cursor,
            fields=fields,
            fragments=fragments,
        )

        async with self._lock:
            # Store subscription
            self._subscriptions[sub_id] = subscription

            # Track by connection
            if connection_id not in self._connection_subscriptions:
                self._connection_subscriptions[connection_id] = set()
            self._connection_subscriptions[connection_id].add(sub_id)

            # Index by pattern
            if uri_pattern not in self._pattern_index:
                self._pattern_index[uri_pattern] = set()
            self._pattern_index[uri_pattern].add(sub_id)

        # Log to event store
        if self.event_store:
            from kailash.middleware.gateway.event_store import EventType

            await self.event_store.append(
                event_type=EventType.REQUEST_COMPLETED,
                request_id=sub_id,
                data={
                    "type": "subscription.created",
                    "subscription_id": sub_id,
                    "connection_id": connection_id,
                    "uri_pattern": uri_pattern,
                    "user_id": user_context.get("user_id") if user_context else None,
                },
            )

        return sub_id

    async def create_batch_subscriptions(
        self,
        subscriptions: List[Dict[str, Any]],
        connection_id: str,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create multiple subscriptions in a single batch operation.

        Args:
            subscriptions: List of subscription requests, each containing:
                - uri_pattern: Resource URI pattern to subscribe to
                - cursor: Optional cursor for pagination
                - fields: Optional field selection
                - fragments: Optional fragment selection
                - subscription_name: Optional name for the subscription
            connection_id: Client connection ID
            user_context: Optional user context for authorization

        Returns:
            Dictionary with created subscription IDs and any errors
        """
        results = {
            "successful": [],
            "failed": [],
            "total_requested": len(subscriptions),
            "total_created": 0,
            "total_failed": 0,
        }

        # Process each subscription request
        for i, sub_request in enumerate(subscriptions):
            try:
                # Extract subscription parameters
                uri_pattern = sub_request.get("uri_pattern")
                if not uri_pattern:
                    results["failed"].append(
                        {
                            "index": i,
                            "error": "Missing required parameter: uri_pattern",
                            "request": sub_request,
                        }
                    )
                    results["total_failed"] += 1
                    continue

                cursor = sub_request.get("cursor")
                fields = sub_request.get("fields")
                fragments = sub_request.get("fragments")
                subscription_name = sub_request.get("subscription_name")

                # Create individual subscription
                subscription_id = await self.create_subscription(
                    connection_id=connection_id,
                    uri_pattern=uri_pattern,
                    user_context=user_context,
                    cursor=cursor,
                    fields=fields,
                    fragments=fragments,
                )

                # Record successful creation
                results["successful"].append(
                    {
                        "index": i,
                        "subscription_id": subscription_id,
                        "uri_pattern": uri_pattern,
                        "subscription_name": subscription_name,
                    }
                )
                results["total_created"] += 1

            except Exception as e:
                # Record failed creation
                results["failed"].append(
                    {"index": i, "error": str(e), "request": sub_request}
                )
                results["total_failed"] += 1

        # Log batch operation to event store
        if self.event_store:
            from kailash.middleware.gateway.event_store import EventType

            await self.event_store.append(
                event_type=EventType.REQUEST_COMPLETED,
                request_id=f"batch_subscribe_{connection_id}_{uuid.uuid4()}",
                data={
                    "type": "batch_subscription_created",
                    "connection_id": connection_id,
                    "total_requested": results["total_requested"],
                    "total_created": results["total_created"],
                    "total_failed": results["total_failed"],
                    "user_id": user_context.get("user_id") if user_context else None,
                },
            )

        return results

    async def remove_subscription(
        self, subscription_id: str, connection_id: str
    ) -> bool:
        """Remove a subscription."""
        async with self._lock:
            if subscription_id not in self._subscriptions:
                return False

            subscription = self._subscriptions[subscription_id]

            # Verify ownership
            if subscription.connection_id != connection_id:
                return False

            # Remove from indices
            self._connection_subscriptions[connection_id].discard(subscription_id)
            if not self._connection_subscriptions[connection_id]:
                del self._connection_subscriptions[connection_id]

            self._pattern_index[subscription.uri_pattern].discard(subscription_id)
            if not self._pattern_index[subscription.uri_pattern]:
                del self._pattern_index[subscription.uri_pattern]

            # Remove subscription
            del self._subscriptions[subscription_id]

        # Log to event store
        if self.event_store:
            from kailash.middleware.gateway.event_store import EventType

            await self.event_store.append(
                event_type=EventType.REQUEST_COMPLETED,
                request_id=subscription_id,
                data={
                    "type": "subscription.removed",
                    "subscription_id": subscription_id,
                    "connection_id": connection_id,
                },
            )

        return True

    async def remove_batch_subscriptions(
        self, subscription_ids: List[str], connection_id: str
    ) -> Dict[str, Any]:
        """Remove multiple subscriptions in a single batch operation.

        Args:
            subscription_ids: List of subscription IDs to remove
            connection_id: Client connection ID

        Returns:
            Dictionary with removal results and any errors
        """
        results = {
            "successful": [],
            "failed": [],
            "total_requested": len(subscription_ids),
            "total_removed": 0,
            "total_failed": 0,
        }

        # Process each unsubscribe request
        for i, subscription_id in enumerate(subscription_ids):
            try:
                # Attempt to remove subscription
                success = await self.remove_subscription(subscription_id, connection_id)

                if success:
                    results["successful"].append(
                        {
                            "index": i,
                            "subscription_id": subscription_id,
                            "removed": True,
                        }
                    )
                    results["total_removed"] += 1
                else:
                    results["failed"].append(
                        {
                            "index": i,
                            "subscription_id": subscription_id,
                            "error": "Subscription not found or not owned by connection",
                        }
                    )
                    results["total_failed"] += 1

            except Exception as e:
                # Record failed removal
                results["failed"].append(
                    {"index": i, "subscription_id": subscription_id, "error": str(e)}
                )
                results["total_failed"] += 1

        # Log batch operation to event store
        if self.event_store:
            from kailash.middleware.gateway.event_store import EventType

            await self.event_store.append(
                event_type=EventType.REQUEST_COMPLETED,
                request_id=f"batch_unsubscribe_{connection_id}_{uuid.uuid4()}",
                data={
                    "type": "batch_subscription_removed",
                    "connection_id": connection_id,
                    "total_requested": results["total_requested"],
                    "total_removed": results["total_removed"],
                    "total_failed": results["total_failed"],
                },
            )

        return results

    def get_subscription(self, subscription_id: str) -> Optional[ResourceSubscription]:
        """Get subscription by ID."""
        return self._subscriptions.get(subscription_id)

    def get_connection_subscriptions(self, connection_id: str) -> Set[str]:
        """Get all subscription IDs for a connection."""
        return self._connection_subscriptions.get(connection_id, set()).copy()

    async def cleanup_connection(self, connection_id: str) -> int:
        """Remove all subscriptions for a connection."""
        sub_ids = self.get_connection_subscriptions(connection_id)
        removed = 0

        for sub_id in sub_ids:
            if await self.remove_subscription(sub_id, connection_id):
                removed += 1

        return removed

    async def find_matching_subscriptions(self, uri: str) -> List[ResourceSubscription]:
        """Find all subscriptions that match a URI."""
        matching = []

        async with self._lock:
            for sub_id, subscription in self._subscriptions.items():
                if subscription.matches_uri(uri):
                    matching.append(subscription)

        return matching

    async def process_resource_change(
        self, change: Union[ResourceChange, Dict[str, Any]]
    ):
        """Process a resource change and notify subscribers."""
        # Convert dict to ResourceChange if needed
        if isinstance(change, dict):
            change = ResourceChange(
                type=ResourceChangeType(change["type"]),
                uri=change["uri"],
                timestamp=datetime.fromisoformat(change["timestamp"]),
            )

        # Find matching subscriptions
        matching_subs = await self.find_matching_subscriptions(change.uri)

        if not matching_subs:
            return

        # Send notifications per subscription (to apply individual transformations and field selection)
        if self._notification_callback:
            for subscription in matching_subs:
                # Get full resource data for transformation and field selection
                resource_data = await self._get_resource_data(change.uri)

                if resource_data:
                    # Apply transformation pipeline before field selection
                    transformed_data = await self.transformation_pipeline.apply(
                        resource_data, change.uri, subscription
                    )

                    # Apply field selection to transformed data
                    filtered_data = subscription.apply_field_selection(transformed_data)
                else:
                    filtered_data = {}

                # Create notification
                notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/resources/updated",
                    "params": {
                        "subscriptionId": subscription.id,
                        "uri": change.uri,
                        "type": change.type.value,
                        "timestamp": change.timestamp.isoformat(),
                        "data": filtered_data,
                    },
                }

                # Send to specific connection
                conn_id = subscription.connection_id

                # Check if callback is async
                if asyncio.iscoroutinefunction(self._notification_callback):
                    await self._notification_callback(conn_id, notification)
                else:
                    self._notification_callback(conn_id, notification)

        # Log to event store
        if self.event_store:
            from kailash.middleware.gateway.event_store import EventType

            await self.event_store.append(
                event_type=EventType.REQUEST_COMPLETED,
                request_id=f"resource_change_{change.uri}",
                data={
                    "type": "resource.changed",
                    "uri": change.uri,
                    "change_type": change.type.value,
                    "timestamp": change.timestamp.isoformat(),
                    "notified_subscriptions": len(matching_subs),
                },
            )

    async def _get_resource_data(self, uri: str) -> Optional[Dict[str, Any]]:
        """Get full resource data for field selection.

        This method should be overridden or configured to fetch actual resource data.
        For now, it returns basic resource information from the monitored state.
        """
        async with self.resource_monitor._lock:
            if uri in self.resource_monitor._resource_states:
                state = self.resource_monitor._resource_states[uri]
                return {
                    "uri": uri,
                    "content": state.get("content", {}),
                    "metadata": {
                        "hash": state.get("hash"),
                        "last_checked": (
                            state.get("last_checked", "").isoformat()
                            if state.get("last_checked")
                            else None
                        ),
                        "size": len(str(state.get("content", ""))),
                    },
                }

        # Fallback: return basic URI info
        return {"uri": uri, "content": {}, "metadata": {"available": False}}


class DistributedSubscriptionManager(ResourceSubscriptionManager):
    """Redis-backed distributed subscription manager for multi-instance MCP servers.

    This manager extends the base ResourceSubscriptionManager to support distributed
    deployments where multiple MCP server instances need to coordinate subscriptions
    and resource notifications across the cluster.

    Key Features:
    - Shared subscription state across server instances
    - Distributed resource change notifications
    - Automatic failover when instances go down
    - Subscription replication and consistency
    - Cross-instance notification routing
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        redis_config: Optional[Dict[str, Any]] = None,
        server_instance_id: Optional[str] = None,
        subscription_key_prefix: str = "mcp:subs:",
        notification_channel_prefix: str = "mcp:notify:",
        heartbeat_interval: int = 30,
        instance_timeout: int = 90,
        **kwargs,
    ):
        """Initialize distributed subscription manager.

        Args:
            redis_url: Redis connection URL
            redis_config: Additional Redis configuration
            server_instance_id: Unique ID for this server instance
            subscription_key_prefix: Redis key prefix for subscriptions
            notification_channel_prefix: Redis channel prefix for notifications
            heartbeat_interval: How often to send heartbeats (seconds)
            instance_timeout: When to consider an instance dead (seconds)
            **kwargs: Arguments passed to parent ResourceSubscriptionManager
        """
        super().__init__(**kwargs)

        if not REDIS_AVAILABLE:
            raise ImportError(
                "Redis support not available. Install with: pip install redis"
            )

        self.redis_url = redis_url
        self.redis_config = redis_config or {}
        self.server_instance_id = (
            server_instance_id or f"mcp_server_{uuid.uuid4().hex[:8]}"
        )
        self.subscription_key_prefix = subscription_key_prefix
        self.notification_channel_prefix = notification_channel_prefix
        self.heartbeat_interval = heartbeat_interval
        self.instance_timeout = instance_timeout

        # Redis connections
        self.redis_client: Optional[redis.Redis] = None
        self.redis_pubsub: Optional[redis.Redis] = None

        # Instance management
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._notification_listener_task: Optional[asyncio.Task] = None
        self._instance_monitor_task: Optional[asyncio.Task] = None

        # Distributed state
        self._other_instances: Set[str] = set()
        self._instance_subscriptions: Dict[str, Set[str]] = (
            {}
        )  # instance_id -> subscription_ids

        self.logger = logging.getLogger(__name__)

    async def initialize(self):
        """Initialize Redis connections and distributed state."""
        await super().initialize()

        # Connect to Redis
        self.redis_client = redis.Redis.from_url(
            self.redis_url, decode_responses=True, **self.redis_config
        )

        # Separate connection for pub/sub
        self.redis_pubsub = redis.Redis.from_url(
            self.redis_url, decode_responses=True, **self.redis_config
        )

        # Test connections
        try:
            await self.redis_client.ping()
            await self.redis_pubsub.ping()
            self.logger.info(f"Connected to Redis at {self.redis_url}")
        except Exception as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            raise

        # Register this instance
        await self._register_instance()

        # Start background tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._notification_listener_task = asyncio.create_task(
            self._notification_listener()
        )
        self._instance_monitor_task = asyncio.create_task(self._instance_monitor())

        # Load existing distributed subscriptions
        await self._load_distributed_subscriptions()

        self.logger.info(
            f"Distributed subscription manager initialized (instance: {self.server_instance_id})"
        )

    async def shutdown(self):
        """Shutdown distributed subscription manager."""
        # Cancel background tasks
        for task in [
            self._heartbeat_task,
            self._notification_listener_task,
            self._instance_monitor_task,
        ]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Unregister instance
        await self._unregister_instance()

        # Close Redis connections
        if self.redis_client:
            await self.redis_client.aclose()
        if self.redis_pubsub:
            await self.redis_pubsub.aclose()

        await super().shutdown()
        self.logger.info(
            f"Distributed subscription manager shutdown (instance: {self.server_instance_id})"
        )

    async def create_subscription(
        self, connection_id: str, uri_pattern: str, **kwargs
    ) -> str:
        """Create subscription and replicate to Redis."""
        # Create local subscription
        subscription_id = await super().create_subscription(
            connection_id, uri_pattern, **kwargs
        )

        # Replicate to Redis
        await self._replicate_subscription_to_redis(subscription_id)

        return subscription_id

    async def remove_subscription(
        self, subscription_id: str, connection_id: str
    ) -> bool:
        """Remove subscription and update Redis."""
        # Remove local subscription
        success = await super().remove_subscription(subscription_id, connection_id)

        if success:
            # Remove from Redis
            await self._remove_subscription_from_redis(subscription_id)

        return success

    async def process_resource_change(
        self, change: Union[ResourceChange, Dict[str, Any]]
    ):
        """Process resource change and distribute notifications across instances."""
        # Process locally first
        await super().process_resource_change(change)

        # Distribute to other instances via Redis
        await self._distribute_resource_change(change)

    async def _register_instance(self):
        """Register this server instance in Redis."""
        instance_key = f"mcp:instances:{self.server_instance_id}"
        instance_data = {
            "id": self.server_instance_id,
            "registered_at": datetime.now(UTC).isoformat(),
            "last_heartbeat": datetime.now(UTC).isoformat(),
            "subscriptions": 0,
        }

        # Set with expiration
        await self.redis_client.hset(instance_key, mapping=instance_data)
        await self.redis_client.expire(instance_key, self.instance_timeout)

        self.logger.info(f"Registered instance {self.server_instance_id}")

    async def _unregister_instance(self):
        """Unregister this server instance from Redis."""
        instance_key = f"mcp:instances:{self.server_instance_id}"
        await self.redis_client.delete(instance_key)

        # Clean up instance subscriptions
        await self.redis_client.delete(f"mcp:instance_subs:{self.server_instance_id}")

        self.logger.info(f"Unregistered instance {self.server_instance_id}")

    async def _heartbeat_loop(self):
        """Send periodic heartbeats to indicate this instance is alive."""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                instance_key = f"mcp:instances:{self.server_instance_id}"
                await self.redis_client.hset(
                    instance_key, "last_heartbeat", datetime.now(UTC).isoformat()
                )
                await self.redis_client.expire(instance_key, self.instance_timeout)

                # Update subscription count
                sub_count = len(self._subscriptions)
                await self.redis_client.hset(instance_key, "subscriptions", sub_count)

                self.logger.debug(
                    f"Heartbeat sent (instance: {self.server_instance_id}, subscriptions: {sub_count})"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")

    async def _instance_monitor(self):
        """Monitor other instances and handle failures."""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                # Get all instances
                instance_keys = await self.redis_client.keys("mcp:instances:*")
                current_instances = set()

                for key in instance_keys:
                    instance_data = await self.redis_client.hgetall(key)
                    if not instance_data:
                        continue

                    instance_id = instance_data.get("id")
                    if instance_id == self.server_instance_id:
                        continue

                    last_heartbeat = instance_data.get("last_heartbeat")
                    if last_heartbeat:
                        try:
                            heartbeat_time = datetime.fromisoformat(last_heartbeat)
                            age = (datetime.now(UTC) - heartbeat_time).total_seconds()

                            if age < self.instance_timeout:
                                current_instances.add(instance_id)
                            else:
                                # Instance is dead, clean up
                                await self._cleanup_dead_instance(instance_id)
                        except ValueError:
                            pass

                # Update known instances
                new_instances = current_instances - self._other_instances
                dead_instances = self._other_instances - current_instances

                if new_instances:
                    self.logger.info(f"New instances detected: {new_instances}")

                if dead_instances:
                    self.logger.info(f"Dead instances detected: {dead_instances}")

                self._other_instances = current_instances

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Instance monitor error: {e}")

    async def _cleanup_dead_instance(self, instance_id: str):
        """Clean up subscriptions from a dead instance."""
        try:
            # Get subscriptions for dead instance
            instance_subs_key = f"mcp:instance_subs:{instance_id}"
            dead_subscriptions = await self.redis_client.smembers(instance_subs_key)

            # Remove subscription data
            if dead_subscriptions:
                pipeline = self.redis_client.pipeline()
                for sub_id in dead_subscriptions:
                    sub_key = f"{self.subscription_key_prefix}{sub_id}"
                    pipeline.delete(sub_key)

                pipeline.delete(instance_subs_key)
                await pipeline.execute()

                self.logger.info(
                    f"Cleaned up {len(dead_subscriptions)} subscriptions from dead instance {instance_id}"
                )

            # Remove instance record
            await self.redis_client.delete(f"mcp:instances:{instance_id}")

        except Exception as e:
            self.logger.error(f"Error cleaning up dead instance {instance_id}: {e}")

    async def _replicate_subscription_to_redis(self, subscription_id: str):
        """Replicate subscription data to Redis."""
        subscription = self._subscriptions.get(subscription_id)
        if not subscription:
            return

        # Serialize subscription data
        sub_data = {
            "id": subscription.id,
            "connection_id": subscription.connection_id,
            "uri_pattern": subscription.uri_pattern,
            "cursor": subscription.cursor or "",
            "created_at": subscription.created_at.isoformat(),
            "fields": json.dumps(subscription.fields or []),
            "fragments": json.dumps(subscription.fragments or {}),
            "server_instance": self.server_instance_id,
        }

        # Store in Redis
        sub_key = f"{self.subscription_key_prefix}{subscription_id}"
        await self.redis_client.hset(sub_key, mapping=sub_data)

        # Track instance subscriptions
        instance_subs_key = f"mcp:instance_subs:{self.server_instance_id}"
        await self.redis_client.sadd(instance_subs_key, subscription_id)

        self.logger.debug(f"Replicated subscription {subscription_id} to Redis")

    async def _remove_subscription_from_redis(self, subscription_id: str):
        """Remove subscription data from Redis."""
        sub_key = f"{self.subscription_key_prefix}{subscription_id}"
        await self.redis_client.delete(sub_key)

        # Remove from instance tracking
        instance_subs_key = f"mcp:instance_subs:{self.server_instance_id}"
        await self.redis_client.srem(instance_subs_key, subscription_id)

        self.logger.debug(f"Removed subscription {subscription_id} from Redis")

    async def _load_distributed_subscriptions(self):
        """Load subscription data for other instances from Redis."""
        # This is for awareness only - we don't process other instances' subscriptions locally
        # but we might need this information for coordination
        try:
            instance_keys = await self.redis_client.keys("mcp:instances:*")

            for key in instance_keys:
                instance_data = await self.redis_client.hgetall(key)
                instance_id = instance_data.get("id")

                if instance_id and instance_id != self.server_instance_id:
                    # Load subscription IDs for this instance
                    instance_subs_key = f"mcp:instance_subs:{instance_id}"
                    sub_ids = await self.redis_client.smembers(instance_subs_key)
                    self._instance_subscriptions[instance_id] = set(sub_ids)

            total_distributed_subs = sum(
                len(subs) for subs in self._instance_subscriptions.values()
            )
            self.logger.info(
                f"Loaded {total_distributed_subs} distributed subscriptions from {len(self._instance_subscriptions)} instances"
            )

        except Exception as e:
            self.logger.error(f"Error loading distributed subscriptions: {e}")

    async def _distribute_resource_change(
        self, change: Union[ResourceChange, Dict[str, Any]]
    ):
        """Distribute resource change notification to other instances."""
        if not self._other_instances:
            return  # No other instances to notify

        # Convert to dict if needed
        if isinstance(change, ResourceChange):
            change_data = {
                "type": change.type.value,
                "uri": change.uri,
                "timestamp": change.timestamp.isoformat(),
                "source_instance": self.server_instance_id,
            }
        else:
            change_data = dict(change)
            change_data["source_instance"] = self.server_instance_id

        # Publish to notification channel
        channel = f"{self.notification_channel_prefix}resource_changes"
        try:
            await self.redis_client.publish(channel, json.dumps(change_data))
            self.logger.debug(
                f"Distributed resource change for {change_data['uri']} to {len(self._other_instances)} instances"
            )
        except Exception as e:
            self.logger.error(f"Error distributing resource change: {e}")

    async def _notification_listener(self):
        """Listen for distributed resource change notifications."""
        try:
            pubsub = self.redis_pubsub.pubsub()
            channel = f"{self.notification_channel_prefix}resource_changes"
            await pubsub.subscribe(channel)

            self.logger.info(
                f"Listening for distributed notifications on channel: {channel}"
            )

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        change_data = json.loads(message["data"])
                        source_instance = change_data.get("source_instance")

                        # Ignore notifications from ourselves
                        if source_instance == self.server_instance_id:
                            continue

                        # Process the resource change locally
                        # This will check local subscriptions and send notifications
                        change = ResourceChange(
                            type=ResourceChangeType(change_data["type"]),
                            uri=change_data["uri"],
                            timestamp=datetime.fromisoformat(change_data["timestamp"]),
                        )

                        # Process without re-distributing (to avoid loops)
                        await super().process_resource_change(change)

                        self.logger.debug(
                            f"Processed distributed resource change from {source_instance}: {change_data['uri']}"
                        )

                    except Exception as e:
                        self.logger.error(
                            f"Error processing distributed notification: {e}"
                        )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Notification listener error: {e}")

    def get_distributed_stats(self) -> Dict[str, Any]:
        """Get statistics about the distributed subscription system."""
        return {
            "instance_id": self.server_instance_id,
            "local_subscriptions": len(self._subscriptions),
            "other_instances": len(self._other_instances),
            "distributed_subscriptions": {
                instance_id: len(subs)
                for instance_id, subs in self._instance_subscriptions.items()
            },
            "total_distributed_subscriptions": sum(
                len(subs) for subs in self._instance_subscriptions.values()
            ),
            "redis_url": self.redis_url,
        }
