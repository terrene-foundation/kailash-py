"""DataFlow Schema Comparison Module."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set


@dataclass
class SchemaDifference:
    """Represents a difference between two schemas."""

    diff_type: str  # 'table_added', 'table_removed', 'column_added', etc.
    table_name: str
    details: Dict[str, Any]


class SchemaComparison:
    """Compares database schemas and identifies differences."""

    def __init__(self):
        self.differences: List[SchemaDifference] = []

    def compare_schemas(
        self, source_schema: Dict[str, Any], target_schema: Dict[str, Any]
    ) -> List[SchemaDifference]:
        """Compare two schemas and return differences."""
        self.differences = []

        source_tables = set(source_schema.get("tables", {}).keys())
        target_tables = set(target_schema.get("tables", {}).keys())

        # Check for added tables
        for table in target_tables - source_tables:
            self.differences.append(
                SchemaDifference(
                    diff_type="table_added",
                    table_name=table,
                    details={"table_schema": target_schema["tables"][table]},
                )
            )

        # Check for removed tables
        for table in source_tables - target_tables:
            self.differences.append(
                SchemaDifference(
                    diff_type="table_removed",
                    table_name=table,
                    details={"table_schema": source_schema["tables"][table]},
                )
            )

        # Check for changes in existing tables
        for table in source_tables & target_tables:
            self._compare_table_schemas(
                table, source_schema["tables"][table], target_schema["tables"][table]
            )

        return self.differences

    def _compare_table_schemas(
        self,
        table_name: str,
        source_table: Dict[str, Any],
        target_table: Dict[str, Any],
    ):
        """Compare schemas of a single table."""
        source_columns = {c["name"]: c for c in source_table.get("columns", [])}
        target_columns = {c["name"]: c for c in target_table.get("columns", [])}

        source_col_names = set(source_columns.keys())
        target_col_names = set(target_columns.keys())

        # Added columns
        for col_name in target_col_names - source_col_names:
            self.differences.append(
                SchemaDifference(
                    diff_type="column_added",
                    table_name=table_name,
                    details={"column": target_columns[col_name]},
                )
            )

        # Removed columns
        for col_name in source_col_names - target_col_names:
            self.differences.append(
                SchemaDifference(
                    diff_type="column_removed",
                    table_name=table_name,
                    details={"column": source_columns[col_name]},
                )
            )

        # Modified columns
        for col_name in source_col_names & target_col_names:
            source_col = source_columns[col_name]
            target_col = target_columns[col_name]

            if self._column_differs(source_col, target_col):
                self.differences.append(
                    SchemaDifference(
                        diff_type="column_modified",
                        table_name=table_name,
                        details={
                            "column_name": col_name,
                            "old": source_col,
                            "new": target_col,
                        },
                    )
                )

        # Compare indexes
        self._compare_indexes(table_name, source_table, target_table)

    def _column_differs(self, col1: Dict[str, Any], col2: Dict[str, Any]) -> bool:
        """Check if two column definitions differ."""
        # Compare key attributes
        attributes = ["type", "not_null", "default", "primary_key", "unique"]

        for attr in attributes:
            if col1.get(attr) != col2.get(attr):
                return True

        return False

    def _compare_indexes(
        self,
        table_name: str,
        source_table: Dict[str, Any],
        target_table: Dict[str, Any],
    ):
        """Compare indexes between two table schemas."""
        source_indexes = {idx["name"]: idx for idx in source_table.get("indexes", [])}
        target_indexes = {idx["name"]: idx for idx in target_table.get("indexes", [])}

        source_idx_names = set(source_indexes.keys())
        target_idx_names = set(target_indexes.keys())

        # Added indexes
        for idx_name in target_idx_names - source_idx_names:
            self.differences.append(
                SchemaDifference(
                    diff_type="index_added",
                    table_name=table_name,
                    details={"index": target_indexes[idx_name]},
                )
            )

        # Removed indexes
        for idx_name in source_idx_names - target_idx_names:
            self.differences.append(
                SchemaDifference(
                    diff_type="index_removed",
                    table_name=table_name,
                    details={"index": source_indexes[idx_name]},
                )
            )

    def generate_summary(self) -> Dict[str, Any]:
        """Generate a summary of schema differences."""
        summary = {
            "total_differences": len(self.differences),
            "tables_added": 0,
            "tables_removed": 0,
            "columns_added": 0,
            "columns_removed": 0,
            "columns_modified": 0,
            "indexes_added": 0,
            "indexes_removed": 0,
        }

        for diff in self.differences:
            if diff.diff_type == "table_added":
                summary["tables_added"] += 1
            elif diff.diff_type == "table_removed":
                summary["tables_removed"] += 1
            elif diff.diff_type == "column_added":
                summary["columns_added"] += 1
            elif diff.diff_type == "column_removed":
                summary["columns_removed"] += 1
            elif diff.diff_type == "column_modified":
                summary["columns_modified"] += 1
            elif diff.diff_type == "index_added":
                summary["indexes_added"] += 1
            elif diff.diff_type == "index_removed":
                summary["indexes_removed"] += 1

        return summary
