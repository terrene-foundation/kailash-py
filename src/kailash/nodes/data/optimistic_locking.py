"""Optimistic locking support for enterprise-grade concurrency control.

Provides version-based concurrency control, conflict detection, and automatic
retry mechanisms to prevent lost updates in concurrent environments.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


class ConflictResolution(Enum):
    """Conflict resolution strategies."""

    FAIL_FAST = "fail_fast"  # Immediately fail on conflict
    RETRY = "retry"  # Retry operation with new version
    MERGE = "merge"  # Attempt to merge changes
    LAST_WRITER_WINS = "last_writer_wins"  # Override with new data


class LockStatus(Enum):
    """Lock operation status."""

    SUCCESS = "success"
    VERSION_CONFLICT = "version_conflict"
    RECORD_NOT_FOUND = "record_not_found"
    RETRY_EXHAUSTED = "retry_exhausted"
    MERGE_CONFLICT = "merge_conflict"


@register_node()
class OptimisticLockingNode(AsyncNode):
    """Implements optimistic locking with version fields for concurrency control.

    Provides:
    - Version-based concurrency control
    - Automatic conflict detection and resolution
    - Configurable retry strategies
    - Performance metrics for lock contention
    - Integration with existing SQL nodes

    Design Purpose:
    - Prevent lost updates in concurrent environments
    - Provide enterprise-grade data consistency
    - Support multiple conflict resolution strategies
    - Enable high-performance concurrent operations

    Examples:
        >>> # Read with version tracking
        >>> lock_manager = OptimisticLockingNode()
        >>> result = await lock_manager.execute(
        ...     action="read_with_version",
        ...     table_name="users",
        ...     record_id=123,
        ...     connection=db_connection
        ... )

        >>> # Update with version check
        >>> update_result = await lock_manager.execute(
        ...     action="update_with_version",
        ...     table_name="users",
        ...     record_id=123,
        ...     update_data={"name": "John Updated"},
        ...     expected_version=result["version"],
        ...     conflict_resolution="retry",
        ...     connection=db_connection
        ... )
    """

    def __init__(
        self,
        version_field: str = "version",
        max_retries: int = 3,
        retry_delay: float = 0.1,
        retry_backoff_multiplier: float = 2.0,
        default_conflict_resolution: ConflictResolution = ConflictResolution.RETRY,
        **kwargs,
    ):
        """Initialize optimistic locking manager."""
        super().__init__(**kwargs)

        self.version_field = version_field
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_backoff_multiplier = retry_backoff_multiplier
        self.default_conflict_resolution = default_conflict_resolution

        # Metrics tracking
        self.lock_metrics = {
            "total_operations": 0,
            "successful_operations": 0,
            "version_conflicts": 0,
            "retries_performed": 0,
            "merge_conflicts": 0,
            "avg_retry_count": 0.0,
        }

        # Conflict history for analysis
        self.conflict_history: List[Dict[str, Any]] = []

        self.logger.info(f"Initialized OptimisticLockingNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=True,
                description="Action to perform (read_with_version, update_with_version, batch_update)",
            ),
            "connection": NodeParameter(
                name="connection",
                type=Any,
                required=True,
                description="Database connection object",
            ),
            "table_name": NodeParameter(
                name="table_name",
                type=str,
                required=True,
                description="Table name for the operation",
            ),
            "record_id": NodeParameter(
                name="record_id",
                type=Any,
                required=False,
                description="Record identifier (for single record operations)",
            ),
            "record_ids": NodeParameter(
                name="record_ids",
                type=list,
                required=False,
                description="Multiple record identifiers (for batch operations)",
            ),
            "update_data": NodeParameter(
                name="update_data",
                type=dict,
                required=False,
                description="Data to update",
            ),
            "batch_updates": NodeParameter(
                name="batch_updates",
                type=list,
                required=False,
                description="List of update operations for batch processing",
            ),
            "expected_version": NodeParameter(
                name="expected_version",
                type=int,
                required=False,
                description="Expected version for conflict detection",
            ),
            "conflict_resolution": NodeParameter(
                name="conflict_resolution",
                type=str,
                required=False,
                default="retry",
                description="Conflict resolution strategy (fail_fast, retry, merge, last_writer_wins)",
            ),
            "version_field": NodeParameter(
                name="version_field",
                type=str,
                required=False,
                default="version",
                description="Name of the version field",
            ),
            "id_field": NodeParameter(
                name="id_field",
                type=str,
                required=False,
                default="id",
                description="Name of the ID field",
            ),
            "merge_strategy": NodeParameter(
                name="merge_strategy",
                type=dict,
                required=False,
                description="Merge strategy configuration for conflict resolution",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                default=30,
                description="Operation timeout in seconds",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node."""
        return {
            "success": NodeParameter(
                name="success",
                type=bool,
                description="Whether the operation succeeded",
            ),
            "status": NodeParameter(
                name="status",
                type=str,
                description="Operation status (success, version_conflict, etc.)",
            ),
            "record": NodeParameter(
                name="record",
                type=dict,
                required=False,
                description="Retrieved record with version information",
            ),
            "records": NodeParameter(
                name="records",
                type=list,
                required=False,
                description="Multiple records (for batch operations)",
            ),
            "version": NodeParameter(
                name="version",
                type=int,
                required=False,
                description="Current version of the record",
            ),
            "new_version": NodeParameter(
                name="new_version",
                type=int,
                required=False,
                description="New version after update",
            ),
            "updated": NodeParameter(
                name="updated",
                type=bool,
                required=False,
                description="Whether record was updated",
            ),
            "retry_count": NodeParameter(
                name="retry_count",
                type=int,
                required=False,
                description="Number of retries performed",
            ),
            "conflict_info": NodeParameter(
                name="conflict_info",
                type=dict,
                required=False,
                description="Information about version conflicts",
            ),
            "execution_time": NodeParameter(
                name="execution_time",
                type=float,
                description="Operation execution time",
            ),
            "metrics": NodeParameter(
                name="metrics",
                type=dict,
                required=False,
                description="Lock contention metrics",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute optimistic locking operations."""
        action = kwargs["action"]
        start_time = time.time()

        try:
            self.lock_metrics["total_operations"] += 1

            if action == "read_with_version":
                result = await self._read_with_version(kwargs)
            elif action == "update_with_version":
                result = await self._update_with_version(kwargs)
            elif action == "batch_update":
                result = await self._batch_update_with_version(kwargs)
            elif action == "get_metrics":
                result = await self._get_lock_metrics()
            elif action == "analyze_conflicts":
                result = await self._analyze_conflict_patterns()
            else:
                raise ValueError(f"Unknown action: {action}")

            execution_time = time.time() - start_time

            if result.get("success", False):
                self.lock_metrics["successful_operations"] += 1

            return {"execution_time": execution_time, **result}

        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Optimistic locking operation failed: {str(e)}")
            return {
                "success": False,
                "status": "error",
                "error": str(e),
                "execution_time": execution_time,
            }

    async def _read_with_version(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Read record with version information."""
        connection = kwargs["connection"]
        table_name = kwargs["table_name"]
        record_id = kwargs["record_id"]
        version_field = kwargs.get("version_field", self.version_field)
        id_field = kwargs.get("id_field", "id")

        try:
            # Build query to fetch record with version
            query = f"SELECT *, {version_field} FROM {table_name} WHERE {id_field} = ?"

            # Execute query
            if hasattr(connection, "execute"):
                # Synchronous connection
                cursor = connection.execute(query, [record_id])
                record = cursor.fetchone()
            else:
                # Assume async connection
                cursor = await connection.execute(query, [record_id])
                record = await cursor.fetchone()

            if record is None:
                return {
                    "success": False,
                    "status": LockStatus.RECORD_NOT_FOUND.value,
                    "error": f"Record with {id_field}={record_id} not found",
                }

            # Convert record to dict if needed
            if hasattr(record, "_asdict"):
                record_dict = record._asdict()
            elif hasattr(record, "keys"):
                record_dict = dict(record)
            else:
                # Assume it's a tuple/list with column names
                columns = [desc[0] for desc in cursor.description]
                record_dict = dict(zip(columns, record))

            current_version = record_dict.get(version_field, 0)

            return {
                "success": True,
                "status": LockStatus.SUCCESS.value,
                "record": record_dict,
                "version": current_version,
            }

        except Exception as e:
            self.logger.error(f"Failed to read record with version: {e}")
            return {
                "success": False,
                "status": "error",
                "error": str(e),
            }

    async def _update_with_version(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Update record with version check and conflict resolution."""
        connection = kwargs["connection"]
        table_name = kwargs["table_name"]
        record_id = kwargs["record_id"]
        update_data = kwargs["update_data"]
        expected_version = kwargs["expected_version"]
        conflict_resolution = ConflictResolution(
            kwargs.get("conflict_resolution", self.default_conflict_resolution.value)
        )
        version_field = kwargs.get("version_field", self.version_field)
        id_field = kwargs.get("id_field", "id")

        retry_count = 0
        current_delay = self.retry_delay

        while retry_count <= self.max_retries:
            try:
                result = await self._attempt_versioned_update(
                    connection,
                    table_name,
                    record_id,
                    update_data,
                    expected_version,
                    version_field,
                    id_field,
                )

                if result["success"]:
                    return {
                        **result,
                        "retry_count": retry_count,
                    }

                # Handle version conflict
                if result["status"] == LockStatus.VERSION_CONFLICT.value:
                    self.lock_metrics["version_conflicts"] += 1

                    # Record conflict for analysis
                    conflict_info = {
                        "timestamp": datetime.now(UTC),
                        "table_name": table_name,
                        "record_id": record_id,
                        "expected_version": expected_version,
                        "current_version": result.get("current_version"),
                        "retry_count": retry_count,
                        "resolution_strategy": conflict_resolution.value,
                    }
                    self.conflict_history.append(conflict_info)

                    # Apply conflict resolution strategy
                    if conflict_resolution == ConflictResolution.FAIL_FAST:
                        return {
                            **result,
                            "retry_count": retry_count,
                            "conflict_info": conflict_info,
                        }

                    elif conflict_resolution == ConflictResolution.RETRY:
                        if retry_count >= self.max_retries:
                            return {
                                "success": False,
                                "status": LockStatus.RETRY_EXHAUSTED.value,
                                "retry_count": retry_count,
                                "conflict_info": conflict_info,
                                "error": f"Maximum retries ({self.max_retries}) exceeded",
                            }

                        # Get current version for retry
                        read_result = await self._read_with_version(
                            {
                                "connection": connection,
                                "table_name": table_name,
                                "record_id": record_id,
                                "version_field": version_field,
                                "id_field": id_field,
                            }
                        )

                        if not read_result["success"]:
                            return read_result

                        expected_version = read_result["version"]
                        retry_count += 1
                        self.lock_metrics["retries_performed"] += 1

                        # Exponential backoff
                        await asyncio.sleep(current_delay)
                        current_delay *= self.retry_backoff_multiplier

                        continue

                    elif conflict_resolution == ConflictResolution.MERGE:
                        merge_result = await self._attempt_merge_update(
                            connection,
                            table_name,
                            record_id,
                            update_data,
                            expected_version,
                            kwargs.get("merge_strategy", {}),
                            version_field,
                            id_field,
                        )
                        return {
                            **merge_result,
                            "retry_count": retry_count,
                            "conflict_info": conflict_info,
                        }

                    elif conflict_resolution == ConflictResolution.LAST_WRITER_WINS:
                        # Force update regardless of version
                        return await self._force_update(
                            connection,
                            table_name,
                            record_id,
                            update_data,
                            version_field,
                            id_field,
                            retry_count,
                            conflict_info,
                        )

                else:
                    # Other error (record not found, etc.)
                    return {
                        **result,
                        "retry_count": retry_count,
                    }

            except Exception as e:
                self.logger.error(f"Update attempt failed: {e}")
                return {
                    "success": False,
                    "status": "error",
                    "error": str(e),
                    "retry_count": retry_count,
                }

        # Should not reach here, but fallback
        return {
            "success": False,
            "status": LockStatus.RETRY_EXHAUSTED.value,
            "retry_count": retry_count,
            "error": "Unexpected retry exhaustion",
        }

    async def _attempt_versioned_update(
        self,
        connection: Any,
        table_name: str,
        record_id: Any,
        update_data: Dict[str, Any],
        expected_version: int,
        version_field: str,
        id_field: str,
    ) -> Dict[str, Any]:
        """Attempt to update record with version check."""
        try:
            # Build update query with version check and increment
            set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
            update_query = f"""
                UPDATE {table_name}
                SET {set_clause}, {version_field} = {version_field} + 1
                WHERE {id_field} = ? AND {version_field} = ?
            """

            params = list(update_data.values()) + [record_id, expected_version]

            # Execute update
            if hasattr(connection, "execute"):
                # Synchronous connection
                result = connection.execute(update_query, params)
                rows_affected = result.rowcount
            else:
                # Assume async connection
                result = await connection.execute(update_query, params)
                rows_affected = result.rowcount

            if rows_affected == 0:
                # Check if record exists or version mismatch
                check_query = (
                    f"SELECT {version_field} FROM {table_name} WHERE {id_field} = ?"
                )

                if hasattr(connection, "execute"):
                    check_result = connection.execute(check_query, [record_id])
                    current_record = check_result.fetchone()
                else:
                    check_result = await connection.execute(check_query, [record_id])
                    current_record = await check_result.fetchone()

                if current_record is None:
                    return {
                        "success": False,
                        "status": LockStatus.RECORD_NOT_FOUND.value,
                        "error": f"Record with {id_field}={record_id} not found",
                    }
                else:
                    current_version = current_record[0]
                    return {
                        "success": False,
                        "status": LockStatus.VERSION_CONFLICT.value,
                        "error": "Version mismatch - record was modified by another transaction",
                        "expected_version": expected_version,
                        "current_version": current_version,
                    }

            return {
                "success": True,
                "status": LockStatus.SUCCESS.value,
                "updated": True,
                "new_version": expected_version + 1,
                "rows_affected": rows_affected,
            }

        except Exception as e:
            return {
                "success": False,
                "status": "error",
                "error": f"Update failed: {e}",
            }

    async def _attempt_merge_update(
        self,
        connection: Any,
        table_name: str,
        record_id: Any,
        update_data: Dict[str, Any],
        expected_version: int,
        merge_strategy: Dict[str, Any],
        version_field: str,
        id_field: str,
    ) -> Dict[str, Any]:
        """Attempt to merge conflicting updates."""
        try:
            # Read current record
            read_result = await self._read_with_version(
                {
                    "connection": connection,
                    "table_name": table_name,
                    "record_id": record_id,
                    "version_field": version_field,
                    "id_field": id_field,
                }
            )

            if not read_result["success"]:
                return read_result

            current_record = read_result["record"]
            current_version = read_result["version"]

            # Apply merge strategy
            merged_data = self._merge_record_data(
                current_record, update_data, merge_strategy
            )

            # Attempt update with current version
            return await self._attempt_versioned_update(
                connection,
                table_name,
                record_id,
                merged_data,
                current_version,
                version_field,
                id_field,
            )

        except Exception as e:
            self.lock_metrics["merge_conflicts"] += 1
            return {
                "success": False,
                "status": LockStatus.MERGE_CONFLICT.value,
                "error": f"Merge failed: {e}",
            }

    def _merge_record_data(
        self,
        current_record: Dict[str, Any],
        update_data: Dict[str, Any],
        merge_strategy: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge record data using specified strategy."""
        merged_data = {}

        # Default merge strategy: last writer wins for each field
        default_strategy = merge_strategy.get("default", "last_writer_wins")
        field_strategies = merge_strategy.get("fields", {})

        for field, new_value in update_data.items():
            strategy = field_strategies.get(field, default_strategy)
            current_value = current_record.get(field)

            if strategy == "last_writer_wins":
                merged_data[field] = new_value
            elif strategy == "keep_current":
                merged_data[field] = current_value
            elif strategy == "numeric_add":
                if isinstance(current_value, (int, float)) and isinstance(
                    new_value, (int, float)
                ):
                    merged_data[field] = current_value + new_value
                else:
                    merged_data[field] = new_value
            elif strategy == "list_append":
                if isinstance(current_value, list) and isinstance(new_value, list):
                    merged_data[field] = current_value + new_value
                else:
                    merged_data[field] = new_value
            else:
                # Default to last writer wins
                merged_data[field] = new_value

        return merged_data

    async def _force_update(
        self,
        connection: Any,
        table_name: str,
        record_id: Any,
        update_data: Dict[str, Any],
        version_field: str,
        id_field: str,
        retry_count: int,
        conflict_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Force update without version check (last writer wins)."""
        try:
            # Build update query without version check
            set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
            update_query = f"""
                UPDATE {table_name}
                SET {set_clause}, {version_field} = {version_field} + 1
                WHERE {id_field} = ?
            """

            params = list(update_data.values()) + [record_id]

            # Execute update
            if hasattr(connection, "execute"):
                result = connection.execute(update_query, params)
                rows_affected = result.rowcount
            else:
                result = await connection.execute(update_query, params)
                rows_affected = result.rowcount

            if rows_affected == 0:
                return {
                    "success": False,
                    "status": LockStatus.RECORD_NOT_FOUND.value,
                    "error": f"Record with {id_field}={record_id} not found",
                    "retry_count": retry_count,
                    "conflict_info": conflict_info,
                }

            # Get new version
            version_query = (
                f"SELECT {version_field} FROM {table_name} WHERE {id_field} = ?"
            )
            if hasattr(connection, "execute"):
                version_result = connection.execute(version_query, [record_id])
                new_version = version_result.fetchone()[0]
            else:
                version_result = await connection.execute(version_query, [record_id])
                new_version_row = await version_result.fetchone()
                new_version = new_version_row[0]

            return {
                "success": True,
                "status": LockStatus.SUCCESS.value,
                "updated": True,
                "new_version": new_version,
                "rows_affected": rows_affected,
                "retry_count": retry_count,
                "conflict_info": conflict_info,
                "forced_update": True,
            }

        except Exception as e:
            return {
                "success": False,
                "status": "error",
                "error": f"Force update failed: {e}",
                "retry_count": retry_count,
                "conflict_info": conflict_info,
            }

    async def _batch_update_with_version(
        self, kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform batch updates with version checking."""
        connection = kwargs["connection"]
        table_name = kwargs["table_name"]
        batch_updates = kwargs["batch_updates"]
        conflict_resolution = ConflictResolution(
            kwargs.get("conflict_resolution", self.default_conflict_resolution.value)
        )
        version_field = kwargs.get("version_field", self.version_field)
        id_field = kwargs.get("id_field", "id")

        results = []
        total_updated = 0
        total_conflicts = 0

        for update_item in batch_updates:
            record_id = update_item["record_id"]
            update_data = update_item["update_data"]
            expected_version = update_item["expected_version"]

            # Perform individual update
            update_kwargs = {
                "connection": connection,
                "table_name": table_name,
                "record_id": record_id,
                "update_data": update_data,
                "expected_version": expected_version,
                "conflict_resolution": conflict_resolution.value,
                "version_field": version_field,
                "id_field": id_field,
            }

            result = await self._update_with_version(update_kwargs)
            results.append({"record_id": record_id, **result})

            if result.get("success"):
                total_updated += 1
            elif result.get("status") == LockStatus.VERSION_CONFLICT.value:
                total_conflicts += 1

        return {
            "success": True,
            "status": "batch_completed",
            "results": results,
            "total_operations": len(batch_updates),
            "total_updated": total_updated,
            "total_conflicts": total_conflicts,
            "success_rate": total_updated / len(batch_updates) if batch_updates else 0,
        }

    async def _get_lock_metrics(self) -> Dict[str, Any]:
        """Get current lock contention metrics."""
        total_ops = self.lock_metrics["total_operations"]

        if total_ops > 0:
            self.lock_metrics["avg_retry_count"] = (
                self.lock_metrics["retries_performed"] / total_ops
            )

        return {
            "success": True,
            "metrics": dict(self.lock_metrics),
            "conflict_rate": (
                self.lock_metrics["version_conflicts"] / total_ops
                if total_ops > 0
                else 0
            ),
            "success_rate": (
                self.lock_metrics["successful_operations"] / total_ops
                if total_ops > 0
                else 0
            ),
        }

    async def _analyze_conflict_patterns(self) -> Dict[str, Any]:
        """Analyze conflict patterns for optimization insights."""
        if not self.conflict_history:
            return {
                "success": True,
                "analysis": "No conflicts recorded yet",
            }

        # Analyze conflict patterns
        table_conflicts = {}
        retry_patterns = {}

        for conflict in self.conflict_history:
            table = conflict["table_name"]
            retry_count = conflict["retry_count"]

            table_conflicts[table] = table_conflicts.get(table, 0) + 1
            retry_patterns[retry_count] = retry_patterns.get(retry_count, 0) + 1

        # Find hotspot tables
        hotspot_tables = sorted(
            table_conflicts.items(), key=lambda x: x[1], reverse=True
        )[:5]

        return {
            "success": True,
            "analysis": {
                "total_conflicts": len(self.conflict_history),
                "hotspot_tables": hotspot_tables,
                "retry_distribution": retry_patterns,
                "avg_retries": sum(
                    conflict["retry_count"] for conflict in self.conflict_history
                )
                / len(self.conflict_history),
                "recommendations": self._generate_optimization_recommendations(
                    table_conflicts, retry_patterns
                ),
            },
        }

    def _generate_optimization_recommendations(
        self, table_conflicts: Dict[str, int], retry_patterns: Dict[int, int]
    ) -> List[str]:
        """Generate optimization recommendations based on conflict patterns."""
        recommendations = []

        # High conflict tables
        high_conflict_tables = [
            table
            for table, conflicts in table_conflicts.items()
            if conflicts > self.lock_metrics["total_operations"] * 0.1
        ]

        if high_conflict_tables:
            recommendations.append(
                f"Consider partitioning or optimizing queries for high-conflict tables: {high_conflict_tables}"
            )

        # High retry rates
        total_retries = sum(retry_patterns.values())
        high_retry_rate = (
            sum(
                count
                for retry_count, count in retry_patterns.items()
                if retry_count >= self.max_retries
            )
            / total_retries
            if total_retries > 0
            else 0
        )

        if high_retry_rate > 0.2:
            recommendations.append(
                "High retry exhaustion rate detected. Consider increasing max_retries or using different conflict resolution strategy."
            )

        # Merge opportunities
        if self.lock_metrics["merge_conflicts"] > 0:
            recommendations.append(
                "Merge conflicts detected. Review merge strategies for better conflict resolution."
            )

        return recommendations
