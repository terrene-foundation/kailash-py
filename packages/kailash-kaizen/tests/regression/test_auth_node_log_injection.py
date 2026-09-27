# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: the kaizen AUTH + node-base log sinks are newline-forgeable.

Three sinks rendered a caller- or IdP-controlled value into a log record with
no newline flatten, so a value carrying ``\\n`` produced a SECOND record that a
downstream reader cannot distinguish from one this process emitted:

* ``kaizen/nodes/auth/sso.py``            -- the SSO assertion's ``email``
* ``kaizen/nodes/auth/directory_integration.py`` -- the directory search term
* ``kaizen/nodes/base.py``                -- the prompt

Prompt and response diagnostics now retain fixed events and counts, without
payload text. Directory search diagnostics retain intent booleans and an
attribute count. Model identifiers and assigned roles retain their existing
bounded display-hygiene contract.

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
  still there (fixed events, counts, intent booleans, and assigned roles). A fix that simply deleted the log statements would pass
  the positive half alone; these controls are what forbid it.

PII disposition (distinct from injection, and NOT satisfied by sanitizing)
--------------------------------------------------------------------------
Role-assignment events retain the assigned roles without an email-derived
field. The former unkeyed fingerprint was recoverable from candidate addresses;
it did not provide the claimed non-reversibility. The implementing log calls are
``packages/kailash-kaizen/src/kaizen/nodes/auth/sso.py:324-326`` and
``packages/kailash-kaizen/src/kaizen/nodes/auth/directory_integration.py:471-473``.
"""

from __future__ import annotations

import asyncio
import inspect
import io
import json
import logging
import pathlib

import pytest

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
    auth_root = root / "packages/kailash-kaizen/src/kaizen/nodes/auth"
    assert pathlib.Path(inspect.getfile(SSOAuthenticationNode)).resolve() == (
        auth_root / "sso.py"
    )
    assert pathlib.Path(inspect.getfile(DirectoryIntegrationNode)).resolve() == (
        auth_root / "directory_integration.py"
    )
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
        self.calls = []

    async def async_run(self, **_kwargs) -> dict:
        self.calls.append(_kwargs)
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


def _assert_email_independent_role_event(caplog, logger_name, assign, expected_roles):
    """Reach both logging layers; an old digest or a hidden extra field fails."""
    standard_fields = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
    expected_message = "AI role assignment completed"
    messages = []
    for email in (EMAIL, "another-person@example.test", EMAIL + FORGED, "", None):
        caplog.clear()
        with emitting(logger_name, logging.INFO) as wire:
            with caplog.at_level(logging.INFO, logger=logger_name):
                roles = asyncio.run(assign(email))
        assert roles == expected_roles
        records = _records(caplog, logger_name)
        message = _assert_single_unforged_record(records)
        assert message == expected_message
        assert wire.lines() == [f"INFO:{logger_name}:{expected_message}"]
        record = records[0]
        assert record.msg == expected_message
        assert record.args == ()
        assert record.role_count == len(expected_roles)
        assert set(record.__dict__) <= standard_fields | {"role_count"}
        raw_record = repr(record.__dict__)
        if email:
            assert email not in raw_record
            assert fingerprint_value(email) not in raw_record
        messages.append(message)
    assert len(set(messages)) == 1


def test_sso_role_assignment_does_not_log_the_email_address(caplog):
    """Different principals produce the same event when roles are equal."""
    node = _sso_node({"roles": ["admin"]})
    _assert_email_independent_role_event(
        caplog,
        SSO_LOGGER,
        lambda email: node._ai_role_assignment({"email": email}, "okta"),
        ["user", "admin"],
    )


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
            intent = asyncio.run(node._ai_search_analysis("find developers" + FORGED))

    assert len(wire.lines()) == 1, f"forged extra line(s): {wire.lines()}"
    _assert_no_forged_line(wire)
    message = _assert_single_unforged_record(_records(caplog, DIR_LOGGER))
    assert message == "AI search analysis completed"
    assert intent == {
        "search_users": True,
        "search_groups": False,
        "search_attributes": ["cn"],
    }
    record = _records(caplog, DIR_LOGGER)[0]
    assert record.search_users is True and record.search_groups is False
    assert record.attribute_count == 1
    assert (
        "find developers" + FORGED in node.llm_agent.calls[0]["messages"][0]["content"]
    )
    assert "find developers" not in repr(vars(record))


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
    assert message == "AI search analysis failed, falling back to default"
    assert intent == {
        "search_users": True,
        "search_groups": False,
        "search_attributes": ["cn", "mail", "uid"],
        "filters": {},
        "reasoning": "Using default search configuration due to AI failure",
    }
    assert "find developers" not in repr(vars(_records(caplog, DIR_LOGGER)[0]))


def test_directory_role_assignment_does_not_log_the_email_address(caplog):
    """Directory provisioning has the same email-independent event contract."""
    node = _dir_node(["auditor"])
    _assert_email_independent_role_event(
        caplog,
        DIR_LOGGER,
        lambda email: node._ai_role_assignment({"email": email}),
        ["user", "auditor"],
    )


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
        r for r in _records(caplog, BASE_LOGGER) if r.getMessage() == "Prompt received"
    ]
    message = _assert_single_unforged_record(prompt_records)
    assert message == "Prompt received"
    assert "summarize this" not in repr(vars(prompt_records[0]))


def test_prompt_carriage_return_cannot_rewrite_the_line(caplog):
    node = _kaizen_node()

    with caplog.at_level(logging.DEBUG, logger=BASE_LOGGER):
        node.run(prompt="summarize this" + FORGED_CR)

    prompt_records = [
        r for r in _records(caplog, BASE_LOGGER) if r.getMessage() == "Prompt received"
    ]
    _assert_single_unforged_record(prompt_records)


def test_prompt_bound_is_retained_alongside_the_flatten(caplog):
    """Long prompts cannot inflate the fixed diagnostic event."""
    node = _kaizen_node()

    with caplog.at_level(logging.DEBUG, logger=BASE_LOGGER):
        node.run(prompt="A" * 5000)

    prompt_records = [
        r for r in _records(caplog, BASE_LOGGER) if r.getMessage() == "Prompt received"
    ]
    message = _assert_single_unforged_record(prompt_records)
    assert len(message) < 200, f"bound lost, record is {len(message)} chars"
    assert message == "Prompt received"
    assert "A" * 100 not in repr(vars(prompt_records[0]))


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
        if r.getMessage() == "Generated response"
    ]
    _assert_single_unforged_record(response_records)


PRIVATE_PAYLOAD = "diagnostic-person@example.invalid"


@pytest.mark.parametrize("surface", ["directory", "sso"])
@pytest.mark.parametrize("role_shape", ["list", "string"])
def test_private_provider_roles_remain_results_not_diagnostics(
    caplog, surface, role_shape
):
    roles = (
        ["user", PRIVATE_PAYLOAD] if role_shape == "list" else "user " + PRIVATE_PAYLOAD
    )
    directory = surface == "directory"
    node = _dir_node(roles) if directory else _sso_node({"roles": roles})
    logger_name = DIR_LOGGER if directory else SSO_LOGGER
    with (
        emitting(logger_name) as wire,
        caplog.at_level(logging.DEBUG, logger=logger_name),
    ):
        result = asyncio.run(
            node._ai_role_assignment({"email": EMAIL})
            if directory
            else node._ai_role_assignment({"email": EMAIL}, "okta")
        )
    assert result == roles
    assert len(node.llm_agent.calls) == 1
    records = _assert_private_records(caplog, logger_name, wire)
    assert len(records) == 1
    assert records[0].getMessage() == "AI role assignment completed"
    assert records[0].role_count == (2 if role_shape == "list" else None)


def _assert_private_records(caplog, logger_name, wire):
    records = _records(caplog, logger_name)
    assert records
    assert PRIVATE_PAYLOAD not in repr([vars(record) for record in records])
    assert PRIVATE_PAYLOAD not in "\n".join(wire.lines())
    assert all(record.exc_info is None for record in records)
    assert all(
        "\n" not in record.getMessage() and "\r" not in record.getMessage()
        for record in records
    )
    _assert_no_forged_line(wire)
    return records


@pytest.mark.parametrize("method", ["_ai_field_mapping", "_ai_role_assignment"])
def test_sso_provider_error_preserves_fallback_without_private_diagnostics(
    caplog, method
):
    error = ValueError(PRIVATE_PAYLOAD + FORGED)
    error.__cause__ = RuntimeError(PRIVATE_PAYLOAD)
    calls = []

    class FailedProvider:
        async def async_run(self, **kwargs):
            calls.append(kwargs)
            raise error

    node = _sso_node({})
    node.attribute_mapping = {"email": "email"}
    node.llm_agent = FailedProvider()
    with (
        emitting(SSO_LOGGER) as wire,
        caplog.at_level(logging.DEBUG, logger=SSO_LOGGER),
    ):
        result = asyncio.run(getattr(node, method)({"email": PRIVATE_PAYLOAD}, "okta"))
    assert result == (
        {"email": PRIVATE_PAYLOAD} if method == "_ai_field_mapping" else ["user"]
    )
    assert len(calls) == 1
    assert PRIVATE_PAYLOAD in calls[0]["messages"][0]["content"]
    assert calls[0]["provider"] == "mock" and calls[0]["model"] == "mock-model"
    records = _assert_private_records(caplog, SSO_LOGGER, wire)
    assert len(records) == 1
    assert records[0].getMessage() == (
        "AI field mapping failed for okta, falling back to rule-based"
        if method == "_ai_field_mapping"
        else "AI role assignment failed, falling back to default"
    )
    assert records[0].error_type == "ValueError" and records[0].error_frames


@pytest.mark.parametrize("users", [True, False, PRIVATE_PAYLOAD + FORGED])
def test_directory_search_preserves_private_provider_input_and_result(caplog, users):
    payload = {
        "search_users": users,
        "search_groups": False,
        "search_attributes": [PRIVATE_PAYLOAD],
        "reasoning": PRIVATE_PAYLOAD,
    }
    node = _dir_node(payload)
    with (
        emitting(DIR_LOGGER) as wire,
        caplog.at_level(logging.DEBUG, logger=DIR_LOGGER),
    ):
        result = asyncio.run(
            node._ai_search_analysis(
                PRIVATE_PAYLOAD + FORGED, {"mail": PRIVATE_PAYLOAD}
            )
        )
    assert result == payload
    call = node.llm_agent.calls[0]
    assert call["provider"] == "mock" and call["model"] == "mock-model"
    assert call["max_completion_tokens"] == 2000
    assert PRIVATE_PAYLOAD + FORGED in call["messages"][0]["content"]
    records = _assert_private_records(caplog, DIR_LOGGER, wire)
    assert len(records) == 1
    assert records[0].getMessage() == "AI search analysis completed"
    assert records[0].search_users is (users is True)
    assert records[0].search_groups is False
    assert records[0].attribute_count == 1


@pytest.mark.parametrize("entry", ["run", "execute"])
def test_base_prompt_and_generated_response_are_not_diagnostics(caplog, entry):
    node = _kaizen_node()
    with (
        emitting(BASE_LOGGER) as wire,
        caplog.at_level(logging.DEBUG, logger=BASE_LOGGER),
    ):
        result = getattr(node, entry)(prompt=PRIVATE_PAYLOAD)
    assert result == {
        "response": f"AI Response to: '{PRIVATE_PAYLOAD[:50]}...' using mock-model",
        "model_used": "mock-model",
        "prompt_length": len(PRIVATE_PAYLOAD),
        "response_length": len(
            f"AI Response to: '{PRIVATE_PAYLOAD[:50]}...' using mock-model"
        ),
    }
    records = _assert_private_records(caplog, BASE_LOGGER, wire)
    assert [r.getMessage() for r in records] == [
        "Executing KaizenNode with model: mock-model",
        "Prompt received",
        "Generated response",
    ]
    assert records[-1].response_length == result["response_length"]


@pytest.mark.parametrize("hostile_type", [False, True])
@pytest.mark.parametrize(
    "entry",
    [
        "run",
        "execute",
        "_ai_search_analysis",
        "_ai_role_assignment",
        "_ai_permission_mapping",
        "_ai_security_settings",
    ],
)
def test_automatic_errors_preserve_results_without_private_diagnostics(
    caplog, monkeypatch, entry, hostile_type
):
    error_type = type(
        "Provider\nFailure" if hostile_type else "ProviderFailure", (ValueError,), {}
    )
    error = error_type(PRIVATE_PAYLOAD + FORGED)
    error.__cause__ = ValueError(PRIVATE_PAYLOAD)
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise error

    class FailedProvider:
        async def async_run(self, **kwargs):
            return fail(**kwargs)

    base = entry in {"run", "execute"}
    node = _kaizen_node() if base else _dir_node({})
    logger = BASE_LOGGER if base else DIR_LOGGER
    if base:
        monkeypatch.setattr(node, "_execute_ai_model", fail)
    else:
        node.llm_agent = FailedProvider()
    with emitting(logger) as wire, caplog.at_level(logging.DEBUG, logger=logger):
        if entry == "run":
            with pytest.raises(ValueError) as caught:
                node.run(prompt=PRIVATE_PAYLOAD)
            assert caught.value is error
        elif entry == "execute":
            from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error

            result = node.execute(prompt=PRIVATE_PAYLOAD)
            assert result == {
                "error": sanitize_provider_error(error, "KaizenNode"),
                "status": "failed",
            }
            assert PRIVATE_PAYLOAD in result["error"]
        else:
            argument = (
                PRIVATE_PAYLOAD
                if entry == "_ai_search_analysis"
                else {"email": PRIVATE_PAYLOAD}
            )
            result = asyncio.run(getattr(node, entry)(argument))
            expected = {
                "_ai_search_analysis": {
                    "search_users": True,
                    "search_groups": False,
                    "search_attributes": ["cn", "mail", "uid"],
                    "filters": {},
                    "reasoning": "Using default search configuration due to AI failure",
                },
                "_ai_role_assignment": ["user"],
                "_ai_permission_mapping": ["read"],
                "_ai_security_settings": {
                    "mfa_required": False,
                    "password_expiry_days": 90,
                    "session_timeout_minutes": 480,
                },
            }
            assert result == expected[entry]
    assert len(calls) == 1
    if base:
        assert calls[0] == {
            "prompt": PRIVATE_PAYLOAD,
            "model": "mock-model",
            "temperature": 0.0,
            "max_tokens": 16,
            "timeout": 1,
        }
    records = _assert_private_records(caplog, logger, wire)
    failures = [record for record in records if record.levelno >= logging.WARNING]
    assert len(failures) == (2 if entry == "execute" else 1)
    assert all(
        record.error_type == ("Provider?Failure" if hostile_type else "ProviderFailure")
        for record in failures
    )
    assert all(record.error_frames for record in failures)
