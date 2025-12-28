"""Redis node for data operations.

This module provides a Redis node for performing various Redis operations
including get, set, hget, hset, hgetall, and more.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union

import redis
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


@register_node()
class RedisNode(Node):
    """Node for Redis operations.

    Supports common Redis operations including:
    - String operations: get, set, delete
    - Hash operations: hget, hset, hgetall
    - List operations: lpush, rpush, lrange
    - Set operations: sadd, smembers
    - Sorted set operations: zadd, zrange

    Example:
        >>> # String operations
        >>> redis_node = RedisNode(
        ...     host="localhost",
        ...     port=6379,
        ...     operation="set",
        ...     key="user:123",
        ...     value="John Doe"
        ... )
        >>> result = redis_node.execute()
        >>> # result = {"success": True, "result": "OK"}

        >>> # Hash operations
        >>> redis_node = RedisNode(
        ...     host="localhost",
        ...     port=6379,
        ...     operation="hgetall",
        ...     key="user:123:profile"
        ... )
        >>> result = redis_node.execute()
        >>> # result = {"name": "John", "age": "30", "city": "NYC"}
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        operation: str = "get",
        key: Optional[str] = None,
        value: Optional[Any] = None,
        field: Optional[str] = None,
        fields: Optional[List[str]] = None,
        ttl: Optional[int] = None,
        decode_responses: bool = True,
        **kwargs,
    ):
        """Initialize Redis node.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (if required)
            operation: Operation to perform (get, set, hget, hset, etc.)
            key: Redis key
            value: Value for set operations
            field: Field name for hash operations
            fields: Multiple fields for hash operations
            ttl: Time to live in seconds
            decode_responses: Whether to decode byte responses to strings
            **kwargs: Additional parameters
        """
        super().__init__(**kwargs)

        # Store all parameters in config for validation
        self.config.update(
            {
                "host": host,
                "port": port,
                "db": db,
                "password": password,
                "operation": operation,
                "key": key,
                "value": value,
                "field": field,
                "fields": fields,
                "ttl": ttl,
                "decode_responses": decode_responses,
            }
        )

        # Also store as instance attributes for backward compatibility
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.operation = operation
        self._client = None  # Initialize to avoid __del__ error
        self.key = key
        self.value = value
        self.field = field
        self.fields = fields
        self.ttl = ttl
        self.decode_responses = decode_responses

    @classmethod
    def get_parameters(cls) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        return {
            "host": NodeParameter(
                name="host",
                type=str,
                required=False,
                default="localhost",
                description="Redis host",
            ),
            "port": NodeParameter(
                name="port",
                type=int,
                required=False,
                default=6379,
                description="Redis port",
            ),
            "db": NodeParameter(
                name="db",
                type=int,
                required=False,
                default=0,
                description="Redis database number",
            ),
            "password": NodeParameter(
                name="password", type=str, required=False, description="Redis password"
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Redis operation (get, set, hget, hset, hgetall, etc.)",
            ),
            "key": NodeParameter(
                name="key",
                type=str,
                required=False,
                description="Redis key",
                input=True,
            ),
            "value": NodeParameter(
                name="value",
                type=Any,
                required=False,
                description="Value for set operations",
                input=True,
            ),
            "field": NodeParameter(
                name="field", type=str, required=False, description="Hash field name"
            ),
            "fields": NodeParameter(
                name="fields",
                type=list,
                required=False,
                description="Multiple hash fields",
            ),
            "ttl": NodeParameter(
                name="ttl",
                type=int,
                required=False,
                description="Time to live in seconds",
            ),
            "decode_responses": NodeParameter(
                name="decode_responses",
                type=bool,
                required=False,
                default=True,
                description="Decode byte responses to strings",
            ),
            "result": NodeParameter(
                name="result",
                type=Any,
                required=False,
                description="Operation result",
                output=True,
            ),
            "success": NodeParameter(
                name="success",
                type=bool,
                required=False,
                description="Operation success status",
                output=True,
            ),
        }

    def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if not self._client:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=self.decode_responses,
            )
        return self._client

    def execute(
        self, key: Optional[str] = None, value: Optional[Any] = None, **kwargs
    ) -> Dict[str, Any]:
        """Execute Redis operation.

        Args:
            key: Override key from config
            value: Override value from config
            **kwargs: Additional runtime parameters

        Returns:
            Dict with result and optional metadata
        """
        # Use runtime parameters if provided
        key = key or self.key or kwargs.get("key")
        value = (
            value
            if value is not None
            else (self.value if self.value is not None else kwargs.get("value"))
        )

        if not key and self.operation not in ["ping", "info", "flushdb"]:
            raise NodeExecutionError("Key is required for this operation")

        try:
            client = self._get_client()
            result = None

            # String operations
            if self.operation == "get":
                result = client.get(key)

            elif self.operation == "set":
                if value is None:
                    raise NodeExecutionError("Value is required for set operation")

                # Serialize non-string values
                if not isinstance(value, (str, bytes)):
                    value = json.dumps(value)

                if self.ttl:
                    result = client.setex(key, self.ttl, value)
                else:
                    result = client.set(key, value)

            elif self.operation == "delete":
                result = client.delete(key)

            # Hash operations
            elif self.operation == "hget":
                if not self.field:
                    raise NodeExecutionError("Field is required for hget operation")
                result = client.hget(key, self.field)

            elif self.operation == "hset":
                if not self.field:
                    raise NodeExecutionError("Field is required for hset operation")
                if value is None:
                    raise NodeExecutionError("Value is required for hset operation")

                # Serialize non-string values
                if not isinstance(value, (str, bytes)):
                    value = json.dumps(value)

                result = client.hset(key, self.field, value)

            elif self.operation == "hgetall":
                result = client.hgetall(key)
                # Convert to regular dict for JSON serialization
                if result:
                    result = dict(result)

            elif self.operation == "hmget":
                if not self.fields:
                    raise NodeExecutionError("Fields are required for hmget operation")
                values = client.hmget(key, self.fields)
                result = dict(zip(self.fields, values))

            # List operations
            elif self.operation == "lpush":
                if value is None:
                    raise NodeExecutionError("Value is required for lpush operation")
                result = client.lpush(key, value)

            elif self.operation == "rpush":
                if value is None:
                    raise NodeExecutionError("Value is required for rpush operation")
                result = client.rpush(key, value)

            elif self.operation == "lrange":
                start = kwargs.get("start", 0)
                end = kwargs.get("end", -1)
                result = client.lrange(key, start, end)

            # Set operations
            elif self.operation == "sadd":
                if value is None:
                    raise NodeExecutionError("Value is required for sadd operation")
                result = client.sadd(key, value)

            elif self.operation == "smembers":
                result = list(client.smembers(key))

            # Sorted set operations
            elif self.operation == "zadd":
                if value is None or "score" not in kwargs:
                    raise NodeExecutionError(
                        "Value and score are required for zadd operation"
                    )
                result = client.zadd(key, {value: kwargs["score"]})

            elif self.operation == "zrange":
                start = kwargs.get("start", 0)
                end = kwargs.get("end", -1)
                result = client.zrange(
                    key, start, end, withscores=kwargs.get("withscores", False)
                )

            # Utility operations
            elif self.operation == "exists":
                result = client.exists(key)

            elif self.operation == "ttl":
                result = client.ttl(key)

            elif self.operation == "ping":
                result = client.ping()

            elif self.operation == "info":
                result = client.info()

            elif self.operation == "flushdb":
                result = client.flushdb()

            else:
                raise NodeExecutionError(f"Unsupported operation: {self.operation}")

            # Handle Redis OK response
            if (
                result is True
                or (isinstance(result, bytes) and result == b"OK")
                or result == "OK"
            ):
                return {"result": result, "success": True}

            return {"result": result}

        except redis.RedisError as e:
            logger.error(f"Redis error: {e}")
            raise NodeExecutionError(f"Redis operation failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise NodeExecutionError(f"Unexpected error: {str(e)}")
        finally:
            # Don't close the connection - keep it for connection pooling
            pass

    def __del__(self):
        """Clean up Redis connection."""
        if self._client:
            try:
                self._client.close()
            except:
                pass
