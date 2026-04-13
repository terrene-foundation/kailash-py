"""Regression: #439 — express_sync.update/read/delete reject integer record IDs on PostgreSQL.

When a model has an integer primary key, passing str(record_id) to
express_sync.update/read/delete causes PostgreSQL to reject the query
because it cannot compare a TEXT argument to an INTEGER column.

The fix normalizes record IDs to match the model's primary key type,
handling Optional[int], Union[int, None], and other wrapped types.
"""

from typing import Optional, Union

import pytest

from dataflow.core.nodes import _coerce_record_id, _normalize_id_type


# --- _normalize_id_type unit tests ---


class TestNormalizeIdType:
    """Verify type annotation normalization strips Optional/Union wrappers."""

    def test_plain_int(self):
        assert _normalize_id_type(int) == int

    def test_plain_str(self):
        assert _normalize_id_type(str) == str

    def test_optional_int(self):
        assert _normalize_id_type(Optional[int]) == int

    def test_optional_str(self):
        assert _normalize_id_type(Optional[str]) == str

    def test_union_int_none(self):
        assert _normalize_id_type(Union[int, None]) == int

    def test_union_str_none(self):
        assert _normalize_id_type(Union[str, None]) == str

    def test_union_int_str(self):
        """Complex union — returns first non-None type."""
        result = _normalize_id_type(Union[int, str])
        assert result == int


# --- _coerce_record_id unit tests ---


class TestCoerceRecordId:
    """Verify record ID coercion matches model PK type."""

    def test_string_to_int_coercion(self):
        """Core bug: string ID passed for int PK model."""
        fields = {"id": {"type": int, "required": True}}
        assert _coerce_record_id(fields, "5") == 5
        assert isinstance(_coerce_record_id(fields, "5"), int)

    def test_int_preserved_for_int_pk(self):
        """Int ID stays int for int PK model."""
        fields = {"id": {"type": int, "required": True}}
        assert _coerce_record_id(fields, 5) == 5

    def test_string_preserved_for_str_pk(self):
        """String ID stays string for str PK model."""
        fields = {"id": {"type": str, "required": True}}
        assert _coerce_record_id(fields, "abc-123") == "abc-123"

    def test_int_to_string_coercion_for_str_pk(self):
        """Int ID converted to string for str PK model."""
        fields = {"id": {"type": str, "required": True}}
        assert _coerce_record_id(fields, 42) == "42"

    def test_optional_int_pk_string_to_int(self):
        """Core bug path: Optional[int] PK with string ID."""
        fields = {"id": {"type": Optional[int], "required": False}}
        assert _coerce_record_id(fields, "5") == 5
        assert isinstance(_coerce_record_id(fields, "5"), int)

    def test_union_int_none_pk_string_to_int(self):
        """Union[int, None] PK with string ID."""
        fields = {"id": {"type": Union[int, None], "required": False}}
        assert _coerce_record_id(fields, "5") == 5

    def test_no_type_info_falls_back_to_int(self):
        """No type info — backward compatibility tries int conversion."""
        fields = {"id": {"required": True}}
        assert _coerce_record_id(fields, "5") == 5

    def test_no_type_info_preserves_non_numeric_string(self):
        """No type info — non-numeric string preserved as-is."""
        fields = {"id": {"required": True}}
        assert _coerce_record_id(fields, "abc-123") == "abc-123"

    def test_none_passthrough(self):
        """None ID returns None."""
        fields = {"id": {"type": int, "required": True}}
        assert _coerce_record_id(fields, None) is None

    def test_no_id_field_in_model(self):
        """Model without id field — backward compat tries int."""
        fields = {"name": {"type": str, "required": True}}
        assert _coerce_record_id(fields, "5") == 5

    def test_invalid_string_for_int_pk_preserved(self):
        """Non-numeric string for int PK — preserve as-is, let DB reject."""
        fields = {"id": {"type": int, "required": True}}
        assert _coerce_record_id(fields, "not-a-number") == "not-a-number"


