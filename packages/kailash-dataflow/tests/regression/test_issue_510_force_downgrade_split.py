"""Regression: #510 — primitive force_drop vs orchestrator force_downgrade split.

The primitive layer (`rules/dataflow-identifier-safety.md` MUST Rule 4) guards
individual DDL DROP statements with ``force_drop=True`` + ``DropRefusedError``.
The orchestrator layer (`rules/schema-migration.md` MUST Rule 7) guards
multi-statement destructive downgrades with ``force_downgrade=True`` +
``DowngradeRefusedError``.

The two layers are deliberately distinct:

- Two separate exception classes (neither is a subclass of the other).
- Two separate helper functions (`require_force_drop`,
  `require_force_downgrade`).
- Two separate module homes (`drop_confirmation.py`,
  `drop_confirmation_downgrade.py`).

A caller that wants to catch only the primitive-layer failure MUST be able to
do so without accidentally catching the orchestrator-layer failure, and vice
versa. If a future refactor ever makes one a subclass of the other, this
regression test breaks at import time.
"""

from __future__ import annotations

import pytest

from dataflow.migrations import (
    DowngradeRefusedError,
    DropRefusedError,
    require_force_downgrade,
    require_force_drop,
)


@pytest.mark.regression
def test_issue_510_drop_refused_error_raised_from_require_force_drop():
    """Primitive-layer helper raises DropRefusedError when force_drop is False."""
    with pytest.raises(DropRefusedError) as excinfo:
        require_force_drop("drop_table('users')", force_drop=False)
    assert "drop_table('users')" in str(excinfo.value)
    assert "force_drop=True" in str(excinfo.value)


@pytest.mark.regression
def test_issue_510_downgrade_refused_error_raised_from_require_force_downgrade():
    """Orchestrator-layer helper raises DowngradeRefusedError when force_downgrade is False."""
    with pytest.raises(DowngradeRefusedError) as excinfo:
        require_force_downgrade("apply_downgrade('0042')", force_downgrade=False)
    assert "apply_downgrade('0042')" in str(excinfo.value)
    assert "force_downgrade=True" in str(excinfo.value)


@pytest.mark.regression
def test_issue_510_require_force_drop_silent_when_true():
    """No error when the primitive flag is explicitly True."""
    require_force_drop("drop_table('users')", force_drop=True)


@pytest.mark.regression
def test_issue_510_require_force_downgrade_silent_when_true():
    """No error when the orchestrator flag is explicitly True."""
    require_force_downgrade("apply_downgrade('0042')", force_downgrade=True)


@pytest.mark.regression
def test_issue_510_drop_and_downgrade_errors_are_distinct_classes():
    """DropRefusedError and DowngradeRefusedError are NOT in a subclass relation.

    Each represents a different layer of the destructive-operation discipline;
    a caller catching only primitive failures must not accidentally swallow
    orchestrator failures (and vice versa). If a future refactor makes one a
    subclass of the other, this assertion fires immediately.
    """
    assert DropRefusedError is not DowngradeRefusedError
    assert not issubclass(DropRefusedError, DowngradeRefusedError)
    assert not issubclass(DowngradeRefusedError, DropRefusedError)


@pytest.mark.regression
def test_issue_510_drop_refused_error_not_caught_by_downgrade_except():
    """A caller catching DowngradeRefusedError MUST NOT catch DropRefusedError."""
    with pytest.raises(DropRefusedError):
        try:
            require_force_drop("drop_table('users')", force_drop=False)
        except DowngradeRefusedError:
            pytest.fail(
                "DropRefusedError should not be caught as DowngradeRefusedError"
            )


@pytest.mark.regression
def test_issue_510_downgrade_refused_error_not_caught_by_drop_except():
    """A caller catching DropRefusedError MUST NOT catch DowngradeRefusedError."""
    with pytest.raises(DowngradeRefusedError):
        try:
            require_force_downgrade("apply_downgrade('0042')", force_downgrade=False)
        except DropRefusedError:
            pytest.fail(
                "DowngradeRefusedError should not be caught as DropRefusedError"
            )


