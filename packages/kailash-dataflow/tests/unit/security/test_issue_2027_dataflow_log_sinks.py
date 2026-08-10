# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Issue #2027 — sensitive values reaching DataFlow's logs.

Two sinks in ``dataflow/core/nodes.py``, both driven through the same public
surfaces a caller uses, so the assertions read what actually reached the log
rather than what the source says:

1. ``sanitize_sql_input`` logged the raw PRE-sanitization value plus the schema
   field name when it detected an injection pattern. The field may be
   ``password``; the value is user-supplied plaintext.
2. The CREATE path built ``repr(value)[:50]`` for every bound parameter and
   emitted it at DEBUG. This one was flagged by neither the issue nor CodeQL —
   the value reaches the logger through an intermediate list, not by direct
   interpolation.

Both closures live inside ``NodeGenerator._create_node_class``, so they are
reachable only through a real node (see ``test_sanitizer_public_api.py``, which
pins the same construction path).
"""

from __future__ import annotations

import logging

import pytest

# An injection payload that also looks like a credential, so a single assertion
# covers both "raw value logged" and "secret logged".
INJECTION_SECRET = "p4ssw0rd'; DROP TABLE users; --"
CREATE_SECRET = "sk-live-9876543210zyxwvutsrq"


@pytest.mark.unit
@pytest.mark.parametrize(
    "rendered",
    [
        # Quoted-key mapping: Python dict repr and JSON.
        "{'id': 't-1', 'token': 'sk-live-9876543210zyxwvutsrq'}",
        '{"api_key": "sk-live-9876543210zyxwvutsrq"}',
        "{'password': 'sk-live-9876543210zyxwvutsrq'}",
        # Keys that CONTAIN a credential word rather than being one. All three
        # are standard credential names and all three leaked when the
        # alternation was anchored to the whole key.
        "{'api_token': 'sk-live-9876543210zyxwvutsrq'}",
        "{'x-api-key': 'sk-live-9876543210zyxwvutsrq'}",
        "{'client_secret': 'sk-live-9876543210zyxwvutsrq'}",
        "{'aws_secret_access_key': 'sk-live-9876543210zyxwvutsrq'}",
        # Unquoted key: object repr / kwargs, the shape
        # mask_sensitive_values(str(kwargs)) genuinely meets.
        "Node(token='sk-live-9876543210zyxwvutsrq')",
        "Create(id='t-1', client_secret='sk-live-9876543210zyxwvutsrq', n=1)",
        "Node(api_token=sk-live-9876543210zyxwvutsrq)",
        # A value containing the OTHER quote character. Python repr switches
        # quote style when the value holds an apostrophe; the single combined
        # value class stopped at that apostrophe and emitted the rest of the
        # secret verbatim -- output that carries BOTH the mask and the secret,
        # which is worse than not masking at all.
        "{'password': \"it's <sk-live-9876543210zyxwvutsrq>\"}",
    ],
)
def test_masker_covers_quoted_key_mapping_form(rendered: str) -> None:
    """``mask_sensitive_values(str(kwargs))`` was a no-op on dict/JSON shape.

    Every pattern required the key to be followed immediately by ``=``/``:``/
    whitespace, but in a mapping repr the key's own closing quote sits in
    between. The helper is the sole masker the node kwargs traces route
    through, so the gap meant credentials passed as ordinary model fields
    reached DEBUG verbatim.
    """
    from dataflow.core.logging_config import mask_sensitive_values

    masked = mask_sensitive_values(rendered)
    assert "sk-live-9876543210zyxwvutsrq" not in masked
    assert "***MASKED***" in masked


@pytest.mark.unit
@pytest.mark.parametrize(
    "rendered",
    [
        "{'id': 't-1', 'name': 'alice'}",
        # Widening the key match to allow affixes must not swallow these.
        # Masking a primary key would gut the parameter traces this issue's
        # other fixes deliberately preserved.
        "{'cache_key': 'users:1'}",
        "{'primary_key': 'id'}",
        "{'sort_key': 'created_at'}",
        # Affixes must be separated by _ or -, so a credential word appearing
        # as a bare substring does not match.
        "{'tokenizer': 'gpt2'}",
        "{'monkey': 'banana'}",
        "{'keyboard': 'qwerty'}",
    ],
)
def test_masker_leaves_non_sensitive_fields_intact(rendered: str) -> None:
    """Over-masking would destroy the diagnostic value of every trace."""
    from dataflow.core.logging_config import mask_sensitive_values

    assert mask_sensitive_values(rendered) == rendered


@pytest.mark.unit
def test_masking_does_not_corrupt_the_surrounding_text() -> None:
    """The mask must replace the value and nothing else.

    The generic value classes excluded whitespace and commas but not brackets,
    so a repr's closing paren was captured into the secret and vanished with
    it -- leaving unbalanced output that is hard to read and hard to parse.
    """
    from dataflow.core.logging_config import mask_sensitive_values

    assert (
        mask_sensitive_values("Node(api_token=sk-live-9876543210zyxwvutsrq)")
        == "Node(api_token=***MASKED***)"
    )
    assert (
        mask_sensitive_values("[token=sk-live-9876543210zyxwvutsrq]")
        == "[token=***MASKED***]"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sanitizer_warning_does_not_log_the_raw_value(memory_dataflow, caplog):
    """The injection warning must not carry the user's plaintext."""
    db = memory_dataflow

    @db.model
    class Credential:
        id: str
        password: str

    node = db.express._create_node("Credential", "Create")

    # The level MUST be set on ``dataflow.core.nodes`` itself. DataFlow
    # configures that logger's own level, so ``caplog.at_level(DEBUG)`` (which
    # raises the root logger) leaves the DEBUG line that carried the raw value
    # unemitted — and the assertion below would then pass against the unfixed
    # code, reporting on a line that never ran.
    caplog.set_level(logging.DEBUG, logger="dataflow.core.nodes")
    node.validate_inputs(id="c-1", password=INJECTION_SECRET)

    sanitizer_lines = [
        r
        for r in caplog.records
        if "injection" in r.getMessage().lower() and r.name == "dataflow.core.nodes"
    ]
    assert sanitizer_lines, "the sanitizer never logged; the test would be vacuous"
    assert any(
        "Sanitized" in r.getMessage() for r in sanitizer_lines
    ), "the DEBUG sanitization line never fired; the raw-value assertion is vacuous"
    for record in sanitizer_lines:
        assert (
            INJECTION_SECRET not in record.getMessage()
        ), "raw pre-sanitization value reached the log"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sanitizer_warning_does_not_log_the_field_name(memory_dataflow, caplog):
    """observability.md Rule 8 — schema field names are hashed, not emitted."""
    db = memory_dataflow

    @db.model
    class Credential:
        id: str
        password: str

    node = db.express._create_node("Credential", "Create")

    with caplog.at_level(logging.DEBUG):
        node.validate_inputs(id="c-1", password=INJECTION_SECRET)

    injection_lines = [
        r for r in caplog.records if "injection" in r.getMessage().lower()
    ]
    assert injection_lines, "the injection log line never fired; test would be vacuous"
    for record in injection_lines:
        assert "'password'" not in record.getMessage()
        assert "fp=" in record.getMessage(), "field fingerprint dropped"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_parameter_trace_does_not_log_bound_values(
    file_test_suite, caplog
):
    """The CREATE parameter trace emits position/type/length, never the value.

    ``file_test_suite`` rather than ``memory_dataflow`` because express CRUD
    dispatches across the runtime thread-pool and SQLite ``:memory:`` has
    thread affinity — same reasoning as ``test_db_express_async_smoke.py``.
    """
    harness = file_test_suite.dataflow_harness
    async with harness.infrastructure.connection() as conn:
        await conn.execute(
            """
            CREATE TABLE api_tokens (
                id TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await conn.commit()

    db = harness.create_dataflow()
    try:

        @db.model
        class ApiToken:
            id: str
            token: str

        await db.initialize()

        node = db.express._create_node("ApiToken", "Create")
        # The level must be set on ``dataflow.core.nodes`` specifically:
        # DataFlow configures that logger's own level, so raising only the
        # root logger leaves the DEBUG trace unemitted and the test vacuous.
        caplog.set_level(logging.DEBUG, logger="dataflow.core.nodes")
        result = await node.async_run(id="t-1", token=CREATE_SECRET)
        assert result["rows_affected"] == 1, "the create never ran; test is vacuous"

        trace_lines = [
            r for r in caplog.records if "Parameter details" in r.getMessage()
        ]
        assert trace_lines, "the CREATE parameter trace never fired; test is vacuous"
        # Scoped to DataFlow's own records. The aiosqlite driver logs its bound
        # parameters at DEBUG independently; that is third-party behaviour on a
        # driver logger an operator silences separately, and is not this fix's
        # surface. Asserting over the whole caplog would fail on it and make
        # this test report on a sink DataFlow does not own.
        ours = "\n".join(
            r.getMessage() for r in caplog.records if r.name.startswith("dataflow.")
        )
        assert CREATE_SECRET not in ours, "bound parameter value reached the DEBUG log"
        # The ordering diagnostic the line exists for must still be present.
        joined = "\n".join(r.getMessage() for r in trace_lines)
        assert "<redacted>" in joined
        assert "type=str" in joined
    finally:
        await db.close_async()
