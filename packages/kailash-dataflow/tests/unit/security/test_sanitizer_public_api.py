"""DEFENSE-2 — Sanitizer public-API canary (issue #979 S6).

Pins the contract documented in ``rules/security.md`` § Sanitizer Contract
against the public ``db.express`` create-path. The actual
``sanitize_sql_input`` helper is a nested closure inside
``CreateNode.validate_inputs`` (see ``dataflow/core/nodes.py``), so the
only defense against silent drift is exercising it through the same
``CreateNode`` instance the express layer constructs at
``express.py:622`` (``self._create_node(model, "Create")``).

The two tests call ``validate_inputs`` directly on the CreateNode the
express layer would use — same construction path, same validation
gate — without triggering the DDL/INSERT that would require auto-
migration. If a refactor moves the ``raise ValueError("parameter type
mismatch: …")`` to a different layer OR weakens the token-replace
strategy in ``sanitize_sql_input``, these tests fail loudly.
"""

from __future__ import annotations

import pytest


def _create_node_for(memory_dataflow, model: str):
    """Build a CreateNode the same way ``express.create`` does at
    ``packages/kailash-dataflow/src/dataflow/features/express.py:622``.
    Returns a node whose ``validate_inputs`` has the live
    ``sanitize_sql_input`` closure + the type-confusion raise.
    """
    return memory_dataflow.express._create_node(model, "Create")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sanitizer_rejects_type_confusion_on_str_field(memory_dataflow):
    """rules/security.md § Sanitizer Contract Rule 2: a declared-string
    field receiving a dict / list / set / tuple value MUST raise
    ``ValueError`` with message ``parameter type mismatch: …`` — silent
    coercion via ``str(value)`` is BLOCKED.
    """
    db = memory_dataflow

    @db.model
    class Account:
        id: str
        name: str
        email: str

    node = _create_node_for(db, "Account")
    with pytest.raises(ValueError, match="parameter type mismatch"):
        # dict where str is declared → MUST raise at validate_inputs gate
        # (nodes.py:923-928 — the type-confusion guard).
        node.validate_inputs(
            id="acct-1",
            name={"$injection": "DROP TABLE users; --"},
            email="alice@example.com",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sanitizer_token_replaces_sql_keywords(memory_dataflow):
    """rules/security.md § Sanitizer Contract Rule 1: dangerous SQL
    keyword sequences in declared-string fields MUST be replaced with
    grep-able sentinel tokens (``STATEMENT_BLOCKED`` / ``DROP_TABLE`` /
    ``COMMENT_BLOCKED``) — quote-escape is BLOCKED.

    Token-replace is defense-in-depth on the display path; parameter
    binding is the primary SQLi defense (see § Parameterized Queries).
    The sentinels make attacker intent grep-able post-incident.
    """
    db = memory_dataflow

    @db.model
    class Item:
        id: str
        name: str

    node = _create_node_for(db, "Item")
    sanitized = node.validate_inputs(
        id="item-1",
        name="'; DROP TABLE users; --",
    )

    payload = sanitized.get("name", "")
    sentinels = ("STATEMENT_BLOCKED", "DROP_TABLE", "COMMENT_BLOCKED")
    assert any(s in payload for s in sentinels), (
        "sanitize_sql_input regressed: expected one of "
        f"{sentinels!r} in sanitized 'name' field; got {payload!r}"
    )
