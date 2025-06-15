"""Migration generator for creating migration files."""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class MigrationGenerator:
    """Generates migration files from templates.

    This class helps create new migration files with proper structure,
    naming conventions, and boilerplate code.

    Example:
        >>> generator = MigrationGenerator("./migrations")
        >>> generator.create_migration(
        ...     name="add_user_table",
        ...     description="Create user table with email and password"
        ... )
        Created migration: ./migrations/001_add_user_table.py
    """

    def __init__(self, migrations_dir: str = "./migrations"):
        """Initialize generator.

        Args:
            migrations_dir: Directory to store migration files
        """
        self.migrations_dir = Path(migrations_dir)
        self.migrations_dir.mkdir(parents=True, exist_ok=True)

    def get_next_migration_number(self) -> str:
        """Get next migration number based on existing files."""
        existing_numbers = []

        for file in self.migrations_dir.glob("*.py"):
            match = re.match(r"^(\d+)_", file.name)
            if match:
                existing_numbers.append(int(match.group(1)))

        next_number = max(existing_numbers, default=0) + 1
        return f"{next_number:03d}"

    def create_migration(
        self,
        name: str,
        description: str,
        migration_type: str = "schema",
        dependencies: Optional[List[str]] = None,
    ) -> str:
        """Create a new migration file.

        Args:
            name: Migration name (will be slugified)
            description: Human-readable description
            migration_type: Type of migration (schema/data)
            dependencies: List of migration IDs this depends on

        Returns:
            Path to created migration file
        """
        # Slugify name
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

        # Get migration ID
        number = self.get_next_migration_number()
        migration_id = f"{number}_{slug}"
        filename = f"{migration_id}.py"
        filepath = self.migrations_dir / filename

        # Generate content
        if migration_type == "schema":
            content = self._generate_schema_migration(
                migration_id, description, dependencies
            )
        elif migration_type == "data":
            content = self._generate_data_migration(
                migration_id, description, dependencies
            )
        else:
            content = self._generate_base_migration(
                migration_id, description, dependencies
            )

        # Write file
        filepath.write_text(content)
        print(f"Created migration: {filepath}")

        return str(filepath)

    def _generate_base_migration(
        self,
        migration_id: str,
        description: str,
        dependencies: Optional[List[str]] = None,
    ) -> str:
        """Generate base migration template."""
        deps = dependencies or []
        deps_str = ", ".join(f'"{d}"' for d in deps)

        return f'''"""
{description}

Generated on: {datetime.now().isoformat()}
"""

from kailash.utils.migrations import Migration


class {self._class_name(migration_id)}(Migration):
    """{description}"""

    id = "{migration_id}"
    description = "{description}"
    dependencies = [{deps_str}]

    async def forward(self, connection):
        """Apply migration forward."""
        # TODO: Implement forward migration
        raise NotImplementedError("Forward migration not implemented")

    async def backward(self, connection):
        """Rollback migration."""
        # TODO: Implement backward migration
        raise NotImplementedError("Backward migration not implemented")

    async def validate(self, connection):
        """Validate migration can be applied."""
        # Add any validation logic here
        return True
'''

    def _generate_schema_migration(
        self,
        migration_id: str,
        description: str,
        dependencies: Optional[List[str]] = None,
    ) -> str:
        """Generate schema migration template."""
        deps = dependencies or []
        deps_str = ", ".join(f'"{d}"' for d in deps)

        return f'''"""
{description}

Generated on: {datetime.now().isoformat()}
"""

from kailash.utils.migrations import Migration


class {self._class_name(migration_id)}(Migration):
    """{description}"""

    id = "{migration_id}"
    description = "{description}"
    dependencies = [{deps_str}]

    async def forward(self, connection):
        """Apply migration forward."""
        # Example: Create table
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS example_table (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Example: Add index
        await connection.execute("""
            CREATE INDEX idx_example_name ON example_table(name)
        """)

    async def backward(self, connection):
        """Rollback migration."""
        # Drop in reverse order
        await connection.execute("DROP TABLE IF EXISTS example_table CASCADE")
'''

    def _generate_data_migration(
        self,
        migration_id: str,
        description: str,
        dependencies: Optional[List[str]] = None,
    ) -> str:
        """Generate data migration template."""
        deps = dependencies or []
        deps_str = ", ".join(f'"{d}"' for d in deps)

        return f'''"""
{description}

Generated on: {datetime.now().isoformat()}
"""

from kailash.utils.migrations import DataMigration


class {self._class_name(migration_id)}(DataMigration):
    """{description}"""

    id = "{migration_id}"
    description = "{description}"
    dependencies = [{deps_str}]
    batch_size = 1000

    async def forward(self, connection):
        """Apply migration forward."""
        # Example: Update data in batches
        total_updated = 0

        while True:
            # Get batch of records to update
            rows = await connection.fetch("""
                SELECT id FROM example_table
                WHERE needs_update = true
                LIMIT $1
            """, self.batch_size)

            if not rows:
                break

            # Update batch
            ids = [row["id"] for row in rows]
            await connection.execute("""
                UPDATE example_table
                SET processed = true, updated_at = CURRENT_TIMESTAMP
                WHERE id = ANY($1)
            """, ids)

            total_updated += len(rows)
            print(f"Updated {{total_updated}} records...")

        print(f"Migration complete. Updated {{total_updated}} total records.")

    async def backward(self, connection):
        """Rollback migration."""
        # Reverse the data changes
        await connection.execute("""
            UPDATE example_table
            SET processed = false
            WHERE processed = true
        """)
'''

    def _class_name(self, migration_id: str) -> str:
        """Convert migration ID to class name."""
        # Remove number prefix and convert to CamelCase
        name_part = re.sub(r"^\d+_", "", migration_id)
        parts = name_part.split("_")
        return "".join(part.capitalize() for part in parts)

    def create_initial_migrations(self) -> List[str]:
        """Create initial system migrations."""
        migrations = []

        # Create users table migration
        migrations.append(
            self.create_migration(
                name="create_users_table",
                description="Create users table for authentication",
                migration_type="schema",
            )
        )

        # Create tenants table migration
        migrations.append(
            self.create_migration(
                name="create_tenants_table",
                description="Create tenants table for multi-tenancy",
                migration_type="schema",
                dependencies=["001_create_users_table"],
            )
        )

        # Create workflow tracking tables
        migrations.append(
            self.create_migration(
                name="create_workflow_tables",
                description="Create workflow execution tracking tables",
                migration_type="schema",
                dependencies=["001_create_users_table", "002_create_tenants_table"],
            )
        )

        return migrations

    def generate_from_diff(
        self,
        current_schema: Dict[str, Any],
        target_schema: Dict[str, Any],
        name: str,
        description: str,
    ) -> str:
        """Generate migration from schema difference.

        Args:
            current_schema: Current database schema
            target_schema: Desired database schema
            name: Migration name
            description: Migration description

        Returns:
            Path to generated migration
        """
        # Analyze differences
        operations = self._analyze_schema_diff(current_schema, target_schema)

        # Generate migration with operations
        number = self.get_next_migration_number()
        migration_id = f"{number}_{re.sub(r'[^a-z0-9]+', '_', name.lower())}"

        content = self._generate_diff_migration(migration_id, description, operations)

        filename = f"{migration_id}.py"
        filepath = self.migrations_dir / filename
        filepath.write_text(content)

        return str(filepath)

    def _analyze_schema_diff(
        self, current: Dict[str, Any], target: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Analyze schema differences."""
        operations = []

        current_tables = set(current.get("tables", {}).keys())
        target_tables = set(target.get("tables", {}).keys())

        # Find new tables
        for table in target_tables - current_tables:
            operations.append(
                {
                    "type": "create_table",
                    "table": table,
                    "definition": target["tables"][table],
                }
            )

        # Find dropped tables
        for table in current_tables - target_tables:
            operations.append({"type": "drop_table", "table": table})

        # Find modified tables
        for table in current_tables & target_tables:
            table_ops = self._analyze_table_diff(
                table, current["tables"][table], target["tables"][table]
            )
            operations.extend(table_ops)

        return operations

    def _analyze_table_diff(
        self, table_name: str, current: Dict[str, Any], target: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Analyze table differences."""
        operations = []

        current_columns = set(current.get("columns", {}).keys())
        target_columns = set(target.get("columns", {}).keys())

        # New columns
        for col in target_columns - current_columns:
            operations.append(
                {
                    "type": "add_column",
                    "table": table_name,
                    "column": col,
                    "definition": target["columns"][col],
                }
            )

        # Dropped columns
        for col in current_columns - target_columns:
            operations.append(
                {"type": "drop_column", "table": table_name, "column": col}
            )

        return operations

    def _generate_diff_migration(
        self, migration_id: str, description: str, operations: List[Dict[str, Any]]
    ) -> str:
        """Generate migration from operations."""
        forward_ops = []
        backward_ops = []

        for op in operations:
            if op["type"] == "create_table":
                forward_ops.append(
                    f'await connection.execute("""{self._create_table_sql(op)}""")'
                )
                backward_ops.append(
                    f'await connection.execute("DROP TABLE IF EXISTS {op["table"]} CASCADE")'
                )
            # Add more operation types as needed

        forward_code = "\n        ".join(forward_ops) or "pass"
        backward_code = "\n        ".join(reversed(backward_ops)) or "pass"

        return f'''"""
{description}

Generated on: {datetime.now().isoformat()}
Auto-generated from schema diff
"""

from kailash.utils.migrations import Migration


class {self._class_name(migration_id)}(Migration):
    """{description}"""

    id = "{migration_id}"
    description = "{description}"
    dependencies = []

    async def forward(self, connection):
        """Apply migration forward."""
        {forward_code}

    async def backward(self, connection):
        """Rollback migration."""
        {backward_code}
'''

    def _create_table_sql(self, operation: Dict[str, Any]) -> str:
        """Generate CREATE TABLE SQL."""
        # Simplified example
        return f"CREATE TABLE {operation['table']} (id SERIAL PRIMARY KEY)"
