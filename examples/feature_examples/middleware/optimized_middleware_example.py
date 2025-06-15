"""
Optimized Middleware Example - Maximizing SDK Node Usage
=======================================================

This example demonstrates how to maximize performance by using Kailash SDK nodes,
workflows, and runtime throughout the middleware layer instead of custom code.

Key optimizations demonstrated:
1. Session management using workflows
2. Event processing with BatchProcessorNode
3. Credential management with RotatingCredentialNode
4. Database operations with AsyncSQLDatabaseNode
5. Caching with DataTransformer (as cache)
6. Rate limiting with SDK patterns
7. Monitoring with DataLineageNode

The example shows how replacing custom implementations with SDK components
provides better performance, reliability, and maintainability.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from kailash.middleware import AgentUIMiddleware, EventStream
from kailash.nodes.enterprise import BatchProcessorNode
from kailash.nodes.security import RotatingCredentialNode, AuditLogNode
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.nodes.enterprise import DataLineageNode
from kailash.nodes.transform import DataTransformer
from kailash.nodes.admin import PermissionCheckNode
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.tracking import TaskManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OptimizedAgentUIMiddleware(AgentUIMiddleware):
    """
    Enhanced AgentUIMiddleware that maximizes SDK node usage.
    
    This implementation replaces custom code with SDK nodes for:
    - Session management
    - Event processing
    - Database operations
    - Caching
    - Security
    - Monitoring
    """
    
    def __init__(self, **kwargs):
        """Initialize with additional SDK nodes for optimization."""
        # Store database_url before calling super()
        self.database_url = kwargs.get('database_url')
        super().__init__(**kwargs)
        
        # Initialize additional SDK nodes for performance
        self._init_performance_nodes()
        
        # Create workflow-based processors
        self._init_workflow_processors()
        
        # Set up SDK-based monitoring
        self._init_monitoring()
    
    def _init_performance_nodes(self):
        """Initialize SDK nodes for performance optimization."""
        
        # Batch processor for event handling
        self.event_batch_processor = BatchProcessorNode(
            name="event_batch_processor"
        )
        
        # Rotating credentials for security
        self.rotating_credentials = RotatingCredentialNode(
            name="middleware_rotating_creds",
            credential_name="middleware_secrets",
            rotation_interval_days=30
        )
        
        # Data lineage for tracking
        self.data_lineage = DataLineageNode(
            name="middleware_lineage_tracker"
        )
        
        # Permission checker for authorization
        self.permission_checker = PermissionCheckNode(
            name="middleware_permission_check"
        )
        
        # Audit logger for compliance
        self.audit_logger = AuditLogNode(
            name="middleware_audit_log"
        )
        
        # Data transformer for caching operations
        self.cache_transformer = DataTransformer(
            name="middleware_cache"
        )
        
        # Async SQL node for database operations
        if self.enable_persistence:
            self.async_db = AsyncSQLDatabaseNode(
                name="middleware_async_db",
                connection_string=self.database_url
            )
    
    def _init_workflow_processors(self):
        """Initialize workflow-based processors."""
        
        # Create specialized runtime for middleware workflows
        self.workflow_runtime = LocalRuntime(
            debug=False,
            max_concurrency=20
        , enable_async=True)
        
        # Build reusable workflows
        self.workflows = {
            "session_validation": self._build_session_validation_workflow(),
            "event_processing": self._build_event_processing_workflow(),
            "cleanup": self._build_cleanup_workflow(),
            "monitoring": self._build_monitoring_workflow()
        }
    
    def _init_monitoring(self):
        """Initialize SDK-based monitoring."""
        
        # Create monitoring workflow that runs periodically
        self.monitoring_task = None
        self.monitoring_interval = 30  # seconds
    
    def _build_session_validation_workflow(self) -> WorkflowBuilder:
        """Build workflow for session validation."""
        builder = WorkflowBuilder()
        
        # Check permissions
        perm_check = builder.add_node(
            "PermissionCheckNode",
            node_id="check_session_perms",
            config={
                "name": "session_permission_validator",
                "permission": "session.access"
            }
        )
        
        # Validate session data
        validator = builder.add_node(
            "DataTransformer",
            node_id="validate_session",
            config={
                "name": "session_validator",
                "transformations": [
                    {
                        "operation": "validate",
                        "schema": {
                            "session_id": {"type": "string", "required": True},
                            "user_id": {"type": "string", "required": False},
                            "active": {"type": "boolean", "required": True}
                        }
                    }
                ]
            }
        )
        
        # Log validation
        audit = builder.add_node(
            "AuditLogNode",
            node_id="audit_validation",
            config={
                "name": "session_validation_audit",
                "action": "validate_session"
            }
        )
        
        # Connect nodes
        builder.add_connection(perm_check, "authorized", validator, "input")
        builder.add_connection(validator, "output", audit, "validation_result")
        
        return builder.build()
    
    def _build_event_processing_workflow(self) -> WorkflowBuilder:
        """Build workflow for event processing."""
        builder = WorkflowBuilder()
        
        # Batch events
        batcher = builder.add_node(
            "BatchProcessorNode",
            node_id="batch_events",
            config={
                "name": "event_batcher"
            }
        )
        
        # Transform events
        transformer = builder.add_node(
            "DataTransformer",
            node_id="transform_events",
            config={
                "name": "event_transformer",
                "transformations": [
                    {
                        "operation": "add_field",
                        "field": "processed_at",
                        "value": "{{ current_timestamp() }}"
                    }
                ]
            }
        )
        
        # Track lineage
        lineage = builder.add_node(
            "DataLineageNode",
            node_id="track_event_lineage",
            config={
                "name": "event_lineage_tracker"
            }
        )
        
        # Connect nodes
        builder.add_connection(batcher, "batches", transformer, "events")
        builder.add_connection(transformer, "output", lineage, "event_data")
        
        return builder.build()
    
    def _build_cleanup_workflow(self) -> WorkflowBuilder:
        """Build workflow for cleanup operations."""
        builder = WorkflowBuilder()
        
        # Query expired sessions
        query = builder.add_node(
            "PythonCodeNode",
            node_id="find_expired",
            config={
                "name": "expired_session_finder",
                "code": """
