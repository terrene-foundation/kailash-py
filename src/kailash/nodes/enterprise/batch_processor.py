"""Batch processing node for optimized operations with rate limiting and progress tracking.

This module provides intelligent batch processing capabilities that optimize
operations for APIs, databases, and data processing tasks. It includes
rate limiting, parallel processing, progress tracking, and automatic
error recovery.

Key Features:
- Intelligent batching strategies
- API rate limit awareness
- Parallel processing support
- Progress tracking and reporting
- Automatic retry and error recovery
- Memory management
- Configurable batch sizes
"""

import asyncio
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union

from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError


@register_node()
class BatchProcessorNode(Node):
    """Node for intelligent batch processing with optimization and rate limiting.

    This node processes large datasets or operations in optimized batches,
    providing rate limiting, parallel processing, progress tracking, and
    automatic error recovery for enterprise-scale operations.

    Key capabilities:
    1. Intelligent batching strategies
    2. API rate limit awareness
    3. Parallel processing support
    4. Progress tracking and reporting
    5. Automatic retry and error recovery
    6. Memory management optimization

    Example:
        >>> processor = BatchProcessorNode()
        >>> result = processor.execute(
        ...     operation="process_data",
        ...     data_items=large_dataset,
        ...     batch_size=100,
        ...     processing_function="data_transformation",
        ...     rate_limit_per_second=10,
        ...     parallel_workers=4,
        ...     retry_failed_batches=True
        ... )
    """

    def get_metadata(self) -> NodeMetadata:
        """Get node metadata for discovery and orchestration."""
        return NodeMetadata(
            name="Batch Processor Node",
            description="Intelligent batch processing with optimization and rate limiting",
            tags={"enterprise", "batch", "processing", "optimization", "parallel"},
            version="1.0.0",
            author="Kailash SDK",
        )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for batch processing operations."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="process_data",
                description="Operation: process_data, api_batch_calls, database_batch_operations",
            ),
            "data_items": NodeParameter(
                name="data_items",
                type=list,
                required=False,
                description="List of data items to process in batches",
            ),
            "batch_size": NodeParameter(
                name="batch_size",
                type=int,
                required=False,
                default=100,
                description="Number of items to process per batch",
            ),
            "processing_function": NodeParameter(
                name="processing_function",
                type=str,
                required=False,
                description="Name of the processing function to apply to each batch",
            ),
            "processing_code": NodeParameter(
                name="processing_code",
                type=str,
                required=False,
                description="Python code to execute for each batch",
            ),
            "rate_limit_per_second": NodeParameter(
                name="rate_limit_per_second",
                type=float,
                required=False,
                default=10.0,
                description="Maximum operations per second (rate limiting)",
            ),
            "parallel_workers": NodeParameter(
                name="parallel_workers",
                type=int,
                required=False,
                default=1,
                description="Number of parallel workers for processing",
            ),
            "retry_failed_batches": NodeParameter(
                name="retry_failed_batches",
                type=bool,
                required=False,
                default=True,
                description="Whether to retry failed batches",
            ),
            "max_retries": NodeParameter(
                name="max_retries",
                type=int,
                required=False,
                default=3,
                description="Maximum number of retries for failed batches",
            ),
            "retry_delay": NodeParameter(
                name="retry_delay",
                type=float,
                required=False,
                default=1.0,
                description="Delay between retries in seconds",
            ),
            "progress_callback": NodeParameter(
                name="progress_callback",
                type=str,
                required=False,
                description="Function name to call for progress updates",
            ),
            "memory_limit_mb": NodeParameter(
                name="memory_limit_mb",
                type=int,
                required=False,
                default=1024,
                description="Memory limit in MB for batch processing",
            ),
            "adaptive_batch_size": NodeParameter(
                name="adaptive_batch_size",
                type=bool,
                required=False,
                default=True,
                description="Whether to adapt batch size based on performance",
            ),
            "api_endpoint": NodeParameter(
                name="api_endpoint",
                type=str,
                required=False,
                description="API endpoint for batch API calls",
            ),
            "api_headers": NodeParameter(
                name="api_headers",
                type=dict,
                required=False,
                default={},
                description="Headers for API requests",
            ),
            "database_config": NodeParameter(
                name="database_config",
                type=dict,
                required=False,
                description="Database configuration for batch database operations",
            ),
        }

    def __init__(self, **kwargs):
        """Initialize the BatchProcessorNode."""
        super().__init__(**kwargs)
        self._processing_stats = {
            "total_items": 0,
            "processed_items": 0,
            "failed_items": 0,
            "total_batches": 0,
            "successful_batches": 0,
            "failed_batches": 0,
            "start_time": None,
            "end_time": None,
            "processing_rate": 0.0,
        }

    def _create_batches(
        self, data_items: List[Any], batch_size: int
    ) -> List[List[Any]]:
        """Create batches from the data items."""
        batches = []
        for i in range(0, len(data_items), batch_size):
            batch = data_items[i : i + batch_size]
            batches.append(batch)
        return batches

    def _calculate_optimal_batch_size(
        self,
        total_items: int,
        rate_limit: float,
        parallel_workers: int,
        memory_limit_mb: int,
    ) -> int:
        """Calculate optimal batch size based on constraints."""
        # Estimate memory per item (rough heuristic: 1KB per item)
        estimated_memory_per_item = 1024  # bytes
        max_items_by_memory = (
            memory_limit_mb * 1024 * 1024
        ) // estimated_memory_per_item

        # Calculate based on rate limiting
        # If we have parallel workers, we can process more items per second
        effective_rate = rate_limit * parallel_workers

        # Target processing time per batch (1-10 seconds)
        target_batch_time = min(10.0, max(1.0, 60.0 / effective_rate))
        rate_based_batch_size = int(effective_rate * target_batch_time)

        # Use minimum of constraints, but ensure at least 1 item per batch
        optimal_size = max(
            1, min(max_items_by_memory, rate_based_batch_size, total_items)
        )

        return optimal_size

    def _execute_processing_code(
        self, batch: List[Any], processing_code: str
    ) -> Dict[str, Any]:
        """Execute custom processing code on a batch."""
        try:
            # Create execution context
            exec_globals = {
                "__builtins__": __builtins__,
                "batch": batch,
                "len": len,
                "range": range,
                "enumerate": enumerate,
                "datetime": datetime,
            }

            # Execute the code
            exec(processing_code, exec_globals)

            # Get the result (expect 'result' variable to be set)
            if "result" in exec_globals:
                return {
                    "success": True,
                    "result": exec_globals["result"],
                    "processed_count": len(batch),
                }
            else:
                return {
                    "success": False,
                    "error": "Processing code must set 'result' variable",
                    "processed_count": 0,
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "processed_count": 0,
            }

    def _process_single_batch(
        self,
        batch: List[Any],
        batch_index: int,
        processing_code: Optional[str] = None,
        processing_function: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a single batch of data."""
        batch_start_time = time.time()

        try:
            if processing_code:
                result = self._execute_processing_code(batch, processing_code)
            elif processing_function:
                # For this example, we'll use a simple default processing
                # In a real implementation, this would look up the function
                result = {
                    "success": True,
                    "result": [f"processed_{item}" for item in batch],
                    "processed_count": len(batch),
                }
            else:
                # Default processing: just pass through with metadata
                result = {
                    "success": True,
                    "result": batch,
                    "processed_count": len(batch),
                }

            batch_end_time = time.time()
            processing_time = batch_end_time - batch_start_time

            return {
                "batch_index": batch_index,
                "success": result["success"],
                "result": result["result"],
                "processed_count": result["processed_count"],
                "processing_time": processing_time,
                "items_per_second": (
                    len(batch) / processing_time
                    if processing_time > 0
                    else float("inf")
                ),
                "error": result.get("error"),
            }

        except Exception as e:
            batch_end_time = time.time()
            processing_time = batch_end_time - batch_start_time

            return {
                "batch_index": batch_index,
                "success": False,
                "result": None,
                "processed_count": 0,
                "processing_time": processing_time,
                "items_per_second": 0.0,
                "error": str(e),
            }

    def _process_batch_with_retry(
        self,
        batch: List[Any],
        batch_index: int,
        max_retries: int,
        retry_delay: float,
        processing_code: Optional[str] = None,
        processing_function: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a batch with retry logic."""
        last_result = None

        for attempt in range(max_retries + 1):
            if attempt > 0:
                time.sleep(retry_delay * (2 ** (attempt - 1)))  # Exponential backoff

            result = self._process_single_batch(
                batch, batch_index, processing_code, processing_function
            )

            if result["success"]:
                if attempt > 0:
                    result["retry_attempts"] = attempt
                return result

            last_result = result

        # All retries failed
        last_result["retry_attempts"] = max_retries
        last_result["final_failure"] = True
        return last_result

    def _update_progress(
        self,
        processed_batches: int,
        total_batches: int,
        processed_items: int,
        total_items: int,
        start_time: float,
        progress_callback: Optional[str] = None,
    ):
        """Update progress and call progress callback if provided."""
        current_time = time.time()
        elapsed_time = current_time - start_time

        batch_progress = processed_batches / total_batches if total_batches > 0 else 0
        item_progress = processed_items / total_items if total_items > 0 else 0

        # Calculate rates
        batches_per_second = processed_batches / elapsed_time if elapsed_time > 0 else 0
        items_per_second = processed_items / elapsed_time if elapsed_time > 0 else 0

        # Estimate time remaining
        if batches_per_second > 0:
            remaining_batches = total_batches - processed_batches
            estimated_time_remaining = remaining_batches / batches_per_second
        else:
            estimated_time_remaining = float("inf")

        progress_info = {
            "batch_progress": batch_progress,
            "item_progress": item_progress,
            "processed_batches": processed_batches,
            "total_batches": total_batches,
            "processed_items": processed_items,
            "total_items": total_items,
            "elapsed_time": elapsed_time,
            "batches_per_second": batches_per_second,
            "items_per_second": items_per_second,
            "estimated_time_remaining": estimated_time_remaining,
        }

        # Call progress callback if provided
        if progress_callback:
            try:
                # Enterprise security: Use safe callback resolution instead of eval
                if callable(progress_callback):
                    # Direct callable
                    progress_callback(progress_info)
                elif isinstance(progress_callback, str):
                    # String callback - validate against safe functions only
                    import importlib

                    parts = progress_callback.split(".")
                    if len(parts) >= 2:
                        module_name = ".".join(parts[:-1])
                        func_name = parts[-1]
                        try:
                            # Only allow importlib for known safe modules
                            if module_name in ["logging", "sys", "json"]:
                                module = importlib.import_module(module_name)
                                callback_func = getattr(module, func_name)
                                if callable(callback_func):
                                    callback_func(progress_info)
                        except (ImportError, AttributeError):
                            pass
            except:
                pass  # Ignore callback errors

        return progress_info

    def _process_data_batches(
        self,
        data_items: List[Any],
        batch_size: int,
        processing_code: Optional[str] = None,
        processing_function: Optional[str] = None,
        rate_limit_per_second: float = 10.0,
        parallel_workers: int = 1,
        retry_failed_batches: bool = True,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        progress_callback: Optional[str] = None,
        adaptive_batch_size: bool = True,
        memory_limit_mb: int = 1024,
    ) -> Dict[str, Any]:
        """Process data items in batches."""
        start_time = time.time()

        # Calculate optimal batch size if adaptive
        if adaptive_batch_size:
            optimal_batch_size = self._calculate_optimal_batch_size(
                len(data_items),
                rate_limit_per_second,
                parallel_workers,
                memory_limit_mb,
            )
            batch_size = min(batch_size, optimal_batch_size)

        # Create batches
        batches = self._create_batches(data_items, batch_size)
        total_batches = len(batches)

        # Initialize tracking
        self._processing_stats.update(
            {
                "total_items": len(data_items),
                "total_batches": total_batches,
                "start_time": start_time,
            }
        )

        successful_results = []
        failed_results = []
        processed_items = 0

        # Calculate delay between batches for rate limiting
        batch_delay = (
            1.0 / (rate_limit_per_second / batch_size)
            if rate_limit_per_second > 0
            else 0
        )

        if parallel_workers == 1:
            # Sequential processing
            for i, batch in enumerate(batches):
                if i > 0 and batch_delay > 0:
                    time.sleep(batch_delay)

                if retry_failed_batches:
                    result = self._process_batch_with_retry(
                        batch,
                        i,
                        max_retries,
                        retry_delay,
                        processing_code,
                        processing_function,
                    )
                else:
                    result = self._process_single_batch(
                        batch, i, processing_code, processing_function
                    )

                if result["success"]:
                    successful_results.append(result)
                    processed_items += result["processed_count"]
                else:
                    failed_results.append(result)

                # Update progress
                self._update_progress(
                    i + 1,
                    total_batches,
                    processed_items,
                    len(data_items),
                    start_time,
                    progress_callback,
                )

        else:
            # Parallel processing
            with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
                # Submit all batches
                future_to_batch = {}
                for i, batch in enumerate(batches):
                    if retry_failed_batches:
                        future = executor.submit(
                            self._process_batch_with_retry,
                            batch,
                            i,
                            max_retries,
                            retry_delay,
                            processing_code,
                            processing_function,
                        )
                    else:
                        future = executor.submit(
                            self._process_single_batch,
                            batch,
                            i,
                            processing_code,
                            processing_function,
                        )
                    future_to_batch[future] = (i, batch)

                # Process completed batches
                completed_batches = 0
                for future in as_completed(future_to_batch):
                    batch_index, batch = future_to_batch[future]

                    try:
                        result = future.result()

                        if result["success"]:
                            successful_results.append(result)
                            processed_items += result["processed_count"]
                        else:
                            failed_results.append(result)

                        completed_batches += 1

                        # Update progress
                        self._update_progress(
                            completed_batches,
                            total_batches,
                            processed_items,
                            len(data_items),
                            start_time,
                            progress_callback,
                        )

                        # Rate limiting for parallel processing
                        if batch_delay > 0:
                            time.sleep(batch_delay / parallel_workers)

                    except Exception as e:
                        failed_results.append(
                            {
                                "batch_index": batch_index,
                                "success": False,
                                "error": str(e),
                                "processed_count": 0,
                            }
                        )
                        completed_batches += 1

        end_time = time.time()
        total_processing_time = end_time - start_time

        # Update final stats
        self._processing_stats.update(
            {
                "processed_items": processed_items,
                "failed_items": len(data_items) - processed_items,
                "successful_batches": len(successful_results),
                "failed_batches": len(failed_results),
                "end_time": end_time,
                "processing_rate": (
                    processed_items / total_processing_time
                    if total_processing_time > 0
                    else 0
                ),
            }
        )

        # Compile all results
        all_successful_results = []
        for result in successful_results:
            if isinstance(result["result"], list):
                all_successful_results.extend(result["result"])
            else:
                all_successful_results.append(result["result"])

        return {
            "success": len(failed_results) == 0,
            "processed_items": processed_items,
            "failed_items": len(data_items) - processed_items,
            "total_batches": total_batches,
            "successful_batches": len(successful_results),
            "failed_batches": len(failed_results),
            "processing_time": total_processing_time,
            "processing_rate": (
                processed_items / total_processing_time
                if total_processing_time > 0
                else 0
            ),
            "batch_size_used": batch_size,
            "results": all_successful_results,
            "successful_batch_details": successful_results,
            "failed_batch_details": failed_results,
            "statistics": self._processing_stats,
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute batch processing operation."""
        operation = kwargs.get("operation", "process_data")

        if operation == "process_data":
            data_items = kwargs.get("data_items", [])
            if not data_items:
                raise NodeConfigurationError(
                    "data_items is required for process_data operation"
                )

            return self._process_data_batches(
                data_items=data_items,
                batch_size=kwargs.get("batch_size", 100),
                processing_code=kwargs.get("processing_code"),
                processing_function=kwargs.get("processing_function"),
                rate_limit_per_second=kwargs.get("rate_limit_per_second", 10.0),
                parallel_workers=kwargs.get("parallel_workers", 1),
                retry_failed_batches=kwargs.get("retry_failed_batches", True),
                max_retries=kwargs.get("max_retries", 3),
                retry_delay=kwargs.get("retry_delay", 1.0),
                progress_callback=kwargs.get("progress_callback"),
                adaptive_batch_size=kwargs.get("adaptive_batch_size", True),
                memory_limit_mb=kwargs.get("memory_limit_mb", 1024),
            )

        elif operation == "api_batch_calls":
            # For API batch calls, we'd implement specific API handling
            # This is a simplified version
            data_items = kwargs.get("data_items", [])
            api_endpoint = kwargs.get("api_endpoint")

            if not api_endpoint:
                raise NodeConfigurationError(
                    "api_endpoint is required for api_batch_calls operation"
                )

            # Create processing code for API calls
            api_processing_code = f"""
import requests
import json

results = []
for item in batch:
    try:
        response = requests.post('{api_endpoint}', json=item, headers={kwargs.get('api_headers', {})})
        if response.status_code == 200:
            results.append(response.json())
        else:
            results.append({{'error': f'HTTP {{response.status_code}}', 'item': item}})
    except Exception as e:
        results.append({{'error': str(e), 'item': item}})

result = results
"""

            return self._process_data_batches(
                data_items=data_items,
                batch_size=kwargs.get(
                    "batch_size", 10
                ),  # Smaller batches for API calls
                processing_code=api_processing_code,
                rate_limit_per_second=kwargs.get(
                    "rate_limit_per_second", 5.0
                ),  # More conservative for APIs
                parallel_workers=kwargs.get("parallel_workers", 2),
                retry_failed_batches=kwargs.get("retry_failed_batches", True),
                max_retries=kwargs.get("max_retries", 3),
                retry_delay=kwargs.get("retry_delay", 2.0),
                progress_callback=kwargs.get("progress_callback"),
                adaptive_batch_size=kwargs.get("adaptive_batch_size", True),
                memory_limit_mb=kwargs.get("memory_limit_mb", 512),
            )

        elif operation == "database_batch_operations":
            # For database batch operations
            data_items = kwargs.get("data_items", [])
            database_config = kwargs.get("database_config", {})

            if not database_config:
                raise NodeConfigurationError(
                    "database_config is required for database_batch_operations"
                )

            # Create processing code for database operations
            db_processing_code = """
# This would typically use actual database connections
# For this example, we'll simulate database operations

import time
results = []

for item in batch:
    # Simulate database operation
    time.sleep(0.01)  # Simulate processing time
    results.append({
        'id': item.get('id', 'unknown'),
        'status': 'processed',
        'timestamp': datetime.now().isoformat()
    })

result = results
"""

            return self._process_data_batches(
                data_items=data_items,
                batch_size=kwargs.get(
                    "batch_size", 1000
                ),  # Larger batches for DB operations
                processing_code=db_processing_code,
                rate_limit_per_second=kwargs.get("rate_limit_per_second", 50.0),
                parallel_workers=kwargs.get("parallel_workers", 4),
                retry_failed_batches=kwargs.get("retry_failed_batches", True),
                max_retries=kwargs.get("max_retries", 2),
                retry_delay=kwargs.get("retry_delay", 1.0),
                progress_callback=kwargs.get("progress_callback"),
                adaptive_batch_size=kwargs.get("adaptive_batch_size", True),
                memory_limit_mb=kwargs.get("memory_limit_mb", 2048),
            )

        else:
            raise NodeConfigurationError(f"Invalid operation: {operation}")

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Async execution method for enterprise integration."""
        return self.execute(**kwargs)