@pytest.mark.regression
def test_issue_439_read_with_string_id_for_int_pk(tmp_path):
    """Read with string ID for int PK model — was broken on PostgreSQL."""
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    from dataflow import DataFlow

    db_file = str(tmp_path / "test_439_read.db")
    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)

    Model = type(
        "Item439R",
        (),
        {
            "__annotations__": {"id": int, "name": str},
            "__tablename__": "items_439r",
            "name": "",
        },
    )
    db.model(Model)

    wf = WorkflowBuilder()
    wf.add_node(
        "SQLDatabaseNode",
        "create_table",
        {
            "query": "CREATE TABLE IF NOT EXISTS items_439r (id INTEGER PRIMARY KEY, name TEXT DEFAULT '')",
            "connection_string": f"sqlite:///{db_file}",
        },
    )
    with LocalRuntime() as runtime:
        runtime.execute(wf.build())

    db.express_sync.create("Item439R", {"id": 42, "name": "Alice"})

    # Read with int — should work
    item = db.express_sync.read("Item439R", 42)
    assert item is not None
    assert item["name"] == "Alice"

    # Read with string — was broken on PostgreSQL before fix
    item2 = db.express_sync.read("Item439R", "42")
    assert item2 is not None
    assert item2["name"] == "Alice"


@pytest.mark.regression
def test_issue_439_update_with_string_id_for_int_pk(tmp_path):
    """Update with string ID for int PK model — was broken on PostgreSQL."""
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    from dataflow import DataFlow

    db_file = str(tmp_path / "test_439_update.db")
    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)

    Model = type(
        "Item439U",
        (),
        {
            "__annotations__": {"id": int, "name": str},
            "__tablename__": "items_439u",
            "name": "",
        },
    )
    db.model(Model)

    wf = WorkflowBuilder()
    wf.add_node(
        "SQLDatabaseNode",
        "create_table",
        {
            "query": "CREATE TABLE IF NOT EXISTS items_439u (id INTEGER PRIMARY KEY, name TEXT DEFAULT '')",
            "connection_string": f"sqlite:///{db_file}",
        },
    )
    with LocalRuntime() as runtime:
        runtime.execute(wf.build())

    db.express_sync.create("Item439U", {"id": 7, "name": "Alice"})

    # Update with string ID — was broken on PostgreSQL before fix
    db.express_sync.update("Item439U", "7", {"name": "Bob"})

    # Verify read-back with int ID
    item = db.express_sync.read("Item439U", 7)
    assert item is not None, "Record missing after update"
    assert item["name"] == "Bob", f"Update not persisted: {item}"


@pytest.mark.regression
def test_issue_439_delete_with_string_id_for_int_pk(tmp_path):
    """Delete with string ID for int PK model — was broken on PostgreSQL."""
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    from dataflow import DataFlow

    db_file = str(tmp_path / "test_439_delete.db")
    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)

    Model = type(
        "Item439D",
        (),
        {
            "__annotations__": {"id": int, "name": str},
            "__tablename__": "items_439d",
            "name": "",
        },
    )
    db.model(Model)

    wf = WorkflowBuilder()
    wf.add_node(
        "SQLDatabaseNode",
        "create_table",
        {
            "query": "CREATE TABLE IF NOT EXISTS items_439d (id INTEGER PRIMARY KEY, name TEXT DEFAULT '')",
            "connection_string": f"sqlite:///{db_file}",
        },
    )
    with LocalRuntime() as runtime:
        runtime.execute(wf.build())

    db.express_sync.create("Item439D", {"id": 99, "name": "Alice"})

    # Delete with string ID — was broken on PostgreSQL before fix
    deleted = db.express_sync.delete("Item439D", "99")
    assert deleted is True

    # Verify deleted
    item = db.express_sync.read("Item439D", 99)
    assert item is None


@pytest.mark.regression
def test_issue_439_int_id_still_works(tmp_path):
    """Int IDs still work after the fix (no regression on the working path)."""
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    from dataflow import DataFlow

    db_file = str(tmp_path / "test_439_int.db")
    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)

    Model = type(
        "Item439I",
        (),
        {
            "__annotations__": {"id": int, "name": str},
            "__tablename__": "items_439i",
            "name": "",
        },
    )
    db.model(Model)

    wf = WorkflowBuilder()
    wf.add_node(
        "SQLDatabaseNode",
        "create_table",
        {
            "query": "CREATE TABLE IF NOT EXISTS items_439i (id INTEGER PRIMARY KEY, name TEXT DEFAULT '')",
            "connection_string": f"sqlite:///{db_file}",
        },
    )
    with LocalRuntime() as runtime:
        runtime.execute(wf.build())

    db.express_sync.create("Item439I", {"id": 1, "name": "Alice"})

    item = db.express_sync.read("Item439I", 1)
    assert item is not None
    assert item["name"] == "Alice"

    db.express_sync.update("Item439I", 1, {"name": "Bob"})
    item2 = db.express_sync.read("Item439I", 1)
    assert item2 is not None
    assert item2["name"] == "Bob"

    deleted = db.express_sync.delete("Item439I", 1)
    assert deleted is True
