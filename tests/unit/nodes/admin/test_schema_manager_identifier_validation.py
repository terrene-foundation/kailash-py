"""Spy-based regression tests for schema_manager.py hardcoded-list validation.

Issue #499 (Finding 7): ``schema_manager.py`` already has a hardcoded
identifier list with ``_validate_identifier()`` calls per
``rules/dataflow-identifier-safety.md`` MUST Rule 5. The validation code
exists; what was missing was a regression test that *proves the
``_validate_identifier`` call fires* for every element of the hardcoded list.

Without this test, a future refactor that "simplifies" ``_drop_existing_schema``
or ``_get_table_row_counts`` by removing the defense-in-depth validator call
would pass CI silently. The spy pattern from
``tests/regression/test_issue_446_dlq_identifier_validation.py`` is the
load-bearing guard: it patches ``_validate_identifier`` with a spy, invokes
the hardcoded-list path, and asserts every element was passed through.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


EXPECTED_DROP_TABLES = [
    "admin_audit_log",
    "user_sessions",
    "resource_attributes",
    "user_attributes",
    "permission_cache",
    "permissions",
    "user_role_assignments",
    "roles",
    "users",
    "admin_schema_version",
]


def _make_schema_manager() -> Any:
    """Build a SchemaManager that does NOT touch a real database.

    SchemaManager's ``execute()`` method requires real workflow infrastructure;
    for this spy test we only need the helper methods to run, so we bypass
    ``execute()`` entirely by instantiating the class and overriding
    ``db_node`` with a MagicMock.
    """
    from kailash.nodes.admin.schema_manager import AdminSchemaManager

    mgr = AdminSchemaManager.__new__(AdminSchemaManager)
    # Minimal attributes the helper methods touch.
    mgr.db_node = MagicMock()
    mgr.logger = MagicMock()
    return mgr


@pytest.mark.regression
def test_drop_existing_schema_validates_every_hardcoded_identifier() -> None:
    """Issue #499 Finding 7: ``_drop_existing_schema`` MUST route every element
    of its hardcoded table list through ``_validate_identifier()``.

    This is the load-bearing test: if a refactor drops the ``_validate_identifier``
    call from the for-loop, the spy captures zero calls and this test fails.
    Per rules/dataflow-identifier-safety.md MUST Rule 5 + BLOCKED rationalization
    "hardcoded list so it's safe".
    """
    from kailash.db import dialect as dialect_module

    # Capture the real validator so the spy can defer to it. Re-importing
    # inside the spy would recurse.
    real_validator = dialect_module._validate_identifier

    seen_identifiers: list[str] = []

    def spy(name: str, *, max_length: int = 128) -> None:
        seen_identifiers.append(name)
        real_validator(name, max_length=max_length)

    with patch.object(dialect_module, "_validate_identifier", side_effect=spy):
        mgr = _make_schema_manager()
        mgr._drop_existing_schema(force_drop=True)

    # Every hardcoded table name MUST have been passed through the validator.
    expected = set(EXPECTED_DROP_TABLES)
    seen = set(seen_identifiers)
    missing = expected - seen
    assert not missing, (
        f"_drop_existing_schema did not validate: {missing}. "
        f"Hardcoded DDL identifiers MUST route through _validate_identifier "
        f"per dataflow-identifier-safety.md MUST Rule 5."
    )
    # Spy count MUST equal list length — proves no early-exit skip.
    assert len(seen_identifiers) == len(EXPECTED_DROP_TABLES), (
        f"Expected {len(EXPECTED_DROP_TABLES)} validator calls, "
        f"got {len(seen_identifiers)}: {seen_identifiers}"
    )


@pytest.mark.regression
def test_drop_existing_schema_refuses_without_force_drop() -> None:
    """Issue #499: ``_drop_existing_schema`` MUST raise when ``force_drop``
    is False. The force_drop gate is itself a rules/dataflow-identifier-safety.md
    MUST Rule 4 requirement; a regression that defaults to True would bypass
    the guard entirely.
    """
    mgr = _make_schema_manager()
    with pytest.raises(ValueError, match="force_drop=True"):
        mgr._drop_existing_schema()  # force_drop defaults to False


@pytest.mark.regression
def test_get_table_row_counts_validates_every_hardcoded_identifier() -> None:
    """Issue #499 Finding 7: the sibling ``_get_table_row_counts`` helper
    also has a hardcoded table list per commit 803e10e0 — it MUST route every
    element through the validator for the same reason.
    """
    from kailash.db import dialect as dialect_module

    real_validator = dialect_module._validate_identifier
    seen_identifiers: list[str] = []

    def spy(name: str, *, max_length: int = 128) -> None:
        seen_identifiers.append(name)
        real_validator(name, max_length=max_length)

    mgr = _make_schema_manager()
    # db_node.execute returns a dict-with-data shape; each call returns 0 count.
    mgr.db_node.execute.return_value = {"data": [{"count": 0}]}

    with patch.object(dialect_module, "_validate_identifier", side_effect=spy):
        # _get_table_row_counts is a method that loops the same list.
        mgr._get_table_row_counts()

    # The same hardcoded table set is expected. Even if this helper drifts
    # to a subset, EVERY call site MUST validate.
    assert seen_identifiers, (
        "_get_table_row_counts emitted zero _validate_identifier calls — "
        "hardcoded-list validation was removed, violating "
        "dataflow-identifier-safety.md MUST Rule 5."
    )
    # Each seen identifier MUST be in the expected admin-schema set, not a
    # surprise table name (would indicate the helper picked up user input).
    unexpected = set(seen_identifiers) - set(EXPECTED_DROP_TABLES)
    assert not unexpected, (
        f"_get_table_row_counts validated unexpected identifiers "
        f"{unexpected} — possible source drift."
    )
