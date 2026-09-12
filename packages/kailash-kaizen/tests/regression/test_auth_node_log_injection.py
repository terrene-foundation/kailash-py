# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: the kaizen AUTH + node-base log sinks are newline-forgeable.

Three sinks rendered a caller- or IdP-controlled value into a log record with
no newline flatten, so a value carrying ``\\n`` produced a SECOND record that a
downstream reader cannot distinguish from one this process emitted:

* ``kaizen/nodes/auth/sso.py``            -- the SSO assertion's ``email``
* ``kaizen/nodes/auth/directory_integration.py`` -- the directory search term
* ``kaizen/nodes/base.py``                -- the prompt

The prompt site is the instructive one: it ALREADY had a 100-character bound
and no flatten -- precisely the wrong half of the barrier. A bound limits how
much log VOLUME a caller can drive; only the flatten stops the forging. The
two are independent properties and a site needs both.

WHY THE INSTRUMENT READS THE HANDLER, not just ``caplog.records``
----------------------------------------------------------------
MEASURED, not assumed: a payload-carrying value produces ONE ``LogRecord``
whose rendered text spans TWO lines. So a record-COUNT assertion alone is not
discriminating here -- it reads 1 both before and after the fix. The forged
record materializes one layer down, at the handler, where every line-oriented
consumer (file handler, journald, a log shipper, ``grep``) sees two records.

``caplog.text`` is no better: it joins records with a newline, so a forged
line and a legitimately-second record render identically in it.

Each site is therefore pinned at BOTH layers -- the lines a real
``StreamHandler`` emits, AND the absence of ``\n``/``\r`` inside the single
record's own message.

BOTH POLARITIES ARE PINNED
--------------------------
* POSITIVE -- no forged second record; no raw ``\\n`` in the message; for the
  auth sites, no raw email address anywhere on the record.
* NEGATIVE -- the diagnostic content that makes each record worth emitting is
  still there (the benign head of the query/prompt, the assigned roles, the
  correlation tag). A "fix" that simply deleted the log statements would pass
  the positive half alone; these controls are what forbid it.

