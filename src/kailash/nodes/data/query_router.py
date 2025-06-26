"""Intelligent query routing for optimal database connection utilization.

This module implements a query router that analyzes queries and routes them
to the most appropriate connection based on query type, connection health,
and historical performance data.
"""

import asyncio
import hashlib
import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Query classification types."""

    READ_SIMPLE = "read_simple"  # Single table SELECT
    READ_COMPLEX = "read_complex"  # JOINs, aggregations
    WRITE_SIMPLE = "write_simple"  # Single row INSERT/UPDATE/DELETE
    WRITE_BULK = "write_bulk"  # Multi-row operations
    DDL = "ddl"  # Schema modifications
    TRANSACTION = "transaction"  # Explicit transaction blocks
    UNKNOWN = "unknown"  # Unclassified queries


@dataclass
class QueryFingerprint:
    """Normalized query representation for caching and pattern matching."""

    template: str  # Query with parameters replaced
    query_type: QueryType  # Classification
    tables: Set[str]  # Tables involved
    is_read_only: bool  # True for SELECT queries
    complexity_score: float  # Estimated complexity (0-1)


@dataclass
class ConnectionInfo:
    """Information about an available connection."""

    connection_id: str
    health_score: float  # 0-100
    current_load: int  # Active queries
    capabilities: Set[str]  # e.g., {"read", "write", "ddl"}
    avg_latency_ms: float  # Recent average latency
    last_used: datetime  # For LRU routing


@dataclass
class RoutingDecision:
    """Result of routing decision."""

    connection_id: str
    decision_factors: Dict[str, Any]  # Why this connection was chosen
    alternatives: List[str]  # Other viable connections
    confidence: float  # 0-1 confidence in decision


class QueryClassifier:
    """Classifies SQL queries for routing decisions."""

    # Regex patterns for query classification
    SELECT_SIMPLE = re.compile(
        r"^\s*SELECT\s+.*?\s+FROM\s+(\w+)(?:\s+WHERE|\s*;?\s*$)",
        re.IGNORECASE | re.DOTALL,
    )
    SELECT_COMPLEX = re.compile(
        r"^\s*SELECT\s+.*?\s+FROM\s+.*?(?:JOIN|GROUP\s+BY|HAVING|UNION|INTERSECT|EXCEPT)",
        re.IGNORECASE | re.DOTALL,
    )
    INSERT_PATTERN = re.compile(r"^\s*INSERT\s+INTO", re.IGNORECASE)
    UPDATE_PATTERN = re.compile(r"^\s*UPDATE\s+", re.IGNORECASE)
    DELETE_PATTERN = re.compile(r"^\s*DELETE\s+FROM", re.IGNORECASE)
    DDL_PATTERN = re.compile(r"^\s*(?:CREATE|ALTER|DROP|TRUNCATE)\s+", re.IGNORECASE)
    TRANSACTION_PATTERN = re.compile(
        r"^\s*(?:BEGIN|START\s+TRANSACTION|COMMIT|ROLLBACK)", re.IGNORECASE
    )
    BULK_PATTERN = re.compile(
        r"(?:VALUES\s*\([^)]+\)(?:\s*,\s*\([^)]+\)){2,}|COPY\s+|BULK\s+INSERT)",
        re.IGNORECASE,
    )

    def __init__(self):
        self.classification_cache = {}
        self.max_cache_size = 10000

    def classify(self, query: str) -> QueryType:
        """Classify a SQL query into one of the defined types."""
        # Check cache first
        query_hash = hashlib.md5(query.encode()).hexdigest()
        if query_hash in self.classification_cache:
            return self.classification_cache[query_hash]

        # Clean the query
        cleaned_query = self._clean_query(query)

        # Classification logic
        query_type = self._classify_query(cleaned_query)

        # Cache the result
        if len(self.classification_cache) >= self.max_cache_size:
            # Simple LRU: remove oldest entries
            oldest_keys = list(self.classification_cache.keys())[:1000]
            for key in oldest_keys:
                del self.classification_cache[key]

        self.classification_cache[query_hash] = query_type
        return query_type

    def _clean_query(self, query: str) -> str:
        """Remove comments and normalize whitespace."""
        # Remove single-line comments
        query = re.sub(r"--[^\n]*", "", query)
        # Remove multi-line comments
        query = re.sub(r"/\*.*?\*/", "", query, flags=re.DOTALL)
        # Normalize whitespace
        query = " ".join(query.split())
        return query.strip()

    def _classify_query(self, query: str) -> QueryType:
        """Perform the actual classification."""
        # Check for transaction commands
        if self.TRANSACTION_PATTERN.match(query):
            return QueryType.TRANSACTION

        # Check for DDL
        if self.DDL_PATTERN.match(query):
            return QueryType.DDL

        # Check for bulk operations
        if self.BULK_PATTERN.search(query):
            return QueryType.WRITE_BULK

        # Check for complex SELECT
        if self.SELECT_COMPLEX.search(query):
            return QueryType.READ_COMPLEX

        # Check for simple SELECT
        if self.SELECT_SIMPLE.match(query):
            return QueryType.READ_SIMPLE

        # Check for INSERT/UPDATE/DELETE
        if (
            self.INSERT_PATTERN.match(query)
            or self.UPDATE_PATTERN.match(query)
            or self.DELETE_PATTERN.match(query)
        ):
            return QueryType.WRITE_SIMPLE

        return QueryType.UNKNOWN

    def fingerprint(
        self, query: str, parameters: Optional[List[Any]] = None
    ) -> QueryFingerprint:
        """Create a normalized fingerprint of the query."""
        cleaned_query = self._clean_query(query)
        query_type = self.classify(query)

        # Extract tables
        tables = self._extract_tables(cleaned_query)

        # Normalize parameters
        template = self._create_template(cleaned_query, parameters)

        # Calculate complexity
        complexity = self._calculate_complexity(cleaned_query, query_type)

        # Determine if read-only
        is_read_only = query_type in [QueryType.READ_SIMPLE, QueryType.READ_COMPLEX]

        return QueryFingerprint(
            template=template,
            query_type=query_type,
            tables=tables,
            is_read_only=is_read_only,
            complexity_score=complexity,
        )

    def _extract_tables(self, query: str) -> Set[str]:
        """Extract table names from query."""
        tables = set()

        # FROM clause
        from_matches = re.findall(r"FROM\s+(\w+)", query, re.IGNORECASE)
        tables.update(from_matches)

        # JOIN clauses
        join_matches = re.findall(r"JOIN\s+(\w+)", query, re.IGNORECASE)
        tables.update(join_matches)

        # INSERT INTO
        insert_matches = re.findall(r"INSERT\s+INTO\s+(\w+)", query, re.IGNORECASE)
        tables.update(insert_matches)

        # UPDATE
        update_matches = re.findall(r"UPDATE\s+(\w+)", query, re.IGNORECASE)
        tables.update(update_matches)

        # DELETE FROM
        delete_matches = re.findall(r"DELETE\s+FROM\s+(\w+)", query, re.IGNORECASE)
        tables.update(delete_matches)

        return tables

    def _create_template(self, query: str, parameters: Optional[List[Any]]) -> str:
        """Create query template with normalized parameters."""
        template = query

        # Replace string literals
        template = re.sub(r"'[^']*'", "?", template)
        template = re.sub(r'"[^"]*"', "?", template)

        # Replace numbers
        template = re.sub(r"\b\d+\.?\d*\b", "?", template)

        # Replace parameter placeholders
        template = re.sub(r"%s|\$\d+|\?", "?", template)

        return template

    def _calculate_complexity(self, query: str, query_type: QueryType) -> float:
        """Calculate query complexity score (0-1)."""
        score = 0.0

        # Base scores by type
        base_scores = {
            QueryType.READ_SIMPLE: 0.1,
            QueryType.READ_COMPLEX: 0.5,
            QueryType.WRITE_SIMPLE: 0.2,
            QueryType.WRITE_BULK: 0.6,
            QueryType.DDL: 0.8,
            QueryType.TRANSACTION: 0.3,
            QueryType.UNKNOWN: 0.5,
        }
        score = base_scores.get(query_type, 0.5)

        # Adjust for query features
        if re.search(r"\bJOIN\b", query, re.IGNORECASE):
            score += 0.1 * len(re.findall(r"\bJOIN\b", query, re.IGNORECASE))

        if re.search(r"\bGROUP\s+BY\b", query, re.IGNORECASE):
            score += 0.15

        if re.search(r"\bORDER\s+BY\b", query, re.IGNORECASE):
            score += 0.05

        if re.search(r"\bDISTINCT\b", query, re.IGNORECASE):
            score += 0.1

        # Subqueries
        if query.count("SELECT") > 1:
            score += 0.2 * (query.count("SELECT") - 1)

        return min(score, 1.0)


class PreparedStatementCache:
    """LRU cache for prepared statements with connection affinity."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: Dict[str, Dict[str, Any]] = {}  # fingerprint -> statement info
        self.usage_order = deque()  # For LRU eviction
        self.usage_stats = defaultdict(int)  # Track usage frequency

    def get(self, fingerprint: str, connection_id: str) -> Optional[Dict[str, Any]]:
        """Get cached statement if available for connection."""
        if fingerprint in self.cache:
            entry = self.cache[fingerprint]
            if connection_id in entry.get("connections", {}):
                # Update usage
                self.usage_stats[fingerprint] += 1
                self._update_usage_order(fingerprint)
                return entry
        return None

    def put(self, fingerprint: str, connection_id: str, statement_info: Dict[str, Any]):
        """Cache a prepared statement."""
        if fingerprint not in self.cache:
            # Check if we need to evict
            if len(self.cache) >= self.max_size:
                self._evict_lru()

            self.cache[fingerprint] = {
                "connections": {},
                "created_at": datetime.now(),
                "last_used": datetime.now(),
            }

        # Add connection-specific info
        self.cache[fingerprint]["connections"][connection_id] = statement_info
        self.cache[fingerprint]["last_used"] = datetime.now()
        self._update_usage_order(fingerprint)

    def invalidate(self, tables: Optional[Set[str]] = None):
        """Invalidate cached statements for specific tables or all."""
        if tables is None:
            # Clear entire cache
            self.cache.clear()
            self.usage_order.clear()
            self.usage_stats.clear()
        else:
            # Invalidate statements touching specified tables
            to_remove = []
            for fingerprint, entry in self.cache.items():
                if "tables" in entry and entry["tables"].intersection(tables):
                    to_remove.append(fingerprint)

            for fingerprint in to_remove:
                del self.cache[fingerprint]
                self.usage_stats.pop(fingerprint, None)

    def _update_usage_order(self, fingerprint: str):
        """Update LRU order."""
        if fingerprint in self.usage_order:
            self.usage_order.remove(fingerprint)
        self.usage_order.append(fingerprint)

    def _evict_lru(self):
        """Evict least recently used entry."""
        if self.usage_order:
            victim = self.usage_order.popleft()
            del self.cache[victim]
            self.usage_stats.pop(victim, None)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = len(self.cache)
        total_usage = sum(self.usage_stats.values())

        return {
            "total_entries": total_entries,
            "total_usage": total_usage,
            "hit_rate": total_usage / (total_usage + 1) if total_entries > 0 else 0,
            "avg_usage_per_entry": (
                total_usage / total_entries if total_entries > 0 else 0
            ),
            "cache_size_bytes": sum(len(str(v)) for v in self.cache.values()),
        }