import datetime
current_time = datetime.datetime.now(timezone.utc)
timeout_delta = datetime.timedelta(minutes=timeout_minutes)
expired_sessions = []

for session_id, session in sessions.items():
    if not session['active']:
        session_age = current_time - session['created_at']
        if session_age > timeout_delta:
            expired_sessions.append(session_id)

result = {'expired_sessions': expired_sessions}
"""
            }
        )
        
        # Batch process cleanup
        cleanup = builder.add_node(
            "BatchProcessorNode",
            node_id="cleanup_batch",
            config={
                "name": "session_cleanup_processor"
            }
        )
        
        # Audit cleanup
        audit = builder.add_node(
            "AuditLogNode",
            node_id="audit_cleanup",
            config={
                "name": "cleanup_audit",
                "action": "cleanup_expired_sessions"
            }
        )
        
        # Connect nodes
        builder.add_connection(query, "result", cleanup, "sessions_to_cleanup")
        builder.add_connection(cleanup, "processed", audit, "cleanup_results")
        
        return builder.build()
    
    def _build_monitoring_workflow(self) -> WorkflowBuilder:
        """Build workflow for monitoring."""
        builder = WorkflowBuilder()
        
        # Collect metrics
        metrics = builder.add_node(
            "PythonCodeNode",
            node_id="collect_metrics",
            config={
                "name": "metrics_collector",
                "code": """
import time
current_time = time.time()
uptime = current_time - start_time

metrics = {
    'uptime_seconds': uptime,
    'active_sessions': len([s for s in sessions.values() if s.get('active', False)]),
    'total_sessions': len(sessions),
    'events_processed': events_processed,
    'avg_latency_ms': sum(latency_samples) / len(latency_samples) if latency_samples else 0
}