PII disposition (distinct from injection, and NOT satisfied by sanitizing)
--------------------------------------------------------------------------
``rules/security.md`` says MUST NOT log PII, and #2030 already ruled agent I/O
values off INFO in this package. An email address on the authentication path
is PII, so the two auth role-assignment records carry a stable non-reversible
``fingerprint_value`` correlation tag INSTEAD of the address: that still
answers the question the record exists for ("which principal received which
roles") and joins across records for the same subject, without putting an
identifier on the line.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import pathlib

import kaizen.nodes.base
from kailash.utils import secure_logging
from kailash.utils.url_credentials import fingerprint_value
from kaizen.nodes.auth.directory_integration import DirectoryIntegrationNode
from kaizen.nodes.auth.sso import SSOAuthenticationNode
from kaizen.nodes.base import KaizenNode

SSO_LOGGER = "kaizen.nodes.auth.sso"
DIR_LOGGER = "kaizen.nodes.auth.directory_integration"
BASE_LOGGER = "kailash.nodes.test_log_injection_node"

#: A forged-record payload: the newline ends the real record and everything
#: after it reads, to any line-oriented consumer, as a record this process
#: emitted at a level it never used.
FORGED = "\nERROR:kaizen.audit:privilege escalation approved for attacker"
#: Carriage return alone re-writes a console line without a newline.
FORGED_CR = "\rCRITICAL:kaizen.audit:all checks bypassed"

EMAIL = "victim@example.com"


def test_modules_under_test_are_the_ones_in_this_checkout():
    """Guard against the false GREEN an unpinned PYTHONPATH produces.

    ``kaizen`` and ``kailash`` are SEPARATE distributions in this repo. A run
    that imports either from site-packages verifies the INSTALLED copy and
    reports on code this branch does not contain -- silently, and in both
    directions. Both are pinned to the tree this test file lives in.
    """
    here = pathlib.Path(__file__).resolve()
    # .../<root>/packages/kailash-kaizen/tests/regression/<this file>
    root = here.parents[4]
    assert (
        pathlib.Path(kaizen.nodes.base.__file__).resolve().is_relative_to(root)
    ), f"kaizen imported from {kaizen.nodes.base.__file__}, not from {root}"
    assert (
        pathlib.Path(secure_logging.__file__).resolve().is_relative_to(root)
    ), f"kailash imported from {secure_logging.__file__}, not from {root}"


class _StubLLM:
    """Stands in for ``LLMAgentNode``: returns one canned nested envelope."""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    async def async_run(self, **_kwargs) -> dict:
        return {"response": {"content": json.dumps(self._payload)}}


def _records(caplog, logger_name: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == logger_name]


class emitting:
    """Capture what a HANDLER actually writes for one logger.

    This is the layer the forged record materializes at, and the reason this
    test does not stop at ``caplog.records``. A payload-carrying value
    produces ONE ``LogRecord`` whose rendered text spans TWO lines -- so a
    record-count assertion alone is NOT discriminating here, and would report
    GREEN against the unfixed code. Every line-oriented consumer downstream
    (a file handler, journald, a log shipper, `grep`) sees two records.

    The format mirrors the conventional ``LEVEL:logger:message`` so a forged
    line is indistinguishable from a real one -- which is the point.
    """

    def __init__(self, logger_name: str, level: int = logging.DEBUG) -> None:
        self._logger = logging.getLogger(logger_name)
        self._stream = io.StringIO()
        self._handler = logging.StreamHandler(self._stream)
        self._handler.setFormatter(
            logging.Formatter("%(levelname)s:%(name)s:%(message)s")
        )
        self._level = level
        self._previous: int | None = None

    def __enter__(self) -> "emitting":
        self._previous = self._logger.level
        self._logger.setLevel(self._level)
        self._logger.addHandler(self._handler)
        return self

    def __exit__(self, *_exc) -> None:
        self._logger.removeHandler(self._handler)
        if self._previous is not None:
            self._logger.setLevel(self._previous)

    def lines(self) -> list[str]:
        """Every non-empty line a consumer would read, forged ones included."""
        return [ln for ln in self._stream.getvalue().split("\n") if ln]


def _assert_no_forged_line(capture: "emitting") -> None:
    """No emitted line may BEGIN with a level/logger prefix we never used.

    This is the precise forging property, and it is deliberately not "the
    payload text is absent": `sanitize_log_value` flattens, it does not
    REDACT. A short attacker-chosen value surviving on one line is the
    documented behaviour and is usually the only diagnostic there is -- what
    must not survive is a value that becomes its OWN record. An assertion
    that the payload text is gone would therefore fail against the correct
    fix, which is how this helper came to exist.
    """
    forged = [
        ln
        for ln in capture.lines()
        if ln.startswith("ERROR:kaizen.audit") or ln.startswith("CRITICAL:kaizen.audit")
    ]
    assert not forged, f"payload forged its own record(s): {forged}"


def _assert_single_unforged_record(records: list[logging.LogRecord]) -> str:
    """The record-level half: ONE record, and its message is one line."""
    assert len(records) == 1, (
        f"expected exactly 1 record, got {len(records)}: "
        f"{[r.getMessage() for r in records]}"
    )
    message = records[0].getMessage()
    assert "\n" not in message, f"newline survived into the record: {message!r}"
    assert "\r" not in message, f"carriage return survived: {message!r}"
    return message


# --------------------------------------------------------------------------
# Site 1 -- SSO role assignment: IdP-supplied email (injection AND PII)
# --------------------------------------------------------------------------


def _sso_node(payload: object) -> SSOAuthenticationNode:
    """Build the node without its env-dependent constructor chain.

    ``__init__`` resolves a model from ``KAIZEN_DEFAULT_MODEL`` and constructs
    a real ``LLMAgentNode``; neither participates in the behaviour under test,
    and requiring them would make this a network-shaped test of a logging
    contract.
    """
    node = SSOAuthenticationNode.__new__(SSOAuthenticationNode)
    node.ai_provider = "mock"
    node.ai_model = "mock-model"
    node.llm_agent = _StubLLM(payload)
    return node


def test_sso_role_assignment_email_cannot_forge_a_record(caplog):
    """SITE 1 -- the IdP-supplied email, at the handler layer AND the record layer."""
    node = _sso_node({"roles": ["user"]})

    with emitting(SSO_LOGGER, logging.INFO) as wire:
        with caplog.at_level(logging.INFO, logger=SSO_LOGGER):
            roles = asyncio.run(
                node._ai_role_assignment({"email": EMAIL + FORGED}, "okta")
            )

    assert roles == ["user"]
    # The forging is a claim about LINES on the wire, so that is measured
    # first: one logging call, one line, and no fabricated ERROR record.
    assert len(wire.lines()) == 1, f"forged extra line(s): {wire.lines()}"
    _assert_no_forged_line(wire)
    message = _assert_single_unforged_record(_records(caplog, SSO_LOGGER))
    assert "privilege escalation approved" not in message


def test_sso_role_assignment_does_not_log_the_email_address(caplog):
    """PII disposition: a correlation TAG, never the address itself."""
    node = _sso_node({"roles": ["user", "admin"]})

    with caplog.at_level(logging.INFO, logger=SSO_LOGGER):
        asyncio.run(node._ai_role_assignment({"email": EMAIL}, "okta"))

    record = _records(caplog, SSO_LOGGER)[0]
    rendered = record.getMessage() + repr(record.__dict__)

    # POSITIVE: the address is absent in every form a handler could emit.
    assert EMAIL not in rendered
    assert "victim" not in rendered
    # NEGATIVE: the record is still useful -- it carries a tag that joins
    # across records for this subject, and the roles that were assigned.
    assert f"email:{fingerprint_value(EMAIL)}" in record.getMessage()
    assert "admin" in record.getMessage()


def test_sso_role_assignment_llm_supplied_roles_cannot_forge_a_record(caplog):
    """The roles come back from the LLM, so they are untrusted too.

    The payload here is a STRING, not a list, and that choice is what makes
    this test discriminating. Rendering a LIST goes through ``repr`` on each
    element, which escapes ``\\n`` to a literal backslash-n -- so a
    list-shaped payload cannot forge a line and a test using one PASSES
    against the unfixed code while appearing to pin the behaviour.

    A bare JSON string is a shape this parser genuinely accepts: ``roles``
    then contains the substring ``"user"``, so the membership guard above
    does not fire, and ``str()`` of a string is the string itself -- the
    newline reaches the record unescaped.
    """
    node = _sso_node({"roles": "user" + FORGED})

    with emitting(SSO_LOGGER, logging.INFO) as wire:
        with caplog.at_level(logging.INFO, logger=SSO_LOGGER):
            asyncio.run(node._ai_role_assignment({"email": EMAIL}, "okta"))

    assert len(wire.lines()) == 1, f"forged extra line(s): {wire.lines()}"
    _assert_single_unforged_record(_records(caplog, SSO_LOGGER))


def test_sso_field_mapping_provider_cannot_forge_a_record(caplog):
    """Same-file sibling of the same class: the provider name."""
    node = _sso_node({"email": EMAIL})

    with caplog.at_level(logging.INFO, logger=SSO_LOGGER):
        asyncio.run(node._ai_field_mapping({"mail": EMAIL}, "okta" + FORGED))

    message = _assert_single_unforged_record(_records(caplog, SSO_LOGGER))
    assert "okta" in message  # NEGATIVE: the benign head survives


# --------------------------------------------------------------------------
# Site 2 -- directory search: the caller-supplied search term
# --------------------------------------------------------------------------


def _dir_node(payload: object) -> DirectoryIntegrationNode:
    node = DirectoryIntegrationNode.__new__(DirectoryIntegrationNode)
    node.ai_provider = "mock"
    node.ai_model = "mock-model"
    node.llm_agent = _StubLLM(payload)
    return node


def test_directory_search_query_cannot_forge_a_record(caplog):
    """SITE 2 -- the caller-supplied directory search term."""
    node = _dir_node(
        {"search_users": True, "search_groups": False, "search_attributes": ["cn"]}
    )

    with emitting(DIR_LOGGER, logging.INFO) as wire:
        with caplog.at_level(logging.INFO, logger=DIR_LOGGER):
            asyncio.run(node._ai_search_analysis("find developers" + FORGED))

    assert len(wire.lines()) == 1, f"forged extra line(s): {wire.lines()}"
    _assert_no_forged_line(wire)
    message = _assert_single_unforged_record(_records(caplog, DIR_LOGGER))
    # NEGATIVE: the benign head of the query and the parsed intent survive.
    assert "find developers" in message
    assert "users=True" in message


def test_directory_search_query_cannot_forge_on_the_failure_path(caplog):
    """Same-file sibling: the ``%s`` warning in the except branch.

    Lazy ``%s`` formatting is not a barrier -- ``logging`` interpolates at
    emit time and the newline reaches the record exactly as an f-string's
    would.
    """
    node = _dir_node("not-a-dict-so-json-parsing-yields-a-string")
    node.llm_agent = _StubLLM(None)  # -> empty content -> documented fallback

    with caplog.at_level(logging.WARNING, logger=DIR_LOGGER):
        intent = asyncio.run(node._ai_search_analysis("find developers" + FORGED))

    assert isinstance(intent, dict)  # fell back, as documented
    message = _assert_single_unforged_record(_records(caplog, DIR_LOGGER))
    assert "find developers" in message


def test_directory_role_assignment_does_not_log_the_email_address(caplog):
    """Same-file sibling of site 1, same PII disposition."""
    node = _dir_node(["user", "auditor"])

    with caplog.at_level(logging.INFO, logger=DIR_LOGGER):
        asyncio.run(node._ai_role_assignment({"email": EMAIL + FORGED}))

    records = _records(caplog, DIR_LOGGER)
    message = _assert_single_unforged_record(records)
    assert EMAIL not in message
    assert f"email:{fingerprint_value(EMAIL + FORGED)}" in message
    assert "auditor" in message


# --------------------------------------------------------------------------
# Site 3 -- KaizenNode.run: the prompt (had the bound, lacked the flatten)
# --------------------------------------------------------------------------


def _kaizen_node() -> KaizenNode:
    node = KaizenNode.__new__(KaizenNode)
    node.signature = None
    node.model = "mock-model"
    node.temperature = 0.0
    node.max_tokens = 16
    node.timeout = 1
    node.logger = logging.getLogger(BASE_LOGGER)
    return node


def test_prompt_cannot_forge_a_record(caplog):
    """SITE 3 -- the prompt, which had the bound but not the flatten."""
    node = _kaizen_node()

    with emitting(BASE_LOGGER, logging.DEBUG) as wire:
        with caplog.at_level(logging.DEBUG, logger=BASE_LOGGER):
            node.run(prompt="summarize this" + FORGED)

    # `run` legitimately emits three records (model, prompt, response), so the
    # count here is 3 -- the forging shows up as EXTRA lines beyond them.
    assert len(wire.lines()) == 3, f"forged extra line(s): {wire.lines()}"
    _assert_no_forged_line(wire)
    prompt_records = [
        r for r in _records(caplog, BASE_LOGGER) if r.getMessage().startswith("Prompt:")
    ]
    message = _assert_single_unforged_record(prompt_records)
    assert "summarize this" in message  # NEGATIVE: the benign head survives


def test_prompt_carriage_return_cannot_rewrite_the_line(caplog):
    node = _kaizen_node()

    with caplog.at_level(logging.DEBUG, logger=BASE_LOGGER):
        node.run(prompt="summarize this" + FORGED_CR)

    prompt_records = [
        r for r in _records(caplog, BASE_LOGGER) if r.getMessage().startswith("Prompt:")
    ]
    _assert_single_unforged_record(prompt_records)


def test_prompt_bound_is_retained_alongside_the_flatten(caplog):
    """The bound was the half this site already had; it must not be lost."""
    node = _kaizen_node()

    with caplog.at_level(logging.DEBUG, logger=BASE_LOGGER):
        node.run(prompt="A" * 5000)

    prompt_records = [
        r for r in _records(caplog, BASE_LOGGER) if r.getMessage().startswith("Prompt:")
    ]
    message = _assert_single_unforged_record(prompt_records)
    assert len(message) < 200, f"bound lost, record is {len(message)} chars"
    assert message.endswith("...")


def test_model_name_cannot_forge_a_record(caplog):
    """Same-file sibling: the model name is caller-supplied too."""
    node = _kaizen_node()

    with caplog.at_level(logging.INFO, logger=BASE_LOGGER):
        node.run(prompt="hello", model="stub-model-name" + FORGED)

    exec_records = [
        r
        for r in _records(caplog, BASE_LOGGER)
        if r.getMessage().startswith("Executing KaizenNode")
    ]
    message = _assert_single_unforged_record(exec_records)
    assert "stub-model-name" in message


def test_generated_response_cannot_forge_a_record(caplog):
    """Same-file sibling: the echo response is built from the prompt."""
    node = _kaizen_node()

    with caplog.at_level(logging.DEBUG, logger=BASE_LOGGER):
        node.run(prompt="x" + FORGED)

    response_records = [
        r
        for r in _records(caplog, BASE_LOGGER)
        if r.getMessage().startswith("Generated response:")
    ]
    _assert_single_unforged_record(response_records)
