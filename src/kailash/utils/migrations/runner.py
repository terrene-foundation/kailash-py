"""Migration runner for executing database migrations."""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Set, Type

from kailash.nodes.data.async_connection import get_connection_manager
from kailash.utils.migrations.models import Migration, MigrationHistory, MigrationPlan

logger = logging.getLogger(__name__)


class MigrationRunner:
    """Executes database migrations with dependency management.

    This class handles the execution of migrations, tracking their
    status, managing dependencies, and providing rollback capabilities.

    Example:
        >>> runner = MigrationRunner(db_config)
        >>> await runner.initialize()
        >>>
        >>> # Apply all pending migrations
        >>> plan = await runner.create_plan()
        >>> await runner.execute_plan(plan)
        >>>
        >>> # Rollback specific migration
        >>> await runner.rollback_migration("001_add_user_table")
    """

    def __init__(
        self,
        db_config: Dict[str, Any],
        tenant_id: str = "default",
        migration_table: str = "kailash_migrations",
    ):
        """Initialize migration runner.

        Args:
            db_config: Database configuration
            tenant_id: Tenant identifier for multi-tenant systems
            migration_table: Table name for tracking migrations
        """
        self.db_config = db_config
        self.tenant_id = tenant_id
        self.migration_table = migration_table
        self.connection_manager = get_connection_manager()
        self.registered_migrations: Dict[str, Type[Migration]] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize migration tracking table."""
        if self._initialized:
            return

        async with self.connection_manager.get_connection(
            self.tenant_id, self.db_config
        ) as conn:
            # Create migration tracking table
            await self._create_migration_table(conn)

        self._initialized = True
        logger.info(f"Migration runner initialized for tenant {self.tenant_id}")

    async def _create_migration_table(self, conn: Any):
        """Create migration tracking table if not exists."""
        db_type = self.db_config.get("type", "postgresql")

        if db_type == "postgresql":
            query = f"""
            CREATE TABLE IF NOT EXISTS {self.migration_table} (
                migration_id VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL,
                applied_by VARCHAR(255) NOT NULL,
                execution_time FLOAT NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                rollback_at TIMESTAMP,
                rollback_by VARCHAR(255),
                migration_hash VARCHAR(32)
            )
            """
        elif db_type == "mysql":
            query = f"""
            CREATE TABLE IF NOT EXISTS {self.migration_table} (
                migration_id VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL,
                applied_by VARCHAR(255) NOT NULL,
                execution_time FLOAT NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                rollback_at TIMESTAMP NULL,
                rollback_by VARCHAR(255),
                migration_hash VARCHAR(32)
            )
            """
        elif db_type == "sqlite":
            query = f"""
            CREATE TABLE IF NOT EXISTS {self.migration_table} (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL,
                applied_by TEXT NOT NULL,
                execution_time REAL NOT NULL,
                success INTEGER NOT NULL,
                error_message TEXT,
                rollback_at TEXT,
                rollback_by TEXT,
                migration_hash TEXT
            )
            """
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

        await conn.execute(query)

    def register_migration(self, migration_class: Type[Migration]):
        """Register a migration class.

        Args:
            migration_class: Migration class to register
        """
        instance = migration_class()
        if instance.id in self.registered_migrations:
            raise ValueError(f"Migration {instance.id} already registered")

        self.registered_migrations[instance.id] = migration_class
        logger.debug(f"Registered migration: {instance.id}")

    def register_migrations_from_module(self, module: Any):
        """Register all migrations from a module.

        Args:
            module: Python module containing Migration subclasses
        """
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, Migration)
                and attr != Migration
            ):
                self.register_migration(attr)

    async def get_applied_migrations(self) -> Set[str]:
        """Get set of applied migration IDs."""
        if not self._initialized:
            await self.initialize()

        async with self.connection_manager.get_connection(
            self.tenant_id, self.db_config
        ) as conn:
            query = f"""
            SELECT migration_id
            FROM {self.migration_table}
            WHERE success = true AND rollback_at IS NULL
            """

            rows = await conn.fetch(query)
            return {row["migration_id"] for row in rows}

    async def get_migration_history(
        self, migration_id: Optional[str] = None
    ) -> List[MigrationHistory]:
        """Get migration history.

        Args:
            migration_id: Optional specific migration to get history for

        Returns:
            List of migration history records
        """
        if not self._initialized:
            await self.initialize()

        async with self.connection_manager.get_connection(
            self.tenant_id, self.db_config
        ) as conn:
            if migration_id:
                query = f"""
                SELECT * FROM {self.migration_table}
                WHERE migration_id = $1
                ORDER BY applied_at DESC
                """
                rows = await conn.fetch(query, migration_id)
            else:
                query = f"""
                SELECT * FROM {self.migration_table}
                ORDER BY applied_at DESC
                """
                rows = await conn.fetch(query)

            history = []
            for row in rows:
                history.append(
                    MigrationHistory(
                        migration_id=row["migration_id"],
                        applied_at=row["applied_at"],
                        applied_by=row["applied_by"],
                        execution_time=row["execution_time"],
                        success=row["success"],
                        error_message=row.get("error_message"),
                        rollback_at=row.get("rollback_at"),
                        rollback_by=row.get("rollback_by"),
                    )
                )

            return history

    async def create_plan(
        self, target_migration: Optional[str] = None, rollback: bool = False
    ) -> MigrationPlan:
        """Create execution plan for migrations.

        Args:
            target_migration: Optional specific migration to target
            rollback: Whether to create rollback plan

        Returns:
            Migration execution plan
        """
        if not self._initialized:
            await self.initialize()

        plan = MigrationPlan()
        applied = await self.get_applied_migrations()

        if rollback:
            # Create rollback plan
            if not target_migration:
                raise ValueError("target_migration required for rollback")

            if target_migration not in applied:
                plan.add_warning(f"Migration {target_migration} not applied")
                return plan

            # TODO: Implement dependency checking for rollback
            migration_class = self.registered_migrations.get(target_migration)
            if migration_class:
                plan.migrations_to_rollback.append(migration_class())
        else:
            # Create forward migration plan
            pending = []

            for migration_id, migration_class in self.registered_migrations.items():
                if migration_id not in applied:
                    instance = migration_class()

                    # Check dependencies
                    missing_deps = [
                        dep
                        for dep in instance.dependencies
                        if dep not in applied and dep not in self.registered_migrations
                    ]

                    if missing_deps:
                        plan.add_warning(
                            f"Migration {migration_id} has missing dependencies: "
                            f"{', '.join(missing_deps)}"
                        )
                    else:
                        pending.append(instance)

            # Sort by dependencies
            plan.migrations_to_apply = self._topological_sort(pending)
            plan.dependency_order = [m.id for m in plan.migrations_to_apply]

            # Stop at target if specified
            if target_migration and target_migration in plan.dependency_order:
                idx = plan.dependency_order.index(target_migration)
                plan.migrations_to_apply = plan.migrations_to_apply[: idx + 1]
                plan.dependency_order = plan.dependency_order[: idx + 1]

        # Estimate execution time (rough estimate)
        plan.estimated_time = len(plan.migrations_to_apply) * 2.0

        return plan

    def _topological_sort(self, migrations: List[Migration]) -> List[Migration]:
        """Sort migrations by dependencies."""
        # Build dependency graph
        graph: Dict[str, Set[str]] = {}
        migration_map = {m.id: m for m in migrations}

        for migration in migrations:
            graph[migration.id] = set(
                dep for dep in migration.dependencies if dep in migration_map
            )

        # Kahn's algorithm
        sorted_migrations = []
        no_deps = [m_id for m_id, deps in graph.items() if not deps]

        while no_deps:
            current = no_deps.pop(0)
            sorted_migrations.append(migration_map[current])

            # Remove current from dependencies
            for m_id, deps in graph.items():
                if current in deps:
                    deps.remove(current)
                    if not deps and m_id not in [m.id for m in sorted_migrations]:
                        no_deps.append(m_id)

        # Check for cycles
        if len(sorted_migrations) != len(migrations):
            remaining = set(m.id for m in migrations) - set(
                m.id for m in sorted_migrations
            )
            raise ValueError(f"Circular dependencies detected: {remaining}")

        return sorted_migrations

    async def execute_plan(
        self, plan: MigrationPlan, dry_run: bool = False, user: str = "system"
    ) -> List[MigrationHistory]:
        """Execute migration plan.

        Args:
            plan: Migration plan to execute
            dry_run: If True, validate but don't apply changes
            user: User executing migrations

        Returns:
            List of migration history records
        """
        if not plan.is_safe():
            raise ValueError("Migration plan is not safe to execute")

        history = []

        if plan.migrations_to_rollback:
            # Execute rollbacks
            for migration in plan.migrations_to_rollback:
                record = await self._rollback_migration(migration, user, dry_run)
                history.append(record)
        else:
            # Execute forward migrations
            for migration in plan.migrations_to_apply:
                record = await self._apply_migration(migration, user, dry_run)
                history.append(record)

                if not record.success:
                    logger.error(f"Migration {migration.id} failed, stopping execution")
                    break

        return history

    async def _apply_migration(
        self, migration: Migration, user: str, dry_run: bool
    ) -> MigrationHistory:
        """Apply a single migration."""
        logger.info(f"Applying migration: {migration.id}")

        start_time = time.time()
        success = True
        error_message = None

        try:
            async with self.connection_manager.get_connection(
                self.tenant_id, self.db_config
            ) as conn:
                # Validate migration
                if not await migration.validate(conn):
                    raise ValueError("Migration validation failed")

                if not dry_run:
                    # Begin transaction
                    if hasattr(conn, "transaction"):
                        async with conn.transaction():
                            await migration.forward(conn)
                    else:
                        await migration.forward(conn)

                    # Record success
                    await self._record_migration(
                        conn, migration, user, time.time() - start_time, True, None
                    )

        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"Migration {migration.id} failed: {e}")

            if not dry_run:
                # Record failure
                try:
                    async with self.connection_manager.get_connection(
                        self.tenant_id, self.db_config
                    ) as conn:
                        await self._record_migration(
                            conn,
                            migration,
                            user,
                            time.time() - start_time,
                            False,
                            error_message,
                        )
                except Exception as record_error:
                    logger.error(f"Failed to record migration failure: {record_error}")

        return MigrationHistory(
            migration_id=migration.id,
            applied_at=datetime.now(UTC),
            applied_by=user,
            execution_time=time.time() - start_time,
            success=success,
            error_message=error_message,
        )

    async def _rollback_migration(
        self, migration: Migration, user: str, dry_run: bool
    ) -> MigrationHistory:
        """Rollback a single migration."""
        logger.info(f"Rolling back migration: {migration.id}")

        start_time = time.time()
        success = True
        error_message = None

        try:
            async with self.connection_manager.get_connection(
                self.tenant_id, self.db_config
            ) as conn:
                if not dry_run:
                    # Begin transaction
                    if hasattr(conn, "transaction"):
                        async with conn.transaction():
                            await migration.backward(conn)
                    else:
                        await migration.backward(conn)

                    # Update migration record
                    await self._update_migration_rollback(conn, migration.id, user)

        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"Rollback of {migration.id} failed: {e}")

        return MigrationHistory(
            migration_id=migration.id,
            applied_at=datetime.now(UTC),
            applied_by=user,
            execution_time=time.time() - start_time,
            success=success,
            error_message=error_message,
            rollback_at=datetime.now(UTC),
            rollback_by=user,
        )

    async def _record_migration(
        self,
        conn: Any,
        migration: Migration,
        user: str,
        execution_time: float,
        success: bool,
        error_message: Optional[str],
    ):
        """Record migration execution."""
        query = f"""
        INSERT INTO {self.migration_table} (
            migration_id, applied_at, applied_by, execution_time,
            success, error_message, migration_hash
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """

        await conn.execute(
            query,
            migration.id,
            datetime.now(UTC),
            user,
            execution_time,
            success,
            error_message,
            migration.get_hash(),
        )

    async def _update_migration_rollback(self, conn: Any, migration_id: str, user: str):
        """Update migration record for rollback."""
        query = f"""
        UPDATE {self.migration_table}
        SET rollback_at = $1, rollback_by = $2
        WHERE migration_id = $3 AND rollback_at IS NULL
        """

        await conn.execute(query, datetime.now(UTC), user, migration_id)
