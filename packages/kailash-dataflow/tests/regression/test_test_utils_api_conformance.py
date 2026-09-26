"""Real SQLite coverage for the testing utility's migration and transaction APIs."""

import logging
import sqlite3
from contextlib import closing

import pytest

from dataflow.adapters.exceptions import InvalidIdentifierError
from dataflow.migrations.drop_confirmation import DropRefusedError
from dataflow.migrations.visual_migration_builder import (
    ColumnType,
    VisualMigrationBuilder,
)
from dataflow.testing.dataflow_test_utils import DataFlowTestUtils
from kailash.sdk_exceptions import RuntimeExecutionError


@pytest.fixture
def utility(tmp_path, caplog):
    helper = DataFlowTestUtils(f"sqlite:///{tmp_path}/utility.db")
    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING] == [
        "DataFlow: Test mode enabled (auto-detected pytest environment)",
        "DataFlow: Aggressive pool cleanup enabled for test mode",
    ]
    try:
        yield helper, tmp_path / "utility.db"
    finally:
        helper.close()


def test_fluent_operations_materialize_once_in_declaration_order(utility):
    helper, path = utility
    builder = VisualMigrationBuilder("ordered", dialect="sqlite")
    builder.create_table("original").add_column("id", ColumnType.INTEGER).primary_key()
    builder.rename_table("original", "renamed")
    builder.add_column("renamed", "label", ColumnType.TEXT).not_null().default_value(
        "O'Brien"
    )
    builder.add_index("renamed", "label_idx").on_columns("label")
    migration = builder.build()
    assert [op.operation_type.value for op in migration.operations] == [
        "create_table",
        "rename_table",
        "add_column",
        "add_index",
    ]
    assert builder.build().operations == migration.operations
    with helper.dataflow.transactions_sync.begin() as transaction:
        for operation in migration.operations:
            transaction.execute_raw(operation.sql_up)
        transaction.execute_raw('INSERT INTO "renamed" (id) VALUES (?)', [1])
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT id, label FROM renamed").fetchall() == [
            (1, "O'Brien")
        ]
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='label_idx'"
        ).fetchall() == [("label_idx",)]


def test_dictionary_migration_preserves_types_defaults_and_constraints(utility):
    helper, path = utility
    helper.run_migration(
        [
            {
                "type": "create_table",
                "name": "records",
                "columns": [
                    {"name": "id", "type": "serial", "primary_key": True},
                    {
                        "name": "label",
                        "type": "varchar(30)",
                        "nullable": False,
                        "default": "O'Brien",
                    },
                ],
            },
            {
                "type": "add_column",
                "table": "records",
                "column": {"name": "enabled", "type": "boolean", "default": False},
            },
        ]
    )
    with closing(sqlite3.connect(path)) as connection:
        columns = connection.execute("PRAGMA table_info(records)").fetchall()
        assert [(row[1], row[2], row[3], row[5]) for row in columns] == [
            ("id", "INTEGER", 1, 1),
            ("label", "VARCHAR(30)", 1, 0),
            ("enabled", "BOOLEAN", 0, 0),
        ]
        connection.execute("INSERT INTO records DEFAULT VALUES")
        assert connection.execute(
            "SELECT id, label, enabled FROM records"
        ).fetchall() == [(1, "O'Brien", 0)]
        with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
            connection.execute("INSERT INTO records(label) VALUES (NULL)")


def test_transactions_commit_read_their_writes_and_rollback_on_failure(utility, caplog):
    helper, path = utility

    @helper.dataflow.model
    class Csq14ConformanceItem:
        id: str
        name: str

    helper.dataflow.create_tables()

    def create(identifier, name):
        return {
            "node_type": "Csq14ConformanceItemCreateNode",
            "parameters": {"id": identifier, "name": name},
        }

    result = helper.execute_transaction(
        [
            create("a", "Alice"),
            {"node_type": "Csq14ConformanceItemListNode", "parameters": {}},
        ]
    )
    assert result["op_0"]["id"] == "a"
    assert [(row["id"], row["name"]) for row in result["op_1"]["records"]] == [
        ("a", "Alice")
    ]
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT id, name FROM csq14_conformance_items"
        ).fetchall() == [("a", "Alice")]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    caplog.clear()
    with pytest.raises(RuntimeExecutionError, match="UNIQUE constraint failed"):
        helper.execute_transaction([create("b", "Bob"), create("a", "Duplicate")])
    failures = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert failures[0] == "nodes.create_operation_failed"
    assert len(failures) == 3
    assert all(
        "op_1" in message and "UNIQUE constraint failed" in message
        for message in failures[1:]
    )
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT id, name FROM csq14_conformance_items"
        ).fetchall() == [("a", "Alice")]


