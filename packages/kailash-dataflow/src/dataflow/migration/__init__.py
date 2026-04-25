"""DataFlow migration helpers.

This module exposes high-level migration builders that emit safely-quoted
DDL for advanced PostgreSQL features that DataFlow's auto-migration does
not generate by default:

* :class:`SecurityDefinerBuilder` — emits ``CREATE OR REPLACE FUNCTION ...
  SECURITY DEFINER`` helpers for pre-auth read paths (login lookup,
  password-reset lookup, invite-accept lookup) where the application has
  no authenticated session yet and a normal RLS-scoped policy would
  break the bootstrap flow. See
  :mod:`dataflow.migration.security_definer` for the rationale and
  invariants.

The module is intentionally lightweight — every builder produces a
``list[str]`` of SQL statements that the caller embeds in their own
migration tooling (Alembic, DataFlow auto-migrate post-hooks, raw
``execute_raw``, etc.). The builder does NOT execute SQL; it only
constructs it.
"""

from dataflow.migration.security_definer import (
    ALLOWED_PG_TYPES,
    FunctionParam,
    ReturnColumn,
    SecurityDefinerBuilder,
    SecurityDefinerBuilderError,
)

__all__ = [
    "ALLOWED_PG_TYPES",
    "FunctionParam",
    "ReturnColumn",
    "SecurityDefinerBuilder",
    "SecurityDefinerBuilderError",
]
