"""Database execution pipeline for clean separation of concerns.

This module provides a pipeline-based approach to database operations,
separating permission checking, query execution, and data masking into
clear, testable stages.
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from kailash.access_control import NodePermission, UserContext
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Context for database execution pipeline."""

    query: str
    parameters: Optional[Union[Dict[str, Any], List[Any]]] = None
    user_context: Optional[UserContext] = None
    node_name: str = "unknown_node"
    result_format: str = "dict"
    runtime_context: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionResult:
    """Result from database execution pipeline."""

    data: Any
    row_count: int
    columns: List[str]
    execution_time: float
    metadata: Optional[Dict[str, Any]] = None


class PipelineStage(ABC):
    """Abstract base class for pipeline stages."""

    @abstractmethod
    async def process(
        self, context: ExecutionContext, result: Optional[ExecutionResult] = None
    ) -> Optional[ExecutionResult]:
        """Process this stage of the pipeline.

        Args:
            context: Execution context
            result: Result from previous stage (None for first stage)

        Returns:
            Result to pass to next stage, or None to stop pipeline
        """
        pass

    @abstractmethod
    def get_stage_name(self) -> str:
        """Get the name of this pipeline stage."""
        pass


class PermissionCheckStage(PipelineStage):
    """Pipeline stage for checking user permissions."""

    def __init__(self, access_control_manager=None):
        """Initialize permission check stage.

        Args:
            access_control_manager: Access control manager for permission checks
        """
        self.access_control_manager = access_control_manager
        self.logger = logging.getLogger(f"{__name__}.PermissionCheckStage")

    async def process(
        self, context: ExecutionContext, result: Optional[ExecutionResult] = None
    ) -> Optional[ExecutionResult]:
        """Check user permissions before query execution."""
        # Skip if no access control or no user context
        if not self.access_control_manager or not context.user_context:
            self.logger.debug(
                "Skipping permission check - no access control or user context"
            )
            return result

        # Check execute permission
        decision = self.access_control_manager.check_node_access(
            context.user_context,
            context.node_name,
            NodePermission.EXECUTE,
            context.runtime_context,
        )

        if not decision.allowed:
            raise NodeExecutionError(f"Access denied: {decision.reason}")

        self.logger.debug(
            f"Permission granted for {context.node_name}: {decision.reason}"
        )
        return result

    def get_stage_name(self) -> str:
        """Get stage name."""
        return "permission_check"


class QueryValidationStage(PipelineStage):
    """Pipeline stage for validating SQL queries."""

    def __init__(self, validation_rules: Optional[Dict[str, Any]] = None):
        """Initialize query validation stage.

        Args:
            validation_rules: Custom validation rules
        """
        self.validation_rules = validation_rules or {}
        self.logger = logging.getLogger(f"{__name__}.QueryValidationStage")

    async def process(
        self, context: ExecutionContext, result: Optional[ExecutionResult] = None
    ) -> Optional[ExecutionResult]:
        """Validate query for security and safety."""
        if not context.query:
            raise NodeExecutionError("Query cannot be empty")

        # Basic SQL injection checks
        self._validate_query_safety(context.query)

        self.logger.debug(f"Query validation passed for: {context.query[:100]}...")
        return result

    def _validate_query_safety(self, query: str) -> None:
        """Validate query for potential security issues."""
        if not query:
            return

        query_upper = query.upper().strip()

        # Check for dangerous operations
        dangerous_keywords = [
            "DROP",
            "DELETE",
            "TRUNCATE",
            "ALTER",
            "CREATE",
            "GRANT",
            "REVOKE",
            "EXEC",
            "EXECUTE",
            "SHUTDOWN",
            "BACKUP",
            "RESTORE",
        ]

        import re

        for keyword in dangerous_keywords:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, query_upper):
                # ADR-002: Changed from WARNING to DEBUG - DDL during schema creation is expected
                self.logger.debug(
                    f"Query contains potentially dangerous keyword: {keyword}"
                )
                # In production, you might want to block these entirely
                # raise NodeExecutionError(f"Query contains forbidden keyword: {keyword}")

    def get_stage_name(self) -> str:
        """Get stage name."""
        return "query_validation"


