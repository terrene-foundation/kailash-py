"""Regression test for issue #1207: Optional[list]/Optional[dict] JSONB round-trip.

`db.express.create`/`db.express.read` returned a JSON-encoded ``str`` instead of a
Python ``list``/``dict`` for model fields declared ``Optional[list]`` /
``Optional[dict]`` (JSONB columns). Plain ``list``/``dict`` fields worked; the
``Optional[...]`` wrap was the trigger.

Root cause: ``_deserialize_json_fields`` (dataflow/core/nodes.py) checked
``field_type in (dict, list)`` against the raw declared annotation. For an
``Optional[list]`` field the annotation is ``Union[list, None]`` (or PEP 604
``list | None``, a ``types.UnionType``), NOT the bare ``list`` type — so the
membership test was False, ``json.loads`` was skipped, and the JSON string leaked.

These are Tier-2 integration tests (real PostgreSQL, NO mocking) exercising the
full ``db.express`` create + read round-trip. CRITICAL per the issue: every
assertion uses a NON-EMPTY value — an empty list/dict passes through the bug
invisibly (``json.loads("[]") == []`` and the raw ``"[]"`` string also looks
benign), so empty values cannot prove the fix.
"""

from typing import Optional

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
async def test_optional_list_nonempty_roundtrip_returns_python_list(test_suite):
    """Optional[list] with a NON-EMPTY value round-trips back to a Python list."""
    db = DataFlow(test_suite.config.url, auto_migrate=True)

    @db.model
    class Issue1207OptListDoc:
        title: str
        tags: Optional[list] = None  # Optional[list] JSONB column — the bug trigger

    await db.initialize()

    payload = ["alpha", "beta", "gamma"]  # NON-EMPTY — empty list hides the bug
    created = await db.express.create(
        "Issue1207OptListDoc", {"title": "doc-a", "tags": payload}
    )

    assert isinstance(
        created["tags"], list
    ), f"create() leaked {type(created['tags']).__name__}: {created['tags']!r}"
    assert created["tags"] == payload

    fetched = await db.express.read("Issue1207OptListDoc", created["id"])
    assert isinstance(
        fetched["tags"], list
    ), f"read() leaked {type(fetched['tags']).__name__}: {fetched['tags']!r}"
    assert fetched["tags"] == payload


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
async def test_optional_dict_nonempty_roundtrip_returns_python_dict(test_suite):
    """Optional[dict] with a NON-EMPTY value round-trips back to a Python dict."""
    db = DataFlow(test_suite.config.url, auto_migrate=True)

    @db.model
    class Issue1207OptDictDoc:
        title: str
        meta: Optional[dict] = None  # Optional[dict] JSONB column — the bug trigger

    await db.initialize()

    payload = {"owner": "alice", "priority": 3, "nested": {"k": "v"}}  # NON-EMPTY
    created = await db.express.create(
        "Issue1207OptDictDoc", {"title": "doc-b", "meta": payload}
    )

    assert isinstance(
        created["meta"], dict
    ), f"create() leaked {type(created['meta']).__name__}: {created['meta']!r}"
    assert created["meta"] == payload

    fetched = await db.express.read("Issue1207OptDictDoc", created["id"])
    assert isinstance(
        fetched["meta"], dict
    ), f"read() leaked {type(fetched['meta']).__name__}: {fetched['meta']!r}"
    assert fetched["meta"] == payload
    assert fetched["meta"]["nested"] == {"k": "v"}


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
async def test_optional_list_none_value_stays_none(test_suite):
    """Optional[list] = None with a None value stays None (no crash, not "null")."""
    db = DataFlow(test_suite.config.url, auto_migrate=True)

    @db.model
    class Issue1207OptListNoneDoc:
        title: str
        tags: Optional[list] = None

    await db.initialize()

    created = await db.express.create(
        "Issue1207OptListNoneDoc", {"title": "doc-c", "tags": None}
    )
    assert created["tags"] is None, f"None leaked as {created['tags']!r}"

    fetched = await db.express.read("Issue1207OptListNoneDoc", created["id"])
    assert fetched["tags"] is None, f"None leaked as {fetched['tags']!r}"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
async def test_pep604_list_or_none_nonempty_roundtrip_returns_python_list(test_suite):
    """PEP 604 ``list | None`` (Python 3.10+) round-trips the same as Optional[list].

    ``list | None`` produces a ``types.UnionType`` whose ``typing.get_origin``
    returns ``types.UnionType`` (NOT ``typing.Union``), so the unwrap MUST handle
    both spellings.
    """
    db = DataFlow(test_suite.config.url, auto_migrate=True)

    @db.model
    class Issue1207Pep604Doc:
        title: str
        labels: list | None = None  # PEP 604 union — distinct origin from Optional

    await db.initialize()

    payload = ["x", "y", "z"]  # NON-EMPTY
    created = await db.express.create(
        "Issue1207Pep604Doc", {"title": "doc-d", "labels": payload}
    )
    assert isinstance(
        created["labels"], list
    ), f"create() leaked {type(created['labels']).__name__}: {created['labels']!r}"
    assert created["labels"] == payload

    fetched = await db.express.read("Issue1207Pep604Doc", created["id"])
    assert isinstance(
        fetched["labels"], list
    ), f"read() leaked {type(fetched['labels']).__name__}: {fetched['labels']!r}"
    assert fetched["labels"] == payload


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
async def test_plain_list_dict_fields_unaffected(test_suite):
    """No behavior change for plain (non-Optional) list/dict fields."""
    db = DataFlow(test_suite.config.url, auto_migrate=True)

    @db.model
    class Issue1207PlainDoc:
        title: str
        tags: list  # plain list — must keep working exactly as before
        meta: dict  # plain dict — must keep working exactly as before

    await db.initialize()

    tags = ["one", "two"]
    meta = {"a": 1, "b": [2, 3]}
    created = await db.express.create(
        "Issue1207PlainDoc", {"title": "doc-e", "tags": tags, "meta": meta}
    )
    assert created["tags"] == tags and isinstance(created["tags"], list)
    assert created["meta"] == meta and isinstance(created["meta"], dict)

    fetched = await db.express.read("Issue1207PlainDoc", created["id"])
    assert fetched["tags"] == tags and isinstance(fetched["tags"], list)
    assert fetched["meta"] == meta and isinstance(fetched["meta"], dict)