@pytest.mark.parametrize(
    "dialect, quote", [("sqlite", '"'), ("postgresql", '"'), ("mysql", "`")]
)
def test_generated_identifiers_are_quoted_and_invalid_names_rejected(dialect, quote):
    builder = VisualMigrationBuilder("quote", dialect=dialect)
    builder.create_table("select").add_column("order", ColumnType.TEXT).default_value(
        "CURRENT_bad'); DROP TABLE x; --"
    )
    sql = builder.build().operations[0].sql_up
    assert f"CREATE TABLE {quote}select{quote}" in sql
    assert f"{quote}order{quote} TEXT" in sql
    assert "DEFAULT 'CURRENT_bad''); DROP TABLE x; --'" in sql
    invalid = VisualMigrationBuilder("invalid", dialect=dialect)
    invalid.add_column("bad; DROP TABLE x", "col", ColumnType.TEXT)
    with pytest.raises(InvalidIdentifierError, match="Invalid SQL identifier"):
        invalid.build()
    assert invalid.operations == []


def test_unknown_operation_and_destructive_migration_fail_before_execution(utility):
    helper, path = utility
    with pytest.raises(ValueError, match="Unsupported migration operation"):
        helper.run_migration([{"type": "unsupported"}])
    with pytest.raises(DropRefusedError, match="force_drop"):
        helper.run_migration([{"type": "drop_table", "name": "records"}])


def test_table_constraints_indexes_and_rename_have_real_sqlite_effect(utility):
    helper, path = utility
    builder = VisualMigrationBuilder("constraints", "sqlite")
    parent = builder.create_table("parents")
    parent.id()
    child = builder.create_table("children")
    child.id()
    child.integer("parent_id").references("parents.id")
    child.integer("age").check("age >= 0")
    child.string("label")
    child.check_constraint("age_ceiling", "age < 100")
    child.index("label").where("age > 0")
    child.foreign_key("parent_id", "parents.id", on_delete="CASCADE")
    builder.rename_column("children", "label", "name")
    migration = builder.build()
    assert len(migration.operations) == 4
    assert len(builder.build().operations) == 4
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for operation in migration.operations:
            connection.execute(operation.sql_up)
        connection.execute("INSERT INTO parents(id) VALUES (1)")
        connection.execute(
            "INSERT INTO children(parent_id,age,name) VALUES (1,10,'valid')"
        )
        for values, reason in [
            ((99, 10, "orphan"), "FOREIGN KEY"),
            ((1, -1, "negative"), "CHECK"),
            ((1, 100, "old"), "CHECK"),
        ]:
            with pytest.raises(sqlite3.IntegrityError, match=reason):
                connection.execute(
                    "INSERT INTO children(parent_id,age,name) VALUES (?,?,?)", values
                )
        assert connection.execute("SELECT name FROM children").fetchall() == [
            ("valid",)
        ]
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='idx_children_label'"
        ).fetchone()[0]
        assert "WHERE age > 0" in sql


@pytest.mark.parametrize(
    "option", ["table_comment", "column_comment", "modify", "include", "hash"]
)
def test_unsupported_sqlite_options_fail_atomically_and_can_retry(option):
    from dataflow.migrations.visual_migration_builder import IndexType

    builder = VisualMigrationBuilder("unsupported", "sqlite")
    table = builder.create_table("records")
    column = table.id()
    if option == "table_comment":
        table.comment("unsupported")
    elif option == "column_comment":
        column.comment("unsupported")
    elif option == "modify":
        builder.modify_column("records", "id", ColumnType.TEXT)
    else:
        index = builder.add_index("records", "idx").on_columns("id")
        if option == "include":
            index.include("other")
        else:
            index.using(IndexType.HASH)
    with pytest.raises(ValueError):
        builder.build()
    assert builder.operations == []
    with pytest.raises(ValueError):
        builder.build()
    assert builder.operations == []


