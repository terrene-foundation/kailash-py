"""Shared destructive-downgrade confirmation helpers for orchestrator-layer APIs.

Per `rules/schema-migration.md` MUST Rule 7, every migration-orchestrator
API that runs destructive DDL or irreversible data transforms as part of a
multi-statement migration (downgrade, rollback, destructive auto-migrate
plan) MUST require an explicit ``force_downgrade=True`` flag on the calling
API. The default MUST be to refuse.

Dropped data is unrecoverable, and the downgrade surface is strictly wider
than the individual DROP primitive — a single ``apply_downgrade`` /
``execute_rollback`` / destructive ``auto_migrate`` call can execute dozens
of destructive statements in one transaction before the operator notices.
Requiring the flag at every layer that can touch destructive DDL is the only
structural defense against "I meant to roll back the schema, not destroy
the data" incidents.

This module is the **orchestrator layer**. Its sibling ``drop_confirmation``
is the **primitive layer** — the two are distinct on purpose. The primitive
flag (``force_drop``) guards one DDL statement; the orchestrator flag
(``force_downgrade``) guards one downgrade of an upgrade. The flag does NOT
flow from one layer to the other.

The two error classes (``DropRefusedError`` and ``DowngradeRefusedError``)
are deliberately **NOT** in a subclass relationship — each represents a
different layer of the destructive-operation discipline, and callers that
want to handle only one layer must be able to catch it precisely.
"""

from __future__ import annotations


class DowngradeRefusedError(RuntimeError):
    """Raised when an orchestrator-layer downgrade API is called without
    ``force_downgrade=True``.

    Extends RuntimeError so callers catching ``RuntimeError`` (e.g. generic
    migration failure handlers) still see it, but the typed class enables
    precise handling in tests and for callers that explicitly anticipate the
    guard.

    This is the **orchestrator-layer** error. Primitive-layer APIs raise
    ``DropRefusedError`` from ``drop_confirmation`` — the two classes are
    deliberately distinct (one is NOT a subclass of the other) because they
    represent different layers of the destructive-operation discipline.
    """


def require_force_downgrade(method_label: str, force_downgrade: bool) -> None:
    """Refuse the call with a typed error unless ``force_downgrade`` is True.

    ``method_label`` is the caller's API name (e.g.
    ``"apply_downgrade('0042')"`` or
    ``"auto_migrate(destructive ops: DROP_TABLE, DROP_COLUMN)"``) — used
    verbatim in the error message so the caller sees exactly which action
    was refused.

    Does NOT echo raw user input that could be a stored XSS / log poisoning
    vector; the caller is responsible for sanitising ``method_label`` if it
    includes caller-supplied strings.
    """
    if not force_downgrade:
        raise DowngradeRefusedError(
            f"{method_label} refused — pass force_downgrade=True to acknowledge "
            f"destructive migration data loss is irreversible "
            f"(see rules/schema-migration.md MUST Rule 7)."
        )


__all__ = ["DowngradeRefusedError", "require_force_downgrade"]
