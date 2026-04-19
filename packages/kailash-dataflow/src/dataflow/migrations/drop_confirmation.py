"""Shared DROP confirmation helpers for primitive-layer DDL APIs.

Per `rules/dataflow-identifier-safety.md` MUST Rule 4, every public migration
API that emits a single DROP TABLE / DROP COLUMN / DROP INDEX / DROP SCHEMA
statement MUST require an explicit ``force_drop=True`` flag on the calling
API. The default MUST be to refuse.

Dropped data is unrecoverable. The explicit flag is the last human gate
before destruction; without it, a typo or a mis-scoped operation takes the
production table with it.

This module is the **primitive layer**: it guards individual DROP-emitting
APIs (one method, one DDL DROP). Orchestrator-layer APIs that replay a
multi-statement destructive plan gate at their own layer via
``drop_confirmation_downgrade.DowngradeRefusedError`` + ``require_force_downgrade``
(see `rules/schema-migration.md` MUST Rule 7).

The two layers are distinct on purpose: the primitive flag guards one DDL
statement, the orchestrator flag guards one downgrade of an upgrade. The
flag does NOT flow from one layer to the other — each layer requires its
own deliberate acknowledgement.
"""

from __future__ import annotations


class DropRefusedError(RuntimeError):
    """Raised when a primitive-layer DROP API is called without ``force_drop=True``.

    Extends RuntimeError so callers catching ``RuntimeError`` (e.g. generic
    migration failure handlers) still see it, but the typed class enables
    precise handling in tests and for callers that explicitly anticipate the
    guard.

    This is the **primitive-layer** error. Orchestrator-layer APIs raise
    ``DowngradeRefusedError`` from ``drop_confirmation_downgrade`` — the two
    classes are deliberately distinct (one is NOT a subclass of the other)
    because they represent different layers of the destructive-operation
    discipline.
    """


def require_force_drop(method_label: str, force_drop: bool) -> None:
    """Refuse the call with a typed error unless ``force_drop`` is True.

    ``method_label`` is the caller's API name (e.g. ``"drop_table('users')"``
    or ``"drop_column('users', 'email')"``) — used verbatim in the
    error message so the caller sees exactly which action was refused.

    Does NOT echo raw user input that could be a stored XSS / log poisoning
    vector; the caller is responsible for sanitising ``method_label`` if it
    includes caller-supplied strings.
    """
    if not force_drop:
        raise DropRefusedError(
            f"{method_label} refused — pass force_drop=True to acknowledge "
            f"data loss is irreversible (see rules/dataflow-identifier-safety.md "
            f"MUST Rule 4)."
        )


__all__ = ["DropRefusedError", "require_force_drop"]
