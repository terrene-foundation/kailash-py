# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: `normalize_tool_input_schema` — three redteam findings (#1720).

`kaizen.core.tool_formatters.normalize_tool_input_schema` is the ONE
normalizer every MCP→provider tool converter routes through. A redteam found
three defects in it:

(a) OBSERVABILITY. A genuinely BROKEN tool registration (``inputSchema`` is a
    list, a string, an int — anything that is not a dict) was silently
    replaced with the empty-object schema, indistinguishable from a
    deliberately permission-GATED tool advertising ``{}``. Nothing was logged,
    so a mis-registered tool looked exactly like a working gated one.

    The empty/absent cases MUST stay SILENT: ``{}`` is what EVERY gated tool
    advertises and ``None`` is what ``tool.get("inputSchema")`` returns for
    every tool that declares no parameters, so warning on either would emit
    one line per tool per conversion — a flood that buries the real signal.

(b) DOC OVER-CLAIM. The docstring promised a return that is "always a VALID
    JSON Schema object", but ``{"type": "string"}`` is passed through
    unchanged — a valid JSON Schema, and deliberately NOT object-typed.

(c) ALIASING. The third branch returned the CALLER'S dict by identity while
    the other two branches returned fresh dicts. The caller's dict is the MCP
    client's cached tool registration, so any downstream mutation of the
    "normalized" schema wrote straight back into the tool registry.

Every test below drives the real function; nothing here is mocked.
"""

import logging

import pytest

from kaizen.core.tool_formatters import normalize_tool_input_schema

#: The structured event name the non-dict branch emits.
EVENT = "tool_formatters.input_schema_not_a_dict"

#: The logger the module logs through (`logging.getLogger(__name__)`).
LOGGER_NAME = "kaizen.core.tool_formatters"


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


# ---------------------------------------------------------------------------
# (a) A broken registration is observable — and ONLY a broken one.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_non_dict_schema_emits_a_structured_warning(caplog):
    """A list where an object schema belongs is a broken tool registration."""
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        out = normalize_tool_input_schema(["type", "object"])

    records = _warnings(caplog)
    assert len(records) == 1, (
        "a NON-DICT inputSchema is a broken tool registration and must be "
        f"observable; got {len(records)} WARN+ records"
    )
    assert records[0].getMessage() == EVENT
    assert records[0].schema_type == "list"
    # The tool still converts — the warning reports, it does not break the run.
    assert out == {"type": "object", "properties": {}}


@pytest.mark.regression
def test_non_dict_warning_reports_the_type_not_the_value(caplog):
    """The warning names the TYPE only.

    A malformed registration can carry anything — including a connection
    string with an embedded credential. `rules/security.md` § "No secrets in
    logs": the diagnostic value is the type, so the type is all that is
    logged.
    """
    secret_bearing = "postgres://user:S3cr3tTOOLSCHEMA@host/db?token=tk_live_9"

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        normalize_tool_input_schema(secret_bearing)

    records = _warnings(caplog)
    assert len(records) == 1
    assert records[0].getMessage() == EVENT
    assert records[0].schema_type == "str"
    assert "S3cr3tTOOLSCHEMA" not in str(records[0].__dict__)
    assert "tk_live_9" not in str(records[0].__dict__)


@pytest.mark.regression
def test_gated_empty_schema_stays_silent(caplog):
    """CONTROL. ``{}`` is what EVERY permission-gated tool advertises.

    Green before and after the fix — it exists to catch an over-broad
    implementation of the warning above, which would emit one line per gated
    tool per conversion.
    """
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        out = normalize_tool_input_schema({})

    assert _warnings(caplog) == []
    assert out == {"type": "object", "properties": {}}


@pytest.mark.regression
def test_absent_schema_stays_silent(caplog):
    """CONTROL. ``tool.get("inputSchema")`` yields ``None`` for every tool
    that declares no parameters — the documented ordinary path, not a broken
    registration. Also green before and after; also an anti-flood guard.
    """
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        out = normalize_tool_input_schema(None)

    assert _warnings(caplog) == []
    assert out == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# (b) The docstring states what is actually guaranteed.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_declared_non_object_type_is_passed_through_uncoerced():
    """A schema that already declares a type keeps it.

    Coercing ``{"type": "string"}`` to ``object`` would silently rewrite a
    tool that legitimately declares a non-object parameter shape. This is the
    behaviour the corrected docstring describes.
    """
    schema = {"type": "string"}
    out = normalize_tool_input_schema(schema)

    assert out == {"type": "string"}
    assert out is not schema


@pytest.mark.regression
def test_docstring_states_the_guarantee_it_actually_delivers():
    """The docstring is the contract every call site reads.

    It must state the three things this function really promises: the result
    is a fresh dict (never the caller's, by identity), a declared type is
    passed through unchanged, and the copy is shallow.
    """
    doc = (normalize_tool_input_schema.__doc__ or "").lower()

    assert "identity" in doc, "must state the caller's dict is never returned"
    assert "unchanged" in doc, "must state a declared type is passed through"
    assert "shallow" in doc, "must state the copy does not reach nested values"


# ---------------------------------------------------------------------------
# (c) The caller's registration is never handed back or written into.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_complete_schema_is_returned_as_a_fresh_dict():
    """The caller's dict is the MCP client's cached tool registration."""
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    out = normalize_tool_input_schema(schema)

    assert out == schema, "a real schema must not be rewritten"
    assert out is not schema, (
        "the caller's registration dict must never be returned by identity; "
        "the other two branches already return fresh dicts"
    )


@pytest.mark.regression
def test_mutating_the_result_leaves_the_registry_entry_intact():
    """The observable consequence of the identity leak.

    A downstream provider adapter that stamps a key onto the schema it was
    handed must not thereby edit the tool registry.
    """
    registry_entry = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
    }

    out = normalize_tool_input_schema(registry_entry)
    out["additionalProperties"] = False

    assert registry_entry == {
        "type": "object",
        "properties": {"query": {"type": "string"}},
    }
