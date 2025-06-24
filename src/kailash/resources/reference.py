"""
Resource References - JSON-serializable references to resources.

This module enables resources to be referenced in JSON APIs by providing
a serializable reference format.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class ResourceReference:
    """
    Reference to a resource that can be resolved by the gateway.

    This class provides a JSON-serializable way to reference resources
    in API calls, solving the problem of passing non-serializable objects.

    Example:
        ```python
        # Create a reference to a database
        db_ref = ResourceReference(
            type="database",
            config={
                "host": "localhost",
                "database": "myapp"
            },
            credentials_ref="db_credentials"
        )

        # Convert to JSON
        json_ref = db_ref.to_json()

        # Use in API call
        response = await client.execute_workflow(
            workflow_id="process_data",
            inputs={"data": [1, 2, 3]},
            resources={"db": db_ref}
        )
        ```

    Attributes:
        type: The type of resource (database, http_client, cache, etc.)
        config: Configuration parameters for the resource
        credentials_ref: Optional reference to credentials in secret manager
        name: Optional name to reference a pre-registered resource
    """

    type: str
    config: Dict[str, Any]
    credentials_ref: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to JSON-serializable dictionary.

        Returns:
            Dictionary representation of the reference
        """
        data = {"type": self.type, "config": self.config}

        if self.credentials_ref:
            data["credentials_ref"] = self.credentials_ref

        if self.name:
            data["name"] = self.name

        return data

    def to_json(self) -> str:
        """
        Convert to JSON string.

        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceReference":
        """
        Create from dictionary.

        Args:
            data: Dictionary with reference data

        Returns:
            ResourceReference instance
        """
        return cls(
            type=data["type"],
            config=data["config"],
            credentials_ref=data.get("credentials_ref"),
            name=data.get("name"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ResourceReference":
        """
        Create from JSON string.

        Args:
            json_str: JSON string representation

        Returns:
            ResourceReference instance
        """
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def for_registered_resource(cls, name: str) -> "ResourceReference":
        """
        Create a reference to a pre-registered resource.

        This is a shorthand for referencing resources that are already
        registered in the ResourceRegistry.

        Args:
            name: Name of the registered resource

        Returns:
            ResourceReference instance

        Example:
            ```python
            # Reference a pre-registered database
            db_ref = ResourceReference.for_registered_resource("main_db")
            ```
        """
        return cls(type="registered", config={}, name=name)


def create_database_reference(
    host: str,
    database: str,
    backend: str = "postgresql",
    port: Optional[int] = None,
    credentials_ref: Optional[str] = None,
    **kwargs,
) -> ResourceReference:
    """
    Helper to create a database resource reference.

    Args:
        host: Database host
        database: Database name
        backend: Database backend (postgresql, mysql, sqlite)
        port: Database port (uses default if not specified)
        credentials_ref: Reference to credentials in secret manager
        **kwargs: Additional configuration

    Returns:
        ResourceReference for a database

    Example:
        ```python
        db_ref = create_database_reference(
            host="db.example.com",
            database="production",
            credentials_ref="prod_db_creds"
        )
        ```
    """
    config = {"backend": backend, "host": host, "database": database, **kwargs}

    if port:
        config["port"] = port

    return ResourceReference(
        type="database", config=config, credentials_ref=credentials_ref
    )


def create_http_client_reference(
    base_url: str,
    backend: str = "aiohttp",
    timeout: int = 30,
    credentials_ref: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    **kwargs,
) -> ResourceReference:
    """
    Helper to create an HTTP client resource reference.

    Args:
        base_url: Base URL for the HTTP client
        backend: HTTP client backend (aiohttp, httpx)
        timeout: Request timeout in seconds
        credentials_ref: Reference to credentials for auth headers
        headers: Additional headers
        **kwargs: Additional configuration

    Returns:
        ResourceReference for an HTTP client

    Example:
        ```python
        api_ref = create_http_client_reference(
            base_url="https://api.example.com",
            timeout=60,
            credentials_ref="api_key"
        )
        ```
    """
    config = {"backend": backend, "base_url": base_url, "timeout": timeout, **kwargs}

    if headers:
        config["headers"] = headers

    return ResourceReference(
        type="http_client", config=config, credentials_ref=credentials_ref
    )


def create_cache_reference(
    backend: str = "redis",
    host: str = "localhost",
    port: Optional[int] = None,
    **kwargs,
) -> ResourceReference:
    """
    Helper to create a cache resource reference.

    Args:
        backend: Cache backend (redis, memcached, memory)
        host: Cache server host
        port: Cache server port
        **kwargs: Additional configuration

    Returns:
        ResourceReference for a cache

    Example:
        ```python
        cache_ref = create_cache_reference(
            backend="redis",
            host="cache.example.com"
        )
        ```
    """
    config = {"backend": backend, "host": host, **kwargs}

    if port:
        config["port"] = port

    return ResourceReference(type="cache", config=config)


def create_message_queue_reference(
    backend: str,
    host: str = "localhost",
    port: Optional[int] = None,
    credentials_ref: Optional[str] = None,
    **kwargs,
) -> ResourceReference:
    """
    Helper to create a message queue resource reference.

    Args:
        backend: Message queue backend (rabbitmq, kafka, redis)
        host: Message queue host
        port: Message queue port
        credentials_ref: Reference to credentials
        **kwargs: Additional configuration

    Returns:
        ResourceReference for a message queue

    Example:
        ```python
        mq_ref = create_message_queue_reference(
            backend="rabbitmq",
            host="mq.example.com",
            credentials_ref="mq_creds"
        )
        ```
    """
    config = {"backend": backend, "host": host, **kwargs}

    if port:
        config["port"] = port

    return ResourceReference(
        type="message_queue", config=config, credentials_ref=credentials_ref
    )
