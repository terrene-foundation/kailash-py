"""Regression test: @db.model MUST handle parameterized generics on Python 3.11+.

Issue #768 — DataFlow's ``FieldTypeProcessor._resolve_type`` returned
parameterized builtin generics (``list[str]``, ``dict[str, Any]``,
``typing.List[str]``, PEP 604 ``list[str] | None``) verbatim. The next
``isinstance(value, expected_type)`` call raised
``TypeError: isinstance() argument 2 cannot be a parameterized generic``
on Python 3.11+, crashing every CRUD operation against the model.

The fix in ``packages/kailash-dataflow/src/dataflow/core/type_processor.py``
strips parameterized generics down to their origin (``list[str] -> list``,
``dict[str, Any] -> dict``) and recurses through ``Optional`` / PEP 604
unions so ``Optional[list[str]]`` resolves to ``list``.

This test exercises:

1. The structural invariant — ``_resolve_type`` strips parameterized
   generics for every shape called out in the issue acceptance.
2. The end-to-end CRUD path against SQLite — create/list/update on a
   ``@db.model`` with ``list[str]`` and ``dict[str, Any]`` fields no
   longer crashes.

See:
- packages/kailash-dataflow/src/dataflow/core/type_processor.py
- packages/kailash-dataflow/src/dataflow/core/nodes.py::_normalize_type_annotation
  (parallel implementation; consolidation tracked separately).
- rules/zero-tolerance.md Rule 4 (no workarounds for SDK bugs)
"""

from __future__ import annotations

import os
import tempfile
import typing

import pytest

from dataflow import DataFlow
from dataflow.core.type_processor import TypeAwareFieldProcessor

pytestmark = [pytest.mark.regression]


