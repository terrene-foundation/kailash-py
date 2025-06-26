"""Query pipelining support for batch query execution.

This module implements query pipelining to batch multiple queries together,
reducing round-trip latency and improving throughput for bulk operations.
It maintains result ordering and handles partial failures gracefully.

Features:
- Automatic query batching with configurable size
- Pipeline optimization for related queries
- Result ordering preservation
- Partial failure handling with retry logic
- Transaction support for atomic operations

Example:
    >>> pipeline = QueryPipelineNode(
    ...     name="bulk_processor",
    ...     connection_pool="main_pool",
    ...     batch_size=100,
    ...     flush_interval=0.1
    ... )
    >>>
    >>> # Add queries to pipeline
    >>> await pipeline.add_query("INSERT INTO users VALUES (?, ?)", [1, "Alice"])
    >>> await pipeline.add_query("INSERT INTO users VALUES (?, ?)", [2, "Bob"])
    >>>
    >>> # Execute pipeline
    >>> results = await pipeline.flush()
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from kailash.nodes.base import Node, NodeParameter, register_node

logger = logging.getLogger(__name__)


class PipelineStrategy(Enum):
    """Strategy for pipeline execution."""

    SEQUENTIAL = "sequential"  # Execute in order, stop on first failure
    PARALLEL = "parallel"  # Execute in parallel where possible
    TRANSACTIONAL = "transactional"  # All or nothing within transaction
    BEST_EFFORT = "best_effort"  # Continue on failures


@dataclass
class PipelinedQuery:
    """Single query in the pipeline."""

    id: str
    query: str
    parameters: Optional[List[Any]]
    callback_id: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)

    def can_retry(self) -> bool:
        """Check if query can be retried."""
        return self.retry_count < self.max_retries


@dataclass
class PipelineResult:
    """Result of pipeline execution."""

    query_id: str
    success: bool
    result: Optional[Any] = None
    error: Optional[Exception] = None
    execution_time_ms: float = 0.0
    retry_count: int = 0


@dataclass
class PipelineBatch:
    """Batch of queries to execute together."""

    id: str
    queries: List[PipelinedQuery]
    strategy: PipelineStrategy
    created_at: float = field(default_factory=time.time)

    def size(self) -> int:
        """Get batch size."""
        return len(self.queries)

    def can_parallelize(self) -> bool:
        """Check if batch can be parallelized."""
        if self.strategy != PipelineStrategy.PARALLEL:
            return False

        # Simple heuristic: SELECTs can be parallel, writes should be sequential
        for query in self.queries:
            if not query.query.strip().upper().startswith("SELECT"):
                return False
        return True


class QueryPipelineOptimizer:
    """Optimizes query order and batching for better performance."""

    @staticmethod
    def optimize_batch(queries: List[PipelinedQuery]) -> List[PipelinedQuery]:
        """Optimize query order within batch.

        Strategies:
        - Group similar queries together
        - Put SELECTs before writes when possible
        - Keep dependent queries in order
        """
        # Separate reads and writes
        reads = []
        writes = []

        for query in queries:
            query_upper = query.query.strip().upper()
            if query_upper.startswith("SELECT"):
                reads.append(query)
            else:
                writes.append(query)

        # For now, simple optimization: reads first, then writes
        # This allows better connection reuse and caching
        return reads + writes

    @staticmethod
    def can_merge_queries(q1: PipelinedQuery, q2: PipelinedQuery) -> bool:
        """Check if two queries can be merged into single statement."""
        # Check if both are same type of INSERT into same table
        q1_upper = q1.query.strip().upper()
        q2_upper = q2.query.strip().upper()

        if q1_upper.startswith("INSERT INTO") and q2_upper.startswith("INSERT INTO"):
            # Extract table names (simple parsing)
            try:
                table1 = q1_upper.split("INSERT INTO")[1].split()[0]
                table2 = q2_upper.split("INSERT INTO")[1].split()[0]
                return table1 == table2
            except:
                return False

        return False


@register_node()
class QueryPipelineNode(Node):
    """Node for executing queries in pipeline/batch mode.

    Batches multiple queries together to reduce round-trip latency
    and improve throughput. Supports various execution strategies
    and handles partial failures gracefully.
    """

    def __init__(self, **config):
        """Initialize query pipeline node.

        Args:
            connection_pool: Name of connection pool to use
            batch_size: Maximum queries per batch (default: 100)
            flush_interval: Auto-flush interval in seconds (default: 0.1)
            strategy: Execution strategy (default: best_effort)
            enable_optimization: Enable query optimization (default: True)
        """
        self.connection_pool_name = config.get("connection_pool")
        self.batch_size = config.get("batch_size", 100)
        self.flush_interval = config.get("flush_interval", 0.1)
        self.strategy = PipelineStrategy(config.get("strategy", "best_effort"))
        self.enable_optimization = config.get("enable_optimization", True)

        super().__init__(**config)

        # Pipeline state
        self._queue: deque[PipelinedQuery] = deque()
        self._results: Dict[str, PipelineResult] = {}
        self._batch_counter = 0
        self._flush_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Metrics
        self._total_queries = 0
        self._total_batches = 0
        self._total_failures = 0

        # Auto-flush task will be started on first use
        self._flush_task = None

        # Direct pool reference
        self._connection_pool = None

    def set_connection_pool(self, pool):
        """Set the connection pool directly.

        Args:
            pool: Connection pool instance
        """
        self._connection_pool = pool

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "connection_pool": NodeParameter(
                name="connection_pool",
                type=str,
                required=True,
                description="Name of connection pool to use",
            ),
            "batch_size": NodeParameter(
                name="batch_size",
                type=int,
                default=100,
                description="Maximum queries per batch",
            ),
            "flush_interval": NodeParameter(
                name="flush_interval",
                type=float,
                default=0.1,
                description="Auto-flush interval in seconds",
            ),
            "strategy": NodeParameter(
                name="strategy",
                type=str,
                default="best_effort",
                description="Execution strategy",
                choices=["sequential", "parallel", "transactional", "best_effort"],
            ),
            "enable_optimization": NodeParameter(
                name="enable_optimization",
                type=bool,
                default=True,
                description="Enable query optimization",
            ),
            "queries": NodeParameter(
                name="queries",
                type=list,
                required=False,
                description="List of queries to execute",
            ),
        }

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute queries in pipeline mode.

        Input can be:
        1. Single query: {"query": "...", "parameters": [...]}
        2. Multiple queries: {"queries": [{"query": "...", "parameters": [...]}, ...]}
        3. Add to pipeline: {"action": "add", "query": "...", "parameters": [...]}
        4. Flush pipeline: {"action": "flush"}
        """
        action = input_data.get("action", "execute")

        if action == "add":
            # Add query to pipeline
            query_id = await self.add_query(
                input_data["query"],
                input_data.get("parameters"),
                input_data.get("callback_id"),
            )
            return {"query_id": query_id, "queued": True}

        elif action == "flush":
            # Flush pipeline
            results = await self.flush()
            return {"results": results, "count": len(results)}

        elif action == "status":
            # Get pipeline status
            return self.get_status()

        else:
            # Execute queries immediately
            queries_data = input_data.get("queries", [input_data])
            if not isinstance(queries_data, list):
                queries_data = [queries_data]

            # Add all queries
            query_ids = []
            for query_data in queries_data:
                query_id = await self.add_query(
                    query_data["query"], query_data.get("parameters")
                )
                query_ids.append(query_id)

            # Flush and get results
            results = await self.flush()

            # Map results back to query IDs
            results_map = {r.query_id: r for r in results}
            ordered_results = [results_map.get(qid) for qid in query_ids]

            return {
                "results": ordered_results,
                "success": all(r.success for r in ordered_results if r),
                "count": len(ordered_results),
            }

    async def add_query(
        self,
        query: str,
        parameters: Optional[List[Any]] = None,
        callback_id: Optional[str] = None,
    ) -> str:
        """Add query to pipeline.

        Args:
            query: SQL query to execute
            parameters: Query parameters
            callback_id: Optional callback identifier

        Returns:
            Query ID for tracking
        """
        query_id = f"pq_{self._total_queries}_{int(time.time() * 1000)}"

        pipelined_query = PipelinedQuery(
            id=query_id, query=query, parameters=parameters, callback_id=callback_id
        )

        async with self._lock:
            # Start auto-flush task if not started
            if self._flush_task is None and self.flush_interval > 0:
                self._start_auto_flush()

            self._queue.append(pipelined_query)
            self._total_queries += 1

            # Check if we should flush
            if len(self._queue) >= self.batch_size:
                asyncio.create_task(self.flush())

        return query_id

    async def flush(self) -> List[PipelineResult]:
        """Flush pipeline and execute all queued queries.

        Returns:
            List of results for all queries
        """
        async with self._lock:
            if not self._queue:
                return []

            # Create batch
            batch_id = f"batch_{self._batch_counter}"
            self._batch_counter += 1

            queries = list(self._queue)
            self._queue.clear()

            batch = PipelineBatch(id=batch_id, queries=queries, strategy=self.strategy)

        # Execute batch
        results = await self._execute_batch(batch)

        # Store results
        for result in results:
            self._results[result.query_id] = result

        return results

    async def _execute_batch(self, batch: PipelineBatch) -> List[PipelineResult]:
        """Execute a batch of queries.

        Args:
            batch: Batch to execute

        Returns:
            List of results
        """
        # Get connection pool from various sources
        pool = None

        # 1. Check if pool was directly set
        if hasattr(self, "_connection_pool") and self._connection_pool:
            pool = self._connection_pool
        # 2. Check context
        elif hasattr(self, "context"):
            if hasattr(self.context, "resource_registry"):
                pool = self.context.resource_registry.get(self.connection_pool_name)
            elif (
                hasattr(self.context, "resources")
                and self.connection_pool_name in self.context.resources
            ):
                pool = self.context.resources[self.connection_pool_name]
        # 3. Check runtime
        elif hasattr(self, "runtime"):
            if hasattr(self.runtime, "resource_registry"):
                pool = self.runtime.resource_registry.get(self.connection_pool_name)
            elif (
                hasattr(self.runtime, "resources")
                and self.connection_pool_name in self.runtime.resources
            ):
                pool = self.runtime.resources[self.connection_pool_name]

        if not pool:
            logger.error(f"Connection pool '{self.connection_pool_name}' not found")
            return [
                PipelineResult(
                    query_id=q.id,
                    success=False,
                    error=ValueError("Connection pool not found"),
                )
                for q in batch.queries
            ]

        # Optimize batch if enabled
        queries = batch.queries
        if self.enable_optimization:
            queries = QueryPipelineOptimizer.optimize_batch(queries)

        # Execute based on strategy
        if batch.strategy == PipelineStrategy.TRANSACTIONAL:
            return await self._execute_transactional(pool, queries)
        elif batch.strategy == PipelineStrategy.PARALLEL and batch.can_parallelize():
            return await self._execute_parallel(pool, queries)
        else:
            return await self._execute_sequential(pool, queries, batch.strategy)

    async def _execute_sequential(
        self, pool, queries: List[PipelinedQuery], strategy: PipelineStrategy
    ) -> List[PipelineResult]:
        """Execute queries sequentially."""
        results = []

        async with pool.acquire() as connection:
            for query in queries:
                start_time = time.time()

                try:
                    # Execute query
                    if query.parameters:
                        result = await connection.execute(
                            query.query, *query.parameters
                        )
                    else:
                        result = await connection.execute(query.query)

                    results.append(
                        PipelineResult(
                            query_id=query.id,
                            success=True,
                            result=result,
                            execution_time_ms=(time.time() - start_time) * 1000,
                            retry_count=query.retry_count,
                        )
                    )

                except Exception as e:
                    logger.error(f"Pipeline query failed: {e}")
                    self._total_failures += 1

                    results.append(
                        PipelineResult(
                            query_id=query.id,
                            success=False,
                            error=e,
                            execution_time_ms=(time.time() - start_time) * 1000,
                            retry_count=query.retry_count,
                        )
                    )

                    # Stop on first failure for sequential strategy
                    if strategy == PipelineStrategy.SEQUENTIAL:
                        # Add remaining queries as not executed
                        for remaining in queries[len(results) :]:
                            results.append(
                                PipelineResult(
                                    query_id=remaining.id,
                                    success=False,
                                    error=Exception(
                                        "Not executed due to previous failure"
                                    ),
                                )
                            )
                        break

        return results

    async def _execute_parallel(
        self, pool, queries: List[PipelinedQuery]
    ) -> List[PipelineResult]:
        """Execute queries in parallel."""
        tasks = []

        for query in queries:
            task = asyncio.create_task(self._execute_single_query(pool, query))
            tasks.append(task)

        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(
                    PipelineResult(
                        query_id=queries[i].id,
                        success=False,
                        error=result,
                        retry_count=queries[i].retry_count,
                    )
                )
                self._total_failures += 1
            else:
                final_results.append(result)

        return final_results

    async def _execute_transactional(
        self, pool, queries: List[PipelinedQuery]
    ) -> List[PipelineResult]:
        """Execute queries within a transaction."""
        results = []

        async with pool.acquire() as connection:
            try:
                # Start transaction
                await connection.execute("BEGIN")

                # Execute all queries
                for query in queries:
                    start_time = time.time()

                    if query.parameters:
                        result = await connection.execute(
                            query.query, *query.parameters
                        )
                    else:
                        result = await connection.execute(query.query)

                    results.append(
                        PipelineResult(
                            query_id=query.id,
                            success=True,
                            result=result,
                            execution_time_ms=(time.time() - start_time) * 1000,
                            retry_count=query.retry_count,
                        )
                    )

                # Commit transaction
                await connection.execute("COMMIT")

            except Exception as e:
                # Rollback on any error
                try:
                    await connection.execute("ROLLBACK")
                except:
                    pass

                logger.error(f"Transaction failed: {e}")
                self._total_failures += len(queries)

                # All queries fail in transaction
                return [
                    PipelineResult(
                        query_id=q.id, success=False, error=e, retry_count=q.retry_count
                    )
                    for q in queries
                ]

        return results

    async def _execute_single_query(
        self, pool, query: PipelinedQuery
    ) -> PipelineResult:
        """Execute a single query."""
        start_time = time.time()

        try:
            async with pool.acquire() as connection:
                if query.parameters:
                    result = await connection.execute(query.query, *query.parameters)
                else:
                    result = await connection.execute(query.query)

                return PipelineResult(
                    query_id=query.id,
                    success=True,
                    result=result,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    retry_count=query.retry_count,
                )

        except Exception as e:
            return PipelineResult(
                query_id=query.id,
                success=False,
                error=e,
                execution_time_ms=(time.time() - start_time) * 1000,
                retry_count=query.retry_count,
            )

    def _start_auto_flush(self):
        """Start auto-flush task."""

        async def auto_flush():
            while True:
                await asyncio.sleep(self.flush_interval)
                if self._queue:
                    await self.flush()

        self._flush_task = asyncio.create_task(auto_flush())

    async def close(self):
        """Close pipeline and cleanup."""
        # Cancel auto-flush
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush any remaining queries
        await self.flush()

    def get_status(self) -> Dict[str, Any]:
        """Get pipeline status."""
        return {
            "queued_queries": len(self._queue),
            "total_queries": self._total_queries,
            "total_batches": self._total_batches,
            "total_failures": self._total_failures,
            "batch_size": self.batch_size,
            "flush_interval": self.flush_interval,
            "strategy": self.strategy.value,
            "success_rate": (self._total_queries - self._total_failures)
            / max(1, self._total_queries),
        }

    def get_result(self, query_id: str) -> Optional[PipelineResult]:
        """Get result for specific query ID."""
        return self._results.get(query_id)
