"""Regression test for issue #1228: PEP 604 ``T | None`` unions across DataFlow.

#1207 fixed the JSONB read-path for ``Optional[list]`` / ``Optional[dict]``. #1228 is
the sibling: every OTHER type-introspection path (SQL-type inference, schema nullable
detection, param generation, validation optional-detection, type coercion) branched on
``origin is Union`` / ``__origin__ is Union`` WITHOUT matching ``types.UnionType``, so a
field declared with the PEP 604 spelling ``T | None`` was NOT recognized as optional.

This Tier-2 test declares a ``@db.model`` using ONLY the PEP 604 ``T | None`` spelling for
every nullable field and asserts the model auto-migrates and round-trips identically to
the ``Optional[T]`` spelling — real PostgreSQL, NO mocking. Per the #1207 precedent, every
JSONB assertion uses a NON-EMPTY value: an empty list/dict passes through the deserializer
bug invisibly (``json.loads("[]") == []``), so empty values cannot prove the fix.
"""

import pytest

from dataflow import DataFlow
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with real PostgreSQL infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
async def test_pep604_nullable_fields_automigrate_and_roundtrip(test_suite):
    """A @db.model using PEP 604 ``T | None`` for every nullable field works end-to-end.

    Exercises (in one path): schema nullable detection, param generation /
    SQL-type inference, validation optional-detection, type coercion, and the
    JSONB deserializer — all of which branched on the legacy Union spelling only.
    """
    db = DataFlow(test_suite.config.url, auto_migrate=True)

    @db.model
    class Issue1228Pep604Doc:
        title: str
        tags: list | None = None  # PEP 604 nullable JSONB (list)
        meta: dict | None = None  # PEP 604 nullable JSONB (dict)
        note: str | None = None  # PEP 604 nullable scalar
        count: int | None = None  # PEP 604 nullable scalar

    # auto_migrate must succeed — schema parsing has to treat every `T | None`
    # field as a nullable column (pre-#1228 the PEP 604 spelling was mishandled).
    await db.initialize()

    tags_payload = ["alpha", "beta", "gamma"]  # NON-EMPTY — empty hides the bug
    meta_payload = {"k1": "v1", "k2": 2, "nested": {"deep": True}}  # NON-EMPTY
    created = await db.express.create(
        "Issue1228Pep604Doc",
        {
            "title": "doc-pep604",
            "tags": tags_payload,
            "meta": meta_payload,
            "note": "hello",
            "count": 7,
        },
    )

    # JSONB fields round-trip back to Python list/dict, NOT a JSON string.
    assert isinstance(
        created["tags"], list
    ), f"create() leaked {type(created['tags']).__name__}: {created['tags']!r}"
    assert created["tags"] == tags_payload
    assert isinstance(
        created["meta"], dict
    ), f"create() leaked {type(created['meta']).__name__}: {created['meta']!r}"
    assert created["meta"] == meta_payload
    assert created["note"] == "hello"
    assert created["count"] == 7

    # Read path applies the same deserialization.
    fetched = await db.express.read("Issue1228Pep604Doc", created["id"])
    assert isinstance(fetched["tags"], list) and fetched["tags"] == tags_payload
    assert isinstance(fetched["meta"], dict) and fetched["meta"] == meta_payload
    assert fetched["note"] == "hello"
    assert fetched["count"] == 7


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
async def test_pep604_nullable_field_accepts_none(test_suite):
    """A PEP 604 ``T | None`` field accepts an omitted/None value (column is NULLABLE).

    If schema parsing failed to mark the column nullable (the pre-#1228 bug), the
    INSERT with the field omitted would violate a NOT NULL constraint.
    """
    db = DataFlow(test_suite.config.url, auto_migrate=True)

    @db.model
    class Issue1228Pep604Nullable:
        title: str
        tags: list | None = None

    await db.initialize()

    # Omit the PEP 604 nullable field entirely — must not raise NOT NULL.
    created = await db.express.create("Issue1228Pep604Nullable", {"title": "no-tags"})
    assert created["title"] == "no-tags"
    assert created["tags"] is None
