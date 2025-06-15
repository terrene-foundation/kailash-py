"""
Workflow-based Architecture for Middleware Operations
=====================================================

This module demonstrates how to convert middleware operations into workflows
for maximum performance using SDK nodes, workflows, and runtime.

Key Optimizations:
- Session management as workflows
- Event processing as workflows
- Cleanup operations as scheduled workflows
- Error handling with retry workflows
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from ...nodes.admin import PermissionCheckNode
from ...nodes.base import register_node
from ...nodes.enterprise import BatchProcessorNode, DataLineageNode
from ...nodes.security import AuditLogNode, SecurityEventNode
from ...nodes.transform import DataTransformer
from ...runtime.async_local import AsyncLocalRuntime
from ...workflow.builder import WorkflowBuilder


class MiddlewareWorkflows:
    """
    Collection of workflow templates for common middleware operations.

    These workflows replace custom code with SDK components for better
    performance, reliability, and maintainability.
    """

    @staticmethod
    def create_session_workflow() -> WorkflowBuilder:
        """
        Create a workflow for session creation with validation and setup.

        Workflow steps:
        1. Validate user credentials
        2. Check permissions
        3. Create session record
        4. Initialize session state
        5. Emit session created event
        6. Log audit entry

        Returns:
            WorkflowBuilder configured for session creation
        """
        builder = WorkflowBuilder()

        # Add permission check node
        permission_check = builder.add_node(
            "PermissionCheckNode",
            node_id="check_permissions",
            config={
                "name": "session_permission_check",
                "permission": "session.create",
                "resource_type": "session",
            },
        )

        # Add data transformer for session initialization
        session_init = builder.add_node(
            "DataTransformer",
            node_id="init_session",
            config={
                "name": "session_initializer",
                "transformations": [
                    {
                        "operation": "add_field",
                        "field": "session_id",
                        "value": "{{ generate_uuid() }}",
                    },
                    {
                        "operation": "add_field",
                        "field": "created_at",
                        "value": "{{ current_timestamp() }}",
                    },
                    {"operation": "add_field", "field": "active", "value": True},
                ],
            },
        )

        # Add security event logging
        security_log = builder.add_node(
            "SecurityEventNode",
            node_id="log_security_event",
            config={
                "name": "session_security_logger",
                "event_type": "session_created",
                "severity": "info",
            },
        )

        # Add audit log entry
        audit_log = builder.add_node(
            "AuditLogNode",
            node_id="audit_session_creation",
            config={
                "name": "session_audit_logger",
                "action": "create_session",
                "resource_type": "session",
            },
        )

        # Connect nodes
        builder.add_connection(permission_check, "authorized", session_init, "input")
        builder.add_connection(session_init, "output", security_log, "event_data")
        builder.add_connection(security_log, "logged", audit_log, "input")

        return builder

    @staticmethod
    def create_execution_monitoring_workflow() -> WorkflowBuilder:
        """
        Create a workflow for monitoring execution progress.

        Workflow steps:
        1. Track execution state
        2. Calculate progress
        3. Emit progress events
        4. Update execution record
        5. Handle timeouts

        Returns:
            WorkflowBuilder configured for execution monitoring
        """
        builder = WorkflowBuilder()

        # Add data lineage tracking
        lineage_tracker = builder.add_node(
            "DataLineageNode",
            node_id="track_lineage",
            config={
                "name": "execution_lineage_tracker",
                "track_transformations": True,
                "track_data_flow": True,
            },
        )

        # Add progress calculator
        progress_calc = builder.add_node(
            "PythonCodeNode",
            node_id="calculate_progress",
            config={
                "name": "progress_calculator",
                "code": """
completed_nodes = len([n for n in execution_data['nodes'] if n['status'] == 'completed'])
total_nodes = len(execution_data['nodes'])
progress = (completed_nodes / total_nodes * 100) if total_nodes > 0 else 0
result = {
    'progress': progress,
    'completed': completed_nodes,
    'total': total_nodes,
    'status': 'completed' if progress == 100 else 'running'
}
""",
            },
        )

        # Add event emitter (would use EventEmitterNode when available)
        event_emitter = builder.add_node(
            "PythonCodeNode",
            node_id="emit_progress_event",
            config={
                "name": "progress_event_emitter",
                "code": """
