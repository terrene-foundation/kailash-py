# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests for ``DataFlow.from_brief()`` (issue #1125).

Closes issue #1125 AC 2 + AC 7 against real Postgres + real LLM. Per
the 3-Tier contract (``rules/testing.md`` § 3-Tier Testing):

* **NO MOCKING** — real PostgreSQL container (via ``postgresql_db_url``
  fixture or ``TEST_DATABASE_URL`` env override); real LLM via the
  ``DEFAULT_LLM_MODEL`` env var per ``rules/env-models.md``.
* **State persistence verification** — every test calls
  ``db.express.create()`` then ``db.express.read()`` and asserts the
  written values come back, per ``rules/testing.md`` § "State
  Persistence Verification".
* **Per-variant direct call** — single-model and multi-model briefs
  each have their own test method, NOT one parameterised test, per
  ``rules/testing.md`` § "One Direct Test Per Variant".

LLM-cost note:
    Each test in this file makes ONE LLM call (to translate the brief
    into a schema plan). The single-model brief is ~70 tokens in /
    ~200 tokens out; the multi-model brief is ~90 tokens in / ~350
    tokens out. With a modest model (e.g. gpt-4o-mini), the per-test
    cost is sub-cent. The cost gate is the responsibility of CI's
    LLM-cost budget; this file does not pin a specific model.

Fixtures live at ``tests/regression/from_brief/fixtures/`` so the
brief / expected-plan contract is decoupled from the test logic. See
``tests/regression/from_brief/test_fixtures_no_secrets.py`` for the
B2b no-credentials-in-fixtures scan.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from dataflow import DataFlow

_REPO_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "regression" / "from_brief" / "fixtures"

# Sentinel that triggers an explicit skip when the LLM model env is
# not configured. Per ``rules/env-models.md``, the model name MUST
# come from .env; if a CI environment runs this Tier-2 file without
# the env set, the right disposition is to skip with a documented
# reason — not to fall back to a hardcoded model.
_LLM_ENV_KEYS = ("DEFAULT_LLM_MODEL", "OPENAI_PROD_MODEL")


def _llm_available() -> bool:
    """Return True when at least one of the LLM model env vars is set.

    Tier-2 tests are skipped (with a reason) when no LLM is reachable
    so the suite stays collectable in offline / clean-CI environments
    that don't carry the model env. The skip is the right disposition
    per ``rules/test-skip-discipline.md`` — better than masking with a
    regex-fallback or running against an inferred default model.
    """
    return any(bool(os.environ.get(k, "").strip()) for k in _LLM_ENV_KEYS)


def _load_fixture(name: str) -> Dict[str, Any]:
    """Load a YAML fixture from ``tests/regression/from_brief/fixtures/``.

    Returns the parsed dict. Raises with a clear message if the file
    is missing — the test surface should make missing fixtures loud,
    not silent.
    """
    path = _FIXTURE_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"from_brief fixture {name!r} not found at {path}; "
            f"this test depends on the fixture set landing in the "
            f"same commit"
        )
    with path.open(encoding="utf-8") as fp:
        loaded = yaml.safe_load(fp)
    assert isinstance(loaded, dict), (
        f"fixture {name!r} root MUST be a YAML mapping (got "
        f"{type(loaded).__name__!r})"
    )
    return loaded