class RoutingDecisionEngine:
    """Makes intelligent routing decisions based on multiple factors."""

    def __init__(
        self, health_threshold: float = 50.0, enable_read_write_split: bool = True
    ):
        self.health_threshold = health_threshold
        self.enable_read_write_split = enable_read_write_split
        self.routing_history = deque(maxlen=1000)  # Recent routing decisions
        self.connection_affinity = {}  # Track query -> connection affinity

    def select_connection(
        self,
        query_fingerprint: QueryFingerprint,
        available_connections: List[ConnectionInfo],
        transaction_context: Optional[str] = None,
    ) -> RoutingDecision:
        """Select the optimal connection for the query."""

        # Filter healthy connections
        healthy_connections = [
            c for c in available_connections if c.health_score >= self.health_threshold
        ]

        if not healthy_connections:
            # Fall back to any available connection
            healthy_connections = available_connections

        if not healthy_connections:
            raise NodeExecutionError("No available connections for routing")

        # If in transaction, must use same connection
        if transaction_context:
            for conn in healthy_connections:
                if conn.connection_id == transaction_context:
                    return RoutingDecision(
                        connection_id=conn.connection_id,
                        decision_factors={"reason": "transaction_affinity"},
                        alternatives=[],
                        confidence=1.0,
                    )
            raise NodeExecutionError(
                f"Transaction connection {transaction_context} not available"
            )

        # Apply routing strategy
        if self.enable_read_write_split and query_fingerprint.is_read_only:
            selected = self._route_read_query(query_fingerprint, healthy_connections)
        else:
            selected = self._route_write_query(query_fingerprint, healthy_connections)

        # Record decision
        self.routing_history.append(
            {
                "timestamp": datetime.now(),
                "query_type": query_fingerprint.query_type,
                "connection": selected.connection_id,
                "confidence": selected.confidence,
            }
        )

        return selected

    def _route_read_query(
        self, fingerprint: QueryFingerprint, connections: List[ConnectionInfo]
    ) -> RoutingDecision:
        """Route read queries with load balancing."""
        # Filter connections that support reads
        read_connections = [c for c in connections if "read" in c.capabilities]

        if not read_connections:
            read_connections = connections

        # Score each connection
        scores = []
        for conn in read_connections:
            score = self._calculate_connection_score(conn, fingerprint)
            scores.append((conn, score))

        # Sort by score (descending)
        scores.sort(key=lambda x: x[1], reverse=True)

        # Select best connection
        best_conn, best_score = scores[0]

        # Calculate confidence based on score distribution
        confidence = self._calculate_confidence(scores)

        return RoutingDecision(
            connection_id=best_conn.connection_id,
            decision_factors={
                "strategy": "load_balanced_read",
                "score": best_score,
                "health": best_conn.health_score,
                "load": best_conn.current_load,
            },
            alternatives=[s[0].connection_id for s in scores[1:3]],
            confidence=confidence,
        )

    def _route_write_query(
        self, fingerprint: QueryFingerprint, connections: List[ConnectionInfo]
    ) -> RoutingDecision:
        """Route write queries to primary connections."""
        # Filter connections that support writes
        write_connections = [c for c in connections if "write" in c.capabilities]

        if not write_connections:
            write_connections = connections

        # For writes, prefer the healthiest primary connection
        write_connections.sort(
            key=lambda c: (c.health_score, -c.current_load), reverse=True
        )

        best_conn = write_connections[0]

        return RoutingDecision(
            connection_id=best_conn.connection_id,
            decision_factors={
                "strategy": "primary_write",
                "health": best_conn.health_score,
                "load": best_conn.current_load,
            },
            alternatives=[c.connection_id for c in write_connections[1:3]],
            confidence=0.9 if best_conn.health_score > 80 else 0.7,
        )

    def _calculate_connection_score(
        self, conn: ConnectionInfo, fingerprint: QueryFingerprint
    ) -> float:
        """Calculate a score for connection suitability."""
        score = 0.0

        # Health score (40% weight)
        score += (conn.health_score / 100) * 0.4

        # Load score (30% weight) - inverse relationship
        max_load = 10  # Assume max 10 concurrent queries
        load_score = 1.0 - (min(conn.current_load, max_load) / max_load)
        score += load_score * 0.3

        # Latency score (20% weight) - inverse relationship
        max_latency = 100  # 100ms threshold
        latency_score = 1.0 - (min(conn.avg_latency_ms, max_latency) / max_latency)
        score += latency_score * 0.2

        # Affinity score (10% weight)
        query_key = fingerprint.template
        if query_key in self.connection_affinity:
            if self.connection_affinity[query_key] == conn.connection_id:
                score += 0.1

        return score

    def _calculate_confidence(
        self, scores: List[Tuple[ConnectionInfo, float]]
    ) -> float:
        """Calculate confidence in routing decision."""
        if len(scores) < 2:
            return 0.5

        best_score = scores[0][1]
        second_score = scores[1][1]

        # Confidence based on score separation
        score_diff = best_score - second_score

        if score_diff > 0.3:
            return 0.95
        elif score_diff > 0.2:
            return 0.85
        elif score_diff > 0.1:
            return 0.75
        else:
            return 0.65


