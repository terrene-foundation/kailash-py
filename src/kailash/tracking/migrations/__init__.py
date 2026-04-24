# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Numbered migration helpers for the ``_kml_*`` tracking schema.

The kailash-ml 0.x → 1.0 cut introduced a small family of schema
transitions (status-vocabulary unification, table-prefix unification,
cache-keyspace reshape, legacy-class deletion). Each transition lives
in a numbered file so the migration framework can discover, order, and
record them without reflection on filenames alone.

Layout::

    src/kailash/tracking/migrations/
        __init__.py                                 exports MigrationBase + registry
        _base.py                                    abstract base + MigrationResult
        _registry.py                                numbered-migration discovery
        0001_status_vocabulary_finished.py          Migration
        0002_kml_prefix_tenant_audit.py             Migration (lands in W4)
        ...

Each migration module exposes a single ``Migration`` class that
inherits :class:`MigrationBase`. The registry discovers them by sorting
file stems lexicographically — ``0001 < 0002 < ...`` — so zero-padding
is MANDATORY in filenames.

See ``specs/kailash-core-ml-integration.md §4``.
"""
from __future__ import annotations

from kailash.tracking.migrations._base import (
    STATUS_ENUM_1_0,
    MigrationBase,
    MigrationResult,
)
from kailash.tracking.migrations._registry import MigrationRegistry, get_registry

__all__ = [
    "MigrationBase",
    "MigrationResult",
    "STATUS_ENUM_1_0",
    "MigrationRegistry",
    "get_registry",
]