# ---------------------------------------------------------------------------
# AC 2 — round-trip create() → read() against real Postgres.
# AC 7 — ≥2 brief shapes (single-model, multi-model + relationship).
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _llm_available(),
    reason=(
        "Tier-2 LLM test — DEFAULT_LLM_MODEL / OPENAI_PROD_MODEL unset; "
        "set per rules/env-models.md to exercise the from_brief() "
        "round-trip"
    ),
)
async def test_from_brief_single_model_round_trip(postgresql_db_url):
    """Single-model brief → realizer → round-trip ``create()`` → ``read()``.

    This is the canonical AC 2 acceptance test. The brief in
    ``dataflow_single_model.yaml`` describes a one-table schema
    (``Ticket``); the test calls ``DataFlow.from_brief(brief,
    conn_str=postgresql_db_url)``, awaits initialisation, then verifies
    a ``create()`` and a follow-up ``read()`` against real PostgreSQL.

    Per ``rules/testing.md`` § "State Persistence Verification",
    every write is verified with a read-back asserting the value
    survived the round-trip — this is the structural defense against
    DataFlow's "node returns success but silently dropped params"
    failure mode.
    """
    fixture = _load_fixture("dataflow_single_model.yaml")
    brief = fixture["brief"]
    expected = fixture["expected"]
    expected_model = expected["models"][0]
    model_name = expected_model["name"]

    # Realize the schema from the brief. ``from_brief`` is bound as a
    # classmethod on DataFlow per dataflow/__init__.py.
    db = DataFlow.from_brief(brief, postgresql_db_url)
    try:
        # AC 7: the realizer produced the expected model count.
        registered_models = db.get_models()
        assert model_name in registered_models, (
            f"realizer did not produce expected model {model_name!r}; "
            f"got {sorted(registered_models)!r}"
        )
        assert len(registered_models) == expected["model_count"], (
            f"realizer produced {len(registered_models)} models; "
            f"expected {expected['model_count']}"
        )

        # AC 7: every expected field name is present on the realized
        # model. Type-name assertions are deliberately lenient — the
        # validator already runs the allowlist gate, and the round-trip
        # below is the load-bearing proof that the type mapping landed
        # correctly (the create+read would fail on a wrong SQL type).
        realized_fields = db.get_model_fields(model_name)
        for spec in expected_model["fields"]:
            fname = spec["name"]
            assert fname in realized_fields, (
                f"realizer did not synthesise expected field "
                f"{fname!r} on model {model_name!r}; got "
                f"{sorted(realized_fields)!r}"
            )

        # Initialise the database so the auto-migrate path creates
        # the table. ``initialize_deferred_migrations`` is the async
        # entry point the engine docs recommend for async test
        # contexts (engine.py:244).
        await db.initialize_deferred_migrations()

        # AC 2 round-trip — create + read against real Postgres.
        # Field values are chosen so a future type-handling bug would
        # surface: a datetime column would fail to round-trip if
        # the realizer mistakenly mapped it to text.
        import datetime as dt

        record_id = 1
        write_payload = {
            "id": record_id,
            "subject": "Cannot log in",
            "body": "Reset password link does not arrive.",
            "status": "open",
            "created_at": dt.datetime(2026, 5, 27, 9, 30, 0),
            "resolved": False,
        }
        created = await db.express.create(model_name, write_payload)
        assert created is not None, "from_brief.create() returned None"
        assert created.get("id") == record_id, (
            f"created record id mismatch: expected {record_id}, "
            f"got {created.get('id')!r}"
        )

        # AC 2 read-back — every written field MUST survive.
        readback = await db.express.read(model_name, record_id)
        assert readback is not None, (
            f"from_brief.read({model_name!r}, {record_id!r}) returned "
            f"None; round-trip broken"
        )
        for field_name, expected_value in write_payload.items():
            actual = readback.get(field_name)
            assert actual == expected_value, (
                f"round-trip mismatch on {field_name!r}: wrote "
                f"{expected_value!r}, read back {actual!r}"
            )
    finally:
        try:
            db.close()
        except Exception:
            pass


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _llm_available(),
    reason=(
        "Tier-2 LLM test — DEFAULT_LLM_MODEL / OPENAI_PROD_MODEL unset; "
        "set per rules/env-models.md to exercise the multi-model "
        "round-trip"
    ),
)
async def test_from_brief_multi_model_with_relationship(postgresql_db_url):
    """Multi-model brief with one_to_many relationship → realizer → round-trip.

    Closes AC 7's "≥2 brief shapes" requirement. The brief in
    ``dataflow_multi_model.yaml`` describes a parent (``User``) and
    child (``Post``) with a one_to_many relationship; the test
    verifies the realizer:

    1. Produced both models.
    2. Spliced the foreign-key column (``user_id``) into the child
       model per ``realize_models`` pass-2 logic.
    3. The round-trip create+read works on BOTH models, with a
       parent row's id linking to a child row's user_id column.
    """
    fixture = _load_fixture("dataflow_multi_model.yaml")
    brief = fixture["brief"]
    expected = fixture["expected"]
    expected_fks = fixture.get("expected_fk_columns", {})

    db = DataFlow.from_brief(brief, postgresql_db_url)
    try:
        registered_models = db.get_models()
        assert len(registered_models) == expected["model_count"], (
            f"realizer produced {len(registered_models)} models; "
            f"expected {expected['model_count']}"
        )
        for spec in expected["models"]:
            assert spec["name"] in registered_models, (
                f"realizer did not produce model {spec['name']!r}; "
                f"got {sorted(registered_models)!r}"
            )

        # AC 7 — FK column was spliced into the child by realize_models
        # pass 2. Per the relationship spec in the brief, ``Post``
        # MUST grow ``user_id: int``.
        for child_name, fk_columns in expected_fks.items():
            realized = db.get_model_fields(child_name)
            for fk in fk_columns:
                assert fk in realized, (
                    f"realizer did not splice FK column {fk!r} into "
                    f"child model {child_name!r}; got "
                    f"{sorted(realized)!r}"
                )

        await db.initialize_deferred_migrations()

        # AC 2 — round-trip on the parent.
        parent_id = 100
        parent_payload = {
            "id": parent_id,
            "username": "alice",
            "email": "alice@example.com",
        }
        parent_created = await db.express.create("User", parent_payload)
        assert parent_created is not None
        assert parent_created.get("id") == parent_id

        parent_readback = await db.express.read("User", parent_id)
        assert parent_readback is not None
        assert parent_readback.get("username") == parent_payload["username"]
        assert parent_readback.get("email") == parent_payload["email"]

        # AC 2 — round-trip on the child, with the FK pointing at the
        # parent row. This is the structural proof that the
        # relationship FK splice produced a usable column.
        import datetime as dt

        child_id = 200
        child_payload = {
            "id": child_id,
            "title": "My first post",
            "body": "Hello, world.",
            "created_at": dt.datetime(2026, 5, 27, 10, 0, 0),
            "user_id": parent_id,
        }
        child_created = await db.express.create("Post", child_payload)
        assert child_created is not None
        assert child_created.get("id") == child_id

        child_readback = await db.express.read("Post", child_id)
        assert child_readback is not None
        for field_name, expected_value in child_payload.items():
            actual = child_readback.get(field_name)
            assert actual == expected_value, (
                f"child round-trip mismatch on {field_name!r}: "
                f"wrote {expected_value!r}, read back {actual!r}"
            )
    finally:
        try:
            db.close()
        except Exception:
            pass
