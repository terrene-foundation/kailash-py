"""Edge migration node for live workload migration between edge nodes.

This node integrates edge migration capabilities into workflows,
enabling zero-downtime migration of workloads and data.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from kailash.edge.migration.edge_migration_service import EdgeMigrationService
from kailash.edge.migration.edge_migrator import (
    EdgeMigrator,
    MigrationPhase,
    MigrationPlan,
    MigrationProgress,
    MigrationStrategy,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class EdgeMigrationNode(AsyncNode):
    """Node for edge migration operations.

    This node provides capabilities for planning and executing live migrations
    of workloads between edge nodes with minimal downtime.

    Example:
        >>> # Plan a migration
        >>> result = await migration_node.execute_async(
        ...     operation="plan_migration",
        ...     source_edge="edge-west-1",
        ...     target_edge="edge-east-1",
        ...     workloads=["api-service", "cache-layer"],
        ...     strategy="live"
        ... )

        >>> # Execute the migration
        >>> result = await migration_node.execute_async(
        ...     operation="execute_migration",
        ...     migration_id=result["plan"]["migration_id"]
        ... )

        >>> # Check progress
        >>> result = await migration_node.execute_async(
        ...     operation="get_progress",
        ...     migration_id="migration_123"
        ... )

        >>> # Rollback if needed
        >>> result = await migration_node.execute_async(
        ...     operation="rollback_migration",
        ...     migration_id="migration_123"
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize edge migration node."""
        super().__init__(**kwargs)

        # Extract node-specific configuration
        self.node_config = {
            "checkpoint_interval": kwargs.get("checkpoint_interval", 60),
            "sync_batch_size": kwargs.get("sync_batch_size", 1000),
            "bandwidth_limit_mbps": kwargs.get("bandwidth_limit_mbps"),
            "enable_compression": kwargs.get("enable_compression", True),
        }

        # Get reference to shared migration service
        self.migration_service = EdgeMigrationService(self.node_config)

        # Get migrator instance from shared service with node-specific config
        self.node_id = f"edge_migration_node_{id(self)}"
        self.migrator = self.migration_service.get_migrator_for_node(
            self.node_id, self.node_config
        )

        self._migrator_started = False

    @property
    def input_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform (plan_migration, execute_migration, get_progress, pause_migration, resume_migration, rollback_migration, get_active_migrations, get_history, get_metrics, start_migrator, stop_migrator)",
            ),
            # For plan_migration
            "source_edge": NodeParameter(
                name="source_edge",
                type=str,
                required=False,
                description="Source edge node",
            ),
            "target_edge": NodeParameter(
                name="target_edge",
                type=str,
                required=False,
                description="Target edge node",
            ),
            "workloads": NodeParameter(
                name="workloads",
                type=list,
                required=False,
                description="List of workloads to migrate",
            ),
            "strategy": NodeParameter(
                name="strategy",
                type=str,
                required=False,
                default="live",
                description="Migration strategy (live, staged, bulk, incremental, emergency)",
            ),
            "constraints": NodeParameter(
                name="constraints",
                type=dict,
                required=False,
                default={},
                description="Migration constraints (time_window, bandwidth, etc.)",
            ),
            "priority": NodeParameter(
                name="priority",
                type=int,
                required=False,
                default=5,
                description="Migration priority (1-10)",
            ),
            # For other operations
            "migration_id": NodeParameter(
                name="migration_id",
                type=str,
                required=False,
                description="Migration identifier",
            ),
            "checkpoint_id": NodeParameter(
                name="checkpoint_id",
                type=str,
                required=False,
                description="Checkpoint identifier for rollback",
            ),
            # Configuration
            "checkpoint_interval": NodeParameter(
                name="checkpoint_interval",
                type=int,
                required=False,
                default=60,
                description="Checkpoint creation interval (seconds)",
            ),
            "sync_batch_size": NodeParameter(
                name="sync_batch_size",
                type=int,
                required=False,
                default=1000,
                description="Records per sync batch",
            ),
            "bandwidth_limit_mbps": NodeParameter(
                name="bandwidth_limit_mbps",
                type=float,
                required=False,
                description="Bandwidth limit in Mbps",
            ),
            "enable_compression": NodeParameter(
                name="enable_compression",
                type=bool,
                required=False,
                default=True,
                description="Enable data compression",
            ),
        }

    @property
    def output_parameters(self) -> Dict[str, NodeParameter]:
        """Define output parameters."""
        return {
            "status": NodeParameter(
                name="status", type=str, description="Operation status"
            ),
            "plan": NodeParameter(
                name="plan",
                type=dict,
                required=False,
                description="Migration plan details",
            ),
            "progress": NodeParameter(
                name="progress",
                type=dict,
                required=False,
                description="Migration progress information",
            ),
            "result": NodeParameter(
                name="result", type=dict, required=False, description="Operation result"
            ),
            "migrations": NodeParameter(
                name="migrations",
                type=list,
                required=False,
                description="List of migrations",
            ),
            "metrics": NodeParameter(
                name="metrics",
                type=dict,
                required=False,
                description="Migration metrics",
            ),
            "migrator_active": NodeParameter(
                name="migrator_active",
                type=bool,
                required=False,
                description="Whether migrator service is active",
            ),
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get all node parameters for compatibility."""
        return self.input_parameters

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute migration operation."""
        operation = kwargs["operation"]

        try:
            if operation == "plan_migration":
                return await self._plan_migration(kwargs)
            elif operation == "execute_migration":
                return await self._execute_migration(kwargs)
            elif operation == "get_progress":
                return await self._get_progress(kwargs)
            elif operation == "pause_migration":
                return await self._pause_migration(kwargs)
            elif operation == "resume_migration":
                return await self._resume_migration(kwargs)
            elif operation == "rollback_migration":
                return await self._rollback_migration(kwargs)
            elif operation == "get_active_migrations":
                return await self._get_active_migrations()
            elif operation == "get_history":
                return await self._get_history()
            elif operation == "get_metrics":
                return await self._get_metrics()
            elif operation == "start_migrator":
                return await self._start_migrator()
            elif operation == "stop_migrator":
                return await self._stop_migrator()
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            self.logger.error(f"Edge migration operation failed: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def _plan_migration(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Plan a migration."""
        # Parse strategy
        strategy_name = kwargs.get("strategy", "live")
        try:
            strategy = MigrationStrategy(strategy_name)
        except ValueError:
            strategy = MigrationStrategy.LIVE

        # Create plan
        plan = await self.migrator.plan_migration(
            source_edge=kwargs.get("source_edge", "unknown"),
            target_edge=kwargs.get("target_edge", "unknown"),
            workloads=kwargs.get("workloads", []),
            strategy=strategy,
            constraints=kwargs.get("constraints", {}),
        )

        # Set priority
        plan.priority = kwargs.get("priority", 5)

        return {
            "status": "success",
            "plan": plan.to_dict(),
            "estimated_duration": self._estimate_duration(plan),
        }

    async def _execute_migration(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a migration."""
        migration_id = kwargs.get("migration_id")
        if not migration_id:
            raise ValueError("migration_id is required")

        # Start execution asynchronously
        result = await self.migrator.execute_migration(migration_id)

        return {"status": "success", "result": result}

    async def _get_progress(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get migration progress."""
        migration_id = kwargs.get("migration_id")
        if not migration_id:
            raise ValueError("migration_id is required")

        progress = await self.migrator.get_progress(migration_id)

        return {"status": "success", "progress": progress.to_dict()}

    async def _pause_migration(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Pause a migration."""
        migration_id = kwargs.get("migration_id")
        if not migration_id:
            raise ValueError("migration_id is required")

        result = await self.migrator.pause_migration(migration_id)

        return {"status": "success", "result": result}

    async def _resume_migration(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Resume a migration."""
        migration_id = kwargs.get("migration_id")
        if not migration_id:
            raise ValueError("migration_id is required")

        result = await self.migrator.resume_migration(migration_id)

        return {"status": "success", "result": result}

    async def _rollback_migration(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Rollback a migration."""
        migration_id = kwargs.get("migration_id")
        if not migration_id:
            raise ValueError("migration_id is required")

        checkpoint_id = kwargs.get("checkpoint_id")

        result = await self.migrator.rollback_migration(migration_id, checkpoint_id)

        return {"status": "success", "result": result}

    async def _get_active_migrations(self) -> Dict[str, Any]:
        """Get active migrations."""
        migrations = self.migrator.get_active_migrations()

        return {
            "status": "success",
            "migrations": [m.to_dict() for m in migrations],
            "count": len(migrations),
        }

    async def _get_history(self) -> Dict[str, Any]:
        """Get migration history."""
        history = self.migrator.get_migration_history()

        return {"status": "success", "migrations": history, "count": len(history)}

    async def _get_metrics(self) -> Dict[str, Any]:
        """Get migration metrics."""
        metrics = self.migrator.get_migration_metrics()

        return {"status": "success", "metrics": metrics}

    async def _start_migrator(self) -> Dict[str, Any]:
        """Start migrator service."""
        if not self._migrator_started:
            await self.migrator.start()
            self._migrator_started = True

        return {"status": "success", "migrator_active": True}

    async def _stop_migrator(self) -> Dict[str, Any]:
        """Stop migrator service."""
        if self._migrator_started:
            await self.migrator.stop()
            self._migrator_started = False

        return {"status": "success", "migrator_active": False}

    def _estimate_duration(self, plan: MigrationPlan) -> float:
        """Estimate migration duration in seconds."""
        # Simple estimation based on data size and strategy
        base_time = plan.data_size_estimate / (100 * 1024 * 1024)  # 100MB/s baseline

        strategy_multipliers = {
            MigrationStrategy.LIVE: 1.5,  # Extra time for live sync
            MigrationStrategy.STAGED: 1.2,  # Controlled phases
            MigrationStrategy.BULK: 1.0,  # Fastest
            MigrationStrategy.INCREMENTAL: 2.0,  # Multiple passes
            MigrationStrategy.EMERGENCY: 0.8,  # Fast but risky
        }

        multiplier = strategy_multipliers.get(plan.strategy, 1.0)

        # Add overhead for validation and cleanup
        overhead = 60 * len(plan.workloads)  # 1 minute per workload

        return base_time * multiplier + overhead

    async def cleanup(self):
        """Clean up resources."""
        if self._migrator_started:
            await self.migrator.stop()