@pytest.mark.parametrize("dialect", ["postgresql", "mysql"])
def test_non_sqlite_comment_and_modify_sql_generation(dialect):
    # SQL generation only: this test does not claim server execution parity.
    builder = VisualMigrationBuilder("comments", dialect)
    table = builder.create_table("records").comment("owner's table")
    table.string("label").comment("owner's label")
    builder.add_column("records", "extra", ColumnType.TEXT).comment("extra info")
    builder.modify_column("records", "extra", ColumnType.VARCHAR).length(
        50
    ).not_null().default_value("a'b").comment("changed")
    sql = "\n".join(operation.sql_up for operation in builder.build().operations)
    assert "owner''s table" in sql and "owner''s label" in sql
    assert "extra info" in sql and "changed" in sql
    assert "VARCHAR(50)" in sql and "NOT NULL" in sql and "'a''b'" in sql
    assert "CONCURRENTLY" not in sql


def test_migration_failure_rolls_back_prior_ddl(utility, caplog):
    helper, path = utility
    with pytest.raises(Exception, match="duplicate column"):
        helper.run_migration(
            [
                {
                    "type": "create_table",
                    "name": "atomic",
                    "columns": [{"name": "id", "type": "integer"}],
                },
                {
                    "type": "add_column",
                    "table": "atomic",
                    "column": {"name": "id", "type": "integer"},
                },
            ]
        )
    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING] == [
        "transaction.sync.rollback"
    ]
    with closing(sqlite3.connect(path)) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='atomic'"
            ).fetchall()
            == []
        )


def test_transaction_rejects_nodes_without_pinned_database_contract(utility):
    helper, _ = utility
    from kailash.nodes.transform.formatters import ChunkTextExtractorNode

    with pytest.raises(ValueError, match="DataFlow nodes for this database"):
        helper.execute_transaction(
            [
                {
                    "node_type": ChunkTextExtractorNode.__name__,
                    "parameters": {"chunks": []},
                }
            ]
        )


def test_close_releases_owned_database_and_borrowed_runtime(tmp_path, caplog):
    from kailash.runtime.local import LocalRuntime

    runtime = LocalRuntime()
    count = runtime.ref_count
    helper = DataFlowTestUtils(f"sqlite:///{tmp_path}/close.db", runtime=runtime)
    try:
        assert runtime.ref_count == count + 1
        helper.run_migration(
            [
                {
                    "type": "create_table",
                    "name": "records",
                    "columns": [{"name": "id", "type": "integer"}],
                }
            ]
        )
        manager = helper.dataflow.transactions_sync
        helper.close()
        helper.close()
        assert helper.dataflow._closed
        assert manager._closed
        assert helper.runtime is None
        assert runtime.ref_count == count
        from kailash.nodes.transform.formatters import ChunkTextExtractorNode
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node(
            ChunkTextExtractorNode.__name__,
            "text",
            {"chunks": [{"content": "still usable"}]},
        )
        with runtime:
            results, _ = runtime.execute(workflow.build())
        assert results["text"]["input_texts"] == ["still usable"]
    finally:
        helper.close()
        runtime.close()


@pytest.mark.parametrize("option", ["length", "decimal", "auto_increment"])
def test_incompatible_column_options_are_rejected(option):
    builder = VisualMigrationBuilder("invalid_option", "sqlite")
    column = builder.create_table("records").text("value")
    if option == "length":
        column.length(10)
    elif option == "decimal":
        column.decimal(10, 2)
    else:
        column.auto_increment()
    with pytest.raises(ValueError):
        builder.build()
    assert builder.operations == []


@pytest.mark.parametrize(
    "kind, expected",
    [
        (ColumnType.INTEGER, "SERIAL"),
        (ColumnType.BIGINT, "BIGSERIAL"),
        (ColumnType.SMALLINT, "SMALLSERIAL"),
    ],
)
def test_postgresql_integer_auto_increment_types(kind, expected):
    builder = VisualMigrationBuilder("serial", "postgresql")
    builder.create_table("records").add_column(
        "id", kind
    ).primary_key().auto_increment()
    assert (
        f'"id" {expected} NOT NULL PRIMARY KEY' in builder.build().operations[0].sql_up
    )


