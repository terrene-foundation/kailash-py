"""EdgeMigrationService singleton for shared migration state management.

This module provides a singleton EdgeMigrationService class that manages
shared migration state across all EdgeMigrationNode instances, enabling
proper cross-node migration workflows.
"""

import asyncio
import hashlib
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from kailash.edge.migration.edge_migrator import (
    EdgeMigrator,
    MigrationPhase,
    MigrationPlan,
    MigrationProgress,
    MigrationStrategy,
)

logger = logging.getLogger(__name__)


class EdgeMigrationService:
    """Singleton service managing shared migration state across EdgeMigrationNode instances.

    This service provides centralized management of migration plans, progress tracking,
    and shared state coordination. It follows the singleton pattern to ensure
    state consistency across multiple EdgeMigrationNode instances.
    """

    _instance: Optional["EdgeMigrationService"] = None
    _lock = threading.Lock()
    _state_lock = threading.RLock()  # For state access synchronization

    def __new__(cls, config: Optional[Dict[str, Any]] = None):
        """Create or return the singleton instance.

        Args:
            config: Migration service configuration

        Returns:
            The singleton EdgeMigrationService instance
        """
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the migration service.

        Args:
            config: Migration service configuration
        """
        # Only initialize once
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            logger.info("Initializing EdgeMigrationService singleton")

            # Merge with defaults
            self._config = self._merge_with_defaults(config or {})

            # Shared migration state (moved from EdgeMigrator instances)
            self._active_migrations: Dict[str, MigrationPlan] = {}
            self._migration_progress: Dict[str, MigrationProgress] = {}
            self._checkpoints: Dict[str, List] = defaultdict(list)
            self._completed_migrations: List[str] = []
            self._failed_migrations: Dict[str, str] = {}  # migration_id -> error

            # Migration ID reservation tracking
            self._reserved_ids: set = set()

            # Migrator instances per configuration
            self._migrators: Dict[str, EdgeMigrator] = {}

            # Metrics tracking
            self._metrics = {
                "total_migrations": 0,
                "active_migrations": 0,
                "completed_migrations": 0,
                "failed_migrations": 0,
                "success_rate": 100.0,
            }

            # Service state
            self._start_time = time.time()
            self._initialized = True

    def _merge_with_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge user config with default values.

        Args:
            config: User-provided configuration

        Returns:
            Merged configuration
        """
        defaults = {
            "checkpoint_interval": 60,
            "sync_batch_size": 1000,
            "bandwidth_limit_mbps": None,
            "enable_compression": True,
            "max_concurrent_migrations": 5,
            "cleanup_completed_after": 3600,  # 1 hour in seconds
        }

        # Deep merge
        merged = defaults.copy()
        merged.update(config)
        return merged

    def get_configuration(self) -> Dict[str, Any]:
        """Get current configuration.

        Returns:
            Current service configuration
        """
        return self._config.copy()

    def store_migration_plan(self, plan: MigrationPlan) -> None:
        """Store a migration plan in shared state.

        Args:
            plan: Migration plan to store
        """
        with self._state_lock:
            self._active_migrations[plan.migration_id] = plan

            # Initialize progress tracking
            if plan.migration_id not in self._migration_progress:
                self._migration_progress[plan.migration_id] = MigrationProgress(
                    migration_id=plan.migration_id,
                    phase=MigrationPhase.PLANNING,
                    progress_percent=0.0,
                    data_transferred=0,
                    workloads_migrated=[],
                    start_time=datetime.now(),
                )

            # Update metrics
            self._metrics["total_migrations"] = len(self._active_migrations) + len(
                self._completed_migrations
            )
            self._metrics["active_migrations"] = len(self._active_migrations)

    def get_migration_plan(self, migration_id: str) -> Optional[MigrationPlan]:
        """Get a migration plan from shared state.

        Args:
            migration_id: ID of migration to retrieve

        Returns:
            Migration plan if found, None otherwise
        """
        with self._state_lock:
            return self._active_migrations.get(migration_id)

    def get_migration_progress(self, migration_id: str) -> Optional[MigrationProgress]:
        """Get migration progress from shared state.

        Args:
            migration_id: ID of migration to get progress for

        Returns:
            Migration progress if found, None otherwise
        """
        with self._state_lock:
            return self._migration_progress.get(migration_id)

    def update_migration_progress(self, progress: MigrationProgress) -> None:
        """Update migration progress in shared state.

        Args:
            progress: Updated migration progress
        """
        with self._state_lock:
            self._migration_progress[progress.migration_id] = progress

    def reserve_migration_id(
        self, source_edge: str, target_edge: str, workloads: List[str]
    ) -> str:
        """Reserve a unique migration ID to prevent collisions.

        Args:
            source_edge: Source edge node
            target_edge: Target edge node
            workloads: List of workloads

        Returns:
            Reserved migration ID

        Raises:
            ValueError: If migration ID collision detected
        """
        with self._state_lock:
            # Generate ID based on parameters and timestamp
            timestamp = str(int(time.time() * 1000))  # millisecond precision
            content = (
                f"{source_edge}-{target_edge}-{'-'.join(sorted(workloads))}-{timestamp}"
            )
            migration_id = hashlib.md5(content.encode()).hexdigest()[:12]

            # Check for collision
            if (
                migration_id in self._reserved_ids
                or migration_id in self._active_migrations
            ):
                raise ValueError(f"Migration ID collision detected: {migration_id}")

            # Reserve the ID
            self._reserved_ids.add(migration_id)
            return f"migration-{migration_id}"

    def mark_migration_completed(self, migration_id: str) -> None:
        """Mark a migration as completed.

        Args:
            migration_id: ID of completed migration
        """
        with self._state_lock:
            if migration_id in self._active_migrations:
                del self._active_migrations[migration_id]
                self._completed_migrations.append(migration_id)

                # Update metrics
                self._metrics["active_migrations"] = len(self._active_migrations)
                self._metrics["completed_migrations"] = len(self._completed_migrations)
                self._update_success_rate()

    def mark_migration_failed(self, migration_id: str, error: str) -> None:
        """Mark a migration as failed.

        Args:
            migration_id: ID of failed migration
            error: Error message
        """
        with self._state_lock:
            if migration_id in self._active_migrations:
                del self._active_migrations[migration_id]
                self._failed_migrations[migration_id] = error

                # Update metrics
                self._metrics["active_migrations"] = len(self._active_migrations)
                self._metrics["failed_migrations"] = len(self._failed_migrations)
                self._update_success_rate()

    def _update_success_rate(self) -> None:
        """Update success rate metric."""
        total_completed = len(self._completed_migrations) + len(self._failed_migrations)
        if total_completed > 0:
            success_rate = (len(self._completed_migrations) / total_completed) * 100
            self._metrics["success_rate"] = round(success_rate, 2)
        else:
            self._metrics["success_rate"] = 100.0

    def get_active_migration_count(self) -> int:
        """Get count of active migrations.

        Returns:
            Number of active migrations
        """
        with self._state_lock:
            return len(self._active_migrations)

    def get_completed_migration_count(self) -> int:
        """Get count of completed migrations.

        Returns:
            Number of completed migrations
        """
        with self._state_lock:
            return len(self._completed_migrations)

    def cleanup_old_migrations(self) -> None:
        """Clean up old completed migrations based on configuration."""
        with self._state_lock:
            cleanup_threshold = self._config["cleanup_completed_after"]
            current_time = time.time()

            # For now, just limit the number of completed migrations kept
            # In a real implementation, we'd track completion timestamps
            max_completed = 100
            if len(self._completed_migrations) > max_completed:
                # Keep only the most recent ones
                self._completed_migrations = self._completed_migrations[-max_completed:]
                self._metrics["completed_migrations"] = len(self._completed_migrations)

    def get_migration_metrics(self) -> Dict[str, Any]:
        """Get migration metrics.

        Returns:
            Dictionary of migration metrics
        """
        with self._state_lock:
            return self._metrics.copy()

    async def plan_migration_async(
        self,
        source_edge: str,
        target_edge: str,
        workloads: List[str],
        strategy: MigrationStrategy = MigrationStrategy.LIVE,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> MigrationPlan:
        """Plan a migration asynchronously.

        Args:
            source_edge: Source edge node
            target_edge: Target edge node
            workloads: List of workloads to migrate
            strategy: Migration strategy
            constraints: Optional constraints

        Returns:
            Created migration plan
        """
        # Reserve unique migration ID
        migration_id = self.reserve_migration_id(source_edge, target_edge, workloads)

        # Create migration plan
        plan = MigrationPlan(
            migration_id=migration_id,
            source_edge=source_edge,
            target_edge=target_edge,
            strategy=strategy,
            workloads=workloads,
            data_size_estimate=len(workloads) * 1024 * 1024,  # Rough estimate
            constraints=constraints or {},
        )

        # Store in shared state
        self.store_migration_plan(plan)

        return plan

    def get_migrator_for_node(
        self, node_id: str, node_config: Optional[Dict[str, Any]] = None
    ) -> EdgeMigrator:
        """Get or create a migrator instance for a specific node.

        Args:
            node_id: Unique identifier for the node
            node_config: Node-specific configuration

        Returns:
            EdgeMigrator instance configured for the node
        """
        with self._state_lock:
            if node_id not in self._migrators:
                # Merge node config with service defaults
                migrator_config = self._config.copy()
                if node_config:
                    migrator_config.update(node_config)

                # Create migrator with shared state access
                migrator = EdgeMigrator(
                    checkpoint_interval=migrator_config.get("checkpoint_interval", 60),
                    sync_batch_size=migrator_config.get("sync_batch_size", 1000),
                    bandwidth_limit_mbps=migrator_config.get("bandwidth_limit_mbps"),
                    enable_compression=migrator_config.get("enable_compression", True),
                )

                # Override migrator's state dictionaries to use shared state
                migrator.active_migrations = self._active_migrations
                migrator.migration_progress = self._migration_progress
                migrator.checkpoints = self._checkpoints
                migrator.completed_migrations = self._completed_migrations

                self._migrators[node_id] = migrator

            return self._migrators[node_id]