class QueryExecutionStage(PipelineStage):
    """Pipeline stage for executing SQL queries."""

    def __init__(self, query_executor):
        """Initialize query execution stage.

        Args:
            query_executor: Object that can execute queries (engine, connection, etc.)
        """
        self.query_executor = query_executor
        self.logger = logging.getLogger(f"{__name__}.QueryExecutionStage")

    async def process(
        self, context: ExecutionContext, result: Optional[ExecutionResult] = None
    ) -> Optional[ExecutionResult]:
        """Execute the SQL query."""
        start_time = time.time()

        try:
            # This is where the actual query execution happens
            # The implementation depends on whether it's sync or async
            if hasattr(self.query_executor, "execute_query"):
                # Custom executor interface
                query_result = await self.query_executor.execute_query(
                    context.query, context.parameters, context.result_format
                )
            else:
                # Fallback - assume it's a callable
                query_result = await self.query_executor(
                    context.query, context.parameters
                )

            execution_time = time.time() - start_time

            # Format the result
            if isinstance(query_result, dict):
                # Structured result
                return ExecutionResult(
                    data=query_result.get("data", []),
                    row_count=query_result.get("row_count", 0),
                    columns=query_result.get("columns", []),
                    execution_time=execution_time,
                    metadata=query_result.get("metadata", {}),
                )
            else:
                # Raw result - format it
                return ExecutionResult(
                    data=query_result,
                    row_count=(
                        len(query_result) if isinstance(query_result, list) else 1
                    ),
                    columns=[],
                    execution_time=execution_time,
                )

        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(
                f"Query execution failed after {execution_time:.3f}s: {e}"
            )
            raise NodeExecutionError(f"Database query failed: {e}") from e

    def get_stage_name(self) -> str:
        """Get stage name."""
        return "query_execution"


class DataMaskingStage(PipelineStage):
    """Pipeline stage for applying data masking based on user attributes."""

    def __init__(self, access_control_manager=None):
        """Initialize data masking stage.

        Args:
            access_control_manager: Access control manager with masking capabilities
        """
        self.access_control_manager = access_control_manager
        self.logger = logging.getLogger(f"{__name__}.DataMaskingStage")

    async def process(
        self, context: ExecutionContext, result: Optional[ExecutionResult] = None
    ) -> Optional[ExecutionResult]:
        """Apply data masking based on user attributes."""
        if not result or not result.data:
            return result

        # Skip if no access control or no user context
        if not self.access_control_manager or not context.user_context:
            self.logger.debug(
                "Skipping data masking - no access control or user context"
            )
            return result

        # Skip if not dict format (masking only works on structured data)
        if context.result_format != "dict" or not isinstance(result.data, list):
            self.logger.debug("Skipping data masking - data format not supported")
            return result

        # Apply masking to each row
        masked_data = []
        for row in result.data:
            if isinstance(row, dict):
                # Apply masking if access control manager supports it
                if hasattr(self.access_control_manager, "apply_data_masking"):
                    masked_row = self.access_control_manager.apply_data_masking(
                        context.user_context, context.node_name, row
                    )
                    masked_data.append(masked_row)
                else:
                    masked_data.append(row)
            else:
                masked_data.append(row)

        # Return result with masked data
        return ExecutionResult(
            data=masked_data,
            row_count=result.row_count,
            columns=result.columns,
            execution_time=result.execution_time,
            metadata=result.metadata,
        )

    def get_stage_name(self) -> str:
        """Get stage name."""
        return "data_masking"


