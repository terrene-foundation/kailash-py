"""
Cache Key Generator

Generates deterministic cache keys from queries and parameters.
"""

import hashlib
import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from dataflow.classification.policy import ClassificationPolicy


class CacheKeyGenerator:
    """Generates cache keys for queries."""

    def __init__(
        self,
        prefix: str = "dataflow",
        namespace: Optional[str] = None,
        version: str = "v2",
        classification_policy: Optional["ClassificationPolicy"] = None,
    ):
        """
        Initialize key generator.

        Args:
            prefix: Global prefix for all keys
            namespace: Optional namespace (e.g., tenant ID)
            version: Cache keyspace version. Default is ``"v2"`` (BP-049
                cross-SDK keyspace; pre-fix ``v1`` entries are orphaned on
                upgrade and naturally expire). Cross-SDK contract matches
                ``kailash-rs`` v3.19.0.
            classification_policy: Optional policy used to hash classified
                PK values before they enter the key-material hash. When
                provided, PKs whose model+field pair is classified are
                routed through ``format_record_id_for_event`` before
                serialization so the raw value never appears in the JSON
                that feeds the MD5/SHA-256 digest. See issue #520.
        """
        self.prefix = prefix
        self.namespace = namespace
        self.version = version
        self._classification_policy = classification_policy

    def _safe_params(self, model_name: str, params: Any) -> Any:
        """Return a copy of ``params`` with classified PK values hashed.

        Routes ``params["id"]`` (and any ``{"id": ...}`` nested in a
        filter dict) through ``format_record_id_for_event`` when the
        classification policy marks the model's PK as classified.
        Non-dict inputs and dicts without an ``id`` key pass through
        unchanged. Mirrors the filtering contract of
        ``kailash-rs`` BP-049.
        """
        if self._classification_policy is None or not isinstance(params, dict):
            return params
        # Lazy import avoids a cycle with features/express.py.
        from dataflow.classification.event_payload import (
            format_record_id_for_event,
        )

        def _hash_id(mapping: Dict[str, Any]) -> Dict[str, Any]:
            if "id" not in mapping:
                return mapping
            safe = dict(mapping)
            safe["id"] = format_record_id_for_event(
                self._classification_policy, model_name, mapping["id"]
            )
            return safe

        safe_params = _hash_id(params)
        # Filter-style params ({"filter": {"id": ...}}) — hash the nested id.
        if isinstance(safe_params.get("filter"), dict):
            safe_params = dict(safe_params)
            safe_params["filter"] = _hash_id(safe_params["filter"])
        return safe_params

    def generate_key(
        self, model_name: str, sql: str, params: List[Any], ttl: Optional[int] = None
    ) -> str:
        """
        Generate cache key from query components.

        Args:
            model_name: Name of the model
            sql: SQL query string
            params: Query parameters
            ttl: TTL (not included in key)

        Returns:
            Deterministic cache key

        Raises:
            ValueError: If inputs are invalid
        """
        if not model_name:
            raise ValueError("Model name is required")
        if not sql:
            raise ValueError("SQL query is required")
        if model_name is None:
            raise ValueError("Model name cannot be None")

        # Normalize SQL (remove extra whitespace)
        normalized_sql = " ".join(sql.split())

        # Create key components
        components = [self.prefix]

        if self.namespace:
            components.append(self.namespace)

        components.extend(
            [model_name, self.version, self._hash_query(normalized_sql, params)]
        )

        # Join with colons
        key = ":".join(components)

        # Ensure reasonable length
        if len(key) > 250:
            # Hash the key if too long
            key_hash = hashlib.sha256(key.encode()).hexdigest()[:32]
            key = f"{self.prefix}:{model_name}:{key_hash}"

        return key

    def generate_key_from_builder(self, model_name: str, builder: Any) -> str:
        """
        Generate cache key from QueryBuilder.

        Args:
            model_name: Name of the model
            builder: QueryBuilder instance

        Returns:
            Cache key
        """
        # Get SQL and params from builder
        sql, params = builder.build_select()
        return self.generate_key(model_name, sql, params)

    def generate_express_key(
        self,
        model_name: str,
        operation: str,
        params: Any = None,
        tenant_id: Optional[str] = None,
    ) -> str:
        """Generate cache key for Express operations (no SQL).

        Produces keys like ``dataflow:v2:<tenant>:<model>:<op>:<hash>``
        where ``<tenant>`` is only included when a ``tenant_id`` is
        provided (or the generator was constructed with a namespace).
        The trailing segment is a short hash of the serialised *params*.
        When a ``classification_policy`` was configured and ``params``
        contains a classified PK under ``id``, the PK is routed through
        ``format_record_id_for_event`` BEFORE serialisation so the raw
        value never enters the hash input. See issue #520 (BP-049).

        Shape (``v2`` keyspace; BP-049 cross-SDK):

        * Without tenant/namespace: ``dataflow:v2:User:list:a1b2c3d4``
        * With tenant_id: ``dataflow:v2:tenant-a:User:list:a1b2c3d4``
        * With namespace: ``dataflow:v2:<namespace>:User:list:a1b2c3d4``

        The ``tenant_id`` argument takes precedence over the
        constructor ``namespace`` when both are supplied, so a
        multi-tenant DataFlow instance can share a single key generator
        across requests and bind the tenant per-call.

        Args:
            model_name: Name of the model (e.g. ``"User"``).
            operation: Express operation name (``"read"``, ``"list"``,
                etc.).
            params: Arbitrary JSON-serialisable parameters (optional).
            tenant_id: Per-call tenant identifier for multi-tenant
                cache partitioning. Callers that hit a ``multi_tenant``
                DataFlow MUST supply this; the Express wrapper enforces
                it before calling into the generator.

        Returns:
            Deterministic cache key.

        Raises:
            ValueError: If *model_name* or *operation* is empty/None.
        """
        if not model_name:
            raise ValueError("Model name is required")
        if not operation:
            raise ValueError("Operation is required")

        parts: list[str] = [self.prefix, self.version]
        if tenant_id is not None:
            parts.append(str(tenant_id))
        elif self.namespace:
            parts.append(self.namespace)
        parts.append(model_name)
        parts.append(operation)

        if params is not None:
            safe = self._safe_params(model_name, params)
            param_str = json.dumps(safe, sort_keys=True, default=str)
            param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
            parts.append(param_hash)

        return ":".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _hash_query(self, sql: str, params: List[Any]) -> str:
        """
        Create hash from query and parameters.

        Args:
            sql: Normalized SQL query
            params: Query parameters

        Returns:
            Hash string
        """
        # Create deterministic string representation
        query_data = {"sql": sql, "params": self._serialize_params(params)}

        # Create hash
        query_string = json.dumps(query_data, sort_keys=True, default=str)
        return hashlib.sha256(query_string.encode()).hexdigest()[:16]

    def _serialize_params(self, params: List[Any]) -> List[Any]:
        """
        Serialize parameters for consistent hashing.

        Args:
            params: Query parameters

        Returns:
            Serializable parameter list
        """
        serialized = []
        for param in params:
            if param is None:
                serialized.append("__null__")
            elif isinstance(param, (str, int, float, bool)):
                serialized.append(param)
            elif isinstance(param, (list, tuple)):
                serialized.append(list(param))
            elif isinstance(param, dict):
                serialized.append(dict(sorted(param.items())))
            else:
                # Convert to string for other types
                serialized.append(str(param))

        return serialized
