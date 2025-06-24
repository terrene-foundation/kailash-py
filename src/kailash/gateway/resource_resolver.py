"""Resource resolution system for gateway.

This module provides resource reference resolution to handle non-serializable
objects like database connections, HTTP clients, and caches through the API.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from ..resources.factory import CacheFactory, DatabasePoolFactory, HttpClientFactory
from ..resources.registry import ResourceFactory, ResourceRegistry
from .security import SecretManager

logger = logging.getLogger(__name__)


@dataclass
class ResourceReference:
    """Reference to a resource that can be resolved by the gateway."""

    type: str  # database, http_client, cache, message_queue, etc.
    config: Dict[str, Any]
    credentials_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "type": self.type,
            "config": self.config,
            "credentials_ref": self.credentials_ref,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceReference":
        """Create from dictionary."""
        return cls(
            type=data["type"],
            config=data["config"],
            credentials_ref=data.get("credentials_ref"),
        )


class ResourceResolver:
    """Resolves resource references to actual resources."""

    def __init__(
        self, resource_registry: ResourceRegistry, secret_manager: SecretManager
    ):
        self.resource_registry = resource_registry
        self.secret_manager = secret_manager
        self._resolvers = {
            "database": self._resolve_database,
            "http_client": self._resolve_http_client,
            "cache": self._resolve_cache,
            "message_queue": self._resolve_message_queue,
            "s3": self._resolve_s3_client,
        }

    async def resolve(self, reference: ResourceReference) -> Any:
        """Resolve a resource reference."""
        resolver = self._resolvers.get(reference.type)
        if not resolver:
            raise ValueError(f"Unknown resource type: {reference.type}")

        # Get credentials if needed
        credentials = None
        if reference.credentials_ref:
            credentials = await self.secret_manager.get_secret(
                reference.credentials_ref
            )

        # Resolve resource
        return await resolver(reference.config, credentials)

    async def _resolve_database(
        self, config: Dict[str, Any], credentials: Optional[Dict[str, Any]]
    ) -> Any:
        """Resolve database resource."""
        # Merge config with credentials
        connection_config = {**config}
        if credentials:
            # Only add known database credential fields
            for key in ["user", "password", "username", "host", "port", "database"]:
                if key in credentials:
                    connection_config[key] = credentials[key]

        # Create unique key for this configuration
        config_str = json.dumps(connection_config, sort_keys=True)
        pool_key = f"db_{hashlib.md5(config_str.encode()).hexdigest()[:8]}"

        try:
            # Try to get existing pool
            return await self.resource_registry.get_resource(pool_key)
        except:
            # Register and create new pool
            factory = DatabasePoolFactory(**connection_config)

            # Health check
            async def health_check(pool):
                try:
                    async with pool.acquire() as conn:
                        await conn.fetchval("SELECT 1")
                    return True
                except Exception:
                    return False

            # Cleanup
            async def cleanup(pool):
                await pool.close()

            self.resource_registry.register_factory(
                pool_key, factory, health_check=health_check, cleanup_handler=cleanup
            )
            return await self.resource_registry.get_resource(pool_key)

    async def _resolve_http_client(
        self, config: Dict[str, Any], credentials: Optional[Dict[str, Any]]
    ) -> Any:
        """Resolve HTTP client resource."""
        # Apply credentials as headers if provided
        if credentials and "headers" not in config:
            config["headers"] = {}

        if credentials:
            if "api_key" in credentials:
                config["headers"]["Authorization"] = f"Bearer {credentials['api_key']}"
            elif "token" in credentials:
                config["headers"]["Authorization"] = f"Bearer {credentials['token']}"
            elif "headers" in credentials:
                config["headers"].update(credentials["headers"])

        # Create unique key
        config_str = json.dumps(config, sort_keys=True)
        client_key = f"http_{hashlib.md5(config_str.encode()).hexdigest()[:8]}"

        try:
            return await self.resource_registry.get_resource(client_key)
        except:
            factory = HttpClientFactory(**config)

            async def cleanup(session):
                await session.close()

            self.resource_registry.register_factory(
                client_key, factory, cleanup_handler=cleanup
            )
            return await self.resource_registry.get_resource(client_key)

    async def _resolve_cache(
        self, config: Dict[str, Any], credentials: Optional[Dict[str, Any]]
    ) -> Any:
        """Resolve cache resource."""
        if credentials and "password" in credentials:
            config["password"] = credentials["password"]

        # Create unique key
        cache_key = (
            f"cache_{config.get('host', 'localhost')}_{config.get('port', 6379)}"
        )

        try:
            return await self.resource_registry.get_resource(cache_key)
        except:
            factory = CacheFactory(**config)

            async def health_check(cache):
                try:
                    await cache.ping()
                    return True
                except Exception:
                    return False

            async def cleanup(cache):
                await cache.aclose()

            self.resource_registry.register_factory(
                cache_key, factory, health_check=health_check, cleanup_handler=cleanup
            )
            return await self.resource_registry.get_resource(cache_key)

    async def _resolve_message_queue(
        self, config: Dict[str, Any], credentials: Optional[Dict[str, Any]]
    ) -> Any:
        """Resolve message queue resource."""
        # Implementation depends on the message queue system
        # This is a placeholder
        queue_type = config.get("type", "rabbitmq")

        if queue_type == "rabbitmq":
            # Would implement RabbitMQ connection
            pass
        elif queue_type == "kafka":
            # Would implement Kafka connection
            pass

        raise NotImplementedError(f"Message queue type {queue_type} not implemented")

    async def _resolve_s3_client(
        self, config: Dict[str, Any], credentials: Optional[Dict[str, Any]]
    ) -> Any:
        """Resolve S3 client resource."""
        # Implementation would depend on boto3 or aioboto3
        # This is a placeholder
        if credentials:
            if "access_key" in credentials:
                config["aws_access_key_id"] = credentials["access_key"]
            if "secret_key" in credentials:
                config["aws_secret_access_key"] = credentials["secret_key"]

        # Create unique key
        s3_key = f"s3_{config.get('region', 'us-east-1')}"

        # Would implement S3 client creation here
        raise NotImplementedError("S3 client resolution not yet implemented")
