"""DataFlow Migration Generator Module."""

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional


class MigrationGenerator:
    """Generates database migration scripts."""

    def __init__(self):
        self.templates = {
            "create_table": "CREATE TABLE {table_name} ({columns});",
            "drop_table": "DROP TABLE {table_name};",
            "add_column": "ALTER TABLE {table_name} ADD COLUMN {column_definition};",
            "drop_column": "ALTER TABLE {table_name} DROP COLUMN {column_name};",
            "create_index": "CREATE INDEX {index_name} ON {table_name} ({columns});",
            "drop_index": "DROP INDEX {index_name};",
        }

    def generate_create_table(
        self, table_name: str, columns: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Generate CREATE TABLE migration."""
        column_defs = []
        for col in columns:
            col_def = f"{col['name']} {col['type']}"
            if col.get("primary_key"):
                col_def += " PRIMARY KEY"
            if col.get("not_null"):
                col_def += " NOT NULL"
            if "default" in col:
                col_def += f" DEFAULT {col['default']}"
            column_defs.append(col_def)

        up_script = self.templates["create_table"].format(
            table_name=table_name, columns=", ".join(column_defs)
        )

        down_script = self.templates["drop_table"].format(table_name=table_name)

        return {
            "up": up_script,
            "down": down_script,
            "id": self._generate_migration_id(f"create_table_{table_name}"),
        }

    def generate_add_column(
        self,
        table_name: str,
        column_name: str,
        column_type: str,
        not_null: bool = False,
        default: Optional[Any] = None,
    ) -> Dict[str, str]:
        """Generate ADD COLUMN migration."""
        col_def = f"{column_name} {column_type}"
        if not_null:
            col_def += " NOT NULL"
        if default is not None:
            col_def += f" DEFAULT {default}"

        up_script = self.templates["add_column"].format(
            table_name=table_name, column_definition=col_def
        )

        down_script = self.templates["drop_column"].format(
            table_name=table_name, column_name=column_name
        )

        return {
            "up": up_script,
            "down": down_script,
            "id": self._generate_migration_id(f"add_column_{table_name}_{column_name}"),
        }

    def generate_create_index(
        self, table_name: str, index_name: str, columns: List[str], unique: bool = False
    ) -> Dict[str, str]:
        """Generate CREATE INDEX migration."""
        index_type = "UNIQUE INDEX" if unique else "INDEX"
        up_template = (
            f"CREATE {index_type} {{index_name}} ON {{table_name}} ({{columns}});"
        )

        up_script = up_template.format(
            index_name=index_name, table_name=table_name, columns=", ".join(columns)
        )

        down_script = self.templates["drop_index"].format(index_name=index_name)

        return {
            "up": up_script,
            "down": down_script,
            "id": self._generate_migration_id(f"create_index_{index_name}"),
        }

    def generate_migration_from_diff(
        self, old_schema: Dict[str, Any], new_schema: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Generate migrations based on schema differences."""
        migrations = []

        # Check for new tables
        old_tables = set(old_schema.get("tables", {}).keys())
        new_tables = set(new_schema.get("tables", {}).keys())

        # Tables to create
        for table in new_tables - old_tables:
            migrations.append(
                self.generate_create_table(
                    table, new_schema["tables"][table]["columns"]
                )
            )

        # Tables to drop
        for table in old_tables - new_tables:
            migrations.append(
                {
                    "up": self.templates["drop_table"].format(table_name=table),
                    "down": self._reconstruct_create_table(
                        table, old_schema["tables"][table]
                    ),
                    "id": self._generate_migration_id(f"drop_table_{table}"),
                }
            )

        # Check for column changes in existing tables
        for table in old_tables & new_tables:
            old_columns = {c["name"] for c in old_schema["tables"][table]["columns"]}
            new_columns = {c["name"] for c in new_schema["tables"][table]["columns"]}

            # New columns
            for col_name in new_columns - old_columns:
                col_def = next(
                    c
                    for c in new_schema["tables"][table]["columns"]
                    if c["name"] == col_name
                )
                migrations.append(
                    self.generate_add_column(
                        table,
                        col_name,
                        col_def["type"],
                        col_def.get("not_null", False),
                        col_def.get("default"),
                    )
                )

        return migrations

    def _generate_migration_id(self, description: str) -> str:
        """Generate unique migration ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        hash_suffix = hashlib.md5(description.encode()).hexdigest()[:6]
        return f"{timestamp}_{hash_suffix}"

    def _reconstruct_create_table(
        self, table_name: str, table_schema: Dict[str, Any]
    ) -> str:
        """Reconstruct CREATE TABLE statement from schema."""
        return self.generate_create_table(table_name, table_schema["columns"])["up"]