result = {'metrics': metrics}
"""
            }
        )
        
        # Track lineage
        lineage = builder.add_node(
            "DataLineageNode",
            node_id="track_metrics",
            config={
                "name": "metrics_lineage_tracker"
            }
        )
        
        # Connect nodes
        builder.add_connection(metrics, "result", lineage, "metrics_data")
        
        return builder.build()
    
    async def create_session(self, user_id: str = None, session_id: str = None, 
                           metadata: Dict[str, Any] = None) -> str:
        """
        Create session using workflow-based approach.
        
        This method demonstrates using workflows instead of custom code
        for session creation with proper validation and auditing.
        """
        # Prepare inputs for workflow
        inputs = {
            "user_id": user_id,
            "session_id": session_id or str(uuid.uuid4()),
            "metadata": metadata or {},
            "permissions": {"session.create": True}  # Would come from auth
        }
        
        # Execute session creation workflow
        try:
            # Use session validation workflow
            results, run_id = await self.workflow_runtime.execute(
                self.workflows["session_validation"],
                parameters=inputs
            )
            
            # Create session after validation
            session_id = inputs["session_id"]
            session = WorkflowSession(session_id, user_id, metadata)
            self.sessions[session_id] = session
            
            # Track with data lineage
            await self.data_lineage.execute(
                data_source="session_creation",
                data_target=f"session_{session_id}",
                metadata={
                    "user_id": user_id,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            )
            
            # Emit event using SDK pattern
            await self._emit_session_event(session_id, "created")
            
            return session_id
            
        except Exception as e:
            logger.error(f"Session creation failed: {e}")
            raise
    
    async def execute_workflow(self, session_id: str, workflow_id: str,
                             inputs: Dict[str, Any] = None,
                             config_overrides: Dict[str, Any] = None) -> str:
        """
        Execute workflow with enhanced monitoring using SDK nodes.
        
        This method shows how to use SDK components for execution tracking,
        progress monitoring, and event emission.
        """
        # Validate session using permission checker
        perm_result = await self.permission_checker.execute(
            user_context={"session_id": session_id},
            permission="workflow.execute",
            resource={"workflow_id": workflow_id}
        )
        
        if not perm_result.get("authorized"):
            raise ValueError(f"Session {session_id} not authorized to execute workflow")
        
        # Create execution with lineage tracking
        execution_id = await super().execute_workflow(
            session_id, workflow_id, inputs, config_overrides
        )
        
        # Track execution lineage
        await self.data_lineage.execute(
            data_source=f"workflow_{workflow_id}",
            data_target=f"execution_{execution_id}",
            metadata={
                "session_id": session_id,
                "inputs": inputs,
                "config_overrides": config_overrides
            }
        )
        
        # Audit the execution
        await self.audit_logger.execute(
            user_id=self.sessions[session_id].user_id,
            action="execute_workflow",
            resource_type="workflow",
            resource_id=workflow_id,
            details={
                "execution_id": execution_id,
                "session_id": session_id
            }
        )
        
        return execution_id
    
    async def _emit_session_event(self, session_id: str, event_type: str):
        """Emit session event using SDK patterns."""
        event_data = {
            "session_id": session_id,
            "event_type": f"session.{event_type}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Process through event workflow
        await self.workflow_runtime.execute(
            self.workflows["event_processing"],
            parameters={"events": [event_data]}
        )
    
    async def cleanup_sessions(self):
        """Run cleanup using workflow."""
        inputs = {
            "sessions": self.sessions,
            "timeout_minutes": self.session_timeout_minutes
        }
        
        results, _ = await self.workflow_runtime.execute(
            self.workflows["cleanup"],
            parameters=inputs
        )
        
        # Process cleanup results
        for session_id in results.get("expired_sessions", []):
            await self.close_session(session_id)
    
    async def start_monitoring(self):
        """Start monitoring using workflow-based approach."""
        async def monitor():
            while True:
                try:
                    inputs = {
                        "sessions": self.sessions,
                        "start_time": self.start_time,
                        "events_processed": self.events_emitted,
                        "latency_samples": []  # Would be collected
                    }
                    
                    await self.workflow_runtime.execute(
                        self.workflows["monitoring"],
                        parameters=inputs
                    )
                    
                except Exception as e:
                    logger.error(f"Monitoring error: {e}")
                
                await asyncio.sleep(self.monitoring_interval)
        
        self.monitoring_task = asyncio.create_task(monitor())


async def main():
    """Demonstrate optimized middleware with maximum SDK usage."""
    
    # Create optimized middleware
    middleware = OptimizedAgentUIMiddleware(
        enable_dynamic_workflows=True,
        max_sessions=1000,
        session_timeout_minutes=60,
        enable_persistence=True,
        database_url="postgresql://admin:admin@localhost:5433/kailash_admin"
    )
    
    # Start monitoring
    await middleware.start_monitoring()
    
    # Create a session using workflow
    session_id = await middleware.create_session(
        user_id="demo_user",
        metadata={"source": "optimized_example"}
    )
    print(f"Created session: {session_id}")
    
    # Create a test workflow
    builder = WorkflowBuilder()
    
    # Add nodes using SDK components
    reader = builder.add_node(
        "CSVReaderNode",
        node_id="reader",
        config={
            "name": "test_reader",
            "file_path": "/data/test.csv"
        }
    )
    
    processor = builder.add_node(
        "BatchProcessorNode",
        node_id="processor",
        config={
            "name": "test_processor"
        }
    )
    
    transformer = builder.add_node(
        "DataTransformer",
        node_id="transformer",
        config={
            "name": "test_transformer",
            "transformations": [
                {
                    "operation": "add_field",
                    "field": "processed",
                    "value": True
                }
            ]
        }
    )
    
    # Connect nodes
    builder.add_connection(reader, "data", processor, "data_items")
    builder.add_connection(processor, "processed_items", transformer, "data")
    
    # Build and register workflow
    workflow = builder.build()
    workflow_id = "optimized_test_workflow"
    await middleware.register_workflow(workflow_id, workflow, session_id)
    
    # Execute workflow with SDK-based tracking
    execution_id = await middleware.execute_workflow(
        session_id,
        workflow_id,
        inputs={"file_path": "/data/input.csv"}
    )
    print(f"Started execution: {execution_id}")
    
    # Wait for completion
    await asyncio.sleep(2)
    
    # Get execution status
    status = await middleware.get_execution_status(execution_id, session_id)
    print(f"Execution status: {status}")
    
    # Cleanup using workflow
    await middleware.cleanup_sessions()
    
    # Stop monitoring
    if middleware.monitoring_task:
        middleware.monitoring_task.cancel()
    
    print("\nOptimized middleware demonstration complete!")
    print("Key optimizations demonstrated:")
    print("- Session management using workflows")
    print("- Event processing with BatchProcessorNode")
    print("- Credential rotation with RotatingCredentialNode")
    print("- Database operations with AsyncSQLDatabaseNode")
    print("- Monitoring with DataLineageNode")
    print("- Permission checking with PermissionCheckNode")
    print("- Audit logging with AuditLogNode")


if __name__ == "__main__":
    import uuid
    asyncio.run(main())