@pytest.fixture
def sqlite_url():
    """Per-test SQLite URL on disk."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="dpi_768_")
    os.close(fd)
    yield f"sqlite:///{path}"
    try:
        os.unlink(path)
    except OSError:
        pass


# -- Structural invariants --------------------------------------------------


def _processor_for(field_type) -> TypeAwareFieldProcessor:
    return TypeAwareFieldProcessor(
        {"f": {"type": field_type, "required": False}}, model_name="Issue768"
    )


def test_resolve_type_strips_pep585_list():
    proc = _processor_for(list[str])
    assert proc._resolved_types["f"] is list


def test_resolve_type_strips_pep585_dict():
    proc = _processor_for(dict[str, typing.Any])
    assert proc._resolved_types["f"] is dict


def test_resolve_type_strips_pep585_tuple():
    proc = _processor_for(tuple[int, ...])
    assert proc._resolved_types["f"] is tuple


def test_resolve_type_strips_typing_list():
    proc = _processor_for(typing.List[str])
    assert proc._resolved_types["f"] is list


def test_resolve_type_strips_typing_dict():
    proc = _processor_for(typing.Dict[str, typing.Any])
    assert proc._resolved_types["f"] is dict


def test_resolve_type_optional_parameterized_typing_union():
    proc = _processor_for(typing.Optional[list[str]])
    assert proc._resolved_types["f"] is list


def test_resolve_type_optional_parameterized_pep604():
    """PEP 604 ``list[str] | None`` — get_origin returns types.UnionType, not Union."""
    proc = _processor_for(list[str] | None)
    assert proc._resolved_types["f"] is list


def test_resolve_type_pep604_dict_optional():
    proc = _processor_for(dict[str, typing.Any] | None)
    assert proc._resolved_types["f"] is dict


def test_resolve_type_plain_types_unchanged():
    """Regression guard: non-generic types still resolve to themselves."""
    assert _processor_for(str)._resolved_types["f"] is str
    assert _processor_for(int)._resolved_types["f"] is int
    assert _processor_for(typing.Optional[int])._resolved_types["f"] is int


def test_validate_field_isinstance_works_after_strip():
    """The bug surface: isinstance(value, resolved_type) MUST not raise."""
    proc = _processor_for(list[str])
    out = proc.validate_field("f", ["a", "b"])
    assert out == ["a", "b"]


def test_validate_field_isinstance_works_for_pep604_union():
    proc = _processor_for(list[str] | None)
    assert proc.validate_field("f", ["a", "b"]) == ["a", "b"]
    assert proc.validate_field("f", None) is None


# -- End-to-end CRUD against SQLite ----------------------------------------


@pytest.mark.asyncio
async def test_db_model_with_pep585_list_str(sqlite_url):
    """@db.model with tags: list[str] = [] — CRUD MUST not crash."""
    db = DataFlow(sqlite_url)
    try:

        @db.model
        class Issue768Doc1:
            id: int
            title: str
            tags: list[str] = []

        # Pre-fix: this raised TypeError("isinstance() argument 2 cannot be a
        # parameterized generic"). The CRUD round-trip succeeding (with whatever
        # SQLite-side serialization the storage layer applies) is the
        # observable proof of the fix.
        created = await db.express.create(
            "Issue768Doc1", {"id": 1, "title": "doc one", "tags": ["a", "b"]}
        )
        assert created["id"] == 1
        rows = await db.express.list("Issue768Doc1")
        assert len(rows) == 1
        await db.express.update("Issue768Doc1", 1, {"tags": ["c"]})
    finally:
        await db.close_async()


@pytest.mark.asyncio
async def test_db_model_with_pep585_dict_str_any(sqlite_url):
    """@db.model with metadata: dict[str, Any] = {} — CRUD MUST not crash."""
    db = DataFlow(sqlite_url)
    try:

        @db.model
        class Issue768Doc2:
            id: int
            title: str
            meta: dict[str, typing.Any] = {}

        # Pre-fix: TypeError on isinstance(value, dict[str, Any]).
        created = await db.express.create(
            "Issue768Doc2",
            {"id": 1, "title": "doc two", "meta": {"k": "v", "n": 1}},
        )
        assert created["id"] == 1
        rows = await db.express.list("Issue768Doc2")
        assert len(rows) == 1
    finally:
        await db.close_async()


@pytest.mark.asyncio
async def test_db_model_with_typing_list_legacy_form(sqlite_url):
    """@db.model with tags: typing.List[str] = [] (legacy form) — CRUD MUST not crash."""
    db = DataFlow(sqlite_url)
    try:

        @db.model
        class Issue768Doc3:
            id: int
            title: str
            tags: typing.List[str] = []

        # Pre-fix: TypeError on isinstance(value, typing.List[str]).
        created = await db.express.create(
            "Issue768Doc3", {"id": 1, "title": "doc three", "tags": ["x"]}
        )
        assert created["id"] == 1
        rows = await db.express.list("Issue768Doc3")
        assert len(rows) == 1
    finally:
        await db.close_async()


@pytest.mark.asyncio
async def test_db_model_with_pep604_optional_parameterized(sqlite_url):
    """@db.model with tags: list[str] | None = None (PEP 604) — CRUD MUST not crash."""
    db = DataFlow(sqlite_url)
    try:

        @db.model
        class Issue768Doc4:
            id: int
            title: str
            tags: list[str] | None = None

        # Pre-fix: TypeError on isinstance(value, list[str] | None) — the union
        # form passes through get_origin as types.UnionType (PEP 604), which
        # the resolver MUST recurse-then-strip to land at ``list``.
        # Both None and concrete list MUST validate against the same field.
        await db.express.create(
            "Issue768Doc4", {"id": 1, "title": "doc four-a", "tags": None}
        )
        await db.express.create(
            "Issue768Doc4", {"id": 2, "title": "doc four-b", "tags": ["t"]}
        )
        rows = sorted(await db.express.list("Issue768Doc4"), key=lambda r: r["id"])
        assert len(rows) == 2
    finally:
        await db.close_async()
