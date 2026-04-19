"""Shared DROP confirmation helpers for migration builders.

Per `rules/dataflow-identifier-safety.md` MUST Rule 4, every public migration
API that emits DROP TABLE / DROP COLUMN / DROP INDEX / DROP SCHEMA SQL MUST
require an explicit ``force_drop=True`` flag on the calling API. The default
MUST be to refuse.

Dropped data is unrecoverable. The explicit flag is the last human gate
before destruction; without it, a typo or a mis-scoped operation takes the
production table with it.

Migration builders that expose destructive entry points should import
``DropRefusedError`` + ``require_force_drop`` from this module so the
message and error type are consistent across the whole migrations package.

Related: ``schema-migration.md`` MUST Rule 7 (``force_downgrade`` on the
migration-orchestrator layer). This module is the primitive-layer sibling:
it guards individual DROP-emitting APIs; orchestrators that replay stored
``down_sql`` gate at their own layer.
"""

from __future__ import annotations


class DropRefusedError(RuntimeError):
    """Raised when a destructive DROP API is called without ``force_drop=True``.

    Extends RuntimeError so callers catching ``RuntimeError`` (e.g. generic
    migration failure handlers) still see it, but the typed class enables
    precise handling in tests and for callers that explicitly anticipate the
    guard.
    """


def require_force_drop(method_label: str, force_drop: bool) -> None:
    """Refuse the call with a typed error unless ``force_drop`` is True.

    ``method_label`` is the caller's API name (e.g. ``"drop_table('users')"``
    or ``"execute_safe_removal(plan=users.email)"``) — used verbatim in the
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