@pytest.mark.regression
def test_issue_510_both_errors_extend_runtimeerror():
    """Both retain RuntimeError ancestry so generic migration handlers still see them."""
    assert issubclass(DropRefusedError, RuntimeError)
    assert issubclass(DowngradeRefusedError, RuntimeError)


@pytest.mark.regression
def test_issue_510_auto_migrate_refuses_without_force_downgrade():
    """AutoMigrationSystem.auto_migrate on a destructive plan raises DowngradeRefusedError.

    This is the orchestrator-layer behavioral regression: the renamed kwarg
    MUST be ``force_downgrade`` (not ``force_drop``) and the refusal MUST be
    ``DowngradeRefusedError`` (not ``DropRefusedError``). Verified via the
    helper contract — the method signature is covered by import-time
    inspection below so the test does not need a real database.
    """
    import inspect

    from dataflow.migrations.auto_migration_system import AutoMigrationSystem

    sig = inspect.signature(AutoMigrationSystem.auto_migrate)
    params = sig.parameters
    assert "force_downgrade" in params, (
        "AutoMigrationSystem.auto_migrate must accept force_downgrade kwarg "
        "(orchestrator layer per rules/schema-migration.md MUST Rule 7)"
    )
    assert "force_drop" not in params, (
        "AutoMigrationSystem.auto_migrate must NOT accept force_drop kwarg — "
        "that is the primitive-layer flag; the orchestrator layer uses "
        "force_downgrade"
    )


@pytest.mark.regression
def test_issue_510_execute_rollback_uses_force_downgrade():
    """RollbackManager.execute_rollback uses force_downgrade (orchestrator layer)."""
    import inspect

    from dataflow.migrations.application_safe_rename_strategy import (
        RollbackManager,
    )

    sig = inspect.signature(RollbackManager.execute_rollback)
    params = sig.parameters
    assert "force_downgrade" in params
    assert "force_drop" not in params


@pytest.mark.regression
def test_issue_510_execute_safe_removal_uses_force_downgrade():
    """ColumnRemovalManager.execute_safe_removal uses force_downgrade (orchestrator layer)."""
    import inspect

    from dataflow.migrations.column_removal_manager import (
        ColumnRemovalManager,
    )

    sig = inspect.signature(ColumnRemovalManager.execute_safe_removal)
    params = sig.parameters
    assert "force_downgrade" in params
    assert "force_drop" not in params


@pytest.mark.regression
def test_issue_510_visual_migration_builder_drops_keep_force_drop():
    """VisualMigrationBuilder.drop_* methods KEEP force_drop (primitive layer).

    Each drop_table / drop_column / drop_index appends one DDL DROP to the
    plan — this is the primitive layer, so force_drop is correct.
    """
    import inspect

    from dataflow.migrations.visual_migration_builder import (
        VisualMigrationBuilder,
    )

    for method_name in ("drop_table", "drop_column", "drop_index"):
        sig = inspect.signature(getattr(VisualMigrationBuilder, method_name))
        params = sig.parameters
        assert "force_drop" in params, (
            f"VisualMigrationBuilder.{method_name} must keep force_drop "
            f"(primitive layer per rules/dataflow-identifier-safety.md "
            f"MUST Rule 4)"
        )
        assert "force_downgrade" not in params, (
            f"VisualMigrationBuilder.{method_name} must NOT accept "
            f"force_downgrade — that is the orchestrator-layer flag; "
            f"each drop_* method appends one DDL DROP and is primitive"
        )


@pytest.mark.regression
def test_issue_510_rollback_not_null_addition_keeps_force_drop():
    """NotNullHandler.rollback_not_null_addition KEEPS force_drop (primitive layer).

    The method runs one DDL DROP COLUMN — primitive layer, not orchestrator.
    """
    import inspect

    from dataflow.migrations.not_null_handler import NotNullColumnHandler

    sig = inspect.signature(NotNullColumnHandler.rollback_not_null_addition)
    params = sig.parameters
    assert "force_drop" in params
    assert "force_downgrade" not in params
