"""Migration models and base classes."""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Set


@dataclass
class MigrationHistory:
    """Record of a migration execution."""

    migration_id: str
    applied_at: datetime
    applied_by: str
    execution_time: float  # seconds
    success: bool
    error_message: Optional[str] = None
    rollback_at: Optional[datetime] = None
    rollback_by: Optional[str] = None


class Migration(ABC):
    """Base class for database migrations.

    Each migration should be a subclass implementing the forward()
    and backward() methods for applying and rolling back changes.

    Example:
        class AddUserTable(Migration):
            id = "001_add_user_table"
            description = "Create user table"
            dependencies = []

            async def forward(self, connection):
                await connection.execute('''
                    CREATE TABLE users (
                        id SERIAL PRIMARY KEY,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

            async def backward(self, connection):
                await connection.execute('DROP TABLE IF EXISTS users')
    """

    # Required attributes to override
    id: str = ""  # Unique migration ID
    description: str = ""  # Human-readable description
    dependencies: List[str] = []  # List of migration IDs this depends on

    def __init__(self):
        """Initialize migration."""
        if not self.id:
            raise ValueError("Migration must have an id")
        if not self.description:
            raise ValueError("Migration must have a description")

    @abstractmethod
    async def forward(self, connection: Any) -> None:
        """Apply the migration forward.

        Args:
            connection: Database connection object
        """
        pass

    @abstractmethod
    async def backward(self, connection: Any) -> None:
        """Roll back the migration.

        Args:
            connection: Database connection object
        """
        pass

    async def validate(self, connection: Any) -> bool:
        """Validate migration can be applied.

        Override this to add custom validation logic.

        Args:
            connection: Database connection object

        Returns:
            True if migration can be applied
        """
        return True

    def get_hash(self) -> str:
        """Get hash of migration for integrity checking."""
        content = f"{self.id}:{self.description}:{','.join(self.dependencies)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class SchemaMigration(Migration):
    """Migration for schema changes (DDL operations)."""

    def __init__(self):
        """Initialize schema migration."""
        super().__init__()
        self.operations: List[Dict[str, Any]] = []

    def add_table(
        self,
        table_name: str,
        columns: List[Dict[str, Any]],
        indexes: Optional[List[Dict[str, Any]]] = None,
    ):
        """Add create table operation."""
        self.operations.append(
            {
                "type": "create_table",
                "table": table_name,
                "columns": columns,
                "indexes": indexes or [],
            }
        )

    def drop_table(self, table_name: str):
        """Add drop table operation."""
        self.operations.append({"type": "drop_table", "table": table_name})

    def add_column(
        self,
        table_name: str,
        column_name: str,
        column_type: str,
        nullable: bool = True,
        default: Any = None,
    ):
        """Add column operation."""
        self.operations.append(
            {
                "type": "add_column",
                "table": table_name,
                "column": column_name,
                "column_type": column_type,
                "nullable": nullable,
                "default": default,
            }
        )

    def drop_column(self, table_name: str, column_name: str):
        """Add drop column operation."""
        self.operations.append(
            {"type": "drop_column", "table": table_name, "column": column_name}
        )

    def add_index(
        self, table_name: str, index_name: str, columns: List[str], unique: bool = False
    ):
        """Add create index operation."""
        self.operations.append(
            {
                "type": "create_index",
                "table": table_name,
                "index": index_name,
                "columns": columns,
                "unique": unique,
            }
        )

    def drop_index(self, table_name: str, index_name: str):
        """Add drop index operation."""
        self.operations.append(
            {"type": "drop_index", "table": table_name, "index": index_name}
        )


class DataMigration(Migration):
    """Migration for data changes (DML operations)."""

    def __init__(self):
        """Initialize data migration."""
        super().__init__()
        self.batch_size: int = 1000

    async def process_batch(
        self, connection: Any, query: str, params: Optional[List[Any]] = None
    ) -> int:
        """Process data in batches.

        Args:
            connection: Database connection
            query: Query to execute
            params: Query parameters

        Returns:
            Number of rows affected
        """
        # Implementation depends on specific database
        # This is a template method
        raise NotImplementedError


@dataclass
class MigrationPlan:
    """Execution plan for a set of migrations."""

    migrations_to_apply: List[Migration] = field(default_factory=list)
    migrations_to_rollback: List[Migration] = field(default_factory=list)
    dependency_order: List[str] = field(default_factory=list)
    estimated_time: float = 0.0  # seconds
    warnings: List[str] = field(default_factory=list)

    def add_warning(self, warning: str):
        """Add a warning to the plan."""
        self.warnings.append(warning)

    def is_safe(self) -> bool:
        """Check if plan is safe to execute."""
        # No rollbacks without specific handling
        if self.migrations_to_rollback:
            return False

        # Check circular dependencies
        applied: Set[str] = set()
        for migration_id in self.dependency_order:
            migration = next(
                (m for m in self.migrations_to_apply if m.id == migration_id), None
            )
            if migration:
                for dep in migration.dependencies:
                    if dep not in applied and dep in self.dependency_order:
                        return False
                applied.add(migration_id)

        return True
