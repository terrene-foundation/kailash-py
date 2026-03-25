"""Resource resolution system for gateway.

This module provides resource reference resolution to handle non-serializable
objects like database connections, HTTP clients, and caches through the API.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from ..resources.factory import (
    CacheFactory,
    DatabasePoolFactory,
    HttpClientFactory,
    MessageQueueFactory,
    S3ClientFactory,
)
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
        credentials: Optional[Dict[str, Any]] = None
        if reference.credentials_ref:
            secret = await self.secret_manager.get_secret(reference.credentials_ref)
            if isinstance(secret, dict):
                credentials = secret
            elif isinstance(secret, str):
                credentials = {"value": secret}

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
        except Exception:
            # Register and create new pool
            factory = DatabasePoolFactory(**connection_config)

            # Health check
            async def health_check(resource: Any) -> bool:
                try:
                    async with resource.acquire() as conn:
                        await conn.fetchval("SELECT 1")
                    return True
                except Exception:
                    return False

            # Cleanup
            async def cleanup(resource: Any) -> None:
                await resource.close()

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
        except Exception:
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
        except Exception:
            factory = CacheFactory(**config)

            async def cache_health_check(resource: Any) -> bool:
                try:
                    await resource.ping()
                    return True
                except Exception:
                    return False

            async def cache_cleanup(resource: Any) -> None:
                await resource.aclose()

            self.resource_registry.register_factory(
                cache_key,
                factory,
                health_check=cache_health_check,
                cleanup_handler=cache_cleanup,
            )
            return await self.resource_registry.get_resource(cache_key)

    async def _resolve_message_queue(
        self, config: Dict[str, Any], credentials: Optional[Dict[str, Any]]
    ) -> Any:
        """Resolve message queue resource."""
        connection_config = {**config}
        queue_type = connection_config.pop("type", "rabbitmq")

        if credentials:
            for key in ["username", "password", "host", "port", "vhost"]:
                if key in credentials:
                    connection_config[key] = credentials[key]

        # Create unique key for this configuration
        config_str = json.dumps(
            {**connection_config, "type": queue_type}, sort_keys=True
        )
        mq_key = f"mq_{queue_type}_{hashlib.md5(config_str.encode()).hexdigest()[:8]}"

        try:
            return await self.resource_registry.get_resource(mq_key)
        except Exception:
            factory = MessageQueueFactory(backend=queue_type, **connection_config)

            mq_health_check: Any = None
            mq_cleanup: Any = None

            if queue_type == "rabbitmq":

                async def _rabbitmq_health(resource: Any) -> bool:
                    try:
                        channel = await resource.channel()
                        await channel.declare_queue(
                            "", exclusive=True, auto_delete=True
                        )
                        await channel.close()
                        return True
                    except Exception:
                        return False

                async def _rabbitmq_cleanup(resource: Any) -> None:
                    await resource.close()

                mq_health_check = _rabbitmq_health
                mq_cleanup = _rabbitmq_cleanup

            elif queue_type == "kafka":

                async def _kafka_health(resource: Any) -> bool:
                    try:
                        await resource.producer.partitions_for("__consumer_offsets")
                        return True
                    except Exception:
                        return False

                async def _kafka_cleanup(resource: Any) -> None:
                    await resource.close()

                mq_health_check = _kafka_health
                mq_cleanup = _kafka_cleanup

            else:

                async def _default_health(resource: Any) -> bool:
                    return True

                async def _default_cleanup(resource: Any) -> None:
                    if hasattr(resource, "close"):
                        await resource.close()
                    elif hasattr(resource, "aclose"):
                        await resource.aclose()

                mq_health_check = _default_health
                mq_cleanup = _default_cleanup

            self.resource_registry.register_factory(
                mq_key,
                factory,
                health_check=mq_health_check,
                cleanup_handler=mq_cleanup,
            )
            return await self.resource_registry.get_resource(mq_key)

    async def _resolve_s3_client(
        self, config: Dict[str, Any], credentials: Optional[Dict[str, Any]]
    ) -> Any:
        """Resolve S3 client resource."""
        connection_config = {**config}
        if credentials:
            if "access_key" in credentials:
                connection_config["aws_access_key_id"] = credentials["access_key"]
            if "secret_key" in credentials:
                connection_config["aws_secret_access_key"] = credentials["secret_key"]
            if "region" in credentials:
                connection_config["region"] = credentials["region"]
            if "endpoint_url" in credentials:
                connection_config["endpoint_url"] = credentials["endpoint_url"]

        # Create unique key for this configuration
        region = connection_config.get("region", "us-east-1")
        config_str = json.dumps(connection_config, sort_keys=True)
        s3_key = f"s3_{region}_{hashlib.md5(config_str.encode()).hexdigest()[:8]}"

        try:
            return await self.resource_registry.get_resource(s3_key)
        except Exception:
            factory = S3ClientFactory(**connection_config)

            default_bucket = connection_config.get("default_bucket", "")

            async def s3_health_check(resource: Any) -> bool:
                try:
                    if default_bucket:
                        await resource.head_bucket(Bucket=default_bucket)
                    else:
                        await resource.list_buckets()
                    return True
                except Exception:
                    return False

            async def s3_cleanup(resource: Any) -> None:
                # Use the stored context manager for proper aioboto3 cleanup
                if hasattr(resource, "_aioboto3_ctx"):
                    await resource._aioboto3_ctx.__aexit__(None, None, None)
                else:
                    await resource.close()

            self.resource_registry.register_factory(
                s3_key,
                factory,
                health_check=s3_health_check,
                cleanup_handler=s3_cleanup,
            )
            return await self.resource_registry.get_resource(s3_key)