# In production, use EventEmitterNode
event_data = {
    'type': 'workflow.progress',
    'execution_id': execution_id,
    'progress': progress_data['progress'],
    'status': progress_data['status']
}
result = {'event_emitted': True, 'event_data': event_data}
""",
            },
        )

        # Connect nodes
        builder.add_connection(
            lineage_tracker, "lineage", progress_calc, "execution_data"
        )
        builder.add_connection(progress_calc, "result", event_emitter, "progress_data")

        return builder

    @staticmethod
    def create_cleanup_workflow() -> WorkflowBuilder:
        """
        Create a workflow for session cleanup operations.

        Workflow steps:
        1. Identify expired sessions
        2. Cancel active executions
        3. Archive session data
        4. Remove from active sessions
        5. Emit cleanup events

        Returns:
            WorkflowBuilder configured for cleanup operations
        """
        builder = WorkflowBuilder()

        # Add batch processor for efficient cleanup
        batch_cleanup = builder.add_node(
            "BatchProcessorNode",
            node_id="batch_cleanup",
            config={"name": "session_batch_cleanup"},
        )

        # Add data transformer for archival
        archiver = builder.add_node(
            "DataTransformer",
            node_id="archive_sessions",
            config={
                "name": "session_archiver",
                "transformations": [
                    {
                        "operation": "add_field",
                        "field": "archived_at",
                        "value": "{{ current_timestamp() }}",
                    },
                    {"operation": "update_field", "field": "active", "value": False},
                ],
            },
        )

        # Add audit logging
        audit_cleanup = builder.add_node(
            "AuditLogNode",
            node_id="audit_cleanup",
            config={
                "name": "cleanup_audit_logger",
                "action": "cleanup_sessions",
                "resource_type": "session",
            },
        )

        # Connect nodes
        builder.add_connection(batch_cleanup, "batches", archiver, "sessions")
        builder.add_connection(archiver, "output", audit_cleanup, "cleanup_data")

        return builder

    @staticmethod
    def create_error_handling_workflow() -> WorkflowBuilder:
        """
        Create a workflow for error handling with retries.

        Workflow steps:
        1. Capture error details
        2. Determine retry strategy
        3. Execute retry if applicable
        4. Log error if retry fails
        5. Emit error events

        Returns:
            WorkflowBuilder configured for error handling
        """
        builder = WorkflowBuilder()

        # Add error analyzer
        error_analyzer = builder.add_node(
            "PythonCodeNode",
            node_id="analyze_error",
            config={
                "name": "error_analyzer",
                "code": """
error_type = error_data.get('type', 'unknown')
retry_count = error_data.get('retry_count', 0)
max_retries = 3

should_retry = retry_count < max_retries and error_type in ['timeout', 'network', 'temporary']
retry_delay = min(2 ** retry_count, 60)  # Exponential backoff

result = {
    'should_retry': should_retry,
    'retry_delay': retry_delay,
    'retry_count': retry_count + 1,
    'error_type': error_type
}
""",
            },
        )

        # Add security event for error
        security_error = builder.add_node(
            "SecurityEventNode",
            node_id="log_error_event",
            config={
                "name": "error_security_logger",
                "event_type": "execution_error",
                "severity": "warning",
            },
        )

        # Connect nodes
        builder.add_connection(error_analyzer, "result", security_error, "error_info")

        return builder


class WorkflowBasedMiddleware:
    """
    Example of how to use workflows for middleware operations.

    This demonstrates replacing custom code with workflow-based
    implementations for better performance and maintainability.
    """

    def __init__(self):
        """Initialize workflow-based middleware."""
        self.runtime = AsyncLocalRuntime(debug=True, max_concurrency=10)

        # Pre-build common workflows
        self.workflows = {
            "session_creation": MiddlewareWorkflows.create_session_workflow().build(),
            "execution_monitoring": MiddlewareWorkflows.create_execution_monitoring_workflow().build(),
            "cleanup": MiddlewareWorkflows.create_cleanup_workflow().build(),
            "error_handling": MiddlewareWorkflows.create_error_handling_workflow().build(),
        }

    async def create_session(self, user_id: str, metadata: Dict[str, Any]) -> str:
        """
        Create a session using workflow-based approach.

        Args:
            user_id: User identifier
            metadata: Session metadata

        Returns:
            Session ID
        """
        inputs = {"user_id": user_id, "metadata": metadata}

        # Execute session creation workflow
        results, run_id = await self.runtime.execute(
            self.workflows["session_creation"], parameters=inputs
        )

        return results.get("session_id")

    async def monitor_execution(
        self, execution_id: str, execution_data: Dict[str, Any]
    ):
        """
        Monitor execution progress using workflow.

        Args:
            execution_id: Execution identifier
            execution_data: Current execution state
        """
        inputs = {"execution_id": execution_id, "execution_data": execution_data}

        # Execute monitoring workflow
        await self.runtime.execute(
            self.workflows["execution_monitoring"], parameters=inputs
        )

    async def cleanup_sessions(self, timeout_minutes: int = 60):
        """
        Run cleanup workflow for expired sessions.

        Args:
            timeout_minutes: Session timeout in minutes
        """
        inputs = {
            "timeout_minutes": timeout_minutes,
            "current_time": datetime.now(timezone.utc),
        }

        # Execute cleanup workflow
        await self.runtime.execute(self.workflows["cleanup"], parameters=inputs)

    async def handle_error(self, error_data: Dict[str, Any]):
        """
        Handle errors using workflow-based retry logic.

        Args:
            error_data: Error information including type and context
        """
        # Execute error handling workflow
        results, _ = await self.runtime.execute(
            self.workflows["error_handling"], parameters={"error_data": error_data}
        )

        if results.get("should_retry"):
            # Schedule retry using appropriate mechanism
            pass


# Export workflow templates for reuse
__all__ = ["MiddlewareWorkflows", "WorkflowBasedMiddleware"]
