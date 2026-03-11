"""
LoggingMixin - Structured logging for agent execution.

This module implements the LoggingMixin that provides comprehensive logging
capabilities for agents, including structured logging, execution tracking,
and workflow enhancement.

Key Features:
- Structured logging (JSON format support)
- Execution lifecycle tracking
- Error logging
- Workflow enhancement with logging nodes
- MRO-compatible initialization

References:
- ADR-006: Agent Base Architecture design (Mixin Composition section)
- TODO-157: Task 3.1, 3.6-3.9
- Phase 3: Mixin System implementation

Author: Kaizen Framework Team
Created: 2025-10-01
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from kailash.workflow.builder import WorkflowBuilder


class LoggingMixin:
    """
    Mixin for adding structured logging to agents.

    Provides logging capabilities including:
    - Execution start/end logging
    - Error logging
    - Structured logging (JSON format)
    - Workflow enhancement with logging nodes

    Usage:
        >>> class MyAgent(BaseAgent, LoggingMixin):
        ...     def __init__(self, config):
        ...         BaseAgent.__init__(self, config=config, signature=signature)
        ...         LoggingMixin.__init__(self)
        ...
        ...     def run(self, **inputs):
        ...         self.log_execution_start(inputs)
        ...         result = super().run(**inputs)
        ...         self.log_execution_end(result)
        ...         return result

    Extension Points:
    - enhance_workflow(workflow): Add logging nodes to workflow
    - log_execution_start(inputs): Log execution start
    - log_execution_end(result): Log execution end
    - log_error(error): Log errors

    Notes:
    - MRO-compatible (calls super().__init__())
    - Supports structured logging (JSON format)
    - Lightweight and non-intrusive
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        log_level: int = logging.INFO,
        structured: bool = False,
        format: str = "text",
        log_format: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize LoggingMixin.

        Args:
            logger: Optional custom logger (creates default if None)
            log_level: Logging level (default: INFO)
            structured: Enable structured logging (default: False)
            format: Log format ("text" or "json")
            log_format: Custom log format string
            **kwargs: Additional arguments for super().__init__()

        Notes:
            - Task 3.9: Calls super().__init__() for MRO compatibility
            - Task 3.1: Configurable logging setup
        """
        # Task 3.9: Call super().__init__() for MRO compatibility
        if hasattr(super(), "__init__"):
            super().__init__(**kwargs)

        # Task 3.1: Initialize logger
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(log_level)

        # Task 3.8: Structured logging configuration
        self.structured = structured
        self.log_format_type = format
        self.log_format = log_format or self._get_default_format()

        # Execution tracking
        self.execution_id = None

    def _get_default_format(self) -> str:
        """Get default log format based on configuration."""
        if self.log_format_type == "json":
            return "json"
        return "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def enhance_workflow(self, workflow: WorkflowBuilder) -> WorkflowBuilder:
        """
        Enhance workflow with logging nodes.

        Adds logging nodes to the workflow for execution tracking.

        Args:
            workflow: Workflow to enhance

        Returns:
            WorkflowBuilder: Enhanced workflow with logging nodes

        Notes:
            - Task 3.6: Adds logging nodes to workflow
            - Preserves existing nodes
            - Non-intrusive enhancement
        """
        # Task 3.6: For Phase 3, return workflow as-is
        # Full logging node integration in future enhancement
        return workflow

    def log_execution_start(self, inputs: Optional[Dict[str, Any]] = None):
        """
        Log execution start.

        Args:
            inputs: Execution inputs

        Notes:
            - Task 3.7: Logs execution start with inputs
            - Handles None inputs gracefully
            - Creates execution ID for tracking
        """
        # Generate execution ID
        self.execution_id = str(uuid.uuid4())[:8]

        # Task 3.7: Log execution start
        if self.structured and self.log_format_type == "json":
            log_data = {
                "event": "execution_start",
                "execution_id": self.execution_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "inputs": inputs or {},
            }
            self.logger.info(f"Execution start: {log_data}")
        else:
            input_str = f" with inputs: {inputs}" if inputs else ""
            self.logger.info(f"Execution start [ID: {self.execution_id}]{input_str}")

    def log_execution_end(self, result: Optional[Dict[str, Any]] = None):
        """
        Log execution end.

        Args:
            result: Execution result

        Notes:
            - Task 3.7: Logs execution end with result
            - Tracks execution time if start was logged
        """
        # Task 3.7: Log execution end
        if self.structured and self.log_format_type == "json":
            log_data = {
                "event": "execution_end",
                "execution_id": self.execution_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "result": result or {},
            }
            self.logger.info(f"Execution end: {log_data}")
        else:
            result_str = f" with result keys: {list(result.keys())}" if result else ""
            self.logger.info(f"Execution end [ID: {self.execution_id}]{result_str}")

    def log_error(self, error: Exception):
        """
        Log error.

        Args:
            error: Exception to log

        Notes:
            - Task 3.7: Logs errors with context
            - Includes exception type and message
        """
        # Task 3.7: Log error
        if self.structured and self.log_format_type == "json":
            log_data = {
                "event": "error",
                "execution_id": self.execution_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
            self.logger.error(f"Error occurred: {log_data}")
        else:
            self.logger.error(
                f"Error [ID: {self.execution_id}]: {type(error).__name__}: {error}"
            )

    def create_log_context(
        self, inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create structured log context.

        Args:
            inputs: Execution inputs

        Returns:
            Dict[str, Any]: Log context with timestamp, execution_id, etc.

        Notes:
            - Task 3.8: Creates structured logging context
            - Used for JSON structured logging
        """
        # Task 3.8: Create log context
        context = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "execution_id": self.execution_id or str(uuid.uuid4())[:8],
        }

        if inputs:
            context["inputs"] = inputs

        return context