@register_node()
class QueryRouterNode(AsyncNode):
    """
    Intelligent query routing for optimal database performance.

    This node analyzes SQL queries and routes them to the most appropriate
    connection from a WorkflowConnectionPool based on:
    - Query type (read/write)
    - Connection health and load
    - Historical performance
    - Prepared statement cache

    Parameters:
        connection_pool (str): Name of the WorkflowConnectionPool node
        enable_read_write_split (bool): Enable read/write splitting
        cache_size (int): Size of prepared statement cache
        pattern_learning (bool): Enable pattern-based optimization
        health_threshold (float): Minimum health score for routing

    Example:
        >>> router = QueryRouterNode(
        ...     name="smart_router",
        ...     connection_pool="db_pool",
        ...     enable_read_write_split=True,
        ...     cache_size=1000
        ... )
        >>>
        >>> # Query is automatically routed to optimal connection
        >>> result = await router.process({
        ...     "query": "SELECT * FROM orders WHERE status = ?",
        ...     "parameters": ["pending"]
        ... })
    """

    def __init__(self, **config):
        super().__init__(**config)

        # Configuration
        self.connection_pool_name = config.get("connection_pool")
        if not self.connection_pool_name:
            raise ValueError("connection_pool parameter is required")

        self.enable_read_write_split = config.get("enable_read_write_split", True)
        self.cache_size = config.get("cache_size", 1000)
        self.pattern_learning = config.get("pattern_learning", True)
        self.health_threshold = config.get("health_threshold", 50.0)

        # Components
        self.classifier = QueryClassifier()
        self.statement_cache = PreparedStatementCache(max_size=self.cache_size)
        self.routing_engine = RoutingDecisionEngine(
            health_threshold=self.health_threshold,
            enable_read_write_split=self.enable_read_write_split,
        )

        # Metrics
        self.metrics = {
            "queries_routed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "routing_errors": 0,
            "avg_routing_time_ms": 0.0,
        }

        # Transaction tracking
        self.active_transactions = {}  # session_id -> connection_id

        # Direct pool reference
        self._connection_pool = None

    def set_connection_pool(self, pool):
        """Set the connection pool directly.

        Args:
            pool: Connection pool instance
        """
        self._connection_pool = pool

    @classmethod
    def get_parameters(cls) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        return {
            "connection_pool": NodeParameter(
                name="connection_pool",
                type=str,
                description="Name of the WorkflowConnectionPool node to use",
                required=True,
            ),
            "enable_read_write_split": NodeParameter(
                name="enable_read_write_split",
                type=bool,
                description="Enable routing reads to replica connections",
                required=False,
                default=True,
            ),
            "cache_size": NodeParameter(
                name="cache_size",
                type=int,
                description="Maximum number of prepared statements to cache",
                required=False,
                default=1000,
            ),
            "pattern_learning": NodeParameter(
                name="pattern_learning",
                type=bool,
                description="Enable pattern-based query optimization",
                required=False,
                default=True,
            ),
            "health_threshold": NodeParameter(
                name="health_threshold",
                type=float,
                description="Minimum health score for connection routing (0-100)",
                required=False,
                default=50.0,
            ),
        }

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Route and execute a query."""
        start_time = time.time()

        try:
            # Extract query and parameters
            query = input_data.get("query")
            if not query:
                raise ValueError("'query' is required in input_data")

            parameters = input_data.get("parameters", [])
            session_id = input_data.get("session_id")

            # Get connection pool
            pool_node = self._connection_pool
            if not pool_node:
                # Try to get from runtime
                if hasattr(self, "runtime") and hasattr(self.runtime, "get_node"):
                    pool_node = self.runtime.get_node(self.connection_pool_name)
                elif hasattr(self, "runtime") and hasattr(
                    self.runtime, "resource_registry"
                ):
                    pool_node = self.runtime.resource_registry.get(
                        self.connection_pool_name
                    )
                elif hasattr(self, "context") and hasattr(
                    self.context, "resource_registry"
                ):
                    pool_node = self.context.resource_registry.get(
                        self.connection_pool_name
                    )

            if not pool_node:
                raise NodeExecutionError(
                    f"Connection pool '{self.connection_pool_name}' not found"
                )

            # Classify and fingerprint query
            fingerprint = self.classifier.fingerprint(query, parameters)

            # Get available connections
            pool_status = await pool_node.process({"operation": "get_status"})
            available_connections = self._parse_pool_status(pool_status)

            # Check for active transaction
            transaction_context = None
            if session_id and session_id in self.active_transactions:
                transaction_context = self.active_transactions[session_id]

            # Handle transaction commands
            if fingerprint.query_type == QueryType.TRANSACTION:
                return await self._handle_transaction_command(
                    query, session_id, pool_node, available_connections
                )

            # Make routing decision
            decision = self.routing_engine.select_connection(
                fingerprint, available_connections, transaction_context
            )

            # Check cache for prepared statement
            cache_key = fingerprint.template
            cached_statement = self.statement_cache.get(
                cache_key, decision.connection_id
            )

            if cached_statement:
                self.metrics["cache_hits"] += 1
            else:
                self.metrics["cache_misses"] += 1

            # Execute query on selected connection
            result = await self._execute_on_connection(
                pool_node,
                decision.connection_id,
                query,
                parameters,
                fingerprint,
                cached_statement,
            )

            # Update metrics
            self.metrics["queries_routed"] += 1
            routing_time = (time.time() - start_time) * 1000
            self.metrics["avg_routing_time_ms"] = (
                self.metrics["avg_routing_time_ms"]
                * (self.metrics["queries_routed"] - 1)
                + routing_time
            ) / self.metrics["queries_routed"]

            # Add routing metadata to result
            result["routing_metadata"] = {
                "connection_id": decision.connection_id,
                "query_type": fingerprint.query_type.value,
                "complexity_score": fingerprint.complexity_score,
                "routing_confidence": decision.confidence,
                "cache_hit": cached_statement is not None,
                "routing_time_ms": routing_time,
            }

            return result

        except Exception as e:
            self.metrics["routing_errors"] += 1
            logger.error(f"Query routing error: {str(e)}")
            raise NodeExecutionError(f"Query routing failed: {str(e)}")

    def _parse_pool_status(self, pool_status: Dict[str, Any]) -> List[ConnectionInfo]:
        """Parse pool status into ConnectionInfo objects."""
        connections = []

        for conn_id, conn_data in pool_status.get("connections", {}).items():
            connections.append(
                ConnectionInfo(
                    connection_id=conn_id,
                    health_score=conn_data.get("health_score", 0),
                    current_load=conn_data.get("active_queries", 0),
                    capabilities=set(conn_data.get("capabilities", ["read", "write"])),
                    avg_latency_ms=conn_data.get("avg_latency_ms", 0),
                    last_used=datetime.fromisoformat(
                        conn_data.get("last_used", datetime.now().isoformat())
                    ),
                )
            )

        return connections

    async def _handle_transaction_command(
        self,
        query: str,
        session_id: Optional[str],
        pool_node: Any,
        connections: List[ConnectionInfo],
    ) -> Dict[str, Any]:
        """Handle transaction control commands."""
        query_upper = query.upper().strip()

        if query_upper.startswith(("BEGIN", "START TRANSACTION")):
            if not session_id:
                raise ValueError("session_id required for transactions")

            # Select a connection for the transaction
            write_connections = [c for c in connections if "write" in c.capabilities]
            if not write_connections:
                raise NodeExecutionError("No write-capable connections available")

            # Use healthiest connection
            best_conn = max(write_connections, key=lambda c: c.health_score)
            self.active_transactions[session_id] = best_conn.connection_id

            # Execute BEGIN on selected connection
            result = await pool_node.process(
                {
                    "operation": "execute",
                    "connection_id": best_conn.connection_id,
                    "query": query,
                }
            )

            result["transaction_started"] = True
            result["connection_id"] = best_conn.connection_id
            return result

        elif query_upper.startswith(("COMMIT", "ROLLBACK")):
            if not session_id or session_id not in self.active_transactions:
                raise ValueError("No active transaction for session")

            conn_id = self.active_transactions[session_id]

            # Execute on transaction connection
            result = await pool_node.process(
                {"operation": "execute", "connection_id": conn_id, "query": query}
            )

            # Clear transaction state
            del self.active_transactions[session_id]

            result["transaction_ended"] = True
            return result

        else:
            raise ValueError(f"Unknown transaction command: {query}")

    async def _execute_on_connection(
        self,
        pool_node: Any,
        connection_id: str,
        query: str,
        parameters: List[Any],
        fingerprint: QueryFingerprint,
        cached_statement: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute query on selected connection."""

        # Build execution request
        execution_request = {
            "operation": "execute",
            "connection_id": connection_id,
            "query": query,
            "parameters": parameters,
        }

        # Add caching hint if available
        if cached_statement:
            execution_request["use_prepared"] = True
            execution_request["statement_name"] = cached_statement.get("statement_name")

        # Execute query
        result = await pool_node.process(execution_request)

        # Cache prepared statement info if not cached
        if not cached_statement and result.get("prepared_statement_name"):
            self.statement_cache.put(
                fingerprint.template,
                connection_id,
                {
                    "statement_name": result["prepared_statement_name"],
                    "tables": list(fingerprint.tables),
                    "created_at": datetime.now(),
                },
            )

        return result

    async def get_metrics(self) -> Dict[str, Any]:
        """Get router metrics and statistics."""
        cache_stats = self.statement_cache.get_stats()

        return {
            "router_metrics": self.metrics,
            "cache_stats": cache_stats,
            "active_transactions": len(self.active_transactions),
            "routing_history": {
                "total_decisions": len(self.routing_engine.routing_history),
                "recent_decisions": list(self.routing_engine.routing_history)[-10:],
            },
        }

    async def invalidate_cache(self, tables: Optional[List[str]] = None):
        """Invalidate prepared statement cache."""
        if tables:
            self.statement_cache.invalidate(set(tables))
        else:
            self.statement_cache.invalidate()

        return {"invalidated": True, "tables": tables}