def test_dictionary_column_options_are_consumed_or_rejected(utility):
    helper, path = utility
    helper.run_migration(
        [
            {
                "type": "create_table",
                "name": "options",
                "columns": [
                    {
                        "name": "id",
                        "type": "integer",
                        "primary_key": True,
                        "auto_increment": True,
                    },
                    {
                        "name": "label",
                        "type": "text",
                        "unique": True,
                        "check": "length(label) > 1",
                    },
                ],
            }
        ]
    )
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT INTO options(label) VALUES ('valid')")
        assert connection.execute("SELECT id FROM options").fetchall() == [(1,)]
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            connection.execute("INSERT INTO options(label) VALUES ('valid')")
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            connection.execute("INSERT INTO options(label) VALUES ('x')")
    with pytest.raises(ValueError, match="Unsupported migration column option"):
        helper.run_migration(
            [
                {
                    "type": "add_column",
                    "table": "options",
                    "column": {"name": "new", "type": "text", "unknown": True},
                }
            ]
        )


def test_transaction_rejects_lookalike_node_without_generated_contract(utility):
    from kailash.nodes.base import Node, register_node

    helper, _ = utility

    @register_node()
    class Csq14LookalikeNode(Node):
        dataflow_instance = helper.dataflow
        model_name = "lookalike"

        def get_parameters(self):
            return {}

        def run(self, **kwargs):
            raise AssertionError("Lookalike node must not execute")

    with pytest.raises(ValueError, match="DataFlow nodes for this database"):
        helper.execute_transaction(
            [{"node_type": Csq14LookalikeNode.__name__, "parameters": {}}]
        )


@pytest.mark.asyncio
async def test_async_created_utility_transaction_context_commit_and_rollback(tmp_path):
    from kailash.runtime import AsyncLocalRuntime

    helper = DataFlowTestUtils(f"sqlite:///{tmp_path}/async-created.db")
    assert isinstance(helper.runtime, AsyncLocalRuntime)
    try:

        @helper.dataflow.model
        class Csq14AsyncConformanceItem:
            id: str
            name: str

        await helper.dataflow.initialize()

        def create(identifier):
            return {
                "node_type": "Csq14AsyncConformanceItemCreateNode",
                "parameters": {"id": identifier, "name": identifier},
            }

        result = helper.execute_transaction([create("a")])
        assert result["op_0"]["id"] == "a"
        with pytest.raises(Exception, match="UNIQUE constraint failed"):
            helper.execute_transaction([create("b"), create("a")])
        with closing(sqlite3.connect(tmp_path / "async-created.db")) as connection:
            assert connection.execute(
                "SELECT id FROM csq14_async_conformance_items"
            ).fetchall() == [("a",)]
    finally:
        await helper.runtime.cleanup()
        helper.close()


@pytest.mark.parametrize("unique", [False, True])
def test_sqlite_auto_increment_does_not_reuse_deleted_identifier(utility, unique):
    helper, path = utility
    helper.run_migration(
        [
            {
                "type": "create_table",
                "name": "monotonic_ids",
                "columns": [
                    {
                        "name": "id",
                        "type": "integer",
                        "primary_key": True,
                        "auto_increment": True,
                        "unique": unique,
                    }
                ],
            }
        ]
    )
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT INTO monotonic_ids DEFAULT VALUES")
        assert connection.execute("SELECT id FROM monotonic_ids").fetchall() == [(1,)]
        connection.execute("DELETE FROM monotonic_ids")
        connection.execute("INSERT INTO monotonic_ids DEFAULT VALUES")
        assert connection.execute("SELECT id FROM monotonic_ids").fetchall() == [(2,)]
        assert connection.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='monotonic_ids'"
        ).fetchone() == (2,)


@pytest.mark.parametrize(
    "option", ["nullable", "primary_key", "unique", "auto_increment"]
)
@pytest.mark.parametrize("invalid", ["false", 0, 1, None, [], {}])
def test_column_boolean_option_rejected_before_builder_mutation(option, invalid):
    calls = []

    def builder(name, kind):
        calls.append((name, kind))
        raise AssertionError("Invalid option reached operation construction")

    with pytest.raises(ValueError, match=f"{option!r} must be a boolean"):
        DataFlowTestUtils._migration_column(
            builder, {"name": "value", "type": "integer", option: invalid}
        )
    assert calls == []