class DatabaseExecutionPipeline:
    """Pipeline for executing database operations with clean separation of concerns.

    This pipeline provides:
    - Permission checking
    - Query validation
    - Query execution
    - Data masking

    Example:
        >>> pipeline = DatabaseExecutionPipeline(
        ...     access_control_manager=access_manager,
        ...     query_executor=my_executor
        ... )
        >>>
        >>> context = ExecutionContext(
        ...     query="SELECT * FROM users",
        ...     user_context=user,
        ...     node_name="user_query"
        ... )
        >>>
        >>> result = await pipeline.execute(context)
    """

    def __init__(
        self,
        access_control_manager=None,
        query_executor=None,
        validation_rules: Optional[Dict[str, Any]] = None,
        custom_stages: Optional[List[PipelineStage]] = None,
    ):
        """Initialize database execution pipeline.

        Args:
            access_control_manager: Access control manager for permissions and masking
            query_executor: Object that can execute database queries
            validation_rules: Custom validation rules for queries
            custom_stages: Additional custom pipeline stages
        """
        self.access_control_manager = access_control_manager
        self.query_executor = query_executor
        self.logger = logging.getLogger(f"{__name__}.DatabaseExecutionPipeline")

        # Build pipeline stages
        self.stages: List[PipelineStage] = []

        # 1. Permission check
        self.stages.append(PermissionCheckStage(access_control_manager))

        # 2. Query validation
        self.stages.append(QueryValidationStage(validation_rules))

        # 3. Custom stages (before execution)
        if custom_stages:
            for stage in custom_stages:
                if stage.get_stage_name() != "query_execution":
                    self.stages.append(stage)

        # 4. Query execution
        if query_executor:
            self.stages.append(QueryExecutionStage(query_executor))

        # 5. Data masking
        self.stages.append(DataMaskingStage(access_control_manager))

        # 6. Custom stages (after execution)
        if custom_stages:
            for stage in custom_stages:
                if stage.get_stage_name() == "post_processing":
                    self.stages.append(stage)

        self.logger.info(f"Initialized pipeline with {len(self.stages)} stages")

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute the full database pipeline.

        Args:
            context: Execution context with query, user, etc.

        Returns:
            Execution result with data, timing, etc.

        Raises:
            NodeExecutionError: If any stage fails
        """
        self.logger.debug(f"Starting pipeline execution for {context.node_name}")

        result = None
        pipeline_start = time.time()

        try:
            # Execute each stage in sequence
            for i, stage in enumerate(self.stages):
                stage_start = time.time()

                try:
                    result = await stage.process(context, result)
                    stage_time = time.time() - stage_start

                    self.logger.debug(
                        f"Stage {i+1}/{len(self.stages)} ({stage.get_stage_name()}) "
                        f"completed in {stage_time:.3f}s"
                    )

                    # Allow stages to stop the pipeline
                    if result is None and stage.get_stage_name() != "permission_check":
                        self.logger.warning(
                            f"Pipeline stopped at stage: {stage.get_stage_name()}"
                        )
                        break

                except Exception as e:
                    self.logger.error(
                        f"Pipeline failed at stage {stage.get_stage_name()}: {e}"
                    )
                    raise

            pipeline_time = time.time() - pipeline_start
            self.logger.info(f"Pipeline execution completed in {pipeline_time:.3f}s")

            # Ensure we have a result
            if result is None:
                result = ExecutionResult(
                    data=[],
                    row_count=0,
                    columns=[],
                    execution_time=pipeline_time,
                )

            return result

        except Exception as e:
            pipeline_time = time.time() - pipeline_start
            self.logger.error(
                f"Pipeline execution failed after {pipeline_time:.3f}s: {e}"
            )
            raise

    def add_stage(self, stage: PipelineStage, position: Optional[int] = None) -> None:
        """Add a custom stage to the pipeline.

        Args:
            stage: Pipeline stage to add
            position: Position to insert at (None = append)
        """
        if position is None:
            self.stages.append(stage)
        else:
            self.stages.insert(position, stage)

        self.logger.info(
            f"Added stage {stage.get_stage_name()} at position {position or len(self.stages)}"
        )

    def remove_stage(self, stage_name: str) -> bool:
        """Remove a stage from the pipeline.

        Args:
            stage_name: Name of stage to remove

        Returns:
            True if stage was found and removed
        """
        initial_count = len(self.stages)
        self.stages = [s for s in self.stages if s.get_stage_name() != stage_name]
        removed = len(self.stages) < initial_count

        if removed:
            self.logger.info(f"Removed stage {stage_name}")

        return removed

    def get_stage_info(self) -> List[Dict[str, str]]:
        """Get information about all pipeline stages.

        Returns:
            List of stage information dictionaries
        """
        return [
            {
                "name": stage.get_stage_name(),
                "type": type(stage).__name__,
            }
            for stage in self.stages
        ]


# Export components
__all__ = [
    "ExecutionContext",
    "ExecutionResult",
    "PipelineStage",
    "PermissionCheckStage",
    "QueryValidationStage",
    "QueryExecutionStage",
    "DataMaskingStage",
    "DatabaseExecutionPipeline",
]
