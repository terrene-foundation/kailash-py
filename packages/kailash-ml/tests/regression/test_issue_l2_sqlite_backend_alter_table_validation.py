# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: L2 — sqlite_backend.py ALTER TABLE hardcoded list MUST validate.

Origin: 2026-04-20 late-session audit finding L2 —
``packages/kailash-ml/src/kailash_ml/tracking/sqlite_backend.py`` had
a hardcoded ``_COLUMNS_ADDED_IN_0_14`` list whose names were
interpolated into an ``ALTER TABLE experiment_runs ADD COLUMN``
f-string without routing through ``_validate_identifier``. Per
``rules/dataflow-identifier-safety.md`` MUST Rule 5, hardcoded
identifier lists MUST still validate — "the list is hardcoded" is
BLOCKED as a rationalization because a future refactor that makes
the list dynamic silently re-opens the injection vector.

Behavioral regression tests per ``rules/testing.md`` § "MUST:
Behavioral Regression Tests Over Source-Grep": we validate the
actual ``_COLUMNS_ADDED_IN_0_14`` entries against the dialect's
allowlist AND we confirm that a poisoned entry (if the list were
ever made dynamic) would be rejected by the same validator the
production path now uses.
"""
from __future__ import annotations

import pytest

from kailash.db.dialect import IdentifierError, _validate_identifier


@pytest.mark.regression
def test_l2_columns_added_in_0_14_all_pass_identifier_validator() -> None:
    """Every shipped migration column name MUST pass ``_validate_identifier``.

    This test exercises the exact validator call path that the
    production ALTER TABLE loop now routes through. If any current
    entry fails the allowlist, the upgrade would raise at runtime;
    the test locks the invariant at collection time.
    """
    from kailash_ml.tracking import sqlite_backend

    assert hasattr(sqlite_backend, "_COLUMNS_ADDED_IN_0_14"), (
        "sqlite_backend._COLUMNS_ADDED_IN_0_14 disappeared — if the "
        "migration list was renamed, update this test; if it was "
        "removed, the ALTER TABLE path is dead code."
    )
    for name, _sql_type in sqlite_backend._COLUMNS_ADDED_IN_0_14:
        # If this raises, the production ALTER TABLE loop would
        # also raise — the defense-in-depth validator would block
        # the migration, and ops would see the typed error.
        _validate_identifier(name)


@pytest.mark.regression
def test_l2_validator_rejects_injection_payloads_that_would_reach_alter_table() -> None:
    """If the list were ever made dynamic, injection payloads MUST be rejected.

    Rule 5's defense-in-depth posture: today's hardcoded list is
    tomorrow's dynamic list. The production loop now calls
    ``_validate_identifier(name)`` before the ``f"ALTER TABLE
    ... ADD COLUMN {name} ..."`` interpolation, so any dynamic
    refactor is guarded by the same validator this test asserts.
    """
    injection_payloads = [
        'users"; DROP TABLE experiment_runs; --',
        "name WITH DATA",
        "123_starts_with_digit",
        'column"; DROP TABLE kml_model_versions; --',
        "tab\tcontrol",
        "null\x00byte",
        '" OR 1=1 --',
        "space in name",
        "",  # empty string
    ]
    for payload in injection_payloads:
        with pytest.raises((IdentifierError, ValueError, TypeError)):
            _validate_identifier(payload)


@pytest.mark.regression
def test_l2_sqlite_backend_imports_validator() -> None:
    """Structural invariant: ``sqlite_backend`` MUST import ``_validate_identifier``.

    If a future refactor removes the import, the loop body will
    NameError at migration time. This invariant catches that at
    collection time instead — the import IS the contract that
    defense-in-depth validation is wired, not an accident.
    """
    import ast
    from pathlib import Path

    # Path relative to this test file (robust against cwd / worktree / main).
    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "kailash_ml"
        / "tracking"
        / "sqlite_backend.py"
    )
    assert src.exists(), f"sqlite_backend.py moved — update this test. Expected: {src}"

    tree = ast.parse(src.read_text())
    imports_validate = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "kailash.db.dialect":
                for alias in node.names:
                    if alias.name == "_validate_identifier":
                        imports_validate = True
                        break
    assert imports_validate, (
        "sqlite_backend.py no longer imports _validate_identifier from "
        "kailash.db.dialect — the defense-in-depth validator call at "
        "the ALTER TABLE loop is unreachable. Restore the import or "
        "file a cross-SDK issue if the contract changed."
    )