@pytest.mark.parametrize(
    "option", ["nullable", "primary_key", "unique", "auto_increment"]
)
def test_invalid_boolean_migration_does_not_write_prior_ddl(utility, option):
    helper, path = utility
    with pytest.raises(ValueError, match=f"{option!r} must be a boolean"):
        helper.run_migration(
            [
                {
                    "type": "create_table",
                    "name": "must_not_exist",
                    "columns": [{"name": "id", "type": "integer"}],
                },
                {
                    "type": "add_column",
                    "table": "must_not_exist",
                    "column": {"name": "value", "type": "integer", option: "false"},
                },
            ]
        )
    with closing(sqlite3.connect(path)) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='must_not_exist'"
            ).fetchall()
            == []
        )


@pytest.mark.parametrize(
    "operation",
    [
        {"type": "create_table", "name": "other", "columns": []},
        {
            "type": "add_column",
            "table": "target",
            "column": {"name": "other", "type": "text"},
        },
        {"type": "drop_table", "name": "target", "force_drop": True},
        {
            "type": "drop_column",
            "table": "target",
            "column": "value",
            "force_drop": True,
        },
    ],
)
def test_unknown_operation_option_rejected_before_any_ddl(utility, operation):
    helper, path = utility
    with pytest.raises(ValueError, match="Unsupported migration operation option"):
        helper.run_migration(
            [
                {
                    "type": "create_table",
                    "name": "must_not_exist",
                    "columns": [{"name": "id", "type": "integer"}],
                },
                {**operation, "unexpected": True},
            ]
        )
    with closing(sqlite3.connect(path)) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='must_not_exist'"
            ).fetchall()
            == []
        )


@pytest.mark.parametrize(
    "method, arguments",
    [
        ("drop_table", ("target",)),
        ("drop_column", ("target", "value")),
        ("drop_index", ("target_idx",)),
    ],
)
@pytest.mark.parametrize("invalid", ["false", 1, None, []])
def test_visual_drop_requires_literal_true_before_appending(method, arguments, invalid):
    builder = VisualMigrationBuilder("refused", "sqlite")
    with pytest.raises(DropRefusedError, match="force_drop=True"):
        getattr(builder, method)(*arguments, force_drop=invalid)
    assert builder.operations == []


@pytest.mark.parametrize("operation", ["drop_table", "drop_column"])
@pytest.mark.parametrize("force_drop", ["false", 1, False])
def test_dictionary_drop_requires_explicit_true_and_preserves_table(
    utility, operation, force_drop
):
    helper, path = utility
    helper.run_migration(
        [
            {
                "type": "create_table",
                "name": "target",
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "value", "type": "text"},
                ],
            }
        ]
    )
    drop = {"type": operation, "force_drop": force_drop}
    drop.update(
        {"name": "target"}
        if operation == "drop_table"
        else {"table": "target", "column": "value"}
    )
    with pytest.raises(DropRefusedError, match="force_drop=True"):
        helper.run_migration([drop])
    with closing(sqlite3.connect(path)) as connection:
        assert [row[1] for row in connection.execute("PRAGMA table_info(target)")] == [
            "id",
            "value",
        ]
    helper.run_migration([{**drop, "force_drop": True}])
    with closing(sqlite3.connect(path)) as connection:
        assert [row[1] for row in connection.execute("PRAGMA table_info(target)")] == (
            [] if operation == "drop_table" else ["id"]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["false", 1, None, []])
async def test_not_null_rollback_rejects_non_boolean_confirmation_before_connection(
    invalid,
):
    from types import SimpleNamespace

    from dataflow.migrations.not_null_handler import NotNullColumnHandler

    # The actual public method must reject before it uses handler-owned resources.
    plan = SimpleNamespace(table_name="target", column=SimpleNamespace(name="value"))
    with pytest.raises(DropRefusedError, match="force_drop=True"):
        await NotNullColumnHandler.rollback_not_null_addition(
            None, plan, force_drop=invalid
        )
