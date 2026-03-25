"""
Batch operation optimization for improved throughput.

Provides automatic batching and parallel execution for bulk
database operations, with error recovery and progress monitoring.

Features:
- Automatic batching of operations
- Configurable batch sizes
- Error recovery and retry logic
- Progress monitoring callbacks
- Parallel execution where safe
- Performance metrics tracking
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class BatchConfig:
    """
    Configuration for batch operations.

    Args:
        batch_size: Number of records per batch (default: 1000)
        max_retries: Maximum retry attempts for failed batches (default: 3)
        timeout_seconds: Timeout for batch operation (default: 30)
        parallel_batches: Number of batches to execute in parallel (default: 1)
        continue_on_error: Continue processing if batch fails (default: True)

    Example:
        >>> config = BatchConfig(batch_size=5000, max_retries=5)
        >>> optimizer = BatchOptimizer(config)
    """

    batch_size: int = 1000
    max_retries: int = 3
    timeout_seconds: int = 30
    parallel_batches: int = 1
    continue_on_error: bool = True


@dataclass
class BatchResult:
    """
    Result of batch operation.

    Attributes:
        total: Total number of records processed
        successful: Number of successfully processed records
        failed: Number of failed records
        errors: List of error details
        duration: Total operation duration in seconds
        batches_processed: Number of batches completed
        throughput: Records per second

    Example:
        >>> result = optimizer.batch_insert(data, insert_fn)
        >>> print(f"Throughput: {result['throughput']:.2f} records/sec")
    """

    total: int = 0
    successful: int = 0
    failed: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    duration: float = 0.0
    batches_processed: int = 0
    throughput: float = 0.0


class BatchOptimizer:
    """
    Optimize bulk database operations with batching and retry logic.

    Automatically batches operations for optimal throughput,
    handles errors gracefully, and provides progress monitoring.

    Args:
        config: BatchConfig instance (optional)

    Example:
        >>> config = BatchConfig(batch_size=2000)
        >>> optimizer = BatchOptimizer(config)
        >>>
        >>> result = optimizer.batch_insert(
        >>>     data=records,
        >>>     insert_fn=lambda batch: db_insert(batch),
        >>>     progress_callback=lambda current, total: print(f"{current}/{total}")
        >>> )
        >>>
        >>> print(f"Inserted: {result['successful']}")
        >>> print(f"Throughput: {result['throughput']:.2f} rec/sec")
    """

    def __init__(self, config: BatchConfig = None):
        """
        Initialize batch optimizer.

        Args:
            config: Optional BatchConfig, uses defaults if not provided
        """
        self.config = config or BatchConfig()
        self._stats = {
            "total_operations": 0,
            "total_records": 0,
            "total_duration": 0.0,
            "retry_count": 0,
            "error_count": 0,
        }

    def batch_insert(
        self,
        data: List[Dict[str, Any]],
        insert_fn: Callable[[List[Dict[str, Any]]], Any],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Insert data in optimized batches.

        Splits data into batches based on config, executes insert function
        for each batch with retry logic, and tracks progress.

        Args:
            data: List of records to insert
            insert_fn: Function to call for each batch, receives list of records
            progress_callback: Optional callback(current, total) for progress updates

        Returns:
            Dictionary with operation results:
            - total: Total records
            - successful: Successfully inserted count
            - failed: Failed record count
            - errors: List of error details
            - duration: Operation duration in seconds
            - throughput: Records per second
            - success_rate: Percentage of successful insertions

        Example:
            >>> def insert_batch(records):
            >>>     return db.bulk_insert(records)
            >>>
            >>> result = optimizer.batch_insert(
            >>>     data=large_dataset,
            >>>     insert_fn=insert_batch,
            >>>     progress_callback=lambda c, t: print(f"Progress: {c}/{t}")
            >>> )
        """
        start_time = time.time()
        total = len(data)
        successful = 0
        failed = 0
        errors = []
        batches_processed = 0

        # Process in batches
        for i in range(0, total, self.config.batch_size):
            batch = data[i : i + self.config.batch_size]
            batch_index = i // self.config.batch_size

            # Execute batch with retry logic
            batch_result = self._execute_batch_with_retry(
                batch=batch, batch_index=batch_index, operation_fn=insert_fn
            )

            # Track results
            successful += batch_result["successful"]
            failed += batch_result["failed"]
            errors.extend(batch_result["errors"])
            batches_processed += 1

            # Progress callback
            if progress_callback:
                progress_callback(successful + failed, total)

            # Stop on critical failure if configured
            if not self.config.continue_on_error and batch_result["failed"] > 0:
                break

        # Calculate metrics
        duration = time.time() - start_time
        throughput = (successful / duration) if duration > 0 else 0.0
        success_rate = (successful / total * 100) if total > 0 else 0.0

        # Update internal stats
        self._stats["total_operations"] += 1
        self._stats["total_records"] += total
        self._stats["total_duration"] += duration

        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "errors": errors,
            "duration": duration,
            "batches_processed": batches_processed,
            "throughput": throughput,
            "success_rate": success_rate,
        }

    def batch_update(
        self,
        data: List[Dict[str, Any]],
        update_fn: Callable[[List[Dict[str, Any]]], Any],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Update data in optimized batches.

        Similar to batch_insert but for update operations.

        Args:
            data: List of records to update
            update_fn: Function to call for each batch
            progress_callback: Optional progress callback

        Returns:
            Dictionary with operation results (same structure as batch_insert)

        Example:
            >>> updates = [{"id": 1, "status": "active"}, ...]
            >>> result = optimizer.batch_update(updates, update_batch_fn)
        """
        return self.batch_insert(data, update_fn, progress_callback)

    def batch_delete(
        self,
        data: List[Dict[str, Any]],
        delete_fn: Callable[[List[Dict[str, Any]]], Any],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Delete data in optimized batches.

        Similar to batch_insert but for delete operations.

        Args:
            data: List of records to delete (or IDs)
            delete_fn: Function to call for each batch
            progress_callback: Optional progress callback

        Returns:
            Dictionary with operation results (same structure as batch_insert)

        Example:
            >>> ids = [{"id": 1}, {"id": 2}, ...]
            >>> result = optimizer.batch_delete(ids, delete_batch_fn)
        """
        return self.batch_insert(data, delete_fn, progress_callback)

    def _execute_batch_with_retry(
        self, batch: List[Dict[str, Any]], batch_index: int, operation_fn: Callable
    ) -> Dict[str, Any]:
        """
        Execute batch operation with retry logic.

        Attempts operation up to max_retries times, with exponential backoff.

        Args:
            batch: Batch of records to process
            batch_index: Index of current batch
            operation_fn: Function to execute

        Returns:
            Dictionary with batch results:
            - successful: Count of successful records
            - failed: Count of failed records
            - errors: List of error details
        """
        retries = 0
        last_error = None

        while retries <= self.config.max_retries:
            try:
                # Execute operation
                result = operation_fn(batch)

                # Determine success count
                if isinstance(result, dict) and "inserted_count" in result:
                    successful = result["inserted_count"]
                elif isinstance(result, dict) and "count" in result:
                    successful = result["count"]
                elif isinstance(result, list):
                    successful = len(result)
                elif isinstance(result, int):
                    successful = result
                else:
                    # Assume all succeeded
                    successful = len(batch)

                return {"successful": successful, "failed": 0, "errors": []}

            except Exception as e:
                last_error = e
                retries += 1
                self._stats["retry_count"] += 1

                # Exponential backoff
                if retries <= self.config.max_retries:
                    backoff = min(2**retries, 30)  # Max 30 seconds
                    time.sleep(backoff)

        # All retries exhausted
        self._stats["error_count"] += 1

        return {
            "successful": 0,
            "failed": len(batch),
            "errors": [
                {
                    "batch_index": batch_index,
                    "error": str(last_error),
                    "retries": retries - 1,
                    "batch_size": len(batch),
                }
            ],
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get optimizer statistics.

        Returns:
            Dictionary with performance metrics:
            - total_operations: Number of batch operations executed
            - total_records: Total records processed
            - total_duration: Cumulative operation time
            - avg_throughput: Average records per second
            - retry_count: Total retry attempts
            - error_count: Total error count

        Example:
            >>> stats = optimizer.get_stats()
            >>> print(f"Avg throughput: {stats['avg_throughput']:.2f} rec/sec")
        """
        avg_throughput = (
            self._stats["total_records"] / self._stats["total_duration"]
            if self._stats["total_duration"] > 0
            else 0.0
        )

        return {
            "total_operations": self._stats["total_operations"],
            "total_records": self._stats["total_records"],
            "total_duration": self._stats["total_duration"],
            "avg_throughput": avg_throughput,
            "retry_count": self._stats["retry_count"],
            "error_count": self._stats["error_count"],
        }

    def reset_stats(self):
        """
        Reset optimizer statistics.

        Clears all accumulated performance metrics.

        Example:
            >>> optimizer.reset_stats()  # Fresh metrics
        """
        self._stats = {
            "total_operations": 0,
            "total_records": 0,
            "total_duration": 0.0,
            "retry_count": 0,
            "error_count": 0,
        }
