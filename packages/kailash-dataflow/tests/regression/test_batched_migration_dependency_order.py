"""Execute planned SQLite DDL to verify prerequisite ordering."""

import itertools
import logging
import sqlite3
from contextlib import closing

import pytest

from dataflow.migrations.auto_migration_system import MigrationOperation, MigrationType
from dataflow.migrations.batched_migration_executor import BatchedMigrationExecutor

pytestmark = pytest.mark.regression
LOGGER = "dataflow.migrations.batched_migration_executor"


def operations():
    definitions = {
        "create": (
            MigrationType.CREATE_TABLE,
            "CREATE TABLE proof(id INTEGER PRIMARY KEY, value TEXT)",
        ),
        "add": (MigrationType.ADD_COLUMN, "ALTER TABLE proof ADD COLUMN extra TEXT"),
        "index": (MigrationType.ADD_INDEX, "CREATE INDEX proof_extra ON proof(extra)"),
        "rename": (
            MigrationType.RENAME_COLUMN,
            "ALTER TABLE proof RENAME COLUMN value TO renamed",
        ),
    }
    return {
        name: MigrationOperation(
            operation_type=kind,
            table_name="proof",
            description=name,
            sql_up=sql,
            sql_down="DROP TABLE proof",
            metadata={},
        )
        for name, (kind, sql) in definitions.items()
    }


@pytest.mark.parametrize(
    "order", list(itertools.permutations(("create", "add", "index", "rename")))
)
def test_every_input_order_produces_executable_prerequisite_batches(order, caplog):
    declared = operations()
    with closing(sqlite3.connect(":memory:")) as connection:
        executor = BatchedMigrationExecutor(connection)
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            batches = executor.batch_ddl_operations([declared[name] for name in order])
        for batch in batches:
            for statement in batch:
                connection.execute(statement)
        assert [row[1] for row in connection.execute("PRAGMA table_info(proof)")] == [
            "id",
            "renamed",
            "extra",
        ]
        assert [
            row[2] for row in connection.execute("PRAGMA index_info(proof_extra)")
        ] == ["extra"]
        assert sum(map(len, batches)) == 4
    assert not [
        record
        for record in caplog.records
        if record.name == LOGGER and record.levelno >= logging.WARNING
    ]


def test_real_cycle_retains_explicit_warning_and_original_order(caplog):
    declared = list(operations().values())[:2]
    executor = BatchedMigrationExecutor(None)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        result = executor._topological_sort(declared, {0: {1}, 1: {0}})
    assert result == declared
    assert [
        record.getMessage() for record in caplog.records if record.name == LOGGER
    ] == ["Circular dependency detected, using original order"]
