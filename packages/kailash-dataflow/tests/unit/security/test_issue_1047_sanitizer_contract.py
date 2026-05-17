"""Issue #1047 — Tier-1 sanitizer-contract tests (C-1 of #979 triage).

Comprehensive Tier-1 coverage of ``rules/security.md`` § "Sanitizer
Contract — DataFlow Display Hygiene" Rules 1+2+3. Pre-existing platform
test-coverage gap — test-authoring only, no production change.

The sanitizer ``sanitize_sql_input`` is a nested closure inside
``DataFlowNode.validate_inputs`` (``dataflow/core/nodes.py:787``). The
type-confusion ``ValueError`` (Rule 2) is raised in the post-sanitize
gate of the *same* ``validate_inputs`` method (``nodes.py:920-928`` for
create/update). Both are exercised through a generated CreateNode built
the same way ``express.create`` builds it
(``features/express.py:214 _create_node`` → ``node_class()`` + bound
``dataflow_instance``). These are BEHAVIORAL tests — they call
``validate_inputs`` and assert on its real return value / the real
raised exception, never grep the source (rules/testing.md §
Behavioral Regression). The sanitizer itself runs real — nothing under
test is mocked (rules/testing.md § no-mocking-the-thing-under-test).

Contract pinned (rules/security.md, authoritative):

* Rule 1 — declared-string fields: dangerous SQL keyword sequences
  MUST be token-replaced with grep-able sentinels
  (``STATEMENT_BLOCKED`` / ``UNION_SELECT`` / ``DROP_TABLE`` /
  ``DELETE_FROM`` / ``OR_1_EQUALS_1`` / ``COMMENT_BLOCKED`` …).
  Quote-escape (``'`` → ``''``) is BLOCKED.
* Rule 2 — declared-string field receiving dict/list/set/tuple MUST
  raise ``ValueError("parameter type mismatch: …")``. Silent
  ``str(value)`` coercion is BLOCKED.
* Rule 3 — safe types (int/float/bool/Decimal/datetime/date/time) and
  declared dict/list (JSON / array columns, bug #515) pass through
  unchanged. No premature ``json.dumps``.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

import pytest


def _create_node_for(db, model: str):
    """Build a CreateNode the same way ``express.create`` does
    (``packages/kailash-dataflow/src/dataflow/features/express.py:214``
    ``_create_node`` → ``node_class()`` bound to the DataFlow instance).
    Returns a node whose ``validate_inputs`` has the live
    ``sanitize_sql_input`` closure + the type-confusion raise gate.
    """
    return db.express._create_node(model, "Create")


# ---------------------------------------------------------------------------
# Rule 1 — token-replace, NOT quote-escape
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule1_drop_table_statement_chain_token_replaced(memory_dataflow):
    """``"'; DROP TABLE users; --"`` MUST yield grep-able sentinels
    (``STATEMENT_BLOCKED`` from the statement-chain regex, plus
    ``COMMENT_BLOCKED`` from the trailing ``--``) and MUST NOT be
    quote-escaped to ``''``.
    """
    db = memory_dataflow

    @db.model
    class R1Drop:
        id: str
        name: str

    node = _create_node_for(db, "R1Drop")
    out = node.validate_inputs(id="x", name="'; DROP TABLE users; --")
    payload = out["name"]

    assert (
        "STATEMENT_BLOCKED" in payload
    ), f"Rule 1 regressed: statement-chain not tokenised; got {payload!r}"
    assert (
        "COMMENT_BLOCKED" in payload
    ), f"Rule 1 regressed: trailing comment not tokenised; got {payload!r}"
    # NEGATIVE — quote-escape strategy is BLOCKED. The original single
    # quote is preserved as data; it MUST NOT be doubled to ''.
    assert "''" not in payload, (
        f"Rule 1 violated: quote-escape detected (''); the sanitizer "
        f"must token-replace, not quote-escape. got {payload!r}"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule1_union_select_token_replaced(memory_dataflow):
    """``UNION SELECT`` MUST become the ``UNION_SELECT`` sentinel."""
    db = memory_dataflow

    @db.model
    class R1Union:
        id: str
        name: str

    node = _create_node_for(db, "R1Union")
    out = node.validate_inputs(id="x", name="1 UNION SELECT password FROM accounts")
    assert (
        "UNION_SELECT" in out["name"]
    ), f"Rule 1 regressed: UNION SELECT not tokenised; got {out['name']!r}"
    assert "''" not in out["name"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule1_select_from_token_replaced(memory_dataflow):
    """``SELECT * FROM`` MUST become the ``SELECT_FROM`` sentinel."""
    db = memory_dataflow

    @db.model
    class R1Select:
        id: str
        name: str

    node = _create_node_for(db, "R1Select")
    out = node.validate_inputs(id="x", name="SELECT * FROM secrets")
    assert (
        "SELECT_FROM" in out["name"]
    ), f"Rule 1 regressed: SELECT FROM not tokenised; got {out['name']!r}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule1_delete_from_statement_chain_token_replaced(memory_dataflow):
    """``"'; DELETE FROM accounts; --"`` MUST tokenise via the
    statement-chain sentinel (not quote-escape)."""
    db = memory_dataflow

    @db.model
    class R1Delete:
        id: str
        name: str

    node = _create_node_for(db, "R1Delete")
    out = node.validate_inputs(id="x", name="'; DELETE FROM accounts; --")
    assert (
        "STATEMENT_BLOCKED" in out["name"]
    ), f"Rule 1 regressed: DELETE chain not tokenised; got {out['name']!r}"
    assert "''" not in out["name"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule1_or_1_equals_1_token_replaced(memory_dataflow):
    """``admin' OR '1'='1`` MUST become the ``OR_1_EQUALS_1`` sentinel."""
    db = memory_dataflow

    @db.model
    class R1Or:
        id: str
        name: str

    node = _create_node_for(db, "R1Or")
    out = node.validate_inputs(id="x", name="admin' OR '1'='1")
    assert (
        "OR_1_EQUALS_1" in out["name"]
    ), f"Rule 1 regressed: OR 1=1 not tokenised; got {out['name']!r}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule1_block_comment_token_replaced(memory_dataflow):
    """A ``/* ... */`` block comment MUST become the
    ``/* COMMENT_BLOCKED */`` sentinel."""
    db = memory_dataflow

    @db.model
    class R1Comment:
        id: str
        name: str

    node = _create_node_for(db, "R1Comment")
    out = node.validate_inputs(id="x", name="value/* hack */tail")
    assert (
        "COMMENT_BLOCKED" in out["name"]
    ), f"Rule 1 regressed: block comment not tokenised; got {out['name']!r}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule1_benign_string_unchanged_no_false_positive(memory_dataflow):
    """A benign string MUST pass through verbatim — the sanitizer must
    not inject sentinels into safe content (no false-positive
    tokenisation)."""
    db = memory_dataflow

    @db.model
    class R1Benign:
        id: str
        name: str

    node = _create_node_for(db, "R1Benign")
    benign = "Alice O'Brien — senior data analyst (NYC)"
    out = node.validate_inputs(id="x", name=benign)
    assert (
        out["name"] == benign
    ), f"benign string altered: {out['name']!r} != {benign!r}"
    for sentinel in (
        "STATEMENT_BLOCKED",
        "UNION_SELECT",
        "DROP_TABLE",
        "COMMENT_BLOCKED",
        "OR_1_EQUALS_1",
    ):
        assert sentinel not in out["name"]


# ---------------------------------------------------------------------------
# Rule 2 — type-confusion MUST raise, never silently coerce
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param({"$injection": "DROP TABLE x; --"}, id="dict"),
        pytest.param(["DROP TABLE x; --"], id="list"),
    ],
)
async def test_rule2_type_confusion_dict_list_on_str_field_raises(
    memory_dataflow, bad_value
):
    """A declared-``str`` field receiving dict/list MUST raise
    ``ValueError`` with ``parameter type mismatch`` — silent
    ``str(value)`` coercion is BLOCKED (nodes.py:920-928).

    dict/list are in ``sanitize_sql_input``'s ``safe_types`` tuple
    (nodes.py:805-816) so they survive the sanitize pass as their
    original type and the post-sanitize type-confusion gate
    (nodes.py:920-928) sees them and raises. CONFORMS to the contract.
    """
    db = memory_dataflow

    @db.model
    class R2Confuse:
        id: str
        name: str
        email: str

    node = _create_node_for(db, "R2Confuse")
    with pytest.raises(ValueError, match="parameter type mismatch"):
        node.validate_inputs(id="acct-1", name=bad_value, email="alice@example.com")


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param({"DROP TABLE x"}, id="set"),
        pytest.param(("DROP TABLE x", "--"), id="tuple"),
    ],
)
async def test_rule2_type_confusion_set_tuple_on_str_field_raises(
    memory_dataflow, bad_value
):
    """CONTRACT ASSERTION (now enforced — issue #1047 production fix):
    a declared-``str`` field receiving set/tuple MUST raise ``ValueError``
    with ``parameter type mismatch``. rules/security.md § Sanitizer
    Contract Rule 2 explicitly enumerates set/tuple as MUST-raise.

    The fix added ``set``/``tuple`` to ``sanitize_sql_input``'s
    ``safe_types`` tuple (nodes.py) so they pass through the sanitizer
    UNCHANGED (not ``str()``-coerced) — exactly the mechanism dict/list
    already used. The downstream type-confusion gate then sees the real
    ``set``/``tuple`` and raises, on BOTH the create/update path
    (single-value) AND the bulk_* path (via ``sanitize_nested_structure``
    leaf → ``sanitize_sql_input`` returning the container unchanged).
    The ``xfail(strict=True)`` marker was removed in the SAME commit as
    the production fix (orphan-detection Rule 4a — implement-the-deferral
    sweeps its own deferral marker).
    """
    db = memory_dataflow

    @db.model
    class R2ConfuseSetTuple:
        id: str
        name: str
        email: str

    node = _create_node_for(db, "R2ConfuseSetTuple")
    with pytest.raises(ValueError, match="parameter type mismatch"):
        node.validate_inputs(id="acct-1", name=bad_value, email="alice@example.com")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule2_error_message_names_field_and_declared_type(
    memory_dataflow,
):
    """The ``ValueError`` MUST identify the offending field and that it
    was declared ``str`` — so the failure is actionable, not opaque."""
    db = memory_dataflow

    @db.model
    class R2Msg:
        id: str
        name: str

    node = _create_node_for(db, "R2Msg")
    with pytest.raises(ValueError) as exc_info:
        node.validate_inputs(id="x", name={"k": "v"})

    msg = str(exc_info.value)
    assert "parameter type mismatch" in msg
    assert "name" in msg, f"error must name the field; got {msg!r}"
    assert "str" in msg, f"error must cite declared type 'str'; got {msg!r}"


# ---------------------------------------------------------------------------
# Rule 3 — safe types pass through unchanged (bug #515 pin)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule3_scalar_safe_types_unchanged(memory_dataflow):
    """int / float / bool MUST pass through ``validate_inputs``
    unchanged (no string coercion, no tokenisation)."""
    db = memory_dataflow

    @db.model
    class R3Scalar:
        id: str
        count: int
        ratio: float
        active: bool

    node = _create_node_for(db, "R3Scalar")
    out = node.validate_inputs(id="x", count=42, ratio=3.14, active=True)
    assert out["count"] == 42 and isinstance(out["count"], int)
    assert out["ratio"] == 3.14 and isinstance(out["ratio"], float)
    assert out["active"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule3_decimal_and_temporal_types_unchanged(memory_dataflow):
    """Decimal / datetime / date / time MUST pass through by identity —
    no coercion to string, no tokenisation."""
    db = memory_dataflow

    @db.model
    class R3Temporal:
        id: str
        price: Decimal
        created_at: datetime
        the_date: date
        the_time: time

    node = _create_node_for(db, "R3Temporal")
    price = Decimal("19.99")
    dt = datetime(2026, 5, 18, 12, 30, 0)
    d = date(2026, 5, 18)
    t = time(12, 30, 0)
    out = node.validate_inputs(
        id="x", price=price, created_at=dt, the_date=d, the_time=t
    )
    assert out["price"] == price and isinstance(out["price"], Decimal)
    assert out["created_at"] == dt and isinstance(out["created_at"], datetime)
    assert out["the_date"] == d
    assert out["the_time"] == t


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule3_declared_dict_field_passthrough_no_premature_jsondumps(
    memory_dataflow,
):
    """Bug #515 pin: a declared-``dict`` field (JSON column) receiving a
    dict MUST pass through as a dict — NOT serialised to a JSON string
    at validation. Premature ``json.dumps`` breaks parameter binding."""
    db = memory_dataflow

    @db.model
    class R3Json:
        id: str
        metadata: dict

    node = _create_node_for(db, "R3Json")
    payload = {"role": "admin", "scopes": ["read", "write"]}
    out = node.validate_inputs(id="x", metadata=payload)
    assert isinstance(out["metadata"], dict), (
        f"bug #515 regression: dict serialised at validation; "
        f"got {type(out['metadata']).__name__}"
    )
    assert out["metadata"] == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rule3_declared_list_field_passthrough_no_premature_jsondumps(
    memory_dataflow,
):
    """Bug #515 pin: a declared-``list`` field (array / JSON column)
    receiving a list MUST pass through as a list, not a JSON string."""
    db = memory_dataflow

    @db.model
    class R3Array:
        id: str
        tags: list

    node = _create_node_for(db, "R3Array")
    payload = ["alpha", "beta", "gamma"]
    out = node.validate_inputs(id="x", tags=payload)
    assert isinstance(out["tags"], list), (
        f"bug #515 regression: list serialised at validation; "
        f"got {type(out['tags']).__name__}"
    )
    assert out["tags"] == payload
